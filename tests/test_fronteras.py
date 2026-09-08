"""Las fronteras de codificacion, cruzadas por BYTES.

Estos tests NO usan `io.StringIO`. Un flujo de texto en memoria entra por
detras de la unica frontera que estaba rota, que es exactamente por lo que la
fixture con el ❌ culpable llevaba pasando desde el principio.

Aqui se lanza `hook_informes.py` como subproceso real, se le mete el payload
por un pipe en utf-8, y se comprueba EL FICHERO EN DISCO: su nombre y su
contenido. No lo que devuelva ninguna funcion.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
LANZADERA = RAIZ / "hook_informes.py"

# Acentos en minuscula: sus bytes utf-8 caen todos en huecos que cp1252 SI
# sabe decodificar, asi que el turno se escribe... con mojibake.
MINUSCULAS = (
    "# Enumeración de qué pasó después\n\n"
    "No edité nada; la sesión terminó ahí.\n"
    "linea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_MINUSCULAS = "enumeracion-paso-despues"

# Mayusculas acentuadas: 'Á' es C3 81 e 'Í' es C3 8D, y 0x81 y 0x8D son dos de
# los cinco huecos de cp1252. Estas son las que matan el informe.
MAYUSCULAS = (
    "# ÍNDICE del ÁRBOL de decisión\n\n"
    "Ángel revisó la Ñ y la Ó.\n"
    "linea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_MAYUSCULAS = "indice-arbol-decision"

# '❌' U+274C es E2 9D 8C: el 0x9D del '\udc9d' que aparece en el log real.
CRUZ = (
    "# Resultado final de la comprobación completa\n\n"
    "Todo verde ✅\nY un fallo ❌\n"
    "linea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_CRUZ = "resultado-final-comprobacion-completa"

# Un turno sin nada raro: sirve para exigir que no quede basura en disco.
LLANA = (
    "# Un turno normal y corriente\n\n"
    "sin nada raro\nlinea tres\nlinea cuatro\nlinea cinco\nlinea seis\n"
)
SLUG_LLANA = "turno-normal-corriente"


def lanzar(markdown, raiz_proyecto, ruta_config):
    """El hook de verdad, en otro proceso, con el payload en bytes utf-8.

    El entorno se limpia a proposito de PYTHONUTF8 y PYTHONIOENCODING: si un
    dia alguien los pone en su maquina, el test tiene que seguir viendo el
    caso real, que es el de Claude Code lanzando `python` a pelo.
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
    assert len(escritos) == 1, f"se esperaba un informe y hay {len(escritos)}: {escritos}"
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
    """El ❌ U+274C lleva el byte 0x9D, uno de los cinco huecos de cp1252."""
    raiz, ruta_config = vigilado

    salida = lanzar(CRUZ, raiz, ruta_config)

    assert salida.returncode == 0
    destino = el_unico_informe(informes)
    assert destino.name == f"01-{SLUG_CRUZ}.json"
    assert markdown_de(destino) == CRUZ
    assert "❌" in markdown_de(destino)


def test_no_lone_surrogate_survives_the_envelope(vigilado, informes):
    """Lo que revienta al escribir es el surrogate, no el caracter."""
    raiz, ruta_config = vigilado

    lanzar(CRUZ, raiz, ruta_config)

    crudo = el_unico_informe(informes).read_bytes()
    crudo.decode("utf-8")  # revienta si quedo un surrogate
    texto = markdown_de(el_unico_informe(informes))
    assert not any(0xD800 <= ord(c) <= 0xDFFF for c in texto)


def test_after_a_correct_turn_neither_a_tmp_nor_a_zero_byte_file_remains(
    vigilado, informes
):
    """Los tres informes a cero de produccion son esto, sin la asercion."""
    raiz, ruta_config = vigilado

    lanzar(LLANA, raiz, ruta_config)

    todo = [p for p in Path(informes).rglob("*") if p.is_file()]
    assert [p.name for p in todo] == [f"01-{SLUG_LLANA}.json"]
    assert not [p for p in todo if p.suffix == ".tmp"]
    assert not [p for p in todo if p.stat().st_size == 0]
