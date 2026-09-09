"""claude-informes: one JSON per Claude Code turn, at no token cost.

Naming note (historic aliases). Two submodules were renamed to English but
keep their old short aliases at the import site: ``report`` is imported
``as inf`` (from ``informe``) and ``journal`` ``as reg`` (from ``registro``).
So ``from . import journal as reg`` is deliberate, not an oversight: renaming
the module file is a rename of ONE name, but renaming the alias would rewrite
``reg.``/``inf.`` at hundreds of call sites --a rename of internal names,
which is out of scope. The module with no alias (``streams``) imports cleanly
under its new name.
"""

__version__ = "1.0.0"
