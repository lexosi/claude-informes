"""Command-line entry point: `hook`, `ultimo`, `pendientes` and `backfill`."""

from __future__ import annotations

import argparse
import fnmatch
import json
import sys
from pathlib import Path

from . import backfill as bf
from . import config as cfg
from . import streams
from . import hook as hk
from . import journal as reg
from . import resolution as res
from . import transcript as tr


def _construir_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="claude-informes", description=__doc__)
    subs = parser.add_subparsers(dest="modo", required=True)

    p_hook = subs.add_parser("hook", help="read the Stop payload from stdin")
    p_hook.add_argument("--config", default=None)

    p_bf = subs.add_parser("backfill", help="reconstruct reports of past turns")
    p_bf.add_argument("--transcript", help="path to the .jsonl")
    p_bf.add_argument("--session", help="session id; the .jsonl is looked up")
    p_bf.add_argument(
        "--cwd",
        help="project: locate its most recent transcript and resolve its config",
    )
    p_bf.add_argument(
        "--salida", default=None, help="report root; by default, the config's"
    )
    p_bf.add_argument(
        "--proyecto", default=None, help="name of the project folder"
    )
    p_bf.add_argument("--umbral", type=int, default=None)
    p_bf.add_argument("--limite", type=int, default=None, help="last N turns")
    p_bf.add_argument("--config", default=None)
    p_bf.add_argument("--dry-run", action="store_true")

    p_ult = subs.add_parser("ultimo", help="the last written report, verified on disk")
    p_ult.add_argument("--proyecto", default=None, help="by default, any")
    p_ult.add_argument("--config", default=None)

    p_pen = subs.add_parser(
        "pendientes", help="sessions the hook saw but did not archive, and what to do"
    )
    p_pen.add_argument("--config", default=None)

    p_ini = subs.add_parser(
        "init", help="create the user config from the example, the first time"
    )
    p_ini.add_argument(
        "--config", default=None, help="where to create it; by default, the OS's standard location"
    )
    return parser


def _sin_config(args) -> bool:
    """No usable config: no --config, no environment, no user file."""
    return not args.config and cfg.ruta_de_config() is None


def _resolver_transcript(args) -> Path | None:
    if args.transcript:
        ruta = Path(args.transcript)
        return ruta if ruta.is_file() else None
    return tr.localizar(cwd=args.cwd, session_id=args.session)


def _motivo_en_ingles(motivo: str) -> str:
    """Render the backfill's internal `motivo` protocol value in English.

    The values stay Spanish because they are protocol: the backfill compares
    them and its tests pin them. Only the threshold value reaches the user here
    (the others are handled by their own branch), so it is the one mapped;
    anything unmapped falls through unchanged rather than being hidden.
    """
    if motivo.startswith("umbral ("):
        return motivo.replace("umbral (", "threshold (").replace(" lineas)", " lines)")
    return motivo


