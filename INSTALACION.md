# Instalacion de los hooks

Son dos hooks de Claude Code con reglas opuestas a proposito:

| Hook | Cuando | Que hace | Si algo falla |
| --- | --- | --- | --- |
| `Stop` | fin de turno | escribe el informe | sale 0 y calla (**falla cerrado**) |
| `PreToolUse` | antes de `Write`/`Edit`/... | deniega escribir dentro del archivo | **permite** (**falla abierto**) |

En lo que sigue, `<claude-informes>` es la ruta donde has clonado este
repositorio. Sustituyela por la tuya.

## 0. La regla de operacion

**El proyecto se deriva de donde ARRANCA la sesion, no de donde este la shell.**
Los `cd` de dentro de un turno no cambian el archivo.

Por eso, para un proyecto nuevo, el orden es: crear la carpeta, registrarlo, y
**entonces** abrir el CLI dentro de ella. `python -m claude_informes nuevo
<nombre>` hace los dos primeros pasos de una vez.

Si abres el CLI en el directorio padre, esa sesion no se archiva. Se puede
recuperar despues con `pendientes` y `backfill`, pero no sobre la marcha.

## 1. La config

La configuracion real **no vive en el repo**: vive en la config de usuario de
tu sistema operativo. Crea la tuya a partir del ejemplo:

```sh
python -m claude_informes init
```

Edita el fichero que crea y pon las rutas reales de tus proyectos y de la raiz
de informes. El detalle del formato, la ubicacion por sistema operativo y el
orden de resolucion estan en el [README](README.md#configuracion).

## 2. El entorno (venv)

El hook corre en **todas** tus sesiones de Claude Code. Para que no dependa del
`python` del PATH (que puede cambiar de version sin avisar), se usa un venv
propio con ruta absoluta:

```sh
# desde <claude-informes>
python -m venv .venv
.venv/Scripts/python -m pip install pytest    # Windows
# .venv/bin/python -m pip install pytest       # macOS / Linux
```

El intérprete del venv es el que iran a buscar los hooks:

- Windows: `<claude-informes>\.venv\Scripts\python.exe`
- macOS / Linux: `<claude-informes>/.venv/bin/python`

Las lanzaderas anaden su propio directorio al `sys.path` y no tienen
dependencias, asi que tecnicamente valdria cualquier Python 3.10+; se prefiere
el venv por determinismo.

## 3. Lo que va en `~/.claude/settings.json`

Ejemplo para Windows (en JSON las barras invertidas van dobladas; tambien sirve
`/`). En macOS/Linux, usa `<claude-informes>/.venv/bin/python`.

```json
{
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "\"<claude-informes>\\.venv\\Scripts\\python.exe\" \"<claude-informes>\\hook_informes.py\"",
            "timeout": 15
          }
        ]
      }
    ],
    "PreToolUse": [
      {
        "matcher": "Write|Edit|MultiEdit|NotebookEdit|mcp__.*",
        "hooks": [
          {
            "type": "command",
            "command": "\"<claude-informes>\\.venv\\Scripts\\python.exe\" \"<claude-informes>\\guardian_informes.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

- El matcher del guardian incluye `mcp__.*` para cubrir servidores MCP con
  escritura (ver README).
- Los `timeout` son una red de seguridad mas; los hooks ya se autolimitan.
- Si ya tienes otros hooks para `Stop` o `PreToolUse`, **anade** estas entradas
  al array existente; no las sustituyas. Claude Code ejecuta todos los hooks de
  un evento y, en `PreToolUse`, gana la decision mas restrictiva.

## 4. Reiniciar Claude Code

**Los hooks se leen al arrancar la sesion.** Una sesion que ya estuviera
abierta cuando se instalaron sigue sin ellos hasta que se reinicie.

## 5. Comprobar que funcionan

Los dos se pueden ejercitar sin abrir una sesion: leen el payload por stdin,
tal cual se lo pasa Claude Code.

```sh
# fin de turno en un proyecto vigilado -> escribe el informe
python <claude-informes>/hook_informes.py < turno.json
echo $?    # 0, y sin imprimir nada

# intento de escribir dentro del archivo -> deniega
python <claude-informes>/guardian_informes.py < escritura.json
# imprime un JSON con permissionDecision: "deny"; exit sigue siendo 0
```

Lo que de verdad conviene mirar es el log, porque ahi queda todo. Su ruta por
defecto es el hermano de la raiz de informes (`<raiz_informes>.log`). Para
contrastar el log con el disco:

```sh
cd <claude-informes>
.venv/Scripts/python -m claude_informes ultimo --proyecto <proyecto>
```

Para mandar el log a otro sitio mientras pruebas, sin tocar el real, define la
variable de entorno `CLAUDE_INFORMES_LOG`.

## 6. Desinstalar

Quita las dos entradas que anadiste al bloque `"hooks"` de
`~/.claude/settings.json` (o restaura tu copia previa de ese fichero).

Para apagar solo la escritura sin tocar los ajustes de Claude Code, basta con
`"activo": false` en la config. El guardian se puede quitar solo, borrando su
entrada `PreToolUse`.
