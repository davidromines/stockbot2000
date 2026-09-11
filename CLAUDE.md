# Stockbot2000

Automated swing-trading system: scores US equities on technical indicators, sizes and
stops positions by ATR, and evolves its own trading strategies against 20 years of
market history before any real capital is committed.

Renamed several times: `betbot9000` -> `trend-scanner` -> `stockpicker2000` ->
**`stockbot2000`** (current, as of 2026-09-08). Older commits, the VM hostname
and the Linux user still say `stockpicker` — that is expected, not a leftover to
clean up. Do not confuse this with the separate `betbot` project (college football
betting), which is a different system entirely.

---

## Current state — READ THIS FIRST

**The market database is built and complete** (2026-09-08): 35.4M price bars across
13,121 instruments back to 1962, plus 33.8M feature rows. Details under Storage
model. Phases 01-05 are done; phase 06 is at 90%.

**The single most important gap:** the daily pipeline still reads Parquet — 18
tickers, 730 days. Nothing consumes the database yet. Repointing `data_pull.py` /
`features.py` / `train_model.py` / `score.py` at SQLite is the next piece of work.

**Data freshness:** the last bar is 2026-09-04. `backfill.py` is incremental, so a
re-run tops it up rather than refetching. Check before trusting any score.

---

### Smoke test — passed 2026-09-08

**The smoke test passed on 2026-09-08.** Every stage ran end to end on the
18-ticker fallback universe, on Python 3.12 with no code changes required.

| Stage | Result |
|---|---|
| `universe.py` | 18 tickers (Wikipedia 403 -> fallback, as expected) |
| `data_pull.py` | 13,140 rows / 18 tickers -> `ohlcv_history.parquet` |
| `features.py` | 20 indicators for 18 tickers -> `features_latest.parquet` |
| `train_model.py` | 9,558 labeled rows, 21.9% positive, test AUC 0.764 |
| `score.py` | 18 scored; top score 41.7 (TSLA) |
| `position_tracking.py` | ledger initialized |
| `check_exits.py` | ran clean (no open positions) |
| `backtest.py` | ran; **result is invalid, see below** |
| `llm_report.py` | ran in fallback mode — Ollama is not installed on this VM |

### Do not trust the backtest number

`backtest.py --threshold 70` reports a **97.9% win rate over 47 trades**. This is
not a result, it is look-ahead leakage. `train_model.py` splits with
`train_test_split(..., stratify=y)` — a *random shuffled* split over time-ordered
rows — so the model is trained on the same history the backtest then evaluates,
including days after each simulated trade. Any figure from `backtest.py` is
meaningless until the walk-forward split in `BACKLOG.md` is implemented. Do not
quote this number, tune against it, or treat it as even an optimistic upper bound.

### What the smoke test did *not* exercise

- **No entry path.** Top score was 41.7 against a threshold of 70, so zero
  candidates qualified and no order was ever proposed. The buy flow is still
  unproven end to end.
- **No exit path.** The ledger is empty, so `check_exits.py` short-circuited.
- **No real LLM report.** Ollama is absent; reasons are generic placeholder text.

Immediate next steps (as of 2026-09-11):
1. Repoint the daily pipeline off Parquet onto `market_data.db`. The data exists
   and is unused; this is what connects them.
2. Fix the train/test split in `train_model.py` so `backtest.py` produces a real
   number. Arguably ahead of (1) in value — everything downstream depends on
   trusting the simulator, and more data cannot fix a leaking split.
3. Top up prices — the last bar is 2026-09-04.
4. Survivorship-bias research, starting with the free Internet Archive
   reconstruction. See `BACKLOG.md`.
5. Install Ollama, or decide the LLM report stays optional.

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
  flagged as missing — are all present and pinned. Requirements installed
  cleanly end to end on Python 3.12 on 2026-09-08. Versions are floors only
  (`>=`), so the working set — pandas 3.0.5, numpy 2.5.3, xgboost 3.4.1 — is not
  recorded anywhere; see `BACKLOG.md`.
- **Indicator count is 20, not 25.** `FEATURE_COLS` in `train_model.py` lists 20,
  and all 20 are verified present in `features.py` output. `README.md` and
  `docs/STRATEGY_LAB.md` both say "~25" in places — the genome's `indicator_weights`
  space is sized off that wrong number and should be built against 20.
- **Wikipedia S&P 500 scrape returns HTTP 403.** Still true, and `universe.source:
  sp500` still falls back to 18 hardcoded tickers — that is the smoke-test path and
  is left alone deliberately. Production uses `universe.source: all_us`, built from
  the NASDAQ Trader symbol directory, which does not scrape and does not 403.
- **yfinance returns negative prices for some tickers.** `auto_adjust=True`
  back-adjusts for splits and dividends; where the cumulative adjustment exceeds
  the original price the result goes negative, which also inverts high/low.
  Found on 8 tickers during the 20-year pull, and the guard has run over the full 13,121-instrument load since. `storage.is_valid_ohlcv()` now rejects these at
  write time — do not remove that guard, and do not "fix" impossible bars by
  taking absolute values. The adjusted series for those tickers is simply wrong.
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
- **Selection: the top 10 by score each day** (`risk.selection_mode: top_n`),
  subject to tradeability floors of `min_price` $5 and `min_dollar_volume` $1M/day.

  The old rule was "score >= 70". **It was unreachable and always selected
  nothing.** The score is a calibrated probability of a ~27%-base-rate event, so
  it rarely exceeds 50 — the highest in 183k out-of-sample rows was 66. Threshold
  and score were on different scales. Changed 2026-09-11 with the user's
  agreement. Do not reinstate an absolute cutoff without first checking it
  against the score distribution.

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
the top candidates by score, checks tradability and fractional eligibility,
checks the open-position count against the cap, presents the list for approval, and on approval places $10
market orders. Fill prices are reported back so the ledger can be written
server-side; Claude has no direct database access.

