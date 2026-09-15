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

**Data freshness: `daily.sh` runs at 07:00 on weekdays via cron** (installed
2026-09-12). It records the symbol directory, tops up prices, rebuilds features
and steps paper trading. Check `logs/daily.log` before trusting any score.

**Step 1 is the survivorship-critical one.** Recording the listing directory is
what stamps a ticker inactive on the day it disappears. The backwards bias
cannot be fixed — 5 tickers stopped trading in the whole 2006-2019 window
against 9,029 the Internet Archive says existed — but from 2026-09-12 forward
the record is point-in-time, and **a missed day loses that day's delistings
permanently.** If the VM is down for a week, that week is gone.

**`backfill.py` needs `--top-up` for daily use.** Plain `backfill.py` resumes an
*interrupted initial load*; it does not fetch new bars for tickers already
marked `done`, which after the historical load is all of them. That made a daily
re-run a silent no-op: on 2026-09-12 the database held bars to 2026-09-04 for
12,750 tickers and a full pipeline run advanced 28. Earlier wording here called
the loader "incremental", which was true of resumability and false of top-up.

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

### Walk-forward result — 2026-09-11

**The edge is stable.** 31 rolling retrains, 2011-2026, each trained on the prior
5 years and predicting the next 6 months. 7,597,510 out-of-sample predictions.

| | |
|---|---|
| AUC mean / min / max | 0.629 / 0.582 / 0.670 |
| Folds above 0.5 | **31 of 31** |
| Pooled AUC | 0.633 |
| Top-decile hit rate | **37.8%** vs 24.5% base (1.54x lift) |

This is the first evidence in the project that the signal persists rather than
being an artifact of where the data was cut. Run it with `walk_forward.py --run`;
it is resumable by fold, and `--report` prints the table.

Mild decay: folds before 2019 average 0.642, folds from 2020 average 0.611.
Consistent with alpha decay or regime change — still positive throughout.

**What this does not establish.** The measurement sits on survivorship-biased
data, so part of the lift may be survivors recovering rather than skill. AUC 0.63
is real but weak. **The 0.43% per-trade return quoted here was an artifact of
close fills and a 10-position config, and is superseded** — under next-bar fills
the same model is gross NEGATIVE. See "Fills happen on the NEXT bar" below. A
stable ranking is not the same as a profitable strategy, and this is the case
that proves it.

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
- **yfinance produces impossible prices for serial reverse-splitters.** TOPS
  carries a maximum adjusted close of **$549 trillion per share**; 425,964 rows
  across 333 tickers sit above $10,000. These passed every filter — `min_price`
  is a floor, and `dollar_volume_20` is close x volume, so inflated tickers looked
  maximally *liquid*. `storage.flag_price_anomalies()` marks them via
  `symbols.data_quality` (120 tickers) and every type-scoped query excludes them.
  The rule is absolute price **and** range, never range alone: Berkshire A really
  trades near $800k and Monster Beverage really is up 15,352x.
- **yfinance does not serve delisted tickers.** This is a real correctness problem
  for backtesting — see the survivorship-bias item under Open Decisions.
- Long backfills must be run under `nohup`/`tmux`/`screen`. SSH sessions to this
  box have dropped mid-run before.

---

## Trading mandate and hard constraints

These came out of the original design conversation and are **not** derivable from
the code. They bound everything else.

- **The account is capped at $100.** That is the entire downside. Sizing is
  **$20 x 5 concentrated positions** (`config.yaml`, changed 2026-09-14 from
  $10 x 10). Do not propose sizing that assumes a larger account.
