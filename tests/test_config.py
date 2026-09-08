"""Lista blanca de proyectos y lectura de la configuracion."""

from pathlib import Path

from claude_informes import config as cfg


def test_solo_los_proyectos_de_la_config_entran(escribir_config, tmp_path):
    dentro = tmp_path / "dentro"
    fuera = tmp_path / "fuera"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(dentro), "activo": True}]))

    assert cfg.buscar_proyecto(str(dentro), configuracion) is not None
    assert cfg.buscar_proyecto(str(fuera), configuracion) is None


def test_un_proyecto_desactivado_no_entra(escribir_config, tmp_path):
    raiz = tmp_path / "pausado"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(raiz), "activo": False}]))
    assert cfg.buscar_proyecto(str(raiz), configuracion) is None


def test_los_subdirectorios_del_proyecto_entran(escribir_config, tmp_path):
    raiz = tmp_path / "repo"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(raiz), "activo": True}]))
    encontrado = cfg.buscar_proyecto(str(raiz / "src" / "hondo"), configuracion)
    assert encontrado is not None and encontrado.raiz == str(raiz)


def test_un_hermano_con_prefijo_comun_no_entra(escribir_config, tmp_path):
    raiz = tmp_path / "repo"
    hermano = tmp_path / "repo-otro"
    configuracion = cfg.cargar(escribir_config([{"cwd": str(raiz), "activo": True}]))
    assert cfg.buscar_proyecto(str(hermano), configuracion) is None


def test_gana_la_raiz_mas_especifica(escribir_config, tmp_path):
    padre = tmp_path / "monorepo"
    hijo = padre / "paquetes" / "uno"
    configuracion = cfg.cargar(
        escribir_config(
            [
                {"nombre": "padre", "cwd": str(padre), "activo": True},
                {"nombre": "hijo", "cwd": str(hijo), "activo": True},
            ]
        )
    )
    encontrado = cfg.buscar_proyecto(str(hijo), configuracion)
    assert encontrado is not None and encontrado.nombre == "hijo"


def test_cwd_ausente_o_absurdo_no_entra(escribir_config, tmp_path):
    configuracion = cfg.cargar(
        escribir_config([{"cwd": str(tmp_path / "x"), "activo": True}])
    )
    assert cfg.buscar_proyecto(None, configuracion) is None
    assert cfg.buscar_proyecto("", configuracion) is None
    assert cfg.buscar_proyecto("   ", configuracion) is None


def test_config_inexistente_no_deja_ningun_proyecto(tmp_path):
    assert cfg.cargar(tmp_path / "no-existe.json").proyectos == []


def test_config_rota_no_deja_ningun_proyecto(tmp_path):
    ruta = tmp_path / "rota.json"
    ruta.write_text("{esto no es json", encoding="utf-8")
    assert cfg.cargar(ruta).proyectos == []


def test_entradas_basura_se_descartan_una_a_una(escribir_config, tmp_path):
    buena = tmp_path / "buena"
    configuracion = cfg.cargar(
        escribir_config(["no soy un objeto", {"activo": True}, {"cwd": str(buena)}])
    )
    assert [p.raiz for p in configuracion.proyectos] == [str(buena)]


def test_valores_por_defecto(escribir_config, tmp_path):
    configuracion = cfg.cargar(escribir_config([{"cwd": str(tmp_path / "r")}]))
    assert configuracion.proyectos[0].activo is True
    assert configuracion.proyectos[0].umbral_lineas == 5


def test_umbral_invalido_cae_al_por_defecto(escribir_config, tmp_path):
    configuracion = cfg.cargar(
        escribir_config([{"cwd": str(tmp_path / "r"), "umbral_lineas": "muchas"}])
    )
    assert configuracion.proyectos[0].umbral_lineas == 5


# --- el nombre del proyecto ---


