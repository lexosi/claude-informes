"""Reading Claude Code's JSONL transcript."""

from __future__ import annotations

import json
import os
import re
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


def turnos(ruta: str | os.PathLike[str]) -> list[dict]:
    """Closed assistant turns, in order.

    Criterion: type=='assistant' AND stop_reason=='end_turn' AND some non-empty
    'text' block. Broken lines are ignored one by one, and a block with a 'text'
    that is not a string is skipped the same way (see `_texto_de`): a malformed
    turn is omitted, it does not bring down the reading.
    """
    resultado: list[dict] = []
    try:
        crudo = Path(ruta).read_text(encoding="utf-8", errors="replace")
    except Exception:
        return []
    for linea in crudo.splitlines():
        linea = linea.strip()
        if not linea:
            continue
        try:
            registro = json.loads(linea)
        except Exception:
            continue
        if not isinstance(registro, dict) or registro.get("type") != "assistant":
            continue
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
    return resultado


def ultimo_turno(ruta: str | os.PathLike[str]) -> dict | None:
    encontrados = turnos(ruta)
    return encontrados[-1] if encontrados else None


def cwd_de_arranque(ruta: str | os.PathLike[str]) -> str | None:
    """The `cwd` of the first record: where the session was opened.

    The following records carry the cwd of the moment, which moves with every
    `cd`. The first one does not: it identifies the startup directory.
    """
    try:
        with open(ruta, encoding="utf-8", errors="replace") as fichero:
            for linea in fichero:
                linea = linea.strip()
                if not linea:
                    continue
                try:
                    registro = json.loads(linea)
                except Exception:
                    continue
                cwd = registro.get("cwd") if isinstance(registro, dict) else None
                if isinstance(cwd, str) and cwd.strip():
                    return cwd
    except Exception:
        return None
    return None
