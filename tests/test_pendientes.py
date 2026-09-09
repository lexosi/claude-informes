"""`pendientes`: the sessions the hook saw but did not archive, and the fix.

A logging oversight cannot stay silent: a project's startup sessions are the
most valuable and exactly the ones that get lost. This command is the only way
to find out that you have been working for two days in a directory that is not
archived, so its output has to say WHAT TO DO, not just what is missing.
"""

import io
import json
import tempfile
from pathlib import Path

from claude_informes import cli
from claude_informes import hook as hk
from claude_informes import journal as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"

_TRANSCRIPTS = Path(tempfile.mkdtemp(prefix="ci-pendientes-transcripts-"))


def transcript_de(cwd):
    """A real transcript for a session started in `cwd`."""
    destino = _TRANSCRIPTS / tr.slug_de_cwd(str(cwd)) / "s.jsonl"
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(
        json.dumps({"type": "user", "cwd": str(cwd)}) + "\n", encoding="utf-8"
    )
    return str(destino)


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


# --- the name a startup would give a project (used in the log detail) ---


def test_the_name_it_would_have_comes_from_the_startup_not_the_cwd():
    transcripcion = "C:\\p\\C--proyectos-claude-informes\\s.jsonl"
    assert hk.nombre_que_tendria(transcripcion, "C:\\proyectos\\claude-informes") == (
        "claude-informes"
    )


def test_without_a_readable_startup_the_name_comes_from_the_slug():
    transcripcion = "C:\\p\\C--proyectos-alfa\\s.jsonl"
    assert hk.nombre_que_tendria(transcripcion, None) == "alfa"


# --- the log remembers what was not archived, with the startup and transcript ---


def test_the_skip_carries_the_transcript_and_the_name_it_would_have(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "work"
    raiz.mkdir()
    ruta_config = escribir_config([], raiz_informes=informes, roots=[raiz])
    fuera = tmp_path / "claude-informes"

    ejecutar(turno(fuera, transcript_de(fuera)), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.FUERA_DE_RAICES
    assert "nombre=claude-informes" in anotacion.detalle
    assert f"arranque={fuera}" in anotacion.detalle
    assert "transcript=" in anotacion.detalle


# --- `pendientes`: outside the roots ---


def test_pending_counts_the_sessions_outside_the_roots_and_says_the_line_to_add(
    escribir_config, informes, tmp_path, log, capsys
):
    raiz = tmp_path / "work"
    raiz.mkdir()
    ruta_config = escribir_config([], raiz_informes=informes, roots=[raiz])
    fuera = tmp_path / "claude-informes"
    transcripcion = transcript_de(fuera)

    for _ in range(3):
        ejecutar(turno(fuera, transcripcion), ruta_config)

    codigo = cli.main(["pendientes", "--config", str(ruta_config)])
    salida = capsys.readouterr().out

    assert codigo == 1
    assert "3 turn(s) not archived" in salida
    assert "under no watched root" in salida
    # the exact line to add: valid JSON, with backslashes escaped, copy-pastable
    esperado = json.dumps({"name": "claude-informes", "path": str(fuera)}, ensure_ascii=False)
    assert esperado in salida, "the exact, valid-JSON line to add to the config"
    assert "backfill" in salida, "and how to recover what was lost"


def test_pending_says_nothing_when_there_is_nothing(escribir_config, informes, capsys):
    ruta_config = escribir_config([], raiz_informes=informes)
    codigo = cli.main(["pendientes", "--config", str(ruta_config)])

    assert codigo == 0
    assert "No sessions seen outside" in capsys.readouterr().out


def test_pending_ignores_the_other_kinds_of_skips(
    proyecto_vigilado, informes, log, capsys
):
    """A turn skipped by the threshold is not a configuration oversight."""
    raiz, ruta_config = proyecto_vigilado
    ejecutar(turno(raiz, transcript_de(raiz)) | {"last_assistant_message": "corta\n1"}, ruta_config)

    cli.main(["pendientes", "--config", str(ruta_config)])
    assert "No sessions seen outside" in capsys.readouterr().out


# --- `pendientes`: filtered by an exclusion ---


def test_pending_names_the_exclusion_pattern_that_filters_a_project(
    escribir_config, informes, tmp_path, log, capsys
):
    raiz = tmp_path / "work"
    (raiz / "alfa-audit").mkdir(parents=True)
    ruta_config = escribir_config(
        [], raiz_informes=informes, roots=[raiz], exclusions=["*-audit*"]
    )
    clon = raiz / "alfa-audit"

    ejecutar(turno(clon, transcript_de(clon)), ruta_config)

    codigo = cli.main(["pendientes", "--config", str(ruta_config)])
    salida = capsys.readouterr().out

    assert codigo == 1
    assert "filtered by an exclusion" in salida
    assert "*-audit*" in salida, "it names the pattern to remove"
    assert 'remove it from "exclusions"' in salida
