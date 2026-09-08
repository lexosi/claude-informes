"""Syntactic splitting of the markdown. Nothing semantic: only syntax."""

from __future__ import annotations

import re
import unicodedata

_FENCE = re.compile(r"^(\s{0,3})(`{3,}|~{3,})\s*(.*)$")
_HEADING = re.compile(r"^(\s{0,3})(#{1,6})\s+(.*?)\s*#*\s*$")
_CASILLA = re.compile(r"^\s*(?:[-*+]|\d+[.)])\s+\[([ xX])\]\s*(.*)$")

# Inline marks removed only to build the slug or the title.
_INLINE = re.compile(r"(\*\*|__|\*|_|`|~~)")
_ENLACE = re.compile(r"\[([^\]]*)\]\([^)]*\)")

# Numbering at the start of a heading: "1. TRANSCRIPT", "2) Cosas", "1.3 - Tal".
_NUMERACION = re.compile(r"^\s*\d+(?:\.\d+)*\s*[.)\-:]\s*")

MINIMO_PALABRAS = 3
TOPE = 60

# Articles, prepositions and common connectors in es/en. Without accents: the
# comparison is done after ascii-folding.
VACIAS = frozenset(
    """
    el la los las lo un una unos unas al del
    de a ante bajo con contra desde durante en entre hacia hasta mediante
    para por segun sin sobre tras
    y e ni o u que como cuando donde pero mas sino aunque porque pues si
    no se le les me te nos os su sus mi mis tu tus
    es son ser esta estan este esta estos estas ese esa esos esas
    fue era han ha hay hemos he ya solo tambien
    the a an of in on at to for from by with within and or but nor so
    if then than that this these those it its as into over under about
    is are was were be been being do does did have has had
    """.split()
)


def _mapa_de_vallas(lineas: list[str]) -> list[bool]:
    """Returns, per line, whether that line is INSIDE a fenced block.

    The opening line and the closing line count as inside.
    """
    dentro = [False] * len(lineas)
    valla: str | None = None
    for i, linea in enumerate(lineas):
        m = _FENCE.match(linea)
        if valla is None:
            if m:
                valla = m.group(2)[0] * 3
                dentro[i] = True
        else:
            dentro[i] = True
            if m and m.group(2).startswith(valla) and not m.group(3).strip():
                valla = None
    return dentro


def limpiar_inline(texto: str) -> str:
    """Remove inline markdown marks. Only for titles and slugs."""
    texto = _ENLACE.sub(r"\1", texto)
    return _INLINE.sub("", texto).strip()


def contar_lineas(markdown: str) -> int:
    """Lines of RAW markdown, exactly as it arrives."""
    return len(markdown.splitlines())


def supera_umbral(markdown: str, umbral: int = 5) -> bool:
    """Threshold: strictly MORE than `umbral` lines of raw markdown."""
    return contar_lineas(markdown) > umbral


def encabezados(markdown: str) -> list[tuple[int, str, int]]:
    """(level, title, line index) of each ATX heading outside fences."""
    lineas = markdown.splitlines()
    dentro = _mapa_de_vallas(lineas)
    fuera = []
    for i, linea in enumerate(lineas):
        if dentro[i]:
            continue
        m = _HEADING.match(linea)
        if m:
            fuera.append((len(m.group(2)), limpiar_inline(m.group(3)), i))
    return fuera


def secciones(markdown: str) -> list[dict]:
    """Split by ATX headings. The content is raw, without the heading."""
    lineas = markdown.splitlines()
    marcas = encabezados(markdown)
    if not marcas:
        return []
    resultado = []
    for pos, (nivel, titulo, inicio) in enumerate(marcas):
        fin = marcas[pos + 1][2] if pos + 1 < len(marcas) else len(lineas)
        cuerpo = "\n".join(lineas[inicio + 1 : fin]).strip("\n")
        resultado.append({"nivel": nivel, "titulo": titulo, "contenido": cuerpo})
    return resultado


