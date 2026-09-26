# TASK-038

- component: research
- priority: medium
- state: TODO
- branch: ado/task-038
- created: 2026-09-26T06:00:00+00:00
- dependencies: none

## Objective
Create strategy_health.py (Addendum D §12, Stage N5): an operational HEALTHY / WATCH / DEGRADING / FAILED state per strategy from its forward paper record against its own backtest, recorded append-only on change, plus its regression test.

## Background
Paper funds: paper_trades(run_id, ticker, entry_date, exit_date, entry_price, exit_price, shares, gross_pnl_usd, costs_usd, net_pnl_usd, pnl_pct, exit_reason) where pnl_pct is percent (1.5 = +1.5%); paper_equity(run_id, date, equity_usd, ...). A strategy key "paper:<run_id>" owns run_id directly; a factory key "fx_..." owns the run_id in factory_paper_link(strategy_key, version, run_id). Other keys (pair:, value:, crypto:) are not measured here. The caller passes rank rows (from ranking.rank) as a list of dicts with strategy_key, version, name, league, backtest (net return per trade as a FRACTION, e.g. 0.004 = 0.4%, or None). Per-trade NET return of a paper trade = net_pnl_usd / (shares * entry_price). Settings come from cfg.get("strategy_health") merged over DEFAULTS = {"window": 20, "min_watch": 5, "min_degrading": 10, "min_failed": 20, "degrading_fraction": 0.5, "dd_watch": 0.5, "dd_degrading": 0.75, "freq_drop": 0.5}; the league drawdown limit is cfg["leagues"][league]["max_drawdown_pct"] (percent), default 15 when absent. RULES, first match wins, n = closed paper trades, roll = mean per-trade net of the last `window` closed trades by exit_date, allt = mean of all, bt = backtest, dd = max drawdown % of paper_equity (peak to trough), lim = league limit: FAILED if (n >= min_failed and roll < 0 and allt < 0) or dd >= lim. DEGRADING if (n >= min_degrading and bt is not None and roll < degrading_fraction * bt) or dd >= dd_degrading * lim. WATCH if (n >= min_watch and bt is not None and roll < bt) or dd >= dd_watch * lim or (n >= 2 * window and the number of trades whose exit_date is in the last 60 calendar days of the record is less than freq_drop times the number in the 60 days before that). Otherwise HEALTHY, with reason "insufficient evidence (n < min_watch)" when n < min_watch, else "within expectations". When bt is None the backtest comparisons are skipped. The reason string names the rule that fired with its numbers.

## Relevant files
- `strategy_health.py`
- `tests/regression/test_strategy_health.py`
## Requirements
1. init(conn) creates strategy_health(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL, state TEXT NOT NULL, reason TEXT NOT NULL, metrics TEXT) — append-only, never UPDATE or DELETE.
2. run_id_for(conn, key, version) returns the paper run id or None, per the Background.
3. metrics(conn, run_id) returns {"n", "roll", "allt", "win_rate_roll", "dd", "recent_60d", "prior_60d"} (None values when not computable).
4. classify(m, bt, lim, s) returns (state, reason) per the RULES.
5. evaluate(conn, cfg, rank_rows, now=None) computes every row with a paper run and returns a list of {strategy_key, version, name, state, reason, metrics}; rows without a paper run get state "HEALTHY" with reason "not measured (no paper trades table for this fund kind)".
6. record(conn, results, now=None) inserts a strategy_health row only when a strategy's state differs from its latest recorded state (or it has none), commits, and returns how many rows it wrote.
7. latest(conn) returns {(strategy_key, version): (state, reason, at)} from the newest row per strategy.
8. main(argv=None) with --run (evaluate with ranking.rank(conn, cfg) and record) and --report (print one line per strategy: state, name, n, roll %, bt %, dd %). Import runtime first; connect with sqlite3.connect(load_config()["database"]["market_data_path"]) (from universe import load_config), row_factory sqlite3.Row.

## Constraints
1. Create ONLY strategy_health.py and tests/regression/test_strategy_health.py. Modify nothing else.
2. No network; the test uses sqlite3.connect(":memory:") with only the tables it needs and never opens data/market_data.db.
3. Keep strategy_health.py under 240 lines and the test under 200 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_strategy_health.py exits 0.
2. The test checks classify directly: n 3 -> HEALTHY with "insufficient evidence"; n 8 with roll below bt -> WATCH; n 12 with roll below half of bt -> DEGRADING; n 25 with roll and allt negative -> FAILED; dd at the league limit -> FAILED regardless of n; bt None skips backtest comparisons.
3. The test checks metrics on a synthetic paper run (per-trade net from net_pnl_usd / (shares * entry_price), max drawdown from paper_equity), run_id_for for a paper: key and a factory key via factory_paper_link, and that record writes once and then writes nothing when the state is unchanged, and writes again when it changes.
4. At least 12 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
