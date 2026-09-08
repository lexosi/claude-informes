"""Backfill: reconstruir informes de turnos pasados desde un transcript."""

import json

import pytest

from claude_informes import backfill as bf
from claude_informes import cli
from claude_informes import informe as inf
from claude_informes import transcript as tr

LARGO_A = "# Primer turno del barrido\n\nuno\ndos\ntres\ncuatro"
LARGO_B = "# Segundo turno del barrido\n\nuno\ndos\ntres\ncuatro"
LARGO_C = "# Tercer turno cerrado\n\nuno\ndos\ntres\ncuatro"
LARGO_D = "# Turno de la vispera anterior\n\nuno\ndos\ntres\ncuatro"

SLUG_A = "01-primer-turno-barrido.json"
SLUG_B = "02-segundo-turno-barrido.json"
SLUG_C = "03-tercer-turno-cerrado.json"


def fecha_local(marca):
    """La fecha que la herramienta asignara a esa marca de tiempo."""
    return inf.construir("x", session_id=None, cwd=None, cuando=marca)["fecha"]


AYER = fecha_local("2026-08-27T10:00:00Z")
HOY = fecha_local("2026-08-28T10:00:00Z")


def turno(texto, *, marca="2026-08-28T10:00:00Z", uuid="u1", cwd="C:\\repo", sesion="s1"):
    return {
        "type": "assistant",
        "uuid": uuid,
        "timestamp": marca,
        "sessionId": sesion,
        "cwd": cwd,
        "gitBranch": "main",
        "message": {
            "stop_reason": "end_turn",
            "content": [{"type": "text", "text": texto}],
        },
    }


