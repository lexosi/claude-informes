"""Per-project configuration. Lives OUTSIDE the watched repositories.

Adding a project means adding an entry to the config JSON.
The code knows no specific path.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import markdown as md
from . import journal as reg

VAR_ENTORNO = "CLAUDE_INFORMES_CONFIG"
VAR_LOG = "CLAUDE_INFORMES_LOG"
UMBRAL_POR_DEFECTO = 5

# Name of the config folder and file for the user. The REAL config lives OUTSIDE
# the repository (see README, "Why the config lives outside the repo"): that way
# the repo is published without anyone's path, and changing machines does not
# generate conflicts in a versioned file.
CARPETA_APP = "claude-informes"
NOMBRE_CONFIG = "proyectos.json"


def raiz_de_la_herramienta() -> Path:
    """The directory of the claude-informes package itself (the repo root)."""
    return Path(__file__).resolve().parent.parent


def dir_config_usuario() -> Path:
    """Per-user config folder, following each OS's convention.

    - Windows: ``%APPDATA%\\claude-informes`` (the user's Roaming folder, where
      Windows keeps app config that follows the profile).
    - macOS: ``~/Library/Application Support/claude-informes`` (the standard
      application-data directory on macOS).
    - Linux and others: ``$XDG_CONFIG_HOME/claude-informes`` or, if it is not
      defined, ``~/.config/claude-informes`` (the XDG Base Directory
      specification, the de facto standard on Linux).
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / CARPETA_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / CARPETA_APP
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / CARPETA_APP


def ruta_config_usuario() -> Path:
    """The user config file in the OS's standard location."""
    return dir_config_usuario() / NOMBRE_CONFIG


def ruta_de_ejemplo() -> Path:
    """The example versioned in the repo. Fictitious paths, never real ones."""
    return raiz_de_la_herramienta() / "config" / "proyectos.ejemplo.json"


@dataclass(frozen=True)
class Proyecto:
    nombre: str
    raiz: str
    activo: bool
    umbral_lineas: int
    raiz_informes: Path
    """Where THIS project is archived. By default, the global root."""


@dataclass(frozen=True)
class Configuracion:
    raiz_informes: Path
    """Global root: the one inherited by projects that do not declare their own."""

    ruta_log: Path
    """The hook's log. Just one, for all projects."""

    proyectos: list[Proyecto] = field(default_factory=list)
    """Explicit project roots: a `path` that is one project, optionally carrying
    overrides (line_threshold, reports_root, name). An entry that only tweaks a
    threshold and an entry that names a standalone project subtree are the same
    thing; which one it is depends only on where the watched roots fall."""

    roots: list[str] = field(default_factory=list)
    """Watched containers: each immediate child directory is a project."""

    exclusions: list[str] = field(default_factory=list)
    """Glob patterns; a resolved project matching one is not archived."""


def normalizar(ruta: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(ruta))))


def raiz_informes_por_defecto() -> Path:
    return raiz_de_la_herramienta() / "informes"


def ruta_de_log(declarada, raiz_informes) -> Path:
    """The environment rules, then the config, and if not, the archive's sibling."""
    del_entorno = os.environ.get(VAR_LOG)
    if del_entorno:
        return Path(del_entorno)
    if isinstance(declarada, str) and declarada.strip():
        return Path(declarada)
    return reg.ruta_por_defecto(raiz_informes)


def por_defecto() -> Configuracion:
    """No readable config: no projects, but the log still exists."""
    raiz = raiz_informes_por_defecto()
    return Configuracion(raiz_informes=raiz, ruta_log=ruta_de_log(None, raiz))


