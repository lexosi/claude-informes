# DO NOT PUBLISH until the history is cleaned

**This repository must NOT be made public as it is.** The current tip is clean,
but the **git history** contains the author's real data. Making it public now
exposes them; removing them in a new commit **does not erase them from the
history**, which is exactly the mistake this file exists to prevent.

Today the repo is **private** on its remote, so there is no external leak. The
risk materializes the day it is made public. This is the last step before
publishing, not before.

## What the history contains (categories, not verbatim)

They are described by category on purpose: reproducing the values here would leak
them into the tip again.

1. **Real Windows username** — from two different machines of the author.
2. **Real absolute paths** — drive letter + author's projects root folder, and
   the report archive root.
3. **REAL `config/proyectos.json` committed** — the actual allowlist, with the
   paths of the author's projects. It is the most sensitive datum: it is not a
   fixture, it is the real configuration. It no longer exists in the tip (it was
   removed), but it is still in the history.
4. **Real names of other projects of the author** — in docstrings, README and
   fixtures of the old versions.

## In which commits

- **Data from the old machine** (username, real `config/proyectos.json`, absolute
  paths): the **6 published commits**, `811481e` .. `c3044d5`.
- **Username of the current machine and real project names**: present in the tree
  up to `1d314bd` inclusive.
- **First commit with an already-clean tree**: `c0fb708` (the one that fixed the
  guard and scrubbed the fixtures). From there on the tip is clean.

In short: everything **before `c0fb708`** has to be rewritten. The hashes may
shift as new commits land; the stable invariant is *"everything prior to the first
clean-tree commit"*.

## What to do before publishing

| Option | What it does | Cost |
| --- | --- | --- |
| `git filter-repo` (or BFG) + `push --force` | Rewrites every commit and deletes the blobs with real data | Changes every hash; rewrites history; irreversible on the remote |
| Recreate the repo from a clean tree | New history (e.g. a squash from `c0fb708`) | The commit history as a narrative of the process is lost |

The decision is the author's. An agent must not make it on its own.

## How to check it came out clean

It must give **zero** across the whole history, not only at HEAD:

```sh
# no real identifier, in any form, in any commit
git log -S "<usuario>"    --all --oneline
git log -S "<raiz-real>"  --all --oneline
git log --all -- config/proyectos.json   # must not exist in any commit
```

And the guard `tests/test_publicable.py` must pass on the tree of **every**
surviving commit, not only on the tip. That guard reads the real identifiers from
a file **outside git** (`identificadores_prohibidos.json`, next to the user
config); if it is missing, it **fails**, it does not skip. It covers the working
tree, **not** the history: this check and the one above are different.

## What is not translated, and why

The commit messages before the language switch, and the internal code names, the
JSON envelope keys and the log labels, are deliberately kept as they are. The
reasons are in [CONTRIBUTING.md](CONTRIBUTING.md#what-is-not-translated-and-why).

## Status

- Remote repo: **private** as of the date of this file.
- Tip (`HEAD`): no real identifiers in the working tree. Verified by
  `tests/test_publicable.py`, which now scans **itself too** (it used to exempt
  itself and pass green while it leaked the author's data). It is a tip check, not
  a history check.
- History: **dirty** — pending rewrite before publishing.
