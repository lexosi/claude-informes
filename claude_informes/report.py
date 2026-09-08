"""The JSON envelope and its writing to disk. One file per turn, always."""

from __future__ import annotations

import json
import os
import re
import subprocess
from datetime import datetime
from pathlib import Path

from . import __version__
from . import markdown as md

_PATRON_ORDINAL = re.compile(r"^(\d{2,})-")


def _git(cwd: str, *argumentos: str) -> str | None:
    """Query git, without noise and without hanging. None if it cannot."""
    try:
        salida = subprocess.run(
            ["git", *argumentos],
            cwd=cwd,
            capture_output=True,
            text=True,
            # git speaks utf-8; `text=True` on its own decodes with the console
            # encoding (cp1252 here): a branch with an accent came out as
            # mojibake, or blew up and both branch AND head were lost.
            encoding="utf-8",
            errors="replace",
            timeout=5,
            check=False,
        )
    except Exception:
        return None
    if salida.returncode != 0:
        return None
    valor = salida.stdout.strip()
    return valor or None


def datos_git(cwd: str) -> tuple[str | None, str | None]:
    if not cwd or not os.path.isdir(cwd):
        return None, None
    rama = _git(cwd, "rev-parse", "--abbrev-ref", "HEAD")
    head = _git(cwd, "rev-parse", "HEAD")
    return rama, head


def _momento(cuando: str | datetime | None) -> datetime:
    """Normalize to local time, TZ-AWARE. Accepts ISO-8601 (with or without Z).

    Tz-aware on purpose: the envelope's `instante` carries the offset so a
    consumer can compare timestamps across machines. `fecha`/`hora` are the same
    local wall-clock as before (a tz-aware `astimezone()` does not shift it), so
    those fields are unchanged; only a new, offset-bearing field is added.
    """
    if isinstance(cuando, datetime):
        instante = cuando
    elif isinstance(cuando, str) and cuando.strip():
        texto = cuando.strip().replace("Z", "+00:00")
        try:
            instante = datetime.fromisoformat(texto)
        except ValueError:
            return datetime.now().astimezone()
    else:
        return datetime.now().astimezone()
    # A naive datetime is assumed to be local; a tz-aware one is converted to local.
    return instante.astimezone()


# Envelope schema version. The consumer contract (see the README): a missing
# field OR version_esquema == 1 means v1, so the reports archived before this
# field existed stay valid as v1 without being rewritten. An incompatible change
# to the shape bumps this; a purely additive one does not.
VERSION_ESQUEMA = 1


def construir(
    respuesta_markdown: str,
    *,
    session_id: str | None,
    cwd: str | None,
    cuando: str | datetime | None = None,
    git_branch: str | None = None,
    git_head: str | None = None,
    proyecto: str | None = None,
    turno_uuid: str | None = None,
) -> dict:
    """The envelope. Its only requirement is to carry the full markdown.

    All the added fields are optional within schema v1 (see the README's
    contract): a consumer reads them if present and does not assume a fixed set.
    `turno_uuid` is OMITTED, not null, when there is no source uuid --the hook's
    Stop payload does not carry one; the backfill does. Absent means "this path
    does not provide it", which is not the same as a null "known to have none".
    """
    instante = _momento(cuando)
    sobre = {
        "version_esquema": VERSION_ESQUEMA,
        "version_herramienta": __version__,
        "instante": instante.isoformat(timespec="seconds"),
        "fecha": instante.strftime("%Y-%m-%d"),
        "hora": instante.strftime("%H:%M:%S"),
        "proyecto": proyecto,
        "session_id": session_id,
        "cwd": cwd,
        "git_branch": git_branch,
        "git_head": git_head,
    }
    if turno_uuid is not None:
        sobre["turno_uuid"] = turno_uuid
    sobre.update(
        {
            "respuesta_markdown": respuesta_markdown,
            "secciones": md.secciones(respuesta_markdown),
            "bloques_codigo": md.bloques_codigo(respuesta_markdown),
            "casillas": md.casillas(respuesta_markdown),
        }
    )
    return sobre


def subcarpeta(base: Path, nombre: str) -> Path:
    """Reuse the folder that already exists. Never a variant or a suffix.

    On Windows `Alfa` and `alfa` are the same folder; the one already on disk is
    returned so as not to end up with two separate histories.
    """
    buscado = os.path.normcase(nombre)
    try:
        for hijo in base.iterdir():
            if hijo.is_dir() and os.path.normcase(hijo.name) == buscado:
                return hijo
    except Exception:
        pass
    return base / nombre


def carpeta_del_dia(raiz_informes: Path, proyecto: str, fecha: str) -> Path:
    """`<root>/<project>/<AAAA-MM-DD>`, reusing the two levels."""
    return subcarpeta(subcarpeta(Path(raiz_informes), proyecto), fecha)


def _cuenta_para_el_ordinal(nombre: str) -> bool:
    """A `.json` already written, or a `.json.tmp` that has its ordinal taken.

    The `.tmp` files count because they are the lock: while one exists, its
    number is reserved. If they were not counted, two simultaneous turns would
    pick the same one, which is exactly what the lock prevents.
    """
    return nombre.endswith(".json") or nombre.endswith(".json.tmp")


