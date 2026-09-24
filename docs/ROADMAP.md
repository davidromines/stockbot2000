# Stockbot2000 — Roadmap

Last updated: 2026-09-24. Phases 01–12 and 6–12 built; Phase 13 and Addendum A
**building** under Addendum B (`ADDENDUM_B_FINAL_BUILD_DIRECTIVE.md`).

Legend: ✅ complete · 🟡 in progress · 🔵 planned · ⚪ backlog

---

## Product definition — Addendum A (approved by Addendum B, building)

**Stockbot2000 is an autonomous algorithmic trading system** that continuously
discovers, tests, ranks and paper-trades strategies, automatically selects the
five best currently eligible ones, allocates ~$20 to each of five slots, and
executes and manages their trades through Robinhood — monitoring performance,
risk and degradation, and replacing weaker strategies with stronger ones
automatically. The objective is **positive trading P&L**; beating SPY is
reported, not required. Spec: `ADDENDUM_A_AUTONOMOUS_5_SLOT.md`; integration:
`ROADMAP_INTEGRATION.md`, Stage I.

---

## Operating mandate

| constraint | in force until the new engine ships | under Addendum A |
|---|---|---|
| Capital | $100 cap, $20 x 5 (`config.yaml`, since 2026-09-14) | unchanged; slot count and size configurable |
| Order placement | system generates the slate, a person places it | automatic, through the central risk and execution layer |
| Holding period | swing only, days to weeks | intraday, day trading, swing and long holds; the risk engine enforces the account's day-trade / settled-cash rules |
| Selection | top 5 by score daily (`top_n`) | slot engine: up to five distinct eligible strategies; an unqualified slot stays in cash |
| Stops | checked once daily by `check_exits.py`, exited by market order; gaps not covered | continuous intraday monitoring; risk exits override strategy signals |
| Broker mechanics | dollar-amount orders are market-only and regular-hours-only, so stops cannot rest at the broker | unchanged — this is why the monitor is client-side |

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

### 06 · Data infrastructure scale-up ✅ 100%
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
- ✅ Daily pipeline reads `market_data.db` throughout; Parquet is gone

**No longer blocked.** The survivorship decision was made: collect now, accept the
bias, track `source` per row so a point-in-time provider can be layered in later.
Daily symbol snapshots now record when tickers leave the listings, so the gap stops
widening from here.

### 07 · Simulator realism & backtest rigor ✅ 100%
**Its deciding question is answered: the signal does not survive costs.**
Re-measured 2026-09-24, same model and window, `backtest.py --fill`: gross
−$82.54 under next-open fills (−$22.70 under close fills), net −$226.11 over
1,062 trades. Negative before a cent of cost.

Promoted in priority — the Strategy Lab is only as trustworthy as the simulator
it optimizes against. Every item is now in code:

- ✅ **Walk-forward** — 31 rolling retrains, all 31 folds above 0.5 AUC
- ✅ **Liquidity floors** — $5 / $1M per day, and applied on the fundamental
  path too as of 2026-09-14, where they had been missing entirely
- ✅ **Survivorship haircut** — measured at ~10.4 points/year, and the hole
  enumerated at 7,062 companies rather than estimated
- ✅ **Cost + slippage** — `costs.py`, charged *inside* the simulator rather
  than subtracted afterwards, so the search cannot discover a strategy that
  fails to pay its own spread
- ✅ **Next-open fills** — 2026-09-15. Signals are computed from a bar's close
  and were filled at that same close, which is look-ahead. Entries now fill at
  the next open, exits at the open after the trigger
- ✅ **Gap-through-stop** — falls out of next-open fills. A stop that cannot
  rest at the broker no longer books its exit at the price that breached it;
  `gap_loss_usd` reports what the gap costs

Long-only was never a constraint to add — nothing here can short.

**What this phase does not fix.** Realistic fills make the measurement honest;
they do not make it unbiased. The missing delisted companies are still missing,
and no fill convention recovers them.

---

## Strategy Lab (new scope)

Full specification in `STRATEGY_LAB.md`.

### 08 · Genome, simulator & reward engine ✅ 100%
`genome.py`, `simulator.py`, `reward.py` all built and repeatedly corrected.
The simulator now fills at the next open, prices exits off the unfiltered
series, and reports gap-through-stop losses. Fitness scores against a
price x horizon null surface, not against zero.

Six searches produced six measurement artifacts before the engine was
trustworthy. That history is in CLAUDE.md and is the most valuable thing
this phase produced.

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

Deflated Sharpe fixed 2026-09-11 and now gives calibrated probabilities. It had
two bugs: an annualised Sharpe compared against a trade count, and a missing
standard-error scaling on the expected maximum. Verified monotonic in all three
directions — more trials lowers the probability, more Sharpe raises it, more
evidence raises it.

