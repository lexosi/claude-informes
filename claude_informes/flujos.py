"""Las fronteras de codificacion del proceso. utf-8 explicito, siempre.

Python en Windows abre `sys.stdin` y `sys.stdout` con el encoding de la
consola --cp1252 aqui-- y con `errors='surrogateescape'`. Ninguno de los dos
se declara en ningun sitio: se heredan. Claude Code entrega y espera utf-8.

Lo que eso provocaba:

- Todo caracter no-ASCII llegaba partido en dos. `ó` (utf-8 C3 B3) se leia
  como `Ã` + `³`, y de ahi el mojibake en los nombres y en el markdown
  archivado.
- cp1252 tiene cinco huecos sin asignar: 0x81 0x8D 0x8F 0x90 0x9D. Un
  caracter cuyo utf-8 pise uno de ellos --`Á` (C3 81), `Í` (C3 8D), `❌`
  (E2 9D 8C), `←` (E2 86 90)-- dejaba un surrogate suelto que reventaba
  cien lineas mas tarde, al escribir el informe en utf-8.

Por eso la entrada se lee en BYTES y se decodifica a mano, y la salida se
escribe en BYTES. Ningun flujo de este proyecto hereda su encoding.
"""

from __future__ import annotations

import json


def leer_payload(flujo) -> dict:
    """El payload del hook, decodificado como utf-8 venga como venga.

    Si el flujo tiene `.buffer` --lo tiene `sys.stdin`-- se leen los bytes
    crudos. Un flujo de texto en memoria no lo tiene, y entonces ya viene
    decodificado por quien lo construyo.
    """
    crudo = getattr(flujo, "buffer", None)
    if crudo is None:
        return json.loads(flujo.read())
    return json.loads(crudo.read().decode("utf-8"))


def escribir(flujo, texto: str) -> None:
    """Escribe en utf-8, sin pasar por el encoding heredado del flujo.

    Importa mas de lo que parece: el guardian devuelve su denegacion por
    aqui. Con cp1252, una ruta con un caracter que no quepa reventaba el
    `write`, el guardian caia a su `except`, y **permitia** la escritura que
    tenia que denegar. Fallar abierto por un fallo propio de codificacion no
    es fallar abierto: es no estar.
    """
    crudo = getattr(flujo, "buffer", None)
    if crudo is None:
        flujo.write(texto)
        return
    flujo.flush()
    crudo.write(texto.encode("utf-8"))
    crudo.flush()


def salida_en_utf8(*flujos) -> None:
    """Pone los flujos de salida en utf-8. Para la CLI, que imprime rutas.

    `errors='replace'` a proposito: que un nombre raro salga con un
    interrogante es mejor que un `UnicodeEncodeError` en mitad de un informe
    de resultados.
    """
    for flujo in flujos:
        reconfigurar = getattr(flujo, "reconfigure", None)
        if reconfigurar is None:
            continue
        try:
            reconfigurar(encoding="utf-8", errors="replace")
        except Exception:  # noqa: BLE001 - un flujo redirigido puede no dejarse
            pass