- **Orders are placed by a person, and the pipeline is built around that.**
  Not as a training-wheels measure: Claude does not execute financial
  transactions, so the loop is *system generates -> human places -> system
  reconciles*. `orders.py` writes an exact slate to `data/orders_today.txt` and
  `.json` each morning; a person places them; the next run reads the real
  account and records actual fills. Nothing needs to be reported back by hand.

  Two consequences worth knowing rather than rediscovering:

  **Sells are always listed before buys.** A fully deployed $100 account has no
  spare cash, so a buy placed before its matching sell is rejected for
  insufficient funds.

  **A `picks` row is `recommended` until the position is confirmed in the
  account, then `open`.** Marking a proposal as held on the day it is proposed
  makes the order generator see a full book and refuse to buy the very names it
  just recommended.
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
| `reconstruct_universe.py` | Replays Internet Archive captures of the symbol directory to measure the survivorship gap. |
| `edgar_registry.py` | Point-in-time registry of every SEC annual filer, 1993-now. The only source here reaching before 2008. |
| `delistings.py` | The delisting registry — which companies died and when. Reads the API key from `~/.alphavantage_key`, never the repo. |
| `stress_test.py` | Bounds how much a result depends on the missing companies. |
| `bias_exposure.py` | Scores a strategy's dependence on deeply drawn-down names; gates the sealed stage. |
| `bias_benchmark.py` | Quantifies that bias in %/year against Ken French's CRSP-based series. |
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
- **The action space is open-ended rule synthesis** as of 2026-09-11, changed
  from parameter tuning with the user's explicit agreement. The search composes
  entry and exit rules from primitives and operators; risk parameters stay as
  tuned genes. Reversed because parameter tuning can only re-tune an idea that
  already loses money after costs, and because net-of-cost fitness now exists to
  make open search survivable. Complexity is penalised so trees cannot grow until
  they memorise history.
- **Score against the null, never against zero.** Buying at random and holding
  five days was profitable in every window this project tests on, because the
  market rose. Scoring against zero rewards being long in a bull market, not
  selection — it let 57% of random strategies pass validation. `benchmark.py`
  computes what chance earns per window; fitness and every gate measure excess
  over it. **Re-run `control.py --calibrate` after any change to fitness, the
  simulator or the gates.** A gate never tested against noise is an assumption.
- **The null is a surface over price and holding period, not a number.** Both
  dimensions were loopholes while flat, and the search found each immediately.
  Holding period: the null is +0.07% at 5 days and +2.1% at 45, so a fixed
  5-day null paid a long-holding strategy 30x for drift it did not earn.
  **Price: the null runs from +25.2% at $5-6 to -0.5% at $100+ over a 45-day
  hold** (2020-22), so a market-wide null handed anything that bought cheap
  stocks an enormous unearned excess. Each trade is charged the null of its own
  entry price, interpolated in log price between band centres — see the next
  item for what that cost. Bands are configured in `config.yaml` under
  `benchmark.price_band_edges`, deliberately fine below $20 where nearly all the
  variation sits.
- **Net P&L in dollars is the headline metric.** Not AUC, not win rate, not
  Sharpe. Those are diagnostics of *why*; money is the test of *whether*. Report
  it first, everywhere.
- **The sealed holdout period is sealed.** Each strategy may be evaluated
  against it exactly once, ever. No peeking for early stopping, ranking, or
  "just checking."
- **Trial count is recorded** so a deflated Sharpe ratio can be computed. Testing
  200k strategies inflates the winner's apparent skill; the correction matters.

New modules to build: `genome.py`, `simulator.py`, `reward.py`, `evolve.py`,
`ledger.py`, `promote.py`, `lab_dashboard.py`.

---

## Open decisions — do not assume answers

