# TASK-056

- component: trading
- priority: high
- state: IN_PROGRESS
- branch: ado/task-056
- created: 2026-09-29T02:00:00+00:00
- dependencies: none

## Objective
Create signal_activity.py: measure how often a strategy's entry rule actually fires, so a slot is never held by a strategy that cannot trade now (owner, 2026-09-28: a "December effect" strategy held slot 1 in September). Pure functions over a price/indicator frame plus a thin wrapper. Plus its regression test.

## Background
A strategy genome is a dict {"entry": node, "exit": node, "risk": {...}}; genome.evaluate(node, df) returns a Series aligned to df (numeric or boolean) and genome._as_bool(series) turns it into booleans (NaN -> False). The frame df has one row per (ticker, date) with columns "ticker", "date" ('YYYY-MM-DD' strings) and indicator columns, sorted by ticker then date; rules such as pct_change / lag look back within each ticker. paper_trading._recent_frame(conn, cfg) returns the trailing window (about 400 calendar days) the live system evaluates rules on. slots.genome_for(conn, key, version) returns a strategy's genome, or a dict with a "pair", "value", "rotation" or "crypto" key for fund-type strategies (those have no entry rule to measure), or None.

## Relevant files
- `signal_activity.py`
- `tests/regression/test_signal_activity.py`
## Requirements
1. active_sessions(df, genome, sessions=60) -> int: the number of distinct dates, among the last `sessions` distinct dates in df["date"], on which the genome's entry rule is True for at least one row. Evaluate the rule once over the whole frame (never row by row), then restrict to those dates.
2. last_signal(df, genome) -> str | None: the latest date on which the entry rule was True for any row, or None if never.
3. measurable(genome) -> bool: True only for a dict with an "entry" node and none of the keys "pair", "value", "rotation", "crypto".
4. activity(conn, cfg, key, version, df=None, sessions=60) -> dict {"key", "version", "measurable", "active_sessions", "last_signal"}; genome from slots.genome_for (import inside the function); when not measurable, active_sessions and last_signal are None; df defaults to paper_trading._recent_frame(conn, cfg) (import inside). A rule that raises during evaluation counts as measurable with active_sessions 0 and an "error" key holding the exception text.
5. main(argv=None): --key KEY --version N [--sessions 60] prints the activity dict. Import runtime first; from universe import load_config inside main; sqlite3.connect("file:<market_data_path>?mode=ro", uri=True) with row_factory sqlite3.Row.

## Constraints
1. Create ONLY signal_activity.py and tests/regression/test_signal_activity.py. Modify nothing else.
2. signal_activity.py under 120 lines; test under 130 lines. pandas and numpy only, plus the project modules named above.
3. The test builds a synthetic frame (3 tickers x 100 business days, columns ticker, date, close, plus a column "flag" that is 1 on chosen rows) and uses genomes whose entry node is {"op": "gt", "args": [{"col": "flag"}, {"const": 0.5}]}; it must not touch the database except activity() with a monkeypatched slots.genome_for and an explicit df.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_signal_activity.py exits 0.
2. The test checks: a rule firing on 5 distinct recent dates gives 5; firing on two tickers the same date counts once; firings older than the window are not counted; a rule that never fires gives 0 and last_signal None; last_signal returns the latest firing date; measurable is False for pair / value / rotation / crypto genomes and None; activity() returns measurable False with active_sessions None for a rotation genome; a rule referencing a missing column gives active_sessions 0 with an "error" key.
3. At least 8 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
