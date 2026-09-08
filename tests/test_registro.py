"""The hook log. Silence on the console, never silence in the log."""

import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from claude_informes import cli
from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import informe as inf
from claude_informes import registro as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"
CORTA = "1\n2\n3"


def payload(**cambios):
    base = {
        "session_id": "s",
        "cwd": "",
        "stop_hook_active": False,
        "last_assistant_message": RESPUESTA,
    }
    base.update(cambios)
    if "transcript_path" not in base:
        base["transcript_path"] = str(
            Path("C:/proyectos") / tr.slug_de_cwd(str(base["cwd"])) / "s.jsonl"
        )
    return base


def ejecutar(datos, ruta_config, texto_crudo=None):
    crudo = texto_crudo if texto_crudo is not None else json.dumps(datos)
    return hk.main(entrada=io.StringIO(crudo), ruta_config=ruta_config)


# --- format ---


def test_the_line_carries_timestamp_project_result_and_detail():
    linea = reg.formatear(
        reg.ESCRITO, "alfa", "C:\\informes-claude\\x.json", datetime(2026, 8, 28, 16, 5, 9)
    )
    campos = [t.strip() for t in linea.split(" | ")]
    assert campos == [
        "2026-08-28T16:05:09",
        "alfa",
        "escrito",
        "C:\\informes-claude\\x.json",
    ]


def test_the_detail_never_splits_the_line_into_two():
    """A reason with line breaks cannot turn into two log entries."""
    linea = reg.formatear(reg.ERROR, "x", "algo\nen dos\nlineas")
    assert "\n" not in linea
    assert reg.leer_linea(linea).detalle == "algo en dos lineas"


def test_the_log_is_append_only(tmp_path):
    ruta = tmp_path / "hook.log"
    reg.anotar(ruta, reg.ESCRITO, "uno", "a.json")
    reg.anotar(ruta, reg.OMITIDO_UMBRAL, "dos", "3 lineas")

    assert [a.proyecto for a in reg.leer(ruta)] == ["uno", "dos"]


def test_the_log_is_written_with_lf_line_endings(tmp_path):
    ruta = tmp_path / "hook.log"
    reg.anotar(ruta, reg.ESCRITO, "uno", "a.json")
    reg.anotar(ruta, reg.ESCRITO, "uno", "b.json")

    assert b"\r\n" not in ruta.read_bytes()


def test_unreadable_lines_are_ignored_one_by_one(tmp_path):
    ruta = tmp_path / "hook.log"
    reg.anotar(ruta, reg.ESCRITO, "uno", "a.json")
    with open(ruta, "a", encoding="utf-8", newline="\n") as f:
        f.write("basura sin formato\n")
    reg.anotar(ruta, reg.ESCRITO, "dos", "b.json")

    assert [a.proyecto for a in reg.leer(ruta)] == ["uno", "dos"]


def test_a_nonexistent_log_is_read_as_empty(tmp_path):
    assert reg.leer(tmp_path / "no-existe.log") == []


def test_the_default_path_is_a_sibling_of_the_archive_not_a_child():
    ruta = reg.ruta_por_defecto("C:\\informes-claude")
    assert ruta == Path("C:\\informes-claude.log")
    assert "informes-claude" not in ruta.parent.name


# --- the five results ---


def test_a_written_turn_is_logged_with_its_path(proyecto_vigilado, informes, log):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ESCRITO
    assert anotacion.proyecto == "vigilado"
    assert anotacion.ruta.is_file()
    assert anotacion.ruta == next(Path(informes).rglob("*.json"))


def test_a_short_turn_is_logged_as_skipped_by_threshold(proyecto_vigilado, log):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz), last_assistant_message=CORTA), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_UMBRAL
    assert anotacion.proyecto == "vigilado"
    assert "3 lineas" in anotacion.detalle and "umbral 5" in anotacion.detalle


def test_a_foreign_cwd_is_logged_as_skipped_by_cwd(proyecto_vigilado, tmp_path, log):
    _, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(tmp_path / "beta")), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert anotacion.proyecto == reg.SIN_PROYECTO
    assert "beta" in anotacion.detalle


