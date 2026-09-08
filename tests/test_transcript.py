"""Reading the transcript, and telling APART the three ways it can be empty.

The old code returned a bare ``[]`` for an unreadable file, a session with no
turn, and a format that drifted --three very different things collapsed into one
silent value. ``leer()`` separates them (LEIDO / VACIO / DERIVA / ILEGIBLE) so a
format drift does not look like an empty session -- otherwise a drift returns
``[]`` and the hook stops archiving in silence.
"""

import json
from pathlib import Path

from claude_informes import transcript as tr

FIXTURE = Path(__file__).parent / "fixtures" / "transcript_real_recortado.jsonl"


def _escribir(tmp_path, registros):
    ruta = tmp_path / "s.jsonl"
    ruta.write_text("\n".join(json.dumps(r) for r in registros) + "\n", encoding="utf-8")
    return ruta


def test_a_real_shaped_transcript_yields_only_the_closed_turns():
    """The fixture carries the exotic line types a REAL transcript has
    (bridge-session, ai-title, atis-latch, last-prompt, attachment,
    file-history-snapshot) plus a tool_use assistant line that is not a closed
    turn. Only the two end_turn assistant turns come out; the rest is skipped.
    """
    lectura = tr.leer(FIXTURE)
    assert lectura.estado == tr.LEIDO
    assert [t["uuid"] for t in lectura.turnos] == ["u-101", "u-102"]
    assert lectura.turnos[0]["respuesta_markdown"].startswith("# Primer turno")
    assert lectura.arranque == "C:/proyectos/demo"  # first cwd, not the later sub
    assert lectura.lineas_asistente == 3            # includes the tool_use line


def test_a_readable_transcript_with_no_assistant_line_is_vacio(tmp_path):
    ruta = _escribir(tmp_path, [{"type": "user", "cwd": "C:/proyectos/demo", "message": {"content": "hola"}}])
    lectura = tr.leer(ruta)
    assert lectura.estado == tr.VACIO
    assert lectura.turnos == []
    assert lectura.arranque == "C:/proyectos/demo"


def test_assistant_lines_that_yield_no_turn_are_deriva(tmp_path):
    """The format drifted: ``stop_reason`` was renamed, so end_turn is never seen
    and every assistant line is skipped -- but there ARE assistant lines, which
    is what tells this apart from a legitimately empty session.
    """
    ruta = _escribir(tmp_path, [
        {"type": "user", "cwd": "C:/proyectos/demo", "message": {"content": "hola"}},
        {"type": "assistant", "message": {"stopReason": "end_turn", "content": [{"type": "text", "text": "# t\n\na\nb\nc\nd\n"}]}},
        {"type": "assistant", "message": {"stopReason": "end_turn", "content": [{"type": "text", "text": "# u\n\ne\nf\ng\nh\n"}]}},
    ])
    lectura = tr.leer(ruta)
    assert lectura.estado == tr.DERIVA
    assert lectura.turnos == []
    assert lectura.lineas_asistente == 2


def test_an_unreadable_transcript_is_ilegible(tmp_path):
    lectura = tr.leer(tmp_path / "no-existe.jsonl")
    assert lectura.estado == tr.ILEGIBLE
    assert lectura.turnos == []
    assert lectura.detalle  # carries the error type, for the log


def test_the_three_empty_states_are_distinct(tmp_path):
    """What the old code collapsed into one silent []: the three empty states."""
    vacio = tr.leer(_escribir(tmp_path, [{"type": "user", "message": {}}]))
    deriva_reg = [{"type": "assistant", "message": {"stopReason": "end_turn", "content": [{"type": "text", "text": "x\ny\nz\n1\n2\n3\n"}]}}]
    otra = tmp_path / "otra.jsonl"
    otra.write_text(json.dumps(deriva_reg[0]) + "\n", encoding="utf-8")
    deriva = tr.leer(otra)
    ilegible = tr.leer(tmp_path / "no.jsonl")
    assert {vacio.estado, deriva.estado, ilegible.estado} == {tr.VACIO, tr.DERIVA, tr.ILEGIBLE}
    # ...yet the compatibility wrapper flattens all three back to []
    assert tr.turnos(tmp_path / "no.jsonl") == []


def test_turnos_is_the_turns_of_leer():
    assert tr.turnos(FIXTURE) == tr.leer(FIXTURE).turnos