def bloques_codigo(markdown: str) -> list[dict]:
    """Blocks fenced with ``` or ~~~. The code is raw, without the fences."""
    lineas = markdown.splitlines()
    resultado: list[dict] = []
    valla: str | None = None
    lenguaje = ""
    cuerpo: list[str] = []
    for linea in lineas:
        m = _FENCE.match(linea)
        if valla is None:
            if m:
                valla = m.group(2)[0] * 3
                lenguaje = m.group(3).strip()
                cuerpo = []
            continue
        if m and m.group(2).startswith(valla) and not m.group(3).strip():
            resultado.append({"lenguaje": lenguaje, "codigo": "\n".join(cuerpo)})
            valla = None
            continue
        cuerpo.append(linea)
    if valla is not None:  # unclosed fence: saved all the same
        resultado.append({"lenguaje": lenguaje, "codigo": "\n".join(cuerpo)})
    return resultado


def casillas(markdown: str) -> list[dict]:
    """Task checkboxes `- [ ]` / `- [x]` outside fenced blocks."""
    lineas = markdown.splitlines()
    dentro = _mapa_de_vallas(lineas)
    resultado = []
    for i, linea in enumerate(lineas):
        if dentro[i]:
            continue
        m = _CASILLA.match(linea)
        if m:
            resultado.append(
                {
                    "marcada": m.group(1).lower() == "x",
                    "texto": limpiar_inline(m.group(2)),
                }
            )
    return resultado


def _asciificar(texto: str) -> str:
    descompuesto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in descompuesto if not unicodedata.combining(c))


def palabras_significativas(texto: str) -> list[str]:
    """Words of the text without articles, prepositions or common connectors.

    Lone numbers also drop out: they are numbering, not content.
    """
    limpio = _asciificar(limpiar_inline(texto)).lower().replace("ß", "ss")
    return [
        trozo
        for trozo in re.split(r"[^a-z0-9]+", limpio)
        if trozo and not trozo.isdigit() and trozo not in VACIAS
    ]


def recortar(slug: str, maximo: int = TOPE) -> str:
    """Cut at a hyphen, never in the middle of a word."""
    if len(slug) <= maximo:
        return slug
    cortado = slug[:maximo].rsplit("-", 1)[0].strip("-")
    return cortado or slug[:maximo].strip("-")


def slugificar(texto: str, maximo: int = TOPE) -> str:
    """Content slug: only significant words."""
    return recortar("-".join(palabras_significativas(texto)), maximo)


def slug_llano(texto: str, maximo: int = TOPE) -> str:
    """Slug of a proper name (a directory, e.g.): nothing is discarded."""
    limpio = _asciificar(limpiar_inline(texto)).lower().replace("ß", "ss")
    return recortar(re.sub(r"[^a-z0-9]+", "-", limpio).strip("-"), maximo)


def _de_los_encabezados(markdown: str) -> list[str]:
    """Successive headings until enough words are gathered, or they run out."""
    palabras: list[str] = []
    for _, titulo, _ in encabezados(markdown):
        palabras.extend(palabras_significativas(_NUMERACION.sub("", titulo, count=1)))
        if len(palabras) >= MINIMO_PALABRAS:
            break
    return palabras


def _del_cuerpo(markdown: str, maximo: int = 8) -> list[str]:
    lineas = markdown.splitlines()
    dentro = _mapa_de_vallas(lineas)
    palabras: list[str] = []
    for i, linea in enumerate(lineas):
        if dentro[i] or not linea.strip() or _HEADING.match(linea):
            continue
        palabras.extend(palabras_significativas(linea))
        if len(palabras) >= maximo:
            break
    return palabras[:maximo]


def nombre_desde_markdown(markdown: str) -> str:
    """The report's slug.

    1. First heading, if it carries 3+ significant words (without its numbering).
    2. If not, successive headings concatenated until reaching 3+ or running out.
    3. If it is still poor, or there are no headings, words from the body.
    """
    palabras = _de_los_encabezados(markdown)
    if len(palabras) < MINIMO_PALABRAS:
        palabras = _del_cuerpo(markdown) or palabras
    return recortar("-".join(palabras)) or "sin-titulo"
