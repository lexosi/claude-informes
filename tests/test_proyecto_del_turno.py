"""De donde sale el proyecto: de la SESION, no de donde este la shell.

El `cwd` del payload sigue a los `cd` que se hagan durante el turno. Archivar
por el falla en las dos direcciones: mete turnos de un proyecto no vigilado en
la carpeta de uno vigilado, y pierde turnos de uno vigilado cuando la shell se
ha ido. Un archivo del que no te puedes fiar no sirve de nada.
"""

import io
import json
from datetime import datetime
from pathlib import Path

from claude_informes import config as cfg
from claude_informes import hook as hk
from claude_informes import registro as reg
from claude_informes import transcript as tr

RESPUESTA = "# Informe de la prueba diaria\n\nlinea 1\nlinea 2\nlinea 3\nlinea 4\n"


def hoy():
    return datetime.now().strftime("%Y-%m-%d")


def transcript_de(raiz_de_arranque):
    """Donde Claude Code pone el transcript de una sesion abierta ahi."""
    return str(
        Path("C:/proyectos") / tr.slug_de_cwd(str(raiz_de_arranque)) / "sesion.jsonl"
    )


def turno(cwd, transcript, texto=RESPUESTA):
    return {
        "session_id": "s",
        "cwd": str(cwd),
        "transcript_path": transcript,
        "stop_hook_active": False,
        "last_assistant_message": texto,
    }


def ejecutar(datos, ruta_config):
    return hk.main(entrada=io.StringIO(json.dumps(datos)), ruta_config=ruta_config)


def escritos(informes, proyecto, fecha=None):
    dia = Path(informes) / proyecto / (fecha or hoy())
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- el mapeo del slug al proyecto ---


def test_el_slug_del_directorio_se_mapea_al_nombre_de_la_config(
    escribir_config, informes, tmp_path
):
    """`e--example-projects-loopward` -> `loopward`, via el cwd declarado."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "loopward", "cwd": "E:\\example-projects\\loopward"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\Users\\x\\.claude\\projects\\E--example-projects-loopward\\abc.jsonl"

    proyecto = hk.proyecto_del_transcript(ruta, configuracion)
    assert proyecto is not None and proyecto.nombre == "loopward"


def test_el_mapeo_no_depende_del_nombre_del_directorio_sino_del_cwd(
    escribir_config, informes, tmp_path
):
    """El nombre de carpeta puede no parecerse al slug: manda el cwd."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "informes-del-curro", "cwd": "E:\\example-projects\\project-b"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\E--example-projects-project-b\\abc.jsonl"

    proyecto = hk.proyecto_del_transcript(ruta, configuracion)
    assert proyecto is not None and proyecto.nombre == "informes-del-curro"


def test_un_slug_de_un_hermano_no_se_confunde_con_un_subdirectorio(
    escribir_config, informes
):
    """`loopward-audit` es otro proyecto, no `loopward/audit`. Sin exactitud,
    no hay mapeo: el slug es ambiguo y no se intenta deshacer."""
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "loopward", "cwd": "E:\\example-projects\\loopward"}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\E--example-projects-loopward-audit\\abc.jsonl"

    assert hk.proyecto_del_transcript(ruta, configuracion) is None


def test_un_proyecto_desactivado_no_se_mapea(escribir_config, informes):
    configuracion = cfg.cargar(
        escribir_config(
            [{"nombre": "loopward", "cwd": "E:\\example-projects\\loopward", "activo": False}],
            raiz_informes=informes,
        )
    )
    ruta = "C:\\p\\E--example-projects-loopward\\abc.jsonl"

    assert hk.proyecto_del_transcript(ruta, configuracion) is None


# --- el fallo original, en sus dos direcciones ---


def test_dos_turnos_con_cwd_distinto_van_al_mismo_proyecto(
    escribir_config, informes, tmp_path, log
):
    """El caso real: entre turno y turno, la shell se movio."""
    raiz = tmp_path / "loopward"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(raiz)}], raiz_informes=informes
    )
    transcript = transcript_de(raiz)

    ejecutar(turno(raiz, transcript, RESPUESTA + "A"), ruta_config)
    ejecutar(turno(raiz / "subdir" / "hondo", transcript, RESPUESTA + "B"), ruta_config)
    ejecutar(turno("E:\\otro\\sitio\\del\\todo", transcript, RESPUESTA + "C"), ruta_config)

    assert len(escritos(informes, "loopward")) == 3
    assert [p.name for p in Path(informes).iterdir()] == ["loopward"]
    assert all(a.resultado == reg.ESCRITO for a in reg.leer(log))


