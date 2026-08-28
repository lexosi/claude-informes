"""El hook. Lo que se prueba aqui es sobre todo lo que NO debe pasar."""

import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import informe as inf

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"
SLUG = "informe-prueba-diaria"


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def payload(**cambios):
    base = {
        "session_id": "sesion-1",
        "transcript_path": "",
        "cwd": "",
        "stop_hook_active": False,
        "last_assistant_message": RESPUESTA,
    }
    base.update(cambios)
    return base


def ejecutar(datos, ruta_config, texto_crudo=None):
    """Llama al hook como lo hace Claude Code: payload por stdin."""
    crudo = texto_crudo if texto_crudo is not None else json.dumps(datos)
    return hk.main(entrada=io.StringIO(crudo), ruta_config=ruta_config)


def escritos(informes, proyecto="vigilado", fecha=None):
    dia = Path(informes) / proyecto / (fecha or hoy())
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- camino normal ---


def test_escribe_un_informe_cuando_todo_encaja(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert escritos(informes) == [f"01-{SLUG}.json"]


def test_la_ruta_es_proyecto_dia_fichero(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    destino = next(Path(informes).rglob("*.json"))
    assert destino.parent.name == hoy()
    assert destino.parent.parent.name == "vigilado"
    assert destino.parent.parent.parent == Path(informes)


def test_el_nombre_no_lleva_fecha_ni_prefijo_de_proyecto(proyecto_vigilado, informes):
    """La ruta ya aporta proyecto y dia; el nombre no los repite."""
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    nombre = escritos(informes)[0]
    assert nombre == f"01-{SLUG}.json"
    assert hoy() not in nombre
    assert "vigilado" not in nombre


def test_los_informes_no_van_dentro_del_proyecto(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    assert not (raiz / "informes").exists()
    assert list(raiz.rglob("*.json")) == []


def test_el_sobre_lleva_exactamente_el_esquema_acordado(proyecto_vigilado, informes):
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


def test_un_json_por_turno_nunca_se_acumulan(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=RESPUESTA + "\nmas"), ruta_config)

    assert escritos(informes) == [f"01-{SLUG}.json", f"02-{SLUG}.json"]


def test_dos_respuestas_con_el_mismo_slug_el_mismo_dia_no_se_pisan(
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


def test_dos_proyectos_distintos_van_a_carpetas_distintas(
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


def test_el_nombre_de_la_carpeta_sale_de_la_config_no_del_directorio(
    escribir_config, informes, tmp_path
):
    raiz = tmp_path / "loopward-renombrado-ayer"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(raiz)}], raiz_informes=informes
    )
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    assert (Path(informes) / "loopward").is_dir()
    assert not (Path(informes) / "loopward-renombrado-ayer").exists()


def test_se_crean_los_dos_niveles_de_directorio(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    assert not Path(informes).exists()
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert (Path(informes) / "vigilado" / hoy()).is_dir()


def test_un_subdirectorio_del_proyecto_escribe_en_la_misma_carpeta(
    proyecto_vigilado, informes
):
    raiz, ruta_config = proyecto_vigilado
    hondo = raiz / "src" / "hondo"
    hondo.mkdir(parents=True)
    ejecutar(payload(cwd=str(hondo)), ruta_config)

    assert escritos(informes) == [f"01-{SLUG}.json"]


def test_background_tasks_no_impide_escribir(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), background_tasks=[{"id": "bash_1", "status": "running"}])
    assert ejecutar(datos, ruta_config) == 0
    assert len(escritos(informes)) == 1


# --- umbral ---


def test_por_debajo_del_umbral_no_escribe_nada(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    corta = "1\n2\n3\n4\n5"
    assert ejecutar(payload(cwd=str(raiz), last_assistant_message=corta), ruta_config) == 0
    assert not Path(informes).exists()


def test_justo_por_encima_del_umbral_si_escribe(proyecto_vigilado, informes):
    raiz, ruta_config = proyecto_vigilado
    justa = "1\n2\n3\n4\n5\n6"
    ejecutar(payload(cwd=str(raiz), last_assistant_message=justa), ruta_config)
    assert len(escritos(informes)) == 1


def test_el_umbral_es_el_de_la_config_del_proyecto(escribir_config, informes, tmp_path):
    raiz = tmp_path / "exigente"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "exigente", "cwd": str(raiz), "umbral_lineas": 20}],
        raiz_informes=informes,
    )
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert not Path(informes).exists()


# --- lista blanca: LO IMPORTANTE ---


def test_un_cwd_fuera_de_la_lista_no_escribe_nada(proyecto_vigilado, informes, tmp_path):
    _, ruta_config = proyecto_vigilado
    ajeno = tmp_path / "project-b"
    ajeno.mkdir()

    assert ejecutar(payload(cwd=str(ajeno)), ruta_config) == 0
    assert list(ajeno.iterdir()) == []
    assert not Path(informes).exists()


def test_el_cwd_de_la_propia_herramienta_no_escribe_nunca(
    escribir_config, informes, tmp_path
):
    """La carpeta de destino vive dentro de claude-informes: guardia obligatoria."""
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia), "activo": True}],
        raiz_informes=informes,
    )

    assert ejecutar(payload(cwd=str(propia)), ruta_config) == 0
    assert ejecutar(payload(cwd=str(propia / "claude_informes")), ruta_config) == 0
    assert ejecutar(payload(cwd=str(propia / "informes" / "loopward")), ruta_config) == 0
    assert not Path(informes).exists()


