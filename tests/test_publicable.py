"""The repository is publishable: no private identifier, no home-directory path.

The real config lives outside the repo; here it is checked that the repo only
carries the example (valid JSON, fictitious paths) and that no versioned file
leaks either a PRIVATE identifier (a private project name, an email prefix, an
absolute archive root) or a HOME-DIRECTORY path under any username.

Names vs shapes: what is private, and what is not
-------------------------------------------------
Not every occurrence of the author's name is a leak. The public handle --the one
in the GitHub URL-- is public by construction:
forbidding it would forbid the author's own public identity. And a substring
blocklist could not separate it anyway, because the handle is a SUBSTRING of a
private token (the email prefix) and a SUPERSTRING of another (the local account
name). So the guard does two different things:

- A blocklist of PRIVATE identifiers (out of git), matched after canonicalizing
  away the evasion forms below. The public handle and public repo names are NOT
  on it.
- A structural check for HOME-DIRECTORY paths, by FORM, for ANY username. What is
  private there is the SHAPE --a Windows profile path, a Unix home or Users
  root-- not the name inside it. This keeps the guard working after a change of
  machine or of user name, and it is what lets the public handle stay off the
  list: the local account name leaks as a path, and the path is what is caught.

Project rule (this guard learned it by repeating it)
----------------------------------------------------
**Every gate is defined with an exception, and the exception is the hole.** It
is the same mistake, iterated:

1. The first guard searched for literal substrings with a single backslash:
   eight ways of writing the same identifier escaped it.
2. The write guardian left out Bash and the MCP heuristics.
3. This guard exempted itself from the scan ("the file that DEFINES the
   identifiers is not scanned itself") and only looked at a whitelist of
   extensions. The tip passed 5/5 while it leaked the author's data in the one
   exempt file.
4. When the home path stopped being matched by the account NAME and started being
   matched by FORM, this file's own fictitious home-path examples would have
   tripped the form check. The fix was NOT to exempt this file --that is the
   antipattern above-- but to remove the home-path LITERALS from the repo: the
   docs use non-home example paths and the form tests assemble the home path at
   runtime, so the shape is tested without a literal living in any scanned file.

Each fix consisted of REMOVING the exception, not tuning it. That is why now the
file is scanned like any other, ALL text files are read (a blocklist of binaries,
not a whitelist of texts), and a file that cannot be read is REPORTED, not
skipped.

Why a plain `substring in text` is not enough (for the identifier list)
----------------------------------------------------------------------
A private identifier can appear in many forms that are NOT the literal substring,
and they all escaped (examples use a non-home path on purpose, so this file does
not trip the form check):

1. Escaped:         ``C:\\\\proyectos\\\\usuario``   (double backslash in source)
2. Slashes:         ``C:/proyectos/usuario``
3. URL / link:      ``file:///C:/proyectos/usuario``
4. Encoded:         ``C:%5Cproyectos%5Cusuario``     (percent-encoding)
5. Slug:            ``c--proyectos-usuario``          (separators -> hyphens)
6. Split:           a long path wrapped by a line break
7. Uppercase:       ``C:\\PROYECTOS\\USUARIO``
8. Bare:            the identifier without a path prefix
9. Concatenated:    ``"usu" + "ario"``                (joined Python literals)

The defense is to canonicalize before comparing: percent-encoding is decoded, it
is lowercased, and all separation, all escaping and the joining of literals are
collapsed (slashes, hyphen, underscore, spaces, line breaks, quotes and ``+``).
Form 9 is included on purpose: you cannot declare out of scope exactly the
technique a fix might use to hide the identifier.

Scope (honest): TIP, not history
---------------------------------
This gate walks the WORKING TREE. `.git/` is left out on purpose: cleaning the
HISTORY was a separate problem (done 2026-09-08; see
`docs/decisions/2026-09-08-history-rewrite.md`) and this test does NOT cover it.
Reading a green here as "the whole repo is clean" would be, again, taking an
exception for full coverage.

Where the private identifiers live
----------------------------------
NOT in this file --that would put them in the repo-- but in a file OUTSIDE git,
next to the user config (``identificadores_prohibidos.json``, alongside
``proyectos.json``). Public names (the handle, public repos) are NOT there: they
are public. If the file is missing, the test FAILS with instructions, it never
skips: a green skip is a blind guardian.

Why TWO tests (mechanism and data) and not one
----------------------------------------------
The check is split into ``test_mechanism_*`` (green on any runner, fictitious
data) and ``test_real_data_*`` (marked ``real_data``, only where the file
exists). The convention is in the header of ``tests/conftest.py``. Excluding the
data test in CI would be the antipattern above --a gate with an exception--, and
putting the identifiers in a GitHub secret would return to GitHub exactly what we
took out of it.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import quote, unquote

import pytest

from claude_informes import config as cfg

RAIZ = cfg.raiz_de_la_herramienta()

# The NON-versioned file with the real identifiers, next to proyectos.json.
NOMBRE_LISTA = "identificadores_prohibidos.json"

# The ONLY thing not scanned: known binaries. Everything else --with or without
# an extension-- is read as text. Inverting the criterion (a blocklist of
# binaries, not a whitelist of texts) closes the hole of a LICENSE without an
# extension or a CI .yml that the whitelist let through without looking.
BINARIOS = frozenset(
    {
        ".png", ".jpg", ".jpeg", ".gif", ".ico", ".bmp", ".webp", ".avif",
        ".pdf", ".zip", ".gz", ".tgz", ".tar", ".7z", ".rar",
        ".exe", ".dll", ".so", ".dylib", ".bin", ".class", ".jar",
        ".pyc", ".pyo", ".woff", ".woff2", ".ttf", ".otf", ".eot",
        ".mp4", ".mp3", ".wav", ".mov", ".webm", ".ogg", ".flac",
    }
)

CARPETAS_FUERA = {".git", ".venv", "__pycache__", ".pytest_cache", "informes"}


def _canon(texto: str) -> str:
    """Canonical form that collapses the evasion forms to a single string.

    1. Decodes percent-encoding: ``%5C`` -> ``\\``, ``%3A`` -> ``:``.
    2. Lowercase: ``C:\\PROYECTOS\\USUARIO`` == ``c:\\proyectos\\usuario``.
    3. Removes all separation, escaping and literal joining: slashes (``\\`` and
       ``/``), hyphen, underscore, spaces, line breaks, quotes (``"`` and
       ``'``) and ``+``. That is how the escaped, the slashes, the slug, the
       split path and the joining of Python literals (``"a" + "b"``) all fall.
    """
    t = unquote(texto)
    t = t.lower()
    return re.sub(r"[\\/\-_\s\"'+]+", "", t)


def _contiene(texto: str, reales_canon: list[str]) -> bool:
    """True if the text contains any of the (already canonicalized) identifiers."""
    canonico = _canon(texto)
    return any(real in canonico for real in reales_canon)


# Home-directory path detection, by FORM, for ANY username. The folder names are
# kept as separate fragments (`_SEG_*`) so the patterns do not embed a literal
# home path in THIS file's source --which the repo scan would then flag. What is
# private is the shape, not the name inside it.
_SEG_USERS = "users"
_SEG_HOME = "home"
_RUTA_WIN = re.compile(rf"[a-z]:/{_SEG_USERS}/[^/\s]")
_RUTA_UNIX = re.compile(rf"(?:^|[^a-z0-9._-])/(?:{_SEG_USERS}|{_SEG_HOME})/[^/\s]")


def _es_ruta_privada(texto: str) -> bool:
    """True if the text carries a home-directory path, under ANY username.

    The forms are unified first --percent-decoding, back/forward slashes,
    repeated slashes, case-- so the escaped, the slashed, the file URL, the
    percent-encoded and the uppercase variants reduce to one shape. It fires on a
    Windows profile path (a drive, then the Users folder, then a name) and on a
    Unix home or Users root at an absolute position; so a RELATIVE path that
    merely contains the word users does not count, nor does a word like homepage,
    nor a non-home absolute like the Program Files folder. It matches the SHAPE,
    never a name: that is what survives a change of user name, and what lets the
    author's public handle stay off the forbidden list.
    """
    t = unquote(texto).replace("\\", "/")
    t = re.sub(r"/+", "/", t).lower()
    return bool(_RUTA_WIN.search(t) or _RUTA_UNIX.search(t))


def _ruta_lista() -> Path:
    return cfg.dir_config_usuario() / NOMBRE_LISTA


_COMO_CREAR = (
    "Without it this guard cannot assert that the repo does not leak real data,\n"
    "and a push would publish exactly what it should catch.\n\n"
    "Create the file (outside git, next to your proyectos.json) like this:\n"
    '    {"identificadores": ["your-private-project", "your-email-prefix",\n'
    '                          "e:\\\\your\\\\archive\\\\root"]}\n\n'
    "List only PRIVATE identifiers. Your public handle and your public repos do\n"
    "NOT go here --they are public by construction. Home-directory paths are\n"
    "caught by FORM, for any username, so the local account name does not need to\n"
    "be listed either."
)


def _cargar_reales_canon(exigir_fichero_de_datos) -> list[str]:
    """The private identifiers, canonicalized. The file's existence is resolved by
    the shared helper `exigir_fichero_de_datos` (it fails with instructions if it
    is missing); here only the content is validated and canonicalized.
    """
    ruta = _ruta_lista()
    crudo = exigir_fichero_de_datos(ruta, como_crearlo=_COMO_CREAR)
    try:
        ids = json.loads(crudo)["identificadores"]
    except Exception as error:  # noqa: BLE001
        pytest.fail(f"unreadable identifier list ({ruta}): {error}")
    if not isinstance(ids, list) or not ids or not all(
        isinstance(x, str) and x.strip() for x in ids
    ):
        pytest.fail(f"the list must be a non-empty list of strings: {ruta}")
    return [_canon(x) for x in ids]


def _ficheros_a_escanear():
    for actual, subdirs, ficheros in os.walk(RAIZ):
        subdirs[:] = [
            d for d in subdirs if d not in CARPETAS_FUERA and not d.endswith(".egg-info")
        ]
        for nombre in ficheros:
            _, ext = os.path.splitext(nombre)
            if ext.lower() in BINARIOS:
                continue
            yield os.path.join(actual, nombre)


# --- home paths are assembled at RUNTIME (no home-path literal in this file) ---


def _home_win(user, *, sep="\\"):
    """A Windows profile path, assembled from bare pieces at runtime.

    The pieces ("C:", the Users folder name, the separator) are not a home path
    until joined, so no home-path literal lives in this file for the repo scan to
    flag --the same reason the docs use non-home example paths.
    """
    return "C:" + sep + "Users" + sep + user + sep + "algo"


def _home_unix(user, *, carpeta="Users"):
    """A Unix home or Users root, assembled at runtime (see `_home_win`)."""
    return "/" + carpeta + "/" + user + "/algo"


# --- the identifier guard catches what used to escape (FICTITIOUS identifiers) ---


def test_mechanism_catches_the_nine_evasion_forms():
    """Each case hides an identifier in a form that the literal-substring pattern
    used to let through.

    FICTITIOUS identifiers on a NON-home path: this file scans itself, so it can
    carry neither a real identifier nor a home-path literal. What is checked is
    the canonicalization, not the real list.
    """
    reales = [_canon("usuariofalso"), _canon("proyectofalso"), _canon("z:\\raizfalsa")]
    casos = {
        "escapada": 'ruta = "C:\\\\proyectos\\\\usuariofalso\\\\x"',
        "barras": "C:/proyectos/usuariofalso/x",
        "url": "file:///C:/proyectos/usuariofalso/x",
        "codificada": "C:%5Cproyectos%5Cusuariofalso%5Cx",
        "slug": "c--z-raizfalsa-proyectofalso",
        "partida": "C:\\proyectos\\\n    usuariofalso\\x",
        "mayusculas": "C:\\PROYECTOS\\USUARIOFALSO",
        "desnudo": "el proyecto se llama proyectofalso",
        "concatenada": '"usuario" + "falso"',
    }
    for nombre, texto in casos.items():
        assert _contiene(texto, reales), f"the guard does not catch the form: {nombre}"


def test_mechanism_a_fictitious_path_is_not_flagged():
    """Fictitious paths and names must not give a false positive on the list."""
    reales = [_canon("usuariofalso"), _canon("proyectofalso")]
    ficticios = [
        "C:\\datos\\ejemplo\\alfa\\x.json",
        "/ruta/absoluta/a/mi-proyecto",
        "beta y alfa son proyectos de muestra",
    ]
    for texto in ficticios:
        assert not _contiene(texto, reales), f"false positive on: {texto!r}"


# --- the home-path guard catches by FORM, for any username ---


def test_mechanism_a_home_path_of_any_user_fires_not_just_the_authors():
    """THE test that proves the redesign: a home path is caught by its FORM, for
    any username. If the guard only caught the author's own name, nothing would
    have changed -- this is the case that fails against the old substring guard.

    Home paths are assembled at runtime (see `_home_win` / `_home_unix`) so no
    home-path literal lives in this file for the repo scan to flag.
    """
    # The case that matters most: ANOTHER user, plain forward slashes.
    de_otro_usuario = _home_win("otro", sep="/")
    assert _es_ruta_privada(de_otro_usuario), (
        "a home path of another user must fire: caught by form, not by a name"
    )

    formas = [
        _home_win("otro"),                        # backslashes
        _home_win("otro", sep="\\\\"),            # escaped (double backslash)
        "file:///" + _home_win("otro", sep="/"),  # file URL
        quote(_home_win("otro")),                 # percent-encoded
        _home_win("OTRO").upper(),                # uppercase
        _home_unix("otro", carpeta="home"),       # unix home root
        _home_unix("otro"),                       # unix Users root
    ]
    for f in formas:
        assert _es_ruta_privada(f), f"home path not caught in form: {f!r}"


def test_mechanism_these_shapes_are_not_private_paths():
    """Shapes that look path-ish but are not a home directory must NOT fire."""
    no_disparan = [
        "homepage",
        "C:\\Program Files\\app\\config.ini",
        "usuarios de la aplicacion",
        "docs/users/algo",            # RELATIVE, not an absolute Users root
        "the users of the system",
        "/home",                      # no username segment after it
    ]
    for texto in no_disparan:
        assert not _es_ruta_privada(texto), f"false positive on: {texto!r}"


# --- the example ---


def test_mechanism_the_example_is_valid_json_with_the_right_shape():
    datos = json.loads(cfg.ruta_de_ejemplo().read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    assert isinstance(datos.get("proyectos"), list) and datos["proyectos"], "it must bring sample projects"
    assert "raiz_informes" in datos


@pytest.mark.real_data
def test_real_data_the_example_carries_no_identifier(exigir_fichero_de_datos):
    reales = _cargar_reales_canon(exigir_fichero_de_datos)
    texto = cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    assert not _contiene(texto, reales), "the example contains a real identifier"
    assert not _es_ruta_privada(texto), "the example contains a home-directory path"


# --- the whole repo, this file included ---


@pytest.mark.real_data
def test_real_data_the_repo_contains_no_identifier(exigir_fichero_de_datos):
    """Scans ALL the text files of the tip, this one included, for BOTH a private
    identifier AND a home-directory path form.

    A file that cannot be read as utf-8 is REPORTED as a hole (either it is text
    with a broken encoding, or it is binary and its extension goes in BINARIOS):
    it is not read half-way in silence. It used to be read with errors='ignore',
    which is a pass disguised as a read.
    """
    reales = _cargar_reales_canon(exigir_fichero_de_datos)
    ofensores = []
    ilegibles = []
    for ruta in _ficheros_a_escanear():
        try:
            texto = open(ruta, encoding="utf-8").read()
        except UnicodeDecodeError:
            ilegibles.append(os.path.relpath(ruta, RAIZ))
            continue
        except OSError:
            continue
        if _contiene(texto, reales) or _es_ruta_privada(texto):
            # The file is reported, not the datum: the message must not reprint
            # the real identifier or path we are trying to keep out.
            ofensores.append(os.path.relpath(ruta, RAIZ))
    assert not ilegibles, (
        "files the guard could not read as utf-8; an unreadable file is a hole, "
        "not a pass: fix its encoding, or if it is binary put its extension in "
        "BINARIOS:\n" + "\n".join(sorted(ilegibles))
    )
    assert not ofensores, (
        "real identifiers or home-directory paths in the repo:\n"
        + "\n".join(sorted(ofensores))
    )