def ruido():
    """Registros que el backfill debe ignorar."""
    return [
        {"type": "user", "message": {"content": "hola"}},
        {"type": "attachment", "payload": {}},
        {
            "type": "assistant",
            "message": {
                "stop_reason": "tool_use",
                "content": [{"type": "text", "text": "voy a mirar"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "stop_reason": "end_turn",
                "content": [{"type": "thinking", "thinking": "mmm"}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "stop_reason": "end_turn",
                "content": [{"type": "text", "text": "   "}],
            },
        },
        {
            "type": "assistant",
            "message": {
                "stop_reason": "max_tokens",
                "content": [{"type": "text", "text": "cortado"}],
            },
        },
    ]


def escribir_transcript(ruta, registros, lineas_rotas=()):
    lineas = [json.dumps(r) for r in registros]
    lineas.extend(lineas_rotas)
    ruta.write_text("\n".join(lineas) + "\n", encoding="utf-8")
    return ruta


@pytest.fixture
def transcripcion(tmp_path):
    ruta = tmp_path / "sesion.jsonl"
    registros = ruido() + [
        turno(LARGO_A, marca="2026-08-28T09:00:00Z", uuid="a"),
        turno("corto\ndos\ntres", marca="2026-08-28T09:10:00Z", uuid="b"),
        turno(LARGO_B, marca="2026-08-28T10:00:00Z", uuid="c"),
        turno(LARGO_C, marca="2026-08-28T11:00:00Z", uuid="d"),
    ]
    return escribir_transcript(ruta, registros, lineas_rotas=["{no soy json", ""])


def nombres(raiz, proyecto="repo", fecha=None):
    dia = raiz / proyecto / (fecha or HOY)
    return sorted(p.name for p in dia.glob("*.json")) if dia.is_dir() else []


# --- lectura del transcript ---


def test_solo_se_recogen_los_turnos_cerrados_con_texto(transcripcion):
    assert [t["uuid"] for t in tr.turnos(transcripcion)] == ["a", "b", "c", "d"]


def test_las_lineas_rotas_no_tumban_la_lectura(transcripcion):
    assert len(tr.turnos(transcripcion)) == 4


def test_un_transcript_inexistente_da_lista_vacia(tmp_path):
    assert tr.turnos(tmp_path / "no-existe.jsonl") == []


def test_ultimo_turno_es_el_ultimo_del_fichero(transcripcion):
    assert tr.ultimo_turno(transcripcion)["uuid"] == "d"


# --- reconstruccion ---


def test_un_fichero_por_turno(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    resultados = bf.reconstruir(transcripcion, raiz, "repo")

    escritos = [r for r in resultados if r["escrito"]]
    assert len(escritos) == 3
    assert len(nombres(raiz)) == 3
    assert len({r["ruta"] for r in escritos}) == 3


def test_los_turnos_cortos_se_omiten_por_umbral(transcripcion, tmp_path):
    resultados = bf.reconstruir(transcripcion, tmp_path / "archivo", "repo")
    omitidos = [r for r in resultados if not r["escrito"]]
    assert len(omitidos) == 1
    assert "umbral" in omitidos[0]["motivo"]


def test_los_nombres_son_ordinal_y_slug_sin_fecha(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")

    assert nombres(raiz) == [SLUG_A, SLUG_B, SLUG_C]
    assert all(HOY not in nombre for nombre in nombres(raiz))


def test_cada_informe_conserva_su_propio_markdown(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")

    dia = raiz / "repo" / HOY
    sobres = [json.loads(p.read_text("utf-8")) for p in sorted(dia.glob("*.json"))]
    assert [s["respuesta_markdown"] for s in sobres] == [LARGO_A, LARGO_B, LARGO_C]


def test_los_metadatos_vienen_del_registro_no_del_reloj(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")

    sobre = json.loads((raiz / "repo" / HOY / SLUG_A).read_text("utf-8"))
    assert sobre["fecha"] == HOY
    assert sobre["session_id"] == "s1"
    assert sobre["cwd"] == "C:\\repo"
    assert sobre["git_branch"] == "main"


def test_cada_dia_va_a_su_carpeta_y_el_ordinal_reinicia(tmp_path):
    ruta = escribir_transcript(
        tmp_path / "sesion.jsonl",
        [
            turno(LARGO_D, marca="2026-08-27T10:00:00Z", uuid="v"),
            turno(LARGO_A, marca="2026-08-28T09:00:00Z", uuid="a"),
            turno(LARGO_B, marca="2026-08-28T10:00:00Z", uuid="c"),
        ],
    )
    raiz = tmp_path / "archivo"
    bf.reconstruir(ruta, raiz, "repo")

    assert sorted(p.name for p in (raiz / "repo").iterdir()) == [AYER, HOY]
    assert nombres(raiz, fecha=AYER) == ["01-turno-vispera-anterior.json"]
    assert nombres(raiz) == [SLUG_A, SLUG_B]


def test_una_carpeta_de_dia_con_ficheros_continua_el_ordinal(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    dia = raiz / "repo" / HOY
    dia.mkdir(parents=True)
    (dia / "01-migrado-a-mano.json").write_text("{}", encoding="utf-8")

    bf.reconstruir(transcripcion, raiz, "repo")

    assert nombres(raiz) == [
        "01-migrado-a-mano.json",
        "02-primer-turno-barrido.json",
        "03-segundo-turno-barrido.json",
        "04-tercer-turno-cerrado.json",
    ]


def test_las_carpetas_existentes_se_reutilizan(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    (raiz / "repo" / HOY).mkdir(parents=True)

    bf.reconstruir(transcripcion, raiz, "repo")

    assert [p.name for p in raiz.iterdir()] == ["repo"]
    assert [p.name for p in (raiz / "repo").iterdir()] == [HOY]


def test_dos_proyectos_distintos_no_se_mezclan(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "uno")
    bf.reconstruir(transcripcion, raiz, "dos")

    assert sorted(p.name for p in raiz.iterdir()) == ["dos", "uno"]
    assert nombres(raiz, "uno") == nombres(raiz, "dos") == [SLUG_A, SLUG_B, SLUG_C]


def test_dos_pasadas_no_pisan_los_informes_anteriores(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo")
    bf.reconstruir(transcripcion, raiz, "repo")

    assert len(nombres(raiz)) == 6
    assert "04-primer-turno-barrido.json" in nombres(raiz)


def test_limite_coge_los_ultimos_turnos(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo", limite=1)
    assert nombres(raiz) == ["01-tercer-turno-cerrado.json"]


def test_la_simulacion_no_escribe_nada(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    resultados = bf.reconstruir(transcripcion, raiz, "repo", simular=True)

    assert not raiz.exists()
    assert all(not r["escrito"] for r in resultados)


def test_el_umbral_del_backfill_es_configurable(transcripcion, tmp_path):
    raiz = tmp_path / "archivo"
    bf.reconstruir(transcripcion, raiz, "repo", umbral=2)
    assert len(nombres(raiz)) == 4


# --- localizacion del transcript ---


def test_se_localiza_el_transcript_por_sesion(tmp_path):
    raiz = tmp_path / "projects" / "C--repo"
    raiz.mkdir(parents=True)
    esperado = escribir_transcript(raiz / "abc-123.jsonl", [turno(LARGO_A)])

    assert tr.localizar(session_id="abc-123", raiz=tmp_path / "projects") == esperado


def test_se_localiza_el_transcript_mas_reciente_del_proyecto(tmp_path):
    import os

    base = tmp_path / "projects"
    carpeta = base / "C--repo"
    carpeta.mkdir(parents=True)
    viejo = escribir_transcript(carpeta / "viejo.jsonl", [turno(LARGO_A)])
    nuevo = escribir_transcript(carpeta / "nuevo.jsonl", [turno(LARGO_B)])
    os.utime(viejo, (1, 1))

    assert tr.localizar(cwd="C:\\repo", raiz=base) == nuevo


def test_sin_transcript_se_devuelve_none(tmp_path):
    assert tr.localizar(cwd="C:\\ninguno", raiz=tmp_path) is None


# --- la orden de consola ---


def test_la_orden_escribe_en_la_raiz_indicada(transcripcion, tmp_path, capsys):
    raiz = tmp_path / "fuera"
    codigo = cli.main(
        [
            "backfill",
            "--transcript",
            str(transcripcion),
            "--salida",
            str(raiz),
            "--proyecto",
            "repo",
        ]
    )
    assert codigo == 0
    assert nombres(raiz) == [SLUG_A, SLUG_B, SLUG_C]
    assert "3 informe(s) escrito(s)" in capsys.readouterr().out


def test_la_orden_respeta_la_lista_blanca(transcripcion, tmp_path, capsys):
    codigo = cli.main(
        [
            "backfill",
            "--transcript",
            str(transcripcion),
            "--config",
            str(tmp_path / "x.json"),
        ]
    )
    assert codigo == 3
    assert "no esta en la lista" in capsys.readouterr().err
    assert list(tmp_path.glob("**/*.json")) == []


def test_la_orden_usa_la_raiz_y_el_nombre_de_la_config(
    transcripcion, escribir_config, tmp_path
):
    proyecto = tmp_path / "repo-renombrado"
    proyecto.mkdir()
    archivo = tmp_path / "archivo"
    ruta_config = escribir_config(
        [{"nombre": "repo", "cwd": str(proyecto), "activo": True}],
        raiz_informes=archivo,
    )

    codigo = cli.main(
        [
            "backfill",
            "--transcript",
            str(transcripcion),
            "--cwd",
            str(proyecto),
            "--config",
            str(ruta_config),
        ]
    )
    assert codigo == 0
    assert nombres(archivo) == [SLUG_A, SLUG_B, SLUG_C]


def test_la_orden_avisa_si_no_hay_transcript(tmp_path, capsys):
    codigo = cli.main(["backfill", "--transcript", str(tmp_path / "no.jsonl")])
    assert codigo == 2
    assert "No se ha encontrado" in capsys.readouterr().err
