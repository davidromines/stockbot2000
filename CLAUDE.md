# StockPicker2000

Automated swing-trading system: scores US equities on technical indicators, sizes and
stops positions by ATR, and evolves its own trading strategies against 20 years of
market history before any real capital is committed.

Formerly named `betbot9000`, then `trend-scanner`. Do not confuse with the separate
`betbot` project (college football betting) that lives on the same host.

---

## Current state — READ THIS FIRST

The project is **mid-smoke-test**. The pipeline has never yet run end to end.
Do not start new feature work until `data_pull.py -> features.py -> score.py`
completes cleanly on the small fallback universe.

Known-good so far:
- `universe.py` runs (falls back to 18 hardcoded tickers — see gotchas)

Not yet verified:
- `data_pull.py`, `features.py`, `score.py`, `train_model.py`, `back_test.py`

Immediate next steps:
1. Confirm the rewritten `features.py` (no `pandas_ta`) is actually deployed.
2. `mkdir -p data/raw models` if missing.
3. Run each stage in order, fix what breaks.

---

## Environment gotchas — these have already cost time

- **Python 3.14 is too new for parts of this stack.** `pandas_ta` pins
  `numba==0.61.2`, which refuses to build on 3.14. `pandas_ta` has been **removed
  entirely**; all indicators are hand-rolled in plain pandas/numpy inside
  `features.py`. Do not reintroduce `pandas_ta`. If the project moves to a fresh
  VM, install **Python 3.12**, not 3.14.
- **Dependencies missing from `requirements.txt`** were found during setup:
  `pyyaml`, `yfinance`, `pyarrow`. They are installed but verify they are pinned
  in `requirements.txt`.
- **Wikipedia S&P 500 scrape returns HTTP 403.** `universe.py` silently falls back
  to 18 hardcoded tickers. Planned replacement: the NASDAQ Trader symbol directory
  (`nasdaqlisted.txt` / `otherlisted.txt`), which is free and does not require scraping.
- **yfinance does not serve delisted tickers.** This is a real correctness problem
  for backtesting — see the survivorship-bias item under Open Decisions.
- Long backfills must be run under `nohup`/`tmux`/`screen`. SSH sessions to this
  box have dropped mid-run before.

---

## Architecture

Pipeline stages, in execution order:

| File | Role |
|---|---|
| `universe.py` | Builds the ticker list. Also owns `load_config()`, imported everywhere. |
| `data_pull.py` | Fetches OHLCV history via yfinance. |
| `features.py` | Computes ~25 technical indicators per (ticker, date). No third-party TA lib. |
| `train_model.py` | Trains the XGBoost classifier. Owns `FEATURE_COLS`. |
| `score.py` | Ranks the universe, writes the scoresheet. |
| `stop_loss.py` | ATR-based stop levels (configurable to fixed-pct). |
| `position_tracking.py` | SQLite trade ledger — entries, exits, exit reasons. |
| `back_test.py` | Walk-forward simulation over the scoring strategy. |
| `check_exists.py` | Evaluates open positions against stop/exit rules. |
| `llm_report.py` | Generates the daily narrative report via local Ollama. |
| `run_pipeline.sh` | Orchestrates the above. |

Config lives in `config.yaml`. Nothing should hardcode paths, thresholds, or
model parameters — read them from config.

### Storage model

Two distinct stores, different purposes:

- **Market data** — currently Parquet files under `data/`. **Being migrated to
  SQLite** (`data/market_data.db`) with `prices` and `features` tables, composite
  primary key `(ticker, date)`, upsert on write so reruns update rather than
  duplicate.
- **Trade ledger** — `data/positions.db` (SQLite). Stays separate. This is the
  "what did the system actually do" record that `back_test.py` reads.

---

## Conventions

- Commit on every meaningful change, and update `README.md` in the same commit.
  See `GIT_WORKFLOW.md`.
- Config over hardcoding, always.
- Pipeline stages must be independently runnable and idempotent — rerunning a
  stage should update state, not duplicate or corrupt it.
- Long-running jobs must be resumable. Assume any run can be interrupted.
- Never introduce a dependency without adding it to `requirements.txt` in the
  same change.

---

## Scale targets

- Universe: full US common stock on NYSE/NASDAQ, ~6,000-8,000 tickers
  (currently 18 via fallback).
- History: 20 years of daily bars (currently configured for 730 days).
- Estimated database size at full scale: 14-19 GB, plus ~5 GB/year of
  strategy-search ledger.

### Target host

Moving to a VM on the "Arena" hypervisor (i7, 8 cores, 32 GB, shared with one
other VM using 4 cores / 12-16 GB).

Allocation: **4 vCPU / 12 GB RAM / 100 GB disk.**

CPU is fully committed across both VMs, so heavy jobs (historical backfill, model
training, strategy search) need an off-peak window. The strategy search and the
Ollama LLM step must not run concurrently — together they exceed 12 GB.

---

## Planned: the Strategy Lab

A major scope addition, fully specced in `docs/STRATEGY_LAB.md`. Summary:

An evolutionary search engine that generates random strategy configurations,
scores them against history on a risk-adjusted reward, keeps and mutates the
winners, and promotes survivors through a validation gauntlet before any real
money is involved.

Key design points (do not silently change these — they were deliberate):

- **Reward is risk-adjusted, not raw profit.** Raw P&L maximization reliably
  discovers strategies that make enormous concentrated bets.
- **The action space is parameter tuning**, not per-ticker RL actions and not
  open-ended rule synthesis. Keeps results interpretable and fast to evaluate.
- **The sealed holdout period is sealed.** Each strategy may be evaluated
  against it exactly once, ever. No peeking for early stopping, ranking, or
  "just checking."
- **Trial count is recorded** so a deflated Sharpe ratio can be computed. Testing
  200k strategies inflates the winner's apparent skill; the correction matters.

New modules to build: `genome.py`, `simulator.py`, `reward.py`, `evolve.py`,
`ledger.py`, `promote.py`, `lab_dashboard.py`.

---

## Open decisions — do not assume answers

1. **Survivorship-bias data source (BLOCKING).** yfinance omits delisted
   companies, so any universe built from it excludes every bankruptcy and
   acquisition — which inflates every backtest. Either budget for point-in-time
   data with dead tickers (~$50-100/mo, e.g. Sharadar via Nasdaq Data Link) or
   explicitly accept a known, unmeasured upward bias. Unresolved.
2. **Arena provisioning** — confirm 100 GB datastore availability and identify
   the other VM's quiet hours for the overnight search window.
3. **Paper-trading duration and funding stake** — no concrete rule agreed yet.

---

## A standing caution

This system searches a large space of strategies against fixed historical data.
That process reliably produces strategies with excellent backtests that are pure
noise, and it gets worse the harder the search works. The validation ladder exists
specifically to catch these. Treat every backtest figure as an optimistic upper
bound, never as a forecast, and never weaken the validation protocol to make
results look better.
