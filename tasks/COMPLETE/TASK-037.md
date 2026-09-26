# TASK-037

- component: reporting
- priority: high
- state: COMPLETE
- branch: ado/task-037
- created: 2026-09-26T05:10:00+00:00
- dependencies: none

## Objective
Create eod_report.py (Addendum D §16, Stage N10): the end-of-day report with the twelve sections ACCOUNT, P&L, TRADES, POSITIONS, STRATEGY PERFORMANCE, RANKING, REPLACEMENTS, RESEARCH, NEW CANDIDATES, FAILURES, SYSTEM HEALTH, NEXT ACTIONS, built read-only from existing tables, plus its regression test.

## Background
All data is in one SQLite database (connection passed in; row_factory sqlite3.Row). "Today" is a session date string YYYY-MM-DD passed as `day`; a row belongs to today when substr(at,1,10) = day (timestamps are ISO UTC). The trading mode reported is `mode` (default "LIVE"). Tables and columns: live_equity(at, session, equity, buying_power) — equity snapshots, `session` is the NY date; trader_runs(id, at, mode, pass, outcome, actions, positions, reconciled, diffs, cash, equity, unsettled, error); slot_trades(id, at, mode, slot_id, strategy_key, version, symbol, action 'OPEN'|'CLOSE', quantity, price, atr, stop_plan, reason, signal_id); slot_marks(id, at, mode, slot_id, symbol, price, high, stop, verdict); slot_assignments(id, at, slot_id, action 'ASSIGN'|'RELEASE', strategy_key, version, capital_usd, mode, reason, evidence); risk_events(id, at, signal_id, symbol, decision, reasons); system_events(id, at, kind, detail, severity); league_state(id, strategy_key, version, at, from_state, to_state, reason, actor); strategy_decisions(id, at, strategy_key, version, decision, from_state, to_state, classification, reason, evidence). Any table may be missing: a missing table makes its section say "no data" instead of raising. The ranking is supplied by an injected function rank_fn(conn) returning a list of dicts with keys name, strategy_key, score, backtest, forward, forward_trades, passes_gate, gate (already sorted best first). Open positions: the latest OPEN per slot_id in slot_trades for `mode` with no later CLOSE for that slot. Realized P&L today: for each CLOSE today, (close price - the price of that slot's preceding OPEN) x the CLOSE quantity, summed; this is GROSS (before costs). Net today = today's last live_equity.equity minus the last equity row of the previous session (NULL if none). Costs are stated as "not separated here (see accounting.py)". Report money with 2 decimals and returns in percent with 2 decimals. The owner reads it on a phone: short lines, no tables wider than 60 characters.

## Relevant files
- `eod_report.py`
- `tests/regression/test_eod_report.py`
## Requirements
1. build(conn, day, mode="LIVE", rank_fn=None) returns a dict with one key per section (lower snake case: account, pnl, trades, positions, strategy_performance, ranking, replacements, research, new_candidates, failures, system_health, next_actions), each a dict or list of plain values.
2. account: latest equity and buying power today, the latest trader_runs cash and unsettled for `mode`, and equity change vs the previous session. pnl: realized gross today, number of closed trades, open positions' unrealized gross using each slot's latest slot_marks price (NULL when no mark), and net equity change.
3. trades: today's slot_trades rows for `mode` (time, slot, action, symbol, quantity, price, reason). positions: open positions with symbol, quantity, entry price, latest mark, latest stop from slot_marks, unrealized % . replacements: today's slot_assignments rows. strategy_performance: for each currently assigned slot (latest ASSIGN without a later RELEASE per slot_id), the ranking row of its strategy_key (score, backtest, forward, forward_trades) or "not ranked".
4. ranking: the top 10 of rank_fn(conn) (empty when rank_fn is None). research: counts of strategy_decisions today grouped by decision. new_candidates: league_state rows today whose to_state is 'PAPER'. failures: today's risk_events whose decision is not 'APPROVED', today's system_events with severity 'critical' or 'warning', and today's trader_runs whose outcome is not 'ok' (each capped at 20 rows).
5. system_health: per mode the latest trader_runs row (at, outcome, reconciled) and whether it is older than 30 minutes relative to a `now` argument (default current UTC). next_actions: a list of plain-English strings derived by rules: "slot N is empty" for each unassigned slot of slots 1..5; "reconciliation failed in the last run" when the latest trader_runs for `mode` has reconciled = 0; "N risk rejection(s) today" when failures has any; "trader heartbeat stale" when system_health says stale; "none" when the list is otherwise empty.
6. render(report) returns plain text with the twelve section headings in the order ACCOUNT, P&L, TRADES, POSITIONS, STRATEGY PERFORMANCE, RANKING, REPLACEMENTS, RESEARCH, NEW CANDIDATES, FAILURES, SYSTEM HEALTH, NEXT ACTIONS, each line at most 60 characters.
7. main(argv=None) with --day (default today's UTC date), --mode (default LIVE), --send: prints the report; with --send calls notify.notify("Stockbot2000 end of day", text) inside try/except so a delivery failure never raises; uses ranking.rank(conn, load_config()) as rank_fn (from universe import load_config), opening the database read-only via sqlite3.connect("file:<path>?mode=ro", uri=True). Import runtime first.

## Constraints
1. Create ONLY eod_report.py and tests/regression/test_eod_report.py. Modify nothing else.
2. No network in tests, never open data/market_data.db in the test; use sqlite3.connect(":memory:") and create only the tables the test needs.
3. Keep eod_report.py under 280 lines and the test under 200 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_eod_report.py exits 0.
2. The test builds a day with: equity 90 the previous session and 92 today; an OPEN of 0.5 at 40 in slot 1 yesterday and a CLOSE of 0.5 at 44 today (realized gross 2.00); an OPEN in slot 2 today of 1.0 at 10 with a mark of 11 (unrealized +1.00, +10.00%); one rejected risk_event today; slots 1 and 2 assigned, slot 3 released. It checks the realized gross, the net change 2.00, the unrealized figures, one failure, "slot 3 is empty" in next_actions, that render contains all twelve headings in order, that no rendered line exceeds 60 characters, and that a missing table (e.g. no system_events) does not raise.
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
