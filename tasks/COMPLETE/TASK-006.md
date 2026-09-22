# TASK-006

- component: value
- priority: high
- state: COMPLETE
- branch: ado/task-006
- created: 2026-09-22T22:24:04+00:00
- dependencies: none

## Objective
Remove the alphabetical sampling bias from Value Fund candidate selection in value_fund.py, and report how much of the universe was actually scored.

## Background
`value_fund.candidates()` takes `limit: int = 600`, which flows into
`value_score.score_division` and then into a query ending
`ORDER BY ticker LIMIT 600`.

That is not a sample. It is the first 600 tickers ALPHABETICALLY out of 5,290
with a tradeable filing — 11% of the universe, spanning A to BEBE. The first
review preview proposed ten companies and every one of them was an A or B
ticker: ABUS, AZZ, APAM, AMN, ADMA, ADVB, APEI, ARES, BANR, BBW. A fund built
on that would hold an alphabetical accident and present it as a value screen.

The limit was a development convenience that became a sampling bias. A review
runs QUARTERLY, so it can afford to score everything: the current run takes
about three minutes for 600 names, implying roughly half an hour for all
5,290, which is acceptable for something that runs four times a year.

## Relevant files
- `value_fund.py`
## Requirements
1. Change the `limit` parameter of `candidates()` to default to `None`,
2. Pass that through to `value_score.score_division` unchanged. When `limit
3. Add a docstring paragraph to `candidates()` explaining that a limit here is
4. Make `candidates()` return the same shape it returns now: a list of row
5. Add a module-level function `coverage(conn, as_of)` returning a dict with
6. In `review()`, after computing candidates, record into the returned dict a
7. In `main()`, when printing a review, print a line stating how many

## Constraints
1. Modify ONLY `value_fund.py`. Do not touch `value_score.py`,
2. Do not change `BUY_PERCENTILE`, `SELL_PERCENTILE`, `MAX_POSITIONS`,
3. Do not add a dependency.
4. Do not add caching, threading or multiprocessing. A slow quarterly job is

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python -c "import inspect, value_fund;
2. PYTHONPATH=. venv/bin/python -c "import value_fund, storage; from universe
3. ./run_tests.sh` reports ALL PASS with 31 files.
4. git status --short` shows exactly one modified file, `value_fund.py`.
