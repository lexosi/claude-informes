# Instalacion del hook

**Todavia no esta instalado.** Estas son las instrucciones para hacerlo cuando
los tests estén en verde y te parezca bien.

## 1. Comprobar que la config apunta a donde quieres

`E:\example-projects\claude-informes\config\proyectos.json` es la lista blanca.
Hoy solo lleva `E:\example-projects\loopward`, con el nombre de carpeta
`loopward`. En cualquier otro proyecto el hook sale 0 sin tocar nada, y en
el propio `claude-informes` no escribe aunque se le anada.

Los informes van a `E:\example-reports\<proyecto>\<dia>\`, fuera de todo
repositorio git. Un proyecto puede declarar su propia `raiz_informes` si
quieres archivarlo en otro sitio.

## 2. Anadir el hook a `~/.claude/settings.json`

El fichero es `C:\Users\iamle\.claude\settings.json`. Hoy contiene:

```json
{
  "autoUpdatesChannel": "latest",
  "theme": "dark",
  "tui": "fullscreen"
}
```

Queda asi:

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
    ]
  }
}
```

Notas:

- En JSON las barras invertidas van dobladas. Si prefieres evitarlo, sirve
  igual `python E:/example-projects/claude-informes/hook_informes.py`.
- `python` tiene que ser el del PATH. Comprueba con `python --version` (aqui,
  3.12.10). Si un dia no lo estuviera, pon la ruta completa al interprete.
- No hace falta instalar el paquete ni un entorno virtual: la lanzadera anade
  su propio directorio al `sys.path`. No tiene dependencias.
- El `timeout` es una red de seguridad mas; el hook ya se autolimita.

## 3. Reiniciar Claude Code

Los hooks se leen al arrancar la sesion.

## 4. Comprobar que funciona

Sin instalar nada, se puede simular un turno tal cual llega por stdin:

```sh
echo {"session_id":"prueba","cwd":"E:\\example-projects\\loopward","stop_hook_active":false,"last_assistant_message":"# Prueba\nuno\ndos\ntres\ncuatro\ncinco\nseis"} | python E:\example-projects\claude-informes\hook_informes.py
```

Deberia aparecer un JSON en `E:\example-reports\loopward\<hoy>\` y la orden no
imprimir nada. En PowerShell es mas comodo con un fichero:

```powershell
Get-Content prueba.json | python E:\example-projects\claude-informes\hook_informes.py
echo $LASTEXITCODE   # tiene que ser 0
```

Para ver por que el hook decidio lo que decidio:

```powershell
$env:CLAUDE_INFORMES_LOG = "C:\Users\iamle\AppData\Local\Temp\informes.log"
```

## 5. Desinstalar

Quitar el bloque `"hooks"` de `~/.claude/settings.json`. No queda nada mas.
Tambien vale con poner `"activo": false` en la config para apagarlo sin tocar
los ajustes de Claude Code.

## Que hay fuera de este repositorio

- `~/.claude/settings.json` sigue como estaba: el hook no esta instalado.
- El repositorio `E:\example-projects\loopward`: solo el commit que quita
  `informes/` de su `.gitignore`. Ni una linea de codigo, tests ni README.
