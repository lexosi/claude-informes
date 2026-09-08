"""Dar de alta un proyecto, y enterarse de lo que no se archivo.

Un olvido del registro no puede quedarse en silencio: las sesiones de arranque
de un proyecto son las mas valiosas y son justo las que se pierden.
"""

import io
import json
from pathlib import Path

import pytest

from claude_informes import alta
from claude_informes import cli
from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import registro as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"


def turno(cwd, transcript):
    return {
        "session_id": "s",
        "cwd": str(cwd),
        "transcript_path": str(transcript),
        "stop_hook_active": False,
        "last_assistant_message": RESPUESTA,
    }


def ejecutar(datos, ruta_config):
    return hk.main(entrada=io.StringIO(json.dumps(datos)), ruta_config=ruta_config)


def transcript_de(raiz):
    return str(Path("C:/proyectos") / tr.slug_de_cwd(str(raiz)) / "sesion.jsonl")


# --- `nuevo`: los tres pasos en uno ---


def test_new_creates_the_folder_and_registers_it(tmp_path, escribir_config, informes):
    ruta_config = escribir_config([], raiz_informes=informes)
    donde = tmp_path / "proyectos"

    carpeta, destino = alta.registrar("mi-proyecto", donde, ruta_config)

    assert carpeta == donde / "mi-proyecto" and carpeta.is_dir()
    configuracion = cfg.cargar(destino)
    assert [p.nombre for p in configuracion.proyectos] == ["mi-proyecto"]
    assert configuracion.proyectos[0].raiz == str(carpeta)


def test_what_new_registers_is_recognized_by_the_hook(tmp_path, escribir_config, informes):
    """La prueba que importa: registrar y que el turno se archive."""
    ruta_config = escribir_config([], raiz_informes=informes)
    carpeta, _ = alta.registrar("recien-nacido", tmp_path / "proyectos", ruta_config)

    ejecutar(turno(carpeta, transcript_de(carpeta)), ruta_config)

    dia = next((Path(informes) / "recien-nacido").iterdir())
    assert len(list(dia.glob("*.json"))) == 1


def test_new_preserves_the_projects_that_were_already_there(tmp_path, escribir_config, informes):
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": "C:\\proyectos\\alfa"}],
        raiz_informes=informes,
    )
    alta.registrar("otro", tmp_path / "p", ruta_config)

    configuracion = cfg.cargar(ruta_config)
    assert sorted(p.nombre for p in configuracion.proyectos) == ["alfa", "otro"]
    assert configuracion.raiz_informes == Path(informes), "la raiz global no se toca"


def test_new_normalizes_the_name(tmp_path, escribir_config):
    ruta_config = escribir_config([])
    carpeta, _ = alta.registrar("Mi Proyecto Nuevo", tmp_path / "p", ruta_config)
    assert carpeta.name == "mi-proyecto-nuevo"


def test_new_does_not_overwrite_an_already_registered_project(tmp_path, escribir_config):
    ruta_config = escribir_config([])
    alta.registrar("uno", tmp_path / "p", ruta_config)

    with pytest.raises(alta.YaExiste):
        alta.registrar("uno", tmp_path / "p", ruta_config)


def test_new_detects_the_same_folder_under_a_different_name(tmp_path, escribir_config):
    ruta_config = escribir_config(
        [{"nombre": "ya-estaba", "cwd": str(tmp_path / "p" / "repe")}]
    )
    with pytest.raises(alta.YaExiste):
        alta.registrar("repe", tmp_path / "p", ruta_config)


def test_new_reuses_a_folder_that_already_exists(tmp_path, escribir_config):
    ruta_config = escribir_config([])
    (tmp_path / "p" / "existente").mkdir(parents=True)
    (tmp_path / "p" / "existente" / "README.md").write_text("hola", encoding="utf-8")

    carpeta, _ = alta.registrar("existente", tmp_path / "p", ruta_config)

    assert (carpeta / "README.md").read_text(encoding="utf-8") == "hola"


def test_new_rejects_an_unusable_name(tmp_path, escribir_config):
    with pytest.raises(ValueError):
        alta.registrar("???", tmp_path / "p", escribir_config([]))


