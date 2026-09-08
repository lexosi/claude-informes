"""The hook. What is tested here is above all what must NOT happen."""

import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import report as inf
from claude_informes import journal as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"
SLUG = "informe-prueba-diaria"


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def transcript_de(cwd):
    """The path Claude Code would give to a session started in `cwd`."""
    return str(Path("C:/proyectos") / tr.slug_de_cwd(str(cwd)) / "sesion-1.jsonl")


def payload(**cambios):
    """A normal turn: the session started where `cwd` says."""
    base = {
        "session_id": "sesion-1",
        "cwd": "",
        "stop_hook_active": False,
        "last_assistant_message": RESPUESTA,
    }
    base.update(cambios)
    if "transcript_path" not in base:
        base["transcript_path"] = transcript_de(base["cwd"])
    return base


def ejecutar(datos, ruta_config, texto_crudo=None):
    """Calls the hook the way Claude Code does: payload via stdin."""
    crudo = texto_crudo if texto_crudo is not None else json.dumps(datos)
    return hk.main(entrada=io.StringIO(crudo), ruta_config=ruta_config)


def escritos(informes, proyecto="vigilado", fecha=None):
    dia = Path(informes) / proyecto / (fecha or hoy())
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- normal path ---


def test_writes_a_report_when_everything_fits(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert escritos(informes) == [f"01-{SLUG}.json"]


def test_the_path_is_project_then_day_then_file(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    destino = next(Path(informes).rglob("*.json"))
    assert destino.parent.name == hoy()
    assert destino.parent.parent.name == "vigilado"
    assert destino.parent.parent.parent == Path(informes)


def test_the_file_name_carries_neither_date_nor_project_prefix(proyecto_vigilado, informes):
    """The path already provides project and day; the name does not repeat them."""
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    nombre = escritos(informes)[0]
    assert nombre == f"01-{SLUG}.json"
    assert hoy() not in nombre
    assert "vigilado" not in nombre


def test_the_reports_do_not_go_inside_the_project(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    assert not (raiz / "informes").exists()
    assert list(raiz.rglob("*.json")) == []


def test_the_envelope_carries_exactly_the_agreed_schema(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    sobre = json.loads(next(Path(informes).rglob("*.json")).read_text("utf-8"))
    assert list(sobre) == [
        "version_esquema",
        "fecha",
        "hora",
        "session_id",
        "cwd",
        "git_branch",
        "git_head",
        "respuesta_markdown",
        "secciones",
        "bloques_codigo",
        "casillas",
    ]
    assert sobre["version_esquema"] == 1
    assert sobre["session_id"] == "sesion-1"
    assert sobre["cwd"] == str(raiz)


def test_one_json_per_turn_they_never_pile_up(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=RESPUESTA + "\nmas"), ruta_config)

    assert escritos(informes) == [f"01-{SLUG}.json", f"02-{SLUG}.json"]


def test_two_responses_with_the_same_slug_on_the_same_day_do_not_overwrite_each_other(
    proyecto_vigilado, informes
):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz), last_assistant_message=RESPUESTA + "\nA"), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=RESPUESTA + "\nB"), ruta_config)

    dia = Path(informes) / "vigilado" / hoy()
    contenidos = [
        json.loads(p.read_text("utf-8"))["respuesta_markdown"]
        for p in sorted(dia.glob("*.json"))
    ]
    assert escritos(informes) == [f"01-{SLUG}.json", f"02-{SLUG}.json"]
    assert contenidos == [RESPUESTA + "\nA", RESPUESTA + "\nB"]


