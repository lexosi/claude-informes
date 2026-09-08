"""Shared test infrastructure.

Mechanism / real-data pairs
---------------------------
Some checks are split into TWO tests because they answer two different
questions, and they are recognized by the name prefix:

- ``test_mechanism_<what>``  -- checks that the LOGIC works. Uses fixture data,
  touches nothing on the machine, and is GREEN on any runner (CI included).
- ``test_real_data_<what>`` -- checks that the real DATA of this machine holds
  (e.g. that the repo does not leak the author's identifiers, or that the
  guardian denies on the real paths). It uses a file outside git and only runs
  where it exists; if it is missing, it FAILS with instructions, it never skips.
  It ALWAYS carries the ``@pytest.mark.real_data`` marker (``tests/test_convencion.py``
  watches it: an unmarked data test is exactly the exception that opens the hole).

How to run each group
---------------------
- CI, any runner:      ``pytest -m "not real_data"``  (mechanism only).
- Pre-push / local:    ``pytest``                      (the WHOLE suite).

IMPORTANT: ``-m "not real_data"`` is NOT full coverage. It leaves out, on
purpose, everything that depends on machine data. The check that your real data
holds is given by the WHOLE suite, which is the one the pre-push runs before
publishing. Reading the CI command as "this is all that is tested" would be
taking a part for the whole.

The prefix groups by nature when the output is sorted (all the mechanism
together, all the data together) and makes a ``test_real_data_`` without its
marker stand out at a glance.
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
    """The condition 'the real-data file exists', in ONE single place.

    Returns a function `(ruta, *, como_crearlo) -> text` that reads the file or
    does `pytest.fail` with the exact path and how to create it. NEVER skip: a
    data test that skips silently is a blind guardian, and the project already
    has three of those. All the mechanism/real-data pairs use it, so none of
    them copy-pastes the "exists or not" logic again.
    """

    def _exigir(ruta: Path, *, como_crearlo: str) -> str:
        if not ruta.exists():
            pytest.fail(
                f"Missing real-data file for this machine:\n    {ruta}\n\n{como_crearlo}"
            )
        return ruta.read_text(encoding="utf-8")

    return _exigir


def pytest_configure(config):
    """The temporary directories go OUTSIDE claude-informes.

    The guardian prevents writing reports with the cwd inside the tool, so a
    tmp_path under the project itself would falsify half the suite.
    """
    if not config.option.basetemp:
        config.option.basetemp = Path(tempfile.gettempdir()) / "claude-informes-tests"


@pytest.fixture(autouse=True)
def log(tmp_path, monkeypatch):
    """Each test's log, isolated. No test touches the real log."""
    ruta = tmp_path / "hook.log"
    monkeypatch.setenv("CLAUDE_INFORMES_LOG", str(ruta))
    return ruta


@pytest.fixture
def escribir_config(tmp_path):
    """Returns a function that writes a config file and gives its path."""

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
    """The tool's report root, outside the projects."""
    return tmp_path / "archivo"


@pytest.fixture
def proyecto_vigilado(tmp_path, informes, escribir_config):
    """A project on the allowlist, with its directory and its config.

    Returns (project root, config path). The reports do NOT go inside the
    project: they go to the common root.
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
