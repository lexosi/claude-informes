# Contributing

## Commit message language

Commit messages are written in **English from the commit that adds this file
onward** (2026-09-08). Earlier commits are in Spanish and are left as they are:
a commit message is dated evidence of what was done and when, and rewriting
history to translate it would destroy that evidence.

The switch is because the repository is becoming public and part of the
author's portfolio, read by reviewers who do not read Spanish.

## Language of the code and docs

Prose is being translated to English (README, INSTALACION, NO-PUBLICAR,
docstrings, comments, and user-facing messages). If you see a mix during that
work, it is in progress, not neglect. Two things are deliberately **not**
translated, and this is the reason, so the mix is read as a decision:

## What is not translated, and why

- **Internal function, class and variable names.** They stay in Spanish. A
  reviewer never sees them (they are not on any user-facing surface), each rename
  is risk that touches imports, call sites and the whole test suite, and the cost
  is measured in days. High cost, low external value: not worth it.
- **The JSON envelope keys and the log result labels.** These are a **data
  format, not text.** The keys (`fecha`, `respuesta_markdown`, `secciones`...) and
  the log labels (`escrito`, `omitido-umbral`...) are the format the tool already
  wrote to disk. Translating them would break every one of the already-archived
  reports, the backfill's `_ya_archivado` check (which compares
  `respuesta_markdown`), the `ultimo` and `pendientes` commands, `construir`, and
  any external consumer. If it is ever done, it goes with a `version` field in the
  envelope and a migration, as an API change --not as part of the language
  switch.
