# TASK-064

- component: paper_trading
- priority: low
- state: COMPLETE
- branch: ado/task-064
- created: 2026-10-03T00:00:00+00:00
- dependencies: none

## Objective
Add `open_fund`, `step_fund`, and `signal` functions to `kalman_pair.py` for the EWA/EWC long-only paper fund, and wire `--step` into `daily.sh [5]`.

## Background
`kalman_pair.py` (Stage AA) implements Kalman-filter pair mean-reversion. It has two modes: `"spread"` (long/short, not tradeable) and `"long_leg"` (buy whichever leg the filter calls cheap — tradeable). The backtest fails after costs, but the strategy must be paper-tracked so forward evidence accrues. Every strategy is paper-tracked regardless of backtest outcome.

`paper_runs` table schema (relevant columns): `id INTEGER PK`, `label TEXT UNIQUE`, `family TEXT`, `strategy TEXT (JSON)`, `capital_real REAL`, `capital_usd REAL`, `state TEXT`. `paper_trading.open_fund(conn, label, family, strategy_json, capital)` may or may not exist — use a direct INSERT OR IGNORE into `paper_runs` instead to be safe.

`paper_trading.step_funds(conn, cfg, [fund_ids])` steps paper funds. Alternatively, `paper_trading._step_one(conn, cfg, run_id, signals)` steps a single fund. The exact API can be inferred from `paper_trading.py` but for safety, implement `step_fund` by querying `paper_runs` for the fund's id and then calling `paper_trading.step_funds(conn, cfg, [run_id])` if that function exists, or do a minimal paper step inline.

For simplicity and safety: `step_fund(conn, cfg)` should call `kalman_pair.py`'s own `signal()` function to get today's signal, then call `paper_trading.step_fund_by_label(conn, cfg, "kalman_ewa_ewc")` if that function exists, else query the run id from `paper_runs` and call whatever step API is available.

`daily.sh` stage `[5]` is the paper step stage. Add `$PY kalman_pair.py --step` to it.

## Relevant files
- `kalman_pair.py`
- `daily.sh`
- `tests/regression/test_kalman_pair.py`
## Requirements
1. signal(conn, a, b, params=None) -> dict | None`: loads close prices for a and b from `prices` from WARMUP to today via `load()`, runs `kalman()`, returns `{"ticker": leg, "side": 1, "entry_z": params.get("entry_z", 1.0)}` when e < -entry_z*sqrt(q) (buy leg b) or e > entry_z*sqrt(q) (buy leg a), else `None`. Default params: `{"mode": "long_leg", "delta": 0.0001, "ve": 0.001, "entry_z": 1.0}`.
2. open_fund(conn)`: INSERT OR IGNORE into `paper_runs (label, family, strategy, capital_real, capital_usd, state)` with `label='kalman_ewa_ewc'`, `family='kalman_pair'`, `strategy=json.dumps({"pair": "EWA/EWC", "mode": "long_leg"})`, `capital_real=100.0`, `capital_usd=100.0`, `state='active'`. Idempotent (INSERT OR IGNORE).
3. step_fund(conn, cfg)`: calls `open_fund(conn)` to ensure the fund exists, then calls `paper_trading.step_funds(conn, cfg)` which steps all active funds including ours. (This is the simplest safe implementation — it re-uses the existing step machinery.)
4. Add `--open` CLI flag: calls `open_fund(conn)` with the real DB and exits 0.
5. Add `--step` CLI flag: calls `step_fund(conn, cfg)` with the real DB and exits 0.
6. In `daily.sh` stage `[5]` (the paper step stage, currently `run "[5/10] Paper step" ...`), add `run "[5b/10] Kalman pair step" $PY kalman_pair.py --step` immediately after the existing stage [5] line.
7. tests/regression/test_kalman_pair.py`: add two tests — `open_fund` idempotency (run twice, check paper_runs has exactly one row with label='kalman_ewa_ewc'); `step_fund` with a minimal in-memory DB completes without error (does not need to check paper equity rows since that depends on real step machinery).

## Constraints
1. Do not change the existing `backtest()`, `main()` argument parsing for `--backtest`/`--all`, or any existing functions.
2. Do not change `paper_trading.py`.
3. Create ONLY changes to `kalman_pair.py`, `daily.sh`, and `tests/regression/test_kalman_pair.py`. Modify nothing else.
4. tests/regression/test_kalman_pair.py` must already exist (TASK-057 created it) — add new tests to it, do not replace existing tests.

## Acceptance criteria
1. tests/regression/test_kalman_pair.py` exits 0 (all existing + new tests pass).
2. grep "kalman_pair.*--step" daily.sh` returns one line.
3. ./run_tests.sh` passes.
