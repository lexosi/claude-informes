"""Configuracion por proyecto. Vive FUERA de los repositorios vigilados.

Anadir un proyecto es anadir una entrada al JSON de configuracion.
El codigo no conoce ninguna ruta concreta.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from . import markdown as md
from . import registro as reg

VAR_ENTORNO = "CLAUDE_INFORMES_CONFIG"
VAR_LOG = "CLAUDE_INFORMES_LOG"
UMBRAL_POR_DEFECTO = 5


def raiz_de_la_herramienta() -> Path:
    """El propio E:\\example-projects\\claude-informes."""
    return Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Proyecto:
    nombre: str
    raiz: str
    activo: bool
    umbral_lineas: int
    raiz_informes: Path
    """Donde se archiva ESTE proyecto. Por defecto, la raiz global."""


@dataclass(frozen=True)
class Configuracion:
    raiz_informes: Path
    """Raiz global: la que heredan los proyectos que no declaran la suya."""

    ruta_log: Path
    """El log del hook. Uno solo, para todos los proyectos."""

    proyectos: list[Proyecto] = field(default_factory=list)


def normalizar(ruta: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(ruta))))


def raiz_informes_por_defecto() -> Path:
    return raiz_de_la_herramienta() / "informes"


def ruta_de_log(declarada, raiz_informes) -> Path:
    """Manda el entorno, luego la config, y si no, el hermano del archivo."""
    del_entorno = os.environ.get(VAR_LOG)
    if del_entorno:
        return Path(del_entorno)
    if isinstance(declarada, str) and declarada.strip():
        return Path(declarada)
    return reg.ruta_por_defecto(raiz_informes)


def por_defecto() -> Configuracion:
    """Sin config legible: ningun proyecto, pero el log sigue existiendo."""
    raiz = raiz_informes_por_defecto()
    return Configuracion(raiz_informes=raiz, ruta_log=ruta_de_log(None, raiz))


def ruta_de_config() -> Path:
    """Ruta del fichero de configuracion, sin comprobar que exista."""
    del_entorno = os.environ.get(VAR_ENTORNO)
    if del_entorno:
        return Path(del_entorno)
    propia = raiz_de_la_herramienta() / "config" / "proyectos.json"
    if propia.exists():
        return propia
    return Path.home() / ".claude-informes" / "proyectos.json"


def _nombre_de(entrada: dict, raiz: str) -> str:
    """El nombre sale de la config; renombrar el directorio no parte el historico."""
    declarado = entrada.get("nombre")
    if isinstance(declarado, str) and declarado.strip():
        return declarado.strip()
    return md.slug_llano(Path(raiz).name) or "sin-nombre"


def cargar(ruta: str | os.PathLike[str] | None = None) -> Configuracion:
    """Lee la configuracion. Si falta o esta rota, no hay ningun proyecto."""
    destino = Path(ruta) if ruta is not None else ruta_de_config()
    try:
        crudo = json.loads(destino.read_text(encoding="utf-8"))
    except Exception:
        return por_defecto()

    entradas = crudo.get("proyectos") if isinstance(crudo, dict) else crudo
    raiz_informes = crudo.get("raiz_informes") if isinstance(crudo, dict) else None
    if not isinstance(raiz_informes, str) or not raiz_informes.strip():
        raiz_informes = raiz_informes_por_defecto()

    declarada = crudo.get("ruta_log") if isinstance(crudo, dict) else None
    ruta_log = ruta_de_log(declarada, raiz_informes)

    if not isinstance(entradas, list):
        return Configuracion(raiz_informes=Path(raiz_informes), ruta_log=ruta_log)

    proyectos = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue
        raiz = entrada.get("cwd") or entrada.get("raiz")
        if not isinstance(raiz, str) or not raiz.strip():
            continue
        umbral = entrada.get("umbral_lineas", UMBRAL_POR_DEFECTO)
        if not isinstance(umbral, int) or isinstance(umbral, bool) or umbral < 0:
            umbral = UMBRAL_POR_DEFECTO
        propia = entrada.get("raiz_informes")
        if not isinstance(propia, str) or not propia.strip():
            propia = raiz_informes
        proyectos.append(
            Proyecto(
                nombre=_nombre_de(entrada, raiz),
                raiz=str(Path(raiz)),
                activo=bool(entrada.get("activo", True)),
                umbral_lineas=umbral,
                raiz_informes=Path(propia),
            )
        )
    return Configuracion(
        raiz_informes=Path(raiz_informes),
        ruta_log=ruta_log,
        proyectos=proyectos,
    )


def _esta_dentro(candidato: str, raiz: str) -> bool:
    if candidato == raiz:
        return True
    return candidato.startswith(raiz.rstrip(os.sep) + os.sep)


def es_la_propia_herramienta(cwd: str | None) -> bool:
    """Guardia: el destino de los informes vive dentro de este proyecto.

    Si algun dia claude-informes acaba en la lista de vigilados, un turno suyo
    escribiria dentro de su propia carpeta de salida. No se escribe, y punto.
    """
    if not isinstance(cwd, str) or not cwd.strip():
        return False
    return _esta_dentro(normalizar(cwd), normalizar(raiz_de_la_herramienta()))


def buscar_proyecto(cwd: str | None, configuracion: Configuracion) -> Proyecto | None:
    """Lista blanca: el cwd debe ser la raiz de un proyecto activo o colgar de ella.

    Devuelve None para cualquier cwd fuera de la lista, y tambien para el
    propio claude-informes. Ante empate, gana la raiz mas larga.
    """
    if not isinstance(cwd, str) or not cwd.strip():
        return None
    if es_la_propia_herramienta(cwd):
        return None
    objetivo = normalizar(cwd)
    candidatos = [
        p
        for p in configuracion.proyectos
        if p.activo and _esta_dentro(objetivo, normalizar(p.raiz))
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: len(normalizar(p.raiz)))