def _ejecutar_backfill(args) -> int:
    if not (args.transcript or args.session or args.cwd):
        print("Specify --transcript, --session or --cwd.", file=sys.stderr)
        return 2
    ruta = _resolver_transcript(args)
    if ruta is None:
        print("Transcript not found.", file=sys.stderr)
        return 2

    configuracion = cfg.cargar(args.config)
    lectura = tr.leer(ruta)
    if not lectura.turnos:
        if lectura.estado in (tr.DERIVA, tr.ILEGIBLE):
            # Not silent: a drift or an unreadable transcript leaves its own line
            # in the log, so a backfill that suddenly extracts nothing is
            # distinguishable from a session that legitimately has no turn.
            etiqueta = (
                reg.DERIVA_FORMATO if lectura.estado == tr.DERIVA else reg.TRANSCRIPT_ILEGIBLE
            )
            try:
                reg.anotar(
                    configuracion.ruta_log,
                    etiqueta,
                    reg.SIN_PROYECTO,
                    f"{lectura.detalle}; transcript={ruta}",
                )
            except Exception:  # noqa: BLE001 - the log cannot bring down the CLI
                pass
            aviso = (
                "has assistant lines but no extractable turn -- possible format drift"
                if lectura.estado == tr.DERIVA
                else f"could not be read ({lectura.detalle})"
            )
            print(f"{ruta}: {aviso} (logged).", file=sys.stderr)
        else:
            print(f"{ruta}: no closed turns.", file=sys.stderr)
        return 1

    turnos = lectura.turnos
    arranque = args.cwd or lectura.arranque or (turnos[-1].get("cwd") if turnos else "") or ""
    proyecto, _etiqueta = res.resolver_proyecto(arranque, configuracion)
    umbral = args.umbral

    if proyecto is None and not args.salida:
        print(
            f"{arranque!r} is under no watched root. "
            "Use --salida to write elsewhere.",
            file=sys.stderr,
        )
        return 3

    raiz = Path(args.salida) if args.salida else (
        proyecto.raiz_informes if proyecto else configuracion.raiz_informes
    )
    nombre = args.proyecto or (
        proyecto.nombre if proyecto else Path(arranque).name
    )
    if not nombre:
        print("Could not deduce the project name. Use --proyecto.", file=sys.stderr)
        return 4
    if umbral is None:
        umbral = proyecto.umbral_lineas if proyecto else cfg.UMBRAL_POR_DEFECTO

    print(f"transcript: {ruta}")
    print(f"output    : {raiz / nombre}")
    resultados = bf.reconstruir(
        ruta,
        raiz,
        nombre,
        umbral=umbral,
        limite=args.limite,
        simular=args.dry_run,
        ruta_log=configuracion.ruta_log,
    )
    escritos = 0
    for entrada in resultados:
        # The `motivo` values ("simulacion", "ya archivado", "umbral ...") stay
        # in Spanish on purpose: they are the backfill's internal protocol, not
        # display text --they are compared here and pinned by the backfill's
        # tests. They are mapped to English only at the moment of showing them,
        # like any internal code presented to a user (see _motivo_en_ingles).
        if entrada["escrito"]:
            escritos += 1
            print(f"  + {Path(entrada['ruta']).name}")
        elif entrada["motivo"] == "simulacion":
            print(f"  ~ {Path(entrada['ruta']).name} (simulation)")
        elif entrada["motivo"] == "ya archivado":
            print(f"  = already archived: {Path(entrada['ruta']).name}")
        else:
            print(f"  - skipped: {_motivo_en_ingles(entrada['motivo'])}")
    print(f"{escritos} report(s) written of {len(resultados)} turn(s).")
    return 0


def _ejecutar_init(args) -> int:
    """Create the user config by copying the example. Idempotent: does not overwrite."""
    destino = Path(args.config) if args.config else cfg.ruta_config_usuario()
    if destino.exists():
        print(f"A user config already exists: {destino}")
        print("It was not touched. Edit it by hand if you want to change it.")
        return 0
    try:
        contenido = cfg.ruta_de_ejemplo().read_text(encoding="utf-8")
    except FileNotFoundError:
        print(f"Example not found: {cfg.ruta_de_ejemplo()}", file=sys.stderr)
        return 2
    destino.parent.mkdir(parents=True, exist_ok=True)
    destino.write_text(contenido, encoding="utf-8", newline="\n")
    print(f"User config created: {destino}")
    print("Edit it and put in the real paths of your projects and of the report root.")
    return 0


def _ejecutar_ultimo(args) -> int:
    """The log says where it is; the disk says whether that is true. The disk rules."""
    if _sin_config(args):
        print(cfg.mensaje_sin_config(), file=sys.stderr)
        return 2
    configuracion = cfg.cargar(args.config)
    anotaciones = reg.leer(configuracion.ruta_log)
    if not anotaciones:
        print(f"The log is empty or does not exist: {configuracion.ruta_log}", file=sys.stderr)
        return 2

    anotacion = reg.ultimo_escrito(anotaciones, args.proyecto)
    if anotacion is None:
        de_quien = f" for {args.proyecto}" if args.proyecto else ""
        print(f"The log records no written report{de_quien}.", file=sys.stderr)
        return 2

    ruta = anotacion.ruta
    print(f"project  : {anotacion.proyecto}")
    print(f"report   : {ruta.name}")
    print(f"path     : {ruta}")
    print(f"recorded : {anotacion.marca}")
    # The log records a PAST FACT --that this was written there that day--, not an
    # index of live files. Whether the file is still at that path is information,
    # not an alarm: renaming it or moving the archive does not make the line a
    # lie. That is why all this goes to stdout and the code is 0.
    if ruta.is_file():
        print(f"status   : still on disk, {ruta.stat().st_size} bytes")
    elif ruta.parent.is_dir():
        print(
            "status   : no longer where the log recorded it. Its day folder is "
            "still there, so it was renamed or deleted within it."
        )
    else:
        print(
            f"status   : no longer where the log recorded it, and its folder "
            f"({ruta.parent}) does not exist either: the whole archive was moved "
            f"or relocated. The log keeps where it was on {anotacion.marca}."
        )
    return 0


