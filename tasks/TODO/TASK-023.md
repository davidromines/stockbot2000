# TASK-023

- component: tests
- priority: high
- state: TODO
- branch: ado/task-023
- created: 2026-09-24T06:59:36+00:00
- dependencies: none

## Objective
Create tests/regression/test_discovery.py covering discovery.py (Phase 13 H9: priority, budgets, failures, recycling).

## Background
discovery.priority(fam, rec, cfg, source) returns None for a family with no rationale or data_available False (look up a real family in strategy_factory.F for each case; pick one with data_available False if any exists, else skip that check with a PASS noting none exist). take(conn, cfg, n) returns at most n items and at most PER_FAMILY_PER_RUN per family, skipping items whose strategy is no longer DISCOVERED (and marking them done). record_failure writes failure_log. recycle() mutates REJECTED fx_ strategies into a new version, never recycling one whose last failure stage is data or sample. Use strategy_objects.register to create strategies (see strategy_objects.py), and research_queue.enqueue to queue them. cfg is a plain dict: {"factory": {"family_explored_after": 8, "max_backtests_per_run": 12, "max_recycles_per_strategy": 2}}.

## Relevant files
- `tests/regression/test_discovery.py`
- `discovery.py`
- `strategy_objects.py`
- `research_queue.py`
- `league.py`
- `strategy_factory.py`
## Requirements
1. priority for an untested family with a rationale and data is a float greater than the same family's priority when rec shows tested >= 8 and good 0.
2. priority with source recycle is lower than with source template for the same family and rec.
3. priority returns None for a family name not in strategy_factory.F.
4. take with n=3 over 5 queued DISCOVERED strategies from one family returns at most PER_FAMILY_PER_RUN items.
5. take skips an item whose strategy was moved out of DISCOVERED (use strategy_objects.decide with to_state SPECIFIED) and that queue item's status becomes done.
6. record_failure then a SELECT on failure_log returns the stage and reason written.
7. recycle on a REJECTED fx_ strategy (DISCOVERED -> REJECTED via strategy_objects.decide with decision REJECT) whose failure stage is backtest creates version 2 whose meta source is recycle.
8. recycle does NOT create a new version when the last failure stage is data.
9. family_record counts the rejected strategy under rejected for its family.

## Constraints
1. Create ONLY the test file this task names. Modify nothing else.
2. No network, no pytest, never open data/market_data.db. Use sqlite3.connect(":memory:") with conn.row_factory = sqlite3.Row.
3. Keep the file under 280 lines. If a function needs a table not created by an init() helper, create it in the fixture.
4. Import `runtime` first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import the modules under test.
5. Plain script, no pytest: a `check(name, cond, detail="")` helper printing `  PASS  name` or `  FAIL  name`, then `sys.exit(1)` if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_discovery.py exits 0.
2. At least 9 lines beginning with `  PASS`.
3. The file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