def test_un_turno_de_una_sesion_no_vigilada_no_se_archiva_aunque_el_cwd_lo_este(
    escribir_config, informes, tmp_path, log
):
    """La direccion peligrosa: la shell dentro de loopward, la sesion no."""
    vigilado = tmp_path / "loopward"
    vigilado.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(vigilado)}], raiz_informes=informes
    )

    datos = turno(vigilado, transcript_de(tmp_path / "example-projects"))
    assert ejecutar(datos, ruta_config) == 0

    assert not Path(informes).exists(), "la sesion manda sobre el cwd"
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert "proyecto no registrado" in anotacion.detalle


def test_un_turno_de_una_sesion_vigilada_no_se_pierde_por_un_cd(
    escribir_config, informes, tmp_path
):
    """La otra direccion: la sesion en loopward, la shell fuera."""
    vigilado = tmp_path / "loopward"
    vigilado.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(vigilado)}], raiz_informes=informes
    )

    datos = turno("C:\\donde\\sea", transcript_de(vigilado))
    ejecutar(datos, ruta_config)

    assert len(escritos(informes, "loopward")) == 1


# --- camino degradado: cae al cwd, pero se ve ---


def test_sin_transcript_path_se_cae_al_cwd_y_se_anota(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "loopward"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(turno(raiz, ""), ruta_config)

    assert len(escritos(informes, "loopward")) == 1, "se archiva igual"
    aviso, escrito = reg.leer(log)
    assert aviso.resultado == reg.PROYECTO_POR_CWD
    assert "sin transcript_path" in aviso.detalle
    assert str(raiz) in aviso.detalle
    assert escrito.resultado == reg.ESCRITO


def test_un_slug_que_no_mapea_no_archiva_y_se_anota(
    escribir_config, informes, tmp_path, log
):
    """Con transcript, manda el transcript: no se cae al cwd.

    Caer al cwd aqui reabriria el agujero, porque una shell dentro de un
    proyecto vigilado volveria a archivar turnos de otra sesion.
    """
    raiz = tmp_path / "loopward"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(raiz)}], raiz_informes=informes
    )

    ejecutar(turno(raiz, "C:\\p\\slug-de-otra-cosa\\abc.jsonl"), ruta_config)

    assert not Path(informes).exists()
    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_SESION
    assert "slug-de-otra-cosa" in anotacion.detalle


def test_el_aviso_solo_aparece_cuando_el_camino_degradado_archiva(
    escribir_config, informes, tmp_path, log
):
    """Si el cwd tampoco vale, no hay nada que avisar: una sola linea."""
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(tmp_path / "loopward")}],
        raiz_informes=informes,
    )

    ejecutar(turno("E:\\nada\\que\\ver", ""), ruta_config)

    (anotacion,) = reg.leer(log)
    assert anotacion.resultado == reg.OMITIDO_CWD


def test_un_transcript_path_ilegible_no_revienta(escribir_config, informes, tmp_path):
    raiz = tmp_path / "loopward"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "loopward", "cwd": str(raiz)}], raiz_informes=informes
    )

    for basura in [None, 42, [], "   "]:
        datos = turno(raiz, "x")
        datos["transcript_path"] = basura
        assert ejecutar(datos, ruta_config) == 0


# --- lo que no cambia ---


def test_un_turno_de_la_propia_herramienta_se_archiva_como_cualquier_otro(
    escribir_config, informes
):
    """La herramienta dejo de ser un caso aparte cuando el archivo se mudo."""
    propia = cfg.raiz_de_la_herramienta()
    ruta_config = escribir_config(
        [{"nombre": "claude-informes", "cwd": str(propia)}], raiz_informes=informes
    )

    ejecutar(turno(propia, transcript_de(propia)), ruta_config)

    dia = Path(informes) / "claude-informes" / hoy()
    assert [p.name for p in dia.iterdir()] == ["01-informe-prueba-diaria.json"]


def test_el_umbral_sigue_siendo_el_del_proyecto_mapeado(
    escribir_config, informes, tmp_path, log
):
    raiz = tmp_path / "exigente"
    raiz.mkdir()
    ruta_config = escribir_config(
        [{"nombre": "exigente", "cwd": str(raiz), "umbral_lineas": 20}],
        raiz_informes=informes,
    )

    ejecutar(turno("C:\\otro\\sitio", transcript_de(raiz)), ruta_config)

    assert not Path(informes).exists()
    assert reg.leer(log)[0].resultado == reg.OMITIDO_UMBRAL
