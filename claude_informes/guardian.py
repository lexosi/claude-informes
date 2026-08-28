"""Modo guardian: un hook PreToolUse que impide escribir informes a mano.

Los informes los escribe el hook Stop. Cualquier otra escritura dentro del
archivo es un error, casi siempre el de anunciar un fichero que no existe.

Regla numero uno, y es la CONTRARIA a la del hook Stop: esto **falla abierto**.
Cualquier excepcion, config ilegible o ruta que no se pueda resolver termina
en "permitido", en silencio. Un guardian que bloquea por error es peor que no
tener guardian: rompe sesiones ajenas por un fallo suyo.

Solo deniega cuando la ruta esta INEQUIVOCAMENTE dentro del archivo.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import registro as reg

# Herramientas cuya ruta de destino es un dato estructurado y sin ambiguedad.
# `Bash` queda fuera a proposito: adivinar rutas dentro de una linea de shell
# da falsos positivos, y ante la duda se permite.
HERRAMIENTAS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
CAMPOS_DE_RUTA = ("file_path", "notebook_path", "path")

# Los servidores MCP no tienen esquema comun: ni el nombre de la herramienta
# ni el del campo de la ruta estan estandarizados. Lo que sigue es heuristica,
# y por eso solo sirve para DENEGAR mejor; permitir sigue garantizado.
PREFIJO_MCP = "mcp__"

# Verbos que delatan una escritura. Se comparan contra las palabras del nombre
# de la herramienta, no como subcadena: si no, `get_output` contendria "put".
VERBOS_DE_ESCRITURA = frozenset(
    {
        "write", "edit", "create", "mkdir", "move", "rename", "copy",
        "delete", "remove", "unlink", "save", "append", "patch",
        "truncate", "upload", "put", "overwrite",
    }
)

CAMPOS_MCP = CAMPOS_DE_RUTA + (
    "filepath",
    "filename",
    "file",
    "destination",
    "destination_path",
    "dest",
    "target",
    "target_path",
    "source",
    "source_path",
    "dir",
    "dir_path",
    "directory",
    "folder",
    "folder_path",
    "paths",
    "files",
)

MENSAJE = (
    "claude-informes: {ruta} esta dentro del archivo de informes ({motivo}).\n"
    "Los informes los escribe el hook Stop al terminar el turno; no se "
    "escriben ni se editan a mano.\n"
    "Para saber cual fue el ultimo y comprobar que existe de verdad:\n"
    "    cd {herramienta}\n"
    "    .venv\\Scripts\\python -m claude_informes ultimo{proyecto}"
)


def es_mcp(nombre) -> bool:
    return isinstance(nombre, str) and nombre.startswith(PREFIJO_MCP)


def parece_escritura(nombre: str) -> bool:
    """Solo mira el nombre de la herramienta, no el del servidor.

    `mcp__servidor__write_file` escribe; `mcp__servidor__read_file` no. Un
    verbo desconocido se trata como lectura: fallar abierto manda.
    """
    palabras = re.split(r"[^a-z0-9]+", nombre.split("__")[-1].lower())
    return bool(VERBOS_DE_ESCRITURA & set(palabras))


def campos_a_mirar(nombre) -> tuple[str, ...] | None:
    """Que campos de `tool_input` pueden llevar la ruta. None = no mirar."""
    if nombre in HERRAMIENTAS:
        return CAMPOS_DE_RUTA
    if es_mcp(nombre) and parece_escritura(nombre):
        return CAMPOS_MCP
    return None


def rutas_del_payload(payload: dict, campos: tuple[str, ...]) -> list[str]:
    """Las rutas de destino declaradas por la herramienta."""
    entrada = payload.get("tool_input")
    if not isinstance(entrada, dict):
        return []
    rutas = []
    for campo in campos:
        valor = entrada.get(campo)
        if isinstance(valor, str) and valor.strip():
            rutas.append(valor)
        elif isinstance(valor, list):
            rutas.extend(v for v in valor if isinstance(v, str) and v.strip())
    for edicion in entrada.get("edits", []) or []:
        if isinstance(edicion, dict):
            valor = edicion.get("file_path")
            if isinstance(valor, str) and valor.strip():
                rutas.append(valor)
    return rutas


def es_un_punto_ciego(payload: dict) -> bool:
    """Una herramienta MCP que dice escribir y no declara ninguna ruta.

    Se permite, porque no se puede afirmar nada, pero no en silencio.
    """
    if not isinstance(payload, dict):
        return False
    nombre = payload.get("tool_name")
    if not (es_mcp(nombre) and parece_escritura(nombre)):
        return False
    return not rutas_del_payload(payload, CAMPOS_MCP)


def resolver(ruta: str, cwd: str | None) -> str:
    """Absoluta y real: relativas, `..` y enlaces incluidos."""
    candidata = Path(ruta)
    if not candidata.is_absolute() and isinstance(cwd, str) and cwd.strip():
        candidata = Path(cwd) / candidata
    return os.path.normcase(os.path.realpath(str(candidata)))


def zonas_protegidas(configuracion: cfg.Configuracion) -> list[tuple[str, str, str]]:
    """(ruta normalizada, tipo, proyecto) de todo lo que no se toca a mano.

    Salen de la config: la raiz global, la de cada proyecto, y el log.
    """
    zonas = [
        (os.path.normcase(os.path.realpath(configuracion.raiz_informes)), "carpeta", ""),
        (os.path.normcase(os.path.realpath(configuracion.ruta_log)), "fichero", ""),
    ]
    for proyecto in configuracion.proyectos:
        zonas.append(
            (
                os.path.normcase(os.path.realpath(proyecto.raiz_informes)),
                "carpeta",
                proyecto.nombre,
            )
        )
    # La mas especifica primero: una raiz propia anidada dentro de la global
    # tiene que ganarle a la global.
    return sorted(zonas, key=lambda z: len(z[0]), reverse=True)


def _proyecto_de_la_carpeta(
    destino: str, zona: str, configuracion: cfg.Configuracion
) -> str:
    """Bajo una raiz compartida, el proyecto es la primera carpeta.

    No se adivina: solo cuenta si ese nombre esta en la config.
    """
    resto = destino[len(zona.rstrip(os.sep)) :].strip(os.sep)
    if not resto:
        return ""
    primera = resto.split(os.sep, 1)[0]
    for proyecto in configuracion.proyectos:
        if os.path.normcase(proyecto.nombre) == primera:
            return proyecto.nombre
    return ""


def _dentro(destino: str, zona: str, tipo: str) -> bool:
    if destino == zona:
        return True
    if tipo != "carpeta":
        return False
    return destino.startswith(zona.rstrip(os.sep) + os.sep)


@dataclass(frozen=True)
class Hallazgo:
    ruta: str
    motivo: str
    proyecto: str = ""


def revisar(payload: dict, configuracion: cfg.Configuracion) -> Hallazgo | None:
    """Devuelve el hallazgo si hay que denegar. None es permitir.

    Puede lanzar: quien llama permite y calla.
    """
    if not isinstance(payload, dict):
        return None
    campos = campos_a_mirar(payload.get("tool_name"))
    if campos is None:
        return None

    zonas = zonas_protegidas(configuracion)
    cwd = payload.get("cwd")
    for ruta in rutas_del_payload(payload, campos):
        destino = resolver(ruta, cwd)
        for zona, tipo, proyecto in zonas:
            if _dentro(destino, zona, tipo):
                donde = "el log del hook" if tipo == "fichero" else f"archivo: {zona}"
                if not proyecto and tipo == "carpeta":
                    proyecto = _proyecto_de_la_carpeta(destino, zona, configuracion)
                return Hallazgo(destino, donde, proyecto)
    return None


def denegar(hallazgo: Hallazgo) -> str:
    razon = MENSAJE.format(
        ruta=hallazgo.ruta,
        motivo=hallazgo.motivo,
        herramienta=cfg.raiz_de_la_herramienta(),
        proyecto=f" --proyecto {hallazgo.proyecto}" if hallazgo.proyecto else "",
    )
    return json.dumps(
        {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": razon,
            }
        },
        ensure_ascii=False,
    )


def main(entrada=None, salida=None, ruta_config: str | os.PathLike[str] | None = None) -> int:
    """Punto de entrada del guardian. SIEMPRE devuelve 0.

    Sin salida = sin decision = la herramienta sigue su curso normal.
    """
    flujo_salida = salida if salida is not None else sys.stdout
    anotacion = None
    try:
        flujo = entrada if entrada is not None else sys.stdin
        payload = json.loads(flujo.read())
        configuracion = cfg.cargar_estricto(ruta_config)
        hallazgo = revisar(payload, configuracion)
        if hallazgo is not None:
            flujo_salida.write(denegar(hallazgo))
            anotacion = (
                configuracion.ruta_log,
                reg.DENEGADO,
                hallazgo.proyecto or reg.SIN_PROYECTO,
                f"{payload.get('tool_name')} -> {hallazgo.ruta}",
            )
        elif es_un_punto_ciego(payload):
            anotacion = (
                configuracion.ruta_log,
                reg.PERMITIDO_SIN_RUTA,
                reg.SIN_PROYECTO,
                f"{payload.get('tool_name')}: sin ruta reconocible en tool_input",
            )
    except Exception as error:  # noqa: BLE001 - falla abierto, siempre
        try:
            anotacion = (
                cfg.por_defecto().ruta_log,
                reg.PERMITIDO_POR_ERROR,
                reg.SIN_PROYECTO,
                f"{type(error).__name__}: {error}",
            )
        except Exception:
            anotacion = None

    if anotacion is not None:
        try:
            reg.anotar(*anotacion)
        except Exception:  # noqa: BLE001 - el log no puede tumbar una sesion
            pass
    return 0
