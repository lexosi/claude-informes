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


def test_nuevo_crea_la_carpeta_y_la_registra(tmp_path, escribir_config, informes):
    ruta_config = escribir_config([], raiz_informes=informes)
    donde = tmp_path / "proyectos"

    carpeta, destino = alta.registrar("mi-proyecto", donde, ruta_config)

    assert carpeta == donde / "mi-proyecto" and carpeta.is_dir()
    configuracion = cfg.cargar(destino)
    assert [p.nombre for p in configuracion.proyectos] == ["mi-proyecto"]
    assert configuracion.proyectos[0].raiz == str(carpeta)


def test_lo_que_registra_nuevo_lo_reconoce_el_hook(tmp_path, escribir_config, informes):
    """La prueba que importa: registrar y que el turno se archive."""
    ruta_config = escribir_config([], raiz_informes=informes)
    carpeta, _ = alta.registrar("recien-nacido", tmp_path / "proyectos", ruta_config)

    ejecutar(turno(carpeta, transcript_de(carpeta)), ruta_config)

    dia = next((Path(informes) / "recien-nacido").iterdir())
    assert len(list(dia.glob("*.json"))) == 1


def test_nuevo_conserva_los_proyectos_que_ya_habia(tmp_path, escribir_config, informes):
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": "C:\\proyectos\\alfa"}],
        raiz_informes=informes,
    )
    alta.registrar("otro", tmp_path / "p", ruta_config)

    configuracion = cfg.cargar(ruta_config)
    assert sorted(p.nombre for p in configuracion.proyectos) == ["alfa", "otro"]
    assert configuracion.raiz_informes == Path(informes), "la raiz global no se toca"


def test_nuevo_normaliza_el_nombre(tmp_path, escribir_config):
    ruta_config = escribir_config([])
    carpeta, _ = alta.registrar("Mi Proyecto Nuevo", tmp_path / "p", ruta_config)
    assert carpeta.name == "mi-proyecto-nuevo"


def test_nuevo_no_pisa_un_proyecto_ya_registrado(tmp_path, escribir_config):
    ruta_config = escribir_config([])
    alta.registrar("uno", tmp_path / "p", ruta_config)

    with pytest.raises(alta.YaExiste):
        alta.registrar("uno", tmp_path / "p", ruta_config)


def test_nuevo_detecta_la_misma_carpeta_con_otro_nombre(tmp_path, escribir_config):
    ruta_config = escribir_config(
        [{"nombre": "ya-estaba", "cwd": str(tmp_path / "p" / "repe")}]
    )
    with pytest.raises(alta.YaExiste):
        alta.registrar("repe", tmp_path / "p", ruta_config)


def test_nuevo_reutiliza_una_carpeta_que_ya_existe(tmp_path, escribir_config):
    ruta_config = escribir_config([])
    (tmp_path / "p" / "existente").mkdir(parents=True)
    (tmp_path / "p" / "existente" / "README.md").write_text("hola", encoding="utf-8")

    carpeta, _ = alta.registrar("existente", tmp_path / "p", ruta_config)

    assert (carpeta / "README.md").read_text(encoding="utf-8") == "hola"


def test_nuevo_rechaza_un_nombre_inservible(tmp_path, escribir_config):
    with pytest.raises(ValueError):
        alta.registrar("???", tmp_path / "p", escribir_config([]))


def test_la_orden_nuevo_dice_donde_abrir_el_cli(tmp_path, escribir_config, capsys):
    ruta_config = escribir_config([])
    codigo = cli.main(
        ["nuevo", "un-proyecto", "--en", str(tmp_path / "p"), "--config", str(ruta_config)]
    )
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "You can now open the CLI there" in salida
    assert str(tmp_path / "p" / "un-proyecto") in salida


def test_la_orden_nuevo_avisa_de_un_duplicado(tmp_path, escribir_config, capsys):
    ruta_config = escribir_config([])
    cli.main(["nuevo", "x", "--en", str(tmp_path / "p"), "--config", str(ruta_config)])
    codigo = cli.main(["nuevo", "x", "--en", str(tmp_path / "p"), "--config", str(ruta_config)])

    assert codigo == 3
    assert "ya hay un proyecto" in capsys.readouterr().err


# --- el log recuerda lo que no se archivo ---


def test_la_omision_lleva_transcript_y_el_nombre_que_tendria(
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


def test_el_nombre_que_tendria_sale_del_arranque_no_del_cwd(tmp_path):
    transcripcion = "C:\\p\\C--proyectos-claude-informes\\s.jsonl"
    assert hk.nombre_que_tendria(transcripcion, "C:\\proyectos\\claude-informes") == (
        "claude-informes"
    )


def test_sin_arranque_legible_el_nombre_sale_del_slug(tmp_path):
    transcripcion = "C:\\p\\C--proyectos-alfa\\s.jsonl"
    assert hk.nombre_que_tendria(transcripcion, None) == "alfa"


# --- `pendientes` ---


def test_pendientes_cuenta_los_turnos_no_archivados(
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


def test_pendientes_no_dice_nada_si_no_hay_nada(escribir_config, informes, capsys):
    ruta_config = escribir_config([], raiz_informes=informes)
    codigo = cli.main(["pendientes", "--config", str(ruta_config)])

    assert codigo == 0
    assert "No unarchived turns" in capsys.readouterr().out


def test_pendientes_ignora_las_demas_omisiones(
    proyecto_vigilado, informes, log, capsys
):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(turno(raiz, transcript_de(raiz)) | {"last_assistant_message": "corta\n1"}, ruta_config)

    cli.main(["pendientes", "--config", str(ruta_config)])
    assert "No unarchived turns" in capsys.readouterr().out
