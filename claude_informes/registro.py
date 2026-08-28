"""El log del hook: una linea por turno, pase lo que pase.

El hook sale en silencio ante cualquier error para no romper la sesion. Sin
este log, un fallo seria invisible. Vive fuera de las carpetas de informes y
fuera de todo repositorio.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

ESCRITO = "escrito"
OMITIDO_UMBRAL = "omitido-umbral"
OMITIDO_CWD = "omitido-cwd"
OMITIDO_SESION = "omitido-sesion"
OMITIDO_GUARDIA = "omitido-guardia"
OMITIDO_REENTRADA = "omitido-reentrada"
OMITIDO_SIN_TEXTO = "omitido-sin-texto"
DENEGADO = "denegado-escritura"
PERMITIDO_POR_ERROR = "permitido-por-error"
PERMITIDO_SIN_RUTA = "permitido-sin-ruta"
PROYECTO_POR_CWD = "proyecto-por-cwd"
ERROR = "ERROR"

SIN_PROYECTO = "-"
_SEPARADOR = " | "
_LINEA = re.compile(r"^(.*?) \| (.*?) \| (.*?) \| (.*)$")


@dataclass(frozen=True)
class Anotacion:
    marca: str
    proyecto: str
    resultado: str
    detalle: str

    @property
    def ruta(self) -> Path | None:
        """Para las lineas de escritura, el detalle es la ruta del informe."""
        return Path(self.detalle) if self.resultado == ESCRITO else None


def ruta_por_defecto(raiz_informes: str | os.PathLike[str]) -> Path:
    """Hermano del archivo, nunca dentro: `E:\\example-reports` -> `...-claude.log`."""
    raiz = Path(raiz_informes)
    return raiz.parent / (raiz.name + ".log")


def formatear(
    resultado: str, proyecto: str, detalle: str, cuando: datetime | None = None
) -> str:
    marca = (cuando or datetime.now()).strftime("%Y-%m-%dT%H:%M:%S")
    limpio = " ".join(str(detalle).split())
    return _SEPARADOR.join([marca, f"{proyecto:<14}", f"{resultado:<18}", limpio])


def anotar(
    ruta_log: str | os.PathLike[str],
    resultado: str,
    proyecto: str,
    detalle: str,
    cuando: datetime | None = None,
) -> None:
    """Anade una linea. Solo anade: nunca reescribe lo ya anotado.

    Puede lanzar; quien llama tiene que tragarselo. El log no vale nada si
    tumba una sesion.
    """
    destino = Path(ruta_log)
    if destino.parent and not destino.parent.exists():
        destino.parent.mkdir(parents=True, exist_ok=True)
    with open(destino, "a", encoding="utf-8", newline="\n") as fichero:
        fichero.write(formatear(resultado, proyecto, detalle, cuando) + "\n")


def leer_linea(linea: str) -> Anotacion | None:
    m = _LINEA.match(linea)
    return Anotacion(*(trozo.strip() for trozo in m.groups())) if m else None


def leer(ruta_log: str | os.PathLike[str]) -> list[Anotacion]:
    """Las anotaciones en orden. Las lineas ilegibles se ignoran una a una."""
    try:
        crudo = Path(ruta_log).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    return [a for a in map(leer_linea, crudo.splitlines()) if a is not None]


def ultimo_escrito(
    anotaciones: list[Anotacion], proyecto: str | None = None
) -> Anotacion | None:
    for anotacion in reversed(anotaciones):
        if anotacion.resultado != ESCRITO:
            continue
        if proyecto is None or anotacion.proyecto == proyecto:
            return anotacion
    return None
