"""El agujero de clase: cualquier MCP con escritura montado en Claude Code.

Los servidores MCP no comparten esquema: ni el nombre de la herramienta ni el
del campo de la ruta estan estandarizados. Por eso aqui la deteccion es
heuristica y solo sirve para denegar mejor. Permitir sigue garantizado.
"""

import pytest

from claude_informes import guardian as gd
from claude_informes import registro as reg

from test_guardian import archivo, deniega, ejecutar, razon  # noqa: F401


def mcp(herramienta, entrada, cwd="C:\\example-projects\\loopward"):
    return {
        "session_id": "s",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": herramienta,
        "tool_input": entrada,
    }


# --- deteccion de escritura por el nombre ---


@pytest.mark.parametrize(
    "herramienta",
    [
        "mcp__informes-claude__write_file",
        "mcp__informes-claude__edit_file",
        "mcp__informes-claude__move_file",
        "mcp__informes-claude__create_directory",
    ],
)
def test_se_miran_las_herramientas_mcp_que_dicen_escribir(herramienta):
    assert gd.campos_a_mirar(herramienta) is gd.CAMPOS_MCP


@pytest.mark.parametrize(
    "herramienta",
    [
        "mcp__informes-claude__read_file",
        "mcp__informes-claude__read_text_file",
        "mcp__informes-claude__list_directory",
        "mcp__informes-claude__directory_tree",
        "mcp__informes-claude__search_files",
        "mcp__informes-claude__get_file_info",
    ],
)
def test_no_se_miran_las_de_solo_lectura(herramienta):
    assert gd.campos_a_mirar(herramienta) is None


def test_el_verbo_sale_del_nombre_de_la_herramienta_no_del_servidor():
    """`mcp__write-tools__read_file` lee, aunque el servidor se llame write."""
    assert gd.campos_a_mirar("mcp__write-tools__read_file") is None
    assert gd.campos_a_mirar("mcp__lectura__write_file") is gd.CAMPOS_MCP


def test_un_verbo_no_se_reconoce_como_subcadena():
    """`get_output` contiene 'put' y no por eso es una escritura."""
    assert gd.campos_a_mirar("mcp__x__get_output") is None


# --- lo que hay que denegar ---


def test_una_escritura_mcp_dentro_del_archivo_se_deniega(archivo):
    comun, _, ruta_config = archivo
    datos = mcp(
        "mcp__informes-claude__write_file",
        {"path": str(comun / "loopward" / "2026-08-28" / "99-a-mano.json"), "content": "{}"},
    )

    codigo, salida = ejecutar(datos, ruta_config)

    assert codigo == 0
    assert deniega(salida)
    assert "--proyecto loopward" in razon(salida)


@pytest.mark.parametrize(
    "campo", ["path", "file_path", "filename", "destination", "target", "dest"]
)
def test_se_prueban_los_nombres_de_campo_habituales(campo, archivo):
    comun, _, ruta_config = archivo
    datos = mcp("mcp__x__write_file", {campo: str(comun / "loopward" / "x.json")})

    assert deniega(ejecutar(datos, ruta_config)[1]), campo


def test_una_lista_de_rutas_se_revisa_entera(archivo):
    comun, _, ruta_config = archivo
    datos = mcp(
        "mcp__x__delete_files",
        {"paths": ["C:\\example-projects\\loopward\\README.md", str(comun / "x.json")]},
    )

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_una_ruta_relativa_de_un_mcp_tambien_se_resuelve(archivo, tmp_path):
    comun, _, ruta_config = archivo
    desde = tmp_path / "repos" / "loopward"
    desde.mkdir(parents=True)
    datos = mcp(
        "mcp__x__write_file",
        {"path": f"..\\..\\{comun.name}\\loopward\\x.json"},
        cwd=str(desde),
    )

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_una_escritura_mcp_a_una_raiz_por_proyecto_se_deniega(archivo):
    _, cofre, ruta_config = archivo
    datos = mcp("mcp__x__write_file", {"path": str(cofre / "project-b" / "x.json")})

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_una_escritura_mcp_al_log_se_deniega(archivo, log):
    _, _, ruta_config = archivo
    assert deniega(ejecutar(mcp("mcp__x__write_file", {"path": str(log)}), ruta_config)[1])


# --- lo que NO se puede denegar ---


def test_una_escritura_mcp_fuera_del_archivo_se_permite(archivo, log):
    _, _, ruta_config = archivo
    for ruta in [
        "C:\\example-projects\\loopward\\README.md",
        "C:\\example-projects\\project-b\\cv.md",
        "C:\\Users\\user\\Documents\\notas.txt",
    ]:
        codigo, salida = ejecutar(mcp("mcp__x__write_file", {"path": ruta}), ruta_config)
        assert codigo == 0 and salida == "", ruta
    assert reg.leer(log) == [], "una escritura legitima no ensucia el log"


def test_una_lectura_mcp_dentro_del_archivo_se_permite(archivo, log):
    """Leer los informes es legitimo: solo se impide escribirlos."""
    comun, _, ruta_config = archivo
    for herramienta in [
        "mcp__informes-claude__read_file",
        "mcp__informes-claude__read_text_file",
        "mcp__informes-claude__list_directory",
        "mcp__informes-claude__directory_tree",
    ]:
        datos = mcp(herramienta, {"path": str(comun / "loopward")})
        codigo, salida = ejecutar(datos, ruta_config)
        assert codigo == 0 and salida == "", herramienta
    assert reg.leer(log) == []


def test_una_herramienta_mcp_sin_ruta_se_permite_y_se_anota(archivo, log):
    """El punto ciego se permite, pero no en silencio."""
    _, _, ruta_config = archivo
    datos = mcp("mcp__x__write_blob", {"contenido": "algo", "id": 42})

    codigo, salida = ejecutar(datos, ruta_config)

    assert codigo == 0 and salida == ""
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.PERMITIDO_SIN_RUTA
    assert "mcp__x__write_blob" in anotacion.detalle
    assert "sin ruta reconocible" in anotacion.detalle


def test_una_herramienta_mcp_con_tool_input_vacio_se_permite_y_se_anota(archivo, log):
    _, _, ruta_config = archivo
    codigo, salida = ejecutar(mcp("mcp__x__save_note", {}), ruta_config)

    assert codigo == 0 and salida == ""
    assert reg.leer(log)[0].resultado == reg.PERMITIDO_SIN_RUTA


def test_una_lectura_mcp_sin_ruta_no_ensucia_el_log(archivo, log):
    """Solo se anota el punto ciego de las que dicen escribir."""
    _, _, ruta_config = archivo
    ejecutar(mcp("mcp__claude_ai_Gmail__search_threads", {"q": "hola"}), ruta_config)

    assert reg.leer(log) == []


def test_un_verbo_desconocido_se_trata_como_lectura(archivo, log):
    """Fallar abierto manda: lo que no se reconoce, pasa."""
    comun, _, ruta_config = archivo
    datos = mcp("mcp__x__persistir_cosa", {"path": str(comun / "x.json")})

    codigo, salida = ejecutar(datos, ruta_config)

    assert codigo == 0 and salida == "", "no se reconoce como escritura: pasa"
    assert reg.leer(log) == []


def test_una_ruta_mcp_ilegible_no_revienta(archivo):
    _, _, ruta_config = archivo
    for entrada in [{"path": 42}, {"path": None}, {"path": ["a", 1, None]}, {"paths": "no soy lista"}]:
        codigo, salida = ejecutar(mcp("mcp__x__write_file", entrada), ruta_config)
        assert codigo == 0, entrada
