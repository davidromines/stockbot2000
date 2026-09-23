# TASK-010

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-010
- created: 2026-09-23T05:44:25+00:00
- dependencies: none

## Objective
Create tests/regression/test_stop_and_compute.py covering stop_conditions.py and compute_priority.py, following the style of the existing files in tests/regression/.

## Background
Phase 6 sections 27 and 28.

`stop_conditions.py` must be able to say DO NOT SEARCH and have that treated
as a legitimate answer. Its four conditions are trial count, diminishing
returns, data quality and validation failures, and ANY ONE is sufficient.

Two defects already found in it, both of which reported the check as PASSING
while it was in fact broken — which is worse than a check that is absent,
because the report shows green:

- it read a dict key that does not exist, so the data-quality condition never
  fired at all;
- reading the right key then reported "0.0% coverage" for a date where
  coverage is UNMEASURABLE (the directory snapshots start after the search
  window opens). Unknown was being rendered as zero.

`compute_priority.py` makes the spec's ordering checkable: data integrity
first, strategy search LAST. `may_run(tier)` refuses a tier when
higher-priority work failed recently.

## Relevant files
- `tests/regression/test_stop_and_compute.py`
- `stop_conditions.py`
- `compute_priority.py`
## Requirements
1. Import `runtime` as the very first import, before pandas or numpy.
2. Use an in-memory sqlite3 database with `conn.row_factory = sqlite3.Row`.
3. Follow the existing style in `tests/regression/`: module docstring, a
4. For stop_conditions, create the tables its queries touch so it can run
5. Test that `evaluate()` returns `stop=True` when the trial count exceeds
6. Test that `evaluate()` returns `stop=True` when the void rate exceeds
7. Test that `evaluate()` returns `stop=True` when random strategies clear
8. Test that the data-quality check distinguishes UNMEASURABLE from zero:
9. Test that ANY single condition is sufficient: with only one condition
10. Test that `render()` output contains "DO NOT SEARCH" when stop is True
11. For compute_priority, test that `TIER_OF` maps `evolve.py` to tier 6 and
12. Test `record()` writes a row with the correct tier, and that an unknown
13. Test `may_run()`: returns True when higher tiers succeeded, False when a
14. Test `spend()` computes `search_share` correctly and sets `honoured` to

## Constraints
1. Create ONLY `tests/regression/test_stop_and_compute.py`. Modify nothing
2. No new dependency. No network. Do not open the real database.
3. Do not use pytest.
4. If a function cannot be exercised against an in-memory database because it

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_stop_and_compute.py
2. It prints at least 12 lines beginning with `  PASS`.
3. ./run_tests.sh` reports ALL PASS with 34 files.
4. git status --short` shows exactly one added file.
