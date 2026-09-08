"""El hook. Lo que se prueba aqui es sobre todo lo que NO debe pasar."""

import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import informe as inf
from claude_informes import registro as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"
SLUG = "informe-prueba-diaria"


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def transcript_de(cwd):
    """La ruta que Claude Code le daria a una sesion arrancada en `cwd`."""
    return str(Path("C:/proyectos") / tr.slug_de_cwd(str(cwd)) / "sesion-1.jsonl")


def payload(**cambios):
    """Un turno normal: la sesion arranco donde dice `cwd`."""
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
    """Llama al hook como lo hace Claude Code: payload por stdin."""
    crudo = texto_crudo if texto_crudo is not None else json.dumps(datos)
    return hk.main(entrada=io.StringIO(crudo), ruta_config=ruta_config)


def escritos(informes, proyecto="vigilado", fecha=None):
    dia = Path(informes) / proyecto / (fecha or hoy())
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- camino normal ---


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
    """La ruta ya aporta proyecto y dia; el nombre no los repite."""
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
    """El slug de un subdirectorio es ambiguo, pero el transcript no lo es.

    `e--proyectos-alfa-audit` tanto podria ser `alfa/audit` como
    el proyecto hermano `alfa-audit`, asi que el slug no basta. El primer
    registro del transcript lleva el cwd de arranque y zanja la duda.
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
    """Sin poder leer el arranque, el slug ambiguo no se fuerza."""
    raiz, ruta_config = proyecto_vigilado
    hondo = raiz / "src" / "hondo"
    hondo.mkdir(parents=True)
    fantasma = str(tmp_path / "projects" / tr.slug_de_cwd(str(hondo)) / "s.jsonl")

    ejecutar(payload(cwd=str(hondo), transcript_path=fantasma), ruta_config)

    assert not Path(informes).exists()
    assert reg.leer(log)[0].resultado == reg.OMITIDO_SESION


def test_background_tasks_does_not_prevent_writing(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), background_tasks=[{"id": "bash_1", "status": "running"}])
    assert ejecutar(datos, ruta_config) == 0
    assert len(escritos(informes)) == 1


# --- umbral ---


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


# --- lista blanca: LO IMPORTANTE ---


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
    """El archivo vive fuera de la herramienta: no hay nada que proteger.

    La guardia que habia aqui se comio dos turnos de trabajo real el 28-ago,
    y se habria comido todos los que se hicieran sobre la propia herramienta.
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


# --- payloads corruptos: sale 0 y NO escribe ---


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
    """Silencio en la consola no puede significar silencio en el log."""
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
    """Crear la carpeta caia al except generico y anotaba '- | ERROR | <exc>'
    sin proyecto, ruta ni sesion: el fallo silencioso que el diseño dice
    eliminar. Ahora cualquier fallo de escritura identifica el turno.
    """
    raiz, ruta_config = proyecto_vigilado

    fallos = {"activo": False}
    mkdir_real = Path.mkdir

    def mkdir_roto(self, *args, **kwargs):
        # solo revienta la carpeta del informe, no la del log
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
        raise FileNotFoundError("git no esta instalado")

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


# --- respaldo desde el transcript ---


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
    resultado = hk.procesar(payload(cwd=str(tmp_path)), configuracion)
    assert resultado.resultado == reg.OMITIDO_SESION
    assert resultado.ruta is None


# --- raiz por proyecto ---


def test_each_project_writes_into_its_own_root(escribir_config, tmp_path):
    """Lo sensible puede ir a un sitio y el resto a otro."""
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
    """La raiz por proyecto manda tambien cuando el proyecto es la herramienta."""
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
