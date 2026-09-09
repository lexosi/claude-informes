# Installing the hooks

They are two Claude Code hooks with deliberately opposite rules:

| Hook | When | What it does | If something fails |
| --- | --- | --- | --- |
| `Stop` | end of turn | writes the report | exits 0 and stays quiet (**fails closed**) |
| `PreToolUse` | before `Write`/`Edit`/... | denies writing inside the archive | **allows** (**fails open**) |

In what follows, `<claude-informes>` is the path where you cloned this
repository. Replace it with yours.

## 0. The operating rule

**The project is derived from where the session STARTS, not from where the shell
is.** The `cd` commands within a turn do not change the archive.

So a session is archived only when its startup directory falls under a watched
root declared in your config. You declare the roots once (see the config
section); there is nothing to register per project.

If the session starts outside every watched root, it is not archived. It can be
recovered afterwards with `pendientes` and `backfill`, but not on the fly.

## 1. The config

The real configuration **does not live in the repo**: it lives in the user config
of your operating system. Create yours from the example:

```sh
python -m claude_informes init
```

Edit the file it creates and put in the real paths of your projects and of the
report root. The detail of the format, the per-operating-system location and the
resolution order are in the [README](README.md#configuration).

## 2. The environment (venv)

The hook runs in **every** one of your Claude Code sessions. So that it does not
depend on the `python` on the PATH (which can change version without warning), a
dedicated venv with an absolute path is used:

```sh
# from <claude-informes>
python -m venv .venv
.venv/Scripts/python -m pip install pytest    # Windows
# .venv/bin/python -m pip install pytest       # macOS / Linux
```

The venv interpreter is the one the hooks will look for:

- Windows: `<claude-informes>\.venv\Scripts\python.exe`
- macOS / Linux: `<claude-informes>/.venv/bin/python`

The launchers add their own directory to `sys.path` and have no dependencies, so
technically any Python 3.10+ would work; the venv is preferred for determinism.

## 3. What goes in `~/.claude/settings.json`

Example for Windows (in JSON the backslashes are doubled; `/` also works). On
macOS/Linux, use `<claude-informes>/.venv/bin/python`.

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

- The guardian's matcher includes `mcp__.*` to cover MCP servers with write
  capability (see README).
- The `timeout` values are one more safety net; the hooks already self-limit.
- If you already have other hooks for `Stop` or `PreToolUse`, **add** these
  entries to the existing array; do not replace them. Claude Code runs all the
  hooks of an event and, in `PreToolUse`, the most restrictive decision wins.

## 4. Restart Claude Code

**The hooks are read when the session starts.** A session that was already open
when they were installed continues without them until it is restarted.

## 5. Checking that they work

Both can be exercised without opening a session: they read the payload from
stdin, exactly as Claude Code passes it.

```sh
# end of turn in a watched project -> writes the report
python <claude-informes>/hook_informes.py < turno.json
echo $?    # 0, and printing nothing

# attempt to write inside the archive -> denies
python <claude-informes>/guardian_informes.py < escritura.json
# prints a JSON with permissionDecision: "deny"; exit is still 0
```

What is really worth looking at is the log, because everything ends up there. Its
default path is the sibling of the report root (`<reports_root>.log`). To check
the log against the disk:

```sh
cd <claude-informes>
.venv/Scripts/python -m claude_informes ultimo --proyecto <proyecto>
```

To send the log elsewhere while you test, without touching the real one, define
the environment variable `CLAUDE_INFORMES_LOG`.

## 6. Uninstalling

Remove the two entries you added to the `"hooks"` block of
`~/.claude/settings.json` (or restore your previous copy of that file).

To stop archiving one project without touching the Claude Code settings, add its
path to `"exclusions"` in the config. The guardian can be removed on its own, by
deleting its `PreToolUse` entry.
