# Git Workflow

This project (`stockbot2000`) lives in **its own folder and its own GitHub
repository**, fully separate from `betbot9000`. Do not nest one inside the
other, and don't share a virtualenv/venv between them.

Actual layout on the Arena VM (hostname `stockpicker2000`, user `stockpicker` —
both predate the rename and are unchanged):

```
~/stockbot2000/           (this project — the repo root)
```

`betbot9000` is not on this VM. An earlier draft of this file suggested
`~/projects/stockbot2000`; the repo has always lived at `~/stockbot2000`
and `CLAUDE.md` refers to that path, so this doc was corrected to match rather
than the other way round.

## One-time setup — done 2026-09-08

```bash
cd ~/stockbot2000
git init -b main
git add .
git commit -m "Initial commit: stockbot2000 on Arena VM"
```

Remote is **not yet configured**. `gh` is not installed on this VM. To add one
later, either install `gh` and run `gh repo create stockbot2000 --private
--source=. --push`, or add the remote by hand:

```bash
git remote add origin <your-repo-url>
git push -u origin main
```

Keep the repo **private** — the scoresheet history and position ledger paths
are in here.

`.gitignore` (below) excludes data, models, and logs — those are
generated locally per-machine and shouldn't bloat the repo or leak your
scoresheet history publicly if the repo is ever made public.

## The rule: every change gets its own commit

**Not "every code change" — every change.** Code, config, documentation, a typo
fix in a comment. Each one is committed before the next piece of work starts, so
the git log reads as a complete, ordered record of how the project got here.

Corollaries:

- Never batch several unrelated edits into one commit. One change, one commit,
  one message that explains it.
- Never end a working session with uncommitted changes in the tree.
- Claude commits as it goes, without being asked each time. If Claude changes a
  file, Claude commits it.

Whenever a file in this project changes:

1. Update `README.md` if the change affects setup, usage, schema, or the
   pipeline shape (new script, new config key, changed file format, etc.)
2. Commit with a message describing *what* changed and *why*:
   ```bash
   git add -A
   git commit -m "Add ATR-based stop-loss calculation"
   git push
   ```
3. Claude, running in Claude Code on this VM, commits directly — it does not
   just prepare files and remind you. Pushing to a remote is a separate,
   outward-facing step and Claude asks before doing it.

## Suggested branch approach for a solo project

Given this is a single-maintainer project, committing directly to `main`
is fine for now. If backtesting (`backtest.py`) later becomes something
you iterate on heavily, consider a `strategy-experiments` branch so `main`
always reflects the version actually running live.
