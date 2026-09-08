"""Guardian mode: a PreToolUse hook that prevents writing reports by hand.

The reports are written by the Stop hook. Any other write inside the archive is
a mistake, almost always the mistake of announcing a file that does not exist.

Rule number one, and it is the OPPOSITE of the Stop hook's: this **fails open**.
Any exception, unreadable config or path that cannot be resolved ends in
"allowed", silently. A guardian that blocks by mistake is worse than having no
guardian: it breaks other people's sessions through a fault of its own.

It only denies when the path is UNEQUIVOCALLY inside the archive.
"""

from __future__ import annotations

import json
import os
import re
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import flujos
from . import registro as reg

# Tools whose destination path is structured data with no ambiguity. `Bash` is
# left out on purpose: guessing paths inside a shell line gives false positives,
# and when in doubt it is allowed.
HERRAMIENTAS = frozenset({"Write", "Edit", "MultiEdit", "NotebookEdit"})
CAMPOS_DE_RUTA = ("file_path", "notebook_path", "path")

# MCP servers do not share a common schema: neither the tool name nor the path
# field name are standardized. What follows is a heuristic, and that is why it
# only serves to DENY better; allowing remains guaranteed.
PREFIJO_MCP = "mcp__"

# Verbs that give away a write. They are compared against the words of the tool
# name, not as a substring: otherwise `get_output` would contain "put".
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
    """Only looks at the tool name, not the server's.

    `mcp__servidor__write_file` writes; `mcp__servidor__read_file` does not. An
    unknown verb is treated as a read: failing open rules.
    """
    palabras = re.split(r"[^a-z0-9]+", nombre.split("__")[-1].lower())
    return bool(VERBOS_DE_ESCRITURA & set(palabras))


def campos_a_mirar(nombre) -> tuple[str, ...] | None:
    """Which `tool_input` fields may carry the path. None = do not look."""
    if nombre in HERRAMIENTAS:
        return CAMPOS_DE_RUTA
    if es_mcp(nombre) and parece_escritura(nombre):
        return CAMPOS_MCP
    return None


def rutas_del_payload(payload: dict, campos: tuple[str, ...]) -> list[str]:
    """The destination paths declared by the tool."""
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
    """An MCP tool that says it writes and declares no path.

    It is allowed, because nothing can be asserted, but not silently.
    """
    if not isinstance(payload, dict):
        return False
    nombre = payload.get("tool_name")
    if not (es_mcp(nombre) and parece_escritura(nombre)):
        return False
    return not rutas_del_payload(payload, CAMPOS_MCP)


def resolver(ruta: str, cwd: str | None) -> str:
    """Absolute and real: relatives, `..` and links included."""
    candidata = Path(ruta)
    if not candidata.is_absolute() and isinstance(cwd, str) and cwd.strip():
        candidata = Path(cwd) / candidata
    return os.path.normcase(os.path.realpath(str(candidata)))


def zonas_protegidas(configuracion: cfg.Configuracion) -> list[tuple[str, str, str]]:
    """(normalized path, type, project) of everything that is not touched by hand.

    They come from the config: the global root, each project's, and the log.
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
    # The most specific one first: a project root nested inside the global one
    # has to beat the global one.
    return sorted(zonas, key=lambda z: len(z[0]), reverse=True)


def _proyecto_de_la_carpeta(
    destino: str, zona: str, configuracion: cfg.Configuracion
) -> str:
    """Under a shared root, the project is the first folder.

    It is not guessed: it only counts if that name is in the config.
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
    """Returns the finding if it has to deny. None means allow.

    It may raise: the caller allows and stays quiet.
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
    """Guardian entry point. ALWAYS returns 0.

    No output = no decision = the tool goes on its normal course.
    """
    flujo_salida = salida if salida is not None else sys.stdout
    anotacion = None
    try:
        flujo = entrada if entrada is not None else sys.stdin
        payload = flujos.leer_payload(flujo)
        configuracion = cfg.cargar_estricto(ruta_config)
        hallazgo = revisar(payload, configuracion)
        if hallazgo is not None:
            flujos.escribir(flujo_salida, denegar(hallazgo))
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
    except Exception as error:  # noqa: BLE001 - fails open, always
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
        except Exception:  # noqa: BLE001 - the log cannot bring down a session
            pass
    return 0
