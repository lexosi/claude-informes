"""De donde sale el proyecto: de la SESION, no de donde este la shell.

El `cwd` del payload sigue a los `cd` que se hagan durante el turno. Archivar
por el falla en las dos direcciones: mete turnos de un proyecto no vigilado en
la carpeta de uno vigilado, y pierde turnos de uno vigilado cuando la shell se
ha ido. Un archivo del que no te puedes fiar no sirve de nada.
"""

import io
import json
from datetime import datetime
from pathlib import Path

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import registro as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def transcript_de(raiz_de_arranque):
    """Donde Claude Code pone el transcript de una sesion abierta ahi."""
    return str(
        Path("C:/proyectos") / tr.slug_de_cwd(str(raiz_de_arranque)) / "sesion.jsonl"
    )


def turno(cwd, transcript, texto=RESPUESTA):
    return {
        "session_id": "s",
        "cwd": str(cwd),
        "transcript_path": transcript,
        "stop_hook_active": False,
        "last_assistant_message": texto,
    }


def ejecutar(datos, ruta_config):
    return hk.main(entrada=io.StringIO(json.dumps(datos)), ruta_config=ruta_config)


def escritos(informes, proyecto, fecha=None):
    dia = Path(informes) / proyecto / (fecha or hoy())
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- el mapeo del slug al proyecto ---


def test_the_directory_slug_maps_to_the_name_declared_in_the_config(
    escribir_config, informes, tmp_path
):
    """`e--proyectos-alfa` -> `alfa`, via el cwd declarado."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "alfa", "cwd": "C:\\proyectos\\alfa"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\Users\\x\\.claude\\projects\\C--proyectos-alfa\\abc.jsonl"

    proyecto = hk.proyecto_del_transcript(ruta, configuracion)
    assert proyecto is not None and proyecto.nombre == "alfa"


def test_the_mapping_does_not_depend_on_the_directory_name_but_on_the_cwd(
    escribir_config, informes, tmp_path
):
    """El nombre de carpeta puede no parecerse al slug: manda el cwd."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "informes-del-curro", "cwd": "C:\\proyectos\\beta"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\C--proyectos-beta\\abc.jsonl"

    proyecto = hk.proyecto_del_transcript(ruta, configuracion)
    assert proyecto is not None and proyecto.nombre == "informes-del-curro"


