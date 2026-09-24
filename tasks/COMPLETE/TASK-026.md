# TASK-026

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-026
- created: 2026-09-24T06:59:36+00:00
- dependencies: none

## Objective
Create tests/regression/test_factory_pipeline.py covering factory_pipeline.py (Phase 13 H11-H13: enrolment, forward promotion, family limit).

## Background
Backtests only admit; forward evidence qualifies. evaluate_forward(conn, cfg) moves PAPER strategies whose league tier is ELIGIBLE/ESTABLISHED to QUALIFIED and QUALIFIED/LIVE_CANDIDATE ones that fall to NOT_ELIGIBLE to DEMOTED. promote_candidates moves at most ONE strategy per concentration family (leagues.family_of) from QUALIFIED to LIVE_CANDIDATE, the highest net_usd. enroll() starts a paper run via paper_trading.start (needs a prices table with at least one row for MAX(date)) and is idempotent through factory_paper_link. To put a strategy in PAPER without running backtests, walk it through the allowed chain with strategy_objects.decide: SPECIFIED, BACKTESTED, VALIDATED, PROMISING, PAPER (league.ALLOWED). Evidence comes from fund_accounting (accounting.init) keyed by the paper run linked in factory_paper_link, and paper_equity row count for sessions. cfg needs risk: {position_size_usd: 20, max_open_positions: 5} plus leagues: {momentum: {min_forward_sessions: 2, min_closed_trades: 1, established_sessions: 60, max_drawdown_pct: 15}, tactical: same} and league_families: {}.

## Relevant files
- `tests/regression/test_factory_pipeline.py`
- `factory_pipeline.py`
- `leagues.py`
- `strategy_objects.py`
- `league.py`
- `accounting.py`
- `paper_trading.py`
- `strategy_factory.py`
## Requirements
1. enroll returns a run_id, writes one factory_paper_link row, and moves the strategy to PAPER.
2. enroll called again returns the same run_id and writes no second link row.
3. A PAPER strategy whose fund has 3 paper_equity rows and a fund_accounting row with net_usd 5 and closed_trades 2 becomes QUALIFIED after evaluate_forward.
4. A PAPER strategy with net_usd -2 stays PAPER.
5. Two QUALIFIED strategies in the SAME family: promote_candidates promotes only the one with higher net_usd to LIVE_CANDIDATE.
6. A LIVE_CANDIDATE whose accounting falls to net_usd -1 becomes DEMOTED after evaluate_forward.
7. live_candidates returns only LIVE_CANDIDATE or LIVE strategies.
8. No function under test imports broker or execution: assert the strings import broker and import execution do not appear in factory_pipeline.py.

## Constraints
1. Create ONLY the test file this task names. Modify nothing else.
2. No network, no pytest, never open data/market_data.db. Use sqlite3.connect(":memory:") with conn.row_factory = sqlite3.Row.
3. Keep the file under 280 lines. If a function needs a table not created by an init() helper, create it in the fixture.
4. Import `runtime` first, then put the repo root on sys.path as tests/regression/test_accounting.py does, then import the modules under test.
5. Plain script, no pytest: a `check(name, cond, detail="")` helper printing `  PASS  name` or `  FAIL  name`, then `sys.exit(1)` if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_factory_pipeline.py exits 0.
2. At least 8 lines beginning with `  PASS`.
3. The file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
