"""El log del hook. Silencio en la consola, nunca silencio en el log."""

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


# --- formato ---


def test_la_linea_lleva_marca_proyecto_resultado_y_detalle():
    linea = reg.formatear(
        reg.ESCRITO, "loopward", "E:\\example-reports\\x.json", datetime(2026, 8, 28, 16, 5, 9)
    )
    campos = [t.strip() for t in linea.split(" | ")]
    assert campos == [
        "2026-08-28T16:05:09",
        "loopward",
        "escrito",
        "E:\\example-reports\\x.json",
    ]


def test_el_detalle_nunca_parte_la_linea():
    """Un motivo con saltos de linea no puede convertirse en dos anotaciones."""
    linea = reg.formatear(reg.ERROR, "x", "algo\nen dos\nlineas")
    assert "\n" not in linea
    assert reg.leer_linea(linea).detalle == "algo en dos lineas"


def test_el_log_es_append_only(tmp_path):
    ruta = tmp_path / "hook.log"
    reg.anotar(ruta, reg.ESCRITO, "uno", "a.json")
    reg.anotar(ruta, reg.OMITIDO_UMBRAL, "dos", "3 lineas")

    assert [a.proyecto for a in reg.leer(ruta)] == ["uno", "dos"]


def test_el_log_se_escribe_en_lf(tmp_path):
    ruta = tmp_path / "hook.log"
    reg.anotar(ruta, reg.ESCRITO, "uno", "a.json")
    reg.anotar(ruta, reg.ESCRITO, "uno", "b.json")

    assert b"\r\n" not in ruta.read_bytes()


def test_las_lineas_ilegibles_se_ignoran_una_a_una(tmp_path):
    ruta = tmp_path / "hook.log"
    reg.anotar(ruta, reg.ESCRITO, "uno", "a.json")
    with open(ruta, "a", encoding="utf-8", newline="\n") as f:
        f.write("basura sin formato\n")
    reg.anotar(ruta, reg.ESCRITO, "dos", "b.json")

    assert [a.proyecto for a in reg.leer(ruta)] == ["uno", "dos"]


def test_un_log_inexistente_se_lee_como_vacio(tmp_path):
    assert reg.leer(tmp_path / "no-existe.log") == []


def test_la_ruta_por_defecto_es_hermana_del_archivo_no_hija():
    ruta = reg.ruta_por_defecto("E:\\example-reports")
    assert ruta == Path("E:\\example-reports.log")
    assert "informes-claude" not in ruta.parent.name


# --- los cinco resultados ---


def test_un_turno_escrito_se_anota_con_su_ruta(proyecto_vigilado, informes, log):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ESCRITO
    assert anotacion.proyecto == "vigilado"
    assert anotacion.ruta.is_file()
    assert anotacion.ruta == next(Path(informes).rglob("*.json"))


def test_un_turno_corto_se_anota_como_omitido_por_umbral(proyecto_vigilado, log):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz), last_assistant_message=CORTA), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_UMBRAL
    assert anotacion.proyecto == "vigilado"
    assert "3 lineas" in anotacion.detalle and "umbral 5" in anotacion.detalle


def test_un_cwd_ajeno_se_anota_como_omitido_por_cwd(proyecto_vigilado, tmp_path, log):
    _, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(tmp_path / "project-b")), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert anotacion.proyecto == reg.SIN_PROYECTO
    assert "project-b" in anotacion.detalle


def test_el_cwd_de_la_herramienta_se_anota_como_omitido_por_guardia(
    escribir_config, informes, log
):
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia)}], raiz_informes=informes
    )
    ejecutar(payload(cwd=str(propia)), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_GUARDIA
    assert not Path(informes).exists()


def test_un_payload_roto_se_anota_como_error(proyecto_vigilado, log):
    _, ruta_config = proyecto_vigilado
    ejecutar(None, ruta_config, texto_crudo="{esto no es json")

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ERROR
    assert "JSONDecodeError" in anotacion.detalle


def test_los_cinco_resultados_caben_en_el_mismo_log(
    escribir_config, informes, tmp_path, log, monkeypatch
):
    """Un log, un turno por linea, los cinco casos distinguibles."""
    raiz = tmp_path / "vigilado"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "vigilado", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=CORTA), ruta_config)
    ejecutar(payload(cwd=str(tmp_path / "ajeno")), ruta_config)
    ejecutar(payload(cwd=str(cfg.raiz_de_la_herramienta())), ruta_config)
    ejecutar(None, ruta_config, texto_crudo="no soy json")

    assert [a.resultado for a in reg.leer(log)] == [
        reg.ESCRITO,
        reg.OMITIDO_UMBRAL,
        reg.OMITIDO_SESION,
        reg.OMITIDO_GUARDIA,
        reg.ERROR,
    ]