def test_two_different_projects_go_to_different_folders(
    escribir_config, informes, tmp_path
):
    uno = tmp_path / "uno"
    dos = tmp_path / "dos"
    uno.mkdir()
    dos.mkdir()
    ruta_config = escribir_config(
        [
            {"nombre": "proyecto-uno", "cwd": str(uno)},
            {"nombre": "proyecto-dos", "cwd": str(dos)},
        ],
        raiz_informes=informes,
    )

    ejecutar(payload(cwd=str(uno)), ruta_config)
    ejecutar(payload(cwd=str(dos)), ruta_config)

    assert escritos(informes, "proyecto-uno") == [f"01-{SLUG}.json"]
    assert escritos(informes, "proyecto-dos") == [f"01-{SLUG}.json"]


def test_the_folder_name_comes_from_the_config_not_from_the_directory(
    escribir_config, informes, tmp_path
):
    raiz = tmp_path / "alfa-renombrado-ayer"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(raiz)}], raiz_informes=informes
    )
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    assert (Path(informes) / "alfa").is_dir()
    assert not (Path(informes) / "alfa-renombrado-ayer").exists()


def test_both_directory_levels_are_created(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    assert not Path(informes).exists()
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert (Path(informes) / "vigilado" / hoy()).is_dir()


def test_a_session_opened_in_a_subdirectory_writes_into_the_same_folder(
    proyecto_vigilado, informes, tmp_path
):
    """A subdirectory's slug is ambiguous, but the transcript is not.

    `e--proyectos-alfa-audit` could be either `alfa/audit` or
    the sibling project `alfa-audit`, so the slug is not enough. The first
    record of the transcript carries the startup cwd and settles the doubt.
    """
    raiz, ruta_config = proyecto_vigilado
    hondo = raiz / "src" / "hondo"
    hondo.mkdir(parents=True)

    transcripcion = tmp_path / "projects" / tr.slug_de_cwd(str(hondo)) / "s.jsonl"
    transcripcion.parent.mkdir(parents=True)
    transcripcion.write_text(
        json.dumps({"type": "user", "cwd": str(hondo)}) + "\n", encoding="utf-8"
    )

    ejecutar(payload(cwd=str(hondo), transcript_path=str(transcripcion)), ruta_config)

    assert escritos(informes) == [f"01-{SLUG}.json"]


def test_a_subdirectory_session_without_a_readable_transcript_is_not_archived(
    proyecto_vigilado, informes, tmp_path, log
):
    """Without being able to read the startup, the ambiguous slug is not forced.

    And the unreadable transcript is logged as such (`transcript-ilegible`), not
    as 'project not registered': mislabeling it would mislead in the one place
    meant to catch it.
    """
    raiz, ruta_config = proyecto_vigilado
    hondo = raiz / "src" / "hondo"
    hondo.mkdir(parents=True)
    fantasma = str(tmp_path / "projects" / tr.slug_de_cwd(str(hondo)) / "s.jsonl")

    ejecutar(payload(cwd=str(hondo), transcript_path=fantasma), ruta_config)

    assert not Path(informes).exists()
    assert reg.leer(log)[0].resultado == reg.TRANSCRIPT_ILEGIBLE


def test_background_tasks_does_not_prevent_writing(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), background_tasks=[{"id": "bash_1", "status": "running"}])
    assert ejecutar(datos, ruta_config) == 0
    assert len(escritos(informes)) == 1


# --- threshold ---


def test_below_the_threshold_it_writes_nothing(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    corta = "1\n2\n3\n4\n5"
    assert ejecutar(payload(cwd=str(raiz), last_assistant_message=corta), ruta_config) == 0
    assert not Path(informes).exists()


def test_just_above_the_threshold_it_does_write(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    justa = "1\n2\n3\n4\n5\n6"
    ejecutar(payload(cwd=str(raiz), last_assistant_message=justa), ruta_config)
    assert len(escritos(informes)) == 1


def test_the_threshold_is_the_one_from_the_project_config(escribir_config, informes, tmp_path):
    raiz = tmp_path / "exigente"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "exigente", "cwd": str(raiz), "umbral_lineas": 20}],
        raiz_informes=informes,
    )
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert not Path(informes).exists()


