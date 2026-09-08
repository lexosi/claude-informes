"""Threshold, slug, and syntactic chunking."""

import pytest

from claude_informes import markdown as md


# --- threshold: strictly more than N lines of RAW markdown ---


def test_threshold_exactly_at_the_limit_does_not_pass():
    assert md.supera_umbral("1\n2\n3\n4\n5", 5) is False


def test_threshold_one_line_over_passes():
    assert md.supera_umbral("1\n2\n3\n4\n5\n6", 5) is True


def test_threshold_counts_lines_not_characters():
    largo_de_una_linea = "x" * 5000
    assert md.supera_umbral(largo_de_una_linea, 5) is False


def test_threshold_counts_blank_lines():
    assert md.supera_umbral("a\n\n\n\n\n\nb", 5) is True


def test_threshold_counts_raw_lines_inside_code_blocks():
    texto = "Mira:\n```py\n1\n2\n3\n4\n```"
    assert md.supera_umbral(texto, 5) is True


def test_threshold_counts_lines_with_crlf_endings():
    assert md.supera_umbral("1\r\n2\r\n3\r\n4\r\n5\r\n6", 5) is True


# --- significant words ---


def test_spanish_articles_and_prepositions_are_discarded():
    assert md.palabras_significativas("el informe de la sesion") == ["informe", "sesion"]


def test_english_articles_and_prepositions_are_discarded():
    assert md.palabras_significativas("the report of the session") == [
        "report",
        "session",
    ]


def test_bare_numbers_do_not_count_as_a_word():
    assert md.palabras_significativas("1. 2026 transcript") == ["transcript"]


def test_an_alphanumeric_identifier_does_count():
    assert md.palabras_significativas("commit ac72eff") == ["commit", "ac72eff"]


# --- slug, rule 1: first heading with 3+ significant words ---


def test_a_rich_heading_is_used_as_is():
    texto = "# Informe de la sesion de hoy\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "informe-sesion-hoy"


def test_the_heading_level_does_not_matter():
    texto = "### Barrido del arbol terminado\ncosas"
    assert md.nombre_desde_markdown(texto) == "barrido-arbol-terminado"


def test_accents_and_inline_marks_are_stripped():
    texto = "# **Investigación** del `transcript` y hooks"
    assert md.nombre_desde_markdown(texto) == "investigacion-transcript-hooks"


def test_the_leading_numbering_is_stripped():
    """The real case that gave '1-transcript'."""
    texto = "## 1. TRANSCRIPT del runtime instalado\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "transcript-runtime-instalado"


@pytest.mark.parametrize(
    "encabezado",
    [
        "## 1. Uno dos tres",
        "## 1) Uno dos tres",
        "## 2.3 - Uno dos tres",
        "## 4: Uno dos tres",
        "## 10 . Uno dos tres",
    ],
)
def test_the_numbering_is_stripped_in_all_its_variants(encabezado):
    assert md.nombre_desde_markdown(encabezado + "\n\ncuerpo") == "uno-dos-tres"


# --- slug, rule 2: concatenate successive headings ---


def test_a_poor_heading_is_concatenated_with_the_next_one():
    """The real case that gave 'tabla'."""
    texto = "## Tabla\n\nfila\n\n## Veredicto final\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "tabla-veredicto-final"


def test_as_many_headings_as_needed_are_concatenated():
    texto = "## Tabla\n\n## Resumen\n\n## Fin\n\n## Sobra\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "tabla-resumen-fin"


def test_the_concatenation_stops_upon_reaching_three_words():
    texto = "## Tabla\n\n## Veredicto final del barrido completo\n\n## Sobra\n\nx"
    assert "sobra" not in md.nombre_desde_markdown(texto)


# --- slug, rule 3: the body ---


def test_without_headings_the_body_words_are_used():
    texto = "Hecho. Sin push. El commit ac72eff queda listo y verde."
    assert md.nombre_desde_markdown(texto) == (
        "hecho-push-commit-ac72eff-queda-listo-verde"
    )


