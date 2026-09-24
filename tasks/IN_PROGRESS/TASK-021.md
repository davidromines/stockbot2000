# TASK-021

- component: reporting
- priority: high
- state: IN_PROGRESS
- branch: ado/task-021
- created: 2026-09-24T05:00:00+00:00
- dependencies: none

## Objective
Create factory_report.py: the daily Strategy Factory report (Phase 13 §36) and the global strategy scoreboard (§17), read-only over existing tables.

## Background
All data already exists in SQLite tables (open the database read-only with a `file:PATH?mode=ro` URI; PATH from universe.load_config()["database"]["market_data_path"]; a `--db` flag overrides it). Tables and columns:

strategy_meta(strategy_key, version, family, league, source, ...). Text columns may hold JSON-encoded strings, e.g. family may be the string "value_quality" or a JSON string with quotes; strip surrounding double quotes when present.
strategy_decisions(id, at, strategy_key, version, decision, from_state, to_state, classification, reason, evidence). `at` is an ISO timestamp.
strategy_metrics(id, strategy_key, version, as_of, phase, window, gross_usd, costs_usd, net_usd, return_pct, max_drawdown_pct, sharpe, sortino, win_rate, profit_factor, trades, sessions, turnover, benchmark_return_pct, excess_vs_null_usd, correlation, capacity_usd, survivorship_status, data_quality_status, detail, recorded_at). phase is one of backtest, validation, robustness, paper, live.
failure_log(id, at, strategy_key, version, family, stage, reason, parameters, window, regimes, data, suggests).
research_queue(id, source, ref, family, strategy_key, version, priority, status, reason, payload, created_at, updated_at). status is queued, taken, done or blocked.
league_standings(as_of, league, strategy_key, version, rank, tier, net_usd, gross_usd, costs_usd, sessions, closed_trades, max_drawdown_pct, family, detail). Use the latest as_of.
fund_accounting(as_of, fund_kind, fund_id, label, capital_usd, gross_usd, costs_realized, costs_open, costs_usd, net_usd, equity_original, equity_restated, open_positions, closed_trades, cost_basis, reconciled, recon_diff_usd, recon_status, cash_drift_usd, mark_diff_usd, unexplained_usd, note, accounting_version, computed_at). Use the latest computed_at per (fund_kind, fund_id).
league_state(id, strategy_key, version, at, from_state, to_state, reason, actor): the current state of a (strategy_key, version) is the to_state of its row with the largest id.
dataset_comparisons(id, at, primary_name, secondary_name, start, end, report) — may not exist yet; if missing, report "FINSABER comparison: not run yet".

Every money line shows GROSS, COSTS and NET side by side (Addendum B §B5). Benchmarks are informational (§B20). Never hide a missing figure: print an em dash and keep the row.

