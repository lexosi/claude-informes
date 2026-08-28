# Instalacion de los hooks

**Instalados el 2026-08-28.** Los dos estan en `C:\Users\iamle\.claude\settings.json`;
la copia previa quedo en `settings.json.antes-de-claude-informes`. Esto documenta
lo que hay puesto, como comprobarlo y como quitarlo.

Son dos hooks con reglas opuestas a proposito:

| Hook | Cuando | Que hace | Si algo falla |
| --- | --- | --- | --- |
| `Stop` | fin de turno | escribe el informe | sale 0 y calla (**falla cerrado**) |
| `PreToolUse` | antes de `Write`/`Edit`/... | deniega escribir dentro del archivo | **permite** (**falla abierto**) |

## 0. La regla de operacion

**El proyecto se deriva de donde ARRANCA la sesion, no de donde este la shell.**
Los `cd` de dentro de un turno no cambian el archivo.

Por eso, para un proyecto nuevo, el orden es: crear la carpeta, registrarlo, y
**entonces** abrir el CLI dentro de ella. `python -m claude_informes nuevo
<nombre>` hace los dos primeros pasos de una vez.

Si abres el CLI en el directorio padre, esa sesion no se archiva. Se puede
recuperar despues con `pendientes` y `backfill`, pero no sobre la marcha.

## 1. La config: a donde apunta

`E:\example-projects\claude-informes\config\proyectos.json` es la lista blanca.
Hoy solo lleva `E:\example-projects\loopward`, con el nombre de carpeta
`loopward`. En cualquier otro proyecto el hook sale 0 sin tocar nada, y en el
propio `claude-informes` no escribe aunque se le anada.

Los informes van a `E:\example-reports\<proyecto>\<dia>\`, y el log a
`E:\example-reports.log`, los dos fuera de todo repositorio git. Un proyecto
puede declarar su propia `raiz_informes` si quieres archivarlo en otro sitio.

## 2. Lo que hay en `~/.claude/settings.json`

```json
{
  "autoUpdatesChannel": "latest",
  "theme": "dark",
  "tui": "fullscreen",
  "hooks": {
    "Stop": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "python \"E:\\example-projects\\claude-informes\\hook_informes.py\"",
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
            "command": "python \"E:\\example-projects\\claude-informes\\guardian_informes.py\"",
            "timeout": 10
          }
        ]
      }
    ]
  }
}
```

Notas:

- En JSON las barras invertidas van dobladas. Si prefieres evitarlo, sirve
  igual `python E:/example-projects/claude-informes/hook_informes.py`.
- `python` tiene que ser el del PATH. Comprueba con `python --version` (aqui,
  3.12.10). Si un dia no lo estuviera, pon la ruta completa al interprete.
- No hace falta instalar el paquete ni un entorno virtual: las lanzaderas
  anaden su propio directorio al `sys.path`. No hay dependencias.
- Los `timeout` son una red de seguridad mas; los hooks ya se autolimitan.

## 3. Reiniciar Claude Code

**Los hooks se leen al arrancar la sesion.** Una sesion que ya estuviera
abierta cuando se instalaron sigue sin ellos hasta que se reinicie.

## 4. Comprobar que funcionan

Los dos se pueden ejercitar sin abrir una sesion: leen el payload por stdin,
tal cual se lo pasa Claude Code.

```powershell
# fin de turno en un proyecto vigilado -> escribe el informe
Get-Content turno.json | python E:\example-projects\claude-informes\hook_informes.py
echo $LASTEXITCODE   # 0, y sin imprimir nada

# intento de escribir dentro del archivo -> deniega
Get-Content escritura.json | python E:\example-projects\claude-informes\guardian_informes.py
# imprime un JSON con permissionDecision: "deny"; exit sigue siendo 0
```

Lo que de verdad conviene mirar es el log, porque ahi queda todo:

```powershell
Get-Content E:\example-reports.log -Tail 10
```

```
2026-08-28T17:02:00 | loopward | escrito            | E:\example-reports\loopward\2026-08-28\08-....json
2026-08-28T17:02:00 | loopward | denegado-escritura | Write -> e:\example-reports\...\99-escrito-a-mano.json
2026-08-28T17:02:00 | -        | omitido-cwd        | cwd fuera de la lista: 'E:\example-projects\project-c'
```

Y para contrastar el log con el disco:

```powershell
cd E:\example-projects\claude-informes
.venv\Scripts\python -m claude_informes ultimo --proyecto loopward
```

Para mandar el log a otro sitio mientras pruebas, sin tocar el real:

```powershell
$env:CLAUDE_INFORMES_LOG = "C:\Users\iamle\AppData\Local\Temp\informes.log"
```

## 5. Desinstalar

Quitar el bloque `"hooks"` de `~/.claude/settings.json`, o restaurar la copia:

```powershell
Copy-Item C:\Users\iamle\.claude\settings.json.antes-de-claude-informes `
          C:\Users\iamle\.claude\settings.json
```

Para apagar solo la escritura sin tocar los ajustes de Claude Code, basta con
`"activo": false` en la config. El guardian se puede quitar solo, borrando su
entrada `PreToolUse`.

## Lo que hay fuera de este repositorio

- `C:\Users\iamle\.claude\settings.json`: los dos hooks.
- `C:\Users\iamle\.claude\CLAUDE.md`: las instrucciones permanentes de no
  escribir informes a mano. Es contexto, no imposicion; lo que impone es el
  guardian.
- `E:\example-reports\` y `E:\example-reports.log`: el archivo y el log, fuera
  de todo arbol git.
- El repositorio `E:\example-projects\loopward`: solo el commit que quito
  `informes/` de su `.gitignore` y el que lo restauro. Ni una linea de codigo.
