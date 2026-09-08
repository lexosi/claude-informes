"""The envelope, its path and its writing to disk."""

import json
import os
import subprocess
import sys
import threading
from pathlib import Path

import pytest

from claude_informes import informe as inf

RAIZ = Path(__file__).resolve().parent.parent
MARKDOWN = "# Informe de la prueba diaria\n\nuno\ndos\ntres"
SLUG = "informe-prueba-diaria"


def sobre(markdown=MARKDOWN, **extras):
    datos = {"session_id": "s", "cwd": None}
    datos.update(extras)
    return inf.construir(markdown, **datos)


def dia(informes, proyecto="repo", fecha="2026-08-28"):
    return Path(informes) / proyecto / fecha


# --- folder structure ---


def test_the_path_is_root_then_project_then_day(tmp_path):
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.parent == dia(tmp_path)
    assert destino.name == f"01-{SLUG}.json"


def test_both_levels_are_created_in_one_go(tmp_path):
    inf.escribir(tmp_path / "sin" / "hacer", "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert (tmp_path / "sin" / "hacer" / "repo" / "2026-08-28").is_dir()


def test_an_existing_project_folder_is_reused(tmp_path):
    dia(tmp_path).mkdir(parents=True)
    inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert [p.name for p in tmp_path.iterdir()] == ["repo"]
    assert [p.name for p in (tmp_path / "repo").iterdir()] == ["2026-08-28"]


def test_no_case_variants_of_an_already_existing_folder_are_created(tmp_path):
    """On Windows 'Repo' and 'repo' are the same; the one already there is used."""
    (tmp_path / "Repo").mkdir()
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert len(list(tmp_path.iterdir())) == 1
    assert destino.parent.parent.name == "Repo"


def test_two_different_days_are_two_folders(tmp_path):
    inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-27T10:00:00Z"))
    inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert sorted(p.name for p in (tmp_path / "repo").iterdir()) == [
        "2026-08-27",
        "2026-08-28",
    ]


def test_two_projects_do_not_share_a_folder(tmp_path):
    inf.escribir(tmp_path, "uno", sobre(cuando="2026-08-28T10:00:00Z"))
    inf.escribir(tmp_path, "dos", sobre(cuando="2026-08-28T10:00:00Z"))

    assert sorted(p.name for p in tmp_path.iterdir()) == ["dos", "uno"]
    assert len(list(dia(tmp_path, "uno").glob("*.json"))) == 1
    assert len(list(dia(tmp_path, "dos").glob("*.json"))) == 1


# --- ordinal ---


def test_the_first_report_of_the_day_is_number_01(tmp_path):
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.name.startswith("01-")


def test_the_ordinal_continues_where_the_previous_one_left_off(tmp_path):
    dia(tmp_path).mkdir(parents=True)
    (dia(tmp_path) / "07-lo-que-sea.json").write_text("{}", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.name.startswith("08-")


def test_the_ordinal_resets_to_01_each_day(tmp_path):
    for _ in range(3):
        inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-27T10:00:00Z"))
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert sorted(p.name[:2] for p in dia(tmp_path, fecha="2026-08-27").iterdir()) == [
        "01",
        "02",
        "03",
    ]
    assert destino.name.startswith("01-")


def test_the_ordinal_does_not_get_confused_between_projects(tmp_path):
    inf.escribir(tmp_path, "uno", sobre(cuando="2026-08-28T10:00:00Z"))
    inf.escribir(tmp_path, "uno", sobre(cuando="2026-08-28T10:00:00Z"))
    destino = inf.escribir(tmp_path, "dos", sobre(cuando="2026-08-28T10:00:00Z"))

    assert destino.name.startswith("01-")


def test_two_reports_with_the_same_slug_do_not_overwrite_each_other(tmp_path):
    uno = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    dos = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert uno.name == f"01-{SLUG}.json"
    assert dos.name == f"02-{SLUG}.json"
    assert len(list(dia(tmp_path).glob("*.json"))) == 2


def test_an_already_reserved_name_is_not_overwritten(tmp_path):
    """Simulates the simultaneous turn: the free ordinal is no longer free."""
    dia(tmp_path).mkdir(parents=True)
    ocupado = dia(tmp_path) / f"01-{SLUG}.json"
    ocupado.write_text("de otro turno", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert destino.name == f"02-{SLUG}.json"
    assert ocupado.read_text(encoding="utf-8") == "de otro turno"


def test_unrelated_files_in_the_folder_do_not_get_in_the_way(tmp_path):
    dia(tmp_path).mkdir(parents=True)
    (dia(tmp_path) / "notas.txt").write_text("hola", encoding="utf-8")
    (dia(tmp_path) / "sin-ordinal.json").write_text("{}", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.name.startswith("01-")


# --- writing ---


def test_no_temporary_file_is_left_behind(tmp_path):
    inf.escribir(tmp_path, "repo", sobre())
    assert list(tmp_path.rglob("*.tmp")) == []


def test_the_json_is_readable_and_indented(tmp_path):
    destino = inf.escribir(tmp_path, "repo", sobre())
    texto = destino.read_text(encoding="utf-8")
    assert texto.endswith("\n")
    assert json.loads(texto)["respuesta_markdown"] == MARKDOWN


# --- date and time ---


def test_a_utc_timestamp_is_converted_to_local_time():
    resultado = inf.construir("x", session_id=None, cwd=None, cuando="2026-08-28T11:31:37.388Z")
    assert resultado["fecha"] == "2026-08-28"
    assert len(resultado["hora"].split(":")) == 3


def test_an_unreadable_timestamp_does_not_blow_up():
    resultado = inf.construir("x", session_id=None, cwd=None, cuando="ayer por la tarde")
    assert len(resultado["fecha"]) == 10


def test_without_a_timestamp_the_clock_is_used():
    resultado = inf.construir("x", session_id=None, cwd=None)
    assert len(resultado["fecha"]) == 10 and len(resultado["hora"]) == 8


# --- git ---


def test_git_in_a_nonexistent_directory_returns_none(tmp_path):
    assert inf.datos_git(str(tmp_path / "fantasma")) == (None, None)


def test_git_outside_a_repository_returns_none(tmp_path):
    assert inf.datos_git(str(tmp_path)) == (None, None)


# --- the launcher, exactly as Claude Code runs it ---


def lanzar(entrada, ruta_config=None):
    """The launcher in another process.

    `ruta_config` is NOT optional for convenience: without it, the launcher reads the
    REAL config and writes to the REAL file. A test that runs the
    launcher and does not pass it is writing to production.
    """
    entorno = dict(os.environ)
    if ruta_config is not None:
        entorno["CLAUDE_INFORMES_CONFIG"] = str(ruta_config)
    return subprocess.run(
        [sys.executable, str(RAIZ / "hook_informes.py")],
        input=entrada,
        capture_output=True,
        text=True,
        timeout=30,
        env=entorno,
    )


def test_the_launcher_exits_0_with_a_corrupt_payload():
    proceso = lanzar("{esto no es json")
    assert proceso.returncode == 0
    assert proceso.stdout == "" and proceso.stderr == ""


def test_the_launcher_exits_0_with_a_foreign_cwd(tmp_path):
    proceso = lanzar(
        json.dumps(
            {
                "session_id": "s",
                "cwd": str(tmp_path),
                "stop_hook_active": False,
                "last_assistant_message": "# Hola\n\nuno\ndos\ntres\ncuatro\ncinco",
            }
        )
    )
    assert proceso.returncode == 0
    assert proceso.stdout == "" and proceso.stderr == ""
    assert list(tmp_path.rglob("*.json")) == []


def test_the_launcher_archives_with_the_tools_own_cwd(
    tmp_path, escribir_config, informes
):
    """With the guard removed, the tool is archived like any project.

    This test used to write to the REAL file: it ran the launcher without
    passing it config, so it read the real one. It passed because it looked in
    `claude-informes/informes/`, the old destination, which no longer exists. The
    guard covered it up; once removed, it began leaving test reports in
    `C:/informes-claude/claude-informes/`.
    """
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(RAIZ)}], raiz_informes=informes
    )

    proceso = lanzar(
        json.dumps(
            {
                "session_id": "s",
                "cwd": str(RAIZ),
                "stop_hook_active": False,
                "last_assistant_message": "# Hola\n\nuno\ndos\ntres\ncuatro\ncinco",
            }
        ),
        ruta_config,
    )

    assert proceso.returncode == 0
    escritos = sorted(Path(informes).rglob("*.json"))
    assert [p.name for p in escritos] == ["01-uno-dos-tres-cuatro-cinco.json"]
    assert not (RAIZ / "informes").exists(), "the old destination must not come back to life"


def test_the_launcher_exits_0_with_empty_stdin():
    assert lanzar("").returncode == 0


# --- the lock: the .tmp reserves, the .json only appears at the end ---


def test_the_json_does_not_exist_until_it_has_content(tmp_path, monkeypatch):
    """While writing there is `.tmp` and NO `.json`. Never a zero-byte one."""
    vistos = []
    real = inf.json.dumps

    def espiar(*args, **kwargs):
        vistos.append(sorted(p.name for p in dia(tmp_path).iterdir()))
        return real(*args, **kwargs)

    monkeypatch.setattr(inf.json, "dumps", espiar)
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert vistos == [[f"01-{SLUG}.json.tmp"]], "the .json cannot exist before it has content"
    assert destino.name == f"01-{SLUG}.json"
    assert [p.name for p in dia(tmp_path).iterdir()] == [f"01-{SLUG}.json"]


def test_an_orphan_tmp_has_its_ordinal_taken(tmp_path):
    """If the .tmp files were not counted, the lock would be useless."""
    dia(tmp_path).mkdir(parents=True)
    (dia(tmp_path) / "01-de-otro-turno.json.tmp").write_text("", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert destino.name == f"02-{SLUG}.json"


def test_eight_simultaneous_turns_do_not_repeat_an_ordinal(tmp_path):
    """O_EXCL still rules now that the lock is the .tmp."""
    errores = []

    def escribe():
        try:
            inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
        except Exception as error:  # noqa: BLE001
            errores.append(error)

    hilos = [threading.Thread(target=escribe) for _ in range(8)]
    for hilo in hilos:
        hilo.start()
    for hilo in hilos:
        hilo.join()

    assert errores == []
    nombres = sorted(p.name for p in dia(tmp_path).iterdir())
    assert len(nombres) == 8
    assert sorted(n[:2] for n in nombres) == [f"{i:02d}" for i in range(1, 9)]


def test_the_race_does_not_reuse_an_already_published_ordinal(tmp_path, monkeypatch):
    """Real data loss: `os.replace` frees the `.tmp` when renaming it, and a
    lagging thread that had chosen that same ordinal reserves it again and its
    `os.replace` clobbers the `.json` that another turn had already written.

    The window between choosing the ordinal and reserving it is widened on purpose so
    that the race is deterministic: without the fix, some turn is lost in each
    batch; with the fix, the N reports always coexist.
    """
    import time

    real = inf.siguiente_ordinal

    def con_ventana(directorio):
        ordinal = real(directorio)
        time.sleep(0.02)
        return ordinal

    monkeypatch.setattr(inf, "siguiente_ordinal", con_ventana)

    N = 8
    for ronda in range(15):
        raiz = tmp_path / f"ronda-{ronda}"
        errores = []

        def escribe():
            try:
                inf.escribir(raiz, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
            except Exception as error:  # noqa: BLE001
                errores.append(error)

        hilos = [threading.Thread(target=escribe) for _ in range(N)]
        for hilo in hilos:
            hilo.start()
        for hilo in hilos:
            hilo.join()

        assert errores == []
        nombres = sorted(p.name for p in dia(raiz).iterdir())
        assert len(nombres) == N, f"round {ronda}: {len(nombres)} of {N} reports; one clobbered"


def test_a_failure_creating_the_folder_is_a_write_failure(tmp_path):
    """mkdir and the .tmp reservation were outside the try, so their failure came out
    raw instead of FalloDeEscritura and lost the turn's path. Now the whole
    body of escribir is wrapped: creating the day folder over a file
    (not a folder) gives FalloDeEscritura, and its path identifies where it was going.
    """
    (tmp_path / "repo").write_text("soy un fichero, no una carpeta", encoding="utf-8")

    with pytest.raises(inf.FalloDeEscritura) as fallo:
        inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert "repo" in str(fallo.value.ruta)


def test_if_the_write_fails_nothing_is_left_on_disk(tmp_path, monkeypatch):
    """The three zero-byte production reports were exactly this."""

    def revienta(*args, **kwargs):
        raise UnicodeEncodeError("utf-8", "x", 0, 1, "de mentira")

    monkeypatch.setattr(inf.json, "dumps", revienta)
    with pytest.raises(inf.FalloDeEscritura) as fallo:
        inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert fallo.value.ruta.name == f"01-{SLUG}.json"
    assert isinstance(fallo.value.causa, UnicodeEncodeError)
    assert list(dia(tmp_path).iterdir()) == []
