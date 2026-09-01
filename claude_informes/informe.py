"""El sobre JSON y su escritura en disco. Un fichero por turno, siempre."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from . import markdown as md

_PATRON_ORDINAL = re.compile(r"^(\d{2,})-")


def _git(cwd: str, *argumentos: str) -> str | None:
    """Consulta a git, sin ruido y sin colgarse. None si no se puede."""
    try:
        salida = subprocess.run(
            ["git", *argumentos],
            cwd=cwd,
            capture_output=True,
            text=True,
            # git habla utf-8; `text=True` a secas decodifica con el
            # encoding de la consola (cp1252 aqui): una rama con acento
            # salia con mojibake, o reventaba y se perdian rama Y head.
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if salida.returncode != 0:
        return None
    valor = salida.stdout.strip()
    return valor or None


def datos_git(cwd: str) -> tuple[str | None, str | None]:
    if not cwd or not os.path.isdir(cwd):
        return None, None
    rama = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(cwd, "rev-parse", "HEAD")
    return rama, head


def _momento(cuando: str | datetime | None) -> datetime:
    """Normaliza a hora local. Acepta ISO-8601 (con o sin Z)."""
    if isinstance(cuando, datetime):
        instante = cuando
    elif isinstance(cuando, str) and cuando.strip():
        texto = cuando.strip().replace("Z", "+00:00")
        try:
            instante = datetime.fromisoformat(texto)
        except ValueError:
            return datetime.now()
    else:
        return datetime.now()
    if instante.tzinfo is not None:
        instante = instante.astimezone()
    return instante.replace(tzinfo=None)


def construir(
    respuesta_markdown: str,
    *,
    session_id: str | None,
    cwd: str | None,
    cuando: str | datetime | None = None,
    git_branch: str | None = None,
    git_head: str | None = None,
) -> dict:
    """El sobre. Su unico requisito es llevar el markdown integro."""
    instante = _momento(cuando)
    return {
        "fecha": instante.strftime("%Y-%m-%d"),
        "hora": instante.strftime("%H:%M:%S"),
        "session_id": session_id,
        "cwd": cwd,
        "git_branch": git_branch,
        "git_head": git_head,
        "respuesta_markdown": respuesta_markdown,
        "secciones": md.secciones(respuesta_markdown),
        "bloques_codigo": md.bloques_codigo(respuesta_markdown),
        "casillas": md.casillas(respuesta_markdown),
    }


def subcarpeta(base: Path, nombre: str) -> Path:
    """Reutiliza la carpeta que ya exista. Nunca una variante ni un sufijo.

    En Windows `Loopward` y `loopward` son la misma carpeta; se devuelve la
    que ya esta en disco para no acabar con dos historicos distintos.
    """
    buscado = os.path.normcase(nombre)
    try:
        for hijo in base.iterdir():
            if hijo.is_dir() and os.path.normcase(hijo.name) == buscado:
                return hijo
    except Exception:
        pass
    return base / nombre


def carpeta_del_dia(raiz_informes: Path, proyecto: str, fecha: str) -> Path:
    """`<raiz>/<proyecto>/<AAAA-MM-DD>`, reutilizando los dos niveles."""
    return subcarpeta(subcarpeta(Path(raiz_informes), proyecto), fecha)


def _cuenta_para_el_ordinal(nombre: str) -> bool:
    """Un `.json` ya escrito, o un `.json.tmp` que tiene su ordinal cogido.

    Los `.tmp` cuentan porque son el cerrojo: mientras uno exista, su numero
    esta reservado. Si no se contaran, dos turnos simultaneos elegirian el
    mismo, que es justo lo que el cerrojo evita.
    """
    return nombre.endswith(".json") or nombre.endswith(".json.tmp")


def siguiente_ordinal(directorio: Path) -> int:
    """El ordinal empieza en 01 en cada carpeta de dia."""
    mayor = 0
    try:
        existentes = list(directorio.iterdir())
    except Exception:
        return 1
    for fichero in existentes:
        if not _cuenta_para_el_ordinal(fichero.name):
            continue
        m = _PATRON_ORDINAL.match(fichero.name)
        if m:
            mayor = max(mayor, int(m.group(1)))
    return mayor + 1


def nombre_de_fichero(directorio: Path, sobre: dict) -> Path:
    """`NN-slug.json`. Sin fecha ni proyecto: ya los aporta la ruta."""
    slug = md.nombre_desde_markdown(sobre["respuesta_markdown"])
    ordinal = siguiente_ordinal(directorio)
    while True:
        destino = directorio / f"{ordinal:02d}-{slug}.json"
        if not destino.exists():
            return destino
        ordinal += 1


def _reservar(directorio: Path, slug: str) -> Path:
    """Reserva un nombre creando su `.tmp` en exclusiva. Devuelve el `.tmp`.

    El cerrojo NO puede ser el fichero de destino. Cuando lo era, cualquier
    fallo posterior --y bastaba un caracter que no cupiera en el encoding--
    dejaba un `.json` de cero bytes indistinguible de un informe de verdad.
    El `.json` ahora solo aparece por el `os.replace` final.

    La garantia es la de siempre, ni mas ni menos: dos turnos a la vez no
    pueden quedarse con el MISMO NOMBRE, porque gana quien logre el O_EXCL y
    el otro prueba con el siguiente ordinal. Para que siga siendo cierta,
    `siguiente_ordinal` cuenta tambien los `.tmp`.
    """
    ordinal = siguiente_ordinal(directorio)
    for _ in range(1000):
        temporal = directorio / f"{ordinal:02d}-{slug}.json.tmp"
        try:
            descriptor = os.open(temporal, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            ordinal += 1
            continue
        os.close(descriptor)
        return temporal
    raise OSError(f"no hay ordinal libre en {directorio}")


class FalloDeEscritura(Exception):
    """Un informe que no llego a existir, y el nombre que iba a tener.

    Lleva la ruta encima para que la linea de ERROR del log pueda decir QUE
    turno se perdio. Sin ella el log solo dice que algo fallo, y `ultimo` no
    tiene nada que contrastar.
    """

    def __init__(self, ruta: Path, causa: BaseException) -> None:
        super().__init__(f"{type(causa).__name__}: {causa}")
        self.ruta = ruta
        self.causa = causa


def escribir(raiz_informes: Path, proyecto: str, sobre: dict) -> Path:
    """Crea `<raiz>/<proyecto>/<fecha>/` si falta y escribe el sobre.

    Orden: se reserva el `.tmp`, se escribe entero, y solo entonces aparece
    el `.json`. Si algo falla por el camino no queda nada en disco: ni un
    informe a cero ni un `.tmp` huerfano.
    """
    directorio = carpeta_del_dia(Path(raiz_informes), proyecto, sobre["fecha"])
    directorio.mkdir(parents=True, exist_ok=True)
    temporal = _reservar(directorio, md.nombre_desde_markdown(sobre["respuesta_markdown"]))
    destino = temporal.with_name(temporal.name[: -len(".tmp")])
    try:
        texto = json.dumps(sobre, ensure_ascii=False, indent=2) + "\n"
        # newline="\n": en Windows, write_text convertiria los saltos a CRLF y
        # el archivo quedaria con dos formatos distintos segun quien lo
        # escribiera.
        temporal.write_text(texto, encoding="utf-8", newline="\n")
        os.replace(temporal, destino)
    except BaseException as error:
        try:
            temporal.unlink(missing_ok=True)
        except Exception:  # noqa: BLE001 - la causa original manda
            pass
        raise FalloDeEscritura(destino, error) from error
    return destino
