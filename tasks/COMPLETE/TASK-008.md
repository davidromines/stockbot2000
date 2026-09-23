# TASK-008

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-008
- created: 2026-09-22T23:59:36+00:00
- dependencies: none

## Objective
Create tests/regression/test_promotion_policy.py, a regression test for promotion_policy.py, following the style of the existing files in tests/regression/.

## Background
Phase 10 item 31. `promotion_policy.py` decides whether a strategy may receive
real money. It asks two SEPARATE questions and refuses unless both pass:

    readiness    does the machinery for safe promotion exist at all?
    eligibility  does this particular strategy qualify?

Conflating them is how a project talks itself into a live trade: a strategy
that looks excellent is an argument for promoting it, and without an
independent readiness gate that argument has nothing standing against it.

The module must never promote anything. Phase 10 says the strategy layer must
never directly place orders, and this project's standing constraint is
stronger — the loop is system generates, human places, system reconciles. A
PERMITTED decision is a recommendation, never an instruction.

One detail that matters. `readiness()` distinguishes evidence strength:
"verified" means the capability was exercised and the result observed,
"present" means only that the code exists. The first version of the function
reported 15 of 15 satisfied on a system that has never placed a trade, purely
because files existed. A path that has never run is an assumption about the
day it first runs, which is the day it must not fail.

## Relevant files
- `tests/regression/test_promotion_policy.py`
- `promotion_policy.py`
## Requirements
1. Import `runtime` as the very first import, before pandas or numpy.
2. Build an in-memory sqlite3 database with `conn.row_factory = sqlite3.Row`.
3. Follow the existing style in `tests/regression/`: a module docstring naming
4. Test that `PREREQUISITES` contains exactly 15 entries, and that every name
5. Test that `evaluate()` records a row in `promotion_decisions` for a
6. Test that `evaluate()` on an unknown strategy key still records a decision
7. Test that `history()` returns the recorded decisions, and that calling
8. Test the readiness/eligibility independence: construct a fake readiness
9. Test that `readiness()` returns, for every check, a dict containing the
10. Test that `readiness()` reports `n_verified` no greater than `n_total`.
11. Test that the module cannot reach the broker: read the source with
12. Test that `promotion_policy.py` issues no SQL against broker or order

## Constraints
1. Create ONLY `tests/regression/test_promotion_policy.py`. Do not modify
2. Do not add a dependency. Standard library plus what the module imports.
3. No network access, and do not open the real database.
4. Do not use pytest. Plain script, matching the rest of `tests/regression/`.
5. readiness()` reads `config/risk.yaml` and `load_config()` from the real

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_promotion_policy.py
2. It prints at least 12 lines beginning with `  PASS`.
3. ./run_tests.sh` reports ALL PASS with 32 files.
4. git status --short` shows exactly one added file.
