# TASK-024

- component: tests
- priority: high
- state: TODO
- branch: ado/task-024
- created: 2026-09-24T06:59:36+00:00
- dependencies: none

## Objective
Create tests/regression/test_leagues.py covering leagues.py (Phase 13 H8: tiers and standings from accounting).

## Background
leagues.tier(ev, lc) is pure: INSUFFICIENT_SAMPLE with no forward record or net None or too few sessions/closed trades; NOT_ELIGIBLE when net <= 0 or drawdown over the limit; else ESTABLISHED at >= established_sessions, otherwise ELIGIBLE. evidence() reads the latest fund_accounting row (create it with accounting.init(conn)) plus paper_equity for sessions and max drawdown. fund_ref maps paper:/pair:/value:/crypto: prefixes and falls back to factory_paper_link. family_of strips a ' · ' suffix and a trailing single-letter sibling from legacy names. lc example: {"min_forward_sessions": 20, "min_closed_trades": 10, "established_sessions": 60, "max_drawdown_pct": 15}.

## Relevant files
- `tests/regression/test_leagues.py`
- `leagues.py`
- `league.py`
- `accounting.py`
- `strategy_objects.py`
- `paper_trading.py`
## Requirements
1. tier returns INSUFFICIENT_SAMPLE for {has_forward_record: False}.
2. tier returns INSUFFICIENT_SAMPLE when sessions 19 with the lc above.
3. tier returns NOT_ELIGIBLE for sessions 30, closed_trades 12, net_usd -1.
4. tier returns NOT_ELIGIBLE for positive net with max_drawdown_pct 16.
5. tier returns ELIGIBLE for sessions 30, closed_trades 12, net 5, drawdown 3; ESTABLISHED for sessions 60.
6. fund_ref(conn, "paper:abc") == ("paper", "abc"); fund_ref for an unknown fx_ key with no link row is None; with a factory_paper_link row it returns ("paper", run_id).
7. _max_dd over paper_equity equities 100, 110, 99 returns 10.0 (within 0.01).
8. evidence() for a paper:RUN key with a fund_accounting row returns that row's net_usd and sessions equal to the paper_equity row count.
9. family_of for a legacy league_strategies name "Crash Buyer 20d b · stop 2.5" (insert into league_strategies via league.register with that name) returns crash_buyer_20d.

## Constraints
1. Create ONLY the test file this task names. Modify nothing else.
2. No network, no pytest, never open data/market_data.db. Use sqlite3.connect(":memory:") with conn.row_factory = sqlite3.Row.
3. Keep the file under 280 lines. If a function needs a table not created by an init() helper, create it in the fixture.
4. Import `runtime` first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import the modules under test.
5. Plain script, no pytest: a `check(name, cond, detail="")` helper printing `  PASS  name` or `  FAIL  name`, then `sys.exit(1)` if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_leagues.py exits 0.
2. At least 9 lines beginning with `  PASS`.
3. The file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