1. **Survivorship bias — now ENUMERATED, not just estimated (2026-09-12).**

   **Every backtest figure is still roughly 10 points a year optimistic**, but
   the hole is now a list rather than an average.

   - `delistings.py` holds the Alpha Vantage registry: **9,464 delisted
     listings, 7,480 of them common stock, and we hold prices for 418 (5.6%).
     7,062 companies a backtest here can never buy**, each with an exact
     delisting date. That independently corroborates the Internet Archive
     figure of 9,029 by a completely unrelated method.
   - **Thin before 2009** — the registry records 4 delistings for all of 2008 —
     so it does *not* cover the financial crisis, which sits inside the
     2006-2019 search window. Use EDGAR for that era.
   - `edgar_registry.py` builds a point-in-time company registry from the SEC
     quarterly indexes, **1993 to now**: 303,383 annual filings, 38,876
     distinct companies, **31,752 (82%) that stopped filing**. Coverage of
     10-K filers by our price data runs **14% in 1998, 26% in 2007, 50% in
     2019, 77% in 2025** — improving toward the present, which is the signature
     of survivorship bias rather than of better collection.
   - `bias_benchmark.py` still gives the headline 10.4 points/year against Ken
     French's CRSP-based series. Treat it as an upper bound; it also contains
     composition differences.
   - **Prices for the dead remain unavailable from any free source.**
     FirstRateData sells 16,302 tickers including 7,000+ delisted back to 2000,
     which matches the size of our hole almost exactly, and is the cheapest
     thing that would close it. CRSP via WRDS is the academic standard and free
     with a university affiliation.

   **A trap worth remembering.** Measuring the 418 delisted names we *do* hold
   suggests delisting is nearly harmless: median drawdown 20%, mean final-60-day
   return **+1.3%**. That is wrong, and the reason is the whole problem in
   miniature — those 418 are the delistings that survived the survivorship
   filter, because a clean acquisition keeps its price history and a bankruptcy
   does not. Never calibrate the failure case on that sample.

   **Drawdown as a proxy for death is real but weak.** 15% of all rows sit more
   than 30% below their 200-day high; 38% of rows at actual delisting do. A 2.5x
   enrichment. `bias_exposure.py` is an ordering, not a probability.

2. **Survivorship-bias data source — interim decision made, still needs work.**
   yfinance omits delisted companies, so the universe excludes every bankruptcy and
   acquisition since 1962. Decided 2026-09-08: collect now and accept the bias, with
   `source` recorded per row and the symbol directory snapshotted daily so the gap
   stops widening. **That is an interim position, not a fix.** A flat haircut cannot
   correct it either, because the bias is not uniform across strategies and the Lab
   preferentially discovers the ones that exploit it. Full reasoning and a costed
   research path — free Internet Archive reconstruction first, paid point-in-time
   data second — are the first section of `BACKLOG.md`.
3. **Arena provisioning** — confirm 100 GB datastore availability and identify
   the other VM's quiet hours for the overnight search window.
4. **Paper-trading duration and funding stake** — no concrete rule agreed yet.
   Note this sits awkwardly against the $100 account cap: the Strategy Lab's
   promotion ladder ends in "funded, small fixed stake", but the mandate above
   caps total exposure at $100. Either the cap rises when the Lab goes live, or
   the funded stake comes out of the same $100. Undecided.

---

## The price-filter result — 2026-09-12

**The Strategy Lab's first 66 "validation survivors" were an artifact of the
benchmark, and all 66 have been voided.** This is the clearest example so far of
the standing caution below, and worth reading before trusting any Lab output.

The search's best answers collapsed to five rule structures, 58 of them the same
idea with a different constant:

| Count | Rule shape |
|---:|---|
| 33 | `sma_200 < N` |
| 25 | `lag(sma_200, N) < N` |
| 8 | everything else |

The top five were `sma_200 < 7.05 / 7.83 / 8.27 / 8.59 / 8.59` — **"buy stocks
whose 200-day average price is under about $8."** A price filter, not a strategy.
They appeared at generations 2-5, barely evolved.

They scored well because they were benchmarked against the whole market while
trading only its cheapest corner. Re-scored against the null of the stocks they
actually bought (`rescore.py`), **0 of the top 25 still clear the gate**:

| | was | now |
|---|---|---|
| `sma_200 < 7.05` net P&L | +$26,166 | +$26,166 |
| its excess over the null | large | **-$585** |
| null charged (45d, ~$6.70 entry) | +2.46% | **+13.38%** |
| fitness | 0.387 | 0.000 |

Three things to take from it:

1. **Net P&L alone cannot tell you anything.** That strategy really did make
   $26k in the simulator. Every dollar of it was the benchmark.
2. **Cheap stocks are where survivorship bias is worst**, since the sub-$8 names
   that went to zero are absent from this database entirely. Bucketing does not
   fix that — it stops the search being *paid* for finding it.
3. **Fixing it in two stages was necessary.** Hard price bands alone were not
   enough: the search immediately moved to the bottom of the cheapest band
   (`sma_200 < 6.81`, entering at a median $6.64 against a band median of $7.59)
   and collected the within-band gradient instead. Interpolating across price,
   and extrapolating below the cheapest band rather than clamping, closed it.

`control.py` still rejects 60 of 60 random strategies after the change.

---

## Search capacity is capped deliberately — 2026-09-12

**Do not add generations, population, or nightly evaluation budget.** The
`docs/STRATEGY_LAB.md` figure of 200,000 evaluations a night is obsolete and
should not be chased.

Four searches have now run. Every one found its result in the scoreboard rather
than in the market, and each fix revealed the next:

| Search | What it "found" | What it actually was |
|---|---|---|
| 1 | `sma_200 < 8` | a price filter, benchmarked against the whole market |
| 2 | one rule, 199 of 200 shortlist slots | monoculture; dedup compared text, not structure |
| 3 | 60 "distinct" entry rules | one rule with 60 dead branches; bloat as mutation armour |
| 4 | `pct_change(sma_200, 20) < -0.1` | buy the crash — 85% of entries in names this data has almost none of the failures for |

More search does not help because the binding constraint is not search. It is
that **5 tickers stopped trading in the whole 2006-2019 window against 9,029
companies the Internet Archive says existed.** A larger search over the same
data finds the same holes faster.

What to add instead, in order: forward paper-trading time (the only unbiased
measurement, and it accrues only in calendar time), then exposure diagnostics
like `bias_exposure.py`, then — if money is ever available — point-in-time
delisted prices at roughly $270/yr, which closes this permanently.

---

## Never version the database or its write-ahead log — 2026-09-12

`data/*.db`, `*.db-wal` and `*.db-shm` are gitignored, and must stay that way.

A tracked `-wal` is not just a large file in the repo. **`git checkout` rewrites
it underneath an open connection**, which is exactly how `market_data.db` was
corrupted: `git add -A` had swept the WAL in, and switching to a branch dropped a
stale write-ahead log onto a live 10 GB database.

Recovery worked by rebuilding into a fresh file, not repairing in place — `DROP
TABLE` cannot run on a corrupt table, because freeing its pages means walking the
tree that is broken. Prices, features, the Internet Archive snapshots, promotions
and every paper-trading run came through intact; `strategies` lost 6.3% and
`evaluations` 0.05%.

**Design note worth keeping:** `paper_runs` stores each strategy's genome inline
as JSON rather than referencing `strategies.id`. That denormalisation is why
every forward test survived a corruption that cost 5,767 strategy rows. Keep it.

---

## Fills happen on the NEXT bar — 2026-09-15. This one answers the project's question.

**Both engines bought at the close of the bar whose close produced the signal.**
Entry rules read `sma_200`, `rsi_14`, `close`; the simulator and the backtest
then filled at that same close, a price nobody can obtain until the session is
over. Exits had it too, which quietly made stops perfect: a stop detected at a
close was filled at that close, so the exit was booked at the very price that
breached it. CLAUDE.md has said for months that overnight gaps are unprotected
while the simulator assumed the opposite.

