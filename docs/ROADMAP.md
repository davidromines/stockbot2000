# Stockbot2000 — Roadmap

Last updated: 2026-09-08. 12 phases. Status: 20yr history loaded; pipeline runs end to end.

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

### 03 · Environment setup ✅ 100%
Fixed three missing dependencies (`pyyaml`, `yfinance`, `pyarrow`). Removed
`pandas_ta` entirely — its pinned `numba` version will not build on Python 3.14 —
and rewrote all indicators in plain pandas/numpy.

✅ `features.py` deployment confirmed 2026-09-08 (byte-identical to known-good; no
module imports `pandas_ta`). ✅ `pandas-ta` removed from `requirements.txt`, where it
was still pinned.

✅ Python 3.12.13 installed from deadsnakes and venv built at `./venv`.
`requirements.txt` installed clean on 2026-09-08 — no `numba`, no build failures.

Note: pip resolved pandas 3.0.5 / numpy 2.5.3 because requirements only sets `>=`
floors. It works today, but the versions that work are unrecorded — see `BACKLOG.md`.

### 04 · End-to-end smoke test 🟡 85%
Every stage now runs start to finish on the 18-ticker fallback universe
(2026-09-08), with no code changes required.

- ✅ `universe.py` — 18 tickers via fallback
- ✅ `data_pull.py` — 13,140 rows
- ✅ `features.py` — 20 indicators
- ✅ `train_model.py` — AUC 0.764 (not a valid estimate, see below)
- ✅ `score.py` — top score 41.7
- ✅ `position_tracking.py`, `check_exits.py`
- ✅ `backtest.py` — runs, **but the number it prints is invalid**
- 🟡 `llm_report.py` — runs in fallback mode; Ollama not installed on this VM

**Not at 100%, because "it runs" is not "it works":** no candidate cleared the
threshold of 70, so the entry path was never exercised and the ledger stayed
empty, meaning the exit path wasn't either. And `backtest.py`'s 97.9% win rate is
look-ahead leakage from the random train/test split — phase 07 work, not a result.

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

### 06 · Data infrastructure scale-up 🟡 85%
**Prices are in.** `data/market_data.db` holds 18,150,413 daily bars across 6,169
tickers, 2006-09-05 to 2026-09-04, in 1.3 GB — the 14-19 GB estimate assumed every
ticker had the full 20 years; only 2,226 do.

- ✅ `universe.py` builds 6,172 tickers from the NASDAQ Trader directory
- ✅ `storage.py` owns the schema; `backfill.py` loads it resumably (11.4 min, 3
  tickers with no Yahoo data)
- ✅ Verified: idempotent re-runs, resumable after SIGTERM, no duplicates, no
  impossible bars
- ✅ `features` table populated — 18,108,070 rows, 5,749 tickers, 3.7 min build.
  16.8M rows have all 20 indicators non-null; 420 tickers are ineligible (under
  210 bars, so the 200-day SMA cannot warm up)
- ✅ Database 4.5 GB, integrity-checked, no orphans or duplicate keys
- ✅ Yahoo rate limiting handled adaptively, with throttling distinguished from
  genuine no-data so a throttled run cannot mark real tickers as failed
- ⏳ Daily pipeline still reads Parquet — repointing it is the next step

**No longer blocked.** The survivorship decision was made: collect now, accept the
bias, track `source` per row so a point-in-time provider can be layered in later.
Daily symbol snapshots now record when tickers leave the listings, so the gap stops
widening from here.

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
| Survivorship-bias data source | Decided 2026-09-08 — collect now, accept bias, keep it reversible. Buying point-in-time data remains open. |
| Arena provisioning (disk, quiet hours) | Partly resolved — 97 GB disk confirmed; quiet hours still open |
| Funded stake vs. the $100 account cap | **Open** — promotion ladder ends in a funded stake, mandate caps total exposure at $100 |
| Paper-trading duration & funding stake | Open |
| Strategy Lab design | Resolved 2026-09-08 |
| Universe & history scope | Resolved — full US equities, 20yr |

---

*Nothing here is investment advice, and no backtested result is a prediction of
future returns.*
