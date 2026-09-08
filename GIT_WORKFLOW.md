# Git Workflow

This project (`stockpicker2000`) lives in **its own folder and its own GitHub
repository**, fully separate from `betbot9000`. Do not nest one inside the
other, and don't share a virtualenv/venv between them.

Suggested layout on the server:

```
~/projects/betbot9000/       (existing, untouched)
~/projects/stockpicker2000/    (this project)
```

## One-time setup

```bash
cd ~/projects/stockpicker2000
git init
git add .
git commit -m "Initial commit: stockpicker2000 v1"
gh repo create stockpicker2000 --private --source=. --push
# (or: git remote add origin <your-repo-url> && git push -u origin main)
```

`.gitignore` (below) excludes data, models, and logs — those are
generated locally per-machine and shouldn't bloat the repo or leak your
scoresheet history publicly if the repo is ever made public.

## Convention: every code change gets a commit + README update

Whenever a file in this project changes:

1. Update `README.md` if the change affects setup, usage, schema, or the
   pipeline shape (new script, new config key, changed file format, etc.)
2. Commit with a message describing *what* changed and *why*:
   ```bash
   git add -A
   git commit -m "Add ATR-based stop-loss calculation"
   git push
   ```
3. If it's a change Claude made during a chat session, Claude will call
   this out explicitly and remind you to commit/push — Claude cannot push
   to GitHub directly, only prepare the files.

## Suggested branch approach for a solo project

Given this is a single-maintainer project, committing directly to `main`
is fine for now. If backtesting (`backtest.py`) later becomes something
you iterate on heavily, consider a `strategy-experiments` branch so `main`
always reflects the version actually running live.