def test_a_sibling_slug_is_not_mistaken_for_a_subdirectory(
    escribir_config, informes
):
    """`alfa-audit` es otro proyecto, no `alfa/audit`. Sin exactitud,
    no hay mapeo: el slug es ambiguo y no se intenta deshacer."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "alfa", "cwd": "C:\\proyectos\\alfa"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\C--proyectos-alfa-audit\\abc.jsonl"

    assert hk.proyecto_del_transcript(ruta, configuracion) is None


def test_a_deactivated_project_is_not_mapped(escribir_config, informes):
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "alfa", "cwd": "C:\\proyectos\\alfa", "activo": False}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\C--proyectos-alfa\\abc.jsonl"

    assert hk.proyecto_del_transcript(ruta, configuracion) is None


# --- el fallo original, en sus dos direcciones ---


def test_two_turns_with_a_different_cwd_go_to_the_same_project(
    escribir_config, informes, tmp_path, log
):
    """El caso real: entre turno y turno, la shell se movio."""
    raiz = tmp_path / "alfa"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(raiz)}], raiz_informes=informes
    )
    transcript = transcript_de(raiz)

    ejecutar(turno(raiz, transcript, RESPUESTA + "A"), ruta_config)
    ejecutar(turno(raiz / "subdir" / "hondo", transcript, RESPUESTA + "B"), ruta_config)
    ejecutar(turno("C:\\otro\\sitio\\del\\todo", transcript, RESPUESTA + "C"), ruta_config)

    assert len(escritos(informes, "alfa")) == 3
    assert [p.name for p in Path(informes).iterdir()] == ["alfa"]
    assert all(a.resultado == reg.ESCRITO for a in reg.leer(log))


def test_a_turn_from_an_unwatched_session_is_not_archived_even_when_the_cwd_is_watched(
    escribir_config, informes, tmp_path, log
):
    """La direccion peligrosa: la shell dentro de alfa, la sesion no."""
    vigilado = tmp_path / "alfa"
    vigilado.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(vigilado)}], raiz_informes=informes
    )

    datos = turno(vigilado, transcript_de(tmp_path / "proyectos"))
    assert ejecutar(datos, ruta_config) == 0

    assert not Path(informes).exists(), "la sesion manda sobre el cwd"
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert "proyecto no registrado" in anotacion.detalle


def test_a_turn_from_a_watched_session_is_not_lost_because_of_a_cd(
    escribir_config, informes, tmp_path
):
    """La otra direccion: la sesion en alfa, la shell fuera."""
    vigilado = tmp_path / "alfa"
    vigilado.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(vigilado)}], raiz_informes=informes
    )

    datos = turno("C:\\donde\\sea", transcript_de(vigilado))
    ejecutar(datos, ruta_config)

    assert len(escritos(informes, "alfa")) == 1


# --- camino degradado: cae al cwd, pero se ve ---


def test_without_a_transcript_path_it_falls_back_to_the_cwd_and_is_logged(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "alfa"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(turno(raiz, ""), ruta_config)

    assert len(escritos(informes, "alfa")) == 1, "se archiva igual"
    aviso, escrito = reg.leer(log)
    assert aviso.resultado == reg.PROYECTO_POR_CWD
    assert "sin transcript_path" in aviso.detalle
    assert str(raiz) in aviso.detalle
    assert escrito.resultado == reg.ESCRITO


def test_a_slug_that_does_not_map_does_not_archive_and_is_logged(
    escribir_config, informes, tmp_path, log
):
    """Con transcript, manda el transcript: no se cae al cwd.

    Caer al cwd aqui reabriria el agujero, porque una shell dentro de un
    proyecto vigilado volveria a archivar turnos de otra sesion.
    """
    raiz = tmp_path / "alfa"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(turno(raiz, "C:\\p\\slug-de-otra-cosa\\abc.jsonl"), ruta_config)

    assert not Path(informes).exists()
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert "slug-de-otra-cosa" in anotacion.detalle


def test_the_warning_only_appears_when_the_degraded_path_actually_archives(
    escribir_config, informes, tmp_path, log
):
    """Si el cwd tampoco vale, no hay nada que avisar: una sola linea."""
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(tmp_path / "alfa")}],
        raiz_informes=informes,
    )

    ejecutar(turno("C:\\nada\\que\\ver", ""), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_CWD


def test_an_unreadable_transcript_path_does_not_blow_up(escribir_config, informes, tmp_path):
    raiz = tmp_path / "alfa"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(raiz)}], raiz_informes=informes
    )

    for basura in [None, 42, [], "   "]:
        datos = turno(raiz, "x")
        datos["transcript_path"] = basura
        assert ejecutar(datos, ruta_config) == 0


# --- lo que no cambia ---


def test_a_turn_from_the_tool_itself_is_archived_like_any_other(
    escribir_config, informes
):
    """La herramienta dejo de ser un caso aparte cuando el archivo se mudo."""
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia)}], raiz_informes=informes
    )

    ejecutar(turno(propia, transcript_de(propia)), ruta_config)

    dia = Path(informes) / "claude-informes" / hoy()
    assert [p.name for p in dia.iterdir()] == ["01-informe-prueba-diaria.json"]


def test_the_threshold_stays_the_one_from_the_mapped_project(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "exigente"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "exigente", "cwd": str(raiz), "umbral_lineas": 20}],
        raiz_informes=informes,
    )

    ejecutar(turno("C:\\otro\\sitio", transcript_de(raiz)), ruta_config)

    assert not Path(informes).exists()
    assert reg.leer(log)[0].resultado == reg.OMITIDO_UMBRAL
