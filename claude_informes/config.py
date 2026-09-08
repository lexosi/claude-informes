"""Configuracion por proyecto. Vive FUERA de los repositorios vigilados.

Anadir un proyecto es anadir una entrada al JSON de configuracion.
El codigo no conoce ninguna ruta concreta.
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from . import markdown as md
from . import registro as reg

VAR_ENTORNO = "CLAUDE_INFORMES_CONFIG"
VAR_LOG = "CLAUDE_INFORMES_LOG"
UMBRAL_POR_DEFECTO = 5

# Nombre de la carpeta y del fichero de configuracion de usuario. La config
# REAL vive FUERA del repositorio (ver README, "Por que la config vive fuera
# del repo"): asi el repo se publica sin ninguna ruta de nadie, y cambiar de
# maquina no genera conflictos en un fichero versionado.
CARPETA_APP = "claude-informes"
NOMBRE_CONFIG = "proyectos.json"


def raiz_de_la_herramienta() -> Path:
    """El directorio del propio paquete claude-informes (la raiz del repo)."""
    return Path(__file__).resolve().parent.parent


def dir_config_usuario() -> Path:
    """Carpeta de configuracion por-usuario, segun la convencion de cada SO.

    - Windows: ``%APPDATA%\\claude-informes`` (la carpeta Roaming del usuario,
      donde Windows guarda config de aplicaciones que sigue al perfil).
    - macOS: ``~/Library/Application Support/claude-informes`` (el directorio
      estandar de datos de aplicacion en macOS).
    - Linux y demas: ``$XDG_CONFIG_HOME/claude-informes`` o, si no esta
      definida, ``~/.config/claude-informes`` (la especificacion XDG Base
      Directory, el estandar de facto en Linux).
    """
    if sys.platform == "win32":
        base = os.environ.get("APPDATA") or str(Path.home() / "AppData" / "Roaming")
        return Path(base) / CARPETA_APP
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / CARPETA_APP
    base = os.environ.get("XDG_CONFIG_HOME") or str(Path.home() / ".config")
    return Path(base) / CARPETA_APP


def ruta_config_usuario() -> Path:
    """El fichero de config de usuario en la ubicacion estandar del SO."""
    return dir_config_usuario() / NOMBRE_CONFIG


def ruta_de_ejemplo() -> Path:
    """El ejemplo versionado en el repo. Rutas ficticias, nunca reales."""
    return raiz_de_la_herramienta() / "config" / "proyectos.ejemplo.json"


@dataclass(frozen=True)
class Proyecto:
    nombre: str
    raiz: str
    activo: bool
    umbral_lineas: int
    raiz_informes: Path
    """Donde se archiva ESTE proyecto. Por defecto, la raiz global."""


@dataclass(frozen=True)
class Configuracion:
    raiz_informes: Path
    """Raiz global: la que heredan los proyectos que no declaran la suya."""

    ruta_log: Path
    """El log del hook. Uno solo, para todos los proyectos."""

    proyectos: list[Proyecto] = field(default_factory=list)


def normalizar(ruta: str | os.PathLike[str]) -> str:
    return os.path.normcase(os.path.normpath(os.path.abspath(str(ruta))))


def raiz_informes_por_defecto() -> Path:
    return raiz_de_la_herramienta() / "informes"


def ruta_de_log(declarada, raiz_informes) -> Path:
    """Manda el entorno, luego la config, y si no, el hermano del archivo."""
    del_entorno = os.environ.get(VAR_LOG)
    if del_entorno:
        return Path(del_entorno)
    if isinstance(declarada, str) and declarada.strip():
        return Path(declarada)
    return reg.ruta_por_defecto(raiz_informes)


def por_defecto() -> Configuracion:
    """Sin config legible: ningun proyecto, pero el log sigue existiendo."""
    raiz = raiz_informes_por_defecto()
    return Configuracion(raiz_informes=raiz, ruta_log=ruta_de_log(None, raiz))


def ruta_de_config() -> Path | None:
    """La config que se debe usar, o None si no hay ninguna.

    Orden de resolucion, documentado y testeado:
      1. La variable de entorno ``CLAUDE_INFORMES_CONFIG``, si esta definida.
         Gana siempre, exista o no el fichero: quien la pone sabe lo que hace.
      2. La config de usuario en la ubicacion estandar del SO, si existe.
      3. Nada: ``None``. El repositorio NO contiene ninguna config real, solo
         el ejemplo, asi que aqui no hay tercer sitio donde mirar.
    """
    del_entorno = os.environ.get(VAR_ENTORNO)
    if del_entorno:
        return Path(del_entorno)
    usuario = ruta_config_usuario()
    if usuario.exists():
        return usuario
    return None


def mensaje_sin_config() -> str:
    """Que decirle a quien arranca sin config. Nunca un traceback."""
    return (
        "No hay configuracion de claude-informes.\n"
        f"El fichero de usuario deberia estar en:\n    {ruta_config_usuario()}\n\n"
        "Crealo a partir del ejemplo con:\n"
        "    python -m claude_informes init\n\n"
        "O indica uno propio con la variable de entorno "
        f"{VAR_ENTORNO}, o con --config.\n"
        f"El ejemplo versionado esta en: {ruta_de_ejemplo()}"
    )


def _nombre_de(entrada: dict, raiz: str) -> str:
    """El nombre sale de la config; renombrar el directorio no parte el historico."""
    declarado = entrada.get("nombre")
    if isinstance(declarado, str) and declarado.strip():
        return declarado.strip()
    return md.slug_llano(Path(raiz).name) or "sin-nombre"


def cargar(ruta: str | os.PathLike[str] | None = None) -> Configuracion:
    """Lee la configuracion. Si falta o esta rota, no hay ningun proyecto."""
    try:
        return cargar_estricto(ruta)
    except Exception:
        return por_defecto()


def cargar_estricto(ruta: str | os.PathLike[str] | None = None) -> Configuracion:
    """Como `cargar`, pero revienta si la config no se puede leer.

    Quien vigila escrituras necesita saber si la config es fiable: sin ella
    no puede afirmar que una ruta este protegida, y entonces permite.
    """
    destino = Path(ruta) if ruta is not None else ruta_de_config()
    if destino is None:
        raise FileNotFoundError("no hay configuracion de claude-informes")
    crudo = json.loads(destino.read_text(encoding="utf-8"))

    entradas = crudo.get("proyectos") if isinstance(crudo, dict) else crudo
    raiz_informes = crudo.get("raiz_informes") if isinstance(crudo, dict) else None
    if not isinstance(raiz_informes, str) or not raiz_informes.strip():
        raiz_informes = raiz_informes_por_defecto()

    declarada = crudo.get("ruta_log") if isinstance(crudo, dict) else None
    ruta_log = ruta_de_log(declarada, raiz_informes)

    if not isinstance(entradas, list):
        return Configuracion(raiz_informes=Path(raiz_informes), ruta_log=ruta_log)

    proyectos = []
    for entrada in entradas:
        if not isinstance(entrada, dict):
            continue
        raiz = entrada.get("cwd") or entrada.get("raiz")
        if not isinstance(raiz, str) or not raiz.strip():
            continue
        umbral = entrada.get("umbral_lineas", UMBRAL_POR_DEFECTO)
        if not isinstance(umbral, int) or isinstance(umbral, bool) or umbral < 0:
            umbral = UMBRAL_POR_DEFECTO
        propia = entrada.get("raiz_informes")
        if not isinstance(propia, str) or not propia.strip():
            propia = raiz_informes
        proyectos.append(
            Proyecto(
                nombre=_nombre_de(entrada, raiz),
                raiz=str(Path(raiz)),
                activo=bool(entrada.get("activo", True)),
                umbral_lineas=umbral,
                raiz_informes=Path(propia),
            )
        )
    return Configuracion(
        raiz_informes=Path(raiz_informes),
        ruta_log=ruta_log,
        proyectos=proyectos,
    )


def _esta_dentro(candidato: str, raiz: str) -> bool:
    if candidato == raiz:
        return True
    return candidato.startswith(raiz.rstrip(os.sep) + os.sep)


def es_la_propia_herramienta(cwd: str | None) -> bool:
    """Guardia: el destino de los informes vive dentro de este proyecto.

    Si algun dia claude-informes acaba en la lista de vigilados, un turno suyo
    escribiria dentro de su propia carpeta de salida. No se escribe, y punto.
    """
    if not isinstance(cwd, str) or not cwd.strip():
        return False
    return _esta_dentro(normalizar(cwd), normalizar(raiz_de_la_herramienta()))


def buscar_proyecto(cwd: str | None, configuracion: Configuracion) -> Proyecto | None:
    """Lista blanca: el cwd debe ser la raiz de un proyecto activo o colgar de ella.

    Devuelve None para cualquier cwd fuera de la lista. Ante empate, gana la
    raiz mas larga.

    La herramienta ya no es un caso aparte. Lo fue mientras `raiz_informes`
    apuntaba dentro de `claude-informes/informes/`: entonces un turno suyo
    habria escrito en su propia carpeta de salida, dentro de un repo. Desde
    que el archivo vive en una raiz propia, fuera de todo arbol git, esa
    premisa no existe, y la guardia solo servia para tirar a la basura los
    turnos de quien trabajaba en la propia herramienta. Lo que de verdad
    protegia --que ningun destino de archivo caiga dentro de la herramienta
    ni de ningun repositorio-- lo afirman los tests de la config real.
    """
    if not isinstance(cwd, str) or not cwd.strip():
        return None
    objetivo = normalizar(cwd)
    candidatos = [
        p
        for p in configuracion.proyectos
        if p.activo and _esta_dentro(objetivo, normalizar(p.raiz))
    ]
    if not candidatos:
        return None
    return max(candidatos, key=lambda p: len(normalizar(p.raiz)))
