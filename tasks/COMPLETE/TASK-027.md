# TASK-027

- component: data
- priority: high
- state: COMPLETE
- branch: ado/task-027
- created: 2026-09-25T15:30:00+00:00
- dependencies: none

## Objective
Create crypto_costs.py (Stage K1): log Robinhood crypto bid/ask spreads into a crypto_spreads table and serve a measured half-spread per pair for backtests, plus its regression test.

## Background
Robinhood charges no crypto commission; the cost is the spread, measured once at ~1.9% round trip. Backtests must charge the MEASURED half-spread per side. The quote tool is called as call("get_crypto_quotes", {"symbols": ["BTC-USD", "ETH-USD"], "rhs_account_number": "403446024"}) where call is robinhood_mcp.call (import robinhood_mcp lazily inside the CLI only, never at module top). Its response shape is {"data": {"results": [{"symbol": "BTCUSD", "bid_price": "83401.74", "ask_price": "84983.6879688", "mark_price": "84192.71", "routing": "Market Maker Routing", "updated_at": "2026-09-25T01:00:27.034-04:00"}]}, "guide": "..."}. Prices are strings. The response symbol is unhyphenated: convert "BTCUSD" to "BTC-USD" by stripping a trailing "USD" and joining with "-USD". A row whose bid or ask is missing, not a number, or <= 0, or whose ask < bid, is skipped. spread_pct = (ask - bid) / ((ask + bid) / 2), a fraction (0.0188 means 1.88%). Settings come from cfg.get("crypto_costs") merged over DEFAULTS = {"default_half_spread": 0.0095, "window_days": 7, "min_samples": 12}. The account number comes from cfg["robinhood"]["account_number"] when present in the CLI path (the CLI loads config/risk.yaml with yaml.safe_load for that key). Symbols default to crypto_data.DEFAULT_PAIRS minus any whose crypto_listings row has status != 'online' or trading_disabled = 1 (the crypto_listings table may not exist; then use all DEFAULT_PAIRS).

## Relevant files
- `crypto_costs.py`
- `tests/regression/test_crypto_costs.py`
## Requirements
1. init(conn) creates table crypto_spreads (symbol TEXT NOT NULL, at_utc TEXT NOT NULL, bid REAL, ask REAL, mark REAL, spread_pct REAL NOT NULL, routing TEXT, quote_time TEXT, source TEXT DEFAULT 'robinhood', PRIMARY KEY (symbol, at_utc)).
2. parse_quotes(resp) returns a list of dicts with keys symbol, bid, ask, mark, spread_pct, routing, quote_time, following the Background rules.
3. log_spreads(conn, call, symbols, account, now=None) calls get_crypto_quotes once for all symbols, inserts one row per parsed quote with at_utc = now (ISO string, UTC, seconds precision; default current time), uses INSERT OR IGNORE, commits, and returns the number of rows inserted.
4. half_spread(conn, symbol, cfg=None, now=None) returns the MEDIAN spread_pct / 2 of that symbol's rows within window_days before now; if it has fewer than min_samples rows, the median over ALL symbols' rows in the window when those number at least min_samples; otherwise default_half_spread.
5. report(conn, now=None) returns a list of dicts per symbol in the window: symbol, n, median_spread_pct, mean_spread_pct, max_spread_pct, sorted by symbol.
6. main(argv=None) with argparse flags --log and --report; --log connects with storage.connect(cfg["database"]["market_data_path"]) and calls log_spreads with robinhood_mcp.call; --report prints a table with spreads in percent (two decimals). Import runtime first in the module.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else.
2. No network in tests; tests use a fake call function and sqlite3.connect(":memory:").
3. Keep crypto_costs.py under 220 lines and the test under 160 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import crypto_costs.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.
6. The test must not contain the string market_data.db and must not import robinhood_mcp.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_costs.py exits 0.
2. The test checks: symbol conversion BTCUSD -> BTC-USD; a zero-bid row skipped; spread_pct for bid 99 ask 101 equals 0.02; log_spreads inserts 2 rows and a repeat with the same now inserts 0; half_spread returns the per-symbol median/2 with >= min_samples rows; falls back to the all-symbol median; falls back to default_half_spread on an empty table.
3. At least 7 lines beginning with `  PASS`.
4. ./run_tests.sh reports ALL PASS.
