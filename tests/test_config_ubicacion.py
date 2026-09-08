"""Where the config lives and how it is resolved.

The REAL config is not in the repo: it lives in the OS user config, or
CLAUDE_INFORMES_CONFIG points to it. The repo only carries the example. Here
the resolution order is pinned down, the message when there is none, and the
`init` command.
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


# --- resolution order ---


def test_the_environment_variable_wins_over_the_user_config(tmp_path, monkeypatch):
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


def test_the_user_config_is_found_without_the_environment_variable(tmp_path, monkeypatch):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    usuario = _escribir(
        tmp_path / "user" / "proyectos.json",
        [{"nombre": "de-usuario", "cwd": str(tmp_path / "u")}],
    )
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: usuario)

    assert cfg.ruta_de_config() == usuario
    assert [p.nombre for p in cfg.cargar().proyectos] == ["de-usuario"]


def test_with_no_config_at_all_there_is_neither_a_path_nor_projects(tmp_path, monkeypatch):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    monkeypatch.setattr(
        cfg, "ruta_config_usuario", lambda: tmp_path / "no-existe" / "proyectos.json"
    )

    assert cfg.ruta_de_config() is None
    assert cfg.cargar().proyectos == []


def test_the_no_config_message_says_how_to_create_it_and_is_not_a_traceback(tmp_path, monkeypatch):
    monkeypatch.delenv(cfg.VAR_ENTORNO, raising=False)
    destino = tmp_path / "no-existe" / "proyectos.json"
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: destino)

    mensaje = cfg.mensaje_sin_config()
    assert isinstance(mensaje, str) and mensaje.strip()
    assert "init" in mensaje, "it must name the command that creates it"
    assert str(destino) in mensaje, "it must say where it goes"
    assert "Traceback" not in mensaje


# --- location by operating system ---


def test_the_user_location_follows_the_convention_of_each_operating_system(monkeypatch):
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


# --- the init command ---


def test_init_creates_the_config_from_the_bundled_example(tmp_path, monkeypatch, capsys):
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


def test_init_does_not_overwrite_an_existing_config(tmp_path, monkeypatch, capsys):
    destino = _escribir(
        tmp_path / "user" / "proyectos.json",
        [{"nombre": "mia", "cwd": str(tmp_path / "m")}],
    )
    monkeypatch.setattr(cfg, "ruta_config_usuario", lambda: destino)
    antes = destino.read_text(encoding="utf-8")

    codigo = cli.main(["init"])

    assert codigo == 0
    assert destino.read_text(encoding="utf-8") == antes, "it does not overwrite what is already there"
    assert "already exists" in capsys.readouterr().out
