"""El repositorio es publicable: ni una ruta ni un identificador real de nadie.

La config real vive fuera del repo; aqui se comprueba que el repo solo lleva el
ejemplo (JSON valido, rutas ficticias) y que en ningun fichero versionado se
cuela un identificador real (usuario, nombre de proyecto o raiz absoluta).

Por que un simple `substring in texto` no basta
------------------------------------------------
La version anterior buscaba subcadenas literales con backslash simple
(``C:\\Users\\<usuario>``). Un identificador real puede aparecer de muchas
formas que NO son esa subcadena literal, y todas se escapaban:

1. Escapada:        ``C:\\\\Users\\\\usuario``  (doble backslash en el fuente)
2. Barras:          ``C:/Users/usuario``
3. URL / enlace:    ``file:///C:/Users/usuario``
4. Codificada:      ``C:%5CUsers%5Cusuario``    (percent-encoding)
5. Slug:            ``c--proyectos-usuario``    (separadores -> guiones)
6. Partida:         una ruta larga envuelta por un salto de linea
7. Mayusculas:      ``C:\\USERS\\USUARIO``
8. Desnudo:         el usuario o el proyecto sin prefijo de ruta

La defensa es canonizar antes de comparar: se descodifica el percent-encoding,
se pasa a minusculas y se colapsa toda separacion y todo escape (barras ``\\``
y ``/``, guion, guion bajo, espacios y saltos de linea). Sobre esa forma
canonica se busca cada identificador real, tambien canonizado. Asi las ocho
formas de arriba colapsan a la misma cadena y se cazan por igual.

Fuera de alcance (honesto): partir un identificador MITAD y mitad entre dos
literales concatenados (``"us" + "er"``) es ofuscacion deliberada, no una fuga
accidental de una ruta; este guard protege contra lo segundo, no contra alguien
que esconde su propio nombre a proposito.
"""

import os
import re
from urllib.parse import unquote

from claude_informes import config as cfg

RAIZ = cfg.raiz_de_la_herramienta()

# Identificadores REALES que no deben aparecer en el repo, en NINGUNA forma. Se
# arman por fragmentos a proposito: asi el literal no aparece en los bytes de
# este fichero y no se delata al escanearse (ademas del auto-descarte de abajo).
_USUARIOS = ["fa" + "ke", "us" + "er", "lex" + "osi"]
_PROYECTOS = ["loop" + "ward", "proj" + "ect-b", "proj" + "ect-c", "proj" + "ects"]
_RAICES = ["e:" + "\\" + "example-projects", "e:" + "\\" + "example-reports"]
REALES = _USUARIOS + _PROYECTOS + _RAICES

EXTENSIONES = {".py", ".md", ".json", ".toml", ".cfg", ".ini", ".txt", ".gitignore", ".gitattributes"}
CARPETAS_FUERA = {".git", ".venv", "__pycache__", ".pytest_cache", "informes"}


def _canon(texto: str) -> str:
    """Forma canonica que colapsa las formas de evasion a una sola cadena.

    1. Descodifica percent-encoding: ``%5C`` -> ``\\``, ``%3A`` -> ``:``.
    2. Minusculas: ``C:\\Users\\USUARIO`` == ``c:\\users\\usuario``.
    3. Quita toda separacion y escape: barras (``\\`` y ``/``), guion, guion
       bajo, espacios y saltos de linea. Asi caen la escapada (doble backslash),
       las barras normales, el slug (guiones) y la ruta partida por un salto.
    """
    t = unquote(texto)
    t = t.lower()
    return re.sub(r"[\\/\-_\s]+", "", t)


_REALES_CANON = [_canon(x) for x in REALES]


def _contiene_real(texto: str) -> bool:
    """True si el texto contiene algun identificador real en cualquier forma."""
    canonico = _canon(texto)
    return any(real in canonico for real in _REALES_CANON)


def _ficheros_versionables():
    for actual, subdirs, ficheros in os.walk(RAIZ):
        subdirs[:] = [
            d for d in subdirs
            if d not in CARPETAS_FUERA and not d.endswith(".egg-info")
        ]
        for nombre in ficheros:
            ruta = os.path.join(actual, nombre)
            _, ext = os.path.splitext(nombre)
            if ext in EXTENSIONES or nombre in {".gitignore", ".gitattributes"}:
                yield ruta


# --- el guard caza lo que antes se escapaba ---


def test_el_guard_caza_las_ocho_formas_de_evasion():
    """Cada caso esconde un identificador real de una forma que el patron de
    subcadena literal con backslash simple dejaba pasar."""
    casos = {
        "escapada": "ruta = \"C:\\\\Users\\\\user\\\\x\"",
        "barras": "C:/Users/user/x",
        "url": "file:///C:/Users/user/x",
        "codificada": "C:%5CUsers%5Cuser%5Cx",
        "slug": "c--example-projects-loopward",
        "partida": "C:\\Users\\\n    user\\x",
        "mayusculas": "C:\\USERS\\user",
        "desnudo": "el proyecto se llama loopward",
    }
    for nombre, texto in casos.items():
        assert _contiene_real(texto), f"el guard no caza la forma: {nombre}"


def test_una_ruta_ficticia_no_se_marca():
    """Las rutas y nombres ficticios del repo no deben dar falso positivo."""
    ficticios = [
        "C:\\Users\\ejemplo\\proyectos\\alfa\\x.json",
        "/ruta/absoluta/a/mi-proyecto",
        "E:\\\\proyectos\\\\alfa",  # 'proyectos' a secas no es 'example-projects'
        "beta y alfa son proyectos de muestra",
    ]
    for texto in ficticios:
        assert not _contiene_real(texto), f"falso positivo en: {texto!r}"


# --- el ejemplo ---


def test_el_ejemplo_es_json_valido_y_tiene_forma():
    import json

    datos = json.loads(cfg.ruta_de_ejemplo().read_text(encoding="utf-8"))
    assert isinstance(datos, dict)
    assert isinstance(datos.get("proyectos"), list) and datos["proyectos"], "debe traer proyectos de muestra"
    assert "raiz_informes" in datos


def test_el_ejemplo_no_lleva_ningun_identificador_real():
    texto = cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    assert not _contiene_real(texto), "el ejemplo contiene un identificador real"


# --- todo el repo ---


def test_el_repo_no_contiene_ningun_identificador_real():
    este_fichero = os.path.abspath(__file__)
    ofensores = []
    for ruta in _ficheros_versionables():
        if os.path.abspath(ruta) == este_fichero:
            continue  # este fichero DEFINE los identificadores; no se escanea a si mismo
        try:
            texto = open(ruta, encoding="utf-8", errors="ignore").read()
        except OSError:
            continue
        if _contiene_real(texto):
            # Se reporta el fichero, no el identificador: el mensaje de fallo no
            # debe reimprimir el dato real que estamos intentando mantener fuera.
            ofensores.append(os.path.relpath(ruta, RAIZ))
    assert not ofensores, "identificadores reales en el repo:\n" + "\n".join(sorted(ofensores))