def test_una_reentrada_tambien_deja_linea(proyecto_vigilado, log):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz), stop_hook_active=True), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_REENTRADA


def test_cada_turno_deja_exactamente_una_linea(proyecto_vigilado, log):
    """Una linea por turno. La segunda solo aparece en el camino degradado."""
    raiz, ruta_config = proyecto_vigilado
    for i in range(4):
        ejecutar(payload(cwd=str(raiz), last_assistant_message=RESPUESTA + str(i)), ruta_config)

    assert len(reg.leer(log)) == 4


# --- lo que no puede pasar ---


def test_si_falla_la_escritura_del_informe_sale_0_y_queda_anotado(
    proyecto_vigilado, informes, log, monkeypatch
):
    """El fallo es invisible en consola, pero no en el log."""
    raiz, ruta_config = proyecto_vigilado

    def escritura_rota(*args, **kwargs):
        raise OSError("no queda espacio en el disco")

    monkeypatch.setattr(inf, "escribir", escritura_rota)

    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert not Path(informes).exists()

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.ERROR
    assert "no queda espacio en el disco" in anotacion.detalle


def test_si_falla_el_log_sale_0_y_sin_ruido(proyecto_vigilado, informes, log, capsys):
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
    assert len(list(Path(informes).rglob("*.json"))) == 1, "el informe si se escribio"


def test_si_falla_el_log_y_ademas_el_informe_sale_0(proyecto_vigilado, log, monkeypatch, capsys):
    raiz, ruta_config = proyecto_vigilado
    monkeypatch.setattr(Path, "mkdir", lambda *a, **k: (_ for _ in ()).throw(OSError("nada")))

    assert ejecutar(payload(cwd=str(raiz)), ruta_config) == 0
    assert capsys.readouterr().out == ""


def test_el_log_nunca_se_escribe_en_stdout(proyecto_vigilado, capsys):
    raiz, ruta_config = proyecto_vigilado
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    capturado = capsys.readouterr()
    assert capturado.out == "" and capturado.err == ""


# --- la orden `ultimo` ---


def escribir_config_con_proyecto(escribir_config, informes, tmp_path, nombre="vigilado"):
    raiz = tmp_path / nombre
    raiz.mkdir(exist_ok=True)
    return raiz, escribir_config(
        [{"nombre": nombre, "cwd": str(raiz)}], raiz_informes=informes
    )


def test_ultimo_da_el_fichero_real_verificado_en_disco(
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
    assert "existe en disco" in salida


def test_ultimo_avisa_si_el_log_miente(escribir_config, informes, tmp_path, capsys):
    """El caso que ya paso una vez: se anuncio un fichero que no existia."""
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    next(Path(informes).rglob("*.json")).unlink()

    codigo = cli.main(["ultimo", "--config", str(ruta_config)])

    capturado = capsys.readouterr()
    assert codigo == 1
    assert "NO EXISTE EN DISCO" in capturado.err


def test_ultimo_coge_el_mas_reciente_de_ese_proyecto(
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

    assert "proyecto : uno" in salida
    assert "02-" in salida, "el segundo de 'uno', no el de 'dos'"


def test_ultimo_ignora_las_lineas_que_no_son_escrituras(
    escribir_config, informes, tmp_path, capsys
):
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)
    ejecutar(payload(cwd=str(raiz), last_assistant_message=CORTA), ruta_config)

    codigo = cli.main(["ultimo", "--config", str(ruta_config)])
    assert codigo == 0
    assert "01-" in capsys.readouterr().out


def test_ultimo_sin_log_lo_dice(escribir_config, tmp_path, capsys):
    ruta_config = escribir_config([{"nombre": "x", "cwd": str(tmp_path)}])
    codigo = cli.main(["ultimo", "--config", str(ruta_config)])

    assert codigo == 2
    assert "vacio o no existe" in capsys.readouterr().err


def test_ultimo_sin_informes_de_ese_proyecto_lo_dice(
    escribir_config, informes, tmp_path, capsys
):
    raiz, ruta_config = escribir_config_con_proyecto(escribir_config, informes, tmp_path)
    ejecutar(payload(cwd=str(raiz)), ruta_config)

    codigo = cli.main(["ultimo", "--proyecto", "project-b", "--config", str(ruta_config)])

    assert codigo == 2
    assert "project-b" in capsys.readouterr().err
