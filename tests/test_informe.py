"""El sobre, su ruta y su escritura en disco."""

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


# --- estructura de carpetas ---


def test_la_ruta_es_raiz_proyecto_dia(tmp_path):
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.parent == dia(tmp_path)
    assert destino.name == f"01-{SLUG}.json"


def test_se_crean_los_dos_niveles_de_golpe(tmp_path):
    inf.escribir(tmp_path / "sin" / "hacer", "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert (tmp_path / "sin" / "hacer" / "repo" / "2026-08-28").is_dir()


def test_una_carpeta_de_proyecto_existente_se_reutiliza(tmp_path):
    dia(tmp_path).mkdir(parents=True)
    inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert [p.name for p in tmp_path.iterdir()] == ["repo"]
    assert [p.name for p in (tmp_path / "repo").iterdir()] == ["2026-08-28"]


def test_no_se_crean_variantes_de_una_carpeta_que_ya_existe(tmp_path):
    """En Windows 'Repo' y 'repo' son la misma; se usa la que ya esta."""
    (tmp_path / "Repo").mkdir()
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert len(list(tmp_path.iterdir())) == 1
    assert destino.parent.parent.name == "Repo"


def test_dos_dias_distintos_son_dos_carpetas(tmp_path):
    inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-27T10:00:00Z"))
    inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert sorted(p.name for p in (tmp_path / "repo").iterdir()) == [
        "2026-08-27",
        "2026-08-28",
    ]


def test_dos_proyectos_no_comparten_carpeta(tmp_path):
    inf.escribir(tmp_path, "uno", sobre(cuando="2026-08-28T10:00:00Z"))
    inf.escribir(tmp_path, "dos", sobre(cuando="2026-08-28T10:00:00Z"))

    assert sorted(p.name for p in tmp_path.iterdir()) == ["dos", "uno"]
    assert len(list(dia(tmp_path, "uno").glob("*.json"))) == 1
    assert len(list(dia(tmp_path, "dos").glob("*.json"))) == 1


# --- ordinal ---


def test_el_primer_informe_del_dia_es_el_01(tmp_path):
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.name.startswith("01-")


def test_el_ordinal_continua_donde_lo_dejo_el_anterior(tmp_path):
    dia(tmp_path).mkdir(parents=True)
    (dia(tmp_path) / "07-lo-que-sea.json").write_text("{}", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.name.startswith("08-")


def test_el_ordinal_reinicia_en_01_cada_dia(tmp_path):
    for _ in range(3):
        inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-27T10:00:00Z"))
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert sorted(p.name[:2] for p in dia(tmp_path, fecha="2026-08-27").iterdir()) == [
        "01",
        "02",
        "03",
    ]
    assert destino.name.startswith("01-")


def test_el_ordinal_no_se_confunde_entre_proyectos(tmp_path):
    inf.escribir(tmp_path, "uno", sobre(cuando="2026-08-28T10:00:00Z"))
    inf.escribir(tmp_path, "uno", sobre(cuando="2026-08-28T10:00:00Z"))
    destino = inf.escribir(tmp_path, "dos", sobre(cuando="2026-08-28T10:00:00Z"))

    assert destino.name.startswith("01-")


def test_dos_informes_con_el_mismo_slug_no_se_pisan(tmp_path):
    uno = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    dos = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert uno.name == f"01-{SLUG}.json"
    assert dos.name == f"02-{SLUG}.json"
    assert len(list(dia(tmp_path).glob("*.json"))) == 2


def test_un_nombre_ya_reservado_no_se_sobrescribe(tmp_path):
    """Simula el turno simultaneo: el ordinal libre ya no lo esta."""
    dia(tmp_path).mkdir(parents=True)
    ocupado = dia(tmp_path) / f"01-{SLUG}.json"
    ocupado.write_text("de otro turno", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert destino.name == f"02-{SLUG}.json"
    assert ocupado.read_text(encoding="utf-8") == "de otro turno"


def test_los_ficheros_ajenos_de_la_carpeta_no_estorban(tmp_path):
    dia(tmp_path).mkdir(parents=True)
    (dia(tmp_path) / "notas.txt").write_text("hola", encoding="utf-8")
    (dia(tmp_path) / "sin-ordinal.json").write_text("{}", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))
    assert destino.name.startswith("01-")


# --- escritura ---


def test_no_queda_ningun_temporal(tmp_path):
    inf.escribir(tmp_path, "repo", sobre())
    assert list(tmp_path.rglob("*.tmp")) == []


def test_el_json_es_legible_y_con_sangria(tmp_path):
    destino = inf.escribir(tmp_path, "repo", sobre())
    texto = destino.read_text(encoding="utf-8")
    assert texto.endswith("\n")
    assert json.loads(texto)["respuesta_markdown"] == MARKDOWN


# --- fecha y hora ---


def test_una_marca_de_tiempo_en_utc_se_pasa_a_hora_local():
    resultado = inf.construir("x", session_id=None, cwd=None, cuando="2026-08-28T11:31:37.388Z")
    assert resultado["fecha"] == "2026-08-28"
    assert len(resultado["hora"].split(":")) == 3


def test_una_marca_de_tiempo_ilegible_no_revienta():
    resultado = inf.construir("x", session_id=None, cwd=None, cuando="ayer por la tarde")
    assert len(resultado["fecha"]) == 10


def test_sin_marca_de_tiempo_se_usa_el_reloj():
    resultado = inf.construir("x", session_id=None, cwd=None)
    assert len(resultado["fecha"]) == 10 and len(resultado["hora"]) == 8


# --- git ---


def test_git_en_un_directorio_que_no_existe_da_none(tmp_path):
    assert inf.datos_git(str(tmp_path / "fantasma")) == (None, None)


def test_git_fuera_de_un_repositorio_da_none(tmp_path):
    assert inf.datos_git(str(tmp_path)) == (None, None)


# --- la lanzadera, tal cual la ejecuta Claude Code ---


def lanzar(entrada, ruta_config=None):
    """La lanzadera en otro proceso.

    `ruta_config` NO es opcional por comodidad: sin ella, la lanzadera lee la
    config REAL y escribe en el archivo REAL. Un test que ejecute la
    lanzadera y no la pase esta escribiendo en produccion.
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


def test_la_lanzadera_sale_0_con_un_payload_corrupto():
    proceso = lanzar("{esto no es json")
    assert proceso.returncode == 0
    assert proceso.stdout == "" and proceso.stderr == ""


def test_la_lanzadera_sale_0_con_un_cwd_ajeno(tmp_path):
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


def test_la_lanzadera_archiva_con_el_cwd_de_la_propia_herramienta(
    tmp_path, escribir_config, informes
):
    """Retirada la guardia, la herramienta se archiva como cualquier proyecto.

    Este test escribia en el archivo DE VERDAD: ejecutaba la lanzadera sin
    pasarle config, con lo que leia la real. Pasaba porque miraba en
    `claude-informes/informes/`, el destino viejo, que ya no existe. La
    guardia lo tapaba; al retirarla, empezo a dejar informes de prueba en
    `E:/example-reports/claude-informes/`.
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
    assert not (RAIZ / "informes").exists(), "el destino viejo no debe resucitar"


def test_la_lanzadera_sale_0_con_stdin_vacio():
    assert lanzar("").returncode == 0


# --- el cerrojo: el .tmp reserva, el .json solo aparece al final ---


def test_el_json_no_existe_hasta_tener_contenido(tmp_path, monkeypatch):
    """Mientras se escribe hay `.tmp` y NO hay `.json`. Nunca uno a cero."""
    vistos = []
    real = inf.json.dumps

    def espiar(*args, **kwargs):
        vistos.append(sorted(p.name for p in dia(tmp_path).iterdir()))
        return real(*args, **kwargs)

    monkeypatch.setattr(inf.json, "dumps", espiar)
    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert vistos == [[f"01-{SLUG}.json.tmp"]], "el .json no puede existir antes de tener contenido"
    assert destino.name == f"01-{SLUG}.json"
    assert [p.name for p in dia(tmp_path).iterdir()] == [f"01-{SLUG}.json"]


def test_un_tmp_huerfano_tiene_su_ordinal_cogido(tmp_path):
    """Si no se contaran los .tmp, el cerrojo no serviria de nada."""
    dia(tmp_path).mkdir(parents=True)
    (dia(tmp_path) / "01-de-otro-turno.json.tmp").write_text("", encoding="utf-8")

    destino = inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert destino.name == f"02-{SLUG}.json"


def test_ocho_turnos_a_la_vez_no_repiten_ordinal(tmp_path):
    """El O_EXCL sigue mandando ahora que el cerrojo es el .tmp."""
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


def test_si_la_escritura_falla_no_queda_nada_en_disco(tmp_path, monkeypatch):
    """Los tres informes a cero de produccion eran exactamente esto."""

    def revienta(*args, **kwargs):
        raise UnicodeEncodeError("utf-8", "x", 0, 1, "de mentira")

    monkeypatch.setattr(inf.json, "dumps", revienta)
    with pytest.raises(inf.FalloDeEscritura) as fallo:
        inf.escribir(tmp_path, "repo", sobre(cuando="2026-08-28T10:00:00Z"))

    assert fallo.value.ruta.name == f"01-{SLUG}.json"
    assert isinstance(fallo.value.causa, UnicodeEncodeError)
    assert list(dia(tmp_path).iterdir()) == []