## Relevant files
- `factory_report.py`
- `universe.py`
## Requirements
1. Import runtime first. Functions take an open sqlite3 connection with row_factory = sqlite3.Row.
2. scoreboard(conn) -> list[dict]`: one row per strategy with a forward record (every (strategy_key, version) in the latest league_standings) PLUS every strategy whose current state is VALIDATED or PROMISING. Fields: strategy, league, status (current state), classification (latest non-null classification from strategy_decisions), gross_usd, costs_usd, net_usd, return_pct (net / 100 * 100 when a fund_accounting capital exists, else from the latest metrics row), max_drawdown_pct, sharpe, sortino, win_rate, profit_factor, trades, turnover, paper_days (sessions from league_standings), benchmark (latest excess_vs_null_usd, labelled informational), correlation, data_quality (latest data_quality_status or "—"), survivorship (latest survivorship_status or "UNKNOWN"), confidence ("established" if tier ESTABLISHED, "eligible" if ELIGIBLE, "insufficient" otherwise). Forward-record rows take money from league_standings; backtest-only rows take money from their latest validation metrics and say evidence "backtest". Sort by evidence (forward first), then net_usd descending. Never rank by raw return alone: include the tier column in the render.
3. daily_report(conn, days=1) -> dict` with sections exactly: discovery {new_strategies, new_variants (decisions/metrics whose strategy_meta.source == 'recycle'), new_research_sources (research_queue rows created in the window with source 'library' or 'human')}, backtesting {completed (distinct strategies with a backtest metrics row in the window), promising (to_state PROMISING or VALIDATED in the window), failed (to_state REJECTED in the window, with stage and reason from failure_log)}, paper {new_enrolments (to_state PAPER), leagues (per league: count, best net, worst net), promotions (to_state QUALIFIED or LIVE_CANDIDATE), demotions (to_state DEMOTED)}, live {candidates (current state LIVE_CANDIDATE or LIVE), note "slot engine not yet built" if there is no table named slots}, accounting {totals by fund_kind and ALL: gross, costs, net; count of recon_status values}, data {finsaber comparison summary or not-run note; data_problem decisions count}, research {families explored (distinct family with any BACKTESTED or later decision), families never tested, queue counts by source/status, diversity (number of distinct families backtested in the window)}.
4. render(scoreboard_rows, report) -> str`: plain text for a terminal and for Telegram, the scoreboard as a fixed-width table with columns: strategy (28 chars), league, status, tier, gross, costs, net, trades, days, maxDD%, survivorship. Money with sign and 2 decimals.
5. CLI: `python factory_report.py [--days N] [--out data/factory_report.txt] [--json data/factory_report.json] [--db PATH]` writes both files and prints the text.
6. Robust to empty tables: every section renders with zeros or "none".

## Constraints
1. Create ONLY `factory_report.py`. Modify nothing else. Keep the WHOLE file under 300 lines: a short module docstring, one-line function docstrings, no comments restating code. The previous attempt was truncated at the output limit.
2. Read-only: no INSERT, UPDATE, DELETE or CREATE statements anywhere in the file.
3. No network, no new dependency.

## Acceptance criteria
1. grep -cE "INSERT|UPDATE |DELETE|CREATE TABLE" factory_report.py` prints 0.
2. PYTHONPATH=. venv/bin/python -c "import sqlite3,factory_report as f; c=sqlite3.connect(':memory:'); c.row_factory=sqlite3.Row; [c.execute(s) for s in ('CREATE TABLE strategy_meta(strategy_key,version,family,league,source)','CREATE TABLE strategy_decisions(id INTEGER PRIMARY KEY,at,strategy_key,version,decision,from_state,to_state,classification,reason,evidence)','CREATE TABLE strategy_metrics(id INTEGER PRIMARY KEY,strategy_key,version,as_of,phase,window,gross_usd,costs_usd,net_usd,return_pct,max_drawdown_pct,sharpe,sortino,win_rate,profit_factor,trades,sessions,turnover,benchmark_return_pct,excess_vs_null_usd,correlation,capacity_usd,survivorship_status,data_quality_status,detail,recorded_at)','CREATE TABLE failure_log(id INTEGER PRIMARY KEY,at,strategy_key,version,family,stage,reason,parameters,window,regimes,data,suggests)','CREATE TABLE research_queue(id INTEGER PRIMARY KEY,source,ref,family,strategy_key,version,priority,status,reason,payload,created_at,updated_at)','CREATE TABLE league_standings(as_of,league,strategy_key,version,rank,tier,net_usd,gross_usd,costs_usd,sessions,closed_trades,max_drawdown_pct,family,detail)','CREATE TABLE fund_accounting(as_of,fund_kind,fund_id,label,capital_usd,gross_usd,costs_realized,costs_open,costs_usd,net_usd,equity_original,equity_restated,open_positions,closed_trades,cost_basis,reconciled,recon_diff_usd,recon_status,cash_drift_usd,mark_diff_usd,unexplained_usd,note,accounting_version,computed_at)','CREATE TABLE league_state(id INTEGER PRIMARY KEY,strategy_key,version,at,from_state,to_state,reason,actor)')]; c.execute(\"INSERT INTO league_standings VALUES('2026-09-22','momentum','k1',1,1,'INSUFFICIENT_SAMPLE',5.0,5.5,0.5,8,10,2.0,'fam','{}')\"); c.execute(\"INSERT INTO league_state(strategy_key,version,at,to_state,reason) VALUES('k1',1,'2026-09-24T00:00:00','PAPER','x')\"); s=f.scoreboard(c); r=f.daily_report(c); t=f.render(s,r); assert len(s)==1 and s[0]['net_usd']==5.0 and s[0]['status']=='PAPER' and 'GROSS' in t.upper() and 'NET' in t.upper(); assert set(r)=={'discovery','backtesting','paper','live','accounting','data','research'}; print('ok')"` prints ok
3. ./run_tests.sh reports ALL PASS.
