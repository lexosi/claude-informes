"""El guardian PreToolUse. Aqui lo grave es denegar de mas, no de menos."""

import io
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from claude_informes import config as cfg
from claude_informes import guardian as gd
from claude_informes import registro as reg

RAIZ = Path(__file__).resolve().parent.parent


def payload(ruta, herramienta="Write", cwd="C:\\proyectos\\alfa", **extras):
    datos = {
        "session_id": "s",
        "cwd": cwd,
        "hook_event_name": "PreToolUse",
        "tool_name": herramienta,
        "tool_input": {"file_path": str(ruta), "file_text": "{}"},
    }
    datos.update(extras)
    return datos


def ejecutar(datos, ruta_config, texto_crudo=None):
    """Devuelve (codigo, lo que el hook escribe en stdout)."""
    crudo = texto_crudo if texto_crudo is not None else json.dumps(datos)
    salida = io.StringIO()
    codigo = gd.main(
        entrada=io.StringIO(crudo), salida=salida, ruta_config=ruta_config
    )
    return codigo, salida.getvalue()


def deniega(salida):
    if not salida:
        return False
    return json.loads(salida)["hookSpecificOutput"]["permissionDecision"] == "deny"


def razon(salida):
    return json.loads(salida)["hookSpecificOutput"]["permissionDecisionReason"]


@pytest.fixture
def archivo(tmp_path, escribir_config, log):
    """Config con raiz global, una raiz por proyecto, y el log."""
    comun = tmp_path / "informes-claude"
    cofre = tmp_path / "informes-claude-privado"
    ruta_config = escribir_config(
        [
            {"nombre": "alfa", "cwd": "C:\\proyectos\\alfa"},
            {
                "nombre": "beta",
                "cwd": "C:\\proyectos\\beta",
                "raiz_informes": cofre,
            },
        ],
        raiz_informes=comun,
    )
    return comun, cofre, ruta_config


# --- lo que hay que denegar ---


def test_a_write_under_the_global_root_is_denied(archivo):
    comun, _, ruta_config = archivo
    codigo, salida = ejecutar(payload(comun / "alfa" / "2026-08-28" / "09-x.json"), ruta_config)

    assert codigo == 0
    assert deniega(salida)


def test_a_write_under_a_per_project_root_is_denied(archivo):
    """La raiz del proyecto no es la global y tambien esta protegida."""
    _, cofre, ruta_config = archivo
    codigo, salida = ejecutar(payload(cofre / "beta" / "2026-08-28" / "01-x.json"), ruta_config)

    assert codigo == 0
    assert deniega(salida)
    assert "beta" in razon(salida)


def test_a_write_to_the_log_file_is_denied(archivo, log):
    _, _, ruta_config = archivo
    codigo, salida = ejecutar(payload(log), ruta_config)

    assert deniega(salida)
    assert "hook's log" in razon(salida)


def test_a_relative_path_with_dot_dot_segments_is_resolved_and_denied(archivo, tmp_path):
    """`..\\..\\informes-claude\\x.json` cae dentro igual."""
    comun, _, ruta_config = archivo
    desde = tmp_path / "repos" / "alfa"
    desde.mkdir(parents=True)
    relativa = Path("..") / ".." / comun.name / "alfa" / "x.json"

    codigo, salida = ejecutar(payload(relativa, cwd=str(desde)), ruta_config)

    assert deniega(salida)
    assert str(comun) in razon(salida).replace("/", "\\") or comun.name in razon(salida)


def test_the_archive_folder_itself_is_denied(archivo):
    comun, _, ruta_config = archivo
    assert deniega(ejecutar(payload(comun), ruta_config)[1])


