# TASK-022

- component: tests
- priority: high
- state: TODO
- branch: ado/task-022
- created: 2026-09-24T06:59:36+00:00
- dependencies: none

## Objective
Create tests/regression/test_strategy_objects.py covering strategy_objects.py (Phase 13 H3: metadata, metrics, §37 decisions).

## Background
strategy_objects wraps league.py identity. register(conn, obj) is idempotent and mints a new version only when the genome/parameters change; the first version enters the lifecycle log at DISCOVERED. decide() writes a strategy_decisions row EVEN WHEN league.transition refuses the move (the reason gets a [transition refused: ...] suffix and to_state is NULL). A genome is built with strategy_factory.G(strategy_factory.gt(strategy_factory.col("rsi_14"), strategy_factory.k(50))). An obj needs strategy_key, name, family, league, genome, parameters, source.

## Relevant files
- `tests/regression/test_strategy_objects.py`
- `strategy_objects.py`
- `league.py`
- `strategy_factory.py`
## Requirements
1. key_for is deterministic: same family and params give the same key; different params give a different key; the key starts with fx_.
2. register twice with an identical obj returns the same version and new False the second time.
3. register with a changed genome (different k constant) returns version 2 and new True; version 1 meta is still readable via meta(conn, key, 1).
4. After the first register, league.state(conn, key, 1) is DISCOVERED.
5. genome(conn, key, 1) returns a dict whose entry equals the registered genome entry.
6. record_metrics then latest_metrics for phase backtest returns the recorded net_usd; a second record returns the newer one.
7. decide with to_state SPECIFIED from DISCOVERED moves the state; the returned dict has to == SPECIFIED and refused None.
8. decide with a skipping to_state (e.g. PAPER from SPECIFIED) is refused: state unchanged, returned refused is not None, and a strategy_decisions row still exists whose reason contains 'transition refused'.
9. decide with an unknown decision string raises ValueError; an unknown classification raises ValueError.
10. classification() returns UNTESTED before any classified decision and the latest classification after one.
11. in_state(conn, SPECIFIED) contains (key, 1).

## Constraints
1. Create ONLY the test file this task names. Modify nothing else.
2. No network, no pytest, never open data/market_data.db. Use sqlite3.connect(":memory:") with conn.row_factory = sqlite3.Row.
3. Keep the file under 280 lines. If a function needs a table not created by an init() helper, create it in the fixture.
4. Import `runtime` first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import the modules under test.
5. Plain script, no pytest: a `check(name, cond, detail="")` helper printing `  PASS  name` or `  FAIL  name`, then `sys.exit(1)` if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_strategy_objects.py exits 0.
2. At least 11 lines beginning with `  PASS`.
3. The file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
