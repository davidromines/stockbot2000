# Stockbot2000 — Roadmap

Last updated: 2026-09-08. 12 phases. Status: full-depth market database loaded; pipeline runs end to end.

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

### 05 · Migration to Arena hypervisor ✅ 100%
Complete 2026-09-11. Running on the Arena VM — hostname `stockpicker2000`, repo at
`~/stockbot2000`, Ubuntu 26.04 LTS, pushed to a private GitHub remote over SSH.

Measured allocation: **4 vCPU / 10.9 GB RAM / 97 GB disk**.

- ✅ Python 3.12.13 from deadsnakes, venv built, requirements install clean
- ✅ git initialised with the migration reconstructed as real commits, remote pushed
- ✅ Strategy Lab compute plan re-sized against measured RAM rather than the planned
  12 GB — see `STRATEGY_LAB.md`. The shared search matrix turned out not to be the
  binding constraint; concurrency with Ollama is

Two things this phase leaves behind deliberately, tracked elsewhere:

- The VM hostname and Linux user still read `stockpicker`. They predate the rename
  and are unrelated to the project name — not a leftover to tidy.
- Code arrived by manual file transfer, so **there is no git history before
  2026-09-08.** Recoverable from the old `betbot9000` box only if that box is ever
  reachable again; not worth blocking on.

### 06 · Data infrastructure scale-up 🟡 90%
**The market database is built.** `data/market_data.db` holds 35,425,982 price
bars across 13,121 instruments spanning 1962-01-02 to 2026-09-04, plus 33,789,595
feature rows — 31.5M of them with all 20 indicators present. 8.5 GB.

- ✅ 13,155 listings from the NASDAQ Trader directory across six venues, every one
  tagged by `security_type` (etf 5,652 · common_stock 5,373 · preferred 465 ·
  warrant 438 · unit 372 · adr 276 · closed_end_fund 273 · note 165 · right 128 ·
  etn 13)
- ✅ Full available history per instrument, not a fixed 20-year window
- ✅ Integrity verified: no negative or inverted bars, no duplicate keys, no orphan
  feature rows, no untagged symbols, `quick_check` clean
- ✅ Yahoo rate limiting handled adaptively, with throttling distinguished from
  genuine no-data
- ⚠️ 24 instruments unavailable (20 SPAC rights Yahoo does not quote, SVA halted,
  3 others). Common-stock coverage is 5,372 of 5,373
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

### 09 · Evolutionary search & idea ledger ✅ 100%
`ledger.py` built 2026-09-11 — strategies, evaluations, promotions and lab_runs.
Records parentage so lineage is inspectable, and a `trial_index` per evaluation so
the deflated Sharpe correction has a true trial count rather than an estimate.
Genomes stored as JSON, so any strategy can be re-run exactly.

✅ `evolve.py` built 2026-09-11 — tournament selection, elitism, mutation and
crossover, with selection pressure on net P&L after costs. Smoke run over
2018-2019 showed the population improving: profitable candidates went 11/40 to
25/40 to 34/40 across three generations. ~4 evaluations/sec on one core.

The loop is deliberately plain. The risk in this design is the fitness function
and the validation ladder, not the optimiser — a clever optimiser pointed at a
bad objective just finds bad answers faster.
`evolve.py`, `ledger.py`. Population loop with parallel scoring; every idea ever
tried recorded with parentage and results. ~200k evaluations per overnight run,
full re-search weekly.

### 10 · Promotion pipeline & lab dashboard ✅ 100%
`promote.py` built 2026-09-11. Six stages from search to funded, with the sealed
holdout enforced in code: a second attempt on the same strategy is refused and the
refusal recorded, because discipline is not a reliable defence against re-testing
until something passes.

Deflated Sharpe is implemented and moves correctly with trial count, but its units
are mismatched (annualised Sharpe against a trade count) so the threshold is too
strict — tracked in `BACKLOG.md`. Stage 04 is directional, not calibrated.

First run through the ladder: 49 shortlisted from 120 scored, 45 surviving
validation. That survival rate is too high and is also in the backlog.

✅ `lab_dashboard.py` built 2026-09-11 — a self-contained HTML page, no server
and no dependencies. Net P&L leads every table; fitness and Sharpe are shown as
diagnostics of *why*, never as the verdict. Renders the family tree of the best
strategy, because a winner reached through a visible line of improving ancestors
is a different proposition from one that appeared fully formed from a random draw.
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

### Paper trading ✅
`paper_trading.py` built 2026-09-11. Forward testing, day by day, with costs
charged through the same `costs.py` the backtest and the Lab use.

**This is the only measurement in the project with no survivorship bias at all.**
A backtest can only buy companies that still exist; paper trading buys what is
listed today and finds out what happens. Whatever the ~10-point haircut on
backtests over- or understates, none of it applies here.

It is also the slowest way to learn anything, which is why it sits at the end of
the promotion ladder. Backtests discard ideas cheaply; this one is for trusting
the survivors. Closing a run files it in the same ledger as the backtests, so
forward and historical results compare on net P&L directly.

### Experiment ledger ✅
`experiments.py` built 2026-09-11. One leaderboard for backtests, paper runs and
lab strategies, ranked by net P&L. `--compare A B` puts two ideas side by side.

The premise, agreed with the user: absolute backtest figures stay
survivorship-inflated, but both ideas carry the same bias, so the *gap* between
them is far more trustworthy than either number alone. That holds best between
similar strategies — a dip-buyer is inflated more than a trend-follower.

---

## Open items

| Item | Status |
|---|---|
| Survivorship-bias data source | **Open — needs work.** Collect-now accepted as an interim, but this is the largest threat to every backtest figure. Research + Internet Archive reconstruction now tracked in `BACKLOG.md`. |
| Arena provisioning (disk, quiet hours) | Partly resolved — 97 GB disk confirmed; quiet hours still open |
| Funded stake vs. the $100 account cap | **Open** — promotion ladder ends in a funded stake, mandate caps total exposure at $100 |
| Paper-trading duration & funding stake | Open |
| Strategy Lab design | Resolved 2026-09-08 |
| Universe & history scope | Resolved — full US equities, 20yr |

---

*Nothing here is investment advice, and no backtested result is a prediction of
future returns.*