---

## Architecture

Pipeline stages, in execution order:

| File | Role |
|---|---|
| `universe.py` | Builds the ticker list (`sp500` / `all_us` / `custom`). Also owns `load_config()`, imported everywhere. |
| `runtime.py` | CPU thread caps and nice level. **Must be imported before numpy/pandas/xgboost.** |
| `storage.py` | Owns `market_data.db` — schema, upserts, ingest state. Only module writing SQL to it. |
| `backfill.py` | Resumable 20-year OHLCV loader for the full universe. Adaptive Yahoo rate limiting. |
| `build_features.py` | Computes the 20 indicators across all history into the `features` table. |
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

- **Market data** — `data/market_data.db` (SQLite), **8.5 GB**.

  `prices`: **35,425,982 rows across 13,121 instruments, 1962-01-02 to 2026-09-04.**
  Pulled at `period: max`, so each instrument carries its full available history —
  Alcoa reaches back to 1962, not just the 20 years the earlier pull captured.

  `features`: **33,789,595 rows across 9,950 tickers**, of which **31,529,867 have
  all 20 indicators non-null** — the trainable set. Computed only for
  `universe.feature_types` (common stock, ADRs, ETFs, closed-end funds); rolling
  indicators on a warrant or a corporate note are arithmetic without meaning.

  `symbols`: all **13,155 listings tagged by `security_type`** — etf 5,652,
  common_stock 5,373, preferred 465, warrant 438, unit 372, adr 276,
  closed_end_fund 273, note 165, right 128, etn 13.

  Integrity verified: zero negative or inverted bars, zero duplicate keys, zero
  orphan feature rows, zero untagged symbols, `quick_check` clean.

  **24 instruments have no data at all** — 20 SPAC rights Yahoo does not quote,
  plus SVA (halted) and three others. Common-stock coverage is 5,372 of 5,373.

  The daily pipeline still reads Parquet. Repointing `data_pull.py` / `features.py` /
  `train_model.py` / `score.py` at SQLite is the next piece of work and is not done.
- **Trade ledger** — `data/positions.db` (SQLite). Stays separate. This is the
  "what did the system actually do" record that `backtest.py` reads.

---

## Conventions

### How to communicate

- **Be brief.** Default to fewer words. Include what is needed to act or decide,
  and stop. No preamble, no restating the question, no summarising work the user
  just watched happen. Length is not thoroughness.
- **Prefer structure over prose.** Bullets, tables, short lists, diagrams and
  charts wherever they carry the information better than paragraphs. Numbers
  belong in tables; comparisons belong side by side; sequences belong in
  ordered lists.
- These two work together: structure is what makes brevity possible. A table of
  six figures replaces a paragraph nobody finishes reading.
- Brevity does not mean omitting bad news. Caveats, risks and failures stay —
  state them in one line instead of three.


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

- Universe: **13,155 listings** from the NASDAQ Trader directory across NASDAQ,
  NYSE, NYSE American, NYSE Arca, Cboe BZX and IEX — every instrument type, each
  tagged. `universe.tradeable_types` keeps the scanner on common stock; the
  database deliberately holds the whole market.
- History: **full available depth**, 1962 to present.
- **Measured** database size: 8.5 GB (73 GB free). The original 14-19 GB estimate
  turned out to be in the right range only by accident — it assumed 20 years for
  6-8k common stocks, and the real shape is 60+ years for 13k instruments.
- Beware the earlier universe count of 6,169 "common stocks": **822 of those were
  not common stock** (closed-end funds, corporate notes, preferred, units). Fixed
  by `security_type` tagging on 2026-09-08.

### Host — migration completed 2026-09-08

Now running on the "Arena" VM. Hostname is `stockpicker2000` and the Linux user is
`stockpicker` — both predate the rename to Stockbot2000 and were left alone; only
the project is renamed. Repo at `~/stockbot2000`. Ubuntu 26.04 LTS.

Measured: **4 vCPU (1 socket) / 11.7 GB RAM / 194 GB disk** (165 GB free).

The disk was resized 2026-09-11 — the volume group had ~98 GB unclaimed, so `/`
was 97 GB against a 200 GB device. `lvextend -l +100%FREE` plus `resize2fs`
recovered it. Worth re-checking after any VM reconfiguration.

RAM is 11.7 GB, not the 12 GB planned. The Strategy Lab compute plan is sized
against the measured figure — see `docs/STRATEGY_LAB.md`.

**CPU is capped deliberately.** `runtime.py` holds OpenBLAS, OpenMP and XGBoost to
`compute.max_threads` (3 of 4 cores) and batch jobs call `be_nice()`. It must be
the *first* import in any entry point: those libraries read their thread counts
once at load time, so setting the variables after numpy is imported does nothing,
silently. Do not reorder those imports.

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

1. **Survivorship-bias data source — interim decision made, still needs work.**
   yfinance omits delisted companies, so the universe excludes every bankruptcy and
   acquisition since 1962. Decided 2026-09-08: collect now and accept the bias, with
   `source` recorded per row and the symbol directory snapshotted daily so the gap
   stops widening. **That is an interim position, not a fix.** A flat haircut cannot
   correct it either, because the bias is not uniform across strategies and the Lab
   preferentially discovers the ones that exploit it. Full reasoning and a costed
   research path — free Internet Archive reconstruction first, paid point-in-time
   data second — are the first section of `BACKLOG.md`.
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
