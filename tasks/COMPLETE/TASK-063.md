# TASK-063

- component: monitoring
- priority: low
- state: COMPLETE
- branch: ado/task-063
- created: 2026-10-03T00:00:00+00:00
- dependencies: none

## Objective
Add `--all-slots` flag to `signal_activity.py` that reads the current slot assignments from the database and prints an activity report for each of the five slots.

## Background
`signal_activity.py` has a CLI requiring `--key` and `--version`. Adding `--all-slots` lets the owner run one command to see all five slot strategies' signal activity without manually looking up each key/version.

Slot assignments are in `slot_assignments` table (columns: `id`, `at`, `slot_id`, `action`, `strategy_key`, `version`, `capital_usd`, `mode`, `reason`). The current holder for each slot is the most recent `ASSIGN` action row (by `at`) for that slot_id. Family name comes from `strategy_objects` table column `family` (join on `strategy_key` and `version`).

The `activity(conn, cfg, key, version, df=None, sessions=60)` function already exists and returns a dict with keys `measurable`, `active_sessions`, `sessions`, `last_signal`, and optionally `error`.

Output format (one line per slot):
```
slot 1  fx_earnings_surprise_abc123  v2  family=earnings_surprise  active=12/60  last=2026-09-30
slot 2  (empty)
slot 3  fx_etf_rotation_xyz  v1  family=etf_rotation  not measurable: frame lacks columns
```

## Relevant files
- `signal_activity.py`
- `tests/regression/test_signal_activity.py`
## Requirements
1. Add `--all-slots` boolean flag to the argparse parser. When set, `--key` and `--version` are not required.
2. Add function `all_slots(conn, cfg) -> list[dict]`: queries `slot_assignments` for the current holder of each slot_id (1-5), calls `activity()` for each occupied slot. Returns a list of 5 dicts: `{slot_id, strategy_key, version, family}` where strategy_key/version/family are None for empty slots; active slots additionally have the `activity()` return value merged in.
3. In `main()`, when `--all-slots` is set, call `all_slots()` and print a summary line per slot in the format shown above.
4. Create `tests/regression/test_signal_activity.py`: plain script (no pytest), creates an in-memory DB with `slot_assignments` and `strategy_objects` tables, inserts two slots (1 and 2 with valid keys) and leaves 3-5 empty, calls `all_slots(conn, cfg={})`, asserts the returned list has length 5, slots 1-2 have strategy_key set, slots 3-5 have strategy_key=None.

## Constraints
1. Do not change the `--key`/`--version` path in `main()`.
2. Do not change the `activity()` function signature.
3. Create ONLY changes to `signal_activity.py` and create `tests/regression/test_signal_activity.py`. Modify nothing else.
4. tests/regression/test_signal_activity.py` under 120 lines.

## Acceptance criteria
1. tests/regression/test_signal_activity.py` exits 0.
2. ./venv/bin/python signal_activity.py --help` shows `--all-slots` in the usage.
3. ./run_tests.sh` passes.
