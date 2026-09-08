"""Infraestructura compartida de los tests.

Pares mecanismo / datos
-----------------------
Algunas comprobaciones se parten en DOS tests porque responden a dos preguntas
distintas, y se reconocen por el prefijo del nombre:

- ``test_mecanismo_<que>``  -- prueba que la LOGICA funciona. Usa datos de
  fixture, no toca nada de la maquina, y esta VERDE en cualquier runner (CI
  incluida).
- ``test_datos_reales_<que>`` -- prueba que los DATOS reales de esta maquina
  cumplen (p. ej. que el repo no filtra los identificadores del autor, o que el
  guardian deniega sobre las rutas reales). Usa un fichero fuera de git y solo
  corre donde existe; si falta, FALLA con instrucciones, nunca hace skip. Lleva
  SIEMPRE el marcador ``@pytest.mark.datos_reales`` (lo vigila
  ``tests/test_convencion.py``: un test de datos sin marcar es justo la
  excepcion que abre el agujero).

Como se corre cada grupo
------------------------
- CI, cualquier runner:   ``pytest -m "not datos_reales"``  (solo mecanismo).
- Pre-push / local:       ``pytest``                         (la suite ENTERA).

IMPORTANTE: ``-m "not datos_reales"`` NO es cobertura completa. Deja fuera, a
proposito, todo lo que depende de datos de la maquina. La comprobacion de que
tus datos reales cumplen la da la suite ENTERA, que es la que corre el pre-push
antes de publicar. Leer el comando de CI como "esto es todo lo que se prueba"
seria tomar una parte por el conjunto.

El prefijo agrupa por naturaleza al ordenar la salida (todo el mecanismo junto,
todos los datos juntos) y hace que un ``test_datos_reales_`` sin su marcador
cante a la vista.
"""

import json
import pathlib
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@pytest.fixture
def exigir_fichero_de_datos():
    """La condicion 'existe el fichero de datos reales', en UN solo sitio.

    Devuelve una funcion `(ruta, *, como_crearlo) -> texto` que lee el fichero
    o hace `pytest.fail` con la ruta exacta y como crearlo. NUNCA skip: un test
    de datos que se salta en silencio es un guardian ciego, y de esos el
    proyecto ya lleva tres. La usan todos los pares mecanismo/datos, para que
    ninguno vuelva a copiar-pegar la logica de "existe o no".
    """

    def _exigir(ruta: Path, *, como_crearlo: str) -> str:
        if not ruta.exists():
            pytest.fail(
                f"Falta el fichero de datos reales de la maquina:\n    {ruta}\n\n{como_crearlo}"
            )
        return ruta.read_text(encoding="utf-8")

    return _exigir


def pytest_configure(config):
    """Los directorios temporales van FUERA de claude-informes.

    La guardia impide escribir informes con el cwd dentro de la herramienta,
    asi que un tmp_path bajo el propio proyecto falsearia media suite.
    """
    if not config.option.basetemp:
        config.option.basetemp = Path(tempfile.gettempdir()) / "claude-informes-tests"


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
    """El log de cada test, aislado. Ningun test toca el log real."""
    ruta = tmp_path / "hook.log"
    monkeypatch.setenv("CLAUDE_INFORMES_LOG", str(ruta))
    return ruta


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
