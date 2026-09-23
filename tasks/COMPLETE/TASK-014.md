# TASK-014

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-014
- created: 2026-09-23T15:19:03+00:00
- dependencies: none

## Objective
Add regression checks for value_fund.review_due() to tests/regression/test_value_fund.py.

## Background
`value_fund.py` declared `REVIEW_DAYS = 90` from the start and never read it,
so `review()` ran whenever it was called. Wired into the daily pipeline as
written, that would have rebalanced a quarterly fund every morning — turning a
long-horizon value book into a high-turnover one.

`review_due(conn, as_of)` now gates it and returns `(due, why)`:
- no value_fund row           -> (False, "no value fund")
- last_review is NULL         -> (True,  "first review — ...")
- last_review >= 90 days ago  -> (True,  "last review N days ago ...")
- last_review < 90 days ago   -> (False, "... next due in N")

## Relevant files
- `tests/regression/test_value_fund.py`
- `value_fund.py`
## Requirements
1. ADD checks to the existing `tests/regression/test_value_fund.py`. Do not
2. Use an in-memory database and call `value_fund.init(conn)`, as the file
3. Check `review_due` returns `(False, ...)` when no fund row exists.
4. Check it returns `(True, ...)` when the fund exists and `last_review` is
5. Check it returns `(False, ...)` when `last_review` is 30 days before
6. Check it returns `(True, ...)` when `last_review` is exactly
7. Check it returns `(False, ...)` when `last_review` is `REVIEW_DAYS - 1` days
8. Check that `REVIEW_DAYS` is actually read by the module: assert
9. Set `last_review` directly with an UPDATE on the in-memory value_fund row

## Constraints
1. Modify ONLY `tests/regression/test_value_fund.py`.
2. No network. No new dependency. Do not use pytest.
3. Do not change `value_fund.py`.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_value_fund.py` exits 0.
2. The file prints at least 6 more PASS lines than before this change.
3. ./run_tests.sh` reports ALL PASS with 35 files.
