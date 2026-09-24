# TASK-025

- component: tests
- priority: high
- state: TODO
- branch: ado/task-025
- created: 2026-09-24T06:59:36+00:00
- dependencies: none

## Objective
Create tests/regression/test_robustness.py covering robustness.py (Phase 13 H10: collapse tests).

## Background
robustness._perturb scales every const in a genome tree by f, except 0, 0.0 and 0.5 (0.5 marks boolean features). regime_labels(conn, start, end) reads SPY closes from a prices table and labels bull (close > 200-day SMA), high_vol and crisis (close < 80% of the 252-day high); it returns an empty frame with the four columns when SPY is absent. analyse() returns verdict INSUFFICIENT_SAMPLE with no trades before touching the simulator: call it with base={"pnl_series": []} and panel=None, cm=None.

## Relevant files
- `tests/regression/test_robustness.py`
- `robustness.py`
## Requirements
1. _perturb on {op: gt, args: [{col: x}, {const: 50}]} with f 1.1 gives const 55.0 (within 1e-9) and does not mutate the input.
2. _perturb leaves {const: 0.5} and {const: 0} unchanged.
3. _perturb reaches nested args (an and of two comparisons).
4. regime_labels on an empty prices table (columns ticker,date,open,high,low,close,volume) returns an empty frame with columns date, bull, high_vol, crisis.
5. regime_labels on 400 synthetic SPY rows rising steadily then one final date at 70% of the peak labels that final date crisis True and an earlier rising date bull True.
6. analyse with an empty pnl_series returns verdict INSUFFICIENT_SAMPLE.
7. RULES contains bootstrap_min_share, param_min_share, universe_min_share, regime_min_trades and max_failures.

## Constraints
1. Create ONLY the test file this task names. Modify nothing else.
2. No network, no pytest, never open data/market_data.db. Use sqlite3.connect(":memory:") with conn.row_factory = sqlite3.Row.
3. Keep the file under 280 lines. If a function needs a table not created by an init() helper, create it in the fixture.
4. Import `runtime` first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import the modules under test.
5. Plain script, no pytest: a `check(name, cond, detail="")` helper printing `  PASS  name` or `  FAIL  name`, then `sys.exit(1)` if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_robustness.py exits 0.
2. At least 7 lines beginning with `  PASS`.
3. The file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
