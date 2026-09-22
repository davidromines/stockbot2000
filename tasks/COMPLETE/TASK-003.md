# TASK-003

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-003
- created: 2026-09-22T22:12:50+00:00
- dependencies: none

## Objective
Create tests/regression/test_value_fund.py, a regression test for the Stockbot Value Fund in value_fund.py, following the style of the existing files in tests/regression/.

## Background
Phase 9 item 30. `value_fund.py` runs the Stockbot Value Fund: a paper-only,
long-horizon portfolio kept deliberately separate from the tactical strategy
league, because the two answer different questions and a shared scoreboard
would rank a five-year thesis on eleven weeks of Sharpe.

Four behaviours in that module are load-bearing and must not regress. Each
exists because the obvious alternative is wrong in a way that produces
plausible-looking output:

- **Hysteresis.** Buy inside the top decile of the industry
  (`BUY_PERCENTILE`), sell only on falling out of the top 40%
  (`SELL_PERCENTILE`). A single threshold churns on noise, and turnover is the
  one cost a long-horizon fund cannot argue away.
- **No stop loss.** A stop converts a fundamental thesis into a price rule. A
  value position down 30% is either a broken thesis or an improved
  opportunity, and a stop cannot tell them apart — it reliably sells the
  second case.
- **A frozen thesis.** The score, dimensions and reasoning are stored as JSON
  on the position at entry and never updated. A thesis that can be edited
  afterwards is not a thesis.
- **Refusing a partial mark.** If any held position cannot be priced on a
  date, `mark()` records NOTHING rather than carrying that position at cost.
  Marking the rest would report a fund that never loses on the names it can no
  longer see.

## Relevant files
- `tests/regression/test_value_fund.py`
- `value_fund.py`
## Requirements
1. Import `runtime` as the very first import, before pandas or numpy.
2. Build an in-memory sqlite3 database with `conn.row_factory = sqlite3.Row`.
3. Follow the existing style in `tests/regression/`: a module docstring saying
4. Test `open_fund`: it creates a row with status 'open', cash equal to
5. Test that calling `open_fund` a SECOND time raises SystemExit. A forward
6. Test `_price` returns the most recent close at or before the as-of date,
7. Test `mark` refuses a partial book: insert two positions, give only one of
8. Test `mark` succeeds when every position is priced: assert a row IS written
9. Test that the constants express hysteresis: assert
10. Test that the module contains NO stop-loss logic: read the module source
11. Test that `value_fund.py` never writes to the tactical league's tables:
12. Test that the module cannot reach the broker: assert the source contains
13. Test the frozen thesis: insert a position whose `thesis` column holds a
14. Test `status` on a fund with no positions: `exists` is True, `positions
15. Test `render` on that status: the returned string contains "NOT YET

## Constraints
1. Create ONLY `tests/regression/test_value_fund.py`. Do not modify
2. Do not add any dependency. Use only the standard library plus what
3. The test must not require network access and must not open
4. Do not use pytest. These are plain scripts run directly, matching the rest

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_value_fund.py` exits 0
2. It prints at least 15 lines beginning with `  PASS`.
3. ./run_tests.sh` still reports ALL PASS, with the file count increased by
4. git status --short` shows exactly one added file.
