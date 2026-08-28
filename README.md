# claude-informes

Captura la respuesta de cada turno de Claude Code y la guarda como JSON. Cero
coste de tokens: lo escribe un hook `Stop`, que es un proceso externo, no una
llamada al modelo.

Motivo: los `.md` llegan vacios al destinatario, y duplicar la respuesta a mano
cuesta tokens.

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
2026-08-28T16:50:38 | -         | omitido-guardia | cwd dentro de la herramienta: E:\example-projects\claude-informes
2026-08-28T16:50:38 | -         | ERROR           | JSONDecodeError: Expecting value: line 1 column 1
```

`marca | proyecto | resultado | ruta o motivo`, solo se anade, y en LF. Hay dos
resultados mas para que ningun turno quede sin linea: `omitido-reentrada`
(`stop_hook_active`) y `omitido-sin-texto`.

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
