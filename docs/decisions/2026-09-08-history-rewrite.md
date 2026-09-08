# 2026-09-08 — Git history rewrite

## What

The entire git history (47 commits) was rewritten with `git filter-repo` and
force-pushed to the private remote. Hashes changed; nothing else about the
narrative did.

## Why

The tip was already clean, but the **history** still carried the author's real
private data in the old commits (before the guard existed): a real Windows
username, real absolute paths, the real `config/proyectos.json` that was once
committed, and the real names of other private projects, left in docstrings and
test fixtures. Making the repo public would have exposed all of that. Removing it
in a new commit does **not** erase it from history — the only fix is to rewrite
every commit that carried it.

## What was preserved

Commit **dates, order, authorship, and the full prose of every commit message**.
Nothing was translated or squashed. The only change to content was the
substitution of the **private tokens** for fictitious placeholders (real paths →
`example-*`, private project names → neutral names, the account name → `user`).
This is why [CONTRIBUTING.md](../../CONTRIBUTING.md) can still say the earlier
commit messages are left as they are: they are — only the private tokens inside
them were swapped.

## How it was verified

Three **independent** reds were run over **every commit** of a fresh clone taken
**from the remote** (not from the local working copy), so the check covered what
the remote actually serves:

1. **Canonical identifier scan (§5)** — the publishability guard's own logic,
   which canonicalizes away escaping/encoding/case before comparing: **0/47**.
2. **Raw substring scan** — the same identifiers as literal substrings, with no
   canonicalization: **0/47**.
3. **Home-path form scan** — every home-directory-shaped path, by form: the only
   usernames left are **fictitious**.

Commit messages carry no private token; the full suite passes (354 tests).

## The lesson (why three reds, not one)

The canonical scan reported **0/47 while a real identifier still survived** in one
old fixture. The value was a home path written split across a line break: the
literal `\n` plus indentation broke the token adjacency that canonicalization
depends on, so **both** the canonical scan and the form detector read it as clean.
It took the **third** red — a raw substring scan with no canonicalization — to
catch it.

This is the project's recurring rule made concrete: **every gate defined with an
exception is the hole.** Canonicalization was the convenience; the `\n`-split was
the case it silently excused. One red that trusts a single normalization is not a
gate — it is a gate with an exception.

## Rollback

A full backup (a `git bundle` of all refs) and a `backup-pre-rewrite` branch
pointing at the pre-rewrite tip were kept until the rewrite was confirmed good.
