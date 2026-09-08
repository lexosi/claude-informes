"""The class-wide hole: any write-capable MCP mounted in Claude Code.

MCP servers don't share a schema: neither the tool name nor the
path field name are standardized. That's why detection here is
heuristic and only serves to deny better. Allowing stays guaranteed.
"""

import pytest

from claude_informes import guardian as gd
from claude_informes import registro as reg

from test_guardian import archivo, deniega, ejecutar, razon  # noqa: F401


def mcp(herramienta, entrada, cwd="C:\\proyectos\\alfa"):
    return {
        "session_id": "s",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": herramienta,
        "tool_input": entrada,
    }


# --- write detection by name ---


@pytest.mark.parametrize(
    "herramienta",
    [
        "mcp__informes-claude__write_file",
        "mcp__informes-claude__edit_file",
        "mcp__informes-claude__move_file",
        "mcp__informes-claude__create_directory",
    ],
)
def test_mcp_tools_whose_names_say_write_are_inspected(herramienta):
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
def test_the_read_only_ones_are_not_inspected(herramienta):
    assert gd.campos_a_mirar(herramienta) is None


def test_the_verb_comes_from_the_tool_name_not_the_server():
    """`mcp__write-tools__read_file` reads, even though the server is named write."""
    assert gd.campos_a_mirar("mcp__write-tools__read_file") is None
    assert gd.campos_a_mirar("mcp__lectura__write_file") is gd.CAMPOS_MCP


def test_a_verb_is_not_recognized_as_a_substring():
    """`get_output` contains 'put' and that doesn't make it a write."""
    assert gd.campos_a_mirar("mcp__x__get_output") is None


# --- what must be denied ---


def test_an_mcp_write_inside_the_archive_is_denied(archivo):
    comun, _, ruta_config = archivo
    datos = mcp(
        "mcp__informes-claude__write_file",
        {"path": str(comun / "alfa" / "2026-08-28" / "99-a-mano.json"), "content": "{}"},
    )

    codigo, salida = ejecutar(datos, ruta_config)

    assert codigo == 0
    assert deniega(salida)
    assert "--proyecto alfa" in razon(salida)


@pytest.mark.parametrize(
    "campo", ["path", "file_path", "filename", "destination", "target", "dest"]
)
def test_the_usual_path_field_names_are_tried(campo, archivo):
    comun, _, ruta_config = archivo
    datos = mcp("mcp__x__write_file", {campo: str(comun / "alfa" / "x.json")})

    assert deniega(ejecutar(datos, ruta_config)[1]), campo


def test_a_list_of_paths_is_reviewed_in_full(archivo):
    comun, _, ruta_config = archivo
    datos = mcp(
        "mcp__x__delete_files",
        {"paths": ["C:\\proyectos\\alfa\\README.md", str(comun / "x.json")]},
    )

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_a_relative_path_from_an_mcp_is_also_resolved(archivo, tmp_path):
    comun, _, ruta_config = archivo
    desde = tmp_path / "repos" / "alfa"
    desde.mkdir(parents=True)
    datos = mcp(
        "mcp__x__write_file",
        {"path": f"..\\..\\{comun.name}\\alfa\\x.json"},
        cwd=str(desde),
    )

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_an_mcp_write_to_a_per_project_root_is_denied(archivo):
    _, cofre, ruta_config = archivo
    datos = mcp("mcp__x__write_file", {"path": str(cofre / "beta" / "x.json")})

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_an_mcp_write_to_the_log_is_denied(archivo, log):
    _, _, ruta_config = archivo
    assert deniega(ejecutar(mcp("mcp__x__write_file", {"path": str(log)}), ruta_config)[1])


# --- what must NOT be denied ---


def test_an_mcp_write_outside_the_archive_is_allowed(archivo, log):
    _, _, ruta_config = archivo
    for ruta in [
        "C:\\proyectos\\alfa\\README.md",
        "C:\\proyectos\\beta\\cv.md",
        "C:\\Users\\ejemplo\\Documents\\notas.txt",
    ]:
        codigo, salida = ejecutar(mcp("mcp__x__write_file", {"path": ruta}), ruta_config)
        assert codigo == 0 and salida == "", ruta
    assert reg.leer(log) == [], "una escritura legitima no ensucia el log"


def test_an_mcp_read_inside_the_archive_is_allowed(archivo, log):
    """Reading the reports is legitimate: only writing them is prevented."""
    comun, _, ruta_config = archivo
    for herramienta in [
        "mcp__informes-claude__read_file",
        "mcp__informes-claude__read_text_file",
        "mcp__informes-claude__list_directory",
        "mcp__informes-claude__directory_tree",
    ]:
        datos = mcp(herramienta, {"path": str(comun / "alfa")})
        codigo, salida = ejecutar(datos, ruta_config)
        assert codigo == 0 and salida == "", herramienta
    assert reg.leer(log) == []


def test_an_mcp_tool_without_a_path_is_allowed_and_logged(archivo, log):
    """The blind spot is allowed, but not silently."""
    _, _, ruta_config = archivo
    datos = mcp("mcp__x__write_blob", {"contenido": "algo", "id": 42})

    codigo, salida = ejecutar(datos, ruta_config)

    assert codigo == 0 and salida == ""
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.PERMITIDO_SIN_RUTA
    assert "mcp__x__write_blob" in anotacion.detalle
    assert "sin ruta reconocible" in anotacion.detalle


def test_an_mcp_tool_with_empty_tool_input_is_allowed_and_logged(archivo, log):
    _, _, ruta_config = archivo
    codigo, salida = ejecutar(mcp("mcp__x__save_note", {}), ruta_config)

    assert codigo == 0 and salida == ""
    assert reg.leer(log)[0].resultado == reg.PERMITIDO_SIN_RUTA


def test_an_mcp_read_without_a_path_does_not_dirty_the_log(archivo, log):
    """Only the blind spot of those that claim to write is recorded."""
    _, _, ruta_config = archivo
    ejecutar(mcp("mcp__claude_ai_Gmail__search_threads", {"q": "hola"}), ruta_config)

    assert reg.leer(log) == []


def test_an_unknown_verb_is_treated_as_a_read(archivo, log):
    """Failing open rules: what isn't recognized passes."""
    comun, _, ruta_config = archivo
    datos = mcp("mcp__x__persistir_cosa", {"path": str(comun / "x.json")})

    codigo, salida = ejecutar(datos, ruta_config)

    assert codigo == 0 and salida == "", "no se reconoce como escritura: pasa"
    assert reg.leer(log) == []


def test_an_unreadable_mcp_path_does_not_blow_up(archivo):
    _, _, ruta_config = archivo
    for entrada in [{"path": 42}, {"path": None}, {"path": ["a", 1, None]}, {"paths": "no soy lista"}]:
        codigo, salida = ejecutar(mcp("mcp__x__write_file", entrada), ruta_config)
        assert codigo == 0, entrada
