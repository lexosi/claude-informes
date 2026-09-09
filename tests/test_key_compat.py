"""Config keys: English is the valid form; the Castilian keys are transitional
compatibility aliases, slated for removal in 2.0.0.

Loading either spelling must give the same configuration. When both spellings
appear on one object, the English one wins and the alias is dropped.
"""

import json
from pathlib import Path

from claude_informes import config as cfg


def escribir(tmp_path, obj):
    ruta = tmp_path / "c.json"
    ruta.write_text(json.dumps(obj, ensure_ascii=False), encoding="utf-8")
    return ruta


def test_english_keys_load_a_project_with_its_overrides(tmp_path):
    proj = tmp_path / "alfa"
    aparte = tmp_path / "privado"
    ruta = escribir(
        tmp_path,
        {
            "reports_root": str(tmp_path / "archivo"),
            "log_path": str(tmp_path / "hook.log"),
            "roots": [str(tmp_path / "proyectos")],
            "exclusions": ["*-audit*"],
            "projects": [
                {"name": "alfa", "path": str(proj), "line_threshold": 7, "reports_root": str(aparte)}
            ],
        },
    )

    configuracion = cfg.cargar(ruta)

    assert configuracion.raiz_informes == tmp_path / "archivo"
    assert configuracion.ruta_log == tmp_path / "hook.log"
    assert configuracion.roots == [str(tmp_path / "proyectos")]
    assert configuracion.exclusions == ["*-audit*"]
    (proyecto,) = configuracion.proyectos
    assert proyecto.nombre == "alfa"
    assert proyecto.raiz == str(Path(proj))
    assert proyecto.umbral_lineas == 7
    assert proyecto.raiz_informes == aparte


def test_castilian_keys_still_load_the_same_project(tmp_path):
    proj = tmp_path / "alfa"
    aparte = tmp_path / "privado"
    ruta = escribir(
        tmp_path,
        {
            "raiz_informes": str(tmp_path / "archivo"),
            "ruta_log": str(tmp_path / "hook.log"),
            "proyectos": [
                {"nombre": "alfa", "cwd": str(proj), "umbral_lineas": 7, "raiz_informes": str(aparte)}
            ],
        },
    )

    configuracion = cfg.cargar(ruta)

    assert configuracion.raiz_informes == tmp_path / "archivo"
    assert configuracion.ruta_log == tmp_path / "hook.log"
    (proyecto,) = configuracion.proyectos
    assert proyecto.nombre == "alfa"
    assert proyecto.raiz == str(Path(proj))
    assert proyecto.umbral_lineas == 7
    assert proyecto.raiz_informes == aparte


def test_english_wins_when_both_spellings_are_present(tmp_path):
    ruta = escribir(
        tmp_path,
        {
            "reports_root": str(tmp_path / "eng"),
            "raiz_informes": str(tmp_path / "esp"),
            "projects": [{"name": "eng", "nombre": "esp", "path": str(tmp_path / "p")}],
            "proyectos": [{"name": "ignored", "path": str(tmp_path / "q")}],
        },
    )

    configuracion = cfg.cargar(ruta)

    assert configuracion.raiz_informes == tmp_path / "eng"
    (proyecto,) = configuracion.proyectos
    assert proyecto.nombre == "eng"


def test_cwd_and_raiz_both_map_to_path_with_cwd_first(tmp_path):
    ruta = escribir(
        tmp_path,
        {"proyectos": [{"nombre": "a", "cwd": str(tmp_path / "uno"), "raiz": str(tmp_path / "dos")}]},
    )

    (proyecto,) = cfg.cargar(ruta).proyectos

    assert proyecto.raiz == str(Path(tmp_path / "uno"))
