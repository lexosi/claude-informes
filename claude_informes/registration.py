"""Register a project: create the folder and register it, in a single step.

Order matters. If the CLI is opened before the project is registered, that
session is not archived, and it is precisely the startup sessions that are worth
the most.
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
    """Create the project folder and add its entry to the config.

    Returns (project folder, config file). It is idempotent on the folder (if it
    already exists, it is reused) but not on the config: an already-registered
    project is an error, so as not to overwrite an entry hand-tuned by hand.
    """
    limpio = md.slug_llano(nombre)
    if not limpio:
        raise ValueError(f"unusable project name: {nombre!r}")

    destino = Path(ruta_config)
    try:
        crudo = json.loads(destino.read_text(encoding="utf-8"))
    except FileNotFoundError:
        crudo = {"proyectos": []}
    if not isinstance(crudo, dict) or not isinstance(crudo.get("proyectos"), list):
        raise ValueError(f"the config does not have the expected shape: {destino}")

    carpeta = Path(raiz_proyectos) / limpio
    for entrada in crudo["proyectos"]:
        if not isinstance(entrada, dict):
            continue
        if entrada.get("nombre") == limpio:
            raise YaExiste(f"a project named {limpio!r} is already in the config")
        declarado = entrada.get("cwd")
        if isinstance(declarado, str) and cfg.normalizar(declarado) == cfg.normalizar(carpeta):
            raise YaExiste(f"{carpeta} is already registered as {entrada.get('nombre')!r}")

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
