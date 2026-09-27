# TASK-051

- component: data
- priority: medium
- state: COMPLETE
- branch: ado/task-051
- created: 2026-09-27T18:30:00+00:00
- dependencies: none

## Objective
Create minute_bars.py (Stage Q3): collect 1-minute OHLCV bars every day for the same-day trading universe so a minute-level history accumulates for backtesting same-day rules, plus a replay helper that walks a stored session minute by minute. Free minute history exists only for the last ~7 days (yfinance), so collection must start now and run daily; a missed week is lost. Plus its regression test.

## Background
The same-day universe is intraday_set.UNIVERSE (a list of 20 ticker strings; import it inside functions, not at module top). yfinance: yf.download(tickers, period="7d", interval="1m", progress=False, auto_adjust=False, group_by="ticker", threads=False) returns a DataFrame indexed by tz-aware timestamps in America/New_York with a column MultiIndex (ticker, field) where field is one of Open, High, Low, Close, Adj Close, Volume (with a single ticker and group_by="ticker" it is still (ticker, field)). Bars cover the regular session 09:30-15:59 ET; a bar for the current, unfinished minute may be present and must be dropped. Our daily prices are split/dividend-ADJUSTED; these minute bars are raw (auto_adjust=False) and are stored raw, marked as such.

## Relevant files
- `minute_bars.py`
- `tests/regression/test_minute_bars.py`
## Requirements
1. init(conn): CREATE TABLE IF NOT EXISTS minute_bars(ticker TEXT, ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, PRIMARY KEY(ticker, ts)) WITHOUT ROWID — ts is the bar's start in New York time as 'YYYY-MM-DD HH:MM'; CREATE TABLE IF NOT EXISTS minute_bars_log(run_at TEXT PRIMARY KEY, tickers INTEGER, rows INTEGER, first_ts TEXT, last_ts TEXT, note TEXT).
2. normalize(df, now=None) -> DataFrame with columns ticker, ts, open, high, low, close, volume from a yfinance frame as described (also accept a frame with single-level columns plus a `ticker` argument via normalize(df, ticker="SPY")): convert the index to America/New_York, keep only 09:30 <= time < 16:00, drop rows with a missing close, drop bars whose minute is not yet complete relative to `now` (a tz-aware datetime; default the current time): keep a bar only if bar_start + 1 minute <= now; drop rows with high < low or any price <= 0.
3. collect(conn, tickers=None, download=None, now=None) -> dict: download (default: a function wrapping yf.download as in Background, called once with the whole list) 7 days of 1-minute bars, normalize, INSERT OR IGNORE into minute_bars (existing bars are never overwritten), write a minute_bars_log row, return {"tickers": n, "rows_new": n, "first_ts": s, "last_ts": s}. A download that raises is logged in minute_bars_log with the error in note and returns rows_new 0 (never raises).
4. coverage(conn) -> list of dicts per ticker: sessions (distinct dates), first_ts, last_ts, bars.
5. session(conn, ticker, day) -> DataFrame of that ticker's bars for one date (ISO), sorted by ts.
6. replay(conn, day, tickers=None) -> iterator yielding (ts, {ticker: row dict}) minute by minute in time order for one session, each yield carrying only bars that exist at that minute (for simulating a same-day rule without look-ahead).
7. main(argv=None): --collect, --coverage (prints a table), --replay DAY TICKER (prints the first 5 and last 5 bars). Import runtime first; sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60) with from universe import load_config inside main.

## Constraints
1. Create ONLY minute_bars.py and tests/regression/test_minute_bars.py. Modify nothing else.
2. minute_bars.py under 200 lines; test under 150 lines.
3. The test never touches the network or the real database: pass a fake download function returning a synthetic frame with the (ticker, field) column MultiIndex for 2 tickers over 2 sessions, and use an in-memory sqlite3 connection.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_minute_bars.py exits 0.
2. The test checks: normalize keeps 09:30 and drops 16:00 and pre-market bars; drops the still-open minute relative to `now`; drops a bar with high < low; ts strings are New York time 'YYYY-MM-DD HH:MM' even when the input index is UTC; collect stores rows and a second collect with the same data adds 0 rows (never overwrites: change a close in the second download and the stored close is unchanged); a raising download is logged and returns rows_new 0; coverage counts sessions per ticker; session returns one day sorted; replay yields minutes in increasing order and never a bar from a later minute.
3. At least 9 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