def test_the_tools_own_cwd_is_logged_as_written(
    escribir_config, informes, log
):
    """With the guard removed, a turn on the tool is a normal turn."""
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia)}], raiz_informes=informes
    )
    ejecutar(payload(cwd=str(propia)), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ESCRITO
    assert anotacion.proyecto == "claude-informes"
    assert anotacion.ruta.is_file()


def test_a_broken_payload_is_logged_as_error(proyecto_vigilado, log):
    _, ruta_config = proyecto_vigilado
    ejecutar(None, ruta_config, texto_crudo="{esto no es json")

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ERROR
    assert "JSONDecodeError" in anotacion.detalle


def test_the_five_results_all_fit_in_the_same_log(
    escribir_config, informes, tmp_path, log, monkeypatch
):
    """One log, one turn per line, the five cases distinguishable."""
    raiz = tmp_path / "vigilado"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "vigilado", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=CORTA), ruta_config)
    ejecutar(payload(cwd=str(tmp_path / "ajeno")), ruta_config)
    ejecutar(payload(cwd=str(raiz), stop_hook_active=True), ruta_config)
    ejecutar(None, ruta_config, texto_crudo="no soy json")

    assert [a.resultado for a in reg.leer(log)] == [
        reg.ESCRITO,
        reg.OMITIDO_UMBRAL,
        reg.OMITIDO_SESION,
        reg.OMITIDO_REENTRADA,
        reg.ERROR,
    ]


def test_a_hook_reentry_also_leaves_a_line(proyecto_vigilado, log):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz), stop_hook_active=True), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_REENTRADA


def test_each_turn_leaves_exactly_one_line(proyecto_vigilado, log):
    """One line per normal turn.

    That a degraded turn adds a second line is a separate guarantee, checked by
    test_the_warning_only_appears_when_the_degraded_path_actually_archives (in
    test_proyecto_del_turno.py); this test only exercises the normal path.
    """
    raiz, ruta_config = proyecto_vigilado
    for i in range(4):
        ejecutar(payload(cwd=str(raiz), last_assistant_message=RESPUESTA + str(i)), ruta_config)

    assert len(reg.leer(log)) == 4


# --- what must not happen ---


def test_if_writing_the_report_fails_it_exits_0_and_stays_logged(
    proyecto_vigilado, informes, log, monkeypatch, capsys
):
    """The failure is invisible on the console, but not in the log."""
    raiz, ruta_config = proyecto_vigilado

    def escritura_rota(*args, **kwargs):
        raise OSError("no queda espacio en el disco")

    monkeypatch.setattr(inf, "escribir", escritura_rota)

    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not Path(informes).exists()

    # invisible on the console: not a byte to stdout or stderr
    capturado = capsys.readouterr()
    assert capturado.out == "" and capturado.err == ""

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ERROR
    assert "no queda espacio en el disco" in anotacion.detalle


def test_if_the_log_fails_it_exits_0_and_stays_silent(proyecto_vigilado, informes, log, capsys):
    raiz, ruta_config = proyecto_vigilado

    def anotar_roto(*args, **kwargs):
        raise PermissionError("el log es de solo lectura")

    original = reg.anotar
    reg.anotar = anotar_roto
    try:
        codigo = ejecutar(payload(cwd=str(raiz)), ruta_config)
    finally:
        reg.anotar = original

    capturado = capsys.readouterr()
    assert codigo == 0
    assert capturado.out == "" and capturado.err == ""
    assert not log.exists()
    assert len(list(Path(informes).rglob("*.json"))) == 1, "the report was indeed written"


def test_if_both_the_log_and_the_report_fail_it_still_exits_0(proyecto_vigilado, log, monkeypatch, capsys):
    raiz, ruta_config = proyecto_vigilado
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("nada")))

    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert capsys.readouterr().out == ""


def test_the_log_is_never_written_to_stdout(proyecto_vigilado, capsys):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    capturado = capsys.readouterr()
    assert capturado.out == "" and capturado.err == ""


# --- the `ultimo` command ---


