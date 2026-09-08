# claude-informes

[![tests](https://github.com/lexosi/claude-informes/actions/workflows/tests.yml/badge.svg)](https://github.com/lexosi/claude-informes/actions/workflows/tests.yml)

> ⛔ **DO NOT PUBLISH yet.** The git history contains the author's real data;
> the tip is clean but the past is not. Before making this repo public, read and
> resolve [NO-PUBLICAR.md](NO-PUBLICAR.md).

Captures the response of every Claude Code turn and saves it as JSON. Zero token
cost: it is written by a `Stop` hook, which is an external process, not a call to
the model.

Why: the `.md` files arrive empty to the recipient, and duplicating the response
by hand costs tokens.

## Starting a new project

**Order matters.** The project is derived from where the session **starts**, not
from where the shell is: the `cd` commands within a turn change nothing.

1. Create the project folder wherever you keep your repos.
2. Register it in the claude-informes config (name + cwd).
3. **Open the CLI inside that folder**, not in the parent.

Steps 1 and 2 are a single command (the example paths are fictitious; on your own
machine you will see yours):

```sh
python -m claude_informes nuevo mi-proyecto
# folder    : /ruta/a/proyectos/mi-proyecto
# registered: <tu config de usuario>/proyectos.json
# You can now open the CLI there:  cd /ruta/a/proyectos/mi-proyecto
```

> **If you open the CLI in the parent directory, that session is NOT archived.**
> And it is precisely the startup sessions that are worth the most: the whole
> construction of the project is there. It is not recoverable on the fly, but it
> is afterwards: see [Recovering what was not archived](#recovering-what-was-not-archived).

## What it does

- **One JSON per turn.** Several turns never accumulate in a single file.
- Only acts on the projects listed in its configuration. Anywhere else it does
  absolutely nothing.
- Only writes if the response has **more than 5 lines of raw markdown**.

## Where it writes

Everything goes to a central archive that lives **outside any git repository**,
under the root declared by `raiz_informes` (for example `~/informes-claude`):

```
<raiz_informes>/<proyecto>/<AAAA-MM-DD>/<NN>-<slug>.json
```

```
<raiz_informes>/
└── alfa/
    └── 2026-08-28/
        ├── 01-readme-extracto-gate-e-infraestructura-informes.json
        ├── 02-investigacion-transcript-hooks-pipeline-informes.json
        └── 03-hecho-push-verificacion-x-get-location-git-remote.json
```

Finding a report means entering the project folder, then the day folder, and
there you have only the reports of that day.

- `<proyecto>` comes from the `nombre` field of the config, **not** from the
  directory name: renaming the repository does not split the history.
- A folder that already exists is reused. A variant or a suffix is never created,
  not even if it differs in case.
- `<NN>` starts at `01` in each day folder. The name does not repeat the date or
  the project: the path already provides them.

The archive is deliberately outside any git tree. It stores the full text of work
sessions of all watched projects, and that must not be able to reach a
`git add -A`, a `git clean -xdf` or a remote by accident. `informes/` is also in
this repository's `.gitignore` as a second belt, in case `raiz_informes` ever
points inside again.

Each project can declare its own `raiz_informes` and be archived separately, to
keep the sensitive apart from the rest. If it does not declare one, it inherits
the global one.

### The slug

1. The first heading, if it carries **3 or more significant words**, after
   removing the leading numbering: `## 1. TRANSCRIPT del runtime` gives
   `transcript-runtime`.
2. If it comes up short, successive headings are concatenated until reaching
   three words or running out: `## Tabla` + `## Veredicto final` gives
   `tabla-veredicto-final`.
3. If it is still poor, or there are no headings, the first significant words of
   the body.
4. Capped at 60 characters. It cuts at a word boundary (a hyphen) when there is
   one within the limit; a single word longer than the limit is cut hard,
   because the result is a filename.

Significant = discarding articles, prepositions and common connectors in Spanish
and English, and lone numbers.

## The envelope

The JSON is a mechanical envelope. Its only requirement is to carry the full
markdown; there is no semantic structure at all.

```json
{
  "fecha": "2026-08-28",
  "hora": "13:35:17",
  "session_id": "a6e5a399-f600-4b6a-a258-e7f1bcae90f8",
  "cwd": "/ruta/a/proyectos/alfa",
  "git_branch": "main",
  "git_head": "ac72eff...",
  "respuesta_markdown": "...el texto INTEGRO, byte a byte...",
  "secciones": [{ "nivel": 2, "titulo": "Tabla", "contenido": "..." }],
  "bloques_codigo": [{ "lenguaje": "python", "codigo": "..." }],
  "casillas": [{ "marcada": true, "texto": "tests verdes" }]
}
```

`secciones`, `bloques_codigo` and `casillas` are **syntactic** splits of the same
markdown, for the convenience of whoever consumes it. The original rules.

> **Note on field names.** The envelope keys (`fecha`, `respuesta_markdown`,
> `secciones`...) are in Spanish on purpose: they are a data format, not text.
> Translating them would break every already-archived report and any consumer.
> See [CONTRIBUTING.md](CONTRIBUTING.md#what-is-not-translated-and-why).

## Configuration

### Why the config lives outside the repo

**Design decision.** This project is public and is installed on machines that are
not the author's. That is why the repository **contains no real configuration**:
only `config/proyectos.ejemplo.json`, with fictitious paths.

A real config inside the repo would have two serious problems:

1. **Leakage.** Absolute paths reveal the author's directory structure, and
   publishing them is publishing information that has no business in a repo.
2. **Conflicts.** Each machine has different paths. A versioned file with paths
   inside turns every change of machine into a git conflict.

The real config therefore lives **outside the repo**, in the standard per-user
configuration location of each operating system:

| System | User config file |
| --- | --- |
| Windows | `%APPDATA%\claude-informes\proyectos.json` (the *Roaming* folder of the profile) |
| macOS | `~/Library/Application Support/claude-informes/proyectos.json` |
| Linux | `$XDG_CONFIG_HOME/claude-informes/proyectos.json` (or `~/.config/claude-informes/proyectos.json`) |

**Resolution order** (documented and tested in `tests/test_config_ubicacion.py`):

1. The environment variable `CLAUDE_INFORMES_CONFIG`, if defined. Always wins.
2. The user config in the standard OS location, if it exists.
3. If there is none: a **clear message** that says how to create it. Never a
   traceback, and the hook/guardian do not break (they behave as if the list were
   empty).

### Creating the config the first time

```sh
python -m claude_informes init
# User config created: <ubicacion estandar del SO>/proyectos.json
```

`init` copies the example to the user location and does not overwrite one that
already exists. Afterwards you edit it by hand and put in the real paths.

### Shape of the file

Adding a project means adding an entry; the code knows no specific path. On
Windows paths use `\` (doubled in JSON: `"C:\\Users\\..."`); on macOS and Linux,
`/`.

```json
{
  "raiz_informes": "/ruta/absoluta/fuera/de/git/informes-claude",
  "proyectos": [
    {
      "nombre": "alfa",
      "cwd": "/ruta/absoluta/a/alfa",
      "activo": true,
      "umbral_lineas": 5
    },
    {
      "nombre": "beta",
      "cwd": "/ruta/absoluta/a/beta",
      "raiz_informes": "/ruta/absoluta/fuera/de/git/informes-privado"
    }
  ]
}
```

| Key | Default | What it does |
| --- | --- | --- |
| `ruta_log` | sibling of the archive | The hook's log. |
| `raiz_informes` (global) | this tool's `informes/` | Root inherited by the projects. |
| `raiz_informes` (per project) | the global one | Archives THAT project separately. |
| `nombre` | the directory's | Project folder inside the archive. |
| `cwd` | required | Project root. Its subdirectories also count. |
| `activo` | `true` | `false` turns it off without deleting the line. |
| `umbral_lineas` | `5` | Written with **more** than this many lines. |

If the config is missing or broken, the tool behaves as if the list were empty:
it writes nowhere.

## Security

This hook runs in **every** Claude Code session. It cannot break any of them,
ever.

- The whole hook mode is wrapped in `try/except`. Any exception exits 0 silently.
- It never writes to `stdout` or `stderr`.
- `cwd` outside the list: exits 0 without touching anything.
- `stop_hook_active`: exits 0 without touching anything, so as not to re-enter.
- If the output directory does not exist, it creates it; if it cannot, it exits 0.
- The file name is reserved with `O_CREAT|O_EXCL`: two turns at once cannot take
  the same ordinal.
- Calls to `git` carry a time limit and their failure does not prevent the report.
- The archive lives outside any repository: no `git add -A` can sweep it into a
  commit, and no `git clean -xdf` can delete it.

> The tool can watch itself like any other project. While the archive lived inside
> `claude-informes/informes/`, one of its own turns would have been written into
> its own output folder, and that is why there was a guard preventing it. Since
> the archive lives in its own root outside any repo, that premise disappeared,
> and the guard was removed: all it did was throw away the turns of whoever was
> working on the tool itself.

## The log

Exiting silently avoids breaking sessions, but it would turn any failure into
something invisible. That is why **every turn leaves a line**, no matter what:

```
2026-08-28T16:50:38 | alfa  | escrito         | <raiz_informes>/alfa/2026-08-28/08-....json
2026-08-28T16:50:38 | alfa  | omitido-umbral  | 2 lineas, umbral 5
2026-08-28T16:50:38 | -         | omitido-cwd     | cwd fuera de la lista: '/ruta/a/beta'
2026-08-28T16:50:38 | -         | omitido-sesion  | proyecto no registrado; nombre=...; arranque=...
2026-08-28T16:50:38 | alfa  | ERROR           | UnicodeEncodeError: ...; ruta=.../14-....json; sesion=abc123
```

`timestamp | project | result | path or reason`, append-only, and in LF. There
are two more results so that no turn is left without a line: `omitido-reentrada`
(`stop_hook_active`) and `omitido-sin-texto`.

The `ERROR` line of a turn that did get a project says **which** one, what path
the report was going to have and which session it belonged to. Without those
three facts the log records that something failed but it cannot be checked against
the disk, and the failure remains silent in practice.

> The result labels in the log (`escrito`, `omitido-umbral`...) are a data format,
> not text, and are kept in Spanish for the same reason as the envelope keys:
> translating them would break every already-written log. See
> [CONTRIBUTING.md](CONTRIBUTING.md#what-is-not-translated-and-why).

It lives outside the report folders and outside any repository. By default it is
the sibling of the archive: with `raiz_informes` at `~/informes-claude`, the log
is `~/informes-claude.log`. It can be fixed with `ruta_log` in the config, or with
the environment variable `CLAUDE_INFORMES_LOG`, which takes precedence over both.

Writing the log also goes inside the `try/except`. If the log fails, the hook
exits 0 all the same and without noise: the log is worthless if it brings down a
session.

It is a single log for all projects. It carries project names and paths (with
their slugs), not the content of the reports.

### `ultimo`: so the log cannot lie

The log says where the report ended up; the disk says whether that is true. The
disk rules.

```sh
python -m claude_informes ultimo --proyecto alfa
```

```
project  : alfa
report   : 08-prueba-humo-hook.json
path     : <raiz_informes>/alfa/2026-08-28/08-prueba-humo-hook.json
recorded : 2026-08-28T16:50:38
status   : still on disk, 453 bytes
```

**The log is a record of what happened, not an index of live files.** If a report
is renamed or moved, the `escrito` line remains true --it describes a past fact--
and `ultimo` reports it without alarm: it says it is no longer where it was
recorded, and distinguishes whether its folder is still there (renamed or deleted
within) or whether the whole archive was moved.

```
status   : no longer where the log recorded it. Its day folder is still there,
           so it was renamed or deleted within it.
```

Without `--proyecto`, the last of any of them. Exit codes: `0` there is a
recorded report (the message says whether it is still at its path or not), `2`
nothing is recorded.

## The guardian: keeping reports from being written by hand

A second hook, `PreToolUse`, denies `Write`, `Edit`, `MultiEdit` and
`NotebookEdit` when the path falls inside the archive or onto the log. The reports
are written by the `Stop` hook; writing them by hand is always a mistake, and
almost always the mistake of announcing a file that does not exist.

Its rule number one is the **opposite** of the `Stop` one: **it fails open.** Any
exception, unreadable config or path that cannot be resolved ends in "allowed",
silently. A guardian that blocks by mistake is worse than having no guardian: it
breaks other people's sessions through a fault of its own.

- It only denies when the path is **unequivocally** inside. When in doubt, it
  allows.
- The zones come from the config, not from the code: the global root, each
  project's, and the log. The most specific one wins.
- The path is resolved before comparing (absolute, `..`, links), so
  `../../informes-claude/x.json` falls in just the same.
- `Bash` is left out on purpose: guessing paths inside a shell line gives false
  positives.
- Each denial is recorded as `denegado-escritura`. Allowed writes record nothing:
  it would be a line for every use of a tool.
- If the config cannot be read, it allows and records it as `permitido-por-error`.

The message says why and what to do instead:

```
claude-informes: <raiz_informes>/alfa/2026-08-28/99-x.json is inside
the report archive (archive: <raiz_informes>).
The reports are written by the Stop hook at the end of the turn; they are not
written or edited by hand.
To find out which was the last one and check that it really exists:
    cd <path to claude-informes>
    .venv\Scripts\python -m claude_informes ultimo --proyecto alfa
```

### MCP servers

Any MCP server with write capability mounted in Claude Code would slip past a
matcher limited to the native tools: the tool would be called
`mcp__servidor__write_file`. That is why the matcher includes `mcp__.*`.

MCP servers do not share a schema: neither the tool name nor the path field name
are standardized. The detection is heuristic, and that is why **it only serves to
deny better; allowing remains guaranteed**:

- The last segment of the name is looked at (`mcp__servidor__write_file` ->
  `write_file`) and a write verb is searched among its words. By words, not by
  substring: otherwise `get_output` would contain "put".
- The read ones (`read_file`, `list_directory`, `directory_tree`...) pass without
  being looked at. Reading the reports is legitimate; only writing them is
  prevented.
- A verb that is not recognized is treated as a read. Failing open rules.
- If the tool says it writes, the usual field names are tried (`path`,
  `file_path`, `filename`, `destination`, `target`, `paths`...). If no recognizable
  path appears, **it is allowed** and recorded as `permitido-sin-ruta`, so the
  blind spot is visible and not silent.

The honest consequence: a server that calls its write `persistir`, or that puts
the path in a field with a made-up name, gets through. Denying is always
best-effort; the only thing guaranteed is that nothing breaks.

## Which project a turn belongs to

To the **session**, not to the shell. The `cwd` of the payload follows every `cd`
made during the turn, and archiving by it fails in both directions: it puts turns
of an unregistered project into a registered one's folder, and loses turns of a
registered one when the shell has gone elsewhere. An archive you cannot trust is
worthless.

The `transcript_path` identifies the session and does not move:

1. The transcript's directory is compared with the slug that each project's
   declared `cwd` produces. The mapping is explicit and checkable; there is no
   attempt to undo the slug, which is ambiguous (`--proyectos-alfa-audit` could be
   either `alfa/audit` or the sibling project `alfa-audit`).
2. If there is no exact match, the **first record** of the transcript is read,
   which carries the startup `cwd` without ambiguity. That resolves sessions
   opened in a subdirectory.
3. If that does not work either, the session is not registered: **it is not
   archived**, and the log line carries the transcript and the name the project
   would have.

Falling back to `cwd` in step 3 would reopen the hole, so it is only used when
there is no `transcript_path` to trust. In that case it archives by `cwd` and
records an extra line, `proyecto-por-cwd`, so the degraded path is visible.

### Recovering what was not archived

```sh
python -m claude_informes pendientes
# 9 turn(s) unarchived from an unregistered project: claude-informes
#    transcript: ~/.claude/projects/--proyectos-claude-informes/978e2c78-....jsonl
#    register  : python -m claude_informes nuevo claude-informes
#    recover   : python -m claude_informes backfill --transcript "..." \
#                --proyecto claude-informes --salida "<raiz_informes>"
```

`pendientes` exits with 1 when there is something to recover, so it is noticed.
The backfill reconstructs the whole session from the transcript, even if the
project was never registered: the JSONL stores the turns all the same.

## Backfill mode

Reconstructs reports of already-past turns by reading the JSONL transcript.
Criterion: `type == "assistant"` and `stop_reason == "end_turn"` and some
non-empty `text` block.

```sh
# The most recent whole session of a project, to its archive folder
python -m claude_informes backfill --cwd "/ruta/a/alfa"

# A specific session, to a different archive
python -m claude_informes backfill --session a6e5a399-... \
    --salida /tmp/archivo --proyecto alfa

# A transcript on disk, without writing anything
python -m claude_informes backfill --transcript ruta/sesion.jsonl --dry-run
```

| Option | What it does |
| --- | --- |
| `--transcript` | Path to the `.jsonl`. |
| `--session` | Session id; looks for the `.jsonl` under `~/.claude/projects/`. |
| `--cwd` | Project: takes its most recent transcript and resolves its config. |
| `--salida` | Root of the archive. Skips the allowlist (it is manual). |
| `--proyecto` | Project folder; by default, the config's. |
| `--umbral` | Minimum lines; by default, the project's. |
| `--limite` | Only the last N turns. |
| `--dry-run` | Says what it would write, without writing. |

Without `--salida`, the backfill respects the allowlist and exits with code 3 if
the project is not in it.

## Installing the hook

See [INSTALACION.md](INSTALACION.md).

## Tests

```sh
python -m venv .venv
.venv/Scripts/python -m pip install pytest
.venv/Scripts/python -m pytest
```
