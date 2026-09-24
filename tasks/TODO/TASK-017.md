# TASK-017

- component: docs
- priority: high
- state: TODO
- branch: ado/task-017
- created: 2026-09-23T17:31:00+00:00
- dependencies: none

## Objective
Create changelog.py, which generates CHANGELOG.md from the git history (Phase 6 section 29).

## Background
Phase 6 section 29 requires a CHANGELOG.md. This project commits every change
separately and the git log is its change record, so the changelog is DERIVED
from git rather than maintained by hand, where it would drift. Merge commits
from the ADO workflow ("Merge ADO TASK-...") duplicate the task commit they
merge and are excluded.

## Relevant files
- `changelog.py`

## Requirements
1. Run `git log --no-merges --date=short --format=%ad%x09%h%x09%s` via subprocess from the script's own directory.
2. Group commits by date, newest date first; within a date keep git's order (newest first).
3. Output markdown: `# Changelog`, a line saying it is generated from git by changelog.py and must not be edited by hand, the total commit count, then per date a `## YYYY-MM-DD` heading with the commit count and a bullet per commit: `- subject (\`shorthash\`)`.
4. Also exclude any subject starting with "Merge " even if git reports it as a non-merge.
5. Provide `parse(log_text) -> dict[str, list[tuple[str, str]]]` and `render(groups) -> str` so the logic is testable without git.
6. CLI: `python changelog.py [--out CHANGELOG.md]`.

## Constraints
1. Create ONLY `changelog.py`. Modify nothing else.
2. Standard library only. Do not import runtime (no numpy/pandas here).
3. Do not generate CHANGELOG.md yourself; the reviewer runs the script.

## Acceptance criteria
1. `PYTHONPATH=. venv/bin/python -c "import changelog as c; g=c.parse('2026-09-23\tabc1234\tAdd x\n2026-09-22\tdef5678\tMerge ADO TASK-1\n2026-09-22\t0123456\tFix y\n'); s=c.render(g); assert '## 2026-09-23' in s and 'Merge ADO' not in s and s.index('2026-09-23') < s.index('2026-09-22'); print('ok')"` prints ok
2. `./run_tests.sh` reports ALL PASS.