The ladder is now trustworthy end to end: gates calibrated so noise passes 0% of
the time, and a sealed-holdout test that gives a real probability rather than a
directional hint.

✅ `lab_dashboard.py` built 2026-09-11 — a self-contained HTML page, no server
and no dependencies. Net P&L leads every table; fitness and Sharpe are shown as
diagnostics of *why*, never as the verdict. Renders the family tree of the best
strategy, because a winner reached through a visible line of improving ancestors
is a different proposition from one that appeared fully formed from a random draw.
`promote.py`, `lab_dashboard.py`. The gauntlet from random guess to funded, plus
leaderboards and strategy family trees.

---

## Going live

### 11 · Live integration & paper trading ✅ 100%
Real money is live in one Robinhood account (~$89, five positions). The loop is
*system generates -> human places -> system reconciles*: `orders.py` writes the
morning slate, a person places it, `--record-fills` records the ACTUAL fills
including share counts, and `--reconcile` reports divergence.

Forward records now run in three places, which between them are the only
unbiased measurement this project has:

- **16 paper funds**, named by what they trade, stepped daily
- **5 bull/bear ETF switching funds**, opened 2026-09-15
- **the Claude Fund**, discretionary and paper-tracked, currently holding nothing

`fund_report.py` reports all of it every morning. See CLAUDE.md "The funds".

The two conviction paper runs stalled 2026-09-11 to 2026-09-22 because
`daily_fundamentals` stopped rebuilding; fixed 2026-09-22 and running since.

### 12 · Notifications & polish ✅ 100%
Telegram + desktop delivery via `notify.py`. The morning slate is formatted for a
phone — one order per block, green for buys, red for sells, because Telegram has
no text colour. Failures send an ALERT naming the symbol-directory step, since
that is the one whose omission is permanent.

The sell path is covered by `tests/test_sell_alert.py`, which caught that an
unescaped `<=` in a stop reason would make Telegram reject the whole message
with a 400 — the alert would have silently never arrived.


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

### Benchmark-relative scoring ✅ (all 3)
`benchmark.py` built 2026-09-11. Computes and caches the null — what buying at
random and holding the horizon actually earns in a given window, net of costs.

`reward.py` now scores **excess over that null** rather than raw P&L, and
`control.py` measures the ladder's false-positive rate by running random,
never-evolved strategies through the live gates.

Measured progression of how much noise the validation gate admits:

| Gate | Random strategies passing |
|---|---|
| net P&L > 0 (original) | **57%** |
| excess over null > 0 | 30% |
| calibrated thresholds | **0%** |

Thresholds come from the 95th percentile of what pure chance achieves — excess
≥ $12.05 and Sharpe ≥ 0.569 — not from a round number. `control.py` reads the
same config the ladder enforces, so the two cannot drift apart.

Built because a control experiment showed **52% of random, never-evolved
strategies passed the validation gate**. The cause: every score in the project
compared against zero, and buying at random was profitable in every window
because the market went up. "Net P&L > 0" was testing whether a strategy was long
in a bull market, not whether it picked well.

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

### 13 · Does anything actually make money? 🟡 in progress
The only open question left, and the one everything above exists to answer.

**What is settled, negatively:**
- The XGBoost classifier ranks better than chance (AUC 0.63, 31/31 folds) and
  still loses money net of honest fills — gross is NEGATIVE before costs.
- Long/inverse ETF switching beats random switching on every index pair and
  loses to buy-and-hold on all of them, including through a crash.
- ERX/ERY specifically has failed twice by unrelated methods.
- 0 of 20 published technical rules beat the null.
- Six Lab searches produced six measurement artifacts.

**What is open, and where to look:**
- ~~**Tight stops.**~~ **Refuted 2026-09-24.** The pre-registered sweep over
  2006-2019 found `rising_200` loses net in all 30 stop x hold cells, and tight
  stops do worse than wide for every entry rule tested.
- **Momentum-plus-pullback.** `MACD Pullback` is the best of 16 at +2.00%.
- **Forward time.** It accrues only in calendar time and cannot be rushed,
  which is why 21 funds now run daily instead of one.

**What would settle it fastest:** point-in-time delisted prices (~$270/yr).
7,062 dead companies are missing, and no amount of search fixes that.

### 14 · Robinhood Agentic autonomous execution 🟡 core built 2026-09-22
Full specification in `ROBINHOOD_AGENTIC.md`. **Core built 2026-09-22**: signal
schema, risk engine, six kill switches, broker abstraction, order state machine,
execution engine and runner, under test. Not built: the LIVE transmit path,
scheduled reconciliation, and order-state recovery on restart.

