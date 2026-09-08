"""The encoding boundaries, crossed by BYTES.

These tests do NOT use `io.StringIO`. An in-memory text stream comes in behind
the only boundary that was broken, which is exactly why the fixture with the
guilty ❌ had been passing from the start.

Here `hook_informes.py` is launched as a real subprocess, the payload is fed to
it through a pipe in utf-8, and THE FILE ON DISK is checked: its name and its
content. Not whatever any function returns.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
LANZADERA = RAIZ / "hook_informes.py"

# Lowercase accents: their utf-8 bytes all fall into gaps that cp1252 DOES
# know how to decode, so the turn gets written... with mojibake.
MINUSCULAS = (
    "# Enumeración de qué pasó después\n\n"
    "No edité nada; la sesión terminó ahí.\n"
    "linea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_MINUSCULAS = "enumeracion-paso-despues"

# Accented uppercase: 'Á' is C3 81 and 'Í' is C3 8D, and 0x81 and 0x8D are two
# of cp1252's five gaps. These are the ones that kill the report.
MAYUSCULAS = (
    "# ÍNDICE del ÁRBOL de decisión\n\n"
    "Ángel revisó la Ñ y la Ó.\n"
    "linea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_MAYUSCULAS = "indice-arbol-decision"

# '❌' U+274C is E2 9D 8C: the 0x9D of the '\udc9d' that appears in the real log.
CRUZ = (
    "# Resultado final de la comprobación completa\n\n"
    "Todo verde ✅\nY un fallo ❌\n"
    "linea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_CRUZ = "resultado-final-comprobacion-completa"

# A turn with nothing odd: used to require that no garbage is left on disk.
LLANA = (
    "# Un turno normal y corriente\n\n"
    "sin nada raro\nlinea tres\nlinea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_LLANA = "turno-normal-corriente"


def lanzar(markdown, raiz_proyecto, ruta_config):
    """The real hook, in another process, with the payload in utf-8 bytes.

    The environment is deliberately cleared of PYTHONUTF8, PYTHONIOENCODING and
    PYTHONLEGACYWINDOWSSTDIO: if one day someone sets them on their machine, the
    test has to keep seeing the real case, which is Claude Code launching
    `python` bare.
    """
    entorno = dict(os.environ)
    for variable in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONLEGACYWINDOWSSTDIO"):
        entorno.pop(variable, None)
    entorno["CLAUDE_INFORMES_CONFIG"] = str(ruta_config)
    payload = {
        "session_id": "sesion-de-prueba",
        "cwd": str(raiz_proyecto),
        "stop_hook_active": False,
        "last_assistant_message": markdown,
    }
    crudo = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    return subprocess.run(
        [sys.executable, str(LANZADERA)], input=crudo, capture_output=True, env=entorno
    )


@pytest.fixture
def vigilado(tmp_path, informes, escribir_config):
    raiz = tmp_path / "vigilado"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "vigilado", "cwd": str(raiz), "umbral_lineas": 5}],
        raiz_informes=informes,
    )
    return raiz, ruta_config


def el_unico_informe(informes):
    escritos = sorted(Path(informes).rglob("*.json"))
    assert len(escritos) == 1, f"expected one report and there are {len(escritos)}: {escritos}"
    return escritos[0]


def markdown_de(ruta):
    return json.loads(ruta.read_text(encoding="utf-8"))["respuesta_markdown"]


@pytest.mark.parametrize(
    "markdown, slug",
    [
        pytest.param(MINUSCULAS, SLUG_MINUSCULAS, id="minusculas"),
        pytest.param(MAYUSCULAS, SLUG_MAYUSCULAS, id="mayusculas"),
    ],
)
def test_the_castilian_accents_arrive_intact_on_disk(
    markdown, slug, vigilado, informes
):
    raiz, ruta_config = vigilado

    salida = lanzar(markdown, raiz, ruta_config)

    assert salida.returncode == 0
    destino = el_unico_informe(informes)
    assert destino.name == f"01-{slug}.json"
    assert markdown_de(destino) == markdown
    assert destino.stat().st_size > 0


def test_a_character_outside_cp1252_does_not_kill_the_report(vigilado, informes):
    """The ❌ U+274C carries the byte 0x9D, one of cp1252's five gaps."""
    raiz, ruta_config = vigilado

    salida = lanzar(CRUZ, raiz, ruta_config)

    assert salida.returncode == 0
    destino = el_unico_informe(informes)
    assert destino.name == f"01-{SLUG_CRUZ}.json"
    assert markdown_de(destino) == CRUZ
    assert "❌" in markdown_de(destino)


def test_no_lone_surrogate_survives_the_envelope(vigilado, informes):
    """What blows up when writing is the surrogate, not the character."""
    raiz, ruta_config = vigilado

    lanzar(CRUZ, raiz, ruta_config)

    crudo = el_unico_informe(informes).read_bytes()
    crudo.decode("utf-8")  # blows up if a surrogate was left
    texto = markdown_de(el_unico_informe(informes))
    assert not any(0xD800 <= ord(c) <= 0xDFFF for c in texto)


def test_after_a_correct_turn_neither_a_tmp_nor_a_zero_byte_file_remains(
    vigilado, informes
):
    """The three zero-byte reports in production are this, without the assertion."""
    raiz, ruta_config = vigilado

    lanzar(LLANA, raiz, ruta_config)

    todo = [p for p in Path(informes).rglob("*") if p.is_file()]
    assert [p.name for p in todo] == [f"01-{SLUG_LLANA}.json"]
    assert not [p for p in todo if p.suffix == ".tmp"]
    assert not [p for p in todo if p.stat().st_size == 0]
