"""Project whitelist and reading of the configuration."""

from pathlib import Path

from claude_informes import config as cfg


def test_only_projects_in_the_config_are_matched(escribir_config, tmp_path):
    dentro = tmp_path / "dentro"
    fuera = tmp_path / "fuera"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(dentro), "activo": True}]))

    assert cfg.buscar_proyecto(str(dentro), configuracion) is not None
    assert cfg.buscar_proyecto(str(fuera), configuracion) is None


def test_a_deactivated_project_is_not_matched(escribir_config, tmp_path):
    raiz = tmp_path / "pausado"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(raiz), "activo": False}]))
    assert cfg.buscar_proyecto(str(raiz), configuracion) is None


def test_subdirectories_of_the_project_are_matched(escribir_config, tmp_path):
    raiz = tmp_path / "repo"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(raiz), "activo": True}]))
    encontrado = cfg.buscar_proyecto(str(raiz / "src" / "hondo"), configuracion)
    assert encontrado is not None and encontrado.raiz == str(raiz)


def test_a_sibling_with_a_common_prefix_is_not_matched(escribir_config, tmp_path):
    raiz = tmp_path / "repo"
    hermano = tmp_path / "repo-otro"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(raiz), "activo": True}]))
    assert cfg.buscar_proyecto(str(hermano), configuracion) is None


def test_the_most_specific_root_wins(escribir_config, tmp_path):
    padre = tmp_path / "monorepo"
    hijo = padre / "paquetes" / "uno"
    configuracion = cfg.cargar(
        escribir_config(
            [
                {"nombre": "padre", "cwd": str(padre), "activo": True},
                {"nombre": "hijo", "cwd": str(hijo), "activo": True},
            ]
        )
    )
    encontrado = cfg.buscar_proyecto(str(hijo), configuracion)
    assert encontrado is not None and encontrado.nombre == "hijo"


def test_an_absent_or_nonsensical_cwd_is_not_matched(escribir_config, tmp_path):
    configuracion = cfg.cargar(
        escribir_config([{"cwd": str(tmp_path / "x"), "activo": True}])
    )
    assert cfg.buscar_proyecto(None, configuracion) is None
    assert cfg.buscar_proyecto("", configuracion) is None
    assert cfg.buscar_proyecto("   ", configuracion) is None


def test_a_nonexistent_config_leaves_no_projects(tmp_path):
    assert cfg.cargar(tmp_path / "no-existe.json").proyectos == []


def test_a_broken_config_leaves_no_projects(tmp_path):
    ruta = tmp_path / "rota.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cfg.cargar(ruta).proyectos == []


def test_junk_entries_are_discarded_one_by_one(escribir_config, tmp_path):
    buena = tmp_path / "buena"
    configuracion = cfg.cargar(
        escribir_config(["no soy un objeto", {"activo": True}, {"cwd": str(buena)}])
    )
    assert [p.raiz for p in configuracion.proyectos] == [str(buena)]


def test_default_values_are_applied(escribir_config, tmp_path):
    configuracion = cfg.cargar(escribir_config([{"cwd": str(tmp_path / "r")}]))
    assert configuracion.proyectos[0].activo is True
    assert configuracion.proyectos[0].umbral_lineas == 5


def test_an_invalid_threshold_falls_back_to_the_default(escribir_config, tmp_path):
    configuracion = cfg.cargar(
        escribir_config([{"cwd": str(tmp_path / "r"), "umbral_lineas": "muchas"}])
    )
    assert configuracion.proyectos[0].umbral_lineas == 5


# --- the project name ---