# --- whitelist: THE IMPORTANT PART ---


def test_a_cwd_outside_the_whitelist_writes_nothing(proyecto_vigilado, informes, tmp_path):
    _, ruta_config = proyecto_vigilado
    ajeno = tmp_path / "beta"
    ajeno.mkdir()

    assert ejecutar(payload(cwd=str(ajeno)), ruta_config) == 0
    assert list(ajeno.iterdir()) == []
    assert not Path(informes).exists()


def test_the_tools_own_cwd_now_does_write(
    escribir_config, informes, tmp_path
):
    """The file lives outside the tool: there is nothing to protect.

    The guard that used to be here ate two turns of real work on 28-Aug,
    and would have eaten every one done on the tool itself.
    """
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia), "activo": True}],
        raiz_informes=informes,
    )

    assert ejecutar(payload(cwd=str(propia)), ruta_config) == 0

    assert escritos(informes, "claude-informes") == [f"01-{SLUG}.json"]


def test_the_tool_under_a_watched_project_is_archived_together_with_it(
    escribir_config, informes
):
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "todo", "cwd": str(propia.parent), "activo": True}],
        raiz_informes=informes,
    )
    datos = payload(cwd=str(propia / "tests"))
    datos["transcript_path"] = transcript_de(propia.parent)

    assert ejecutar(datos, ruta_config) == 0

    assert escritos(informes, "todo") == [f"01-{SLUG}.json"]


def test_a_deactivated_project_writes_nothing(escribir_config, informes, tmp_path):
    raiz = tmp_path / "pausado"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"cwd": str(raiz), "activo": False}], raiz_informes=informes
    )

    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not Path(informes).exists()


def test_without_a_config_it_writes_nowhere(informes, tmp_path):
    raiz = tmp_path / "cualquiera"
    raiz.mkdir()

    assert ejecutar(payload(cwd=str(raiz)), tmp_path / "no-hay-config.json") == 0
    assert list(raiz.iterdir()) == []
    assert not Path(informes).exists()


def test_stop_hook_active_exits_without_writing(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    assert ejecutar(payload(cwd=str(raiz), stop_hook_active=True), ruta_config) == 0
    assert not Path(informes).exists()


# --- corrupt payloads: exits 0 and does NOT write ---


BASURA = [
    pytest.param("", id="vacio"),
    pytest.param("no soy json", id="texto-suelto"),
    pytest.param("{", id="json-truncado"),
    pytest.param("[1, 2, 3]", id="lista-en-vez-de-objeto"),
    pytest.param('"solo una cadena"', id="cadena"),
    pytest.param("null", id="null"),
    pytest.param("{}", id="objeto-vacio"),
    pytest.param('{"cwd": 42}', id="cwd-numerico"),
    pytest.param('{"cwd": null, "last_assistant_message": null}', id="todo-null"),
    pytest.param('{"last_assistant_message": "hola"}', id="sin-cwd"),
]


@pytest.mark.parametrize("crudo", BASURA)
def test_a_corrupt_payload_exits_0_and_writes_nothing(
    crudo, proyecto_vigilado, informes, tmp_path, log
):
    _, ruta_config = proyecto_vigilado
    antes = sorted(p.name for p in tmp_path.rglob("*") if p != log)

    assert ejecutar(None, ruta_config, texto_crudo=crudo) == 0

    assert sorted(p.name for p in tmp_path.rglob("*") if p != log) == antes
    assert not Path(informes).exists()


@pytest.mark.parametrize("crudo", BASURA)
def test_a_corrupt_payload_leaves_a_trace_in_the_log(crudo, proyecto_vigilado, log):
    """Silence in the console cannot mean silence in the log."""
    _, ruta_config = proyecto_vigilado
    ejecutar(None, ruta_config, texto_crudo=crudo)

    anotaciones = reg.leer(log)
    assert len(anotaciones) == 1
    assert anotaciones[0].resultado in {reg.ERROR, reg.OMITIDO_CWD}


def test_a_payload_with_a_corrupt_cwd_but_on_the_whitelist_does_not_blow_up(
    proyecto_vigilado, informes
):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), last_assistant_message=12345)
    assert ejecutar(datos, ruta_config) == 0
    assert not Path(informes).exists()