def siguiente_ordinal(directorio: Path) -> int:
    """The ordinal starts at 01 in each day folder."""
    mayor = 0
    try:
        existentes = list(directorio.iterdir())
    except Exception:
        return 1
    for fichero in existentes:
        if not _cuenta_para_el_ordinal(fichero.name):
            continue
        m = _PATRON_ORDINAL.match(fichero.name)
        if m:
            mayor = max(mayor, int(m.group(1)))
    return mayor + 1


def nombre_de_fichero(directorio: Path, sobre: dict) -> Path:
    """`NN-slug.json`. No date or project: the path already provides them."""
    slug = md.nombre_desde_markdown(sobre["respuesta_markdown"])
    ordinal = siguiente_ordinal(directorio)
    while True:
        destino = directorio / f"{ordinal:02d}-{slug}.json"
        if not destino.exists():
            return destino
        ordinal += 1


def _reservar(directorio: Path, slug: str) -> Path:
    """Reserve a name by creating its `.tmp` exclusively. Returns the `.tmp`.

    The lock CANNOT be the destination file. When it was, any later failure --and
    a single character that did not fit in the encoding was enough-- left a
    zero-byte `.json` indistinguishable from a real report. The `.json` now
    appears only through the final `os.replace`.

    The guarantee is the same as always, no more and no less: two turns at once
    cannot take the SAME NAME, because whoever wins the O_EXCL keeps it and the
    other tries the next ordinal. For that to stay true, `siguiente_ordinal` also
    counts the `.tmp` files.

    The O_EXCL on the `.tmp` is NOT enough on its own: `os.replace` renames it to
    the final `.json` and frees its name, so a straggler turn that had picked
    that same ordinal before the release would win the O_EXCL again and its
    `os.replace` would clobber the already-written `.json` --silent data loss,
    with no exception--. The release of the `.tmp` and the appearance of the
    final `.json` are the SAME atomic `os.replace`: so, after winning the `.tmp`,
    if the `.json` of this ordinal already exists, the ordinal is taken; the
    `.tmp` is released and we move up. While we hold the `.tmp` (O_EXCL) nobody
    else can create that `.json`, so the check has no race window.
    """
    ordinal = siguiente_ordinal(directorio)
    for _ in range(1000):
        temporal = directorio / f"{ordinal:02d}-{slug}.json.tmp"
        try:
            descriptor = os.open(temporal, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except (FileExistsError, PermissionError):
            # FileExistsError: another turn holds that `.tmp`. PermissionError: on
            # Windows, a just-released `.tmp` stays in "pending delete" and its
            # name gives EACCES, not FileExistsError; in both cases the ordinal is
            # taken and the next one is tried. A directory truly without
            # permission exhausts the 1000 attempts and ends in the OSError below.
            ordinal += 1
            continue
        os.close(descriptor)
        if (directorio / f"{ordinal:02d}-{slug}.json").exists():
            os.unlink(temporal)
            ordinal += 1
            continue
        return temporal
    raise OSError(f"no free ordinal in {directorio}")


class FalloDeEscritura(Exception):
    """A report that never came to exist, and the name it was going to have.

    It carries the path so the log's ERROR line can say WHICH turn was lost.
    Without it the log only says that something failed, and `ultimo` has nothing
    to check against.
    """

    def __init__(self, ruta: Path, causa: BaseException) -> None:
        super().__init__(f"{type(causa).__name__}: {causa}")
        self.ruta = ruta
        self.causa = causa


def escribir(raiz_informes: Path, proyecto: str, sobre: dict) -> Path:
    """Create `<root>/<project>/<date>/` if missing and write the envelope.

    Order: the `.tmp` is reserved, it is written whole, and only then does the
    `.json` appear. If something fails along the way nothing is left on disk:
    neither a zero-byte report nor an orphan `.tmp`.

    The WHOLE body goes inside the try, `mkdir` and the reservation included:
    when they were outside, a permission failure while creating the folder came
    out raw instead of as `FalloDeEscritura`, and the hook's ERROR line lost the
    project, path and session --exactly the silent failure the design says it
    eliminates--. `destino` holds the best name known at each moment (the day
    folder until the `.tmp` is reserved), so the path identifies the turn even if
    the failure happens before the file is chosen.
    """
    directorio = carpeta_del_dia(Path(raiz_informes), proyecto, sobre["fecha"])
    destino: Path = directorio
    temporal: Path | None = None
    try:
        directorio.mkdir(parents=True, exist_ok=True)
        temporal = _reservar(directorio, md.nombre_desde_markdown(sobre["respuesta_markdown"]))
        destino = temporal.with_name(temporal.name[: -len(".tmp")])
        texto = json.dumps(sobre, ensure_ascii=False, indent=2) + "\n"
        # newline="\n": on Windows, write_text would convert the line breaks to
        # CRLF and the file would end up with two different formats depending on
        # who wrote it.
        temporal.write_text(texto, encoding="utf-8", newline="\n")
        os.replace(temporal, destino)
    except BaseException as error:
        if temporal is not None:
            try:
                temporal.unlink(missing_ok=True)
            except Exception:  # noqa: BLE001 - the original cause rules
                pass
        raise FalloDeEscritura(destino, error) from error
    return destino