def test_the_name_comes_from_the_config_not_from_the_directory(escribir_config, tmp_path):
    """A directory rename must not break the history."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "alfa", "cwd": str(tmp_path / "alfa-renombrado")}]
        )
    )
    assert configuracion.proyectos[0].nombre == "alfa"


def test_without_a_name_the_directory_name_is_used(escribir_config, tmp_path):
    configuracion = cfg.cargar(escribir_config([{"cwd": str(tmp_path / "Mi Repo")}]))
    assert configuracion.proyectos[0].nombre == "mi-repo"


# --- reports root ---


def test_the_reports_root_comes_from_the_config(escribir_config, tmp_path):
    destino = tmp_path / "archivo"
    configuracion = cfg.cargar(escribir_config([], raiz_informes=destino))
    assert configuracion.raiz_informes == destino


def test_without_a_declared_root_the_tools_own_root_is_used(escribir_config, tmp_path):
    configuracion = cfg.cargar(escribir_config([{"cwd": str(tmp_path)}]))
    assert configuracion.raiz_informes == cfg.raiz_de_la_herramienta() / "informes"


def test_the_default_root_lives_inside_the_tool():
    assert cfg.raiz_informes_por_defecto().parent == cfg.raiz_de_la_herramienta()


# --- the tool itself: one more project ---


def test_claude_informes_itself_can_be_a_watched_project(escribir_config):
    """The guard that prevented it was removed along with its reason.

    While the archive lived inside `claude-informes/informes/`, a turn
    of its own would have written into its own output folder. With the archive in a
    root of its own outside every repo, all the guard did was throw away
    the turns of whoever worked on the tool.
    """
    propia = cfg.raiz_de_la_herramienta()
    configuracion = cfg.cargar(
        escribir_config([{"nombre": "claude-informes", "cwd": str(propia)}])
    )
    encontrado = cfg.buscar_proyecto(str(propia), configuracion)
    assert encontrado is not None
    assert encontrado.nombre == "claude-informes"


def test_a_subdirectory_of_the_tool_also_maps(escribir_config):
    propia = cfg.raiz_de_la_herramienta()
    configuracion = cfg.cargar(escribir_config([{"cwd": str(propia)}]))
    assert cfg.buscar_proyecto(str(propia / "claude_informes"), configuracion) is not None
    assert cfg.buscar_proyecto(str(propia / "tests"), configuracion) is not None


# The tests that asserted about "the repo's real config" were removed: the
# real config no longer lives in the repository (it lives in the OS user
# config). The equivalent invariant -that the EXAMPLE is valid JSON and carries no
# real paths, and that the archive falls outside every repo- is now checked
# in test_publicable.py and test_config_ubicacion.py.


# --- per-project root ---


def test_the_per_project_root_overrides_the_global_one(escribir_config, tmp_path):
    suya = tmp_path / "aparte"
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "beta", "cwd": str(tmp_path / "co"), "raiz_informes": suya}],
            raiz_informes=tmp_path / "comun",
        )
    )
    assert configuracion.raiz_informes == tmp_path / "comun"
    assert configuracion.proyectos[0].raiz_informes == suya


def test_without_its_own_root_the_project_inherits_the_global_one(escribir_config, tmp_path):
    comun = tmp_path / "comun"
    configuracion = cfg.cargar(
        escribir_config([{"nombre": "alfa", "cwd": str(tmp_path / "lw")}], raiz_informes=comun)
    )
    assert configuracion.proyectos[0].raiz_informes == comun


def test_each_project_can_go_to_a_different_root(escribir_config, tmp_path):
    configuracion = cfg.cargar(
        escribir_config(
            [
                {"nombre": "publico", "cwd": str(tmp_path / "a")},
                {"nombre": "sensible", "cwd": str(tmp_path / "b"), "raiz_informes": tmp_path / "cofre"},
            ],
            raiz_informes=tmp_path / "comun",
        )
    )
    por_raiz = {p.nombre: p.raiz_informes for p in configuracion.proyectos}
    assert por_raiz["publico"] == tmp_path / "comun"
    assert por_raiz["sensible"] == tmp_path / "cofre"


def test_an_invalid_per_project_root_falls_back_to_the_global_one(escribir_config, tmp_path):
    comun = tmp_path / "comun"
    configuracion = cfg.cargar(
        escribir_config(
            [{"cwd": str(tmp_path / "x"), "raiz_informes": "   "}], raiz_informes=comun
        )
    )
    assert configuracion.proyectos[0].raiz_informes == comun


