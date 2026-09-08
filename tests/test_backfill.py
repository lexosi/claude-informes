"""Backfill: reconstruct reports for past turns from a transcript."""

import json
from pathlib import Path

import pytest

from claude_informes import backfill as bf
from claude_informes import cli
from claude_informes import informe as inf
from claude_informes import registro as reg
from claude_informes import transcript as tr

LARGO_A = "# Primer turno del barrido\n\nuno\ndos\ntres\ncuatro"
LARGO_B = "# Segundo turno del barrido\n\nuno\ndos\ntres\ncuatro"
LARGO_C = "# Tercer turno cerrado\n\nuno\ndos\ntres\ncuatro"
LARGO_D = "# Turno de la vispera anterior\n\nuno\ndos\ntres\ncuatro"

SLUG_A = "01-primer-turno-barrido.json"
SLUG_B = "02-segundo-turno-barrido.json"
SLUG_C = "03-tercer-turno-cerrado.json"


def fecha_local(marca):
    """The date the tool will assign to that timestamp."""
    return inf.construir("x", session_id=None, cwd=None, cuando=marca)["fecha"]


AYER = fecha_local("2026-08-27T10:00:00Z")
HOY = fecha_local("2026-08-28T10:00:00Z")


def turno(texto, *, marca="2026-08-28T10:00:00Z", uuid="u1", cwd="C:\\repo", sesion="s1"):
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": marca,
        "sessionId": sesion,
        "cwd": cwd,
        "gitBranch": "main",
        "message": {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": texto}],
        },
    }


