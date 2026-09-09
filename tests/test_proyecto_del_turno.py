"""Which project a turn belongs to, under the watched-roots model.

The project comes from where the session STARTS, not from the directory the
shell wanders into during the turn. The startup directory is read from the
transcript (its first record), so here the transcript is a real file, as in
production; its startup cwd is resolved against the watched roots.

The pure resolution rule (segment below a root, most-specific match, borders)
lives in test_resolution.py. This file checks the HOOK's behavior around it:
which label reaches the log, the degraded no-transcript fallback, and that an
unreadable or drifted transcript is told apart from a startup outside the roots.
"""

import io
import json
import tempfile
from datetime import datetime
from pathlib import Path

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import journal as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"

_TRANSCRIPTS = Path(tempfile.mkdtemp(prefix="ci-pdt-transcripts-"))


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def transcript_real(cwd, *, deriva=False):
    """A real transcript for a session started in `cwd`.

    With `deriva`, it carries an assistant line that does NOT produce a turn (a
    renamed `stop_reason`), which is the format-drift case.
    """
    destino = _TRANSCRIPTS / tr.slug_de_cwd(str(cwd)) / "s.jsonl"
    destino.parent.mkdir(parents=True, exist_ok=True)
    lineas = [json.dumps({"type": "user", "cwd": str(cwd)})]
    if deriva:
        lineas.append(
            json.dumps(
                {
                    "type": "assistant",
                    "message": {
                        "stopReason": "end_turn",  # renamed -> never recognized as a turn
                        "content": [{"type": "text", "text": "# t\n\na\nb\nc\nd\n"}],
                    },
                }
            )
        )
    destino.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return str(destino)


def turno(cwd, transcript=None, texto=RESPUESTA):
    return {
        "session_id": "s",
        "cwd": str(cwd),
        "transcript_path": transcript if transcript is not None else transcript_real(cwd),
        "stop_hook_active": False,
        "last_assistant_message": texto,
    }


def ejecutar(datos, ruta_config):
    return hk.main(entrada=io.StringIO(json.dumps(datos)), ruta_config=ruta_config)


def escritos(informes, proyecto, fecha=None):
    dia = Path(informes) / proyecto / (fecha or hoy())
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


def config_con_raiz(escribir_config, informes, raiz, **kwargs):
    return escribir_config([], raiz_informes=informes, roots=[raiz], **kwargs)


# --- the original bug, in its two directions ---


def test_two_turns_with_a_different_cwd_go_to_the_same_project(
    escribir_config, informes, tmp_path, log
):
    """The real case: between one turn and the next, the shell moved. The session
    (its startup) is what decides the project, so all three land in `alfa`."""
    raiz = tmp_path / "work"
    (raiz / "alfa").mkdir(parents=True)
    ruta_config = config_con_raiz(escribir_config, informes, raiz)
    transcript = transcript_real(raiz / "alfa")

    ejecutar(turno(raiz / "alfa", transcript, RESPUESTA + "A"), ruta_config)
    ejecutar(turno(raiz / "alfa" / "sub" / "deep", transcript, RESPUESTA + "B"), ruta_config)
    ejecutar(turno("C:\\otro\\sitio\\del\\todo", transcript, RESPUESTA + "C"), ruta_config)

    assert len(escritos(informes, "alfa")) == 3
    assert [p.name for p in Path(informes).iterdir()] == ["alfa"]
    assert all(a.resultado == reg.ESCRITO for a in reg.leer(log))


def test_a_turn_from_a_watched_session_is_not_lost_because_of_a_cd(
    escribir_config, informes, tmp_path
):
    """The session starts under the root; the shell has wandered out. Archived."""
    raiz = tmp_path / "work"
    (raiz / "alfa").mkdir(parents=True)
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    ejecutar(turno("C:\\donde\\sea", transcript_real(raiz / "alfa")), ruta_config)

    assert len(escritos(informes, "alfa")) == 1


def test_a_turn_whose_startup_is_outside_the_roots_is_not_archived(
    escribir_config, informes, tmp_path, log
):
    """The dangerous direction: the shell inside a watched root, the session not."""
    raiz = tmp_path / "work"
    raiz.mkdir()
    ajeno = tmp_path / "ajeno"
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    # payload cwd is inside the watched root, but the SESSION started in `ajeno`
    ejecutar(turno(raiz / "alfa", transcript_real(ajeno)), ruta_config)

    assert not Path(informes).exists(), "the session rules over the cwd"
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.FUERA_DE_RAICES
    assert str(ajeno) in anotacion.detalle


# --- the three distinct no-project labels ---


