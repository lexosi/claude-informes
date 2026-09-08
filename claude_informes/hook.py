"""Modo hook: lee el payload de Stop por stdin y escribe el informe del turno.

Regla numero uno: este codigo corre en TODAS las sesiones de Claude Code.
Pase lo que pase, sale 0 y en silencio.

Silencio no es invisibilidad: cada turno deja una linea en el log, y el fallo
del log tampoco puede tumbar nada.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from pathlib import Path

from . import config as cfg
from . import flujos
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
    aviso: tuple[str, str] | None = None
    """(resultado, detalle) de una linea extra que se anota ANTES que la suya."""


def proyecto_del_transcript(
    ruta_transcript: str, configuracion: cfg.Configuracion
) -> cfg.Proyecto | None:
    """Mapea el directorio del transcript al proyecto de la config.

    El mapeo es explicito y comprobable: se compara el nombre del directorio
    con el slug que produce el `cwd` declarado de cada proyecto. No se intenta
    deshacer el slug, que es una operacion ambigua (`e--proyectos-alfa-audit`
    tanto podria ser un subdirectorio de `alfa` como el proyecto hermano
    `alfa-audit`). Sin coincidencia exacta, no hay mapeo.
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
    """El proyecto sale de la SESION, no del directorio donde este la shell.

    El `cwd` del payload sigue a los `cd` que se hagan durante el turno, asi
    que archivar por el mete turnos en la carpeta equivocada y pierde otros.
    El `transcript_path` identifica la sesion y no se mueve.

    Cuando hay `transcript_path`, **manda**: si no mapea a ningun proyecto de
    la config, la sesion no esta vigilada y no se archiva. Caer al cwd aqui
    reabriria el mismo agujero, porque una shell paseando por un proyecto
    vigilado volveria a archivar turnos que no son suyos.

    El cwd solo entra cuando no hay transcript del que fiarse.

    Devuelve (proyecto, motivo de degradacion, motivo de omision).
    """
    ruta = payload.get("transcript_path")
    if isinstance(ruta, str) and ruta.strip():
        proyecto = proyecto_del_transcript(ruta, configuracion)
        if proyecto is not None:
            return proyecto, "", ""
        # El slug es ambiguo para los subdirectorios, pero el primer registro
        # del transcript lleva el cwd de arranque sin ambiguedad ninguna.
        arranque = tr.cwd_de_arranque(ruta)
        proyecto = cfg.buscar_proyecto(arranque, configuracion)
        if proyecto is not None:
            return proyecto, "", ""
        return None, "", motivo_de_omision(ruta, arranque)
    proyecto = cfg.buscar_proyecto(payload.get("cwd"), configuracion)
    return proyecto, "sin transcript_path", ""


def nombre_que_tendria(ruta_transcript: str, arranque: str | None) -> str:
    """Como se llamaria el proyecto si lo registraras ahora mismo."""
    if isinstance(arranque, str) and arranque.strip():
        return md.slug_llano(Path(arranque).name) or "sin-nombre"
    tramo = Path(ruta_transcript).parent.name.rsplit("-", 1)[-1]
    return md.slug_llano(tramo) or "sin-nombre"


def motivo_de_omision(ruta_transcript: str, arranque: str | None) -> str:
    """Lo que hace falta para poder recuperar el turno mas tarde."""
    return (
        "proyecto no registrado"
        f"; nombre={nombre_que_tendria(ruta_transcript, arranque)}"
        f"; arranque={arranque or '?'}"
        f"; transcript={ruta_transcript}"
    )


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
    proyecto, degradacion, omision = proyecto_del_turno(payload, configuracion)
    if omision:
        return Resultado(reg.OMITIDO_SESION, detalle=omision)
    if proyecto is None:
        return Resultado(
            reg.OMITIDO_CWD,
            detalle=f"{degradacion}; cwd fuera de la lista: {cwd!r}",
        )

    # Solo se avisa cuando el camino degradado llega a archivar algo: es el
    # caso en que un turno puede acabar en la carpeta de otro proyecto.
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
        # El unico ERROR que sabe de quien era el turno. Sin proyecto, sin
        # ruta y sin sesion, la linea del log no se puede contrastar contra
        # nada y el fallo sigue siendo, en la practica, silencioso.
        return Resultado(
            reg.ERROR,
            proyecto.nombre,
            f"{fallo}; ruta={fallo.ruta}; sesion={payload.get('session_id')}",
            aviso=aviso,
        )
    return Resultado(reg.ESCRITO, proyecto.nombre, str(destino), destino, aviso)


def main(entrada=None, ruta_config: str | os.PathLike[str] | None = None) -> int:
    """Punto de entrada del hook. SIEMPRE devuelve 0."""
    configuracion = None
    try:
        flujo = entrada if entrada is not None else sys.stdin
        payload = flujos.leer_payload(flujo)
        configuracion = cfg.cargar(ruta_config)
        resultado = procesar(payload, configuracion)
    except Exception as error:  # noqa: BLE001 - por diseno: nada puede escapar
        resultado = Resultado(reg.ERROR, detalle=f"{type(error).__name__}: {error}")

    try:
        ruta_log = (configuracion or cfg.cargar(ruta_config)).ruta_log
        if resultado.aviso is not None:
            reg.anotar(ruta_log, resultado.aviso[0], resultado.proyecto, resultado.aviso[1])
        reg.anotar(ruta_log, resultado.resultado, resultado.proyecto, resultado.detalle)
    except Exception:  # noqa: BLE001 - si el log falla, la sesion sigue igual
        pass
    return 0