def test_el_nombre_sale_de_la_config_no_del_directorio(escribir_config, tmp_path):
    """Un rename del directorio no debe partir el historico."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "loopward", "cwd": str(tmp_path / "loopward-renombrado")}]
        )
    )
    assert configuracion.proyectos[0].nombre == "loopward"


def test_sin_nombre_se_usa_el_del_directorio(escribir_config, tmp_path):
    configuracion = cfg.cargar(escribir_config([{"cwd": str(tmp_path / "Mi Repo")}]))
    assert configuracion.proyectos[0].nombre == "mi-repo"


# --- raiz de informes ---


def test_la_raiz_de_informes_sale_de_la_config(escribir_config, tmp_path):
    destino = tmp_path / "archivo"
    configuracion = cfg.cargar(escribir_config([], raiz_informes=destino))
    assert configuracion.raiz_informes == destino


def test_sin_raiz_declarada_se_usa_la_de_la_herramienta(escribir_config, tmp_path):
    configuracion = cfg.cargar(escribir_config([{"cwd": str(tmp_path)}]))
    assert configuracion.raiz_informes == cfg.raiz_de_la_herramienta() / "informes"


def test_la_raiz_por_defecto_esta_dentro_de_la_herramienta():
    assert cfg.raiz_informes_por_defecto().parent == cfg.raiz_de_la_herramienta()


# --- la propia herramienta: un proyecto mas ---


def test_el_propio_claude_informes_puede_ser_un_proyecto_vigilado(escribir_config):
    """La guardia que lo impedia se retiro con su motivo.

    Mientras el archivo vivia dentro de `claude-informes/informes/`, un turno
    suyo habria escrito en su propia carpeta de salida. Con el archivo en una
    raiz propia fuera de todo repo, lo unico que hacia la guardia era tirar
    los turnos de quien trabajaba en la herramienta.
    """
    propia = cfg.raiz_de_la_herramienta()
    configuracion = cfg.cargar(
        escribir_config([{"nombre": "claude-informes", "cwd": str(propia)}])
    )
    encontrado = cfg.buscar_proyecto(str(propia), configuracion)
    assert encontrado is not None
    assert encontrado.nombre == "claude-informes"


def test_un_subdirectorio_de_la_herramienta_tambien_mapea(escribir_config):
    propia = cfg.raiz_de_la_herramienta()
    configuracion = cfg.cargar(escribir_config([{"cwd": str(propia)}]))
    assert cfg.buscar_proyecto(str(propia / "claude_informes"), configuracion) is not None
    assert cfg.buscar_proyecto(str(propia / "tests"), configuracion) is not None


def test_la_guardia_reconoce_la_herramienta():
    propia = cfg.raiz_de_la_herramienta()
    assert cfg.es_la_propia_herramienta(str(propia)) is True
    assert cfg.es_la_propia_herramienta(str(propia / "tests")) is True
    assert cfg.es_la_propia_herramienta(str(propia.parent)) is False
    assert cfg.es_la_propia_herramienta(None) is False


# Los tests que afirmaban sobre "la config real del repo" se retiraron: la
# config real ya no vive en el repositorio (vive en la config de usuario del
# SO). La invariante equivalente -que el EJEMPLO sea JSON valido y no lleve
# rutas reales, y que el archivo caiga fuera de todo repo- se comprueba ahora
# en test_publicable.py y test_config_ubicacion.py.


# --- raiz por proyecto ---


def test_la_raiz_del_proyecto_anula_la_global(escribir_config, tmp_path):
    suya = tmp_path / "aparte"
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "project-b", "cwd": str(tmp_path / "co"), "raiz_informes": suya}],
            raiz_informes=tmp_path / "comun",
        )
    )
    assert configuracion.raiz_informes == tmp_path / "comun"
    assert configuracion.proyectos[0].raiz_informes == suya


def test_sin_raiz_propia_el_proyecto_hereda_la_global(escribir_config, tmp_path):
    comun = tmp_path / "comun"
    configuracion = cfg.cargar(
        escribir_config([{"nombre": "loopward", "cwd": str(tmp_path / "lw")}], raiz_informes=comun)
    )
    assert configuracion.proyectos[0].raiz_informes == comun


def test_cada_proyecto_puede_ir_a_una_raiz_distinta(escribir_config, tmp_path):
    configuracion = cfg.cargar(
        escribir_config(
            [
                {"nombre": "publico", "cwd": str(tmp_path / "a")},
                {"nombre": "sensible", "cwd": str(tmp_path / "b"), "raiz_informes": tmp_path / "cofre"},
            ],
            raiz_informes=tmp_path / "comun",
        )
    )
    por_raiz = {p.nombre: p.raiz_informes for p in configuracion.proyectos}
    assert por_raiz["publico"] == tmp_path / "comun"
    assert por_raiz["sensible"] == tmp_path / "cofre"


def test_una_raiz_propia_invalida_cae_a_la_global(escribir_config, tmp_path):
    comun = tmp_path / "comun"
    configuracion = cfg.cargar(
        escribir_config(
            [{"cwd": str(tmp_path / "x"), "raiz_informes": "   "}], raiz_informes=comun
        )
    )
    assert configuracion.proyectos[0].raiz_informes == comun


