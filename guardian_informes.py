#!/usr/bin/env python
"""Lanzadera del hook PreToolUse. Es lo que se pone en ~/.claude/settings.json.

Falla abierto: si algo va mal, no imprime nada y sale 0, y la herramienta
sigue su curso normal.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from claude_informes.guardian import main
except Exception:  # el paquete no esta, o esta roto: no se bloquea nada
    sys.exit(0)

sys.exit(main())
