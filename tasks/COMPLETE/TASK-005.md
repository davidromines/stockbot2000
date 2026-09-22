# TASK-005

- component: reporting
- priority: normal
- state: COMPLETE
- branch: ado/task-005
- created: 2026-09-22T22:21:12+00:00
- dependencies: none

## Objective
Add the Stockbot Value Fund to fund_report.py so it appears in the daily report alongside the paper funds and pair funds.

## Background
Phase 9 item 30 added `value_fund.py`, a paper-only long-horizon portfolio.
It is deliberately kept out of the tactical strategy league — the two answer
different questions, and ranking a five-year thesis on eleven weeks of Sharpe
would imply a refutation that has not happened. But it still has to be
VISIBLE, or nobody will notice it drifting.

`fund_report.py` already renders paper funds and pair funds. It gains a value
fund section, following the pattern the pair-fund section already uses at
around line 196: import the module inside a try/except so one failing section
cannot kill the whole report.

The fund opened on 2026-09-21 with $100 and currently holds nothing. A report
that prints an empty section without explaining WHY is worse than no section,
because a reader assumes a bug. It has to say the fund is new and that its
first review has not run.

## Relevant files
- `fund_report.py`
## Requirements
1. Add a `VALUE FUND` section to the report produced by `render()`, placed
2. Wrap it in `try/except Exception` exactly as the pair-funds section does,
3. Import `value_fund` inside the try block, not at module top level, matching
4. Call `value_fund.status(conn)`. When it returns `{"exists": False}`, print
5. When the fund exists, print: the start date, the weighting, equity against
6. When positions exist, print one line per position with ticker, industry,
7. When the fund has FEWER than 60 daily marks, print a line stating it is not
8. Add one sentence to the closing explanatory block at the end of `render()
9. Use only `conn`, which `render()` already receives. Do not open a second

## Constraints
1. Modify ONLY `fund_report.py`. Do not touch `value_fund.py`.
2. Do not change any existing section's output text.
3. Do not add a dependency.
4. Do not add a command-line argument.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python fund_report.py --out /tmp/fr_test.txt` exits
2. The output contains the fund's start date `2026-09-21` and the text
3. ./run_tests.sh` reports ALL PASS with 31 files.
4. git status --short` shows exactly one modified file, `fund_report.py`.
