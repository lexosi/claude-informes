"""The project a session belongs to, under the watched-roots model.

The config declares WHERE to watch (`roots`, whose children are projects) and,
optionally, explicit project roots with overrides (`projects`). One rule,
most-specific match, resolves every case -- there is no leaf/container flag.

These tests create REAL directories under tmp_path, because the resolver uses
`os.path.realpath`: the on-disk casing is what gives a project its folder name,
and a junction only resolves against something that exists.
"""

import os

import pytest

from claude_informes import config as cfg
from claude_informes import journal as reg
from claude_informes import resolution as res


def load(ruta):
    return cfg.cargar(ruta)


def test_project_is_first_segment_below_the_root(escribir_config, informes, tmp_path):
    root = tmp_path / "proyectos"
    (root / "alfa" / "src" / "lib").mkdir(parents=True)
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, etiqueta = res.resolver_proyecto(
        str(root / "alfa" / "src" / "lib"), configuracion
    )

    assert etiqueta == ""
    assert proyecto.nombre == "alfa"
    assert proyecto.raiz_informes == informes
    assert proyecto.umbral_lineas == cfg.UMBRAL_POR_DEFECTO


def test_nested_roots_most_specific_wins(escribir_config, informes, tmp_path):
    outer = tmp_path / "proyectos"
    inner = outer / "clientes"
    (inner / "acme" / "src").mkdir(parents=True)
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[outer, inner]))

    proyecto, _ = res.resolver_proyecto(str(inner / "acme" / "src"), configuracion)

    assert proyecto.nombre == "acme"


def test_explicit_project_root_wins_over_the_container_and_carries_overrides(
    escribir_config, informes, tmp_path
):
    """Border (d): a project root is longer than the container it hangs off, so
    it wins by the same most-specific rule -- no special case. Its overrides apply."""
    container = tmp_path / "proyectos"
    proj = container / "alfa"
    (proj / "src").mkdir(parents=True)
    aparte = tmp_path / "privado"
    configuracion = load(
        escribir_config(
            [{"nombre": "alfa-pinned", "cwd": str(proj), "umbral_lineas": 20, "raiz_informes": aparte}],
            raiz_informes=informes,
            roots=[container],
        )
    )

    proyecto, _ = res.resolver_proyecto(str(proj / "src"), configuracion)

    assert proyecto.nombre == "alfa-pinned"
    assert proyecto.umbral_lineas == 20
    assert proyecto.raiz_informes == aparte


def test_a_project_root_names_a_standalone_subtree(escribir_config, informes, tmp_path):
    """Border (d), the standalone-tool case: any session inside it is that one
    project, whatever its depth -- the root IS the project, with no flag."""
    mas = tmp_path / "standalone-tool"
    (mas / "docs" / "deep").mkdir(parents=True)
    configuracion = load(
        escribir_config([{"nombre": "standalone-tool", "cwd": str(mas)}], raiz_informes=informes)
    )

    proyecto, _ = res.resolver_proyecto(str(mas / "docs" / "deep"), configuracion)

    assert proyecto.nombre == "standalone-tool"


def test_startup_at_the_root_itself_has_no_project(escribir_config, informes, tmp_path):
    """Border (a): the startup IS a watched container, there is no segment below."""
    root = tmp_path / "proyectos"
    root.mkdir()
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, etiqueta = res.resolver_proyecto(str(root), configuracion)

    assert proyecto is None
    assert etiqueta == reg.RAIZ_DESNUDA


def test_startup_outside_all_roots(escribir_config, informes, tmp_path):
    root = tmp_path / "proyectos"
    root.mkdir()
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, etiqueta = res.resolver_proyecto(str(tmp_path / "otra-cosa" / "x"), configuracion)

    assert proyecto is None
    assert etiqueta == reg.FUERA_DE_RAICES


def test_the_folder_name_is_the_raw_basename_not_a_slug(escribir_config, informes, tmp_path):
    """Border: a directory name is already a valid folder name; slugging a valid
    name only introduces collisions where there were none."""
    root = tmp_path / "proyectos"
    (root / "My Project").mkdir(parents=True)
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, _ = res.resolver_proyecto(str(root / "My Project" / "x"), configuracion)

    assert proyecto.nombre == "My Project"


@pytest.mark.skipif(
    os.path.normcase("A") == "A", reason="only a case-insensitive filesystem unifies the casings"
)
def test_case_insensitive_root_yields_one_project(escribir_config, informes, tmp_path):
    """Border (e): the startup typed in another casing resolves to the same project,
    and the folder takes the real on-disk casing."""
    root = tmp_path / "proyectos"
    (root / "Alfa").mkdir(parents=True)
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, _ = res.resolver_proyecto(str(root) + os.sep + "alfa" + os.sep + "src", configuracion)

    assert proyecto.nombre == "Alfa"


def test_a_junction_is_resolved_before_matching(escribir_config, informes, tmp_path):
    """Border (f): a link into a watched root resolves to the real project."""
    real = tmp_path / "proyectos"
    (real / "alfa").mkdir(parents=True)
    enlace = tmp_path / "enlace"
    try:
        os.symlink(real, enlace, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("this environment does not allow creating symlinks")
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[real]))

    proyecto, _ = res.resolver_proyecto(str(enlace / "alfa" / "src"), configuracion)

    assert proyecto.nombre == "alfa"


def test_a_root_that_is_also_a_repo_archives_normally(escribir_config, informes, tmp_path):
    """Border (c): a project that is a git repo is resolved like any other; the
    guardian, not the resolver, is what keeps the archive out of a repo."""
    root = tmp_path / "proyectos"
    proj = root / "alfa"
    (proj / ".git").mkdir(parents=True)
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, _ = res.resolver_proyecto(str(proj / "src"), configuracion)

    assert proyecto.nombre == "alfa"


def test_an_excluded_glob_is_not_archived(escribir_config, informes, tmp_path):
    root = tmp_path / "proyectos"
    (root / "alfa-audit").mkdir(parents=True)
    configuracion = load(
        escribir_config([], raiz_informes=informes, roots=[root], exclusions=["*-audit*"])
    )

    proyecto, etiqueta = res.resolver_proyecto(
        str(root / "alfa-audit" / "src"), configuracion
    )

    assert proyecto is None
    assert etiqueta == reg.EXCLUIDO_PATRON


def test_a_discovered_project_inherits_the_global_report_root(escribir_config, informes, tmp_path):
    root = tmp_path / "proyectos"
    (root / "beta").mkdir(parents=True)
    configuracion = load(escribir_config([], raiz_informes=informes, roots=[root]))

    proyecto, _ = res.resolver_proyecto(str(root / "beta"), configuracion)

    assert proyecto.raiz_informes == informes
    assert proyecto.umbral_lineas == cfg.UMBRAL_POR_DEFECTO


def test_a_legacy_entry_without_roots_behaves_as_a_project_root(
    escribir_config, informes, tmp_path
):
    """Compat: a config with the old `proyectos`/`cwd` and no `roots` treats each
    entry as an explicit project root -- same result the watched-roots model gives."""
    proj = tmp_path / "alfa"
    (proj / "src").mkdir(parents=True)
    configuracion = load(escribir_config([{"nombre": "alfa", "cwd": str(proj)}], raiz_informes=informes))

    proyecto, _ = res.resolver_proyecto(str(proj / "src"), configuracion)

    assert proyecto.nombre == "alfa"
