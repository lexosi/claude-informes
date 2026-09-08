# 2026-09-08 — Git history rewrite

## What

The git history (47 commits) was rewritten with `git filter-repo` and
force-pushed to the private remote. Only the commit hashes changed.

## Why

The tip was clean, but the history still carried real private data in the old
commits: a Windows username, absolute paths, a `config/proyectos.json` that was
once committed, and the names of other private projects, in docstrings and test
fixtures. Removing them in a new commit does not erase them from history — the
only fix is to rewrite every commit that carried them.

## What was preserved

Commit dates, order, authorship, and the prose of every commit message. Nothing
was translated or squashed. The only content change was substituting the private
tokens for fictitious placeholders (real paths → `example-*`, private project
names → neutral names, the account name → `user`). This is why
[CONTRIBUTING.md](../../CONTRIBUTING.md) can still say the earlier commit messages
are left as they are: only the private tokens inside them were swapped.

## How it was verified

Three independent scans were run over every commit of a fresh clone taken from
the remote:

1. Canonical identifier scan (the guard's own logic): 0/47.
2. Raw substring scan, no canonicalization: 0/47.
3. Home-path form scan: the only usernames left are fictitious.

The suite passes and the commit messages carry no private token.

## Rollback

A `git bundle` of all refs and a `backup-pre-rewrite` branch were kept until the
rewrite was confirmed.
