"""Umbral, slug y troceo sintactico."""

import pytest

from claude_informes import markdown as md


# --- umbral: estrictamente mas de N lineas de markdown CRUDO ---


def test_umbral_justo_en_el_limite_no_pasa():
    assert md.supera_umbral("1\n2\n3\n4\n5", 5) is False


def test_umbral_una_linea_mas_pasa():
    assert md.supera_umbral("1\n2\n3\n4\n5\n6", 5) is True


def test_umbral_cuenta_lineas_no_caracteres():
    largo_de_una_linea = "x" * 5000
    assert md.supera_umbral(largo_de_una_linea, 5) is False


def test_umbral_cuenta_lineas_en_blanco():
    assert md.supera_umbral("a\n\n\n\n\n\nb", 5) is True


def test_umbral_cuenta_lineas_crudas_dentro_de_bloques_de_codigo():
    texto = "Mira:\n```py\n1\n2\n3\n4\n```"
    assert md.supera_umbral(texto, 5) is True


def test_umbral_con_crlf():
    assert md.supera_umbral("1\r\n2\r\n3\r\n4\r\n5\r\n6", 5) is True


# --- palabras significativas ---


def test_se_descartan_articulos_y_preposiciones_en_espanol():
    assert md.palabras_significativas("el informe de la sesion") == ["informe", "sesion"]


def test_se_descartan_articulos_y_preposiciones_en_ingles():
    assert md.palabras_significativas("the report of the session") == [
        "report",
        "session",
    ]


def test_los_numeros_sueltos_no_cuentan_como_palabra():
    assert md.palabras_significativas("1. 2026 transcript") == ["transcript"]


def test_un_identificador_alfanumerico_si_cuenta():
    assert md.palabras_significativas("commit ac72eff") == ["commit", "ac72eff"]


# --- slug, regla 1: primer encabezado con 3+ palabras significativas ---


def test_un_encabezado_rico_se_usa_tal_cual():
    texto = "# Informe de la sesion de hoy\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "informe-sesion-hoy"


def test_el_nivel_del_encabezado_da_igual():
    texto = "### Barrido del arbol terminado\ncosas"
    assert md.nombre_desde_markdown(texto) == "barrido-arbol-terminado"


def test_se_quitan_acentos_y_marcas_inline():
    texto = "# **Investigación** del `transcript` y hooks"
    assert md.nombre_desde_markdown(texto) == "investigacion-transcript-hooks"


def test_se_quita_la_numeracion_inicial():
    """El caso real que daba '1-transcript'."""
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
def test_la_numeracion_se_quita_en_todas_sus_variantes(encabezado):
    assert md.nombre_desde_markdown(encabezado + "\n\ncuerpo") == "uno-dos-tres"


# --- slug, regla 2: concatenar encabezados sucesivos ---


def test_un_encabezado_pobre_se_concatena_con_el_siguiente():
    """El caso real que daba 'tabla'."""
    texto = "## Tabla\n\nfila\n\n## Veredicto final\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "tabla-veredicto-final"


def test_se_concatenan_tantos_encabezados_como_hagan_falta():
    texto = "## Tabla\n\n## Resumen\n\n## Fin\n\n## Sobra\n\ntexto"
    assert md.nombre_desde_markdown(texto) == "tabla-resumen-fin"


def test_la_concatenacion_para_al_llegar_a_tres_palabras():
    texto = "## Tabla\n\n## Veredicto final del barrido completo\n\n## Sobra\n\nx"
    assert "sobra" not in md.nombre_desde_markdown(texto)


# --- slug, regla 3: el cuerpo ---


def test_sin_encabezados_se_usan_las_palabras_del_cuerpo():
    texto = "Hecho. Sin push. El commit ac72eff queda listo y verde."
    assert md.nombre_desde_markdown(texto) == (
        "hecho-push-commit-ac72eff-queda-listo-verde"
    )


def test_si_los_encabezados_se_agotan_pobres_manda_el_cuerpo():
    texto = "## Tabla\n\nEl cuerpo tiene palabras utiles aqui"
    assert md.nombre_desde_markdown(texto) == "cuerpo-tiene-palabras-utiles-aqui"


