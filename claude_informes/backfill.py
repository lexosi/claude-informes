"""Backfill mode: reconstructs reports of past turns from a transcript."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import report as inf
from . import markdown as md
from . import journal as reg
from . import transcript as tr


def _ya_archivado(dia: Path, respuesta_markdown: str) -> Path | None:
    """The report for this turn is already in the day folder, or None.

    A turn's identity is its full markdown: two different turns do not share text
    byte for byte. Comparing by the markdown makes re-running a backfill fill in
    what is missing without duplicating what is already there --and a turn
    already written by the Stop hook is not archived a second time--. An
    unreadable file does not count as a match: when in doubt, it is rewritten.
    """
    if not dia.is_dir():
        return None
    for fichero in sorted(dia.glob("*.json")):
        try:
            sobre = json.loads(fichero.read_text(encoding="utf-8"))
        except Exception:
            continue
        if isinstance(sobre, dict) and sobre.get("respuesta_markdown") == respuesta_markdown:
            return fichero
    return None


def _nombre_simulado(dia: Path, sobre: dict, simulados_por_dia: dict[Path, int]) -> Path:
    """The name the report would have, counting the turns already simulated.

    Like `inf.nombre_de_fichero`, but without writing: since in a dry-run no
    `.json` appears on disk, all the turns of the same day would pick ordinal
    `01`. The already-simulated ones in that folder are counted --the ordinal is
    per day folder, not per slug-- so the simulation predicts the real ordinals
    (01, 02, 03...) instead of lying.
    """
    slug = md.nombre_desde_markdown(sobre["respuesta_markdown"])
    ordinal = inf.siguiente_ordinal(dia) + simulados_por_dia.get(dia, 0)
    simulados_por_dia[dia] = simulados_por_dia.get(dia, 0) + 1
    return dia / f"{ordinal:02d}-{slug}.json"


def reconstruir(
    ruta_transcript: str | os.PathLike[str],
    raiz_informes: str | os.PathLike[str],
    proyecto: str,
    *,
    umbral: int = 5,
    limite: int | None = None,
    simular: bool = False,
    ruta_log: str | os.PathLike[str] | None = None,
) -> list[dict]:
    """One file per turn. Returns one entry per considered turn.

    It is idempotent: a turn whose report is already in the day folder is skipped
    (`motivo == "ya archivado"`), so re-running fills gaps without duplicating.
    With `ruta_log`, each written report leaves an ESCRITO line in the log, just
    like the Stop hook: without it, `ultimo` would be blind to what the backfill
    reconstructs.
    """
    raiz = Path(raiz_informes)
    resultado: list[dict] = []
    simulados_por_dia: dict[Path, int] = {}
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
        dia = inf.carpeta_del_dia(raiz, proyecto, sobre["fecha"])
        existente = _ya_archivado(dia, respuesta)
        if existente is not None:
            resultado.append(
                {"escrito": False, "motivo": "ya archivado", "ruta": existente, "turno": turno}
            )
            continue
        if simular:
            resultado.append(
                {
                    "escrito": False,
                    "motivo": "simulacion",
                    "ruta": _nombre_simulado(dia, sobre, simulados_por_dia),
                    "turno": turno,
                }
            )
            continue
        destino = inf.escribir(raiz, proyecto, sobre)
        if ruta_log is not None:
            try:
                reg.anotar(ruta_log, reg.ESCRITO, proyecto, str(destino))
            except Exception:  # noqa: BLE001 - the log cannot bring down an already-written backfill
                pass
        resultado.append(
            {"escrito": True, "motivo": None, "ruta": destino, "turno": turno}
        )
    return resultado
