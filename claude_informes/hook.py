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
) -> tuple[cfg.Proyecto | None, str, tuple[str, str] | None]:
    """The project comes from the SESSION, not from the directory the shell is in.

    The payload's `cwd` follows the `cd` commands made during the turn, so
    archiving by it puts turns in the wrong folder and loses others. The
    `transcript_path` identifies the session and does not move.

    When there is a `transcript_path`, it **rules**: if it does not map to any
    project in the config, the session is not watched and is not archived.
    Falling back to cwd here would reopen the same hole, because a shell strolling
    through a watched project would archive turns that are not its own again.

    The cwd only comes into play when there is no transcript to trust.

    Returns (project, degradation reason, omission). The omission, when there is
    one, is a `(label, detail)` pair so the RIGHT reason reaches the log: a
    transcript that cannot be read or whose format drifted is not the same as a
    project that is simply not registered --logging the wrong one is worse than
    not logging, because the log is the only way to find out.
    """
    ruta = payload.get("transcript_path")
    if isinstance(ruta, str) and ruta.strip():
        proyecto = proyecto_del_transcript(ruta, configuracion)
        if proyecto is not None:
            return proyecto, "", None
        # The folder slug did not map. Read the transcript ONCE: its first record
        # carries the startup cwd without the slug's ambiguity, and reading also
        # tells us whether the file is unreadable or its format drifted --neither
        # of which is "project not registered".
        lectura = tr.leer(ruta)
        if lectura.estado == tr.ILEGIBLE:
            return None, "", (reg.TRANSCRIPT_ILEGIBLE, f"transcript ilegible ({lectura.detalle}); transcript={ruta}")
        if lectura.estado == tr.DERIVA:
            return None, "", (reg.DERIVA_FORMATO, f"{lectura.detalle}; transcript={ruta}")
        proyecto = cfg.buscar_proyecto(lectura.arranque, configuracion)
        if proyecto is not None:
            return proyecto, "", None
        return None, "", (reg.OMITIDO_SESION, motivo_de_omision(ruta, lectura.arranque))
    proyecto = cfg.buscar_proyecto(payload.get("cwd"), configuracion)
    return proyecto, "sin transcript_path", None


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


def _markdown_del_payload(payload: dict) -> tuple[str, str]:
    """The turn's markdown and the transcript-read state behind it.

    The normal path parses nothing: the text already comes in the payload
    (`last_assistant_message`), and the state is `LEIDO`. Only when that field is
    missing does it fall back to the transcript, and it returns the read state so
    that a fallback which comes back empty can say WHY (drift, unreadable) instead
    of being logged as a plain 'no text'.
    """
    directo = payload.get("last_assistant_message")
    if isinstance(directo, str) and directo.strip():
        return directo, tr.LEIDO
    ruta = payload.get("transcript_path")
    if isinstance(ruta, str) and ruta.strip():
        lectura = tr.leer(ruta)
        if lectura.turnos:
            return lectura.turnos[-1]["respuesta_markdown"], tr.LEIDO
        return "", lectura.estado
    return "", tr.VACIO


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
    if omision is not None:
        etiqueta, detalle = omision
        return Resultado(etiqueta, detalle=detalle)
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

    respuesta, estado_texto = _markdown_del_payload(payload)
    if not respuesta.strip():
        if estado_texto == tr.DERIVA:
            return Resultado(
                reg.DERIVA_FORMATO,
                proyecto.nombre,
                "transcript con lineas de asistente y ningun turno extraible",
            )
        if estado_texto == tr.ILEGIBLE:
            return Resultado(
                reg.TRANSCRIPT_ILEGIBLE, proyecto.nombre, "transcript_path ilegible"
            )
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
