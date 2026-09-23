# TASK-009

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-009
- created: 2026-09-23T05:39:51+00:00
- dependencies: none

## Objective
Create tests/regression/test_allocation_roster.py covering allocation.py and roster.py, following the style of the existing files in tests/regression/.

## Background
Phase 10 items 32 and 33. `allocation.py` sizes live roster slots against the
account cap; `roster.py` computes who joins and who leaves.

Three properties must not regress, each because the alternative fails
silently rather than loudly:

- **The allocator never invents capital.** The sum of allocations may fall
  below the cap but must never exceed it, and each slot is additionally
  capped at `risk.position_size_usd`. An over-allocation would propose orders
  the account cannot fund, and the rejection would arrive from the broker
  rather than from us.
- **Demotion is easier than promotion.** A strategy leaves the roster on any
  single failure; joining requires every gate. Symmetric thresholds produce a
  roster that churns, and churn is the one cost a small account cannot pay.
- **Promotion stops at LIVE_CANDIDATE.** `roster.apply()` must never
  transition a strategy directly to LIVE. That intermediate state is where a
  human decides, and skipping it makes promotion automatic, which Phase 10
  forbids outright.

## Relevant files
- `tests/regression/test_allocation_roster.py`
- `allocation.py`
- `roster.py`
## Requirements
1. Import `runtime` as the very first import, before pandas or numpy.
2. Use an in-memory sqlite3 database with `conn.row_factory = sqlite3.Row`.
3. Follow the existing style in `tests/regression/`: module docstring naming
4. Test `allocation.capital(cfg)` returns `position_size_usd *
5. Test each scheme in `allocation.SCHEMES` with a synthetic list of roster
6. Test `_score` falls back to equal weighting when every score is zero or
7. Test `_risk_parity` gives a LARGER share to the strategy with LOWER
8. Test that `allocation.record()` writes one row per allocation and that
9. Test `allocation.allocate` raises SystemExit on an unknown scheme name.
10. Test `roster.current(conn)` returns only strategies whose league state is
11. Test that `roster.apply` never transitions a strategy to `league.LIVE`:
12. Test that `roster.history()` returns rows newest first after two
13. Test that neither module imports the broker: assert

## Constraints
1. Create ONLY `tests/regression/test_allocation_roster.py`. Modify nothing
2. No new dependency. Standard library plus what the modules import.
3. No network, and do not open the real database.
4. Do not use pytest.
5. roster.plan()` and `roster.apply()` call into eligibility and scoreboard,

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_allocation_roster.py
2. It prints at least 14 lines beginning with `  PASS`.
3. ./run_tests.sh` reports ALL PASS with 33 files.
4. git status --short` shows exactly one added file.