def _patrones_que_casan(ruta: str, patrones: list[str]) -> list[str]:
    """Which exclusion globs match a path (fnmatch normalizes case on its own)."""
    return [p for p in patrones if fnmatch.fnmatch(ruta, p)]


def _detalle_como_dict(detalle: str) -> dict[str, str]:
    """Parse the log detail `nombre=..; arranque=..; transcript=..` into a dict."""
    return dict(
        trozo.split("=", 1) for trozo in detalle.split("; ") if "=" in trozo
    )


def _ejecutar_pendientes(args) -> int:
    """Sessions the hook saw but did not archive, and the exact fix for each.

    Two cases, both actionable: a startup outside every watched root (says the
    line to add to the config), and a project filtered by an exclusion (says
    which pattern, so it can be removed). A startup AT a bare root is left out:
    it is self-correcting -- open the CLI inside a project subdirectory.
    """
    if _sin_config(args):
        print(cfg.mensaje_sin_config(), file=sys.stderr)
        return 2
    configuracion = cfg.cargar(args.config)
    interesan = (reg.FUERA_DE_RAICES, reg.EXCLUIDO_PATRON)
    anotaciones = [a for a in reg.leer(configuracion.ruta_log) if a.resultado in interesan]
    if not anotaciones:
        print("No sessions seen outside the watched roots or filtered by a pattern.")
        return 0

    grupos: dict[tuple[str, str, str, str], int] = {}
    for anotacion in anotaciones:
        datos = _detalle_como_dict(anotacion.detalle)
        clave = (
            anotacion.resultado,
            datos.get("nombre", "?"),
            datos.get("arranque", "?"),
            datos.get("transcript", "?"),
        )
        grupos[clave] = grupos.get(clave, 0) + 1

    for (etiqueta, nombre, arranque, transcripcion), cuantos in sorted(grupos.items()):
        if etiqueta == reg.FUERA_DE_RAICES:
            entrada = json.dumps({"name": nombre, "path": arranque}, ensure_ascii=False)
            print(f"{cuantos} turn(s) not archived: {arranque} is under no watched root.")
            print('   to archive this subtree as one project, add to "projects":')
            print(f"       {entrada}")
            print('   or, to watch each child of a directory, add the parent to "roots".')
        else:  # EXCLUIDO_PATRON
            casantes = _patrones_que_casan(arranque, configuracion.exclusions)
            print(f"{cuantos} turn(s) not archived: {arranque} is filtered by an exclusion.")
            if casantes:
                print(f'   matched by {", ".join(casantes)}; remove it from "exclusions" to archive it.')
            else:
                print('   no current exclusion matches it; it will archive from now on.')
        print(
            f"   recover what was lost:  python -m claude_informes backfill "
            f'--transcript "{transcripcion}" --proyecto {nombre} '
            f'--salida "{configuracion.raiz_informes}"'
        )
    return 1


def main(argv: list[str] | None = None) -> int:
    streams.salida_en_utf8(sys.stdout, sys.stderr)
    argumentos = list(sys.argv[1:] if argv is None else argv)
    # The hook must never fail, not even from an angry argparse.
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
    if args.modo == "pendientes":
        return _ejecutar_pendientes(args)
    if args.modo == "init":
        return _ejecutar_init(args)
    return _ejecutar_backfill(args)


if __name__ == "__main__":
    raise SystemExit(main())
