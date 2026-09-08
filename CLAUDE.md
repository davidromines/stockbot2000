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
- `data_pull.py`, `features.py`, `score.py`, `train_model.py`, `backtest.py`

Immediate next steps:
1. ~~Confirm the rewritten `features.py` is deployed.~~ **Done 2026-09-08** —
   verified byte-identical to the known-good copy; no module imports `pandas_ta`.
2. ~~`mkdir -p data/raw models`.~~ **Done** — `data/raw`, `models`, `logs` exist.
3. Build the venv on Python 3.12, install `requirements.txt`.
4. Run each stage in order, fix what breaks.

---

## Environment gotchas — these have already cost time

- **Python 3.14 is too new for parts of this stack.** `pandas_ta` pins
  `numba==0.61.2`, which refuses to build on 3.14. `pandas_ta` has been **removed
  entirely**; all indicators are hand-rolled in plain pandas/numpy inside
  `features.py`. Do not reintroduce `pandas_ta`. **This VM also ships Python 3.14
  as the system Python** (Ubuntu 26.04) — 3.12 is installed alongside it from the
  deadsnakes PPA. Always build the venv with `python3.12`, never bare `python3`.
- **`requirements.txt` had `pandas-ta` still pinned** long after the code stopped
  importing it. Removed 2026-09-08. `pyyaml`, `yfinance` and `pyarrow` — previously
  flagged as missing — are all present and pinned. Requirements are now believed
  correct but have not yet been installed cleanly end to end.
- **Indicator count is 20, not 25.** `FEATURE_COLS` in `train_model.py` lists 20,
  and all 20 are verified present in `features.py` output. `README.md` and
  `docs/STRATEGY_LAB.md` both say "~25" in places — the genome's `indicator_weights`
  space is sized off that wrong number and should be built against 20.
- **Wikipedia S&P 500 scrape returns HTTP 403.** `universe.py` silently falls back
  to 18 hardcoded tickers. Planned replacement: the NASDAQ Trader symbol directory
  (`nasdaqlisted.txt` / `otherlisted.txt`), which is free and does not require scraping.
- **yfinance does not serve delisted tickers.** This is a real correctness problem
  for backtesting — see the survivorship-bias item under Open Decisions.
- Long backfills must be run under `nohup`/`tmux`/`screen`. SSH sessions to this
  box have dropped mid-run before.

---

## Trading mandate and hard constraints

These came out of the original design conversation and are **not** derivable from
the code. They bound everything else.

- **The account is capped at $100.** That is the entire downside. Position sizing
  (`$10` x 10 positions in `config.yaml`) exists to spend exactly that budget, not
  as an arbitrary default. Do not propose sizing that assumes a larger account.
- **Every order is human-approved.** Entries and exits both. The system produces
  candidates; a person authorizes each trade. This was agreed explicitly at design
  time and is not a temporary training-wheels measure.
- **The user owns the outcome.** This is a data-gathering and scoring tool. It does
  not give investment advice, and no backtest figure is a forecast.
- **Swing trading, days to weeks — never intraday.** Not a style preference: US
  pattern-day-trader rules require $25k equity to day-trade without restriction, so
  a $100 account cannot day-trade. Any change toward intraday breaks this.
- **Entry threshold: score >= 70.** Currently hardcoded in the Claude-side workflow
  and passed as `--threshold` to `backtest.py`. It is *not* in `config.yaml` yet,
  which violates the config-over-hardcoding rule. See `BACKLOG.md`.

### Robinhood order mechanics — these shape the design

Dollar-based fractional orders are supported (to 6 decimal places), which is what
makes a $100 account workable at all. But:

- **Dollar-amount orders are market orders only.** No limit or stop order can carry
  a dollar amount.
- **They execute only during regular hours**, 09:30-16:00 ET.

The consequence matters: **stop-losses cannot rest at the broker.** `stop_loss.py`
computes a level, `check_exits.py` compares it against a daily quote, and the exit
is then placed as an approved market order. So a stop is checked roughly once a day,
not continuously — **overnight and intraday gaps below the stop are not protected
against.** Any future work on exits should start from this limitation rather than
assume a broker-side stop exists.

### Claude's role in the daily loop

Claude reads exactly two files — `data/scoresheet.json` and `data/exits_needed.json`
— and nothing else. Not the raw data, features, or model. For entries it filters to
score >= 70, checks tradability and fractional eligibility, checks the open-position
count against the cap, presents the list for approval, and on approval places $10
market orders. Fill prices are reported back so the ledger can be written
server-side; Claude has no direct database access.

---

## Architecture

Pipeline stages, in execution order:

| File | Role |
|---|---|
| `universe.py` | Builds the ticker list. Also owns `load_config()`, imported everywhere. |
| `data_pull.py` | Fetches OHLCV history via yfinance. |
| `features.py` | Computes **20** technical indicators per (ticker, date). No third-party TA lib. |
| `train_model.py` | Trains the XGBoost classifier. Owns `FEATURE_COLS`. |
| `score.py` | Ranks the universe, writes the scoresheet. |
| `stop_loss.py` | ATR-based stop levels (configurable to fixed-pct). |
| `position_tracking.py` | SQLite trade ledger — entries, exits, exit reasons. |
| `backtest.py` | Walk-forward simulation over the scoring strategy. |
| `check_exits.py` | Evaluates open positions against stop/exit rules. |
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
  "what did the system actually do" record that `backtest.py` reads.

---

## Conventions

- **Commit on every change. No exceptions.** This is the project's primary rule and
  it overrides any instinct to batch work up. Every edit — code, config, docs,
  a one-line typo fix — gets its own commit before moving to the next thing. The
  git log is the project's change record; if a change isn't committed, it didn't
  happen. Do not wait to be asked, do not finish a session with a dirty tree, and
  do not roll unrelated changes into one commit.
- Update `README.md` in the same commit whenever a change affects setup, usage,
  schema, or pipeline shape. See `GIT_WORKFLOW.md` for message conventions.
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

### Host — migration completed 2026-09-08

Now running on the "Arena" VM. Hostname `stockpicker2000`, user `stockpicker`,
repo at `~/stockpicker2000`. Ubuntu 26.04 LTS.

Measured: **4 vCPU / 11 GB RAM / 97 GB disk** (83 GB free at migration).
Note the RAM is ~11 GB, not the 12 GB planned — the strategy-search memory
budget should be sized against the real number.

The old host (`betbot9000`) is not reachable from this VM. Code arrived by
manual file transfer, so **there is no git history before this point.**

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
   Note this sits awkwardly against the $100 account cap: the Strategy Lab's
   promotion ladder ends in "funded, small fixed stake", but the mandate above
   caps total exposure at $100. Either the cap rises when the Lab goes live, or
   the funded stake comes out of the same $100. Undecided.

---

## A standing caution

This system searches a large space of strategies against fixed historical data.
That process reliably produces strategies with excellent backtests that are pure
noise, and it gets worse the harder the search works. The validation ladder exists
specifically to catch these. Treat every backtest figure as an optimistic upper
bound, never as a forecast, and never weaken the validation protocol to make
results look better.
