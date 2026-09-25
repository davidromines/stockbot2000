# TASK-030

- component: paper
- priority: high
- state: TODO
- branch: ado/task-030
- created: 2026-09-25T16:40:00+00:00
- dependencies: TASK-028, TASK-029

## Objective
Create crypto_trend_fund.py (Stage K4): forward paper funds for crypto_trend genomes, stored in the EXISTING crypto_fund tables so accounting.py and leagues.py pick them up unchanged; plus its regression test.

## Background
crypto_fund.init(conn) creates the tables: crypto_fund(name PK, capital_usd, started_ts, interval, strategy TEXT json, library_ref, symbols TEXT json, status, last_step, created_at), crypto_fund_trades(name, symbol, entry_ts, exit_ts, reason, levels, deployed_usd, gross_usd, fees_usd, net_usd, ret_pct, null_pct; PK name,symbol,entry_ts), crypto_fund_open(name, symbol, entry_ts, state TEXT json; PK name,symbol), crypto_fund_equity(name, date, equity_usd, realised_usd, unrealised_usd, open_positions; PK name,date). Bars: crypto_prices(symbol, open_time epoch seconds, interval, open, high, low, close) with interval '1d'. crypto_trend.simulate(o, h, l, c, g, hs, start_i, close_at_end=False) returns {"trades": [...], "open": None or {entry_i, entry_px, stop}}; trade dicts have entry_i, exit_i, entry_px, exit_px, reason, gross, net. crypto_costs.half_spread(conn, symbol, cfg) gives hs. crypto_backtest.strategy_id(genome) names a genome. crypto_listings(symbol, status, trading_disabled) marks online pairs. A fund is DETERMINISTIC REPLAY like crypto_fund.step: every step replays each symbol from the fund's start and records closed trades with INSERT OR IGNORE keyed by (name, symbol, entry_ts), and rewrites crypto_fund_open for the fund, so re-running a step changes nothing. Only bars whose open_time >= started_ts may produce an entry (start_i = first index with open_time >= started_ts); earlier bars feed indicators only. started_ts at open = the newest 1d open_time + 86400 (the next bar to open), unless given. Capital is split evenly across the fund's symbols: per_symbol = capital / len(symbols). For a closed trade: deployed_usd = per_symbol, gross_usd = per_symbol * gross, net_usd = per_symbol * net, fees_usd = gross_usd - net_usd, ret_pct = net * 100, levels = 1, null_pct NULL. Open position state JSON: {"entry_px", "stop", "deployed_usd": per_symbol, "qty": per_symbol * (1 - hs) / entry_px, "last_close": last close, "entry_fees_usd": per_symbol * hs, "hs": hs}. The hs used for a symbol is fixed at the fund's open and stored in the strategy JSON as {"hs": {symbol: value}} so later spread measurements never rewrite the forward record.

## Relevant files
- `crypto_trend_fund.py`
- `tests/regression/test_crypto_trend_fund.py`
## Requirements
1. open_fund(conn, name, genome, capital=100.0, symbols=None, cfg=None, started_ts=None) inserts one crypto_fund row: interval '1d', strategy = json {"engine": "crypto_trend", "genome": genome, "strategy_id": crypto_backtest.strategy_id(genome), "hs": {...}}, library_ref = the strategy_id, symbols = given list or every online pair (crypto_listings status 'online' and trading_disabled 0) that has 1d bars, sorted; status 'open'; raises SystemExit if the name exists; returns a dict of what it opened.
2. step(conn, name) replays as in Background and returns {"stepped": True, "new_trades": n}; returns {"stepped": False, "reason": ...} for an unknown fund or a fund whose strategy engine is not crypto_trend.
3. mark(conn, name, date=None) writes one crypto_fund_equity row per UTC date (INSERT OR REPLACE): realised = sum of net_usd of its trades; unrealised = sum over open positions of qty * last_close - deployed_usd (entry fees are already inside qty); equity = capital + realised + unrealised; returns the values.
4. funds(conn) returns the names of crypto_fund rows whose strategy engine is crypto_trend.
5. main(argv=None) with --open NAME --genome JSON [--capital], --step (all crypto_trend funds), --mark (all), --status (one line per fund: name, equity, closed trades, open positions). Connect via storage.connect(load_config()["database"]["market_data_path"]). Import runtime first.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else; do not change crypto_fund.py.
2. No network. Tests use sqlite3.connect(":memory:") with crypto_data.init and crypto_fund.init and synthetic bars; never open data/market_data.db.
3. Keep crypto_trend_fund.py under 240 lines and the test under 180 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_trend_fund.py exits 0.
2. The test checks: open_fund writes one row with interval 1d and engine crypto_trend; opening the same name again raises SystemExit; with started_ts set after all bars, step records no trades; with started_ts at an early bar on a synthetic series that rises then falls, step records at least one closed trade and re-running step adds none; no recorded trade has entry_ts before started_ts; mark writes equity = capital + realised + unrealised; funds() lists the fund and not a grid fund whose strategy JSON lacks engine.
3. At least 7 lines beginning with `  PASS`.
4. ./run_tests.sh reports ALL PASS.
