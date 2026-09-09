"""Per-project configuration. Lives OUTSIDE the watched repositories.

Adding a project means adding an entry to the config JSON.
The code knows no specific path.
"""

from __future__ import annotations

import glob
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

# --- Config keys: English is the only valid form; the Castilian keys are
# TRANSITIONAL compatibility aliases, not a second supported spelling. They are
# read so that a config written before the rename keeps working, and they are
# slated for removal in 2.0.0. A config should be written in English; the
# example and the README show only the English keys. When both spellings appear
# on the same object, the English one wins and the alias is dropped.
_ALIAS_SUPERIOR = {
    "proyectos": "projects",
    "raiz_informes": "reports_root",
    "ruta_log": "log_path",
}
_ALIAS_ENTRADA = {
    "nombre": "name",
    "umbral_lineas": "line_threshold",
    "activo": "active",
    "raiz_informes": "reports_root",
}


def _renombrar(destino: dict, alias: dict) -> None:
    """Apply one alias map in place: English wins, the Castilian alias is dropped."""
    for viejo, nuevo in alias.items():
        if viejo in destino and nuevo not in destino:
            destino[nuevo] = destino.pop(viejo)
        else:
            destino.pop(viejo, None)


def _canonizar_entrada(entrada):
    """One project entry with its keys in English. `cwd`/`raiz` both map to `path`."""
    if not isinstance(entrada, dict):
        return entrada
    d = dict(entrada)
    if "path" not in d:
        if isinstance(d.get("cwd"), str):
            d["path"] = d["cwd"]
        elif isinstance(d.get("raiz"), str):
            d["path"] = d["raiz"]
    d.pop("cwd", None)
    d.pop("raiz", None)
    _renombrar(d, _ALIAS_ENTRADA)
    return d


def _canonizar(crudo):
    """Translate a raw config to the English keys the parser reads.

    A single uniform alias pass, applied at the top level and to each entry; no
    per-key special case. A bare list of entries (a legacy shape) is wrapped as
    ``{"projects": [...]}`` so the rest is uniform.

    A legacy ``active: false`` entry (the old way of turning a project off
    without deleting its line) is TRANSITIONALLY translated to an exclusion: its
    path is escaped into ``exclusions`` and the entry is dropped, so a config
    written before the rename keeps NOT archiving that project -- the only change
    is the log label, which becomes the more precise ``excluido-patron``. The
    model itself has no ``active``; this translation dies with the aliases in
    2.0.0.
    """
    if isinstance(crudo, list):
        crudo = {"projects": crudo}
    if not isinstance(crudo, dict):
        return crudo
    d = dict(crudo)
    _renombrar(d, _ALIAS_SUPERIOR)
    entradas = d.get("projects")
    if isinstance(entradas, list):
        vivas, excluidas = [], []
        for entrada in entradas:
            canonica = _canonizar_entrada(entrada)
            if isinstance(canonica, dict) and not bool(canonica.get("active", True)):
                ruta = canonica.get("path")
                if isinstance(ruta, str) and ruta.strip():
                    excluidas.append(glob.escape(ruta))
                continue
            vivas.append(canonica)
        d["projects"] = vivas
        if excluidas:
            d["exclusions"] = list(d.get("exclusions") or []) + excluidas
    return d


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
    declarado = entrada.get("name")
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
    crudo = _canonizar(json.loads(destino.read_text(encoding="utf-8")))

    es_dict = isinstance(crudo, dict)
    entradas = crudo.get("projects") if es_dict else crudo
    raiz_informes = crudo.get("reports_root") if es_dict else None
    if not isinstance(raiz_informes, str) or not raiz_informes.strip():
        raiz_informes = raiz_informes_por_defecto()

    declarada = crudo.get("log_path") if es_dict else None
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
        raiz = entrada.get("path")
        if not isinstance(raiz, str) or not raiz.strip():
            continue
        umbral = entrada.get("line_threshold", UMBRAL_POR_DEFECTO)
        if not isinstance(umbral, int) or isinstance(umbral, bool) or umbral < 0:
            umbral = UMBRAL_POR_DEFECTO
        propia = entrada.get("reports_root")
        if not isinstance(propia, str) or not propia.strip():
            propia = raiz_informes
        proyectos.append(
            Proyecto(
                nombre=_nombre_de(entrada, raiz),
                raiz=str(Path(raiz)),
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
