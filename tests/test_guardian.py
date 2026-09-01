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


def payload(ruta, herramienta="Write", cwd="E:\\example-projects\\loopward", **extras):
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
            {"nombre": "loopward", "cwd": "E:\\example-projects\\loopward"},
            {
                "nombre": "project-b",
                "cwd": "E:\\example-projects\\project-b",
                "raiz_informes": cofre,
            },
        ],
        raiz_informes=comun,
    )
    return comun, cofre, ruta_config


# --- lo que hay que denegar ---


def test_una_escritura_bajo_la_raiz_global_se_deniega(archivo):
    comun, _, ruta_config = archivo
    codigo, salida = ejecutar(payload(comun / "loopward" / "2026-08-28" / "09-x.json"), ruta_config)

    assert codigo == 0
    assert deniega(salida)


def test_una_escritura_bajo_una_raiz_por_proyecto_se_deniega(archivo):
    """La raiz del proyecto no es la global y tambien esta protegida."""
    _, cofre, ruta_config = archivo
    codigo, salida = ejecutar(payload(cofre / "project-b" / "2026-08-28" / "01-x.json"), ruta_config)

    assert codigo == 0
    assert deniega(salida)
    assert "project-b" in razon(salida)


def test_una_escritura_al_fichero_de_log_se_deniega(archivo, log):
    _, _, ruta_config = archivo
    codigo, salida = ejecutar(payload(log), ruta_config)

    assert deniega(salida)
    assert "log del hook" in razon(salida)


def test_una_ruta_relativa_con_dos_puntos_se_resuelve_y_se_deniega(archivo, tmp_path):
    """`..\\..\\informes-claude\\x.json` cae dentro igual."""
    comun, _, ruta_config = archivo
    desde = tmp_path / "repos" / "loopward"
    desde.mkdir(parents=True)
    relativa = Path("..") / ".." / comun.name / "loopward" / "x.json"

    codigo, salida = ejecutar(payload(relativa, cwd=str(desde)), ruta_config)

    assert deniega(salida)
    assert str(comun) in razon(salida).replace("/", "\\") or comun.name in razon(salida)


def test_la_propia_carpeta_del_archivo_se_deniega(archivo):
    comun, _, ruta_config = archivo
    assert deniega(ejecutar(payload(comun), ruta_config)[1])


@pytest.mark.parametrize("herramienta", ["Write", "Edit", "MultiEdit", "NotebookEdit"])
def test_todas_las_herramientas_de_escritura_quedan_cubiertas(herramienta, archivo):
    comun, _, ruta_config = archivo
    campo = "notebook_path" if herramienta == "NotebookEdit" else "file_path"
    datos = payload(comun / "x.json", herramienta=herramienta)
    datos["tool_input"] = {campo: str(comun / "x.json")}

    assert deniega(ejecutar(datos, ruta_config)[1])


def test_una_edicion_multiple_se_revisa_entrada_por_entrada(archivo):
    comun, _, ruta_config = archivo
    datos = payload(comun / "x.json", herramienta="MultiEdit")
    datos["tool_input"] = {
        "edits": [
            {"file_path": "E:\\example-projects\\loopward\\README.md"},
            {"file_path": str(comun / "loopward" / "x.json")},
        ]
    }
    assert deniega(ejecutar(datos, ruta_config)[1])


def test_el_mensaje_dice_por_que_y_que_hacer(archivo):
    comun, _, ruta_config = archivo
    motivo = razon(ejecutar(payload(comun / "loopward" / "x.json"), ruta_config)[1])

    assert "archivo de informes" in motivo
    assert "hook Stop" in motivo
    assert "ultimo" in motivo, "tiene que decir que hacer en su lugar"
    assert "--proyecto loopward" in motivo


# --- lo que NO se puede denegar ---


def test_una_escritura_normal_en_un_repo_se_permite(archivo):
    _, _, ruta_config = archivo
    for ruta in [
        "E:\\example-projects\\loopward\\README.md",
        "E:\\example-projects\\loopward\\loopward\\cli.py",
        "E:\\example-projects\\project-b\\cv.md",
        "E:\\example-projects\\claude-informes\\claude_informes\\hook.py",
    ]:
        codigo, salida = ejecutar(payload(ruta), ruta_config)
        assert codigo == 0 and salida == "", ruta


def test_un_hermano_con_prefijo_comun_se_permite(archivo, tmp_path):
    """`informes-claude-otra-cosa` no esta dentro de `informes-claude`."""
    comun, _, ruta_config = archivo
    vecino = comun.parent / (comun.name + "-otra-cosa") / "x.json"

    assert ejecutar(payload(vecino), ruta_config)[1] == ""


def test_una_herramienta_que_no_escribe_ficheros_se_permite(archivo):
    comun, _, ruta_config = archivo
    for herramienta in ["Read", "Bash", "Glob", "Grep"]:
        datos = payload(comun / "x.json", herramienta=herramienta)
        assert ejecutar(datos, ruta_config)[1] == "", herramienta


def test_bash_no_se_intercepta_aunque_mencione_el_archivo(archivo):
    """Adivinar rutas dentro de una linea de shell da falsos positivos."""
    comun, _, ruta_config = archivo
    datos = payload("x", herramienta="Bash")
    datos["tool_input"] = {"command": f"echo hola > {comun}\\x.json"}

    assert ejecutar(datos, ruta_config)[1] == ""


