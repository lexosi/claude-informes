"""Entrada de linea de ordenes: `hook`, `backfill` y `ultimo`."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import backfill as bf
from . import config as cfg
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
    return parser


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


def _ejecutar_ultimo(args) -> int:
    """El log dice donde esta; el disco dice si es verdad. Manda el disco."""
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
    if not ruta.is_file():
        print(
            f"estado   : NO EXISTE EN DISCO. El log dice que se escribio el "
            f"{anotacion.marca}, pero el fichero no esta.",
            file=sys.stderr,
        )
        return 1
    print(f"estado   : existe en disco, {ruta.stat().st_size} bytes")
    return 0


def main(argv: list[str] | None = None) -> int:
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
    return _ejecutar_backfill(args)


if __name__ == "__main__":
    raise SystemExit(main())