def test_stdin_that_blows_up_on_read_exits_0(proyecto_vigilado, informes):
    _, ruta_config = proyecto_vigilado

    class StdinRoto:
        def read(self):
            raise OSError("el pipe se ha ido")

    assert hk.main(entrada=StdinRoto(), ruta_config=ruta_config) == 0
    assert not Path(informes).exists()


def test_if_it_cannot_write_it_exits_0(proyecto_vigilado, informes, monkeypatch):
    raiz, ruta_config = proyecto_vigilado

    def mkdir_roto(*args, **kwargs):
        raise PermissionError("disco de solo lectura")

    monkeypatch.setattr(Path, "mkdir", mkdir_roto)
    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not Path(informes).exists()


def test_a_write_failure_identifies_the_turn_in_the_log(
    proyecto_vigilado, informes, log, monkeypatch
):
    """Creating the folder fell into the generic except and logged '- | ERROR | <exc>'
    with no project, path or session: the silent failure that the design says
    to eliminate. Now any write failure identifies the turn.
    """
    raiz, ruta_config = proyecto_vigilado

    fallos = {"activo": False}
    mkdir_real = Path.mkdir

    def mkdir_roto(self, *args, **kwargs):
        # only blows up the report folder, not the log's
        if "vigilado" in str(self):
            raise PermissionError("disco de solo lectura")
        return mkdir_real(self, *args, **kwargs)

    monkeypatch.setattr(Path, "mkdir", mkdir_roto)
    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0

    linea = reg.leer(log)[-1]
    assert linea.resultado == reg.ERROR
    assert linea.proyecto == "vigilado"
    assert "sesion-1" in linea.detalle
    assert "ruta=" in linea.detalle


def test_if_git_blows_up_the_report_is_written_anyway(
    proyecto_vigilado, informes, monkeypatch
):
    raiz, ruta_config = proyecto_vigilado

    def git_roto(*args, **kwargs):
        raise FileNotFoundError("git is not installed")

    monkeypatch.setattr(inf.subprocess, "run", git_roto)
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    sobre = json.loads(next(Path(informes).rglob("*.json")).read_text("utf-8"))
    assert sobre["git_branch"] is None and sobre["git_head"] is None


def test_the_hook_writes_to_neither_stdout_nor_stderr(proyecto_vigilado, capsys):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(None, ruta_config, texto_crudo="{basura")
    ejecutar(payload(cwd="C:\\otro\\sitio"), ruta_config)

    capturado = capsys.readouterr()
    assert capturado.out == ""
    assert capturado.err == ""


# --- fallback from the transcript ---


def test_without_last_assistant_message_it_reads_from_the_transcript(
    proyecto_vigilado, informes, tmp_path
):
    raiz, ruta_config = proyecto_vigilado
    transcripcion = tmp_path / "sesion.jsonl"
    registro = {
        "type": "assistant",
        "timestamp": "2026-08-28T11:31:37.388Z",
        "sessionId": "sesion-1",
        "cwd": str(raiz),
        "gitBranch": "main",
        "message": {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": RESPUESTA}],
        },
    }
    transcripcion.write_text(json.dumps(registro) + "\n", encoding="utf-8")

    datos = payload(cwd=str(raiz), transcript_path=str(transcripcion))
    del datos["last_assistant_message"]
    ejecutar(datos, ruta_config)

    sobre = json.loads(next(Path(informes).rglob("*.json")).read_text("utf-8"))
    assert sobre["respuesta_markdown"] == RESPUESTA


