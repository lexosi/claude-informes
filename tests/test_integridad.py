"""The envelope's only requirement: carry the markdown INTACT.

These checks are byte by byte, not by eye.
"""

import io
import json
from pathlib import Path

import pytest

from claude_informes import hook as hk

MUESTRAS = {
    "acentos": "# Investigación\n\nJosé compró ñoñerías: ¿qué tal?\nUn, dos\ntres\ncuatro\ncinco",
    "emoji": "# Resultado \U0001f7e2\n\nTodo verde ✅\nY un fallo ❌\n1\n2\n3\n4",
    "crlf": "# Con CRLF\r\n\r\nlinea uno\r\nlinea dos\r\nlinea tres\r\nlinea cuatro\r\n",
    "tabuladores": "# Tabs\n\n\tsangrado con tab\n\t\tdoble\n1\n2\n3\n4",
    "espacios_finales": "# Cola   \n\nlinea con dos espacios  \notra \n1\n2\n3\n4",
    "barras": "# Rutas\n\nC:\\proyectos\\ejemplo\\.claude\nregex: \\d+\\s*\\\\\n1\n2\n3\n4",
    "comillas": '# Comillas\n\n"dobles" y \'simples\' y `back`\n1\n2\n3\n4\n5',
    "bloque_de_codigo": "# Codigo\n\n```python\ndef f():\n    return {'a': 1}\n```\n\nfin\n1\n2",
    "vallas_anidadas": "# Anidado\n\n````md\n```py\nx = 1\n```\n````\n1\n2\n3",
    "json_dentro": '# JSON\n\n```json\n{"clave": "valor con \\"escape\\""}\n```\n1\n2\n3',
    "lineas_en_blanco": "# Huecos\n\n\n\n\n\nfinal",
    "sin_salto_final": "# Sin salto\n\nuno\ndos\ntres\ncuatro\ncinco",
    "muchos_saltos_finales": "# Cola larga\n\nuno\ndos\ntres\ncuatro\n\n\n\n",
    "separadores_unicode": "# Unicode\n\nlinea partida otra\n1\n2\n3\n4",
    "espacio_duro": "# Duro\n\nespacio duro y ​ invisible\n1\n2\n3\n4",
    "bom_incrustado": "# BOM\n\n﻿despues del bom\n1\n2\n3\n4",
    "cirilico_y_cjk": "# Mezcla\n\nПривет, 世界, مرحبا\n1\n2\n3\n4",
    "muy_largo": "# Largo\n\n" + ("x" * 20000 + "\n") * 5,
}


def _escribir_y_releer(markdown, raiz, ruta_config, informes):
    entrada = io.StringIO(
        json.dumps(
            {
                "session_id": "s",
                "cwd": str(raiz),
                "stop_hook_active": False,
                "last_assistant_message": markdown,
            }
        )
    )
    assert hk.main(entrada=entrada, ruta_config=ruta_config) == 0
    escritos = list(Path(informes).rglob("*.json"))
    assert len(escritos) == 1
    return json.loads(escritos[0].read_text(encoding="utf-8"))


@pytest.mark.parametrize("nombre", sorted(MUESTRAS))
def test_the_markdown_in_the_json_matches_the_input_byte_for_byte(
    nombre, proyecto_vigilado, informes
):
    raiz, ruta_config = proyecto_vigilado
    entrada = MUESTRAS[nombre]

    sobre = _escribir_y_releer(entrada, raiz, ruta_config, informes)

    assert sobre["respuesta_markdown"].encode("utf-8") == entrada.encode("utf-8")
    assert len(sobre["respuesta_markdown"]) == len(entrada)


def test_the_file_on_disk_is_valid_utf8(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    entrada = MUESTRAS["cirilico_y_cjk"]
    _escribir_y_releer(entrada, raiz, ruta_config, informes)

    crudo = next(Path(informes).rglob("*.json")).read_bytes()
    crudo.decode("utf-8")  # blows up if it isn't
    assert not crudo.startswith(b"\xef\xbb\xbf"), "no BOM at the start of the file"


def test_the_chunking_does_not_alter_the_original_markdown(proyecto_vigilado, informes):
    """The sections and blocks are extras; the original stays intact."""
    raiz, ruta_config = proyecto_vigilado
    entrada = MUESTRAS["bloque_de_codigo"]

    sobre = _escribir_y_releer(entrada, raiz, ruta_config, informes)

    assert sobre["respuesta_markdown"] == entrada
    assert sobre["bloques_codigo"] == [
        {"lenguaje": "python", "codigo": "def f():\n    return {'a': 1}"}
    ]


def test_the_line_breaks_are_not_translated_when_writing(proyecto_vigilado, informes):
    """On Windows nothing should convert \\n into \\r\\n inside the markdown."""
    raiz, ruta_config = proyecto_vigilado
    entrada = "# LF puro\n\nuno\ndos\ntres\ncuatro\ncinco\n"

    sobre = _escribir_y_releer(entrada, raiz, ruta_config, informes)

    assert "\r" not in sobre["respuesta_markdown"]
    assert sobre["respuesta_markdown"] == entrada


def test_the_crlfs_from_the_input_are_preserved(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    entrada = MUESTRAS["crlf"]

    sobre = _escribir_y_releer(entrada, raiz, ruta_config, informes)

    assert sobre["respuesta_markdown"].count("\r\n") == entrada.count("\r\n")
    assert sobre["respuesta_markdown"] == entrada


def test_the_file_on_disk_uses_lf_line_breaks(proyecto_vigilado, informes):
    """The whole file in LF: otherwise git and the tools see noise."""
    raiz, ruta_config = proyecto_vigilado
    _escribir_y_releer(MUESTRAS["crlf"], raiz, ruta_config, informes)

    crudo = next(Path(informes).rglob("*.json")).read_bytes()
    assert b"\r\n" not in crudo, "the JSON must not carry structural CRLF"
    assert rb"\r\n" in crudo, "the markdown CRLFs go escaped, not raw"