@pytest.mark.parametrize("herramienta", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_all_the_write_tools_are_covered(herramienta, archivo):
    comun, _, ruta_config = archivo
    campo = "notebook_path" if herramienta == "NotebookEdit" else "file_path"
    datos = payload(comun / "x.json", herramienta=herramienta)
    datos["tool_input"] = {campo: str(comun / "x.json")}

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_a_multi_edit_is_checked_entry_by_entry(archivo):
    comun, _, ruta_config = archivo
    datos = payload(comun / "x.json", herramienta="MultiEdit")
    datos["tool_input"] = {
        "edits": [
            {"file_path": "C:\\proyectos\\alfa\\README.md"},
            {"file_path": str(comun / "alfa" / "x.json")},
        ]
    }
    assert deniega(ejecutar(datos, ruta_config)[1])


def test_the_message_says_why_and_what_to_do_instead(archivo):
    comun, _, ruta_config = archivo
    motivo = razon(ejecutar(payload(comun / "alfa" / "x.json"), ruta_config)[1])

    assert "report archive" in motivo
    assert "Stop hook" in motivo
    assert "ultimo" in motivo, "tiene que decir que hacer en su lugar"
    assert "--proyecto alfa" in motivo


# --- lo que NO se puede denegar ---


def test_a_normal_write_inside_a_repo_is_allowed(archivo):
    _, _, ruta_config = archivo
    for ruta in [
        "C:\\proyectos\\alfa\\README.md",
        "C:\\proyectos\\alfa\\alfa\\cli.py",
        "C:\\proyectos\\beta\\cv.md",
        "C:\\proyectos\\claude-informes\\claude_informes\\hook.py",
    ]:
        codigo, salida = ejecutar(payload(ruta), ruta_config)
        assert codigo == 0 and salida == "", ruta


def test_a_sibling_sharing_a_common_prefix_is_allowed(archivo, tmp_path):
    """`informes-claude-otra-cosa` no esta dentro de `informes-claude`."""
    comun, _, ruta_config = archivo
    vecino = comun.parent / (comun.name + "-otra-cosa") / "x.json"

    assert ejecutar(payload(vecino), ruta_config)[1] == ""


def test_a_tool_that_does_not_write_files_is_allowed(archivo):
    comun, _, ruta_config = archivo
    for herramienta in ["Read", "Bash", "Glob", "Grep"]:
        datos = payload(comun / "x.json", herramienta=herramienta)
        assert ejecutar(datos, ruta_config)[1] == "", herramienta


def test_bash_is_not_intercepted_even_when_it_mentions_the_archive(archivo):
    """Adivinar rutas dentro de una linea de shell da falsos positivos."""
    comun, _, ruta_config = archivo
    datos = payload("x", herramienta="Bash")
    datos["tool_input"] = {"command": f"echo hola > {comun}\\x.json"}

    assert ejecutar(datos, ruta_config)[1] == ""


# --- falla abierto: lo contrario del hook Stop ---


def test_a_missing_config_allows_and_records_it(tmp_path, log):
    codigo, salida = ejecutar(
        payload(tmp_path / "informes-claude" / "x.json"), tmp_path / "no-existe.json"
    )

    assert codigo == 0 and salida == "", "sin config no se puede afirmar nada: permite"
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.PERMITIDO_POR_ERROR
    assert "FileNotFoundError" in anotacion.detalle


def test_a_corrupt_config_allows_and_records_it(tmp_path, log):
    rota = tmp_path / "rota.json"
    rota.write_text("{esto no es json", encoding="utf-8")

    codigo, salida = ejecutar(payload(tmp_path / "informes-claude" / "x.json"), rota)

    assert codigo == 0 and salida == ""
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.PERMITIDO_POR_ERROR


def test_a_corrupt_payload_allows_without_noise(archivo, capsys):
    _, _, ruta_config = archivo
    for crudo in ["", "no soy json", "{", "[1,2]", "null", '"cadena"']:
        codigo, salida = ejecutar(None, ruta_config, texto_crudo=crudo)
        assert codigo == 0 and salida == "", crudo
    assert capsys.readouterr().out == ""


def test_a_payload_missing_the_expected_fields_is_allowed(archivo):
    _, _, ruta_config = archivo
    for datos in [{}, {"tool_name": "Write"}, {"tool_name": "Write", "tool_input": None}]:
        assert ejecutar(datos, ruta_config)[1] == ""


def test_if_the_review_blows_up_it_allows(archivo, monkeypatch, log):
    _, _, ruta_config = archivo

    def revisar_roto(*args, **kwargs):
        raise RuntimeError("algo se ha roto por dentro")

    monkeypatch.setattr(gd, "revisar", revisar_roto)
    codigo, salida = ejecutar(payload("C:\\lo\\que\\sea"), ruta_config)

    assert codigo == 0 and salida == ""
    assert reg.leer(log)[0].resultado == reg.PERMITIDO_POR_ERROR


def test_if_the_log_fails_the_denial_still_comes_out(archivo, monkeypatch):
    comun, _, ruta_config = archivo

    def anotar_roto(*args, **kwargs):
        raise PermissionError("el log es de solo lectura")

    monkeypatch.setattr(reg, "anotar", anotar_roto)
    codigo, salida = ejecutar(payload(comun / "alfa" / "x.json"), ruta_config)

    assert codigo == 0
    assert deniega(salida), "el log es secundario; la decision no depende de el"


def test_it_never_returns_a_nonzero_exit_code(archivo, tmp_path):
    comun, _, ruta_config = archivo
    casos = [
        (payload(comun / "x.json"), ruta_config),
        (payload("C:\\normal\\x.md"), ruta_config),
        (payload(comun / "x.json"), tmp_path / "no-existe.json"),
    ]
    for datos, config in casos:
        assert ejecutar(datos, config)[0] == 0


# --- el log ---


def test_the_denial_is_recorded_in_the_log(archivo, log):
    comun, _, ruta_config = archivo
    ejecutar(payload(comun / "alfa" / "2026-08-28" / "09-x.json"), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.DENEGADO
    assert anotacion.proyecto == "alfa"
    assert "Write ->" in anotacion.detalle
    assert "09-x.json" in anotacion.detalle


def test_an_allowed_write_does_not_clutter_the_log(archivo, log):
    """Una linea por tool call llenaria el log de ruido."""
    _, _, ruta_config = archivo
    ejecutar(payload("C:\\proyectos\\alfa\\README.md"), ruta_config)

    assert reg.leer(log) == []


# --- la lanzadera, tal cual la ejecuta Claude Code ---


def lanzar(entrada):
    return subprocess.run(
        [sys.executable, str(RAIZ / "guardian_informes.py")],
        input=entrada,
        capture_output=True,
        text=True,
        timeout=30,
    )


def test_mechanism_the_launcher_denies_inside_the_archive(
    escribir_config, informes, log, tmp_path
):
    """La lanzadera de verdad, en otro proceso, deniega una escritura dentro del
    archivo. Config de FIXTURE: prueba el CABLEADO --lee la config, resuelve la
    zona protegida, deniega-- y esta verde en cualquier runner. Su contraparte de
    datos comprueba lo otro: que deniega sobre las rutas REALES.
    """
    ruta_config = escribir_config(
        [{"nombre": "vigilado", "cwd": str(tmp_path / "vigilado")}],
        raiz_informes=informes,
    )
    destino = Path(informes) / "vigilado" / "2026-08-28" / "99-falso.json"

    salida = _lanzar_guardian(
        {"tool_name": "Write", "cwd": str(tmp_path), "tool_input": {"file_path": str(destino)}},
        ruta_config,
        log,
    )

    assert salida.returncode == 0
    assert deniega(salida.stdout.decode("utf-8"))
    assert not destino.exists(), "denegar no crea nada"


@pytest.mark.real_data
def test_real_data_the_launcher_denies_over_my_real_paths(exigir_fichero_de_datos):
    """La lanzadera deniega sobre MIS rutas reales: la unica garantia que este
    test existe para dar.

    Hermeticizarlo con una config de fixture comprobaria que el guardian deniega
    EN GENERAL --y eso ya lo hace `test_mechanism_the_launcher_denies_inside_the
    _archive`-- pero dejaria de comprobar que deniega sobre las rutas REALES del
    archivo, que es lo unico que impide que alguien escriba a mano dentro de el.
    Por eso el par: mecanismo y datos son dos preguntas distintas. Solo corre
    donde existe la config real; si falta, FALLA con instrucciones, nunca skip.
    """
    ruta_real = cfg.ruta_de_config() or cfg.ruta_config_usuario()
    exigir_fichero_de_datos(
        ruta_real,
        como_crearlo=(
            "Create your real config with 'python -m claude_informes init' and put the\n"
            "real paths of your projects and of the reports root."
        ),
    )

    real = cfg.cargar()
    destino = str(Path(real.raiz_informes) / "alfa" / "2026-08-28" / "99-falso.json")
    proceso = lanzar(json.dumps(payload(destino)))

    assert proceso.returncode == 0
    assert deniega(proceso.stdout)
    assert not Path(destino).exists(), "denegar no crea nada"


def test_the_launcher_allows_a_normal_write():
    proceso = lanzar(json.dumps(payload("C:\\proyectos\\alfa\\README.md")))

    assert proceso.returncode == 0
    assert proceso.stdout == ""


def test_the_launcher_allows_with_a_broken_payload():
    proceso = lanzar("{esto no es json")

    assert proceso.returncode == 0
    assert proceso.stdout == ""


def test_an_own_root_nested_inside_the_global_one_wins_over_the_global(
    escribir_config, tmp_path, log
):
    """La zona mas especifica manda, y con ella el proyecto que se anota."""
    comun = tmp_path / "archivo"
    dentro = comun / "privado"
    ruta_config = escribir_config(
        [{"nombre": "beta", "cwd": "C:\\proyectos\\beta", "raiz_informes": dentro}],
        raiz_informes=comun,
    )

    codigo, salida = ejecutar(payload(dentro / "beta" / "x.json"), ruta_config)

    assert codigo == 0 and deniega(salida)
    assert reg.leer(log)[0].proyecto == "beta"


def test_an_unknown_folder_under_the_root_is_denied_without_a_project(archivo, log):
    """No se adivina el proyecto, pero se deniega igual."""
    comun, _, ruta_config = archivo
    assert deniega(ejecutar(payload(comun / "quien-sabe" / "x.json"), ruta_config)[1])
    assert reg.leer(log)[0].proyecto == reg.SIN_PROYECTO


# --- las fronteras del guardian, cruzadas por bytes ---


def _lanzar_guardian(payload, ruta_config, log):
    """El guardian de verdad, en otro proceso, hablando en bytes utf-8."""
    entorno = dict(os.environ)
    for variable in ("PYTHONUTF8", "PYTHONIOENCODING", "PYTHONLEGACYWINDOWSSTDIO"):
        entorno.pop(variable, None)
    entorno["CLAUDE_INFORMES_CONFIG"] = str(ruta_config)
    entorno["CLAUDE_INFORMES_LOG"] = str(log)
    lanzadera = Path(__file__).resolve().parent.parent / "guardian_informes.py"
    return subprocess.run(
        [sys.executable, str(lanzadera)],
        input=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        capture_output=True,
        env=entorno,
    )


def test_it_denies_even_when_the_path_does_not_fit_the_console_encoding(
    escribir_config, informes, log, tmp_path
):
    """La frontera con consecuencia de seguridad.

    Con `sys.stdout` heredado (cp1252), escribir una denegacion cuya ruta
    lleve un caracter que no quepa reventaba el write, el guardian caia a su
    `except`... y PERMITIA la escritura que tenia que denegar. Fallar abierto
    por un fallo propio de codificacion no es fallar abierto: es no estar.
    """
    ruta_config = escribir_config(
        [{"nombre": "vigilado", "cwd": str(tmp_path / "vigilado")}],
        raiz_informes=informes,
    )
    destino = Path(informes) / "vigilado" / "2026-09-01" / "01-anlisis-\u2190-\u274c.json"

    salida = _lanzar_guardian(
        {
            "tool_name": "Write",
            "cwd": str(tmp_path),
            "tool_input": {"file_path": str(destino)},
        },
        ruta_config,
        log,
    )

    assert salida.returncode == 0
    respuesta = json.loads(salida.stdout.decode("utf-8"))
    decision = respuesta["hookSpecificOutput"]
    assert decision["permissionDecision"] == "deny"
    assert "\u274c" in decision["permissionDecisionReason"]


def test_faced_with_invalid_json_it_keeps_failing_open(escribir_config, informes, log, tmp_path):
    """Regla numero uno del guardian, comprobada DESPUES de tocar sus flujos."""
    ruta_config = escribir_config(
        [{"nombre": "vigilado", "cwd": str(tmp_path / "vigilado")}],
        raiz_informes=informes,
    )
    lanzadera = Path(__file__).resolve().parent.parent / "guardian_informes.py"
    entorno = dict(os.environ)
    entorno["CLAUDE_INFORMES_CONFIG"] = str(ruta_config)
    entorno["CLAUDE_INFORMES_LOG"] = str(log)

    salida = subprocess.run(
        [sys.executable, str(lanzadera)],
        input=b"{esto no es json",
        capture_output=True,
        env=entorno,
    )

    assert salida.returncode == 0
    assert salida.stdout == b"", "sin salida = sin decision = la herramienta sigue"
    assert reg.leer(log)[-1].resultado == reg.PERMITIDO_POR_ERROR
