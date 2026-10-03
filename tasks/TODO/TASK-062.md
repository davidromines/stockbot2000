# TASK-062

- component: acceptance
- priority: low
- state: TODO
- branch: ado/task-062
- created: 2026-10-03T00:00:00+00:00
- dependencies: none

## Objective

Add acceptance check 27 to `acceptance.py`: verify that `slots.plan(conn, {})` with an empty config dict produces no `KeyError: 'universe'` WARNING in the slots logger.

## Background

Commit d816d2d fixed `slots._idle_check` to catch `KeyError`/`TypeError` silently when `cfg={}`. The fix prevents a spammy WARNING that previously appeared in acceptance test logs. This check pins the fix as a regression guard in the acceptance checklist itself. A matching regression test already exists in `tests/regression/test_slots.py` (passes since d816d2d), but having an acceptance item makes the fix visible when running the checklist.

`acceptance.py` currently has 26 items. The 27th item is added at the end of `run()` before `return items`. The item's function captures the `slots` logger output, calls `slots.plan(conn, {})` with a mocked `slots.assess`, then asserts `"KeyError: 'universe'"` does not appear.

Pattern for capturing the logger (already used in `test_slots.py`):
```python
import logging, io
log_buf = io.StringIO()
handler = logging.StreamHandler(log_buf)
logging.getLogger("slots").addHandler(handler)
try:
    ... slots.plan(conn, {}) ...
    warn_output = log_buf.getvalue()
finally:
    logging.getLogger("slots").removeHandler(handler)
```

The `_fixture()` helper and `_patch()` function are already available in `acceptance.py`.

## Relevant files

- `acceptance.py`

## Requirements

1. Add `item(27, "slots.plan with empty cfg emits no KeyError: 'universe' warning", fn)` at the end of `run()` before `return items`.
2. `fn()` uses an in-memory fixture via `_fixture()`, patches `slots.assess` to return one minimal row, captures the `slots` logger, calls `slots.plan(conn, {})`, then returns `(True, "no KeyError: 'universe' in log")` if the warning is absent, else `(False, repr(warn_output[:200]))`.
3. Update the module docstring `"Twenty-six items"` to `"Twenty-seven items"`.
4. Update `ap.add_argument` description from `"(26 executed items)"` to `"(27 executed items)"`.

## Constraints

1. Do not change items 1-26.
2. Create ONLY changes to `acceptance.py`. Modify nothing else.

## Acceptance criteria

1. `python acceptance.py --no-suite 2>&1 | grep "27\."` shows `PASS  27`.
2. `./run_tests.sh` passes.
