# TASK-001

- component: data
- priority: high
- state: COMPLETE
- branch: ado/task-001
- created: 2026-09-22
- dependencies: none

## Objective
Create `data_audit.py`, which reports how complete the research universe
actually is, and writes both a machine-readable and a human-readable report.

## Background
Phase 6 section 6 requires this. The project knows it is missing thousands of
delisted companies but cannot currently state, per research period, which
securities have complete price history and which do not. Every backtest figure
inherits that gap, so it needs to be measurable rather than estimated.

## Relevant files
- `data_audit.py`
## Requirements
1. Read the database path and universe settings from `config.yaml` via `universe.load_config()`.
2. Import `runtime` as the first import, before pandas or numpy.
3. Connect with `storage.connect()`; do not open sqlite3 directly.
4. Report total securities in the `symbols` table, broken down by `security_type`.
5. Report how many securities have at least one row in `prices`, and how many have none.
6. Report delisted securities from the `delistings` table: total, how many have price rows, how many have none.
7. Report listing-date coverage: how many `symbols` rows have a non-null `first_seen`.
8. Report fundamental-date coverage: how many distinct tickers appear in `daily_fundamentals`.
9. Write a machine-readable report to `reports/data_completeness.json`.
10. Write a human-readable report to `reports/data_completeness.md`.
11. Create the `reports/` directory if it does not exist.
12. Provide a `main()` guarded by `if __name__ == "__main__":` and an `--out-dir` argument defaulting to `reports`.
13. Log progress with the `logging` module, not `print`, except for the final summary.

## Constraints
1. Do not modify any other file.
2. Do not write to any table. This module is read-only against the database.
3. Do not download anything.
4. Queries must complete on a 35M-row `prices` table; use aggregate SQL rather than loading frames into pandas.
5. Comments must explain why a choice was made, not restate the code.

## Acceptance criteria
1. python data_audit.py` exits 0.
2. reports/data_completeness.json` exists and parses as JSON.
3. reports/data_completeness.md` exists and is non-empty.
4. The JSON contains keys: `total_securities`, `securities_with_prices`, `securities_without_prices`, `delisted_total`, `delisted_with_prices`, `delisted_without_prices`.
5. ./run_tests.sh` still passes.

## Testing requirements
1. The module must run against the real database without error.
2. Numbers reported must be internally consistent: securities_with_prices + securities_without_prices == total_securities.

## Deliverables
1. data_audit.py
