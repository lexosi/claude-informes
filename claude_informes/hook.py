"""Modo hook: lee el payload de Stop por stdin y escribe el informe del turno.

Regla numero uno: este codigo corre en TODAS las sesiones de Claude Code.
Pase lo que pase, sale 0 y en silencio.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from . import config as cfg
from . import informe as inf
from . import markdown as md
from . import transcript as tr


def _apuntar(mensaje: str) -> None:
    """Traza opcional a fichero. Jamas a stdout ni a stderr."""
    destino = os.environ.get("CLAUDE_INFORMES_LOG")
    if not destino:
        return
    try:
        with open(destino, "a", encoding="utf-8") as fichero:
            fichero.write(mensaje + "\n")
    except Exception:
        pass


def _markdown_del_payload(payload: dict) -> str:
    """El camino normal no parsea nada: el texto ya viene en el payload."""
    directo = payload.get("last_assistant_message")
    if isinstance(directo, str) and directo.strip():
        return directo
    ruta = payload.get("transcript_path")
    if isinstance(ruta, str) and ruta.strip():
        ultimo = tr.ultimo_turno(ruta)
        if ultimo:
            return ultimo["respuesta_markdown"]
    return ""


def procesar(payload: dict, configuracion: cfg.Configuracion) -> Path | None:
    """Decide y escribe. Devuelve la ruta escrita, o None si no toca escribir.

    Puede lanzar: quien llama es responsable de tragarse la excepcion.
    """
    if not isinstance(payload, dict):
        return None
    if payload.get("stop_hook_active"):
        _apuntar("stop_hook_active: no se hace nada")
        return None

    cwd = payload.get("cwd")
    if cfg.es_la_propia_herramienta(cwd):
        _apuntar("cwd es la propia herramienta: no se escribe")
        return None
    proyecto = cfg.buscar_proyecto(cwd, configuracion)
    if proyecto is None:
        _apuntar(f"cwd fuera de la lista: {cwd!r}")
        return None

    respuesta = _markdown_del_payload(payload)
    if not respuesta.strip():
        _apuntar("sin texto de respuesta")
        return None
    if not md.supera_umbral(respuesta, proyecto.umbral_lineas):
        _apuntar(f"por debajo del umbral ({md.contar_lineas(respuesta)} lineas)")
        return None

    rama, head = inf.datos_git(str(cwd))
    sobre = inf.construir(
        respuesta,
        session_id=payload.get("session_id"),
        cwd=cwd,
        git_branch=rama,
        git_head=head,
    )
    destino = inf.escribir(proyecto.raiz_informes, proyecto.nombre, sobre)
    _apuntar(f"escrito {destino}")
    return destino


def main(entrada=None, ruta_config: str | os.PathLike[str] | None = None) -> int:
    """Punto de entrada del hook. SIEMPRE devuelve 0."""
    try:
        flujo = entrada if entrada is not None else sys.stdin
        crudo = flujo.read()
        payload = json.loads(crudo)
        procesar(payload, cfg.cargar(ruta_config))
    except Exception as error:  # noqa: BLE001 - por diseno: nada puede escapar
        try:
            _apuntar(f"excepcion tragada: {type(error).__name__}: {error}")
        except Exception:
            pass
    return 0
