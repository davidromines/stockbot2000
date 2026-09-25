# TASK-029

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-029
- created: 2026-09-25T16:10:00+00:00
- dependencies: TASK-027, TASK-028

## Objective
Create crypto_backtest.py (Stage K3): run a fixed, small grid of crypto_trend genomes over the daily crypto history, net of measured Robinhood spreads, and store one result row per strategy in crypto_backtests; plus its regression test.

## Background
crypto_trend.simulate(o, h, l, c, g, hs, start_i=0, close_at_end=True) returns {"trades": [...], "open": ...}; each trade has entry_i, exit_i, bars, gross, net. crypto_trend.summarize(trades) returns trades, gross_per_trade, net_per_trade, win_rate, mean_bars. crypto_trend.null_per_trade(o, trades, hs, lo_i, hi_i) and crypto_trend.buy_and_hold(o, c, lo_i, hi_i, hs) as their names say. crypto_costs.half_spread(conn, symbol, cfg) returns the per-side cost fraction. Bars live in table crypto_prices(symbol, open_time INTEGER epoch seconds, interval TEXT, bar_seconds, open, high, low, close, volume, ...); use interval '1d' ordered by open_time. A pair whose data ends early (delisted, e.g. MATIC-USD) is kept: its last position closes at its last close with reason "end". GRID: family trend_sma with n in (20, 50, 100, 200); tsmom with n in (30, 90, 180); breakout with n in (20, 55); each with stop_atr in (3.0, 5.0) and universe in ("btc_eth", "all") = 36 genomes. universe btc_eth = ["BTC-USD", "ETH-USD"]; all = every symbol with 1d bars. A genome is a dict {family, n, stop_atr, universe}; strategy_id = "ctrend_" + sha1(json.dumps(genome, sort_keys=True)).hexdigest()[:10]. Window: bars with open_time >= window start (default 2016-01-01 UTC) up to the last bar; indicators may read earlier bars (start_i = index of the first bar in the window; lo_i = start_i; hi_i = last index). Per symbol: hs = half_spread for that symbol, trades = simulate(..., start_i=start_i, close_at_end=True)["trades"], null = null_per_trade(o, trades, hs, start_i, N-1), bh = buy_and_hold(o, c, start_i, N-1, hs). Aggregate over the universe: all trades pooled into summarize; null_per_trade = trade-count-weighted mean of per-symbol nulls (symbols with None skipped); excess_per_trade = net_per_trade - null_per_trade; bh_mean = mean of per-symbol bh; half_spread_mean = mean hs over symbols; by_year = {entry year (UTC, from open_time at entry_i): {"trades": n, "net_per_trade": mean net}}.

## Relevant files
- `crypto_backtest.py`
- `tests/regression/test_crypto_backtest.py`
## Requirements
1. GRID constant and genomes() returning the 36 genome dicts in a stable order; strategy_id(genome) as in Background.
2. init(conn) creates crypto_backtests (strategy_id TEXT PRIMARY KEY, genome TEXT NOT NULL, window_start TEXT, window_end TEXT, symbols TEXT, trades INTEGER, gross_per_trade REAL, net_per_trade REAL, win_rate REAL, mean_bars REAL, null_per_trade REAL, excess_per_trade REAL, bh_mean REAL, half_spread_mean REAL, by_year TEXT, run_at TEXT).
3. load_bars(conn, symbol) returns (open_time int64 array, o, h, l, c float arrays) for interval '1d', or None when there are no bars; symbols_1d(conn) returns every symbol with 1d bars, sorted.
4. run_one(conn, genome, cfg=None, window_start="2016-01-01") computes the Background aggregates and returns a dict with every crypto_backtests column except run_at; window_start and window_end are ISO dates; symbols is a JSON list; by_year is JSON.
5. run(conn, cfg=None, window_start="2016-01-01", only=None) runs every genome (or those whose strategy_id is in `only`), INSERT OR REPLACE each row with run_at = current UTC time, commits, and returns the list of rows.
6. result(conn, strategy_id) returns the stored row as a dict, or None.
7. main(argv=None) with --run and --report; connect with storage.connect(load_config()["database"]["market_data_path"]) (from universe import load_config); pass cfg.get("crypto_costs") to half_spread; --report prints one line per stored row sorted by net_per_trade descending: strategy_id, family, n, stop_atr, universe, trades, gross %, net %, null %, excess %, buy-and-hold %, with percentages at two decimals. Import runtime first.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else.
2. No network. Tests use sqlite3.connect(":memory:") with crypto_prices created by crypto_data.init(conn) and synthetic bars; never open data/market_data.db.
3. Keep crypto_backtest.py under 240 lines and the test under 180 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_backtest.py exits 0.
2. The test checks: genomes() has 36 entries with unique strategy_ids; strategy_id is stable for an equal genome; run over two synthetic symbols (a steadily rising one of 400 daily bars and a falling one of 300 bars that ends early) writes one row per genome run; re-running replaces rather than duplicates rows; excess_per_trade equals net_per_trade minus null_per_trade; a rising-series trend_sma genome has net_per_trade below gross_per_trade (costs charged); window_start excludes entries before it; result() returns None for an unknown id.
3. At least 8 lines beginning with `  PASS`.
4. ./run_tests.sh reports ALL PASS.
