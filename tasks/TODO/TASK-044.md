# TASK-044

- component: reporting
- priority: medium
- state: TODO
- branch: ado/task-044
- created: 2026-09-26T08:30:00+00:00
- dependencies: none

## Objective
Create live_feedback.py (Addendum D §11, Stage N6): per live slot trade, compare what was expected with what happened — the signal-time price vs the fill, slippage, submit-to-fill delay, holding time and exit reason — and aggregate by strategy; plus its regression test. Read-only analysis; it changes no strategy.

## Background
Tables: slot_trades(id, at, mode, slot_id, strategy_key, version, symbol, action 'OPEN'|'CLOSE', quantity, price, atr, stop_plan, reason, signal_id); orders(client_order_id, signal_id, created_at, session, symbol, side, asset_type, notional, quantity, state, broker_order_id, filled_quantity, avg_fill_price, mode, note); signals(signal_id, timestamp, session, symbol, asset_type, action, quantity, notional_value, confidence, strategy, reason, ...) — only the columns named here are used; slot_marks(id, at, mode, slot_id, symbol, price, high, stop, verdict) — the quote the trader saw. For each slot_trades row of `mode`: the expected price is the latest slot_marks.price for that symbol at or before the order's created_at (None if none); fill = slot_trades.price; slippage_bps = (fill / expected - 1) * 10000 for an OPEN (paying more is positive = bad) and (expected / fill - 1) * 10000 for a CLOSE (receiving less is positive = bad); delay_s = seconds from orders.created_at to slot_trades.at (joined by signal_id; None if no order). A round trip pairs a CLOSE with the preceding OPEN of the same slot_id and strategy_key: gross return = close price / open price - 1, holding_days = calendar days between them, exit_reason = the CLOSE row's reason. Timestamps are ISO UTC strings.

## Relevant files
- `live_feedback.py`
- `tests/regression/test_live_feedback.py`
## Requirements
1. trades(conn, mode="LIVE") returns one dict per slot_trades row: id, at, slot_id, strategy_key, symbol, action, quantity, fill, expected, slippage_bps, delay_s.
2. round_trips(conn, mode="LIVE") returns one dict per completed OPEN->CLOSE pair: strategy_key, symbol, opened, closed, open_price, close_price, gross_return, holding_days, exit_reason.
3. by_strategy(conn, mode="LIVE") returns, per strategy_key: n_fills, mean_slippage_bps (over fills with an expected price), mean_delay_s, n_round_trips, mean_gross_return, win_rate, exit_reasons ({reason: count}).
4. render(conn, mode="LIVE") returns a plain-text report (lines at most 72 characters): one block per strategy, then the ten worst slippages.
5. main(argv=None) with --mode (default LIVE) printing render; open the database read-only via sqlite3.connect("file:<path>?mode=ro", uri=True) using load_config()["database"]["market_data_path"] (from universe import load_config). Import runtime first.

## Constraints
1. Create ONLY live_feedback.py and tests/regression/test_live_feedback.py. Modify nothing else.
2. No network; the test uses sqlite3.connect(":memory:") with only the tables it needs; never opens data/market_data.db.
3. Keep live_feedback.py under 200 lines and the test under 160 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_live_feedback.py exits 0.
2. The test checks: an OPEN filled at 101 with a mark of 100 has slippage +100.00 bps; a CLOSE filled at 99 with a mark of 100 has slippage +101.01 bps (expected/fill - 1); delay_s from order created_at to fill; a round trip OPEN 100 -> CLOSE 110 has gross_return 0.10 and the CLOSE reason as exit_reason; by_strategy averages slippage only over fills with an expected price; a fill with no mark has expected None; render lines are at most 72 characters.
3. At least 8 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
