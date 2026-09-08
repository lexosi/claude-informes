"""El repositorio es publicable: ni una ruta ni un identificador real de nadie.

La config real vive fuera del repo; aqui se comprueba que el repo solo lleva el
ejemplo (JSON valido, rutas ficticias) y que en ningun fichero versionado se
cuela un identificador real (usuario, nombre de proyecto o raiz absoluta).

Regla del proyecto (este guard la aprendio a base de repetirla)
---------------------------------------------------------------
**Cada gate se define con una excepcion, y la excepcion es el agujero.** Es la
tercera iteracion del mismo error:

1. El primer guard buscaba subcadenas literales con backslash simple: se
   escapaban ocho formas de escribir el mismo identificador.
2. El guardian de escrituras dejaba fuera Bash y las heuristicas MCP.
3. Este guard se auto-eximia del escaneo ("el fichero que DEFINE los
   identificadores no se escanea a si mismo") y ademas solo miraba una lista
   blanca de extensiones. La punta pasaba 5/5 mientras filtraba el usuario, los
   proyectos y las rutas del autor, en el unico fichero exento.

Cada arreglo consistio en QUITAR la excepcion, no en afinarla. Por eso ahora:
el fichero se escanea como cualquier otro, se leen TODOS los ficheros de texto
(lista negra de binarios, no lista blanca de textos), y un fichero que no se
puede leer se REPORTA, no se salta.

Por que un simple `substring in texto` no basta
------------------------------------------------
Un identificador real puede aparecer de muchas formas que NO son la subcadena
literal, y todas se escapaban:

1. Escapada:        ``C:\\\\Users\\\\usuario``   (doble backslash en el fuente)
2. Barras:          ``C:/Users/usuario``
3. URL / enlace:    ``file:///C:/Users/usuario``
4. Codificada:      ``C:%5CUsers%5Cusuario``     (percent-encoding)
5. Slug:            ``c--proyectos-usuario``      (separadores -> guiones)
6. Partida:         una ruta larga envuelta por un salto de linea
7. Mayusculas:      ``C:\\USERS\\USUARIO``
8. Desnudo:         el usuario o el proyecto sin prefijo de ruta
9. Concatenada:     ``"usu" + "ario"``            (literales de Python unidos)

La defensa es canonizar antes de comparar: se descodifica el percent-encoding,
se pasa a minusculas y se colapsa toda separacion, todo escape y la union de
literales (barras, guion, guion bajo, espacios, saltos de linea, comillas y
``+``). La forma 9 entra a proposito: no se puede declarar fuera de alcance
justo la tecnica que un fix podria usar para esconder el identificador --y de
hecho una version anterior de este fichero la usaba--.

Alcance (honesto): PUNTA, no historia
-------------------------------------
Este gate recorre el ARBOL DE TRABAJO. `.git/` queda fuera del recorrido a
proposito: la limpieza del HISTORIAL es un problema aparte (ver NO-PUBLICAR.md)
y este test NO la cubre. Leer un verde aqui como "el repo entero esta limpio"
seria, otra vez, tomar una excepcion por cobertura total.

Donde viven los identificadores reales
--------------------------------------
NO en este fichero --eso los meteria en el repo, que es justo lo que se quiere
evitar-- sino en un fichero FUERA de git, junto a la config de usuario
(``identificadores_prohibidos.json``, al lado de ``proyectos.json``). Si falta,
el test FALLA con instrucciones, nunca se salta: un skip verde es un guardian
ciego, y de esos ya llevamos tres.

Por que DOS tests (mecanismo y datos) y no uno
----------------------------------------------
La comprobacion se parte en un ``test_mechanism_*`` (verde en cualquier runner,
con identificadores ficticios) y un ``test_real_data_*`` (marcado
``real_data``, solo donde existe el fichero). La convencion general esta en
la cabecera de ``tests/conftest.py``; aqui quedan escritas las tres razones de
elegir esta separacion antes que excluir el test en CI o meter los datos en un
secret:

1. Es la misma separacion que el proyecto ya usa en todas partes: la LOGICA
   vive en el repo, los DATOS de la maquina viven fuera. El guard era el ultimo
   sitio donde faltaba aplicarla.
2. Excluir el test en CI romperia la regla de arriba: seria la cuarta iteracion
   del mismo fallo --un gate con una excepcion-- cometida a proposito tres dias
   despues de escribirla.
3. Meter los identificadores en un secret de GitHub devuelve a GitHub
   exactamente lo que sacamos de GitHub. Un secret cifrado sigue siendo el
   nombre y los proyectos del autor en infraestructura ajena.
"""

