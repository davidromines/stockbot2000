# TASK-061

- component: monitoring
- priority: medium
- state: TODO
- branch: ado/task-061
- created: 2026-10-03T00:00:00+00:00
- dependencies: none

## Objective

Emit a `system_events` row when `strategy_health.py` records a new DEGRADING or FAILED state for a slot strategy.

## Background

`strategy_health.py` runs daily (`[9j]` in `daily.sh`) and writes rows to the `strategy_health` table. The `system_events` table (schema: `id INTEGER PRIMARY KEY, at TEXT, kind TEXT, detail TEXT, severity TEXT`) is the canonical place for noteworthy events; it is read by `eod_report.py` under the FAILURES section and by the Control Center.

`strategy_health.run(conn, cfg)` already reads the previous state before writing a new one (line ~260: `SELECT state FROM strategy_health WHERE strategy_key=? AND version=?`). The new behaviour: if prev_state != new_state AND new_state in ("DEGRADING", "FAILED"), insert into `system_events`.

Insert values: `kind='health_alert'`, `detail=f"{key} v{version}: {new_state} — {reason}"`, `severity='warning'` for DEGRADING or `severity='critical'` for FAILED. Use `datetime.utcnow().isoformat(timespec='seconds') + 'Z'` for `at`.

Do NOT import `killswitch` to perform the insert — use inline SQL. If `system_events` does not exist (e.g., a fresh test DB without killswitch.init), catch `sqlite3.OperationalError` silently.

## Relevant files

- `strategy_health.py`
- `tests/regression/test_strategy_health.py`

## Requirements

1. In `strategy_health.run(conn, cfg)`, after writing a new health row, check if new_state in ("DEGRADING", "FAILED") and prev_state (from the prior SELECT) differs. If so, INSERT into `system_events`.
2. Insert: `INSERT INTO system_events (at, kind, detail, severity) VALUES (?,?,?,?)` with the values described in Background.
3. Wrap the insert in try/except sqlite3.OperationalError and silently skip.
4. Create `tests/regression/test_strategy_health.py`: a plain script (no pytest) that creates an in-memory DB, calls `strategy_health.run` twice (first call produces FAILED from HEALTHY, second call produces FAILED again), and asserts exactly one `system_events` row with `kind='health_alert'` and `severity='critical'`.

## Constraints

1. Do not change the `strategy_health` table schema.
2. Do not change the health evaluation logic in `strategy_health.py`.
3. Create ONLY changes to `strategy_health.py` and create `tests/regression/test_strategy_health.py`. Modify nothing else.
4. `tests/regression/test_strategy_health.py` under 120 lines.

## Acceptance criteria

1. `tests/regression/test_strategy_health.py` exits 0.
2. The test confirms HEALTHY -> FAILED writes exactly one `system_events` row with `kind='health_alert'` and `severity='critical'`.
3. A second run with the same FAILED result writes no additional row.
4. `./run_tests.sh` passes.
