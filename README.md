# claude-informes

Captura la respuesta de cada turno de Claude Code y la guarda como JSON. Cero
coste de tokens: lo escribe un hook `Stop`, que es un proceso externo, no una
llamada al modelo.

Motivo: los `.md` llegan vacios al destinatario, y duplicar la respuesta a mano
cuesta tokens.

## Para empezar un proyecto nuevo

**El orden importa.** El proyecto se deriva de donde **arranca** la sesion, no
de donde este la shell: los `cd` de dentro del turno no cambian nada.

1. Crear la carpeta del proyecto dentro de `example-projects`.
2. Registrarlo en la config de claude-informes (nombre + cwd).
3. **Abrir el CLI dentro de esa carpeta**, no en el padre.

Los pasos 1 y 2 son una sola orden:

```sh
python -m claude_informes nuevo mi-proyecto
# carpeta   : E:\example-projects\mi-proyecto
# registrado: E:\example-projects\claude-informes\config\proyectos.json
# Ya puedes abrir el CLI ahi:  cd E:\example-projects\mi-proyecto
```

> **Si abres el CLI en el directorio padre, esa sesion NO se archiva.** Y son
> justo las sesiones de arranque las que mas valen: toda la construccion del
> proyecto esta ahi. No es recuperable sobre la marcha, pero si despues: ver
> [Recuperar lo que no se archivo](#recuperar-lo-que-no-se-archivo).

## Que hace

- **Un JSON por turno.** Nunca se acumulan varios turnos en un fichero.
- Solo actua en los proyectos listados en su configuracion. En cualquier otro
  sitio no hace absolutamente nada.
- Solo escribe si la respuesta tiene **mas de 5 lineas de markdown crudo**.

## Donde escribe

Todo va a un archivo central que vive **fuera de cualquier repositorio git**.
Hoy, `E:\example-reports`:

```
<raiz_informes>\<proyecto>\<AAAA-MM-DD>\<NN>-<slug>.json
```

```
E:\example-reports\
└── loopward/
    └── 2026-08-28/
        ├── 01-readme-extracto-gate-e-infraestructura-informes.json
        ├── 02-investigacion-transcript-hooks-pipeline-informes.json
        └── 03-hecho-push-verificacion-x-get-location-git-remote.json
```

Buscar un informe es entrar en la carpeta del proyecto, en la del dia, y ahi
solo estan los de esa jornada.

- `<proyecto>` sale del campo `nombre` de la config, **no** del nombre del
  directorio: renombrar el repositorio no parte el historico.
- Una carpeta que ya existe se reutiliza. Nunca se crea una variante ni un
  sufijo, ni siquiera si difiere en mayusculas.
- `<NN>` empieza en `01` en cada carpeta de dia. El nombre no repite la fecha
  ni el proyecto: ya los aporta la ruta.

El archivo esta deliberadamente fuera de todo arbol git. Guarda el texto
integro de sesiones de trabajo de todos los proyectos vigilados, y eso no debe
poder llegar a un `git add -A`, a un `git clean -xdf` ni a un remoto por
descuido. `informes/` esta ademas en el `.gitignore` de este repositorio como
segundo cinturon, por si algun dia `raiz_informes` volviera a apuntar dentro.

Cada proyecto puede declarar su propia `raiz_informes` y archivarse aparte,
para separar lo sensible del resto. Si no la declara, hereda la global.

### El slug

1. El primer encabezado, si trae **3 o mas palabras significativas**, quitandole
   la numeracion inicial: `## 1. TRANSCRIPT del runtime` da `transcript-runtime`.
2. Si se queda corto, se concatenan encabezados sucesivos hasta llegar a tres
   palabras o agotarlos: `## Tabla` + `## Veredicto final` da
   `tabla-veredicto-final`.
3. Si aun asi es pobre, o no hay encabezados, las primeras palabras
   significativas del cuerpo.
4. Tope de 60 caracteres, cortando siempre por guion.

Significativas = descartando articulos, preposiciones y conectores comunes en
espanol e ingles, y los numeros sueltos.

## El sobre

El JSON es un sobre mecanico. Su unico requisito es llevar el markdown
integro; no hay estructura semantica ninguna.

```json
{
  "fecha": "2026-08-28",
  "hora": "13:35:17",
  "session_id": "a6e5a399-f600-4b6a-a258-e7f1bcae90f8",
  "cwd": "E:\\example-projects\\loopward",
  "git_branch": "main",
  "git_head": "ac72eff...",
  "respuesta_markdown": "...el texto INTEGRO, byte a byte...",
  "secciones": [{ "nivel": 2, "titulo": "Tabla", "contenido": "..." }],
  "bloques_codigo": [{ "lenguaje": "python", "codigo": "..." }],
  "casillas": [{ "marcada": true, "texto": "tests verdes" }]
}
```

`secciones`, `bloques_codigo` y `casillas` son troceos **sintacticos** del
mismo markdown, por comodidad de quien lo consuma. El original manda.

## Configuracion

Un unico fichero, `config/proyectos.json`, que vive **fuera** de los
repositorios vigilados. Anadir un proyecto es anadir una entrada; el codigo no
conoce ninguna ruta concreta.

```json
{
  "raiz_informes": "E:\\example-reports",
  "proyectos": [
    {
      "nombre": "loopward",
      "cwd": "E:\\example-projects\\loopward",
      "activo": true,
      "umbral_lineas": 5
    },
    {
      "nombre": "project-b",
      "cwd": "E:\\example-projects\\project-b",
      "raiz_informes": "E:\\example-reports-privado"
    }
  ]
}
```

| Clave | Por defecto | Que hace |
| --- | --- | --- |
| `ruta_log` | hermano del archivo | El log del hook. |
| `raiz_informes` (global) | `informes/` de esta herramienta | Raiz que heredan los proyectos. |
| `raiz_informes` (por proyecto) | la global | Archiva ESE proyecto aparte. |
| `nombre` | el del directorio | Carpeta del proyecto dentro del archivo. |
| `cwd` | obligatorio | Raiz del proyecto. Sus subdirectorios tambien cuentan. |
| `activo` | `true` | `false` lo apaga sin borrar la linea. |
| `umbral_lineas` | `5` | Se escribe con **mas** de estas lineas. |

Se puede apuntar a otro fichero con la variable de entorno
`CLAUDE_INFORMES_CONFIG`. Si la config falta o esta rota, la herramienta se
comporta como si la lista estuviera vacia: no escribe en ningun sitio.

## Seguridad

Este hook corre en **todas** las sesiones de Claude Code. No puede romper
ninguna, jamas.

- Todo el modo hook va envuelto en `try/except`. Cualquier excepcion sale 0 en
  silencio.
- Nunca escribe en `stdout` ni en `stderr`.
- `cwd` fuera de la lista: sale 0 sin tocar nada.
- **`cwd` dentro del propio `claude-informes`: no se escribe nunca**, ni aunque
  alguien lo meta en la lista. La carpeta de destino vive aqui dentro, y un
  turno de este proyecto acabaria escribiendose a si mismo.
- `stop_hook_active`: sale 0 sin tocar nada, para no reentrar.
- Si el directorio de salida no existe, lo crea; si no puede, sale 0.
- El nombre del fichero se reserva con `O_CREAT|O_EXCL`: dos turnos a la vez no
  pueden quedarse con el mismo ordinal.
- Las llamadas a `git` llevan tiempo limite y su fallo no impide el informe.
- El archivo vive fuera de todo repositorio: ningun `git add -A` puede barrerlo
  a un commit, y ningun `git clean -xdf` puede borrarlo.

## El log

Salir en silencio evita romper sesiones, pero convertiria cualquier fallo en
algo invisible. Por eso **cada turno deja una linea**, pase lo que pase:

```
2026-08-28T16:50:38 | loopward  | escrito         | E:\example-reports\loopward\2026-08-28\08-....json
2026-08-28T16:50:38 | loopward  | omitido-umbral  | 2 lineas, umbral 5
2026-08-28T16:50:38 | -         | omitido-cwd     | cwd fuera de la lista: 'E:\example-projects\project-b'
2026-08-28T16:50:38 | -         | omitido-sesion  | proyecto no registrado; nombre=...; arranque=...
2026-08-28T16:50:38 | loopward  | ERROR           | UnicodeEncodeError: ...; ruta=...\14-....json; sesion=abc123
```

`marca | proyecto | resultado | ruta o motivo`, solo se anade, y en LF. Hay dos
resultados mas para que ningun turno quede sin linea: `omitido-reentrada`
(`stop_hook_active`) y `omitido-sin-texto`.

La linea de `ERROR` de un turno que llego a tener proyecto dice **cual**, que
ruta iba a tener el informe y de que sesion era. Sin esos tres datos el log
registra que algo fallo pero no se puede contrastar contra el disco, y el
fallo sigue siendo silencioso en la practica.

Vive fuera de las carpetas de informes y fuera de todo repositorio. Por defecto
es el hermano del archivo: con `raiz_informes` en `E:\example-reports`, el log
es `E:\example-reports.log`. Se puede fijar con `ruta_log` en la config, o con
la variable de entorno `CLAUDE_INFORMES_LOG`, que manda sobre las dos.

Escribir el log tambien va dentro del `try/except`. Si el log falla, el hook
sale 0 igual y sin ruido: el log no vale nada si tumba una sesion.

Es un log unico para todos los proyectos. Lleva nombres de proyecto y rutas
(con sus slugs), no contenido de los informes.

### `ultimo`: que el log no pueda mentir

El log dice donde quedo el informe; el disco dice si es verdad. Manda el disco.

```sh
python -m claude_informes ultimo --proyecto loopward
```

```
proyecto : loopward
informe  : 08-prueba-humo-hook.json
ruta     : E:\example-reports\loopward\2026-08-28\08-prueba-humo-hook.json
anotado  : 2026-08-28T16:50:38
estado   : existe en disco, 453 bytes
```

Si el log dice que se escribio y el fichero no esta, lo dice y sale con 1:

```
estado   : NO EXISTE EN DISCO. El log dice que se escribio el 2026-08-28T16:50:38,
           pero el fichero no esta.
```

Sin `--proyecto`, el ultimo de cualquiera. Codigos: `0` existe, `1` el log
miente, `2` no hay nada anotado.

## El guardian: que no se escriban informes a mano

Un segundo hook, `PreToolUse`, deniega `Write`, `Edit`, `MultiEdit` y
`NotebookEdit` cuando la ruta cae dentro del archivo o sobre el log. Los
informes los escribe el hook `Stop`; escribirlos a mano es siempre un error, y
casi siempre el de anunciar un fichero que no existe.

Su regla numero uno es la **contraria** a la del `Stop`: **falla abierto**.
Cualquier excepcion, config ilegible o ruta que no se pueda resolver termina en
"permitido", en silencio. Un guardian que bloquea por error es peor que no
tener guardian: rompe sesiones ajenas por un fallo suyo.

- Solo deniega cuando la ruta esta **inequivocamente** dentro. Ante la duda,
  permite.
- Las zonas salen de la config, no del codigo: la raiz global, la de cada
  proyecto, y el log. Gana la mas especifica.
- La ruta se resuelve antes de comparar (absoluta, `..`, enlaces), asi que
  `..\..\informes-claude\x.json` cae igual.
- `Bash` queda fuera a proposito: adivinar rutas dentro de una linea de shell
  da falsos positivos.
- Cada denegacion se anota como `denegado-escritura`. Las escrituras permitidas
  no anotan nada: seria una linea por cada uso de una herramienta.
- Si la config no se puede leer, permite y lo anota como `permitido-por-error`.

El mensaje dice por que y que hacer en su lugar:

```
claude-informes: e:\example-reports\loopward\2026-08-28\99-x.json esta dentro
del archivo de informes (archivo: e:\example-reports).
Los informes los escribe el hook Stop al terminar el turno; no se escriben ni
se editan a mano.
Para saber cual fue el ultimo y comprobar que existe de verdad:
    cd E:\example-projects\claude-informes
    .venv\Scripts\python -m claude_informes ultimo --proyecto loopward
```

### Servidores MCP

Cualquier servidor MCP con escritura montado en Claude Code se saltaria un
matcher limitado a las herramientas nativas: la herramienta se llamaria
`mcp__servidor__write_file`. Por eso el matcher incluye `mcp__.*`.

Los servidores MCP no comparten esquema: ni el nombre de la herramienta ni el
del campo de la ruta estan estandarizados. La deteccion es heuristica, y por
eso **solo sirve para denegar mejor; permitir sigue garantizado**:

- Se mira el ultimo tramo del nombre (`mcp__servidor__write_file` -> `write_file`)
  y se busca un verbo de escritura entre sus palabras. Por palabras, no por
  subcadena: si no, `get_output` contendria "put".
- Las de lectura (`read_file`, `list_directory`, `directory_tree`...) pasan sin
  mirarse. Leer los informes es legitimo; solo se impide escribirlos.
- Un verbo que no se reconoce se trata como lectura. Fallar abierto manda.
- Si la herramienta dice escribir, se prueban los nombres de campo habituales
  (`path`, `file_path`, `filename`, `destination`, `target`, `paths`...). Si no
  aparece ninguna ruta reconocible, **se permite** y se anota como
  `permitido-sin-ruta`, para que el punto ciego sea visible y no silencioso.

La consecuencia honesta: un servidor que llame `persistir` a su escritura, o
que meta la ruta en un campo con un nombre inventado, pasa. Denegar es siempre
mejor esfuerzo; lo unico garantizado es que no se rompe nada.

## De que proyecto es un turno

De la **sesion**, no de la shell. El `cwd` del payload sigue a cada `cd` que se
haga durante el turno, y archivar por el falla en las dos direcciones: mete
turnos de un proyecto no registrado en la carpeta de uno registrado, y pierde
turnos de uno registrado cuando la shell se ha ido a otro sitio. Un archivo del
que no te puedes fiar no sirve de nada.

El `transcript_path` identifica la sesion y no se mueve:

1. Se compara el directorio del transcript con el slug que produce el `cwd`
   declarado de cada proyecto. El mapeo es explicito y comprobable; no se
   intenta deshacer el slug, que es ambiguo (`e--example-projects-loopward-audit`
   tanto podria ser `loopward/audit` como el proyecto hermano `loopward-audit`).
2. Si no hay coincidencia exacta, se lee el **primer registro** del transcript,
   que lleva el `cwd` de arranque sin ambiguedad. Eso resuelve las sesiones
   abiertas en un subdirectorio.
3. Si con eso tampoco sale, la sesion no esta registrada: **no se archiva**, y
   la linea del log lleva el transcript y el nombre que tendria el proyecto.

Caer al `cwd` en el paso 3 reabriria el agujero, asi que solo se usa cuando no
hay `transcript_path` del que fiarse. En ese caso se archiva por `cwd` y se
anota una linea extra, `proyecto-por-cwd`, para que el camino degradado se vea.

### Recuperar lo que no se archivo

```sh
python -m claude_informes pendientes
# 9 turno(s) sin archivar de un proyecto no registrado: claude-informes
#    transcript: C:\Users\...\projects\e--example-projects\978e2c78-....jsonl
#    registrar : python -m claude_informes nuevo claude-informes
#    recuperar : python -m claude_informes backfill --transcript "..." \
#                --proyecto claude-informes --salida "E:\example-reports"
```

`pendientes` sale con 1 cuando hay algo que recuperar, para que se note. El
backfill reconstruye la sesion entera desde el transcript, aunque el proyecto
nunca haya estado registrado: el JSONL guarda los turnos igual.

## Modo backfill

Reconstruye informes de turnos ya pasados leyendo el transcript JSONL. Criterio:
`type == "assistant"` y `stop_reason == "end_turn"` y algun bloque `text` no
vacio.

```sh
# Toda la sesion mas reciente de un proyecto, a su carpeta del archivo
python -m claude_informes backfill --cwd "E:\example-projects\loopward"

# Una sesion concreta, a otro archivo distinto
python -m claude_informes backfill --session a6e5a399-... \
    --salida C:\tmp\archivo --proyecto loopward

# Un transcript en disco, sin escribir nada
python -m claude_informes backfill --transcript ruta\sesion.jsonl --dry-run
```

| Opcion | Que hace |
| --- | --- |
| `--transcript` | Ruta al `.jsonl`. |
| `--session` | Id de sesion; busca el `.jsonl` bajo `~/.claude/projects/`. |
| `--cwd` | Proyecto: coge su transcript mas reciente y resuelve su config. |
| `--salida` | Raiz del archivo. Salta la lista blanca (es manual). |
| `--proyecto` | Carpeta de proyecto; por defecto, la de la config. |
| `--umbral` | Lineas minimas; por defecto, el del proyecto. |
| `--limite` | Solo los ultimos N turnos. |
| `--dry-run` | Dice que escribiria, sin escribir. |

Sin `--salida`, el backfill respeta la lista blanca y sale con codigo 3 si el
proyecto no esta en ella.

## Instalacion del hook

Ver [INSTALACION.md](INSTALACION.md).

## Tests

```sh
python -m venv .venv
.venv\Scripts\python -m pip install pytest
.venv\Scripts\python -m pytest
```
