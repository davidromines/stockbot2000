# StockPicker2000 — Roadmap

Last updated: 2026-09-08. 12 phases. Status: smoke test in progress.

Legend: ✅ complete · 🟡 in progress · 🔵 planned · ⚪ backlog

---

## Foundation

### 01 · Project foundation ✅ 100%
Renamed (betbot9000 → trend-scanner → StockPicker2000), repo identity established,
git conventions documented in `GIT_WORKFLOW.md`.

### 02 · Core pipeline build ✅ 100%
All nine pipeline modules written: universe selection, data pull, feature engineering,
scoring, model training, ATR stop-loss, position ledger, backtest, LLM report.

### 03 · Environment setup 🟡 80%
Fixed three missing dependencies (`pyyaml`, `yfinance`, `pyarrow`). Removed
`pandas_ta` entirely — its pinned `numba` version will not build on Python 3.14 —
and rewrote all indicators in plain pandas/numpy.

**Remaining:** confirm the rewritten `features.py` is actually deployed on the box.

### 04 · End-to-end smoke test 🟡 35%
Proving the pipeline runs start to finish on the 18-ticker fallback universe.
**This is the current focus. Nothing downstream is worth building until it passes.**

- ✅ `universe.py`
- ⏳ `data_pull.py` — retry pending
- ⏳ `features.py` — pending
- ⏳ `score.py` — pending
- ⏳ `train_model.py` — not yet run
- ⏳ `back_test.py` — not yet run

---

## Infrastructure

### 05 · Migration to Arena hypervisor 🔵 0%
New VM on the i7 host, sharing 8 cores / 32 GB with one existing VM.
Allocation: 4 vCPU / 12 GB RAM / 100 GB disk. Install Python 3.12, not 3.14.

### 06 · Data infrastructure scale-up 🔵 0%
Replace the Parquet cache with SQLite (`market_data.db`, `prices` + `features`
tables). Scale from 18 tickers to the full US equity universe (~6-8k) with 20
years of daily history. Estimated 14-19 GB.

**Blocked on:** the survivorship-bias data source decision.

### 07 · Simulator realism & backtest rigor 🔵 0%
Costs, slippage, liquidity floors, true walk-forward splitting, long-only
constraint. Promoted in priority — the Strategy Lab is only as trustworthy as
the simulator it optimizes against.

---

## Strategy Lab (new scope)

Full specification in `STRATEGY_LAB.md`.

### 08 · Genome, simulator & reward engine 🔵 0%
`genome.py`, `simulator.py`, `reward.py`. The searchable strategy definition and
the vectorized engine that scores one against history.

### 09 · Evolutionary search & idea ledger 🔵 0%
`evolve.py`, `ledger.py`. Population loop with parallel scoring; every idea ever
tried recorded with parentage and results. ~200k evaluations per overnight run,
full re-search weekly.

### 10 · Promotion pipeline & lab dashboard 🔵 0%
`promote.py`, `lab_dashboard.py`. The gauntlet from random guess to funded, plus
leaderboards and strategy family trees.

---

## Going live

### 11 · Live integration & paper trading ⚪ backlog
Brokerage connection, paper-trading harness against live forward data, then small
real allocations for strategies that survive everything upstream.

### 12 · Notifications & polish ⚪ backlog
Telegram daily scorecard and lab digest; LLM report refinements.

---

## Open items

| Item | Status |
|---|---|
| Survivorship-bias data source | **Open — blocking phase 06** |
| Arena provisioning (disk, quiet hours) | Open |
| Paper-trading duration & funding stake | Open |
| Strategy Lab design | Resolved 2026-09-08 |
| Universe & history scope | Resolved — full US equities, 20yr |

---

*Nothing here is investment advice, and no backtested result is a prediction of
future returns.*