Fixed in `simulator.py`, `benchmark.py` (the null must match, or the comparison
is rigged — the second time that asymmetry has had to be closed) and
`backtest.py`. Signals fill at the next open; exits trigger on a close and fill
on the following open. `tests/test_fills.py` pins the semantics: one synthetic
trade goes from -$11.76 to **-$51.46** once the stop is allowed to gap.

### The measurement, controlled

Same model, same window (2022-07-20 -> 2026-09-11), same $20 x 5 config. **Only
the fill convention differs** — that is what `--fill close` exists for:

| | close fills | next-open fills |
|---|---:|---:|
| trades | 1,054 | 1,053 |
| **gross P&L** | **+$1.63** | **-$58.77** |
| gross per trade | +0.008% | **-0.279%** |
| trading costs | -$104.35 | -$104.29 |
| survivorship haircut | -$38.31 | -$38.27 |
| **net P&L** | **-$141.03** | **-$201.33** |
| win rate | 41.4% | 40.9% |

**The look-ahead was worth 0.287 points per trade.** Not the 0.7 estimated from
the older `baseline_top10` row — that comparison was contaminated, see below.

### Two findings, not one

1. **The signal does not survive costs, because there is no signal to survive
   them.** Gross is *negative* under honest fills. The strategy loses money
   before it pays a cent of spread. The question "does the edge survive costs"
   is answered, but not the way it was posed.

2. **The 0.43%/trade figure does not reproduce at 5 positions even WITH the
   look-ahead.** `baseline_top10` (2026-09-11) ran $10 x 10 and recorded gross
   +$90.31 over 2,109 trades = +0.428%/trade. The same model at $20 x 5 with the
   same close fills yields +0.008%/trade. **The top 5 names perform worse than
   the top 10** — a model whose ranking is not monotonic at its own top decile
   is evidence against the ranking being real, independent of fills.

**AUC 0.63 is not contradicted.** The classifier does rank better than chance;
31 of 31 walk-forward folds said so. It does not rank well enough to pay for
acting on it. Ranking skill and tradeable edge are different quantities and this
is the distance between them.

**Do not quote a per-trade return without stating its fill convention and
position count.** Both move it by more than the entire claimed edge.

---

## Size and liquidity in the fundamental screens — 2026-09-14

Two separate problems, found by asking why the daily book never recommends an
S&P 500 name. Neither was exclusion: large caps are in the universe and lose on
rank.

**1. The liquidity floor was missing from the conviction path.** `_load_panel`
filtered on `min_price` alone, so `min_dollar_volume` — the $1M/day floor the
scanner has enforced since the penny-stock result — never applied to any
fundamental screen. Only the classifier and Lab paths had it. It put **MXC at
the top of the daily book, agreed on by two systems, at $890k/day and a $15M
market cap**. Fixed; panel 2,674 -> 2,349 names. **If you add another screen,
apply both floors.**

**2. Value ranks were size ranks in disguise.** Measured on our own panel:

| metric | Spearman vs log market cap |
|---|---:|
| **book_to_market** | **-0.352** |
| earnings_yield | +0.185 |
| gross_profitability | -0.029 |
| beta | -0.026 |

B/M and EBIT/EV carry market cap in the denominator, and large companies hold
most of their worth in brand and goodwill no balance sheet records. So ranking
on B/M sorts toward small before it sorts toward cheap. Every value pick the
book made was in the bottom half by size, three of five in the bottom quartile,
from a universe whose median company is $3.1B.

**The tilt is not wrong in general and was not removed.** The size premium is
real and these screens are meant to lean small. It is wrong on *this* data:
microcaps are where the 7,062 missing delisted companies concentrate, so the
small-cap leg is the least trustworthy thing these screens do.

`conviction._rank(s, d)` now ranks within the row's size bucket. Two details
that are load-bearing:

- **Buckets are assigned within each review date, never pooled across dates.**
  The market roughly quadrupled over the backtest window, so pooled buckets
  would be a calendar variable — a company of unchanged real size would drift
  from "small" to "large" by doing nothing, and the late years would be almost
  entirely top-bucket.
