"""The process's encoding boundaries. Explicit utf-8, always.

Python on Windows opens `sys.stdin` and `sys.stdout` with the console encoding
--cp1252 here-- and with `errors='surrogateescape'`. Neither of the two is
declared anywhere: they are inherited. Claude Code delivers and expects utf-8.

What that caused:

- Every non-ASCII character arrived split in two. `ó` (utf-8 C3 B3) was read as
  `Ã` + `³`, and from there the mojibake in the archived names and markdown.
- cp1252 has five unassigned holes: 0x81 0x8D 0x8F 0x90 0x9D. A character whose
  utf-8 lands on one of them --`Á` (C3 81), `Í` (C3 8D), `❌` (E2 9D 8C), `←`
  (E2 86 90)-- left a stray surrogate that blew up a hundred lines later, when
  writing the report in utf-8.

That is why the input is read as BYTES and decoded by hand, and the output is
written as BYTES. No stream in this project inherits its encoding.
"""

from __future__ import annotations

import json


def leer_payload(flujo) -> dict:
    """The hook's payload, decoded as utf-8 whatever it comes as.

    If the stream has `.buffer` --`sys.stdin` does-- the raw bytes are read. An
    in-memory text stream does not have it, and then it already comes decoded by
    whoever built it.
    """
    crudo = getattr(flujo, "buffer", None)
    if crudo is None:
        return json.loads(flujo.read())
    return json.loads(crudo.read().decode("utf-8"))


def escribir(flujo, texto: str) -> None:
    """Write in utf-8, without going through the stream's inherited encoding.

    It matters more than it seems: the guardian returns its denial through here.
    With cp1252, a path with a character that did not fit blew up the `write`,
    the guardian fell to its `except`, and **allowed** the write it was supposed
    to deny. Failing open through an encoding fault of its own is not failing
    open: it is not being there.
    """
    crudo = getattr(flujo, "buffer", None)
    if crudo is None:
        flujo.write(texto)
        return
    flujo.flush()
    crudo.write(texto.encode("utf-8"))
    crudo.flush()


def salida_en_utf8(*flujos) -> None:
    """Put the output streams in utf-8. For the CLI, which prints paths.

    `errors='replace'` on purpose: a strange name coming out as a question mark
    is better than a `UnicodeEncodeError` in the middle of a results report.
    """
    for flujo in flujos:
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is None:
            continue
        try:
            reconfigurar(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - a redirected stream may not allow it
            pass
