#!/usr/bin/env python
"""Lanzadera del hook Stop. Es lo que se pone en ~/.claude/settings.json.

No hace falta instalar nada: anade su propio directorio al path y sale 0
pase lo que pase.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from claude_informes.hook import main
except Exception:  # el paquete no esta, o esta roto: no se rompe la sesion
    sys.exit(0)

sys.exit(main())