import json
import os
import re
from pathlib import Path
from urllib.parse import unquote

import pytest

from claude_informes import config as cfg

RAIZ = cfg.raiz_de_la_herramienta()

# El fichero NO versionado con los identificadores reales, junto a proyectos.json.
NOMBRE_LISTA = "identificadores_prohibidos.json"

# Lo UNICO que no se escanea: binarios conocidos. Todo lo demas --tenga o no
# extension-- se lee como texto. Invertir el criterio (lista negra de binarios,
# no lista blanca de textos) cierra el hueco de un LICENSE sin extension o un
# .yml de CI que la lista blanca dejaba pasar sin mirar.
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
    """Forma canonica que colapsa las formas de evasion a una sola cadena.

    1. Descodifica percent-encoding: ``%5C`` -> ``\\``, ``%3A`` -> ``:``.
    2. Minusculas: ``C:\\Users\\USUARIO`` == ``c:\\users\\usuario``.
    3. Quita toda separacion, escape y union de literales: barras (``\\`` y
       ``/``), guion, guion bajo, espacios, saltos de linea, comillas (``"`` y
       ``'``) y ``+``. Asi caen la escapada, las barras, el slug, la ruta
       partida y la concatenacion de literales de Python (``"a" + "b"``).
    """
    t = unquote(texto)
    t = t.lower()
    return re.sub(r"[\\/\-_\s\"'+]+", "", t)


def _contiene(texto: str, reales_canon: list[str]) -> bool:
    """True si el texto contiene algun identificador (ya canonizado) buscado."""
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
    """Los identificadores reales, canonizados. La existencia del fichero la
    resuelve el helper compartido `exigir_fichero_de_datos` (falla con
    instrucciones si no esta); aqui solo se valida y canoniza el contenido.
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


# --- el guard caza lo que antes se escapaba (identificadores FICTICIOS) ---


def test_mechanism_catches_the_nine_evasion_forms():
    """Cada caso esconde un identificador de una forma que el patron de
    subcadena literal dejaba pasar.

    Se usan identificadores FICTICIOS a proposito: este fichero se escanea a si
    mismo, asi que no puede contener ninguno real. Lo que se comprueba es la
    canonizacion, no la lista real.
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
    """Las rutas y nombres ficticios no deben dar falso positivo."""
    reales = [_canon("usuariofalso"), _canon("proyectofalso")]
    ficticios = [
        "C:\\Users\\ejemplo\\proyectos\\alfa\\x.json",
        "/ruta/absoluta/a/mi-proyecto",
        "beta y alfa son proyectos de muestra",
    ]
    for texto in ficticios:
        assert not _contiene(texto, reales), f"falso positivo en: {texto!r}"


# --- el ejemplo ---


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


# --- todo el repo, este fichero incluido ---


@pytest.mark.real_data
def test_real_data_the_repo_contains_no_identifier(exigir_fichero_de_datos):
    """Escanea TODOS los ficheros de texto de la punta, este incluido.

    Un fichero que no se puede leer como utf-8 se REPORTA como hueco (o es texto
    con encoding roto, o es binario y su extension va en BINARIOS): no se lee a
    medias en silencio. Antes se leia con errors='ignore', que es un pase
    disfrazado de lectura.
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
            # Se reporta el fichero, no el identificador: el mensaje no debe
            # reimprimir el dato real que se intenta mantener fuera.
            ofensores.append(os.path.relpath(ruta, RAIZ))
    assert not ilegibles, (
        "ficheros que el guard no pudo leer como utf-8; un fichero ilegible es un "
        "hueco, no un pase: arregla su encoding, o si es binario mete su extension "
        "en BINARIOS:\n" + "\n".join(sorted(ilegibles))
    )
    assert not ofensores, "identificadores reales en el repo:\n" + "\n".join(sorted(ofensores))
