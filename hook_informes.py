#!/usr/bin/env python
"""Launcher for the Stop hook. This is what goes in ~/.claude/settings.json.

Nothing needs to be installed: it adds its own directory to the path and exits 0
no matter what.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from claude_informes.hook import main
except Exception:  # the package is not there, or is broken: the session is not broken
    sys.exit(0)

sys.exit(main())
