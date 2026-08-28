"""Modo backfill: reconstruye informes de turnos pasados desde un transcript."""

from __future__ import annotations

import os
from pathlib import Path

from . import informe as inf
from . import markdown as md
from . import transcript as tr


def reconstruir(
    ruta_transcript: str | os.PathLike[str],
    raiz_informes: str | os.PathLike[str],
    proyecto: str,
    *,
    umbral: int = 5,
    limite: int | None = None,
    simular: bool = False,
) -> list[dict]:
    """Un fichero por turno. Devuelve una entrada por turno considerado."""
    raiz = Path(raiz_informes)
    resultado: list[dict] = []
    seleccionados = tr.turnos(ruta_transcript)
    if limite is not None:
        seleccionados = seleccionados[-limite:]

    for turno in seleccionados:
        respuesta = turno["respuesta_markdown"]
        if not md.supera_umbral(respuesta, umbral):
            resultado.append(
                {
                    "escrito": False,
                    "motivo": f"umbral ({md.contar_lineas(respuesta)} lineas)",
                    "ruta": None,
                    "turno": turno,
                }
            )
            continue
        cwd = turno.get("cwd") or ""
        _, head = inf.datos_git(str(cwd)) if cwd else (None, None)
        sobre = inf.construir(
            respuesta,
            session_id=turno.get("session_id"),
            cwd=cwd or None,
            cuando=turno.get("timestamp"),
            git_branch=turno.get("git_branch"),
            git_head=head,
        )
        if simular:
            dia = inf.carpeta_del_dia(raiz, proyecto, sobre["fecha"])
            resultado.append(
                {
                    "escrito": False,
                    "motivo": "simulacion",
                    "ruta": inf.nombre_de_fichero(dia, sobre),
                    "turno": turno,
                }
            )
            continue
        destino = inf.escribir(raiz, proyecto, sobre)
        resultado.append(
            {"escrito": True, "motivo": None, "ruta": destino, "turno": turno}
        )
    return resultado