def test_when_the_headings_run_out_poor_the_body_takes_over():
    texto = "## Tabla\n\nEl cuerpo tiene palabras utiles aqui"
    assert md.nombre_desde_markdown(texto) == "cuerpo-tiene-palabras-utiles-aqui"


def test_a_heading_of_only_symbols_contributes_nothing():
    texto = "### ???\n\n### !!!\n\nEl cuerpo si tiene palabras utiles"
    assert md.nombre_desde_markdown(texto) == "cuerpo-tiene-palabras-utiles"


def test_headings_inside_a_code_block_do_not_count():
    texto = "```sh\n# no soy un titulo\n```\nTexto real de la respuesta larga"
    assert md.nombre_desde_markdown(texto) == "texto-real-respuesta-larga"


def test_the_body_does_not_pick_up_the_heading_lines():
    texto = "## Tabla\n\ncuerpo de verdad con palabras"
    assert "tabla" not in md.nombre_desde_markdown(texto)


def test_with_nothing_sluggable_a_fallback_name_remains():
    assert md.nombre_desde_markdown("### ???\n\n!!!") == "sin-titulo"


def test_an_empty_markdown_does_not_blow_up():
    assert md.nombre_desde_markdown("") == "sin-titulo"


# --- slug, rule 4: length cap ---


def test_the_slug_is_trimmed_without_splitting_words():
    largo = "# " + " ".join(["palabra"] * 30)
    slug = md.nombre_desde_markdown(largo)

    assert len(slug) <= md.TOPE
    assert not slug.endswith("-")
    assert all(trozo == "palabra" for trozo in slug.split("-"))


def test_a_single_very_long_word_is_cut_anyway():
    slug = md.nombre_desde_markdown("# " + "x" * 200)
    assert len(slug) <= md.TOPE


def test_trimming_a_word_longer_than_the_cap_cuts_it_hard():
    """Degenerate case, pinned: a single word without a hyphen longer than the cap
    does not fit at any word boundary. Since the result is a FILE
    NAME, the cap is HARD: it is cut hard and the result NEVER exceeds the cap,
    even if that splits the word. A soft cap that returned the whole word
    (more than TOPE) would fail here.
    """
    resultado = md.recortar("x" * 300)

    assert len(resultado) <= md.TOPE, "the cap is hard: it is never exceeded"
    assert len(resultado) == md.TOPE, "a 300-char word is cut exactly at the cap"


# --- plain slug, for proper names ---


def test_the_plain_slug_does_not_discard_words():
    assert md.slug_llano("Mi Repo de la Empresa") == "mi-repo-de-la-empresa"


# --- syntactic chunking ---


def test_sections_are_split_by_headings():
    texto = "# Uno\ncuerpo uno\n\n## Dos\ncuerpo dos"
    assert md.secciones(texto) == [
        {"nivel": 1, "titulo": "Uno", "contenido": "cuerpo uno"},
        {"nivel": 2, "titulo": "Dos", "contenido": "cuerpo dos"},
    ]


def test_no_sections_when_there_are_no_headings():
    assert md.secciones("solo texto\nen dos lineas") == []


def test_code_blocks_with_a_language():
    texto = "antes\n```python\nprint(1)\nprint(2)\n```\ndespues"
    assert md.bloques_codigo(texto) == [
        {"lenguaje": "python", "codigo": "print(1)\nprint(2)"}
    ]


def test_unclosed_code_blocks_are_saved_anyway():
    assert md.bloques_codigo("```\nabc") == [{"lenguaje": "", "codigo": "abc"}]


def test_checked_and_unchecked_checkboxes():
    texto = "- [x] hecho\n- [ ] pendiente\n- [X] tambien hecho"
    assert md.casillas(texto) == [
        {"marcada": True, "texto": "hecho"},
        {"marcada": False, "texto": "pendiente"},
        {"marcada": True, "texto": "tambien hecho"},
    ]


def test_checkboxes_inside_a_code_block_are_ignored():
    texto = "- [x] real\n```\n- [ ] falsa\n```"
    assert md.casillas(texto) == [{"marcada": True, "texto": "real"}]
