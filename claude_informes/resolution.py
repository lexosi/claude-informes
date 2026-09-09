"""Resolve which project a session belongs to, under the watched-roots model.

The config no longer lists the projects that exist. It declares WHERE to watch
and, optionally, explicit project roots with their overrides:

- ``roots``: watched containers. Each immediate child directory is a project.
  A session that starts in ``<root>/alfa/src`` is archived under ``alfa``.
- ``projects``: a path that is itself one project, optionally carrying overrides
  (``line_threshold``, ``reports_root``, ``name``). A session anywhere inside a
  standalone tool's own directory is archived under that tool's name.

Both kinds are matched by the SAME rule: of every watched place that contains
the session's startup directory, the most specific (the longest path) wins.
There is no leaf/container flag: such a flag would be the exception, and the
exception is the hole. A container contributes its child; a project contributes
itself, and because a project root is longer than the container it hangs off,
it wins on its own subtree without a special case.

The project is derived from where the session STARTS, never from the directory
the shell wanders into during the turn.
"""

from __future__ import annotations

import fnmatch
import os

from . import config as cfg
from . import journal as reg


def _resuelto(ruta) -> str:
    """Absolute and real: symlinks and junctions resolved, casing preserved."""
    return os.path.realpath(str(ruta))


def _dentro(raiz_nc: str, objetivo_nc: str) -> bool:
    if objetivo_nc == raiz_nc:
        return True
    return objetivo_nc.startswith(raiz_nc.rstrip(os.sep) + os.sep)


def _primer_segmento(raiz_real: str, objetivo_real: str) -> str | None:
    """The first path component of `objetivo` below `raiz`. None if they are equal.

    The prefix is stripped by length; `normcase` does not change a path's length,
    so this holds whatever the casing the startup arrived with.
    """
    resto = objetivo_real[len(raiz_real.rstrip(os.sep)):].strip(os.sep)
    if not resto:
        return None
    return resto.split(os.sep, 1)[0]


def _excluido(proyecto: cfg.Proyecto, patrones: list[str]) -> bool:
    """A glob matched against the project's full path OR its bare name.

    ``fnmatch`` normalizes case on its own (``os.path.normcase``), so both the
    full path and the bare ``alfa-audit`` match ``*-audit*`` on Windows.
    """
    ruta = proyecto.raiz
    base = os.path.basename(ruta.rstrip(os.sep))
    return any(
        fnmatch.fnmatch(ruta, patron) or fnmatch.fnmatch(base, patron)
        for patron in patrones
    )


def _descubierto(raiz_real: str, segmento: str, configuracion: cfg.Configuracion) -> cfg.Proyecto:
    """A project found under a container: name is its real on-disk basename, and
    it inherits the global threshold and report root (overrides live in `projects`)."""
    directorio = os.path.join(raiz_real, segmento)
    nombre = os.path.basename(_resuelto(directorio))
    return cfg.Proyecto(
        nombre=nombre,
        raiz=directorio,
        umbral_lineas=cfg.UMBRAL_POR_DEFECTO,
        raiz_informes=configuracion.raiz_informes,
    )


def resolver_proyecto(
    arranque: str | None, configuracion: cfg.Configuracion
) -> tuple[cfg.Proyecto | None, str]:
    """Return (project, label). The label is '' when a project is found.

    When the project is None, the label says WHY, and they are three distinct
    cases on purpose: `fuera-de-raices` (the startup is under no watched place),
    `raiz-desnuda` (the startup IS a watched container, with no project below it)
    and `excluido-patron` (it resolved to a project that matches an exclusion).
    """
    if not isinstance(arranque, str) or not arranque.strip():
        return None, reg.FUERA_DE_RAICES
    objetivo = _resuelto(arranque)
    objetivo_nc = os.path.normcase(objetivo)

    candidatos: list[tuple[str, cfg.Proyecto | None]] = []
    for entrada in configuracion.proyectos:
        raiz = _resuelto(entrada.raiz)
        if _dentro(os.path.normcase(raiz), objetivo_nc):
            candidatos.append((raiz, entrada))
    for root in configuracion.roots:
        raiz = _resuelto(root)
        if _dentro(os.path.normcase(raiz), objetivo_nc):
            candidatos.append((raiz, None))

    if not candidatos:
        return None, reg.FUERA_DE_RAICES

    raiz_real, entrada = max(candidatos, key=lambda c: len(os.path.normcase(c[0])))

    if entrada is not None:
        proyecto = entrada
    else:
        segmento = _primer_segmento(raiz_real, objetivo)
        if segmento is None:
            return None, reg.RAIZ_DESNUDA
        proyecto = _descubierto(raiz_real, segmento, configuracion)

    if _excluido(proyecto, configuracion.exclusions):
        return None, reg.EXCLUIDO_PATRON
    return proyecto, ""