def ruido():
    """Records that the backfill must ignore."""
    return [
        {"type": "user", "message": {"content": "hola"}},
        {"type": "attachment", "payload": {}},
        {
            "type": "assistant",
            "message": {
                "stop_reason": "tool_use",
                "content": [{"type": "text", "text": "voy a mirar"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "stop_reason": "end_turn",
                "content": [{"type": "thinking", "thinking": "mmm"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "   "}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "stop_reason": "max_tokens",
                "content": [{"type": "text", "text": "cortado"}],
            },
        },
    ]


def escribir_transcript(ruta, registros, lineas_rotas=()):
    lineas = [json.dumps(r) for r in registros]
    lineas.extend(lineas_rotas)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


@pytest.fixture
def transcripcion(tmp_path):
    ruta = tmp_path / "sesion.jsonl"
    registros = ruido() + [
        turno(LARGO_A, marca="2026-08-28T09:00:00Z", uuid="a"),
        turno("corto\ndos\ntres", marca="2026-08-28T09:10:00Z", uuid="b"),
        turno(LARGO_B, marca="2026-08-28T10:00:00Z", uuid="c"),
        turno(LARGO_C, marca="2026-08-28T11:00:00Z", uuid="d"),
    ]
    return escribir_transcript(ruta, registros, lineas_rotas=["{no soy json", ""])


def nombres(raiz, proyecto="repo", fecha=None):
    dia = raiz / proyecto / (fecha or HOY)
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- reading the transcript ---


def test_only_closed_turns_with_text_are_collected(transcripcion):
    assert [t["uuid"] for t in tr.turnos(transcripcion)] == ["a", "b", "c", "d"]


def test_broken_lines_do_not_bring_down_the_reading(transcripcion):
    assert len(tr.turnos(transcripcion)) == 4


def test_a_non_string_text_block_does_not_bring_down_the_reading(tmp_path):
    """A `text` that is not a string (number, null, list) gave TypeError in
    _texto_de and brought down the entire reading --and with it the CLI backfill, with
    a raw traceback--. Now that block is skipped as one that contributes no text:
    a turn with only blocks like that is omitted, and a mixed one keeps its string part.
    """
    malo = {
        "type": "assistant", "uuid": "malo", "timestamp": "2026-08-28T09:30:00Z",
        "sessionId": "s", "cwd": "C:\\repo", "gitBranch": "main",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": 123}]},
    }
    mixto = {
        "type": "assistant", "uuid": "mixto", "timestamp": "2026-08-28T09:40:00Z",
        "sessionId": "s", "cwd": "C:\\repo", "gitBranch": "main",
        "message": {"stop_reason": "end_turn", "content": [
            {"type": "text", "text": None},
            {"type": "text", "text": "# Titulo con texto de verdad\nuno\ndos\ntres\ncuatro"},
        ]},
    }
    registros = [
        turno(LARGO_A, marca="2026-08-28T09:00:00Z", uuid="ok1"),
        malo,
        mixto,
        turno(LARGO_B, marca="2026-08-28T10:00:00Z", uuid="ok2"),
    ]
    ruta = escribir_transcript(tmp_path / "sesion.jsonl", registros)

    leidos = tr.turnos(ruta)

    assert [t["uuid"] for t in leidos] == ["ok1", "mixto", "ok2"]
    assert "de verdad" in dict((t["uuid"], t["respuesta_markdown"]) for t in leidos)["mixto"]


def test_the_backfill_does_not_blow_up_with_a_malformed_turn(tmp_path):
    """The backfill read the transcript with tr.turnos, so the same TypeError
    killed it with a traceback and exit 1. Now it reconstructs the good turns and skips
    the bad one without raising."""
    malo = {
        "type": "assistant", "uuid": "malo", "timestamp": "2026-08-28T09:30:00Z",
        "sessionId": "s", "cwd": "C:\\repo", "gitBranch": "main",
        "message": {"stop_reason": "end_turn", "content": [{"type": "text", "text": 123}]},
    }
    registros = [
        turno(LARGO_A, marca="2026-08-28T09:00:00Z", uuid="ok1"),
        malo,
        turno(LARGO_B, marca="2026-08-28T10:00:00Z", uuid="ok2"),
    ]
    ruta = escribir_transcript(tmp_path / "sesion.jsonl", registros)

    resultados = bf.reconstruir(ruta, tmp_path / "archivo", "repo")

    assert sum(1 for r in resultados if r["escrito"]) == 2


def test_a_nonexistent_transcript_gives_an_empty_list(tmp_path):
    assert tr.turnos(tmp_path / "no-existe.jsonl") == []


def test_the_last_turn_is_the_last_one_in_the_file(transcripcion):
    assert tr.ultimo_turno(transcripcion)["uuid"] == "d"


# --- reconstruction ---


def test_one_file_is_written_per_turn(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    resultados = bf.reconstruir(transcripcion, raiz, "repo")

    escritos = [r for r in resultados if r["escrito"]]
    assert len(escritos) == 3
    assert len(nombres(raiz)) == 3
    assert len({r["ruta"] for r in escritos}) == 3


def test_short_turns_are_skipped_by_the_threshold(transcripcion, tmp_path):
    resultados = bf.reconstruir(transcripcion, tmp_path / "archivo", "repo")
    omitidos = [r for r in resultados if not r["escrito"]]
    assert len(omitidos) == 1
    assert "umbral" in omitidos[0]["motivo"]


def test_the_filenames_are_ordinal_and_slug_without_the_date(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")

    assert nombres(raiz) == [SLUG_A, SLUG_B, SLUG_C]
    assert all(HOY not in nombre for nombre in nombres(raiz))


def test_each_report_keeps_its_own_markdown(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")

    dia = raiz / "repo" / HOY
    sobres = [json.loads(p.read_text("utf-8")) for p in sorted(dia.glob("*.json"))]
    assert [s["respuesta_markdown"] for s in sobres] == [LARGO_A, LARGO_B, LARGO_C]


def test_the_metadata_comes_from_the_record_not_from_the_clock(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")

    sobre = json.loads((raiz / "repo" / HOY / SLUG_A).read_text("utf-8"))
    assert sobre["fecha"] == HOY
    assert sobre["session_id"] == "s1"
    assert sobre["cwd"] == "C:\\repo"
    assert sobre["git_branch"] == "main"


def test_each_day_goes_to_its_own_folder_and_the_ordinal_restarts(tmp_path):
    ruta = escribir_transcript(
        tmp_path / "sesion.jsonl",
        [
            turno(LARGO_D, marca="2026-08-27T10:00:00Z", uuid="v"),
            turno(LARGO_A, marca="2026-08-28T09:00:00Z", uuid="a"),
            turno(LARGO_B, marca="2026-08-28T10:00:00Z", uuid="c"),
        ],
    )
    raiz = tmp_path / "archivo"
    bf.reconstruir(ruta, raiz, "repo")

    assert sorted(p.name for p in (raiz / "repo").iterdir()) == [AYER, HOY]
    assert nombres(raiz, fecha=AYER) == ["01-turno-vispera-anterior.json"]
    assert nombres(raiz) == [SLUG_A, SLUG_B]


def test_a_day_folder_with_existing_files_continues_the_ordinal(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    dia = raiz / "repo" / HOY
    dia.mkdir(parents=True)
    (dia / "01-migrado-a-mano.json").write_text("{}", encoding="utf-8")

    bf.reconstruir(transcripcion, raiz, "repo")

    assert nombres(raiz) == [
        "01-migrado-a-mano.json",
        "02-primer-turno-barrido.json",
        "03-segundo-turno-barrido.json",
        "04-tercer-turno-cerrado.json",
    ]


def test_existing_folders_are_reused(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    (raiz / "repo" / HOY).mkdir(parents=True)

    bf.reconstruir(transcripcion, raiz, "repo")

    assert [p.name for p in raiz.iterdir()] == ["repo"]
    assert [p.name for p in (raiz / "repo").iterdir()] == [HOY]


def test_two_different_projects_do_not_get_mixed_together(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "uno")
    bf.reconstruir(transcripcion, raiz, "dos")

    assert sorted(p.name for p in raiz.iterdir()) == ["dos", "uno"]
    assert nombres(raiz, "uno") == nombres(raiz, "dos") == [SLUG_A, SLUG_B, SLUG_C]


def test_a_second_pass_is_idempotent(transcripcion, tmp_path):
    """Re-running the same backfill does not duplicate: each already-archived turn is skipped."""
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")
    segunda = bf.reconstruir(transcripcion, raiz, "repo")

    assert len(nombres(raiz)) == 3, "la segunda pasada no anade ficheros"
    assert all(not r["escrito"] for r in segunda)
    ya = [r for r in segunda if r["motivo"] == "ya archivado"]
    assert len(ya) == 3


def test_fills_a_gap_without_duplicating_what_is_already_there(transcripcion, tmp_path):
    """If a report is missing, it is rewritten; the present ones are not duplicated."""
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")
    (raiz / "repo" / HOY / SLUG_B).unlink()  # the second turn is lost

    bf.reconstruir(transcripcion, raiz, "repo")

    dia = raiz / "repo" / HOY
    markdowns = [json.loads(p.read_text("utf-8"))["respuesta_markdown"] for p in dia.glob("*.json")]
    assert sorted(markdowns) == sorted([LARGO_A, LARGO_B, LARGO_C]), "cada turno aparece una sola vez"
    assert markdowns.count(LARGO_B) == 1, "el hueco se rellena, no se duplica"


def test_the_backfill_records_in_the_log_and_ultimo_finds_it(transcripcion, tmp_path):
    """Without a log line, `ultimo` is blind to what was backfilled. With it, it sees it."""
    raiz = tmp_path / "archivo"
    log = tmp_path / "hook.log"
    bf.reconstruir(transcripcion, raiz, "repo", ruta_log=log)

    escritos = [a for a in reg.leer(log) if a.resultado == reg.ESCRITO]
    assert len(escritos) == 3
    assert all(a.proyecto == "repo" for a in escritos)
    assert [Path(a.detalle).name for a in escritos] == [SLUG_A, SLUG_B, SLUG_C]

    # The point of the log line: `ultimo` finds what the backfill wrote. This
    # closes the loop of the fix -- the backfill records PRECISELY so `ultimo`
    # can see it -- so it is asserted end to end, not just that a line exists.
    ultimo = reg.ultimo_escrito(reg.leer(log), "repo")
    assert ultimo is not None
    assert ultimo.ruta.name == SLUG_C
    assert ultimo.ruta.is_file()


def test_the_simulation_does_not_record_in_the_log(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    log = tmp_path / "hook.log"
    bf.reconstruir(transcripcion, raiz, "repo", ruta_log=log, simular=True)
    assert not log.exists()


def test_the_limit_takes_the_most_recent_turns(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo", limite=1)
    assert nombres(raiz) == ["01-tercer-turno-cerrado.json"]


def test_the_simulation_writes_nothing(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    resultados = bf.reconstruir(transcripcion, raiz, "repo", simular=True)

    assert not raiz.exists()
    assert all(not r["escrito"] for r in resultados)


def test_the_simulation_predicts_the_real_ordinals(transcripcion, tmp_path):
    """A dry-run that numbers everything 01 lies about the result and is useless.

    Three turns of the same day must come out 01, 02, 03 in the simulation, just as
    they would come out in the real pass (SLUG_A/B/C already carry that ordinal).
    """
    raiz = tmp_path / "archivo"
    simulados = [
        r["ruta"].name
        for r in bf.reconstruir(transcripcion, raiz, "repo", simular=True)
        if r["motivo"] == "simulacion"
    ]
    assert simulados == [SLUG_A, SLUG_B, SLUG_C]
    assert not raiz.exists(), "seguir siendo un dry-run: cero escrituras"


def test_the_simulation_continues_the_ordinal_of_what_is_already_there(transcripcion, tmp_path):
    """If the day already has other files, the simulation continues where it should.

    The day is seeded with three FOREIGN reports (other content): the simulation
    of the three transcript turns, which match none of them, continues at
    04, 05, 06. (Re-running the SAME transcript would give 'ya archivado', not a new
    ordinal: that is covered by test_a_second_pass_is_idempotent.)
    """
    raiz = tmp_path / "archivo"
    dia = raiz / "repo" / HOY
    dia.mkdir(parents=True)
    for ordinal in ("01", "02", "03"):
        (dia / f"{ordinal}-ajeno.json").write_text(
            json.dumps({"respuesta_markdown": f"ajeno {ordinal}"}), encoding="utf-8"
        )
    simulados = [
        r["ruta"].name
        for r in bf.reconstruir(transcripcion, raiz, "repo", simular=True)
        if r["motivo"] == "simulacion"
    ]
    assert [n[:2] for n in simulados] == ["04", "05", "06"]


def test_the_backfill_threshold_is_configurable(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo", umbral=2)
    assert len(nombres(raiz)) == 4


# --- locating the transcript ---


def test_the_transcript_is_located_by_session_id(tmp_path):
    raiz = tmp_path / "projects" / "C--repo"
    raiz.mkdir(parents=True)
    esperado = escribir_transcript(raiz / "abc-123.jsonl", [turno(LARGO_A)])

    assert tr.localizar(session_id="abc-123", raiz=tmp_path / "projects") == esperado


def test_the_most_recent_transcript_of_the_project_is_located(tmp_path):
    import os

    base = tmp_path / "projects"
    carpeta = base / "C--repo"
    carpeta.mkdir(parents=True)
    viejo = escribir_transcript(carpeta / "viejo.jsonl", [turno(LARGO_A)])
    nuevo = escribir_transcript(carpeta / "nuevo.jsonl", [turno(LARGO_B)])
    os.utime(viejo, (1, 1))

    assert tr.localizar(cwd="C:\\repo", raiz=base) == nuevo


def test_when_there_is_no_transcript_none_is_returned(tmp_path):
    assert tr.localizar(cwd="C:\\ninguno", raiz=tmp_path) is None


# --- the console command ---


def test_the_command_writes_to_the_indicated_root(transcripcion, tmp_path, capsys):
    raiz = tmp_path / "fuera"
    codigo = cli.main(
        [
            "backfill",
            "--transcript",
            str(transcripcion),
            "--salida",
            str(raiz),
            "--proyecto",
            "repo",
        ]
    )
    assert codigo == 0
    assert nombres(raiz) == [SLUG_A, SLUG_B, SLUG_C]
    assert "3 report(s) written" in capsys.readouterr().out


def test_the_command_respects_the_whitelist(transcripcion, tmp_path, capsys):
    codigo = cli.main(
        [
            "backfill",
            "--transcript",
            str(transcripcion),
            "--config",
            str(tmp_path / "x.json"),
        ]
    )
    assert codigo == 3
    assert "is not in the list" in capsys.readouterr().err
    assert list(tmp_path.glob("**/*.json")) == []


def test_the_command_uses_the_root_and_name_from_the_config(
    transcripcion, escribir_config, tmp_path
):
    proyecto = tmp_path / "repo-renombrado"
    proyecto.mkdir()
    archivo = tmp_path / "archivo"
    ruta_config = escribir_config(
        [{"nombre": "repo", "cwd": str(proyecto), "activo": True}],
        raiz_informes=archivo,
    )

    codigo = cli.main(
        [
            "backfill",
            "--transcript",
            str(transcripcion),
            "--cwd",
            str(proyecto),
            "--config",
            str(ruta_config),
        ]
    )
    assert codigo == 0
    assert nombres(archivo) == [SLUG_A, SLUG_B, SLUG_C]


def test_the_command_warns_when_there_is_no_transcript(tmp_path, capsys):
    codigo = cli.main(["backfill", "--transcript", str(tmp_path / "no.jsonl")])
    assert codigo == 2
    assert "Transcript not found" in capsys.readouterr().err