def test_un_encabezado_de_solo_simbolos_no_aporta_nada():
    texto = "### ???\n\n### !!!\n\nEl cuerpo si tiene palabras utiles"
    assert md.nombre_desde_markdown(texto) == "cuerpo-tiene-palabras-utiles"


def test_los_encabezados_dentro_de_un_bloque_de_codigo_no_cuentan():
    texto = "```sh\n# no soy un titulo\n```\nTexto real de la respuesta larga"
    assert md.nombre_desde_markdown(texto) == "texto-real-respuesta-larga"


def test_el_cuerpo_no_recoge_las_lineas_de_encabezado():
    texto = "## Tabla\n\ncuerpo de verdad con palabras"
    assert "tabla" not in md.nombre_desde_markdown(texto)


def test_sin_nada_slugificable_queda_un_nombre_de_reserva():
    assert md.nombre_desde_markdown("### ???\n\n!!!") == "sin-titulo"


def test_un_markdown_vacio_no_revienta():
    assert md.nombre_desde_markdown("") == "sin-titulo"


# --- slug, regla 4: tope de longitud ---


def test_el_slug_se_recorta_sin_partir_palabras():
    largo = "# " + " ".join(["palabra"] * 30)
    slug = md.nombre_desde_markdown(largo)

    assert len(slug) <= md.TOPE
    assert not slug.endswith("-")
    assert all(trozo == "palabra" for trozo in slug.split("-"))


def test_una_sola_palabra_larguisima_se_corta_igual():
    slug = md.nombre_desde_markdown("# " + "x" * 200)
    assert len(slug) <= md.TOPE


def test_recortar_una_palabra_mas_larga_que_el_tope_corta_duro():
    """Caso degenerado, fijado: una sola palabra sin guion mas larga que el tope
    no cabe en ninguna frontera de palabra. Como el resultado es un NOMBRE DE
    FICHERO, el tope es DURO: se corta duro y el resultado NUNCA excede el tope,
    aunque eso parta la palabra. Un cap blando que devolviera la palabra entera
    (mas de TOPE) fallaria aqui.
    """
    resultado = md.recortar("x" * 300)

    assert len(resultado) <= md.TOPE, "el tope es duro: nunca se excede"
    assert len(resultado) == md.TOPE, "una palabra de 300 se corta justo al tope"


# --- slug llano, para nombres propios ---


def test_el_slug_llano_no_descarta_palabras():
    assert md.slug_llano("Mi Repo de la Empresa") == "mi-repo-de-la-empresa"


# --- troceo sintactico ---


def test_secciones_por_encabezados():
    texto = "# Uno\ncuerpo uno\n\n## Dos\ncuerpo dos"
    assert md.secciones(texto) == [
        {"nivel": 1, "titulo": "Uno", "contenido": "cuerpo uno"},
        {"nivel": 2, "titulo": "Dos", "contenido": "cuerpo dos"},
    ]


def test_secciones_vacias_si_no_hay_encabezados():
    assert md.secciones("solo texto\nen dos lineas") == []


def test_bloques_de_codigo_con_lenguaje():
    texto = "antes\n```python\nprint(1)\nprint(2)\n```\ndespues"
    assert md.bloques_codigo(texto) == [
        {"lenguaje": "python", "codigo": "print(1)\nprint(2)"}
    ]


def test_bloques_de_codigo_sin_cerrar_se_guardan_igual():
    assert md.bloques_codigo("```\nabc") == [{"lenguaje": "", "codigo": "abc"}]


def test_casillas_marcadas_y_sin_marcar():
    texto = "- [x] hecho\n- [ ] pendiente\n- [X] tambien hecho"
    assert md.casillas(texto) == [
        {"marcada": True, "texto": "hecho"},
        {"marcada": False, "texto": "pendiente"},
        {"marcada": True, "texto": "tambien hecho"},
    ]


def test_casillas_ignora_las_de_dentro_de_un_bloque_de_codigo():
    texto = "- [x] real\n```\n- [ ] falsa\n```"
    assert md.casillas(texto) == [{"marcada": True, "texto": "real"}]
