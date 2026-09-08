"""Entrada de linea de ordenes: `hook`, `nuevo`, `ultimo`, `pendientes` y `backfill`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import alta
from . import backfill as bf
from . import config as cfg
from . import flujos
from . import hook as hk
from . import markdown as md
from . import registro as reg
from . import transcript as tr


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude-informes", description=__doc__)
    subs = parser.add_subparsers(dest="modo", required=True)

    p_hook = subs.add_parser("hook", help="lee el payload de Stop por stdin")
    p_hook.add_argument("--config", default=None)

    p_bf = subs.add_parser("backfill", help="reconstruye informes de turnos pasados")
    p_bf.add_argument("--transcript", help="ruta al .jsonl")
    p_bf.add_argument("--session", help="id de sesion; se busca el .jsonl")
    p_bf.add_argument(
        "--cwd",
        help="proyecto: localiza su transcript mas reciente y resuelve su config",
    )
    p_bf.add_argument(
        "--salida", default=None, help="raiz de informes; por defecto, la de la config"
    )
    p_bf.add_argument(
        "--proyecto", default=None, help="nombre de la carpeta de proyecto"
    )
    p_bf.add_argument("--umbral", type=int, default=None)
    p_bf.add_argument("--limite", type=int, default=None, help="ultimos N turnos")
    p_bf.add_argument("--config", default=None)
    p_bf.add_argument("--dry-run", action="store_true")

    p_ult = subs.add_parser("ultimo", help="el ultimo informe escrito, verificado en disco")
    p_ult.add_argument("--proyecto", default=None, help="por defecto, cualquiera")
    p_ult.add_argument("--config", default=None)

    p_new = subs.add_parser("nuevo", help="crea la carpeta del proyecto y lo registra")
    p_new.add_argument("nombre")
    p_new.add_argument(
        "--en", default=None, help="donde crear la carpeta; por defecto, junto a esta herramienta"
    )
    p_new.add_argument("--umbral", type=int, default=cfg.UMBRAL_POR_DEFECTO)
    p_new.add_argument("--raiz-informes", default=None, help="archivar este proyecto aparte")
    p_new.add_argument("--config", default=None)

    p_pen = subs.add_parser(
        "pendientes", help="turnos que no se archivaron por proyecto no registrado"
    )
    p_pen.add_argument("--config", default=None)

    p_ini = subs.add_parser(
        "init", help="crea la config de usuario a partir del ejemplo, la primera vez"
    )
    p_ini.add_argument(
        "--config", default=None, help="donde crearla; por defecto, la ubicacion estandar del SO"
    )
    return parser


def _sin_config(args) -> bool:
    """No hay config utilizable: ni --config, ni entorno, ni fichero de usuario."""
    return not args.config and cfg.ruta_de_config() is None


def _resolver_transcript(args) -> Path | None:
    if args.transcript:
        ruta = Path(args.transcript)
        return ruta if ruta.is_file() else None
    return tr.localizar(cwd=args.cwd, session_id=args.session)


def _ejecutar_backfill(args) -> int:
    if not (args.transcript or args.session or args.cwd):
        print("Indica --transcript, --session o --cwd.", file=sys.stderr)
        return 2
    ruta = _resolver_transcript(args)
    if ruta is None:
        print("No se ha encontrado el transcript.", file=sys.stderr)
        return 2

    turnos = tr.turnos(ruta)
    if not turnos:
        print(f"{ruta}: sin turnos cerrados.", file=sys.stderr)
        return 1

    cwd_transcript = args.cwd or turnos[-1].get("cwd") or ""
    configuracion = cfg.cargar(args.config)
    proyecto = cfg.buscar_proyecto(cwd_transcript, configuracion)
    umbral = args.umbral

    if proyecto is None and not args.salida:
        print(
            f"{cwd_transcript!r} no esta en la lista de proyectos. "
            "Usa --salida para escribir en otro sitio.",
            file=sys.stderr,
        )
        return 3

    raiz = Path(args.salida) if args.salida else (
        proyecto.raiz_informes if proyecto else configuracion.raiz_informes
    )
    nombre = args.proyecto or (
        proyecto.nombre if proyecto else md.slug_llano(Path(cwd_transcript).name)
    )
    if not nombre:
        print("No se ha podido deducir el nombre del proyecto. Usa --proyecto.", file=sys.stderr)
        return 4
    if umbral is None:
        umbral = proyecto.umbral_lineas if proyecto else cfg.UMBRAL_POR_DEFECTO

    print(f"transcript: {ruta}")
    print(f"salida    : {raiz / nombre}")
    resultados = bf.reconstruir(
        ruta, raiz, nombre, umbral=umbral, limite=args.limite, simular=args.dry_run
    )
    escritos = 0
    for entrada in resultados:
        if entrada["escrito"]:
            escritos += 1
            print(f"  + {Path(entrada['ruta']).name}")
        elif entrada["motivo"] == "simulacion":
            print(f"  ~ {Path(entrada['ruta']).name} (simulacion)")
        else:
            print(f"  - omitido: {entrada['motivo']}")
    print(f"{escritos} informe(s) escrito(s) de {len(resultados)} turno(s).")
    return 0


def _ejecutar_init(args) -> int:
    """Crea la config de usuario copiando el ejemplo. Idempotente: no pisa."""
    destino = Path(args.config) if args.config else cfg.ruta_config_usuario()
    if destino.exists():
        print(f"Ya existe una config de usuario: {destino}")
        print("No se ha tocado. Editala a mano si quieres cambiarla.")
        return 0
    try:
        contenido = cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"No se encuentra el ejemplo: {cfg.ruta_de_ejemplo()}", file=sys.stderr)
        return 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8", newline="\n")
    print(f"Config de usuario creada: {destino}")
    print("Editala y pon las rutas reales de tus proyectos y de la raiz de informes.")
    return 0


def _ejecutar_ultimo(args) -> int:
    """El log dice donde esta; el disco dice si es verdad. Manda el disco."""
    if _sin_config(args):
        print(cfg.mensaje_sin_config(), file=sys.stderr)
        return 2
    configuracion = cfg.cargar(args.config)
    anotaciones = reg.leer(configuracion.ruta_log)
    if not anotaciones:
        print(f"El log esta vacio o no existe: {configuracion.ruta_log}", file=sys.stderr)
        return 2

    anotacion = reg.ultimo_escrito(anotaciones, args.proyecto)
    if anotacion is None:
        de_quien = f" de {args.proyecto}" if args.proyecto else ""
        print(f"El log no registra ningun informe escrito{de_quien}.", file=sys.stderr)
        return 2

    ruta = anotacion.ruta
    print(f"proyecto : {anotacion.proyecto}")
    print(f"informe  : {ruta.name}")
    print(f"ruta     : {ruta}")
    print(f"anotado  : {anotacion.marca}")
    # El log registra un HECHO PASADO --que ese dia se escribio esto ahi--, no
    # un indice de ficheros vivos. Que el fichero siga o no en esa ruta es
    # informacion, no una alarma: renombrarlo o mover el archivo no convierte
    # la linea en mentira. Por eso todo esto sale por stdout y el codigo es 0.
    if ruta.is_file():
        print(f"estado   : sigue en disco, {ruta.stat().st_size} bytes")
    elif ruta.parent.is_dir():
        print(
            "estado   : ya no esta donde el log lo registro. Su carpeta del dia "
            "sigue ahi, asi que se renombro o se borro dentro de ella."
        )
    else:
        print(
            f"estado   : ya no esta donde el log lo registro, y su carpeta "
            f"({ruta.parent}) tampoco existe: el archivo entero se movio o se "
            f"relocalizo. El log conserva donde estaba el {anotacion.marca}."
        )
    return 0


def _ejecutar_nuevo(args) -> int:
    """Los tres pasos del arranque en uno, y en el orden correcto."""
    ruta_config = Path(args.config) if args.config else (
        cfg.ruta_de_config() or cfg.ruta_config_usuario()
    )
    donde = Path(args.en) if args.en else cfg.raiz_de_la_herramienta().parent
    try:
        carpeta, destino = alta.registrar(
            args.nombre,
            donde,
            ruta_config,
            umbral_lineas=args.umbral,
            raiz_informes=args.raiz_informes,
        )
    except alta.YaExiste as choque:
        print(f"No se ha registrado: {choque}", file=sys.stderr)
        return 3
    except Exception as error:  # noqa: BLE001
        print(f"No se ha podido registrar: {error}", file=sys.stderr)
        return 4

    print(f"carpeta   : {carpeta}")
    print(f"registrado: {destino}")
    print(f"Ya puedes abrir el CLI ahi:  cd {carpeta}")
    return 0


def _ejecutar_pendientes(args) -> int:
    """Lo que el log sabe de los turnos que no se archivaron."""
    if _sin_config(args):
        print(cfg.mensaje_sin_config(), file=sys.stderr)
        return 2
    configuracion = cfg.cargar(args.config)
    anotaciones = [
        a for a in reg.leer(configuracion.ruta_log) if a.resultado == reg.OMITIDO_SESION
    ]
    if not anotaciones:
        print("No hay turnos sin archivar por proyecto no registrado.")
        return 0

    por_proyecto: dict[tuple[str, str], int] = {}
    for anotacion in anotaciones:
        datos = dict(
            trozo.split("=", 1)
            for trozo in anotacion.detalle.split("; ")
            if "=" in trozo
        )
        clave = (datos.get("nombre", "?"), datos.get("transcript", "?"))
        por_proyecto[clave] = por_proyecto.get(clave, 0) + 1

    for (nombre, transcripcion), cuantos in sorted(por_proyecto.items()):
        print(f"{cuantos} turno(s) sin archivar de un proyecto no registrado: {nombre}")
        print(f"   transcript: {transcripcion}")
        print(f"   registrar : python -m claude_informes nuevo {nombre}")
        print(
            f"   recuperar : python -m claude_informes backfill "
            f'--transcript "{transcripcion}" --proyecto {nombre} '
            f'--salida "{configuracion.raiz_informes}"'
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    flujos.salida_en_utf8(sys.stdout, sys.stderr)
    argumentos = list(sys.argv[1:] if argv is None else argv)
    # El hook no debe fallar nunca, ni siquiera por un argparse enfadado.
    if argumentos and argumentos[0] == "hook":
        ruta_config = None
        if "--config" in argumentos:
            try:
                ruta_config = argumentos[argumentos.index("--config") + 1]
            except IndexError:
                ruta_config = None
        return hk.main(ruta_config=ruta_config)
    args = _construir_parser().parse_args(argumentos)
    if args.modo == "ultimo":
        return _ejecutar_ultimo(args)
    if args.modo == "nuevo":
        return _ejecutar_nuevo(args)
    if args.modo == "pendientes":
        return _ejecutar_pendientes(args)
    if args.modo == "init":
        return _ejecutar_init(args)
    return _ejecutar_backfill(args)


if __name__ == "__main__":
    raise SystemExit(main())
