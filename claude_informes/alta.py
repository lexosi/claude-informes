"""Dar de alta un proyecto: crear la carpeta y registrarlo, en un solo paso.

El orden importa. Si se abre el CLI antes de registrar el proyecto, esa sesion
no se archiva, y son justo las sesiones de arranque las que mas valen.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import config as cfg
from . import markdown as md


class YaExiste(Exception):
    pass


def registrar(
    nombre: str,
    raiz_proyectos: str | os.PathLike[str],
    ruta_config: str | os.PathLike[str],
    *,
    umbral_lineas: int = cfg.UMBRAL_POR_DEFECTO,
    raiz_informes: str | None = None,
) -> tuple[Path, Path]:
    """Crea la carpeta del proyecto y anade su entrada a la config.

    Devuelve (carpeta del proyecto, fichero de config). Es idempotente en la
    carpeta (si ya existe, se reutiliza) pero no en la config: un proyecto ya
    registrado es un error, para no pisar una entrada afinada a mano.
    """
    limpio = md.slug_llano(nombre)
    if not limpio:
        raise ValueError(f"nombre de proyecto inservible: {nombre!r}")

    destino = Path(ruta_config)
    try:
        crudo = json.loads(destino.read_text(encoding="utf-8"))
    except FileNotFoundError:
        crudo = {"proyectos": []}
    if not isinstance(crudo, dict) or not isinstance(crudo.get("proyectos"), list):
        raise ValueError(f"la config no tiene la forma esperada: {destino}")

    carpeta = Path(raiz_proyectos) / limpio
    for entrada in crudo["proyectos"]:
        if not isinstance(entrada, dict):
            continue
        if entrada.get("nombre") == limpio:
            raise YaExiste(f"ya hay un proyecto llamado {limpio!r} en la config")
        declarado = entrada.get("cwd")
        if isinstance(declarado, str) and cfg.normalizar(declarado) == cfg.normalizar(carpeta):
            raise YaExiste(f"{carpeta} ya esta registrado como {entrada.get('nombre')!r}")

    nueva = {
        "nombre": limpio,
        "cwd": str(carpeta),
        "activo": True,
        "umbral_lineas": umbral_lineas,
    }
    if raiz_informes:
        nueva["raiz_informes"] = str(raiz_informes)

    carpeta.mkdir(parents=True, exist_ok=True)
    crudo["proyectos"].append(nueva)
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps(crudo, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    return carpeta, destino