def escribir_config_con_proyecto(escribir_config, informes, tmp_path, nombre="vigilado"):
    raiz = tmp_path / nombre
    raiz.mkdir(exist_ok=True)
    return raiz, escribir_config(
        [{"nombre": nombre, "cwd": str(raiz)}], raiz_informes=informes
    )


def test_last_gives_the_real_file_verified_on_disk(
    escribir_config, informes, tmp_path, capsys
):
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    escrito = next(Path(informes).rglob("*.json"))

    codigo = cli.main(["ultimo", "--proyecto", "vigilado", "--config", str(ruta_config)])

    salida = capsys.readouterr().out
    assert codigo == 0
    assert escrito.name in salida
    assert str(escrito) in salida
    assert "still on disk" in salida


def test_last_reports_when_the_file_is_gone_without_alarming(
    escribir_config, informes, tmp_path, capsys
):
    """The log records a past fact, not an index of live files.

    Deleting or moving a report does not turn its `escrito` line into a lie: it keeps
    describing what happened that day. `ultimo` reports it as information (exits
    0, via stdout), not as an alarm (before: exit 1, stderr, 'NO EXISTE EN DISCO').
    """
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    next(Path(informes).rglob("*.json")).unlink()  # its day folder is still there

    codigo = cli.main(["ultimo", "--config", str(ruta_config)])

    capturado = capsys.readouterr()
    assert codigo == 0, "the file's absence is information, not an error"
    assert capturado.err == "", "not an alarm: nothing on stderr"
    assert "no longer where the log recorded it" in capturado.out
    assert "renamed or deleted within" in capturado.out, "it distinguishes: its folder is still there"
    assert "miente" not in capturado.out


def test_last_distinguishes_when_the_whole_folder_disappears(
    escribir_config, informes, tmp_path, capsys
):
    """The other branch: not only is the file missing, its day folder is missing."""
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    escrito = next(Path(informes).rglob("*.json"))
    import shutil

    shutil.rmtree(escrito.parent)  # takes the whole day folder with it

    codigo = cli.main(["ultimo", "--config", str(ruta_config)])
    salida = capsys.readouterr().out

    assert codigo == 0
    assert "does not exist either" in salida
    assert "was moved or relocated" in salida


def test_last_picks_the_most_recent_one_of_that_project(
    escribir_config, informes, tmp_path, capsys
):
    uno = tmp_path / "uno"
    dos = tmp_path / "dos"
    uno.mkdir()
    dos.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "uno", "cwd": str(uno)}, {"nombre": "dos", "cwd": str(dos)}],
        raiz_informes=informes,
    )
    ejecutar(payload(cwd=str(uno), last_assistant_message=RESPUESTA + "A"), ruta_config)
    ejecutar(payload(cwd=str(dos), last_assistant_message=RESPUESTA + "B"), ruta_config)
    ejecutar(payload(cwd=str(uno), last_assistant_message=RESPUESTA + "C"), ruta_config)

    cli.main(["ultimo", "--proyecto", "uno", "--config", str(ruta_config)])
    salida = capsys.readouterr().out

    assert "project  : uno" in salida
    assert "02-" in salida, "the second of 'uno', not the one of 'dos'"


def test_last_ignores_the_lines_that_are_not_writes(
    escribir_config, informes, tmp_path, capsys
):
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=CORTA), ruta_config)

    codigo = cli.main(["ultimo", "--config", str(ruta_config)])
    assert codigo == 0
    assert "01-" in capsys.readouterr().out


def test_last_says_so_when_there_is_no_log(escribir_config, tmp_path, capsys):
    ruta_config = escribir_config([{"nombre": "x", "cwd": str(tmp_path)}])
    codigo = cli.main(["ultimo", "--config", str(ruta_config)])

    assert codigo == 2
    assert "empty or does not exist" in capsys.readouterr().err


def test_last_says_so_when_that_project_has_no_reports(
    escribir_config, informes, tmp_path, capsys
):
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    codigo = cli.main(["ultimo", "--proyecto", "beta", "--config", str(ruta_config)])

    assert codigo == 2
    assert "beta" in capsys.readouterr().err
