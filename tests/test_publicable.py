"""El repositorio es publicable: ni una ruta real de nadie dentro.

La config real vive fuera del repo; aqui se comprueba que el repo solo lleva el
ejemplo (JSON valido, rutas ficticias) y que en ningun fichero versionado se
cuela una ruta absoluta concreta.
"""

import json
import os

from claude_informes import config as cfg

RAIZ = cfg.raiz_de_la_herramienta()

# Se arman por fragmentos a proposito: asi la secuencia prohibida no aparece
# literal en este fichero, que si no se delataria a si mismo al escanearse.
PROHIBIDOS = [
    "F" + ":" + "\\",
    "F" + ":" + "/",
    "E" + ":" + "\\",
    "E" + ":" + "/",
    "C:" + "\\" + "Users" + "\\" + "user",
    "C:" + "/" + "Users" + "/" + "user",
]

EXTENSIONES = {".py", ".md", ".json", ".toml", ".cfg", ".ini", ".txt", ".gitignore", ".gitattributes"}
CARPETAS_FUERA = {".git", ".venv", "__pycache__", ".pytest_cache", "informes"}


def _ficheros_versionables():
    for actual, subdirs, ficheros in os.walk(RAIZ):
        subdirs[:] = [
            d for d in subdirs
            if d not in CARPETAS_FUERA and not d.endswith(".egg-info")
        ]
        for nombre in ficheros:
            ruta = os.path.join(actual, nombre)
            _, ext = os.path.splitext(nombre)
            if ext in EXTENSIONES or nombre in {".gitignore", ".gitattributes"}:
                yield ruta


# --- el ejemplo ---


def test_el_ejemplo_es_json_valido_y_tiene_forma():
    datos = json.loads(cfg.ruta_de_ejemplo().read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    assert isinstance(datos.get("proyectos"), list) and datos["proyectos"], "debe traer proyectos de muestra"
    assert "raiz_informes" in datos


def test_el_ejemplo_no_lleva_ninguna_ruta_real():
    texto = cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    for prohibido in PROHIBIDOS:
        assert prohibido not in texto, f"el ejemplo contiene una ruta real: {prohibido!r}"


# --- todo el repo ---


def test_el_repo_no_contiene_ninguna_ruta_real_de_nadie():
    este_fichero = os.path.abspath(__file__)
    ofensores = []
    for ruta in _ficheros_versionables():
        if os.path.abspath(ruta) == este_fichero:
            continue  # este fichero define los patrones; no se escanea a si mismo
        try:
            texto = open(ruta, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        for prohibido in PROHIBIDOS:
            if prohibido in texto:
                ofensores.append(f"{os.path.relpath(ruta, RAIZ)}: {prohibido!r}")
    assert not ofensores, "rutas reales en el repo:\n" + "\n".join(ofensores)