Connects the strategy engine to the Agentic account through Robinhood's official
Trading MCP (`https://agent.robinhood.com/mcp/trading`), with a deterministic
pipeline: signal -> risk engine -> order validation -> execution -> state
machine -> reconciliation. The LLM is the supervisory layer, not part of the
execution path.

**Roughly half the 25 phases already exist here.** Simulation, backtesting,
walk-forward, database, scheduling, alerting, ML and external data are built and
running; the spec was written greenfield. The genuinely new work is phases
5, 6, 7, 17, 20, 24 and 25 — kill switches, the execution engine, the order
state machine, live mode, order-state recovery, and the test suite that has to
exist before any of it runs. See the phase-by-phase audit in the spec.

Five questions are open and listed at the end of that document, including
whether to extend this project or fork a new tree, and what the system would
trade given that nothing here has yet demonstrated an edge.

### 15 · Research integrity & independent validation ✅ built 2026-09-22/24
**This is the new project direction.** Full specification, reproduced verbatim,
in `PHASE6_RESEARCH_INTEGRITY.md`. Stage-by-stage status in
`ROADMAP_INTEGRATION.md`. Built: freeze, ancestry, truth set, PIT universe, audits,
freshness gate, sealed holdout, experiment registry, random control, multiple
testing, integrity report, signal decay (§20), and on 2026-09-24 baseline
portfolios (§16, `baselines.py`), calibration metrics (§19,
`model_calibration.py`), regime analysis with rates (§21, `regimes.py`), the
TNON case study (§24), the §29 documents and the §31 report generator
(`phase6_report.py`). The stop-width experiment (§13) is COMPLETE: refuted.

31 sections covering: freezing open-ended search, removing seed contamination and
tracking strategy ancestry, an immutable versioned truth set, a point-in-time
universe, data-completeness and fundamental-availability audits, freshness as a
first-class failing metric, a documented validation firewall, a genuinely sealed
holdout, an experiment registry with pre-registration, a forward scoreboard with
time-in-test made prominent, matched-universe nulls, expanded random controls,
multiple-testing accounting, model calibration separated from trading
performance, signal-decay and regime analysis, explicit promotion rules, a TNON
case study, and a regression suite covering every historical measurement bug.

All existing systems integrate into this direction rather than continuing
alongside it.

Its stated goal is not to find a profitable strategy. It is to make a positive
result substantially harder to dismiss as an artifact.

---

## The long-term direction — Phases 6–13

**Added 2026-09-22. This is the new direction of the project and a full revamp
of its planning.** All existing systems integrate into it. Phases 6–12 are
built (status per stage in `ROADMAP_INTEGRATION.md`); Phase 13 is planned.

The numbered phases above (01–15) record what was built. These six describe
where it goes: Stockbot2000 becomes a continuously operating research
laboratory, a persistent strategy league, and a promotion pipeline — rather
than a system that searches for a good backtest.

| Phase | Name | Spec |
|---|---|---|
| 6 | Research Integrity & Independent Validation | `PHASE6_RESEARCH_INTEGRITY.md` |
| 7 | Continuous Strategy Laboratory & Paper Trading League | `PHASES_7_11_STRATEGY_LEAGUE.md` |
| 8 | Continuous Strategy Discovery & Real-World Strategy Library | `PHASES_7_11_STRATEGY_LEAGUE.md` |
| 9 | Fundamental Value Intelligence Engine | `PHASES_7_11_STRATEGY_LEAGUE.md` |
| 10 | Live Capital Allocation & Strategy Promotion | `PHASES_7_11_STRATEGY_LEAGUE.md` |
| 11 | Continuous Research Loop | `PHASES_7_11_STRATEGY_LEAGUE.md` |
| 12 | Crypto Fund — and Stage K, crypto earns a slot (planned) | `PHASE12_CRYPTO_FUND.md`, `ROADMAP_INTEGRATION.md` Stage K |
| 13 | Strategy Factory 2.0 + Data Integrity + Continuous Discovery | `PHASE13_STRATEGY_FACTORY.md` |
| L | Published signals as a strategy source (planned) | `ROADMAP_INTEGRATION.md` Stage L |
| M | Realistic dead companies — synthetic generator v5 (planned) | `ROADMAP_INTEGRATION.md` Stage M |

Dependencies, module reuse, architectural gaps, schema changes, risks, minimum
infrastructure and the proposed implementation order are in
**`ROADMAP_INTEGRATION.md`**.

The shape it is heading for:

```text
Thousands of ideas → rigorous backtesting → hundreds of paper strategies
→ continuously ranked strategy league → risk-filtered top 5
→ Robinhood Agentic → live results feed back into the league → repeat forever

SEC filings → fundamental intelligence → intrinsic-value analysis
→ long-term value candidates → a separate Value Fund
```

