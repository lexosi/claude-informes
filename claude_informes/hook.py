"""Modo hook: lee el payload de Stop por stdin y escribe el informe del turno.

Regla numero uno: este codigo corre en TODAS las sesiones de Claude Code.
Pase lo que pase, sale 0 y en silencio.

Silencio no es invisibilidad: cada turno deja una linea en el log, y el fallo
del log tampoco puede tumbar nada.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import informe as inf
from . import markdown as md
from . import registro as reg
from . import transcript as tr


@dataclass(frozen=True)
class Resultado:
    """Lo que ha pasado en este turno, listo para anotar."""

    resultado: str
    proyecto: str = reg.SIN_PROYECTO
    detalle: str = ""
    ruta: Path | None = None


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


def procesar(payload: dict, configuracion: cfg.Configuracion) -> Resultado:
    """Decide y escribe. Devuelve que ha pasado, para el log.

    Puede lanzar: quien llama es responsable de tragarse la excepcion y de
    anotar el ERROR.
    """
    if not isinstance(payload, dict):
        return Resultado(reg.ERROR, detalle=f"payload que no es un objeto: {type(payload).__name__}")
    if payload.get("stop_hook_active"):
        return Resultado(reg.OMITIDO_REENTRADA, detalle="stop_hook_active")

    cwd = payload.get("cwd")
    if cfg.es_la_propia_herramienta(cwd):
        return Resultado(reg.OMITIDO_GUARDIA, detalle=f"cwd dentro de la herramienta: {cwd}")

    proyecto = cfg.buscar_proyecto(cwd, configuracion)
    if proyecto is None:
        return Resultado(reg.OMITIDO_CWD, detalle=f"cwd fuera de la lista: {cwd!r}")

    respuesta = _markdown_del_payload(payload)
    if not respuesta.strip():
        return Resultado(reg.OMITIDO_SIN_TEXTO, proyecto.nombre, "sin texto de respuesta")
    lineas = md.contar_lineas(respuesta)
    if not md.supera_umbral(respuesta, proyecto.umbral_lineas):
        return Resultado(
            reg.OMITIDO_UMBRAL,
            proyecto.nombre,
            f"{lineas} lineas, umbral {proyecto.umbral_lineas}",
        )

    rama, head = inf.datos_git(str(cwd))
    sobre = inf.construir(
        respuesta,
        session_id=payload.get("session_id"),
        cwd=cwd,
        git_branch=rama,
        git_head=head,
    )
    destino = inf.escribir(proyecto.raiz_informes, proyecto.nombre, sobre)
    return Resultado(reg.ESCRITO, proyecto.nombre, str(destino), destino)


def main(entrada=None, ruta_config: str | os.PathLike[str] | None = None) -> int:
    """Punto de entrada del hook. SIEMPRE devuelve 0."""
    configuracion = None
    try:
        flujo = entrada if entrada is not None else sys.stdin
        payload = json.loads(flujo.read())
        configuracion = cfg.cargar(ruta_config)
        resultado = procesar(payload, configuracion)
    except Exception as error:  # noqa: BLE001 - por diseno: nada puede escapar
        resultado = Resultado(reg.ERROR, detalle=f"{type(error).__name__}: {error}")

    try:
        ruta_log = (configuracion or cfg.cargar(ruta_config)).ruta_log
        reg.anotar(ruta_log, resultado.resultado, resultado.proyecto, resultado.detalle)
    except Exception:  # noqa: BLE001 - si el log falla, la sesion sigue igual
        pass
    return 0
