# Stockbot2000 — Roadmap

Last updated: 2026-09-08. 12 phases. Status: migrated to Arena; smoke test resuming.

Legend: ✅ complete · 🟡 in progress · 🔵 planned · ⚪ backlog

---

## Operating mandate

Fixed constraints the phases below all sit inside:

- **$100 total account cap** — $10 x 10 positions. Total downside is bounded at $100.
- **Every order human-approved**, entries and exits alike.
- **Swing trading only** (days-weeks). Intraday is ruled out by pattern-day-trader
  rules, which require $25k equity.
- **Entry threshold: score >= 70.**
- **Stops are not broker-side.** Robinhood dollar-amount orders are market-only and
  regular-hours-only, so stops are evaluated once daily by `check_exits.py` and
  filled as approved market orders. Gap risk is not covered.

---

## Foundation

### 01 · Project foundation ✅ 100%
Renamed (betbot9000 → trend-scanner → stockpicker2000 → Stockbot2000), repo identity established,
git conventions documented in `GIT_WORKFLOW.md`.

### 02 · Core pipeline build ✅ 100%
All nine pipeline modules written: universe selection, data pull, feature engineering,
scoring, model training, ATR stop-loss, position ledger, backtest, LLM report.

### 03 · Environment setup 🟡 90%
Fixed three missing dependencies (`pyyaml`, `yfinance`, `pyarrow`). Removed
`pandas_ta` entirely — its pinned `numba` version will not build on Python 3.14 —
and rewrote all indicators in plain pandas/numpy.

✅ `features.py` deployment confirmed 2026-09-08 (byte-identical to known-good; no
module imports `pandas_ta`). ✅ `pandas-ta` removed from `requirements.txt`, where it
was still pinned.

**Remaining:** install Python 3.12 on the Arena VM and build the venv against it —
Ubuntu 26.04 ships 3.14 as system Python.

### 04 · End-to-end smoke test 🟡 35%
Proving the pipeline runs start to finish on the 18-ticker fallback universe.
**This is the current focus. Nothing downstream is worth building until it passes.**

- ✅ `universe.py`
- ⏳ `data_pull.py` — retry pending
- ⏳ `features.py` — pending
- ⏳ `score.py` — pending
- ⏳ `train_model.py` — not yet run
- ⏳ `backtest.py` — not yet run

---

## Infrastructure

### 05 · Migration to Arena hypervisor 🟡 85%
VM is provisioned and the project now lives on it — hostname `stockbot2000`,
repo at `~/stockbot2000`, Ubuntu 26.04 LTS.

Measured allocation: **4 vCPU / 11 GB RAM / 97 GB disk** (83 GB free). Note the RAM
is 11 GB, not the 12 GB planned — the Strategy Lab compute budget assumes 12 GB and
should be re-sized against the real figure.

**Remaining:** install Python 3.12 (deadsnakes has 3.12.13 built for Ubuntu 26.04),
build the venv, initialize git. Code arrived by manual file transfer, so there is no
git history prior to this point.

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
| Arena provisioning (disk, quiet hours) | Partly resolved — 97 GB disk confirmed; quiet hours still open |
| Funded stake vs. the $100 account cap | **Open** — promotion ladder ends in a funded stake, mandate caps total exposure at $100 |
| Paper-trading duration & funding stake | Open |
| Strategy Lab design | Resolved 2026-09-08 |
| Universe & history scope | Resolved — full US equities, 20yr |

---

*Nothing here is investment advice, and no backtested result is a prediction of
future returns.*
