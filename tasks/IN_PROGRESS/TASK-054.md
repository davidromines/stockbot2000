# TASK-054

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-054
- created: 2026-09-27T22:30:00+00:00
- dependencies: none

## Objective
Create rotation.py: a sector / asset-class ETF rotation engine (relative momentum with an optional absolute-momentum filter, Faber 2007; Antonacci 2014 "dual momentum") — ranking a fixed ETF universe on its trailing return, holding the top K, rebalancing monthly, stepping into a safe ETF when momentum is not positive. Pure functions over price frames plus loaders; used for backtests, paper trading and live slots by other modules. Plus its regression test.

## Background
Prices: table prices(ticker TEXT, date TEXT 'YYYY-MM-DD', open REAL, high REAL, low REAL, close REAL, volume REAL), split/dividend adjusted. A trading day is a date present for SPY. Entries and exits fill at the NEXT session's open after the signal day's close (the project's fill convention). Costs: charge `cost_bps` (basis points) of each trade's notional on entry AND on exit.

## Relevant files
- `rotation.py`
- `tests/regression/test_rotation.py`
## Requirements
1. UNIVERSES = {"sectors": ["XLB","XLE","XLF","XLI","XLK","XLP","XLU","XLV","XLY"], "assets": ["SPY","EFA","EEM","TLT","IEF","GLD","VNQ","DBC"]}; SAFE = "SHY".
2. load(conn, tickers, start, end) -> (close, open): two DataFrames indexed by date string, one column per ticker, from the prices table (pivot), restricted to SPY's dates; missing values stay NaN.
3. month_starts(dates) -> list of the first date of each calendar month in the sorted date index.
4. rank(close, as_of, lookback, universe) -> list of (ticker, trailing return) sorted best first: return = close[as_of] / close[lookback sessions earlier] - 1 for tickers with both values; tickers lacking data are omitted.
5. holdings(close, as_of, params) -> list of tickers to hold after the signal day `as_of`. params: {"universe": key of UNIVERSES, "lookback": int sessions, "top_k": int, "abs_filter": bool}. Take the top_k of rank(); with abs_filter, each chosen ticker whose trailing return is not greater than SAFE's trailing return over the same lookback is replaced by SAFE (SAFE may appear once; if every pick is replaced the result is [SAFE]). Without abs_filter SAFE is never held. Returns [] if no ticker can be ranked.
6. backtest(close, open_, params, start, end, cost_bps=5.0) -> dict: signal days are the LAST session of each month within [start, end] (the day before each month start); on the next session's open, sell holdings no longer chosen and buy new ones; an unchanged holding is carried (no trade). Each position is equal weight of the book (1/len(holdings)). A "trade" is one holding from its entry open to its exit open (the final open trades are closed at the last open in the range). Return {"trades": list of dicts (ticker, entry_date, exit_date, ret_gross, ret_net), "n_trades", "mean_net", "mean_gross", "win_rate", "equity": pd.Series of the book's value by date starting at 1.0 (marked at close, costs deducted when trades occur), "cagr", "max_drawdown" (positive fraction), "benchmark_cagr" (SPY buy and hold over the same dates)}.
7. current(conn, params, as_of=None) -> {"as_of": date, "holdings": list, "ranked": rank() output} using load() over enough history (lookback + 30 sessions) ending at as_of (default: SPY's latest date).
8. main(argv=None): --backtest --universe sectors --lookback 126 --top-k 3 [--abs-filter] [--start 2006-01-01] [--end today]; prints n_trades, mean net per trade, CAGR vs SPY, max drawdown; --current (same params) prints today's holdings. Import runtime first; sqlite3.connect(load_config()["database"]["market_data_path"]) read-only via "file:...?mode=ro", uri=True; from universe import load_config inside main.

## Constraints
1. Create ONLY rotation.py and tests/regression/test_rotation.py. Modify nothing else.
2. rotation.py under 230 lines; test under 170 lines. pandas and numpy only.
3. The test uses synthetic price frames (no database except an in-memory sqlite3 for load()): e.g. 3 sector tickers + SHY + SPY over ~400 business days where one ticker trends up, one down, one flat.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_rotation.py exits 0.
2. The test checks: rank orders by trailing return and omits a ticker with missing data; holdings takes the top_k; with abs_filter a ticker trailing SHY is replaced by SHY and a book of all-losers becomes [SHY]; without abs_filter SHY never appears; backtest trades fill at the next session's open (entry_date is the day after the signal day), a carried holding makes no new trade, the uptrend ticker is held most of the time and the backtest's mean_net is below mean_gross by the cost; max_drawdown is between 0 and 1; load() pivots an in-memory prices table and keeps only SPY's dates; month_starts returns one date per month.
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