- **Market cap is point-in-time.** `value_metrics._market_cap` multiplies shares
  taken *from the filing* by the price *on the filing date*. Never substitute a
  current share count: dilution is exactly what distressed companies do between
  then and now.

`buffett` was already the least affected screen — its quality and low-beta legs
pull against the value leg, and its top-10 median sat at the panel median while
the two pure value screens sat in the bottom quintile. The z-scores inside
`buffett.quality_score` are deliberately left global; their inputs correlate
-0.03 with size, so there is nothing to neutralise, and per-bucket z-scores
would thin each group until they stop meaning anything.

`daily_picks` takes at most one name per bucket, because neutral ranks still
permit three names from one corner on the days that corner holds the top
percentiles.

**Re-measured, and it helped.** `conviction_walkforward --all`, 15 rolling
2-year windows against SPY over the same dates:

| screen | was | now |
|---|---|---|
| deep_value | 6/15, -1.5% | **7/15, +0.8%** |
| quality_value | 4/15, -4.2% | **6/15, -3.6%** |
| buffett | 6/15 | 6/15, -3.7% |

Two of the three screens the book uses improved, none got worse. That is weak
evidence the small-cap tilt was costing these screens rather than paying them —
consistent with the tilt leaning on exactly the part of the sample where our
missing delistings concentrate.

**Do not read deep_value's +0.8% as an edge.** Its *median* window is -0.5%, so
a few windows carry the mean; the 15 windows overlap heavily and are nowhere
near independent; and 7 of 15 is a coin. The three screens the book does not
use remain poor — magic_formula 1/15, conservative 2/15, piotroski_value 3/15.

---

## The exit-pricing bug — 2026-09-12. Read this before trusting any old number.

**71% of the Lab's reported profit was a defect in its own simulator.**

`simulator.Panel` built its forward-price matrix by shifting within the
*filtered* panel. Tradeability floors decide what may be **bought**; they were
also deciding what an open position could be **sold** for. When a holding fell
below the $5 floor its rows left the frame, the forward price became NaN, and the
exit was booked at "the last price we have" — the last bar *above* the floor. A
company falling from $6 to $0.20 exited near $5.50 and its collapse never
happened.

Measured on the search's best strategy, 2006-2019:

| | filtered exits | true exits |
|---|---:|---:|
| net P&L | +26,065 | **+7,575** |
| mean trade return | 13.46% | **4.22%** |
| median trade return | 3.54% | **0.26%** |
| win rate | 60.7% | **49.2%** |

11.9% of its 20,000 trades had a truncated forward series; those returned -0.02%
against +15.29% for the rest.

**`benchmark.py` had the identical bug**, so the null was inflated the same way.
Both are fixed via `storage.load_exit_prices()`, and every `simulator.Panel`
construction in the project now passes unfiltered closes. **If you add another,
pass them.**

Three consequences worth holding on to:

1. **The crash-buying artifact was mostly this, not survivorship bias.** The
   search kept discovering "buy falling stocks" because the simulator refused to
   let falling stocks finish falling.
2. **The price gradient was partly this too.** The null for $5-6 names at a
   45-day hold fell from +6.19% to +3.85% once exits were priced honestly, so
   roughly half of "cheap stocks earn more" was truncation rather than a market
   fact.
3. **Noise lost its edge as well.** Random genomes beating the null fell from
   45% to 15%.

The same defect was found and fixed once before in the daily pipeline — see the
`storage.price_series` note. The Lab kept it for months. **A filter that decides
what you may buy must never decide what you may sell.**

---

## A standing caution

This system searches a large space of strategies against fixed historical data.
That process reliably produces strategies with excellent backtests that are pure
noise, and it gets worse the harder the search works. The validation ladder exists
specifically to catch these. Treat every backtest figure as an optimistic upper
bound, never as a forecast, and never weaken the validation protocol to make
results look better.