def ruta_de_config() -> Path | None:
    """The config to use, or None if there is none.

    Resolution order, documented and tested:
      1. The environment variable ``CLAUDE_INFORMES_CONFIG``, if defined. Always
         wins, whether or not the file exists: whoever sets it knows what they
         are doing.
      2. The user config in the OS's standard location, if it exists.
      3. Nothing: ``None``. The repository contains NO real config, only the
         example, so there is no third place to look here.
    """
    del_entorno = os.environ.get(VAR_ENTORNO)
    if del_entorno:
        return Path(del_entorno)
    usuario = ruta_config_usuario()
    if usuario.exists():
        return usuario
    return None


def mensaje_sin_config() -> str:
    """What to tell whoever starts without a config. Never a traceback."""
    return (
        "There is no claude-informes configuration.\n"
        f"The user file should be at:\n    {ruta_config_usuario()}\n\n"
        "Create it from the example with:\n"
        "    python -m claude_informes init\n\n"
        "Or point to your own with the environment variable "
        f"{VAR_ENTORNO}, or with --config.\n"
        f"The versioned example is at: {ruta_de_ejemplo()}"
    )


def _nombre_de(entrada: dict, raiz: str) -> str:
    """The name comes from the config; renaming the directory does not split the history."""
    declarado = entrada.get("nombre")
    if isinstance(declarado, str) and declarado.strip():
        return declarado.strip()
    return md.slug_llano(Path(raiz).name) or "sin-nombre"


def cargar(ruta: str | os.PathLike[str] | None = None) -> Configuracion:
    """Read the configuration. If it is missing or broken, there is no project."""
    try:
        return cargar_estricto(ruta)
    except Exception:
        return por_defecto()


def cargar_estricto(ruta: str | os.PathLike[str] | None = None) -> Configuracion:
    """Like `cargar`, but blows up if the config cannot be read.

    Whoever watches writes needs to know whether the config is trustworthy:
    without it, it cannot assert that a path is protected, and then it allows.
    """
    destino = Path(ruta) if ruta is not None else ruta_de_config()
    if destino is None:
        raise FileNotFoundError("no claude-informes configuration")
    crudo = json.loads(destino.read_text(encoding="utf-8"))

    es_dict = isinstance(crudo, dict)
    entradas = crudo.get("proyectos") if es_dict else crudo
    raiz_informes = crudo.get("raiz_informes") if es_dict else None
    if not isinstance(raiz_informes, str) or not raiz_informes.strip():
        raiz_informes = raiz_informes_por_defecto()

    declarada = crudo.get("ruta_log") if es_dict else None
    ruta_log = ruta_de_log(declarada, raiz_informes)

    roots = [
        r
        for r in ((crudo.get("roots") if es_dict else None) or [])
        if isinstance(r, str) and r.strip()
    ]
    exclusions = [
        g
        for g in ((crudo.get("exclusions") if es_dict else None) or [])
        if isinstance(g, str) and g.strip()
    ]

    if not isinstance(entradas, list):
        return Configuracion(
            raiz_informes=Path(raiz_informes),
            ruta_log=ruta_log,
            roots=roots,
            exclusions=exclusions,
        )

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
        roots=roots,
        exclusions=exclusions,
    )


def _esta_dentro(candidato: str, raiz: str) -> bool:
    if candidato == raiz:
        return True
    return candidato.startswith(raiz.rstrip(os.sep) + os.sep)


def buscar_proyecto(cwd: str | None, configuracion: Configuracion) -> Proyecto | None:
    """Allowlist: the cwd must be the root of an active project or hang off it.

    Returns None for any cwd outside the list. On a tie, the longest root wins.

    The tool is no longer a special case. It was while `raiz_informes` pointed
    inside `claude-informes/informes/`: back then one of its own turns would have
    written into its own output folder, inside a repo. Since the archive lives in
    its own root, outside any git tree, that premise does not exist, and the guard
    only served to throw away the turns of whoever was working on the tool
    itself. What it really protected --that no archive destination falls inside
    the tool or any repository-- is asserted by the tests of the real config.
    """
    if not isinstance(cwd, str) or not cwd.strip():
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