def test_a_startup_at_a_bare_root_is_logged_as_bare_root(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "work"
    raiz.mkdir()
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    ejecutar(turno(raiz, transcript_real(raiz)), ruta_config)

    assert not Path(informes).exists()
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.RAIZ_DESNUDA


def test_a_startup_in_an_excluded_project_is_logged_as_excluded(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "work"
    (raiz / "alfa-audit").mkdir(parents=True)
    ruta_config = config_con_raiz(escribir_config, informes, raiz, exclusions=["*-audit*"])

    ejecutar(turno(raiz / "alfa-audit", transcript_real(raiz / "alfa-audit")), ruta_config)

    assert not Path(informes).exists()
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.EXCLUIDO_PATRON


# --- degraded path: no transcript, falls back to the cwd, but it shows ---


def test_without_a_transcript_path_it_falls_back_to_the_cwd_and_is_logged(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "work"
    (raiz / "alfa").mkdir(parents=True)
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    ejecutar(turno(raiz / "alfa", transcript=""), ruta_config)

    assert len(escritos(informes, "alfa")) == 1, "it is archived all the same"
    aviso, escrito = reg.leer(log)
    assert aviso.resultado == reg.PROYECTO_POR_CWD
    assert "sin transcript_path" in aviso.detalle
    assert escrito.resultado == reg.ESCRITO


def test_the_warning_only_appears_when_the_degraded_path_actually_archives(
    escribir_config, informes, tmp_path, log
):
    """If the cwd is no good either, there is nothing to warn about: a single line."""
    raiz = tmp_path / "work"
    raiz.mkdir()
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    ejecutar(turno("C:\\nada\\que\\ver", transcript=""), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_CWD


def test_an_unreadable_transcript_path_does_not_blow_up(escribir_config, informes, tmp_path):
    raiz = tmp_path / "work"
    (raiz / "alfa").mkdir(parents=True)
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    for basura in [None, 42, [], "   "]:
        datos = turno(raiz / "alfa")
        datos["transcript_path"] = basura
        assert ejecutar(datos, ruta_config) == 0


# --- a wrong label is worse than no label: the log is the only way to find out ---


def test_an_unreadable_transcript_is_logged_as_ilegible_not_outside(
    escribir_config, informes, tmp_path, log
):
    """A transcript that cannot be read is not 'outside the roots'. Logging
    FUERA_DE_RAICES here would be a lie in the one place meant to catch it."""
    raiz = tmp_path / "work"
    raiz.mkdir()
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    # a transcript path that does not exist -> ILEGIBLE
    ejecutar(turno(raiz / "alfa", str(tmp_path / "no" / "existe.jsonl")), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.TRANSCRIPT_ILEGIBLE
    assert anotacion.resultado != reg.FUERA_DE_RAICES


def test_a_drifted_transcript_is_logged_as_drift(
    escribir_config, informes, tmp_path, log
):
    """Assistant lines but no extractable turn while resolving the project: the
    format drifted. Logged as drift, not as 'outside the roots'."""
    raiz = tmp_path / "work"
    raiz.mkdir()
    ruta_config = config_con_raiz(escribir_config, informes, raiz)

    ejecutar(turno(raiz / "alfa", transcript_real(tmp_path / "x", deriva=True)), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.DERIVA_FORMATO


def test_a_resolved_turn_whose_transcript_drifted_is_drift_not_no_text(
    escribir_config, informes, tmp_path, log
):
    """The startup resolves, but there is no `last_assistant_message` and the
    fallback to the transcript hits a drift: logged as drift, not 'no text'."""
    raiz = tmp_path / "work"
    (raiz / "alfa").mkdir(parents=True)
    ruta_config = config_con_raiz(escribir_config, informes, raiz)
    transcripcion = transcript_real(raiz / "alfa", deriva=True)
    datos = {
        "session_id": "s",
        "cwd": str(raiz / "alfa"),
        "transcript_path": transcripcion,
        "stop_hook_active": False,
        # no last_assistant_message on purpose: forces the transcript fallback
    }

    ejecutar(datos, ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.DERIVA_FORMATO


# --- what does not change ---


def test_a_turn_from_the_tool_itself_is_archived_like_any_other(
    escribir_config, informes, tmp_path
):
    """The tool is a project like any other: declared as its own project root."""
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia)}], raiz_informes=informes
    )

    ejecutar(turno(propia, transcript_real(propia)), ruta_config)

    dia = Path(informes) / "claude-informes" / hoy()
    assert [p.name for p in dia.iterdir()] == ["01-informe-prueba-diaria.json"]


def test_the_threshold_comes_from_an_explicit_project_entry(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "exigente"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "exigente", "cwd": str(raiz), "umbral_lineas": 20}],
        raiz_informes=informes,
    )

    ejecutar(turno(raiz, transcript_real(raiz)), ruta_config)

    assert not Path(informes).exists()
    assert reg.leer(log)[0].resultado == reg.OMITIDO_UMBRAL