Two funds, two philosophies, one research infrastructure: a **Tactical Fund** of
continuously selected strategies and a **Value Fund** of long-term fundamentally
selected companies, independently measurable.

### Phase 13 · Strategy Factory 2.0 🟡 BUILDING from 2026-09-24
Full specification, verbatim, in `PHASE13_STRATEGY_FACTORY.md`; integration,
reuse map and the 15-step status table in `ROADMAP_INTEGRATION.md` (Stage H).

**The shift:** from a backtesting engine that is good at rejecting ideas to a
continuous research laboratory that decides *what to test next*. Breadth of
economically motivated hypotheses over more brute-force search; the
evolutionary search stays frozen.

What it adds, over the existing system rather than replacing it:

- **Strategy Factory** — classical, combination and fundamental generators
  from controlled templates; every idea becomes a versioned Strategy object
- **Accounting fix first** — one gross / costs / net model for every fund,
  opening costs charged, reconciliation to the cent, affected history restated
- **FINSABER** — an S&P 500 dataset including delisted names, 2000–2024, as an
  independent *validation* source behind a data-provider interface; never the
  master database
- **Survivorship tags** — SAFE / ADJUSTED / LIMITED / UNKNOWN per strategy
- **Nine leagues** — tactical, momentum, mean reversion, fundamental, value,
  ETF/macro, ML, event, crypto — each with its own horizon; the Value Fund gets
  long-horizon gates instead of the 60-mark tactical rule
- **Continuous discovery** — research queue, experiment budgets, family
  allocation, failed-strategy recycling as new versions, a priority engine
- **Robustness** — Monte Carlo, parameter/date/universe perturbation, cost and
  slippage stress, regime breakdown
- **Promotion to live candidate** — family-concentration limits so five
  Rising 200 variants count as one bet; orders only through the central risk
  and execution layer
- **Daily factory report and a global scoreboard** — gross, costs and net on
  every line

Six decisions are listed in `ROADMAP_INTEGRATION.md` Stage H, each with the
default the build follows unless changed.

### Addendum A · Autonomous 5-slot trading system 🟡 BUILDING from 2026-09-24
The product definition above, as a build: a **trading engine** fed by the
Phase 13 research engine. Spec verbatim in `ADDENDUM_A_AUTONOMOUS_5_SLOT.md`;
reuse map, the 14 steps (I1–I14), sequencing with Phase 13 and seven decisions
in `ROADMAP_INTEGRATION.md`, Stage I.

- **Slots** — five ~$20 slots, each held by a distinct eligible strategy; a slot
  with no qualified strategy stays in cash
- **Replacement engine** — centralized, configurable evidence thresholds with
  hysteresis, so a stronger strategy displaces the weakest without churn
- **P&L-first leaderboard** — gross, costs and net on every line
- **Continuous risk** — intraday position monitor, mandatory stop plan per
  strategy, risk exits override strategy signals
- **Automatic execution** — the LIVE path through the existing risk engine,
  order state machine and broker adapter, with confirmation, retry and
  recovery on restart
- **Kill switches** — global and per-strategy: stop orders, cancel, emergency
  exit, freeze promotions, alert
- **Daily five-slot reassessment** plus separate always-on services for
  trading, backtesting, paper, ingestion, ranking and discovery

### Addendum B · Final build directive ✅ in force 2026-09-24
Authorizes construction of Phase 13 then Addendum A in roadmap order,
resolves their open decisions (table at the end of `ROADMAP_INTEGRATION.md`),
and fixes the definition of done: the full discover → trade → replace loop
running autonomously, with real-money activation the user's step.

### Addendum C (revision 2) · Survivorship-bias-free universe reconstruction 📋 PLANNED 2026-09-24 — awaiting confirmation
Spec verbatim in `ADDENDUM_C_SYNTHETIC_DELISTING.md`. Revision 1 wrongly
narrowed it to S&P 500 delisting returns; the scope is the full US equity
universe, including the ~7,000 delisted companies with no free prices.

- **Layer A** rebuilds which companies existed, from EDGAR, Alpha Vantage,
  Internet Archive snapshots, FinanceDatabase and FINSABER, with per-field
  provenance.
- **Layer B** generates cohort-conditioned synthetic price paths for the
  missing companies, every row tagged, real rows never touched.

Synthetic data is for bias correction, not a substitute for real data.

**Feasibility, stated plainly:** free data supports **1996–2024**; before 1996
EDGAR coverage is too thin and the universe would be mostly imputed. The
cohorts that matter most, small failing companies, have the least real data to
calibrate from. The existing generator is distinguishable from real data at
AUC 0.978, so synthetic rows stay out of discovery and promotion until a new
generator passes that test. Five stages and eight questions are in
`ROADMAP_INTEGRATION.md`, Stage J.