def test_la_guardia_gana_aunque_la_herramienta_cuelgue_de_un_proyecto_vigilado(
    escribir_config, informes
):
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "todo", "cwd": str(propia.parent), "activo": True}],
        raiz_informes=informes,
    )
    assert ejecutar(payload(cwd=str(propia / "tests")), ruta_config) == 0
    assert not Path(informes).exists()


def test_un_proyecto_desactivado_no_escribe_nada(escribir_config, informes, tmp_path):
    raiz = tmp_path / "pausado"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"cwd": str(raiz), "activo": False}], raiz_informes=informes
    )

    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not Path(informes).exists()


def test_sin_config_no_escribe_en_ningun_sitio(informes, tmp_path):
    raiz = tmp_path / "cualquiera"
    raiz.mkdir()

    assert ejecutar(payload(cwd=str(raiz)), tmp_path / "no-hay-config.json") == 0
    assert list(raiz.iterdir()) == []
    assert not Path(informes).exists()


def test_stop_hook_active_sale_sin_escribir(proyecto_vigilado, informes):
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
def test_un_payload_corrupto_sale_0_y_no_escribe_nada(
    crudo, proyecto_vigilado, informes, tmp_path
):
    _, ruta_config = proyecto_vigilado
    antes = sorted(p.name for p in tmp_path.rglob("*"))

    assert ejecutar(None, ruta_config, texto_crudo=crudo) == 0

    assert sorted(p.name for p in tmp_path.rglob("*")) == antes
    assert not Path(informes).exists()


def test_un_payload_con_cwd_corrupto_pero_de_la_lista_no_revienta(
    proyecto_vigilado, informes
):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), last_assistant_message=12345)
    assert ejecutar(datos, ruta_config) == 0
    assert not Path(informes).exists()


def test_stdin_que_revienta_al_leer_sale_0(proyecto_vigilado, informes):
    _, ruta_config = proyecto_vigilado

    class StdinRoto:
        def read(self):
            raise OSError("el pipe se ha ido")

    assert hk.main(entrada=StdinRoto(), ruta_config=ruta_config) == 0
    assert not Path(informes).exists()


def test_si_no_se_puede_escribir_sale_0(proyecto_vigilado, informes, monkeypatch):
    raiz, ruta_config = proyecto_vigilado

    def mkdir_roto(*args, **kwargs):
        raise PermissionError("disco de solo lectura")

    monkeypatch.setattr(Path, "mkdir", mkdir_roto)
    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not Path(informes).exists()


def test_si_git_revienta_el_informe_se_escribe_igual(
    proyecto_vigilado, informes, monkeypatch
):
    raiz, ruta_config = proyecto_vigilado

    def git_roto(*args, **kwargs):
        raise FileNotFoundError("git no esta instalado")

    monkeypatch.setattr(inf.subprocess, "run", git_roto)
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    sobre = json.loads(next(Path(informes).rglob("*.json")).read_text("utf-8"))
    assert sobre["git_branch"] is None and sobre["git_head"] is None


def test_el_hook_no_escribe_en_stdout_ni_en_stderr(proyecto_vigilado, capsys):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(None, ruta_config, texto_crudo="{basura")
    ejecutar(payload(cwd="C:\\otro\\sitio"), ruta_config)

    capturado = capsys.readouterr()
    assert capturado.out == ""
    assert capturado.err == ""


# --- respaldo desde el transcript ---


def test_sin_last_assistant_message_se_lee_del_transcript(
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


def test_un_transcript_inexistente_no_revienta(proyecto_vigilado, informes, tmp_path):
    raiz, ruta_config = proyecto_vigilado
    datos = payload(cwd=str(raiz), transcript_path=str(tmp_path / "no-existe.jsonl"))
    del datos["last_assistant_message"]

    assert ejecutar(datos, ruta_config) == 0
    assert not Path(informes).exists()


def test_procesar_devuelve_none_si_el_cwd_no_esta_en_la_lista(tmp_path):
    configuracion = cfg.cargar(tmp_path / "no-existe.json")
    assert hk.procesar(payload(cwd=str(tmp_path)), configuracion) is None


# --- raiz por proyecto ---


def test_cada_proyecto_escribe_en_su_propia_raiz(escribir_config, tmp_path):
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


def test_sin_raiz_propia_se_escribe_en_la_global(escribir_config, tmp_path):
    comun = tmp_path / "comun"
    raiz = tmp_path / "hereda"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "hereda", "cwd": str(raiz)}], raiz_informes=comun
    )

    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert escritos(comun, "hereda") == [f"01-{SLUG}.json"]


def test_la_guardia_sigue_valiendo_con_una_raiz_propia(escribir_config, tmp_path):
    """Que el archivo viva fuera no reabre la puerta a auto-escribirse."""
    propia = cfg.raiz_de_la_herramienta()
    cofre = tmp_path / "cofre"
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia), "raiz_informes": cofre}],
        raiz_informes=tmp_path / "comun",
    )

    assert ejecutar(payload(cwd=str(propia)), ruta_config) == 0
    assert ejecutar(payload(cwd=str(propia / "claude_informes")), ruta_config) == 0
    assert not cofre.exists()
    assert not (tmp_path / "comun").exists()


def test_una_raiz_que_no_existe_se_crea_entera(escribir_config, tmp_path):
    lejos = tmp_path / "sin" / "crear" / "todavia"
    raiz = tmp_path / "repo"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "repo", "cwd": str(raiz), "raiz_informes": lejos}]
    )

    ejecutar(payload(cwd=str(raiz)), ruta_config)
    assert escritos(lejos, "repo") == [f"01-{SLUG}.json"]


def test_si_la_raiz_no_se_puede_crear_sale_0(escribir_config, tmp_path, monkeypatch):
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
