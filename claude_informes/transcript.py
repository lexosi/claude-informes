"""Lectura del transcript JSONL de Claude Code."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def directorio_de_proyectos() -> Path:
    return Path(os.environ.get("CLAUDE_CONFIG_DIR", Path.home() / ".claude")) / "projects"


def slug_de_cwd(cwd: str) -> str:
    r"""`E:\example-projects\loopward` -> `E--example-projects-loopward`."""
    return re.sub(r"[\\/:]", "-", str(cwd))


def localizar(
    *, cwd: str | None = None, session_id: str | None = None, raiz: Path | None = None
) -> Path | None:
    """Encuentra un transcript por sesion o por proyecto (el mas reciente)."""
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
    partes = [
        bloque.get("text", "")
        for bloque in mensaje.get("content", [])
        if isinstance(bloque, dict) and bloque.get("type") == "text"
    ]
    return "".join(partes)


def turnos(ruta: str | os.PathLike[str]) -> list[dict]:
    """Turnos cerrados del asistente, en orden.

    Criterio: type=='assistant' AND stop_reason=='end_turn' AND algun bloque
    'text' no vacio. Las lineas rotas se ignoran una a una.
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
    """El `cwd` del primer registro: donde se abrio la sesion.

    Los registros siguientes llevan el cwd del momento, que se mueve con cada
    `cd`. El primero no: identifica el directorio de arranque.
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
