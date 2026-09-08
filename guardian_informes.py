#!/usr/bin/env python
"""Launcher for the PreToolUse hook. This is what goes in ~/.claude/settings.json.

Fails open: if something goes wrong, it prints nothing and exits 0, and the tool
goes on its normal course.
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

try:
    from claude_informes.guardian import main
except Exception:  # the package is not there, or is broken: nothing is blocked
    sys.exit(0)

sys.exit(main())
