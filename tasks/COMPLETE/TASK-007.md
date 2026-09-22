# TASK-007

- component: value
- priority: high
- state: COMPLETE
- branch: ado/task-007
- created: 2026-09-22T23:51:24+00:00
- dependencies: none

## Objective
Fix the TypeError that TASK-006 introduced: value_fund.candidates() passes limit=None into value_score._panel_metrics, which calls int(limit) and raises.

## Background
TASK-006 changed `value_fund.candidates()` to default `limit=None` so the fund
scores the whole universe instead of the first 600 tickers alphabetically.
That part was right and must be kept.

But it passes `None` straight through to `value_score.score_division`, which
passes it to `value_score._panel_metrics`, whose query ends:

    f"ORDER BY ticker LIMIT {int(limit)}"

`int(None)` raises `TypeError: int() argument must be a string, a bytes-like
object or a real number, not 'NoneType'`. The review crashes.

TASK-006's own requirement 2 said: if the callee cannot accept None, pass a
number larger than the universe (100000) rather than editing value_score.py.
That is what was missed.

**This got merged because the acceptance criteria were too weak** — they
checked the function signature and `coverage()`, and never ran the code path
that breaks. The criteria below run it.

## Relevant files
- `value_fund.py`
## Requirements
1. In `candidates()`, keep the parameter as `limit: int | None = None`.
2. When `limit` is None, call `value_score.score_division` with `100000
3. Do this once, in a local variable, rather than repeating the conditional at
4. Add a short comment saying WHY the substitution exists: `_panel_metrics
5. Do not otherwise change `candidates()`, `coverage()`, `review()`, `mark()`,

## Constraints
1. Modify ONLY `value_fund.py`. Do not touch `value_score.py`.
2. Do not add a dependency.
3. Do not change any constant.

## Acceptance criteria
1. This command exits 0 and prints a number, rather than raising TypeError:
2. The same command with `limit=None` passed explicitly also exits 0 without
3. PYTHONPATH=. venv/bin/python -c "import inspect, value_fund;
4. ./run_tests.sh` reports ALL PASS with 31 files.
5. git status --short` shows exactly one modified file, `value_fund.py`.