# --- falla abierto: lo contrario del hook Stop ---


def test_una_config_ausente_permite_y_lo_anota(tmp_path, log):
    codigo, salida = ejecutar(
        payload(tmp_path / "informes-claude" / "x.json"), tmp_path / "no-existe.json"
    )

    assert codigo == 0 and salida == "", "sin config no se puede afirmar nada: permite"
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.PERMITIDO_POR_ERROR
    assert "FileNotFoundError" in anotacion.detalle


def test_una_config_corrupta_permite_y_lo_anota(tmp_path, log):
    rota = tmp_path / "rota.json"
    rota.write_text("{esto no es json", encoding="utf-8")

    codigo, salida = ejecutar(payload(tmp_path / "informes-claude" / "x.json"), rota)

    assert codigo == 0 and salida == ""
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.PERMITIDO_POR_ERROR


def test_un_payload_corrupto_permite_sin_ruido(archivo, capsys):
    _, _, ruta_config = archivo
    for crudo in ["", "no soy json", "{", "[1,2]", "null", '"cadena"']:
        codigo, salida = ejecutar(None, ruta_config, texto_crudo=crudo)
        assert codigo == 0 and salida == "", crudo
    assert capsys.readouterr().out == ""


def test_un_payload_sin_los_campos_esperados_permite(archivo):
    _, _, ruta_config = archivo
    for datos in [{}, {"tool_name": "Write"}, {"tool_name": "Write", "tool_input": None}]:
        assert ejecutar(datos, ruta_config)[1] == ""


def test_si_revisar_revienta_se_permite(archivo, monkeypatch, log):
    _, _, ruta_config = archivo

    def revisar_roto(*args, **kwargs):
        raise RuntimeError("algo se ha roto por dentro")

    monkeypatch.setattr(gd, "revisar", revisar_roto)
    codigo, salida = ejecutar(payload("E:\\lo\\que\\sea"), ruta_config)

    assert codigo == 0 and salida == ""
    assert reg.leer(log)[0].resultado == reg.PERMITIDO_POR_ERROR


def test_si_falla_el_log_la_denegacion_sigue_saliendo(archivo, monkeypatch):
    comun, _, ruta_config = archivo

    def anotar_roto(*args, **kwargs):
        raise PermissionError("el log es de solo lectura")

    monkeypatch.setattr(reg, "anotar", anotar_roto)
    codigo, salida = ejecutar(payload(comun / "loopward" / "x.json"), ruta_config)

    assert codigo == 0
    assert deniega(salida), "el log es secundario; la decision no depende de el"


def test_nunca_devuelve_un_codigo_distinto_de_cero(archivo, tmp_path):
    comun, _, ruta_config = archivo
    casos = [
        (payload(comun / "x.json"), ruta_config),
        (payload("E:\\normal\\x.md"), ruta_config),
        (payload(comun / "x.json"), tmp_path / "no-existe.json"),
    ]
    for datos, config in casos:
        assert ejecutar(datos, config)[0] == 0


# --- el log ---


def test_la_denegacion_queda_en_el_log(archivo, log):
    comun, _, ruta_config = archivo
    ejecutar(payload(comun / "loopward" / "2026-08-28" / "09-x.json"), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.DENEGADO
    assert anotacion.proyecto == "loopward"
    assert "Write ->" in anotacion.detalle
    assert "09-x.json" in anotacion.detalle


def test_una_escritura_permitida_no_ensucia_el_log(archivo, log):
    """Una linea por tool call llenaria el log de ruido."""
    _, _, ruta_config = archivo
    ejecutar(payload("E:\\example-projects\\loopward\\README.md"), ruta_config)

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


def test_la_lanzadera_deniega_con_la_config_real():
    real = cfg.cargar()
    destino = str(Path(real.raiz_informes) / "loopward" / "2026-08-28" / "99-falso.json")
    proceso = lanzar(json.dumps(payload(destino)))

    assert proceso.returncode == 0
    assert deniega(proceso.stdout)
    assert not Path(destino).exists(), "denegar no crea nada"


def test_la_lanzadera_permite_una_escritura_normal():
    proceso = lanzar(json.dumps(payload("E:\\example-projects\\loopward\\README.md")))

    assert proceso.returncode == 0
    assert proceso.stdout == ""


def test_la_lanzadera_permite_con_un_payload_roto():
    proceso = lanzar("{esto no es json")

    assert proceso.returncode == 0
    assert proceso.stdout == ""


def test_una_raiz_propia_anidada_en_la_global_gana_a_la_global(
    escribir_config, tmp_path, log
):
    """La zona mas especifica manda, y con ella el proyecto que se anota."""
    comun = tmp_path / "archivo"
    dentro = comun / "privado"
    ruta_config = escribir_config(
        [{"nombre": "project-b", "cwd": "E:\\example-projects\\project-b", "raiz_informes": dentro}],
        raiz_informes=comun,
    )

    codigo, salida = ejecutar(payload(dentro / "project-b" / "x.json"), ruta_config)

    assert codigo == 0 and deniega(salida)
    assert reg.leer(log)[0].proyecto == "project-b"


def test_una_carpeta_desconocida_bajo_la_raiz_se_deniega_sin_proyecto(archivo, log):
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


def test_deniega_aunque_la_ruta_no_quepa_en_el_encoding_de_la_consola(
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


def test_ante_un_json_invalido_sigue_fallando_abierto(escribir_config, informes, log, tmp_path):
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