def test_a_nonexistent_transcript_does_not_blow_up(proyecto_vigilado, informes, tmp_path):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), transcript_path=str(tmp_path / "no-existe.jsonl"))
    del datos["last_assistant_message"]

    assert ejecutar(datos, ruta_config) == 0
    assert not Path(informes).exists()


def test_procesar_reports_that_the_session_is_not_registered(tmp_path):
    configuracion = cfg.cargar(tmp_path / "no-existe.json")
    # A REAL transcript (as in production) whose startup cwd is not registered:
    # that is 'not registered', distinct from an unreadable transcript.
    transcripcion = tmp_path / "projects" / tr.slug_de_cwd(str(tmp_path)) / "s.jsonl"
    transcripcion.parent.mkdir(parents=True)
    transcripcion.write_text(
        json.dumps({"type": "user", "cwd": str(tmp_path)}) + "\n", encoding="utf-8"
    )
    resultado = hk.procesar(
        payload(cwd=str(tmp_path), transcript_path=str(transcripcion)), configuracion
    )
    assert resultado.resultado == reg.OMITIDO_SESION
    assert resultado.ruta is None


# --- per-project root ---


def test_each_project_writes_into_its_own_root(escribir_config, tmp_path):
    """The sensitive can go to one place and the rest to another."""
    comun = tmp_path / "comun"
    cofre = tmp_path / "cofre"
    publico = tmp_path / "publico"
    sensible = tmp_path / "sensible"
    publico.mkdir()
    sensible.mkdir()
    ruta_config = escribir_config(
        [
            {"nombre": "publico", "cwd": str(publico)},
            {"nombre": "sensible", "cwd": str(sensible), "raiz_informes": cofre},
        ],
        raiz_informes=comun,
    )

    ejecutar(payload(cwd=str(publico)), ruta_config)
    ejecutar(payload(cwd=str(sensible)), ruta_config)

    assert escritos(comun, "publico") == [f"01-{SLUG}.json"]
    assert escritos(cofre, "sensible") == [f"01-{SLUG}.json"]
    assert not (comun / "sensible").exists()
    assert not (cofre / "publico").exists()


def test_without_its_own_root_it_writes_into_the_global_one(escribir_config, tmp_path):
    comun = tmp_path / "comun"
    raiz = tmp_path / "hereda"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "hereda", "cwd": str(raiz)}], raiz_informes=comun
    )

    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert escritos(comun, "hereda") == [f"01-{SLUG}.json"]


def test_the_tool_with_its_own_root_archives_into_its_own_vault(escribir_config, tmp_path):
    """The per-project root rules also when the project is the tool."""
    propia = cfg.raiz_de_la_herramienta()
    cofre = tmp_path / "cofre"
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia), "raiz_informes": cofre}],
        raiz_informes=tmp_path / "comun",
    )

    assert ejecutar(payload(cwd=str(propia)), ruta_config) == 0

    assert escritos(cofre, "claude-informes") == [f"01-{SLUG}.json"]
    assert not (tmp_path / "comun").exists()


def test_a_root_that_does_not_exist_is_created_in_full(escribir_config, tmp_path):
    lejos = tmp_path / "sin" / "crear" / "todavia"
    raiz = tmp_path / "repo"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "repo", "cwd": str(raiz), "raiz_informes": lejos}]
    )

    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert escritos(lejos, "repo") == [f"01-{SLUG}.json"]


def test_if_the_root_cannot_be_created_it_exits_0(escribir_config, tmp_path, monkeypatch):
    lejos = tmp_path / "imposible"
    raiz = tmp_path / "repo"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "repo", "cwd": str(raiz), "raiz_informes": lejos}]
    )

    def mkdir_roto(*args, **kwargs):
        raise OSError("unidad no disponible")

    monkeypatch.setattr(Path, "mkdir", mkdir_roto)
    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not lejos.exists()
