import json
import pathlib
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def pytest_configure(config):
    """Los directorios temporales van FUERA de claude-informes.

    La guardia impide escribir informes con el cwd dentro de la herramienta,
    asi que un tmp_path bajo el propio proyecto falsearia media suite.
    """
    if not config.option.basetemp:
        config.option.basetemp = Path(tempfile.gettempdir()) / "claude-informes-tests"


@pytest.fixture
def escribir_config(tmp_path):
    """Devuelve una funcion que deja un fichero de config y da su ruta."""

    def _escribir(entradas, raiz_informes=None):
        ruta = tmp_path / "proyectos.json"
        contenido = {"proyectos": entradas}
        if raiz_informes is not None:
            contenido["raiz_informes"] = str(raiz_informes)
        for entrada in entradas:
            if isinstance(entrada, dict) and isinstance(entrada.get("raiz_informes"), pathlib.Path):
                entrada["raiz_informes"] = str(entrada["raiz_informes"])
        ruta.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
        return ruta

    return _escribir


@pytest.fixture
def informes(tmp_path):
    """La raiz de informes de la herramienta, fuera de los proyectos."""
    return tmp_path / "archivo"


@pytest.fixture
def proyecto_vigilado(tmp_path, informes, escribir_config):
    """Un proyecto en la lista blanca, con su directorio y su config.

    Devuelve (raiz del proyecto, ruta de la config). Los informes NO van
    dentro del proyecto: van a la raiz comun.
    """
    raiz = tmp_path / "vigilado"
    raiz.mkdir()
    ruta_config = escribir_config(
        [
            {
                "nombre": "vigilado",
                "cwd": str(raiz),
                "activo": True,
                "umbral_lineas": 5,
            }
        ],
        raiz_informes=informes,
    )
    return raiz, ruta_config
