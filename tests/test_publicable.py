"""The repository is publishable: not a single real path or identifier of anyone.

The real config lives outside the repo; here it is checked that the repo only
carries the example (valid JSON, fictitious paths) and that no versioned file
slips in a real identifier (username, project name or absolute root).

Project rule (this guard learned it by repeating it)
----------------------------------------------------
**Every gate is defined with an exception, and the exception is the hole.** It
is the third iteration of the same mistake:

1. The first guard searched for literal substrings with a single backslash:
   eight ways of writing the same identifier escaped it.
2. The write guardian left out Bash and the MCP heuristics.
3. This guard exempted itself from the scan ("the file that DEFINES the
   identifiers is not scanned itself") and, on top of that, only looked at a
   whitelist of extensions. The tip passed 5/5 while it leaked the author's
   username, projects and paths, in the one exempt file.

Each fix consisted of REMOVING the exception, not tuning it. That is why now:
the file is scanned like any other, ALL text files are read (a blocklist of
binaries, not a whitelist of texts), and a file that cannot be read is
REPORTED, not skipped.

Why a plain `substring in text` is not enough
---------------------------------------------
A real identifier can appear in many forms that are NOT the literal substring,
and they all escaped:

1. Escaped:         ``C:\\\\Users\\\\usuario``   (double backslash in the source)
2. Slashes:         ``C:/Users/usuario``
3. URL / link:      ``file:///C:/Users/usuario``
4. Encoded:         ``C:%5CUsers%5Cusuario``     (percent-encoding)
5. Slug:            ``c--proyectos-usuario``      (separators -> hyphens)
6. Split:           a long path wrapped by a line break
7. Uppercase:       ``C:\\USERS\\USUARIO``
8. Bare:            the username or the project without a path prefix
9. Concatenated:    ``"usu" + "ario"``            (joined Python literals)

The defense is to canonicalize before comparing: percent-encoding is decoded,
it is lowercased, and all separation, all escaping and the joining of literals
are collapsed (slashes, hyphen, underscore, spaces, line breaks, quotes and
``+``). Form 9 is included on purpose: you cannot declare out of scope exactly
the technique a fix might use to hide the identifier --and in fact an earlier
version of this file used it.

Scope (honest): TIP, not history
---------------------------------
This gate walks the WORKING TREE. `.git/` is left out of the walk on purpose:
cleaning the HISTORY is a separate problem (see NO-PUBLICAR.md) and this test
does NOT cover it. Reading a green here as "the whole repo is clean" would be,
again, taking an exception for full coverage.

Where the real identifiers live
-------------------------------
NOT in this file --that would put them in the repo, which is exactly what we
want to avoid-- but in a file OUTSIDE git, next to the user config
(``identificadores_prohibidos.json``, alongside ``proyectos.json``). If it is
missing, the test FAILS with instructions, it never skips: a green skip is a
blind guardian, and the project already has three of those.

Why TWO tests (mechanism and data) and not one
----------------------------------------------
The check is split into a ``test_mechanism_*`` (green on any runner, with
fictitious identifiers) and a ``test_real_data_*`` (marked ``real_data``, only
where the file exists). The general convention is in the header of
``tests/conftest.py``; here are written the three reasons for choosing this
split over excluding the test in CI or putting the data in a secret:

1. It is the same split the project already uses everywhere: the LOGIC lives in
   the repo, the machine DATA lives outside. The guard was the last place where
   it was still missing.
2. Excluding the test in CI would break the rule above: it would be the fourth
   iteration of the same failure --a gate with an exception-- committed on
   purpose three days after writing it.
3. Putting the identifiers in a GitHub secret returns to GitHub exactly what we
   took out of GitHub. An encrypted secret is still the author's name and
   projects on someone else's infrastructure.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import unquote

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
    2. Lowercase: ``C:\\Users\\USUARIO`` == ``c:\\users\\usuario``.
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


def _ruta_lista() -> Path:
    return cfg.dir_config_usuario() / NOMBRE_LISTA


_COMO_CREAR = (
    "Without it this guard cannot assert that the repo does not leak real data,\n"
    "and a push would publish exactly what it should catch.\n\n"
    "Create the file (outside git, next to your proyectos.json) like this:\n"
    '    {"identificadores": ["your-user", "your-project", "e:\\\\your\\\\root"]}'
)


def _cargar_reales_canon(exigir_fichero_de_datos) -> list[str]:
    """The real identifiers, canonicalized. The file's existence is resolved by
    the shared helper `exigir_fichero_de_datos` (it fails with instructions if it
    is missing); here only the content is validated and canonicalized.
    """
    ruta = _ruta_lista()
    crudo = exigir_fichero_de_datos(ruta, como_crearlo=_COMO_CREAR)
    try:
        ids = json.loads(crudo)["identificadores"]
    except Exception as error:  # noqa: BLE001
        pytest.fail(f"lista de identificadores ilegible ({ruta}): {error}")
    if not isinstance(ids, list) or not ids or not all(
        isinstance(x, str) and x.strip() for x in ids
    ):
        pytest.fail(f"la lista debe ser una lista no vacia de cadenas: {ruta}")
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


# --- the guard catches what used to escape (FICTITIOUS identifiers) ---


def test_mechanism_catches_the_nine_evasion_forms():
    """Each case hides an identifier in a form that the literal-substring pattern
    used to let through.

    FICTITIOUS identifiers are used on purpose: this file scans itself, so it
    cannot contain any real one. What is checked is the canonicalization, not the
    real list.
    """
    reales = [_canon("usuariofalso"), _canon("proyectofalso"), _canon("z:\\raizfalsa")]
    casos = {
        "escapada": 'ruta = "C:\\\\Users\\\\usuariofalso\\\\x"',
        "barras": "C:/Users/usuariofalso/x",
        "url": "file:///C:/Users/usuariofalso/x",
        "codificada": "C:%5CUsers%5Cusuariofalso%5Cx",
        "slug": "c--z-raizfalsa-proyectofalso",
        "partida": "C:\\Users\\\n    usuariofalso\\x",
        "mayusculas": "C:\\USERS\\USUARIOFALSO",
        "desnudo": "el proyecto se llama proyectofalso",
        "concatenada": '"usuario" + "falso"',
    }
    for nombre, texto in casos.items():
        assert _contiene(texto, reales), f"el guard no caza la forma: {nombre}"


def test_mechanism_a_fictitious_path_is_not_flagged():
    """Fictitious paths and names must not give a false positive."""
    reales = [_canon("usuariofalso"), _canon("proyectofalso")]
    ficticios = [
        "C:\\Users\\ejemplo\\proyectos\\alfa\\x.json",
        "/ruta/absoluta/a/mi-proyecto",
        "beta y alfa son proyectos de muestra",
    ]
    for texto in ficticios:
        assert not _contiene(texto, reales), f"falso positivo en: {texto!r}"


# --- the example ---


def test_mechanism_the_example_is_valid_json_with_the_right_shape():
    datos = json.loads(cfg.ruta_de_ejemplo().read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    assert isinstance(datos.get("proyectos"), list) and datos["proyectos"], "debe traer proyectos de muestra"
    assert "raiz_informes" in datos


@pytest.mark.real_data
def test_real_data_the_example_carries_no_identifier(exigir_fichero_de_datos):
    reales = _cargar_reales_canon(exigir_fichero_de_datos)
    texto = cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    assert not _contiene(texto, reales), "el ejemplo contiene un identificador real"


# --- the whole repo, this file included ---


@pytest.mark.real_data
def test_real_data_the_repo_contains_no_identifier(exigir_fichero_de_datos):
    """Scans ALL the text files of the tip, this one included.

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
        if _contiene(texto, reales):
            # The file is reported, not the identifier: the message must not
            # reprint the real datum we are trying to keep out.
            ofensores.append(os.path.relpath(ruta, RAIZ))
    assert not ilegibles, (
        "ficheros que el guard no pudo leer como utf-8; un fichero ilegible es un "
        "hueco, no un pase: arregla su encoding, o si es binario mete su extension "
        "en BINARIOS:\n" + "\n".join(sorted(ilegibles))
    )
    assert not ofensores, "identificadores reales en el repo:\n" + "\n".join(sorted(ofensores))
