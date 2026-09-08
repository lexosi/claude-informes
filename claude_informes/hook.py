"""Hook mode: reads the Stop payload from stdin and writes the turn's report.

Rule number one: this code runs in EVERY Claude Code session. No matter what, it
exits 0 and silently.

Silence is not invisibility: every turn leaves a line in the log, and the log's
failure cannot bring anything down either.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import streams
from . import report as inf
from . import markdown as md
from . import journal as reg
from . import transcript as tr


@dataclass(frozen=True)
class Resultado:
    """What happened in this turn, ready to record."""

    resultado: str
    proyecto: str = reg.SIN_PROYECTO
    detalle: str = ""
    ruta: Path | None = None
    aviso: tuple[str, str] | None = None
    """(result, detail) of an extra line recorded BEFORE its own."""


def proyecto_del_transcript(
    ruta_transcript: str, configuracion: cfg.Configuracion
) -> cfg.Proyecto | None:
    """Maps the transcript's directory to the config's project.

    The mapping is explicit and checkable: the directory name is compared with
    the slug that each project's declared `cwd` produces. There is no attempt to
    undo the slug, which is an ambiguous operation (`e--proyectos-alfa-audit`
    could be either a subdirectory of `alfa` or the sibling project
    `alfa-audit`). Without an exact match, there is no mapping.
    """
    carpeta = os.path.normcase(Path(ruta_transcript).parent.name)
    for proyecto in configuracion.proyectos:
        if not proyecto.activo:
            continue
        if os.path.normcase(tr.slug_de_cwd(proyecto.raiz)) == carpeta:
            return proyecto
    return None


def proyecto_del_turno(
    payload: dict, configuracion: cfg.Configuracion
) -> tuple[cfg.Proyecto | None, str, str]:
    """The project comes from the SESSION, not from the directory the shell is in.

    The payload's `cwd` follows the `cd` commands made during the turn, so
    archiving by it puts turns in the wrong folder and loses others. The
    `transcript_path` identifies the session and does not move.

    When there is a `transcript_path`, it **rules**: if it does not map to any
    project in the config, the session is not watched and is not archived.
    Falling back to cwd here would reopen the same hole, because a shell strolling
    through a watched project would archive turns that are not its own again.

    The cwd only comes into play when there is no transcript to trust.

    Returns (project, degradation reason, omission reason).
    """
    ruta = payload.get("transcript_path")
    if isinstance(ruta, str) and ruta.strip():
        proyecto = proyecto_del_transcript(ruta, configuracion)
        if proyecto is not None:
            return proyecto, "", ""
        # The slug is ambiguous for subdirectories, but the transcript's first
        # record carries the startup cwd without any ambiguity.
        arranque = tr.cwd_de_arranque(ruta)
        proyecto = cfg.buscar_proyecto(arranque, configuracion)
        if proyecto is not None:
            return proyecto, "", ""
        return None, "", motivo_de_omision(ruta, arranque)
    proyecto = cfg.buscar_proyecto(payload.get("cwd"), configuracion)
    return proyecto, "sin transcript_path", ""


def nombre_que_tendria(ruta_transcript: str, arranque: str | None) -> str:
    """What the project would be called if you registered it right now."""
    if isinstance(arranque, str) and arranque.strip():
        return md.slug_llano(Path(arranque).name) or "sin-nombre"
    tramo = Path(ruta_transcript).parent.name.rsplit("-", 1)[-1]
    return md.slug_llano(tramo) or "sin-nombre"


def motivo_de_omision(ruta_transcript: str, arranque: str | None) -> str:
    """What is needed to be able to recover the turn later."""
    return (
        "proyecto no registrado"
        f"; nombre={nombre_que_tendria(ruta_transcript, arranque)}"
        f"; arranque={arranque or '?'}"
        f"; transcript={ruta_transcript}"
    )


def _markdown_del_payload(payload: dict) -> str:
    """The normal path parses nothing: the text already comes in the payload."""
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
    """Decide and write. Returns what happened, for the log.

    It may raise: the caller is responsible for swallowing the exception and
    recording the ERROR.
    """
    if not isinstance(payload, dict):
        return Resultado(reg.ERROR, detalle=f"payload que no es un objeto: {type(payload).__name__}")
    if payload.get("stop_hook_active"):
        return Resultado(reg.OMITIDO_REENTRADA, detalle="stop_hook_active")

    cwd = payload.get("cwd")
    proyecto, degradacion, omision = proyecto_del_turno(payload, configuracion)
    if omision:
        return Resultado(reg.OMITIDO_SESION, detalle=omision)
    if proyecto is None:
        return Resultado(
            reg.OMITIDO_CWD,
            detalle=f"{degradacion}; cwd fuera de la lista: {cwd!r}",
        )

    # A warning is only issued when the degraded path does archive something: it
    # is the case in which a turn can end up in another project's folder.
    aviso = (
        (reg.PROYECTO_POR_CWD, f"{degradacion}; proyecto tomado del cwd: {cwd}")
        if degradacion
        else None
    )

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
    try:
        destino = inf.escribir(proyecto.raiz_informes, proyecto.nombre, sobre)
    except inf.FalloDeEscritura as fallo:
        # The only ERROR that knows whose turn it was. Without a project, a path
        # and a session, the log line cannot be checked against anything and the
        # failure remains, in practice, silent.
        return Resultado(
            reg.ERROR,
            proyecto.nombre,
            f"{fallo}; ruta={fallo.ruta}; sesion={payload.get('session_id')}",
            aviso=aviso,
        )
    return Resultado(reg.ESCRITO, proyecto.nombre, str(destino), destino, aviso)


def main(entrada=None, ruta_config: str | os.PathLike[str] | None = None) -> int:
    """Hook entry point. ALWAYS returns 0."""
    configuracion = None
    try:
        flujo = entrada if entrada is not None else sys.stdin
        payload = streams.leer_payload(flujo)
        configuracion = cfg.cargar(ruta_config)
        resultado = procesar(payload, configuracion)
    except Exception as error:  # noqa: BLE001 - by design: nothing can escape
        resultado = Resultado(reg.ERROR, detalle=f"{type(error).__name__}: {error}")

    try:
        ruta_log = (configuracion or cfg.cargar(ruta_config)).ruta_log
        if resultado.aviso is not None:
            reg.anotar(ruta_log, resultado.aviso[0], resultado.proyecto, resultado.aviso[1])
        reg.anotar(ruta_log, resultado.resultado, resultado.proyecto, resultado.detalle)
    except Exception:  # noqa: BLE001 - if the log fails, the session goes on unchanged
        pass
    return 0
