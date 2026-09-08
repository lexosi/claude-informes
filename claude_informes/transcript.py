"""Reading Claude Code's JSONL transcript."""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path


def directorio_de_proyectos() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def slug_de_cwd(cwd: str) -> str:
    r"""The folder name Claude Code gives the project: separators and colons
    become hyphens. E.g. ``<drive>:\path\project`` -> ``<drive>--path-project``.
    """
    return re.sub(r"[\\/:]", "-", str(cwd))


def localizar(
    *, cwd: str | None = None, session_id: str | None = None, raiz: Path | None = None
) -> Path | None:
    """Find a transcript by session or by project (the most recent one)."""
    base = raiz or directorio_de_proyectos()
    if not base.is_dir():
        return None
    if session_id:
        for encontrado in base.glob(f"*/{session_id}.jsonl"):
            return encontrado
        return None
    if not cwd:
        return None
    buscado = os.path.normcase(slug_de_cwd(cwd))
    candidatos: list[Path] = []
    for carpeta in base.iterdir():
        if carpeta.is_dir() and os.path.normcase(carpeta.name) == buscado:
            candidatos.extend(carpeta.glob("*.jsonl"))
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: p.stat().st_mtime)


def _texto_de(mensaje: dict) -> str:
    """Concatenate the text of the `text` blocks.

    A block whose `text` is not a string (a number, `null`, a list) is skipped
    like the ones that carry no text: `"".join` would blow up with a
    `TypeError`, and that brought down the reading of the whole transcript --and
    with it the CLI's backfill, with a raw traceback-- over a single malformed
    turn.
    """
    partes = [
        bloque["text"]
        for bloque in mensaje.get("content", [])
        if isinstance(bloque, dict)
        and bloque.get("type") == "text"
        and isinstance(bloque.get("text"), str)
    ]
    return "".join(partes)


# The four ways reading a transcript can end. The old code collapsed the last
# three into a single silent `[]`, so a format change and a legitimately empty
# session looked identical.
LEIDO = "leido"        # at least one closed turn was extracted
VACIO = "vacio"        # readable, but no `assistant` line at all: nothing to archive yet
DERIVA = "deriva"      # readable, `assistant` lines PRESENT but none produced a turn
ILEGIBLE = "ilegible"  # the file could not be read (permissions, gone, IO)


@dataclass(frozen=True)
class Lectura:
    """The result of reading a transcript, WITH why it may carry no turns.

    Only `LEIDO` carries turns. `DERIVA` is the alarm: there are assistant lines
    but not one of them could be turned into a turn, which is what happens when
    the JSONL format drifts (a renamed field, a new `content` shape). It is a
    SUSPICION, stated as a fact (`detalle` says how many assistant lines yielded
    zero turns), not a certainty.
    """

    estado: str
    turnos: list[dict] = field(default_factory=list)
    arranque: str | None = None
    lineas_asistente: int = 0
    detalle: str = ""


def leer(ruta: str | os.PathLike[str]) -> Lectura:
    """Read a transcript once, returning the turns AND why they may be empty.

    Criterion for a turn: type=='assistant' AND stop_reason=='end_turn' AND some
    non-empty 'text' block. Broken lines are ignored one by one, and a block with
    a 'text' that is not a string is skipped the same way (see `_texto_de`): a
    malformed turn is omitted, it does not bring down the reading. `arranque` is
    the `cwd` of the first record that carries one --the startup directory, which
    does not move with the `cd`s of the turn.
    """
    try:
        crudo = Path(ruta).read_text(encoding="utf-8", errors="replace")
    except Exception as error:
        return Lectura(ILEGIBLE, detalle=f"{type(error).__name__}: {error}")

    resultado: list[dict] = []
    arranque: str | None = None
    asistentes = 0
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            registro = json.loads(linea)
        except Exception:
            continue
        if not isinstance(registro, dict):
            continue
        if arranque is None:
            cwd = registro.get("cwd")
            if isinstance(cwd, str) and cwd.strip():
                arranque = cwd
        if registro.get("type") != "assistant":
            continue
        asistentes += 1
        mensaje = registro.get("message")
        if not isinstance(mensaje, dict) or mensaje.get("stop_reason") != "end_turn":
            continue
        texto = _texto_de(mensaje)
        if not texto.strip():
            continue
        resultado.append(
            {
                "respuesta_markdown": texto,
                "timestamp": registro.get("timestamp"),
                "session_id": registro.get("sessionId"),
                "cwd": registro.get("cwd"),
                "git_branch": registro.get("gitBranch"),
                "uuid": registro.get("uuid"),
            }
        )

    if resultado:
        return Lectura(LEIDO, resultado, arranque, asistentes)
    if asistentes:
        return Lectura(
            DERIVA,
            arranque=arranque,
            lineas_asistente=asistentes,
            detalle=f"{asistentes} lineas de asistente, 0 turnos extraibles",
        )
    return Lectura(VACIO, arranque=arranque)


def turnos(ruta: str | os.PathLike[str]) -> list[dict]:
    """Just the closed turns. See `leer` for the reason an empty list can hide."""
    return leer(ruta).turnos


def ultimo_turno(ruta: str | os.PathLike[str]) -> dict | None:
    encontrados = leer(ruta).turnos
    return encontrados[-1] if encontrados else None


def cwd_de_arranque(ruta: str | os.PathLike[str]) -> str | None:
    """The `cwd` of the first record: where the session was opened (see `leer`)."""
    return leer(ruta).arranque
