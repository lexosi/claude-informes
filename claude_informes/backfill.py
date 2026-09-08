"""Modo backfill: reconstruye informes de turnos pasados desde un transcript."""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import informe as inf
from . import markdown as md
from . import registro as reg
from . import transcript as tr


def _ya_archivado(dia: Path, respuesta_markdown: str) -> Path | None:
    """El informe de este turno ya esta en la carpeta del dia, o None.

    La identidad de un turno es su markdown integro: dos turnos distintos no
    comparten texto byte a byte. Comparar por el markdown hace que reejecutar
    un backfill rellene lo que falte sin duplicar lo que ya esta --y que un
    turno ya escrito por el hook Stop no se archive por segunda vez--. Un
    fichero ilegible no cuenta como coincidencia: ante la duda, se reescribe.
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
    """El nombre que tendria el informe, contando los turnos ya simulados.

    Igual que `inf.nombre_de_fichero`, pero sin escribir: como en un dry-run no
    aparece ningun `.json` en disco, todos los turnos del mismo dia elegirian el
    ordinal `01`. Se lleva la cuenta de los ya simulados en esa carpeta --el
    ordinal es por carpeta de dia, no por slug-- para que la simulacion prediga
    los ordinales reales (01, 02, 03...) en vez de mentir.
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
    """Un fichero por turno. Devuelve una entrada por turno considerado.

    Es idempotente: un turno cuyo informe ya esta en la carpeta del dia se
    salta (`motivo == "ya archivado"`), asi que reejecutar rellena huecos sin
    duplicar. Con `ruta_log`, cada informe escrito deja una linea ESCRITO en el
    log, igual que el hook Stop: sin ella, `ultimo` seria ciego a lo que
    reconstruye el backfill.
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
            except Exception:  # noqa: BLE001 - el log no puede tumbar un backfill ya escrito
                pass
        resultado.append(
            {"escrito": True, "motivo": None, "ruta": destino, "turno": turno}
        )
    return resultado
