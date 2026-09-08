"""Where the project comes from: from the SESSION, not from where the shell is.

The payload's `cwd` follows the `cd`s done during the turn. Archiving by it
fails in both directions: it puts turns from an unwatched project into the
folder of a watched one, and loses turns from a watched one when the shell has
gone. An archive you can't trust is worthless.
"""

import io
import json
from datetime import datetime
from pathlib import Path

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import journal as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def transcript_de(raiz_de_arranque):
    """Where Claude Code puts the transcript of a session opened there."""
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


# --- the mapping from slug to project ---


def test_the_directory_slug_maps_to_the_name_declared_in_the_config(
    escribir_config, informes, tmp_path
):
    """`C--proyectos-alfa` -> `alfa`, via the declared cwd."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "alfa", "cwd": "C:\\proyectos\\alfa"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\C--proyectos-alfa\\abc.jsonl"

    proyecto = hk.proyecto_del_transcript(ruta, configuracion)
    assert proyecto is not None and proyecto.nombre == "alfa"


def test_the_mapping_does_not_depend_on_the_directory_name_but_on_the_cwd(
    escribir_config, informes, tmp_path
):
    """The folder name may not resemble the slug: the cwd rules."""
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
    """`alfa-audit` is another project, not `alfa/audit`. Without an exact
    match there is no mapping: the slug is ambiguous and no attempt is made to undo it."""
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


# --- the original bug, in its two directions ---


def test_two_turns_with_a_different_cwd_go_to_the_same_project(
    escribir_config, informes, tmp_path, log
):
    """The real case: between one turn and the next, the shell moved."""
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
    """The dangerous direction: the shell inside alfa, the session not."""
    vigilado = tmp_path / "alfa"
    vigilado.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(vigilado)}], raiz_informes=informes
    )

    datos = turno(vigilado, transcript_de(tmp_path / "proyectos"))
    assert ejecutar(datos, ruta_config) == 0

    assert not Path(informes).exists(), "the session rules over the cwd"
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert "proyecto no registrado" in anotacion.detalle


def test_a_turn_from_a_watched_session_is_not_lost_because_of_a_cd(
    escribir_config, informes, tmp_path
):
    """The other direction: the session in alfa, the shell outside."""
    vigilado = tmp_path / "alfa"
    vigilado.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(vigilado)}], raiz_informes=informes
    )

    datos = turno("C:\\donde\\sea", transcript_de(vigilado))
    ejecutar(datos, ruta_config)

    assert len(escritos(informes, "alfa")) == 1


# --- degraded path: falls back to the cwd, but it shows ---


def test_without_a_transcript_path_it_falls_back_to_the_cwd_and_is_logged(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "alfa"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "alfa", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(turno(raiz, ""), ruta_config)

    assert len(escritos(informes, "alfa")) == 1, "it is archived all the same"
    aviso, escrito = reg.leer(log)
    assert aviso.resultado == reg.PROYECTO_POR_CWD
    assert "sin transcript_path" in aviso.detalle
    assert str(raiz) in aviso.detalle
    assert escrito.resultado == reg.ESCRITO


def test_a_slug_that_does_not_map_does_not_archive_and_is_logged(
    escribir_config, informes, tmp_path, log
):
    """With a transcript, the transcript rules: it does not fall back to the cwd.

    Falling back to the cwd here would reopen the hole, because a shell inside
    a watched project would again archive turns from another session.
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
    """If the cwd is no good either, there is nothing to warn about: a single line."""
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


# --- what does not change ---


def test_a_turn_from_the_tool_itself_is_archived_like_any_other(
    escribir_config, informes
):
    """The tool stopped being a special case when the archiving moved."""
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
