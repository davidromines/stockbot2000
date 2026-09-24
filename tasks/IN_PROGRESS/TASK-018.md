# TASK-018

- component: tests
- priority: high
- state: IN_PROGRESS
- branch: ado/task-018
- created: 2026-09-24T02:00:00+00:00
- dependencies: none

## Objective
Create tests/regression/test_accounting.py covering accounting.py and the two paper_trading.py fixes of 2026-09-24.

## Background
accounting.py is the authoritative P&L (Addendum B §B18). Liquidation basis:
equity_restated = capital + gross - costs, costs = costs_realized + costs_open,
where costs_open is cost_model.round_trip(shares*mark, dollar_volume, shares)
for every open position. `_row(**kw)` computes costs_usd, net_usd,
equity_restated and the reconciliation: diff = equity_original - (capital +
gross - costs_realized); unexplained = diff - cash_drift_usd - mark_diff_usd;
recon_status is RECONCILED if |diff| <= TOLERANCE_USD, EXPLAINED if
|unexplained| <= TOLERANCE_USD, else ACCOUNTING_PROBLEM.

paper_trading.py gained `_stale_marks(conn, tickers, prices, today)`, which
returns the last real close at or before `today` from the `prices` table for
held tickers missing from the `prices` dict; and position inserts are now a
plain INSERT that skips a ticker already held (sqlite3.IntegrityError), so a
held position is never overwritten.

## Relevant files
- `tests/regression/test_accounting.py`
- `accounting.py`
- `paper_trading.py`
- `costs.py`
## Requirements
1. Import `runtime` first. Plain script, no pytest: a `check(name, cond, detail="")` helper printing `  PASS  name` or `  FAIL  name`, and `sys.exit(1)` if any failed. Put the repo root on sys.path as the other tests in tests/regression do.
2. Test `_row` identity: for capital 100, gross 5, costs_realized 1, costs_open 0.5, equity_original None: costs_usd == 1.5, net_usd == 3.5, equity_restated == 103.5, recon_status RECONCILED.
3. Test RECONCILED: equity_original == capital + gross - costs_realized (within 0.01) gives reconciled 1.
4. Test EXPLAINED: equity_original off by 3.0 with cash_drift_usd 2.0 and mark_diff_usd 1.0 gives recon_status EXPLAINED and unexplained_usd ~0.
5. Test ACCOUNTING_PROBLEM: equity_original off by 3.0 with no drift or mark diff gives ACCOUNTING_PROBLEM.
6. Test `paper_funds(conn, cm)` on an in-memory sqlite3 db (row_factory = sqlite3.Row) with hand-created tables: paper_runs(run_id,name,strategy,capital_usd,cash_usd,started_on,last_step_on,status,created_at,last_review,label,family), paper_equity(run_id,date,cash_usd,positions_usd,equity_usd,open_positions), paper_trades(run_id,ticker,entry_date,exit_date,entry_price,exit_price,shares,gross_pnl_usd,costs_usd,net_pnl_usd,pnl_pct,exit_reason), paper_positions(run_id,ticker,entry_date,entry_price,shares,stop_price,days_held), prices(ticker,date,open,high,low,close,volume,source), features(ticker,date,dollar_volume_20). One run, capital 100; one closed trade gross +2 costs 0.1 net 1.9; one open position 2 shares at entry 10 with a prices close of 12 on the mark date; cash 100 - 20 + (net of the closed trade's round trip, i.e. consistent with the ledger); paper_equity row with positions_usd 24 and equity cash+24. Use a costs.CostModel built from a minimal cfg dict — read costs.py CostModel.__init__ to supply the keys it needs, or use a stub object with round_trip returning 0.2. Assert gross_usd == 2 + 4, costs_open == 0.2 (stub), recon_status RECONCILED.
7. Same fixture but paper_equity positions_usd 20 (position marked at entry): assert mark_diff_usd ~ -4 and recon_status EXPLAINED.
8. Test `paper_trading._stale_marks`: with prices rows for X on 2026-09-18 (close 7) and 2026-09-21 (close 8), `_stale_marks(conn, ["X","Y"], {"Y": 5.0}, "2026-09-22")` returns {"X": 8.0}.
9. Test the no-overwrite rule by source inspection: the text of paper_trading.py contains no "INSERT OR REPLACE INTO paper_positions" inside the genome/model step (the conviction step may keep its own), i.e. assert the substring "except sqlite3.IntegrityError" is present.

## Constraints
1. Create ONLY `tests/regression/test_accounting.py`. Modify nothing else.
2. No network, no pytest, never open data/market_data.db.
3. If a function needs a table not listed, create it in the fixture.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_accounting.py exits 0.
2. At least 9 lines beginning with `  PASS`.
3. The file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