def test_the_new_command_says_where_to_open_the_cli(tmp_path, escribir_config, capsys):
    ruta_config = escribir_config([])
    codigo = cli.main(
        ["nuevo", "un-proyecto", "--en", str(tmp_path / "p"), "--config", str(ruta_config)]
    )
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "You can now open the CLI there" in salida
    assert str(tmp_path / "p" / "un-proyecto") in salida


def test_the_new_command_warns_about_a_duplicate(tmp_path, escribir_config, capsys):
    ruta_config = escribir_config([])
    cli.main(["nuevo", "x", "--en", str(tmp_path / "p"), "--config", str(ruta_config)])
    codigo = cli.main(["nuevo", "x", "--en", str(tmp_path / "p"), "--config", str(ruta_config)])

    assert codigo == 3
    assert "ya hay un proyecto" in capsys.readouterr().err


# --- el log recuerda lo que no se archivo ---


def test_the_skip_carries_the_transcript_and_the_name_it_would_have(
    escribir_config, informes, tmp_path, log
):
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(tmp_path / "alfa")}],
        raiz_informes=informes,
    )
    sin_registrar = tmp_path / "claude-informes"
    transcripcion = tmp_path / "projects" / tr.slug_de_cwd(str(sin_registrar)) / "s.jsonl"
    transcripcion.parent.mkdir(parents=True)
    transcripcion.write_text(
        json.dumps({"type": "user", "cwd": str(sin_registrar)}) + "\n", encoding="utf-8"
    )

    ejecutar(turno(sin_registrar, transcripcion), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert "nombre=claude-informes" in anotacion.detalle
    assert f"transcript={transcripcion}" in anotacion.detalle
    assert f"arranque={sin_registrar}" in anotacion.detalle


def test_the_name_it_would_have_comes_from_the_startup_not_the_cwd(tmp_path):
    transcripcion = "C:\\p\\C--proyectos-claude-informes\\s.jsonl"
    assert hk.nombre_que_tendria(transcripcion, "C:\\proyectos\\claude-informes") == (
        "claude-informes"
    )


def test_without_a_readable_startup_the_name_comes_from_the_slug(tmp_path):
    transcripcion = "C:\\p\\C--proyectos-alfa\\s.jsonl"
    assert hk.nombre_que_tendria(transcripcion, None) == "alfa"


# --- `pendientes` ---


def test_pending_counts_the_unarchived_turns(
    escribir_config, informes, tmp_path, log, capsys
):
    ruta_config = escribir_config([], raiz_informes=informes)
    sin_registrar = tmp_path / "claude-informes"
    transcripcion = tmp_path / "projects" / tr.slug_de_cwd(str(sin_registrar)) / "s.jsonl"
    transcripcion.parent.mkdir(parents=True)
    transcripcion.write_text(
        json.dumps({"type": "user", "cwd": str(sin_registrar)}) + "\n", encoding="utf-8"
    )
    for _ in range(3):
        ejecutar(turno(sin_registrar, transcripcion), ruta_config)

    codigo = cli.main(["pendientes", "--config", str(ruta_config)])
    salida = capsys.readouterr().out

    assert codigo == 1
    assert "3 turn(s) unarchived" in salida
    assert "claude-informes" in salida
    assert str(transcripcion) in salida
    assert "nuevo claude-informes" in salida, "dice como registrarlo"
    assert "backfill" in salida, "y como recuperar lo perdido"


def test_pending_says_nothing_when_there_is_nothing(escribir_config, informes, capsys):
    ruta_config = escribir_config([], raiz_informes=informes)
    codigo = cli.main(["pendientes", "--config", str(ruta_config)])

    assert codigo == 0
    assert "No unarchived turns" in capsys.readouterr().out


def test_pending_ignores_the_other_kinds_of_skips(
    proyecto_vigilado, informes, log, capsys
):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(turno(raiz, transcript_de(raiz)) | {"last_assistant_message": "corta\n1"}, ruta_config)

    cli.main(["pendientes", "--config", str(ruta_config)])
    assert "No unarchived turns" in capsys.readouterr().out
