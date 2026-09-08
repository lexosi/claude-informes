"""Donde vive la config y como se resuelve.

La config REAL no esta en el repo: vive en la config de usuario del SO, o la
apunta CLAUDE_INFORMES_CONFIG. El repo solo lleva el ejemplo. Aqui se fija el
orden de resolucion, el mensaje cuando no hay ninguna, y el comando `init`.
"""

import json
import sys
from pathlib import Path

from claude_informes import cli
from claude_informes import config as cfg


def _escribir(ruta: Path, proyectos, raiz=None) -> Path:
    ruta.parent.mkdir(parents=True, exist_ok=True)
    contenido = {"proyectos": proyectos}
    if raiz is not None:
        contenido["raiz_informes"] = str(raiz)
    ruta.write_text(json.dumps(contenido, ensure_ascii=False), encoding="utf-8")
    return ruta


# --- orden de resolucion ---


def test_el_entorno_gana_sobre_la_config_de_usuario(tmp_path, monkeypatch):
    usuario = _escribir(
        tmp_path / "user" / "proyectos.json",
        [{"nombre": "de-usuario", "cwd": str(tmp_path / "u")}],
    )
    del_entorno = _escribir(
        tmp_path / "env" / "otro.json",
        [{"nombre": "del-entorno", "cwd": str(tmp_path / "e")}],
    )
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: usuario)
    monkeypatch.setenv(cfg.VAR_ENTORNO, str(del_entorno))

    assert cfg.ruta_de_config() == del_entorno
    assert [p.nombre for p in cfg.cargar().proyectos] == ["del-entorno"]


def test_la_config_de_usuario_se_encuentra_sin_variable(tmp_path, monkeypatch):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    usuario = _escribir(
        tmp_path / "user" / "proyectos.json",
        [{"nombre": "de-usuario", "cwd": str(tmp_path / "u")}],
    )
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: usuario)

    assert cfg.ruta_de_config() == usuario
    assert [p.nombre for p in cfg.cargar().proyectos] == ["de-usuario"]


def test_sin_ninguna_config_no_hay_ruta_ni_proyectos(tmp_path, monkeypatch):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    monkeypatch.setattr(
        cfg, "ruta_config_usuario", lambda: tmp_path / "no-existe" / "proyectos.json"
    )

    assert cfg.ruta_de_config() is None
    assert cfg.cargar().proyectos == []


def test_el_mensaje_sin_config_dice_como_crearla_y_no_es_un_traceback(tmp_path, monkeypatch):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    destino = tmp_path / "no-existe" / "proyectos.json"
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: destino)

    mensaje = cfg.mensaje_sin_config()
    assert isinstance(mensaje, str) and mensaje.strip()
    assert "init" in mensaje, "tiene que decir el comando que la crea"
    assert str(destino) in mensaje, "tiene que decir donde va"
    assert "Traceback" not in mensaje


# --- ubicacion por sistema operativo ---


def test_la_ubicacion_de_usuario_sigue_la_convencion_de_cada_so(monkeypatch):
    monkeypatch.setattr(sys, "platform", "win32")
    monkeypatch.setenv("APPDATA", str(Path.home() / "Roaming"))
    win = cfg.dir_config_usuario()
    assert win.name == cfg.CARPETA_APP
    assert win.parent.name == "Roaming"

    monkeypatch.setattr(sys, "platform", "linux")
    monkeypatch.setenv("XDG_CONFIG_HOME", str(Path.home() / ".config"))
    linux = cfg.dir_config_usuario()
    assert linux.parent.name == ".config" and linux.name == cfg.CARPETA_APP

    monkeypatch.setattr(sys, "platform", "darwin")
    mac = cfg.dir_config_usuario()
    partes = mac.parts
    assert "Library" in partes and "Application Support" in partes
    assert mac.name == cfg.CARPETA_APP


# --- el comando init ---


def test_init_crea_la_config_desde_el_ejemplo(tmp_path, monkeypatch, capsys):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    destino = tmp_path / "user" / "proyectos.json"
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: destino)

    codigo = cli.main(["init"])
    salida = capsys.readouterr().out

    assert codigo == 0 and destino.is_file()
    assert json.loads(destino.read_text(encoding="utf-8")) == json.loads(
        cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    )
    assert str(destino) in salida


def test_init_no_pisa_una_config_existente(tmp_path, monkeypatch, capsys):
    destino = _escribir(
        tmp_path / "user" / "proyectos.json",
        [{"nombre": "mia", "cwd": str(tmp_path / "m")}],
    )
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: destino)
    antes = destino.read_text(encoding="utf-8")

    codigo = cli.main(["init"])

    assert codigo == 0
    assert destino.read_text(encoding="utf-8") == antes, "no pisa lo que ya hay"
    assert "already exists" in capsys.readouterr().out
