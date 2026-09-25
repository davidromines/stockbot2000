# Roadmap integration — Phases 6–13

The deliverable required by `PHASES_7_11_STRATEGY_LEAGUE.md`. Ten items, in the
order that document asks for them.

Written 2026-09-22 as the analysis that preceded implementation. Stages A–G have
since been built; the status tables in §10 are current. Stages H (Phase 13),
I (Addendum A, SIMULATION/SHADOW) and J (Addendum C) were built 2026-09-24.
Stages K (crypto earns a slot), L (published signals) and M (generator v5) are planned.

---

## 1. The project plan, updated

Eight phases now define the direction. Phases 1–5 (data, pipeline, environment,
smoke test, migration) and the numbered phases 06–15 already in `ROADMAP.md`
describe what was built; these describe where it goes.

| Phase | Name | Status |
|---|---|---|
| 6 | Research Integrity & Independent Validation | **built 2026-09-24** — Stage A; §16, §19, §21, §24, §29, §31 finished 2026-09-24. `phase6_report.py` writes the §31 report and §30 checklist |
| 7 | Continuous Strategy Laboratory & Paper Trading League | **built** — Stage B |
| 8 | Continuous Strategy Discovery & Real-World Strategy Library | **built** — Stage C |
| 9 | Fundamental Value Intelligence Engine | **built** — Stage D |
| 10 | Live Capital Allocation & Strategy Promotion | **built** — Stage E |
| 11 | Continuous Research Loop | **built** — Stage F |
| 12 | Crypto Fund | **built** — Stage G, `PHASE12_CRYPTO_FUND.md` |
| 13 | Strategy Factory 2.0 + Data Integrity + Continuous Discovery | **built 2026-09-24 (H1-H15), in daily.sh** — Stage H, `PHASE13_STRATEGY_FACTORY.md` |
| A | **Addendum A — Autonomous 5-Slot Trading System** (product definition; overrides ambiguity) | **I1-I14 built 2026-09-24; LIVE armed by the owner 2026-09-24 15:39 UTC (real orders, Agentic account)** — Stage I, `ADDENDUM_A_AUTONOMOUS_5_SLOT.md` |
| B | **Addendum B — Final Build Directive** (resolves the Stage H/I decisions; authorizes the build) | **in force 2026-09-24** — `ADDENDUM_B_FINAL_BUILD_DIRECTIVE.md` |
| C | **Addendum C (rev 2) — Survivorship-bias-free universe reconstruction** | **Stages 1-5 built 2026-09-24 on the recommended answers; generator fails the realism gate (AUC 0.768; v4 written 2026-09-24, not yet scored), so retest-only** — Stage J, `ADDENDUM_C_SYNTHETIC_DELISTING.md` |
| K | **Crypto earns a slot** (Stage K) | **planned 2026-09-24** — Robinhood crypto spread measured at ~1.9% round trip, so grid-DCA cannot pass; low-turnover strategies, crypto execution path, 24/7 stop monitoring. Arming (`allow_crypto`) is the owner's step |
| L | **Published signals as a strategy source** (Stage L) | **planned 2026-09-24** — Open Source Asset Pricing (212 signals, survivorship-free CRSP returns) as the strategy database, Global Factor Data (93 countries) as the cross-check; trader.dev's 797k leaderboard not used |
| M | **Realistic dead companies — generator v5** (Stage M) | **planned 2026-09-24** — real failure histories (bankruptcy Q tickers, FINSABER, our own delisted names) as templates for synthetic failures; realism graded per exit type |
| D | **Addendum D — Live Growth & Continuous Improvement** (Stage N) | **entered 2026-09-25, not yet started; build order is the spec's own (§20)** — keep LIVE running; Live Control Center first, then live reliability, leaderboard, replacement visibility, decay monitoring, live->research feedback, continuous discovery, K/L/M, scaling. `ADDENDUM_D_LIVE_GROWTH.md` |

---

## 2. Dependencies between Phase 6 and Phases 7–11

**Phase 6 is not optional groundwork. It is load-bearing for everything after
it**, because Phases 7–11 all multiply the number of results the system
produces, and the project's own record is that its results have mostly been
artifacts. Building a league on an uncontrolled research process would
industrialise the error rather than the discovery.

| Phase 6 item | Blocks | Why |
|---|---|---|
| §2 strategy ancestry, `seed_mode` | **7, 8, 11** | A league ranks strategies. Without ancestry, a seeded rule and its 400 descendants occupy the leaderboard as if they were 401 independent findings. This has already happened once. |
| §4 truth set, §5 point-in-time universe | **7, 8, 9, 10** | Every backtest, paper fund and valuation in the later phases reads market data. If the dataset is mutable or has look-ahead, every downstream number inherits it. |
| §7 fundamental availability dates | **9** | The Fundamental Value Engine is *entirely* a point-in-time problem. Phase 9 cannot start before this. |
| §9 validation firewall, §10 sealed holdout | **7, 10** | Promotion decisions are selection. Selection that can see holdout or forward results is the leakage the firewall exists to stop. |
| §11–12 experiment registry, pre-registration | **8** | The strategy library is a large set of published hypotheses. Testing hundreds without pre-registration is researcher degrees of freedom at scale. |
| §17 random control, §16 matched-universe null | **7** | A leaderboard is meaningless without knowing how high random strategies climb in the same pipeline. |
| §18 multiple-testing accounting | **7, 8, 11** | The plan states a leaderboard must never be read independently of the number of strategies tested. That counter has to exist first. |
| §25 regression suite | **all** | Each later phase adds surface area. Without the bug suite, a fixed defect can silently return in new code. |
| §1 `SEARCH_MODE=FROZEN` | **8** | Phase 8 *restarts* generation deliberately, through a governed pipeline. Freezing first is what makes the restart a controlled experiment rather than a continuation. |

**Ordering consequence:** Phase 7 cannot begin until Phase 6 §2, §4, §5, §9,
§10, §17, §18 and §25 exist. See item 9.

---

## 3. Existing modules that will be reused

Most of the machinery exists. The gap is the layer connecting it.

### Reused largely as-is
| Module | Role in the new phases |
|---|---|
| `simulator.py` | The backtest engine for every strategy in the league. Already has next-open fills and unfiltered exit pricing. |
| `benchmark.py` | **Is** the matched-universe null Phase 7 §16 requires — a surface over entry price × holding period. The hard part is built. |
| `costs.py` | Keeps transaction costs *inside* the competition, which Phase 11 explicitly requires. |
| `control.py` | The random control Phase 6 §17 expands. |
| `storage.py` | Owns the database; all new tables go through it. |
| `killswitch.py`, `risk_engine.py` | Phase 10's risk layer already exists and is tested. |
| `signals.py`, `execution.py`, `broker.py` | Phase 10's "strategy layer never places arbitrary orders" is already the architecture. |
| `backup.py` | Forward records are the league's permanent memory; they are already backed up and restore-verified. |

### Reused as a foundation, needing extension
| Module | Extension needed |
|---|---|
| `paper_trading.py` | Phase 7's arena. Currently 16 funds; must scale to hundreds or thousands without mixing results. |
| `pair_funds.py` | Its **replay-from-inception** design is the right pattern for the arena — idempotent, self-healing on a missed day. Generalise it. |
| `ledger.py`, `promote.py` | Strategy identity, the six-stage ladder and deflated Sharpe exist. Needs lifecycle states, versioning and demotion. |
| `genome.py`, `evolve.py` | The machine-idea source in Phase 8's factory. |
| `conviction.py`, `buffett.py`, `pead.py` | Already implement value, quality, Buffett/QMJ and earnings drift — the first entries in Phase 8's library, and already size-bucketed. |
| `sec_fundamentals.py`, `value_metrics.py`, `fundamental_features.py` | Phase 9's foundation. ~40 metrics per filing and a point-in-time lag already exist. |
| `edgar_registry.py`, `edgar_events.py` | EDGAR ingestion and 8-K taxonomy for Phase 9. |
| `fund_report.py` | The embryo of the Phase 7 scoreboard; currently a text report, not a persistent ranked history. |
| `daily.sh` | Phase 11's loop. Already 8 stages on cron. |

---

## 4. Architectural gaps

Ordered by how much later work they block.

1. **No strategy identity or versioning.** `strategies` stores genomes but has no
   version, family, hypothesis, source, ancestry or lifecycle state. Phase 7's
   "never overwrite a version" rule has nothing to attach to. **Largest gap.**
2. **No correlation measurement between strategies.** The "top 5 after risk and
   correlation constraints" rule — the central architectural change in this plan
   — cannot be implemented at all today.
3. **No degradation tracking.** Backtest, validation, paper and live results are
   never compared for the same strategy, so the system cannot learn how
   predictive its own backtests are.
4. **Paper arena does not scale.** `paper_trading.py --step` already takes
   minutes for 16 funds. Hundreds or thousands needs a different execution model.
5. **No capital allocation engine.** Nothing sizes across strategies.
6. **No persistent leaderboard with history.** Rankings are recomputed and
   discarded; Phase 7 requires current *and* complete historical ranking.
7. **No industry classification.** Phase 9's industry-aware valuation requires
   SIC/GICS mapping that does not exist.
8. **Fundamental facts lack full provenance.** `fundamentals` has `filed` but not
   accession number, acceptance datetime, amendment status or source-filing
   reference. Phase 9 §"critical point-in-time requirement" needs all of them.
9. **No intrinsic-value models.** DCF, earnings, FCF, relative and asset-based
   valuation are all absent.
10. **No strategy library schema.** Nothing records a published strategy's
    origin, author, original universe, known limitations or Stockbot
    interpretation.

---

## 5. Database and schema changes required

New tables, grouped by phase. All in `market_data.db` via `storage.py`.

### Phase 7 — the league
```text
strategy_versions     immutable; strategy_id, version, hypothesis, family,
                      source, entry/exit/sizing rules, params, code_version,
                      data_version, created_at, parent_version
strategy_lifecycle    state transitions with timestamp and reason
                      (DISCOVERED … RETIRED)
strategy_scores       time series: strategy_id, version, as_of, every metric,
                      rank — never overwritten
strategy_correlations pairwise return correlation, as_of
strategy_degradation  backtest / validation / paper / live returns and the
                      three degradation ratios
arena_portfolios      per-strategy virtual portfolio (extends paper_runs)
arena_equity          daily equity curve per strategy
arena_trades          per-strategy fills, costs, slippage, turnover
```

### Phase 8 — the library
```text
strategy_library      name, author, source, publication, original hypothesis,
                      original universe, original period, original metrics,
                      required data, interpretation, known biases, limitations,
                      validation status
library_implementations  library_id → strategy_version_id
```

### Phase 9 — fundamentals
```text
sec_facts_pit         company, CIK, ticker, metric, value, fiscal period,
                      filing date, accepted datetime, accession, amendment
                      status, source filing, provenance
industry_map          ticker → SIC/GICS, effective dates
intrinsic_values      method (DCF | earnings | FCF | relative | asset),
                      inputs, assumptions, output, as_of
value_scores          per-component scores + margin of safety + explanation
value_watchlist       ranked long-term candidates
```

### Phase 10 — capital
```text
capital_allocations   strategy_version_id, weight, capital, effective_from
promotion_decisions   decision, reasons, metrics at decision time, actor
live_strategy_roster  current roster with entry/exit timestamps
```

### Phase 6 prerequisites (already specified there)
```text
truth_set + manifest + hash, experiments registry, ancestry columns on
strategies, freshness_log
```

**Migration note:** existing `paper_runs` / `paper_equity` hold 14 days of
irreplaceable forward record. They must be migrated into the arena tables, not
replaced. `paper_runs` stores each genome inline as JSON — that denormalisation
already survived one database corruption and should be preserved in the new
schema.

---

## 6. Components that must remain independent

1. **Research Factory / Strategy League / Capital Deployment.** The plan says do
   not collapse these; the practical rule is that the league must not be able to
   call the broker, and the factory must not be able to write scores.
2. **Tactical Fund vs Value Fund.** Different philosophies, different horizons,
   independently measurable. Sharing infrastructure is fine; sharing a P&L line
   is not.
3. **Truth set from the backtest engine.** Phase 6 §4 is explicit: the backtest
   engine does not build the truth set. Enforce by permissions, not discipline.
4. **Sealed holdout from everything except `evaluate_holdout.py`.**
5. **`config/risk.yaml` from strategy configuration.** Already separate; a
   strategy edit must never widen a risk limit.
6. **Scoring formula from the scoreboard.** Phase 7 says do not fix the weights
   yet — so the formula must be pluggable and versioned, and scores must record
   which formula produced them.
7. **The random control from the strategies it calibrates.** It must run the
   same pipeline without entering the league.

---

## 7. Risks of continuously promoting strategies

1. **Continuous selection is continuous multiple testing.** Picking the top 5
   from a growing pool, repeatedly, is a search — and its false-discovery rate
   compounds with every re-ranking. The multiple-testing counter must include
   promotion decisions, not just backtests.
2. **Regime chasing.** Ranking on trailing performance systematically promotes
   whatever suited the last regime, at the moment it is most likely to mean-
   revert. Phase 6 §21 regime analysis is the mitigation.
3. **Churn costs are real and asymmetric.** Demoting and promoting means
   liquidating and rebuilding positions. On a $100 account, a full roster change
   could cost more in spread than the ranking difference that triggered it.
4. **Correlation clustering.** The central risk the plan already identifies; it
   needs a measured correlation matrix, not an assumption.
5. **Survivorship inside the league.** If retired strategies are excluded from
   aggregate statistics, the league's own track record becomes biased — the same
   error the project spent weeks removing from its market data.
6. **Short-sample whiplash.** With 14-day forward records, ranking is mostly
   noise. The minimum-forward-duration gate is what stops the roster oscillating.
7. **Feedback contamination.** Live results feeding the scoreboard which feeds
   promotion means the system trains on its own output. That loop needs an
   explicit firewall or it is a slow path back to overfitting.

---

## 8. Risks of raw profitability as the only ranking metric

1. **Five copies of one trade** — the plan's own reason for the change.
2. **It rewards volatility and leverage**, which raise expected return without
   raising skill.
3. **It rewards luck at short horizons.** Over 14 days, the highest return in a
   pool of 100 strategies is a near-certain artifact of variance.
4. **It ignores the path.** A strategy that made 10% via a 40% drawdown is not
   equivalent to one that made 8% smoothly, and only the second is survivable.
5. **It ignores turnover and costs** — and this project has already measured
   costs taking 87% of gross profit.
6. **It ignores capacity and liquidity.** The highest-returning strategy is
   often the one trading names that cannot absorb capital. **TNON is the
   worked example.**
7. **It ignores degradation.** A strategy whose paper return is far below its
   backtest is showing the signature of overfitting, and raw profit cannot see
   it.
8. **It has no null.** Profit without a matched benchmark says only that the
   market rose — the error that produced this project's first 66 false
   survivors.

---

## 9. Minimum infrastructure before Phase 7 can begin

**From Phase 6 — all mandatory:**

- §2 strategy ancestry and `seed_mode`, with seed descendants distinguishable
- §4 truth set: immutable, versioned, hashed
- §5 point-in-time universe (`get_available_securities(date)`)
- §9 validation firewall, documented
- §10 sealed holdout, enforced by permissions
- §17 expanded random control — the calibration a leaderboard is read against
- §18 multiple-testing accounting
- §25 regression suite for all eleven historical bug classes

**New, specific to Phase 7:**

- Strategy identity and immutable versioning schema
- Lifecycle state machine with recorded transitions
- Arena that scales to hundreds of strategies
- Degradation tracking across backtest → validation → paper → live
- Pairwise correlation measurement
- Persistent scoreboard with historical ranks and a pluggable, versioned formula

**Already in place and sufficient:** simulator, null surface, cost model, risk
engine, kill switches, execution engine, backup.

---

## 10. Proposed implementation order

Sequenced so each step is independently testable and nothing depends on
something unbuilt. Phase numbers are the plan's; the order within them is the
recommendation.

**Stage A — integrity foundation (Phase 6)** — status as of 2026-09-22

| | item | state |
|---:|---|---|
| 1 | Regression suite (§25) | **done** — 18 files, `./run_tests.sh` is the gate |
| 2 | Ancestry + `seed_mode` (§2) | **done** — `ancestry.py`, 1.03M classified |
| 2b | Seed-free control run (§3) | **registered and running** — `experiments/seed_free_search/` |
| 3 | `SEARCH_MODE=FROZEN` (§1) | **done** — frozen 2026-09-22 |
| 4 | Truth set (§4), PIT universe (§5) | **done** — `truth_v1`, `pit_universe.py` |
| 5 | Completeness + availability audits (§6, §7) | **done** |
| 6 | Freshness as a failing metric (§8) | **done** |
| 7 | Validation firewall (§9), sealed holdout (§10) | **done** — seal carved out 2026-09-22 |
| 8 | Experiment registry (§11, §12) | **done** — `experiment_registry.py` |
| 9 | Random control (§17), multiple testing (§18) | **done** — `random_control.py`, `multiple_testing.py` |
| 10 | Research integrity report (§26) | **done** — regenerated daily |
| 10a | Baseline portfolios (§16) | **done 2026-09-24** — `baselines.py`: every forward fund beside cash, SPY, its index ETF (fixed rule), the matched-universe null and 1,000 same-size random portfolios (pair funds: random switching at their own count), on its own window and capital |
| 10b | Model search separation (§19) | **done 2026-09-24** — `model_calibration.py`: AUC, Brier / log loss vs base rate, reliability + ECE, precision and gross/net return by fixed 10% band. Run on the VM to get the numbers |
| 10c | Regime analysis (§21) | **done 2026-09-24** — `regimes.py`: rate regimes (FRED DGS3MO, fixed 2.0% line) added to robustness's SPY regimes; `--forward` breaks every forward fund's daily P&L down by regime. Definitions fixed in `config.yaml` `regimes:` |
| 10d | TNON case study (§24) | **done 2026-09-24** — `case_studies/TNON.md`; `tests/regression/test_tnon.py` pins every route an equivalent name could take (no cap, sourced $3.5M cap, fallback failed or stale) and that a known $5B cap still passes |
| 10e | Documentation (§29) | **done 2026-09-24** — `docs/RESEARCH_METHODOLOGY.md`, `docs/EXPERIMENT_PROTOCOL.md` added (`VALIDATION_FIREWALL.md`, `DATA_DICTIONARY.md` existed); README, ARCHITECTURE, PROJECT_STATUS, CHANGELOG updated |
| 10f | Final phase report (§31) | **done 2026-09-24** — `phase6_report.py` -> `reports/phase6_report.md`, built from the database and a test run, with the §30 checklist mapped to evidence. Run it on the VM |

Stage A is complete (2026-09-24). The seed-free comparison ran both arms
(2026-09-22) with n=1 per arm, so its fitness difference is not separable
from run-to-run variance; that caveat is recorded with the result. Nothing in Stage A produced a positive
result about any strategy, which is the expected outcome: it is scaffolding
for honest measurement, not a source of edge.

**Stage B — the league (Phase 7)** — status as of 2026-09-22

| | item | state |
|---:|---|---|
| 11 | Strategy identity, immutable versioning | **done** — `league.py` |
| 12 | Lifecycle state machine | **done** — 10 states, whitelisted transitions |
| 13 | Migrate 16 paper + 5 pair funds | **done** — 21 in, no data moved |
| 14 | Scale the arena | **measured, no work needed** — see below |
| 15 | Degradation tracking | **done** — `degradation.py`, 11 of 21 paired |
| 16 | Correlation measurement | **done** — `eligibility.matrix()` |
| 17 | Persistent scoreboard, pluggable formula | **done** — `scoreboard.py` |
| 18 | Eligibility rules, no promotion to live | **done** — `eligibility.py` |

**Item 14 was measured rather than built.** The spec asks for "hundreds or
thousands of simultaneously tracked paper strategies without mixing their
results." Measured on this VM:

| | |
|---|---:|
| panel load, fixed and shared by every run | 13.3s |
| marginal cost per genome strategy | 0.07s |
| projected cost at 1,000 strategies | ~1.4 min |
| conviction fundamental panel, cached after first call | 1.1s -> 0.2s |

The expensive work is already loaded once and shared by `_recent_frame`, and
results are scoped by `run_id` so they cannot mix. A `--step` that appeared to
take four minutes was competing with two evolutionary search arms for three
cores, not hitting a scaling limit. **No refactor was written, because the
measurement said none was needed** — building an arena scaled for thousands
before anything has earned sixty equity marks would be machinery serving a
problem nobody has.

**What Stage B does not do.** Nothing is promoted, nothing is ranked, and
nothing is eligible. The scoreboard reports 0 of 21 rankable and eligibility
reports 0 of 21 eligible, because every fund holds a median of 7 equity marks
against a floor of 60 and every one of the 210 strategy pairs shares too few
marks for a correlation to mean anything. That is the honest state of a league
whose oldest member has three weeks of history — the machinery is in place and
accruing, and only calendar time populates it.

**Stage C — supply (Phase 8)** — status as of 2026-09-22

| | item | state |
|---:|---|---|
| 19 | `strategy_library` schema | **done** — provenance fields required, not optional |
| 20 | Import existing strategies | **done** — 28 entries with measured evidence |
| 21 | Value / quality / momentum families | **done** — pre-registered as hypotheses |
| 22 | Combination families | **done** — value+momentum, value+quality |
| 23 | Governed generation | **built, and it refuses every run today** |

35 library entries: 16 REFUTED, 5 INCONCLUSIVE, 14 HYPOTHESIS, **0 SUPPORTED**.
Nothing here has cleared a forward test, and a citation is recorded as
provenance rather than as evidence.

**A distinction item 20 forced.** Five of the twenty published rules say
outright that their encoding is not the rule as published — "an adaptation, not
the strategy", "a z-score break and an N-day-high break are not the same
event". Their encodings failed here, which says little about Jegadeesh & Titman
or Donchian. Only faithful encodings may be marked REFUTED; the five are
INCONCLUSIVE with the deviation named. "Jegadeesh & Titman: REFUTED" is a far
larger claim than anything measured here, and it is the version someone would
remember.

**Item 23 built the gates, not the unfreeze.** `factory.authorize()` requires a
registered experiment, `seed_mode: NONE`, a declared trial budget priced against
the ledger, explicit acknowledgement of the freeze, and ancestry recording. It
cannot write config, cannot set `search.mode`, and cannot register an experiment
to satisfy its own first gate. **Search remains FROZEN** — lifting it is a human
edit to `config.yaml`, deliberately outside this code.

**Stage D — fundamentals (Phase 9)** — status as of 2026-09-22

| | item | state |
|---:|---|---|
| 24 | `sec_facts_pit` with full provenance | **done** — `pit_backfill.py`, `pit_facts.py` |
| 25 | Industry classification | **done** — `industry.py`, point-in-time SIC |
| 26 | Financial statement analysis engine | **done** — `statements.py` |
| 27 | Valuation engine, industry-aware | **done** — `valuation.py` |
| 28 | Intrinsic-value models | **done** — `intrinsic.py` |
| 29 | Value score and watchlist (experiment) | **done** — `value_score.py`, registered |
| 30 | Value Fund architecture, paper only | **done 2026-09-23** — `value_fund.py`, quarterly review, daily mark |

**Statement coverage is uneven and that is a data fact, not a bug.** Measured
across 400 companies:

| field | coverage |
|---|---:|
| assets / equity / book value | ~98% |
| net income | 93% |
| revenue | 75% |
| EBITDA | 58% |
| **debt** | **38%** |
| debt/EBITDA | 26% |

**Debt at 38% is the binding constraint on item 27.** Many filers do not tag
`LongTermDebtNoncurrent` or `ShortTermBorrowings` in every filing, so EV-based
multiples — EV/EBITDA, EV/EBIT, EV/Sales — are computable for a minority of the
universe. A valuation engine that silently treats missing debt as zero would
report every such company as having no leverage and an artificially low
enterprise value, which is the most flattering possible error. `statements.py`
returns `None` instead, and item 27 carries that through rather than defaulting
it.

**Item 28 makes a DCF announce how much of itself is assumption.** The
terminal-value share is reported every time and flagged above 75%; sensitivity
is returned with every valuation rather than on request; and refusal is the
expected outcome — a DCF on sign-changing cash flow values the assumption that
it turns around, not the business. Apple spans **$81 to $267** across plausible
discount and terminal-growth inputs (3.3x), and its four methods span **32x**,
which is the point: disagreement between independent methods says at least one
set of assumptions is wrong, and no single method can tell you that.

**Item 27 turned the coverage gap into a refusal.** Market-wide EV rankings are
refused outright rather than warned about, EV multiples are excluded for
financials where debt is inventory, and coverage is reported alongside every
rank. The measured bias that forced this: EV/EBITDA-computable companies have a
median market cap of **$2.20B against $0.88B** for the rest, with coverage
running 7.5% (finance) to 53.8% (wholesale).
27. Valuation engine, industry-aware
28. Intrinsic-value models
29. Value score and watchlist — **as an experiment, formula not fixed**
30. Value Fund architecture, paper only

**Stage E — capital (Phase 10)** — done 2026-09-23

| | item | state |
|---:|---|---|
| 31 | Promotion policy | **done** — `promotion_policy.py`, two gates |
| 32 | Capital allocation engine | **done** — `allocation.py`, 3 schemes |
| 33 | Roster management and demotion | **done** — `roster.py` |
| 34 | Wire to execution — not automatic | **done** — `live_pipeline.py` stops at order validation |

**Stage F — the loop (Phase 11)** — done 2026-09-23

| | item | state |
|---:|---|---|
| 35 | Full research loop in `daily.sh` | **done** — stop conditions, roster plan, live slate, compute report |
| 36 | Automatic stop conditions (§27) | **done** — `stop_conditions.py` |
| 37 | Compute allocation by priority (§28) | **done** — `compute_priority.py` |

**What the system says today, having been asked properly:**

| question | answer |
|---|---|
| Should the search run? | **DO NOT SEARCH — COLLECT MORE FORWARD DATA** |
| Is promotion machinery ready? | **NOT READY** — 4 of 15 prerequisites verified |
| How many strategies are eligible? | **0 of 21** |
| What is on the live slate? | **NO ORDERS**, with three named blockers |

Every stage of the roadmap is built. None of it has produced an edge, and each
component says so in its own output rather than leaving the reader to infer it.

**Stage G — crypto (Phase 12)** — added 2026-09-23

| | item | state |
|---:|---|---|
| 38 | Crypto market data into its own table | **done** — `crypto_data.py`, 171,654 hourly bars, listing status recorded |
| 39 | Decide the session and fill convention explicitly | **done** — a bar is a session; fill at the next bar's open |
| 40 | Crypto paper fund, separate from the equity league | **done 2026-09-23** — `crypto_fund.py`, one engine with the backtest, forward-only |
| 41 | Crypto strategies via the research library | **done** — `crypto_grid.py`; grid-DCA 0 of 10 beat the null after fees |
| 42 | Crypto order slate — human places | **done 2026-09-23** — `crypto_orders.py`, crypto adapters, crypto risk floors |

Spec in `docs/PHASE12_CRYPTO_FUND.md`. Execution runs through the existing
risk engine, kill switches and order state machine, with a crypto broker
adapter behind `BrokerInterface`; live transmission is armed by the operator.

Item 39 blocks everything after it. Crypto has no close and no next open, so
the next-open fill convention cannot be inherited unmodified — and getting a
fill convention wrong is the defect that cost this project its largest single
correction.

**Two ordering constraints worth stating plainly.** Stage A item 1 comes first
because every later stage adds surface area to a codebase with a documented
history of silent measurement defects. And Stage B item 13 comes before item 14
because the existing forward record is the most valuable and least replaceable
data in the project — migrate it before changing the thing that writes it.

---

**Stage H — Strategy Factory 2.0 (Phase 13)** — entered 2026-09-24, **building** (Addendum B)

Spec in `docs/PHASE13_STRATEGY_FACTORY.md`, verbatim. An orchestration and
expansion layer over what exists; §3 of the spec forbids rewriting working
components. Build order is the spec's §39, unchanged.

*Reuse map (preview of Step 1 — the step itself re-verifies it against the code)*

| spec concept | existing module(s) | Phase 13 work |
|---|---|---|
| Strategy object, versioning | `league.py` (identity/version split, `definition_hash`, append-only log) | extend to the §13 field list; do not fork a second identity model |
| Lifecycle | `league.py` (10 states) | adopt §14's exact states — see decision 1 |
| Backtest | `simulator.py`, `backtest.py`, `benchmark.py`, `costs.py` | reuse as-is; generators emit genomes the simulator already runs |
| Validation | `promote.py`, `evaluate_holdout.py`, `random_control.py`, `multiple_testing.py` | wire into the factory pipeline |
| Robustness | `stress_test.py`, `bias_exposure.py` (partial) | new `robustness.py` for the §28 perturbations |
| Paper trading | `paper_trading.py`, `pair_funds.py`, `value_fund.py`, `crypto_fund.py` | auto-enrol from the factory; one accounting model (Step 2) |
| League / ranking | `scoreboard.py`, `degradation.py`, `eligibility.py` | split into the nine §16 leagues with per-league horizons |
| Research library | `strategy_library.py`, `factory.py` | add the §7 fields; entries generate Strategy objects |
| Fundamentals | `pit_facts.py`, `statements.py`, `valuation.py`, `intrinsic.py`, `value_score.py`, `conviction.py` | fundamental generators (§5) on top of these |
| Data | `storage.py`, `backfill.py`, `pit_universe.py`, `delistings.py` | provider interface (§10) + FINSABER provider |
| Promotion / allocation | `promotion_policy.py`, `allocation.py`, `roster.py` | add the family-concentration limit (§18) |
| Live execution | `signals.py`, `risk_engine.py`, `killswitch.py`, `broker.py`, `execution.py`, `live_pipeline.py` | connect LIVE_CANDIDATE output; orders only via the central risk layer |
| Reporting | `fund_report.py`, `build_dashboard.py`, `notify.py` | daily factory report, global scoreboard, data-quality report |

*Implementation order and status*

| step | item | spec § | state |
|---:|---|---|---|
| H1 | Audit existing architecture, document the mapping | §39.1 | **done** 2026-09-24 |
| H2 | Authoritative gross / costs / net accounting; reconciliation; restatement | §12, §34, §35 | **done** 2026-09-24 |
| H3 | Strategy object model, lifecycle, families, generators | §4, §13–15 | **done** 2026-09-24 |
| H4 | Research library schema + automatic strategy generation | §7, §32 | **done** 2026-09-24 |
| H5 | Fundamental strategy factory (PIT) incl. Value family | §5, §6, §33 | **done** 2026-09-24 |
| H6 | FINSABER import as a validation dataset + provider interface | §8–10 | **done** 2026-09-24 |
| H7 | Cross-dataset validation + discrepancy report; survivorship tags | §11, §29 | **done** 2026-09-24 |
| H8 | Nine strategy leagues with horizon-appropriate gates | §16, §33 | **done** 2026-09-24 |
| H9 | Continuous discovery: queue, budgets, family allocation, recycling, priority | §22–25 | **done** 2026-09-24 |
| H10 | Robustness: Monte Carlo, perturbations, cost/slippage stress, regimes | §28 | **done** 2026-09-24 |
| H11 | Automatic paper-trading enrolment with the §26 record | §26, §27 | **done** 2026-09-24 |
| H12 | Promotion integration: factory → validation → paper → league → risk → candidate | §18, §37 | **done** 2026-09-24 |
| H13 | Live allocation into the existing execution/risk layer | §13 (spec step 13) | **done** 2026-09-24 |
| H14 | Daily factory report, global scoreboard, data-quality + coverage reports | §17, §36 | **done** 2026-09-24 |
| H15 | End-to-end test on a few representative strategies | §39.15, §40 | **done** 2026-09-24 `tests/e2e/e2e_factory.py` |

*Phase 6 items this absorbs.* Phase 6 §16 (baseline portfolios) is covered by
§30 here; §19 (XGBoost calibration) by §20; §21 (regime analysis) by H10. The
Phase 6 remainder was finished on 2026-09-24 as items 10a-10f of Stage A.

*Decisions to confirm before building* — each has a default the build will
follow if nothing else is said:

1. **Lifecycle names.** §14 prescribes an exact 9 + 3 state machine;
   `league.py` already has 10 states with different names (BACKTESTING,
   VALIDATING, ELIGIBLE, SUSPENDED). *Default:* adopt §14 exactly and map the
   existing log through a versioned name mapping — the append-only log itself
   is not rewritten.
2. **Rising 200 classification.** §19 says PROMISING / INSUFFICIENT EVIDENCE.
   The pre-registered stop-width sweep (completed 2026-09-24) found the
   `rising_200` entry loses net in all 30 stop x hold cells over 2006-2019.
   *Default:* classify as §19 says and attach the sweep result to the strategy
   record as evidence, so both are visible.
3. **Template generation vs. the search freeze.** `SEARCH_MODE=FROZEN` and
   `seed_mode: NONE` were written for the evolutionary search, and
   `factory.py` refuses every run while frozen. §4/§5 generators are
   predefined templates, not evolution. *Default:* treat template generation
   as a separate governed path; the freeze stays on `evolve.py`. Lifting the
   freeze itself remains a human edit to `config.yaml`.
4. **Restating forward records.** §35 requires restatement after the
   accounting fix; Phase 6 §14 says forward records are never modified
   retrospectively. *Default:* keep original curves untouched, write restated
   curves alongside under a versioned accounting model, and preserve the §35
   snapshot as a file.
5. **FINSABER download.** ~253 MB CSV from
   `huggingface.co/datasets/finsaber-team/FINSABER-reproduce`. Will ask for an
   explicit go-ahead at H6 before downloading.
6. **Live step (H13).** The existing execution layer produces a validated,
   risk-checked order; the LIVE transmit path is an existing unbuilt item
   (see CLAUDE.md, Robinhood Agentic). H13 connects qualified candidates to
   that layer and does not change it.

---

**Stage I — Addendum A: the autonomous 5-slot trading system** — entered 2026-09-24, **building** (Addendum B)

Spec in `docs/ADDENDUM_A_AUTONOMOUS_5_SLOT.md`, verbatim. It defines the end
product: research feeds a trading engine that runs five ~$20 slots, each
controlled by a distinct eligible strategy, executed, monitored and replaced
automatically through Robinhood. It reframes Phase 13 as the *research engine*
and adds the *trading engine* Phase 13 only reaches at H12-H13.

*What it supersedes on approval* (flagged in CLAUDE.md, "Trading mandate"):

| existing rule | replaced by |
|---|---|
| human places every order | automatic execution through the central risk/execution layer (§2, §23, §24) |
| swing only, never intraday | intraday, day trading, swing and long holds all permitted (§3) |
| `top_n` fills every slot daily | slot engine leaves a slot in cash rather than fund a losing strategy (§11-13) |
| stops checked once a day | continuous intraday position monitor; risk overrides strategy (§16-17) |
| scored against the null / benchmark as a gate | positive P&L is the objective; benchmark and null displayed, not required (§5-6) |

*Reuse map*

| addendum concept | existing module(s) | Stage I work |
|---|---|---|
| Five slots, ~$20 each | `allocation.py` (3 schemes), `config.yaml` sizing | new slot model and table (§4); capital per slot from config |
| Slot allocation / replacement | `roster.py` (top five eligible, demotion), `eligibility.py` (correlation) | new slot engine with centralized, configurable replacement rules and hysteresis (§8-11) |
| Family diversity | Phase 13 H12 family-concentration limit | one slot per family unless evidence supports more; empty slot beats a losing one (§12-13) |
| Leaderboard | `scoreboard.py`; Phase 13 H14 global scoreboard | continuously updated, P&L-first ordering (§10) |
| Order path | `signals.py`, `risk_engine.py`, `execution.py`, `broker.py` (`RobinhoodBroker`, order state machine) | finish the LIVE transmit path, execution confirmation, retry/escalation (§16, §23) |
| Kill switches | `killswitch.py` (six switches, `data/KILL_SWITCH`) | add cancel-open-orders, emergency exit policy, promotion freeze, per-strategy switches (§25) |
| Stops | `stop_loss.py`, `check_exits.py` (daily) | intraday position monitor + stop/risk engine; all stop types in §15 |
| Reconciliation | `orders.py --reconcile` | scheduled reconciliation loop and order-state recovery on restart (existing unbuilt items) |
| Processes | `daily.sh` (cron), `run_bounded.sh` | separate long-running services A-F (§27) with memory caps |
| Reporting | `fund_report.py`, `notify.py`, `build_dashboard.py` | slots, replacements, risk events, gross/costs/net (§23) |

*Implementation order and status*

| step | item | addendum § | state |
|---:|---|---|---|
| I1 | Slot model: table, config (count, capital per slot), slot state fields | §4, §14 | **done** `slots.py` (append-only slot log) |
| I2 | Live slot allocation engine: filters, ranking, family diversity, cash-when-unqualified | §11-13 | **done** `slots.py` (eligibility first, net rank, one per family, cash when none) |
| I3 | Centralized replacement engine: configurable evidence thresholds, hysteresis, recorded decisions | §8-9, §21 | **done** `slots.py` (margin, min hold, daily churn cap) |
| I4 | P&L-first leaderboard, continuously updated | §5-7, §10 | **done** `slots.py --leaderboard` |
| I5 | Mandatory risk plan per strategy; all stop types; risk-over-strategy priority | §15, §17 | **done** `stop_plans.py` |
| I6 | Intraday market data feed + position monitor during market hours | §16, §18 | **done** `slot_trader.py --monitor`, `quotes.LiveQuotes` (stale refused) |
| I7 | Intraday signal engine and intraday strategy support | §3, §18 | **done, SHADOW only (B8)** `intraday.py` |
| I8 | LIVE execution path: transmit, confirm, retry/escalate, order-state recovery, reconciliation loop | §16, §23 | **done for SIMULATION/SHADOW** `slot_trader.py`, `LedgerSimulatedBroker`; LIVE transmit remains the operator step |
| I9 | Global and per-strategy kill switches with cancel / emergency-exit / freeze / alert | §25 | **done** per-strategy switches + emergency policy (`killswitch.py`, `slot_trader.emergency`) |
| I10 | Daily five-slot reassessment | §26 | **done** `slots.py --apply` in daily.sh |
| I11 | Process separation: live trading, backtesting, paper, ingestion, ranking, discovery as independent services | §19, §27 | **done** `services.sh` (cron, 5-min trader) |
| I12 | Account-rule guard in the risk engine (day-trade count / settled cash) | §3 | **done** `account_rules.py` in the risk engine (cash, T+1) |
| I13 | Reporting: slots, trades, replacements, risk events, gross/costs/net | §23 | **done** slot section in `factory_report` |
| I14 | End-to-end in SIMULATION, then SHADOW, then live once the operator authorizes the account | §24 | **SIMULATION + SHADOW done** (`tests/e2e/e2e_factory.py`); LIVE is the user's authorization (B14) |

*Sequencing with Phase 13.* Slots need ranked strategies and trustworthy P&L,
so H2 (accounting) comes first for both. Proposed interleave: H1-H2, then I1-I5
and I8-I9 (the trading engine on SIMULATION) alongside H3-H8, then I6-I7 and
I10-I13 alongside H9-H14, and I14 with H15. Each I-step runs on the simulated
broker until I14.

*Decisions to confirm before building* — each with the default the build will
follow if nothing else is said:

1. **What ranks a strategy for a slot: gross or net P&L.** §7 prioritises
   gross; §6 says a strategy that loses money is not successful. A strategy
   can be positive gross and negative net — it then loses money in the
   account. *Default:* rank on **net P&L using measured execution costs**
   where live fills exist and modeled costs otherwise; gross, costs and net
   shown side by side on every line.
2. **Account rules for intraday trading.** FINRA's pattern-day-trader rule
   applies to margin accounts: 4 or more day trades in 5 business days
   requires $25,000 equity, and below that the account is restricted. Cash
   accounts are exempt from PDT but can only trade with settled funds (T+1),
   so same-day round trips on unsettled proceeds risk good-faith violations.
   *Needed from you:* is the Agentic account margin or cash? *Default:* the
   risk engine counts day trades and blocks any trade that would breach the
   rule for that account type.
3. **Minimum evidence to take a slot.** The league's `min_rank_marks` is 60
   sessions, which leaves every slot in cash for about three months.
   *Default:* a separate, configurable slot-eligibility threshold — proposed
   20 forward sessions, 10 closed trades, positive net P&L, drawdown under a
   configured limit — while the 60-mark rank stays as the "established" tier.
4. **Backtest gates.** The null and SPY benchmark stop being promotion
   requirements (§5-6). *Default:* a positive net backtest admits a strategy
   to paper trading; only forward (paper/live) evidence can win a slot (§29:
   never backtest alone); null and benchmark excess are reported, not gating.
5. **Intraday data.** Continuous stops and intraday signals need a live quote
   source; the database holds daily bars, and free intraday history covers
   about 60 days. *Default:* poll quotes for held positions and candidates
   at a configurable interval through the broker/market-data interface;
   intraday strategies are tested forward on paper until an intraday history
   source exists.
6. **The current real positions.** The Agentic account holds the positions
   placed by hand on 2026-09-14. *Default:* adopt them as legacy positions,
   exit each under its recorded stop, and open nothing new outside the slot
   engine.
7. **Arming live execution.** The code path to live is built and tested on
   SIMULATION and SHADOW; switching the account to LIVE uses the operator
   authorization §24 reserves for a human. *Default:* I14 ends with LIVE ready
   to arm, and arming is your step.

---

**Addendum B — how it resolves the Stage H and Stage I decisions** (2026-09-24)

Build authorized; order is H1-H15 then I1-I14 (B23), integrating as it goes.

| decision | resolution |
|---|---|
| H1 lifecycle names | default stands: §14 names, legacy log mapped not rewritten |
| H2 Rising 200 | default stands: PROMISING / INSUFFICIENT EVIDENCE with the sweep attached |
| H3 template generation vs freeze | resolved by B16: factory templates are the discovery path; `evolve.py` stays frozen |
| H4 restating history | resolved by B18: preserve, mark original, restate alongside, never overwrite |
| H5 FINSABER download | **answered 2026-09-24: yes, all three files.** Downloaded, schema-checked, imported to `data/finsaber.db`; returns agree 99.5-99.8%/yr with the primary DB |
| H6 live step | resolved by B13/B14: connect into the existing execution/risk layer; real-money activation is a user authorization event |
| I1 gross vs net | resolved by B5: rank on net (measured costs, else modeled); gross/costs/net always shown |
| I2 account type | **CASH** (user, 2026-09-24): no PDT limit; trade settled funds only (T+1); `config/risk.yaml` `account_type` |
| I3 slot evidence | resolved by B11: 20 forward sessions, 10 closed trades, positive net, drawdown under limit; 60 sessions = established tier |
| I4 backtest role | resolved by B3: backtest admits to paper; only forward evidence wins a slot |
| I5 intraday data | resolved by B8: live polling for monitoring; intraday strategies stay paper/shadow until a historical intraday provider exists; interface built now |
| I6 legacy positions | default stands |
| I7 arming live | resolved by B14: SIMULATION -> SHADOW -> LIVE; activation is the user's |

Benchmarks and the null are informational, never promotion gates (B20).

---

**Stage J — Addendum C (revision 2): survivorship-bias-free universe reconstruction** — entered 2026-09-24, **BUILT 2026-09-24 (stages 1-5) on the recommended answer to each question below, under the user's instruction to build every roadmap item. Each answer is a config value; change it and rebuild.** Results: Layer A ~8,000 companies alive per year; 7,618 synthetic dead companies; discriminability AUC 0.768 (gate 0.60 — fails, so retest-only); 12-1 momentum 23.3% -> 19.0% -> 14.3% CAGR (our data / with synthetic / every death a total loss).

Spec verbatim in `docs/ADDENDUM_C_SYNTHETIC_DELISTING.md`. Revision 1 narrowed
the request to S&P 500 delisting returns; the scope is the full US equity
universe. **Synthetic data here corrects survivorship bias; it is not a
substitute for real data, and every result resting on it carries wider error
bars.**

*Feasibility — stated plainly*

| part | 1990–1995 | 1996–2024 |
|---|---|---|
| Layer A: which companies existed | **not feasible at quality with free data.** EDGAR electronic filing phased in 1993–1996: the 1993 Q1 full index is 1 KB, 1996 Q1 is 7.8 MB. A 1990–95 universe would be mostly imputed | **feasible.** EDGAR registry (38,876 annual filers, 31,752 that stopped filing), Alpha Vantage delistings (9,464 with exact dates, thin before 2009), Internet Archive directory snapshots (2008 on), FinanceDatabase (delisted flag, sector, industry) |
| Layer A: ticker for a dead company | mostly unknown | often unknown — EDGAR is keyed by CIK and company name. Where no ticker is recoverable, the record gets a synthetic identifier tied to the CIK, tagged imputed |
| Layer A: IPO date, delisting date | imputed | first/last EDGAR filing as approximations, tagged; Alpha Vantage dates are real where present |
| Layer A: market cap at first observation | not available | real from XBRL filings after ~2009; before that mostly unavailable, so the cohort key would be "unknown" rather than guessed |
| Layer B: calibration data | — | real paths exist for survivors and for the 553 delisted names we hold — which are biased toward clean exits (CLAUDE.md: never calibrate the failure case on that sample). **The cohorts that matter most — small, failing companies — have the least real data.** Their paths would be calibrated from pre-delisting drawdown behaviour of distressed names we do hold, plus the published delisting-return statistics |
| Layer B: realism | — | the existing generator (`synthetic_delistings.py`) is distinguishable from real delisted names at **AUC 0.978**. A new generator must be tested the same way; until it passes, synthetic rows are for retests and stress bounds only, never for strategy discovery or promotion gates |

**Proposed feasible scope:** the full US common-stock universe on NYSE, NASDAQ
and AMEX from **1996 to 2024**, with 1990–1995 either dropped or carried as an
explicitly low-confidence, mostly-imputed period. Full 1990 coverage would
need paid data (CRSP via a university affiliation, or Norgate's delisted
add-on, ~$270/yr).

*Free sources — verified accessible on 2026-09-24*

| source | verified | gives | does not give |
|---|---|---|---|
| SEC EDGAR full-index | HTTP 200 with the project's User-Agent (403 without one) | every filer by CIK, name, form, date, 1993– (dense from 1996) | tickers, prices |
| Alpha Vantage LISTING_STATUS (already loaded: `delistings`) | in use | 9,464 delisted listings, exchange, IPO and delisting dates | reasons, prices; thin before 2009 |
| Internet Archive NASDAQ Trader directory (already loaded) | in use, 119 snapshots | which symbols were listed on each date, 2008– | anything before 2008 |
| FinanceDatabase (JerBouma/FinanceDatabase, GitHub) | repo active (updated 2026-09-20); per-exchange CSVs under `database/equities/` | `delisted` flag, sector, industry, ISIN/CUSIP/FIGI | IPO or delisting dates, prices |
| 8-K events (already loaded: `edgar_events`, 238,756 items) | in use | real delisting reasons where filed: 1.03 bankruptcy, 2.01 completed acquisition, 3.01 delisting notice | coverage for companies that never filed an 8-K |
| FINSABER | repository verified earlier; not yet downloaded | real S&P 500 paths incl. delisted names, 2000–2024 | anything outside the S&P 500 |
| Primary database | in use | 35.5M real bars, 13,200+ instruments incl. 553 delisted | the ~7,000 other delisted companies |

*Staged plan* (the spec requires confirmation before any code)

| stage | what | reuses | deliverable |
|---|---|---|---|
| 1 | Universe reconstruction: merge EDGAR, Alpha Vantage, IA snapshots, FinanceDatabase and FINSABER into one Layer A record per company, per-field provenance (`real` / `imputed`), reasons from 8-K events where filed, null otherwise | `edgar_registry.py`, `delistings.py`, `reconstruct_universe.py`, `pit_universe.py`, `edgar_events.py` | universe table + provenance report |
| 2 | Cohort analysis: cohorts by sector x cap bucket x exchange x IPO decade x reason class; per-cohort return, volatility, drawdown, market-beta, time-to-delisting and delisting-return distributions from real data; small cohorts pooled up a documented hierarchy; saved as a versioned, hashed artifact | `synthetic_delistings.py` calibration, `bias_exposure.py` | versioned cohort artifact |
| 3 | Synthetic paths: for each missing company, sample a real donor path's residuals from its cohort (block bootstrap), scaled to the cohort's volatility and tied to the actual market return on each date through the cohort beta; a delisting return drawn by reason class (mergers near zero, configurable); reverse splits handled on adjusted prices; partial real histories get only their missing tail | `synthetic_delistings.py`, `mc_1m.py` | tagged synthetic OHLCV |
| 4 | Provenance and integration: real rows pass through untouched; synthetic rows appended with `is_synthetic`, `data_source`, `cohort_id`, `generation_method`, `synthetic_reason`, `synthetic_seed`; stored outside the primary `prices` table; `load_backtest_data` with `as_is` / `exclude` / `zero` / `optimistic` / `real_only` | `data_providers.py` (a new provider) | merged store + loader |
| 5 | Validation and sensitivity: synthetic vs real statistics per cohort, QQ plots, the discriminability test, provenance-integrity assertions, synthetic share by year / sector / symbol; a strategy re-run across all five loader modes | `synthetic_validate.py`, `retest_synthetic.py`, `dataset_compare.py` | validation report + README |

*Clarifying questions — to answer before Stage 1*

1. **Start year.** 1996–2024, where free coverage is defensible, or 1990–2024
   with 1990–1995 carried as a mostly-imputed, low-confidence period?
2. **Real data beyond FINSABER.** Use the primary database (35.5M bars, 553
   delisted names) as `real_other` alongside FINSABER? Recommended — it is far
   larger than FINSABER and outside the S&P 500.
3. **Universe definition.** Common stock on NYSE, NASDAQ and AMEX only —
   excluding OTC, ADRs, funds, units and preferreds?
4. **Unknown tickers.** For dead companies with no recoverable ticker, use a
   synthetic identifier tied to the SEC CIK, tagged imputed?
5. **How backtests may use it.** Retests and stress bounds only, never
   strategy discovery or promotion gates, until the new generator passes the
   discriminability test? The existing generator scores AUC 0.978.
6. **Storage.** A separate store (parquet under `data/universe/`), never the
   primary `prices` table?
7. **Time variation.** Condition severities on SPY's trailing 12-month return
   (held locally), and add VIX via a free fetch?
8. **Merger delisting return default.** Near zero, e.g. centred at +1% with a
   3% spread, configurable?

---

**Stage K — crypto earns a slot** — entered 2026-09-24, **PLANNED** (owner: "add the plan for crypto to the roadmap")

Goal: a crypto strategy competes for one of the five slots through the same
ranking as everything else (`ranking.py`: backtest gate, then paper evidence
takes over), and trades through the Agentic account's linked crypto account.

*Where it stands, 2026-09-24*

| | state |
|---|---|
| account | the Agentic account has a linked crypto account (Robinhood `get_accounts`: `rhc_account_number` present; onboarding reports `already_onboarded`). Not yet confirmed tradeable |
| data | Coinbase hourly bars, 10 pairs, ~2 years (`crypto_prices`); topped up once a day |
| strategy | grid-DCA only (`crypto_grid.py`) — 0 of 10 pairs beat their null after fees |
| paper fund | `crypto_fund.py`, stepped daily |
| ranking | `ranking.backtest_per_trade` returns None for `crypto:`, so the grid ranks from a neutral 0 instead of being gated on its losing backtest |
| execution | slot_trader is equity-only; `config/risk.yaml` `allow_crypto: false`; the cron window is weekday market hours, crypto trades 24/7 |

*The finding that sets the plan: Robinhood's spread*

Robinhood charges no crypto commission; the cost is the spread. Measured
read-only on the Agentic account's routing, 2026-09-24 22:10 UTC (one
snapshot, after US hours):

| | BTC | ETH | SOL | XRP | LINK |
|---|---:|---:|---:|---:|---:|
| round-trip spread | 1.89% | 1.88% | 1.84% | 1.91% | 1.89% |

The backtests assume 1.2% (Coinbase taker 0.6% per side). **Grid-DCA takes
profit at +2%, so the spread consumes nearly all of every win** — it cannot
pass at Robinhood cost. Crypto needs LOW-turnover strategies, where ~1.9% per
round trip is small beside the move being held.

*Steps, in order*

| | step | where | deliverable |
|---:|---|---|---|
| K1 | Robinhood crypto cost model | here, then VM | `crypto_spreads` table logged from `get_crypto_quotes` (bid/ask, per pair, hourly for a week); `crypto_grid` / backtests charge the measured half-spread per side instead of the Coinbase taker fee |
| K2 | Daily history back to ~2016 | VM (network) | `crypto_data.py --interval 1d` full load, so a backtest spans the 2018 and 2022 crashes, not two years of hourly bars |
| K3 | Low-turnover strategies | here, run on VM | registered experiment; families e.g. trend (hold BTC/ETH above an N-day average, else cash), time-series momentum, BTC/cash switch in the pair-fund style. Scored net of K1 costs against the crypto null AND buy-and-hold. Each enters the library as HYPOTHESIS |
| K4 | Ranking wired | here | `ranking.backtest_per_trade` reads the crypto backtest; a losing crypto backtest is OUT, like any other; forward per-trade from the crypto paper fund(s) |
| K5 | Execution path | here | slot_trader trades a `crypto:` holder through Robinhood crypto orders (`rhs_account_number`), orders ledger + idempotency as for equities, a mandatory price stop, reconciliation against crypto positions |
| K6 | 24/7 monitoring | here, install on VM | a crypto-only cron pass (hourly, every day) so stops are watched on nights and weekends; equity slots keep their window |
| K7 | Arm | **owner** | `config/risk.yaml` `allow_crypto: true` on the VM |

*What is not claimed.* A positive crypto backtest over ~9 years of daily bars
is a few dozen trades for a trend rule — thin evidence, and the period is
mostly a bull market. The ranking will admit it on a positive backtest (the
owner's rule) and the paper record then moves it; that is the design, not a
finding of edge. The spread is one after-hours snapshot; K1 measures it
properly and may find it narrower in US hours.

---

**Profit exits** — added 2026-09-24 (owner: "we have stop loss rules but do we have 'we made some money, let's sell it' rules?")

| | item | state |
|---:|---|---|
| P1 | Live slots apply the strategy's own `take_profit_pct` | **done** — `stop_plans.py` dropped it; backtest and paper applied it. Older positions pick it up from their strategy version |
| P2 | Measure take-profit and trailing stops before adopting any | **built, not yet run** — `exit_sweep.py`, experiment `exit_rules`; simulator gained `trailing_atr_multiple` |
| P3 | Adopt a winning exit as a new strategy version | waits on P2; only cells that beat the strategy as it is over 2006-2019 AND in most two-year blocks |
| P4 | Slot-wide trailing stop, untested | **declined by the owner 2026-09-24** (steps 1 and 2 only) |

---

**Stage L — published signals as a strategy source** — entered 2026-09-24, **PLANNED** (owner: "the 700,000 strategies database, let's find something like that")

The owner asked for a large strategy database like trader.dev's (~797k user
strategies, ranked by their own backtests). That kind of list is a
leaderboard of backtests: the multiple-testing trap this project has already
fallen into. The academic equivalent is smaller, but every entry is a
published hypothesis, independently reproduced, **on survivorship-free data**.

| source | holds | survivorship | role |
|---|---|---|---|
| trader.dev | public user strategies, mostly crypto derivatives (Bybit, Toobit, ...) | unknown | **not used** — backtest leaderboard; needs an account and its MCP |
| **Open Source Asset Pricing** (Chen & Zimmermann; openassetpricing.com, `openassetpricing` on PyPI) | 212 published cross-sectional predictors: signal code, firm-level signals, decile / quintile portfolio returns, before and after publication | **free of it** — built on CRSP, dead companies included | **primary** |
| **Global Factor Data** (Jensen, Kelly & Pedersen; jkpfactors.com) | 153 factors (406 characteristics) across 93 countries | free of it (CRSP / Compustat) | **cross-check**: does the pattern hold outside the US |

*Why it matters here.* This project's backtests see 22.6% of the knowable 2008
universe. These portfolio returns include the companies that died, so they
are the only long-history evidence available to this project with no
survivorship bias. Decile returns give the long-only top decile, which is
what a slot can hold. Published anomalies lose roughly half their return
after publication, so only the **post-publication** record counts.

*Steps, in order*

| | step | where | deliverable |
|---:|---|---|---|
| L1 | Import OSAP decile portfolio returns and JKP factor returns into their own tables (`published_signals`, `published_returns`), source and release recorded | VM (network — both sites are blocked from the cloud session) | loader + tables, added to `backup.GROUPS` |
| L2 | One research-library entry per signal, status HYPOTHESIS, citation as provenance; evidence = post-publication top-decile return net of an estimated cost, and whether JKP's non-US version agrees | here | `library_bridge.py` / `strategy_library.py` entries |
| L3 | Rebuild the signals computable on our own data — price-based (momentum, short-term reversal, 52-week high, volatility, ...) and SEC-statement-based (gross profitability, accruals, asset growth, ...) — as `strategy_factory.py` templates, then the normal path: backtest -> rank -> paper | here | new factory families |
| L4 | **Decision for the owner:** use a signal's survivorship-free post-publication return as its ranking prior instead of our survivorship-biased backtest | owner | `ranking.py` prior source |

*Constraints stated up front*

- **Multiple testing:** 212 pre-existing hypotheses is a small, honest trial
  count, but it is still 212 — a signal is adopted only at t > 3
  (Harvey-Liu-Zhu), and every one counts against the trial counter.
- **Portfolio vs slot:** the published returns come from monthly-rebalanced
  portfolios of hundreds of stocks; a slot holds one $20 position. The
  published figure is a discounted prior, never a forecast for the slot.
- **Identifiers:** OSAP firm-level signals are keyed by CRSP `permno`, not
  ticker, and a ticker map needs CRSP. That is why L3 recomputes signals on
  our data instead of copying stock lists (the ticker-reuse trap applies).
- **Licence:** JKP data is CC BY-NC 4.0 — fine for this personal project.

---

**Survivorship in the ranking** — added 2026-09-24 (owner: "use the synthetic data")

| | item | state |
|---:|---|---|
| S1 | Indicators for the synthetic dead companies; append them to the real panel | **done** — `survivorship_backtest.synthetic_frames` |
| S2 | Every ranked strategy backtested in exclude / as_is / zero, same simulator, costs and fills | **built, not yet run** — `survivorship_backtest.py`, nightly `daily.sh [9f2]` |
| S3 | `ranking.py` scores and gates on as_is, shows zero as the worst case | **done** — falls back to the survivors-only backtest only until S2 has run |
| S4 | Drawdown exposure gate (was only on the retired promotion ladder) | **done** — in `ranking.gate` |

Overrides Addendum C question 5 ("retests and stress bounds only") for the
ranking, by the owner's ruling, although the generator still fails its realism
gate. Not used for strategy discovery.

---

**Stage M — realistic dead companies (synthetic generator v5)** — entered 2026-09-24, **PLANNED** (owner)

Why: the ranking now scores backtests WITH the synthetic dead companies
(survivorship_backtest.py), so their realism now moves money. The generator
copies real dead companies — 158 after impostor removal — but almost all are
clean ACQUISITIONS: a buyout keeps its price history in free data, a
bankruptcy does not. v3 fails the realism gate (AUC 0.768 vs < 0.60); v4 fixes
the buyout shape only; failures still end on literature numbers (Shumway:
-55% NASDAQ) with no real failing year behind them.

| | step | where | deliverable |
|---:|---|---|---|
| M1 | Build and score v4 — measures how much of the gap the buyout fix closes | VM (~1 h) | `synthetic_v4.parquet`, `validation_v4.json` |
| M2a | **Bankruptcy "Q" tickers**: for every Layer A company with an 8-K item 1.03, try `ticker + "Q"` (OTC continuation, e.g. LEHMQ, WAMUQ) from yfinance; store dated, sourced, tagged `real_failure` | VM (network) | `failure_paths` table / parquet, coverage count |
| M2b | **FINSABER S&P pickle** (27.3 GB, resumable import): its delisted S&P 500 members as failure donors where 8-K / Layer A says bankruptcy or delisting notice | VM | failures found, by name |
| M2c | **Label our own delisted names** (418-553 in `prices`) by 8-K item: 1.03 / 3.01 -> failure donors | here | donor labels in `universe_cohorts` |
| M3 | **Generator v5**: a synthetic FAILURE copies a real failure's final year (collapse, then the OTC slide) on its own dates, as v4 does for buyouts; literature delisting returns only where no real template exists, tagged | here, built on VM | `donor_failure_final_year_v5` |
| M4 | **Realism test split by exit type**: failures graded separately (AUC per reason), so a buyout pass cannot hide an unrealistic failure | here | `universe_validate.py` per-reason gate |
| M5 | **Permanent fix (paid, owner's call)**: Norgate or FirstRateData delisted prices (~$270/yr) replace most synthetic companies with real ones | owner | — |

*Real-world sources found 2026-09-24 (web search; none reachable from the
cloud session, all to be tried on the VM)*

| source | what it gives | use |
|---|---|---|
| **Florida-UCLA-LoPucki Bankruptcy Research Database** (lopucki.law.ufl.edu) — Cases table, free download | ~1,000+ large public-company bankruptcies since 1979, ~200 fields per case incl. filing date; frozen at the Dec 2022 update | **M2d**: the failure list with exact filing dates, beyond our 8-Ks (which thin out before 2009) — drives the Q-ticker fetch and aligns each real path to its filing day |
| **Yahoo Q tickers** — e.g. LEHKQ (a Lehman trust security) has a Yahoo history page | OTC Pink continuation after a Chapter 11 filing | **M2a** confirmed plausible; coverage unknown until the VM tries |
| Kaggle "Arandkei: Historical Delisted Assets Archive" (updated 2026-03) | daily OHLCV for delisted stocks; contents and licence unverified | **M2e**: inspect on the VM; use only with provenance and the ticker-reuse check |
| HistoricalData.net (23,259 delisted tickers), EODHD, FirstRateData (7,000+ delisted from 2000), Norgate | full delisted histories, paid | **M5** candidates |

*Calibration targets from the literature — M4 checks the synthetic failures against these*

| fact | figure | source |
|---|---|---|
| performance-delisting return, missing in CRSP | -30% (NYSE/AMEX), -55% (NASDAQ) | Beaver, McNichols & Price 2007; Shumway 1997, Shumway & Warther 1999 |
| drift AFTER a Chapter 11 filing, on Pink Sheets | about -28% over the following 12 months (602 filings, 1998-2006) | Coelho & Taffler, "Gambling on the market" / "Bankruptcy sells stocks" |
| BEFORE failure | lower past returns, much higher volatility and beta, lower share prices, small caps | Campbell, Hilscher & Szilagyi 2008, "In Search of Distress Risk" |

So a realistic synthetic failure has three phases, not one delisting-day
drop: a volatile decline into the filing, the delisting return, then a
negative OTC drift afterwards. v4 models only the second.

*Limit stated up front:* even with Q tickers there will be tens to a few
hundred real failure paths against ~3,000 synthetic failures, so each real
template is reused many times; the realism test measures whether that reuse
is detectable.


---

**Stage N — Addendum D: Live Growth & Continuous Improvement** — entered 2026-09-25, **NOT YET STARTED** (owner: "add the following items to the roadmap. do not change them just add them in and integrate them faithfully")

Spec verbatim in `ADDENDUM_D_LIVE_GROWTH.md`. It sets its own order (§20) and
its own definition of done (§23); both are reproduced here unchanged. The
columns "exists today" and "gap" are the integration: per §21, an existing
component is improved, never duplicated.

**Standing rules from the spec** (apply to every step below)

- §1 LIVE is not stopped for this phase. A change that can touch live trading
  is isolated, tested, deployed safely, and the live system verified after
  (versioned modules, feature flags, staging or SHADOW where needed).
- §2 / §22 the loop is continuous: live -> observation -> measurement ->
  discovery -> backtest -> robustness -> paper -> eligibility -> ranking ->
  promotion -> live.
- §13 a slot may be CASH; quality is never manufactured to fill five.
- §14 broker state is authoritative; nothing is assumed filled because it was
  requested.
- §18 research -> candidate -> eligibility -> ranking -> live allocation ->
  execution; only the last two can trade. (Already enforced in part:
  `tests/regression/test_freeze_boundary.py`, `eligibility.py` imports neither
  `execution` nor `broker`.)
- §9 / §21 the frozen evolutionary search stays frozen; discovery runs through
  the Phase 13 architecture.

| step | spec | priority (§20) | exists today | gap to build |
|---:|---|---|---|---|
| N1 | §3, §4, §5, §15 | 1 — Live visibility: the real-time **Control Center** — account overview (BROKER / SIMULATED-PAPER / RESEARCH never mixed), five-slot view with "why this strategy is in the slot", live trade feed, system health | `monitor.py --serve` (stdlib web page, read-only DB, port 8787); `build_dashboard.py` (daily static page); tables `slot_assignments`, `slot_trades`, `slot_marks`, `slot_reviews`, `orders`, `signals`, `system_events`, `risk_events`; `slot_trader.py --status` | one served live page over those tables + broker snapshot: account block, slot cards, event feed, health panel (heartbeats, last quote/order/fill/reconcile, CPU/RAM/disk, error counts) |
| N2 | §14 | 2 — Live reliability: verify every execution and reconciliation path in the §14 list | `risk_engine.py`, `killswitch.py`, `execution.py` (idempotent `signal_id`), `robinhood_live.LiveBroker` (review -> place -> confirm, ref_id), per-run reconciliation in `slot_trader.py`, 67 test files | a §14 checklist test per item (partial fills, rejects, stale price, market closed, API failure, restart) against the live broker's fake; any item uncovered is fixed |
| N3 | §6 | 3 — Strategy leaderboard: every eligible strategy, status, scores, evidence age, current slot | `ranking.py` (single ranking), `scoreboard.py`, `leagues.py`, `league_standings` | leaderboard view in the Control Center with lifecycle status (LIVE / PAPER / PROMISING / BACKTEST) and movement since the previous ranking |
| N4 | §7, §8 | 4 — Replacement visibility + strategy journal | `slots.py` replacement engine, `slot_assignments` / `slot_reviews`, `strategy_decisions`, `league_state` (append-only), `strategy_objects.py` | "NEXT POSSIBLE REPLACEMENTS" table; a replacement record with old/new strategy, reason, old/new performance, time, account effect; a per-strategy journal view assembled from the append-only logs (nothing deleted) |
| N5 | §12 | 5 — Strategy health / decay: HEALTHY / WATCH / DEGRADING / FAILED | `degradation.py` (backtest -> forward per-trade), `signal_decay.py` | rolling live/paper P&L, win rate, expectancy, drawdown vs own baseline, paper and backtest; state recorded per strategy; a DEGRADING live strategy is easier to replace when a qualified alternative exists |
| N6 | §11 | 6 — Live -> research feedback: predicted vs actual, slippage, delay, exit reason, regime | `orders` / `slot_trades` (fills), `costs.py` (modelled cost), `regimes.py` | per-trade feedback table joining the signal's expected fill and return to the broker's actual; aggregated only, never a change to a live strategy from one trade |
| N7 | §9, §10 | 7 — Continuous discovery targeted at measured weaknesses | `discovery.py`, `factory_pipeline.py` (in `daily.sh` [9c]-[9h]), `research_queue.py`, `exit_sweep.py` | discovery priority fed by N5/N6 weaknesses (exits, drawdown, regime, turnover, costs, correlation) |
| N8 | §19 | 8 — Stages K, L, M continue in parallel | Stages K / L / M above | unchanged; run as part of the research program without interrupting live |
| N9 | §17 | 9 — Scaling: TOTAL_CAPITAL, NUMBER_OF_SLOTS, CAPITAL_PER_SLOT, MAX_POSITION_SIZE, MAX_DAILY_LOSS, MAX_STRATEGY_LOSS, MAX_DRAWDOWN | `config.yaml` `slots:` (count, capital per slot), `config/risk.yaml` limits | every §17 key in config, read by the engine; today's ~$100 / five-slot values kept |
| N10 | §16 | (spans 1-7) Daily autonomous operating loop + end-of-day report (ACCOUNT ... NEXT ACTIONS) | cron: `daily.sh` 07:00 UTC, slot trader every 5 min, `lab_watchdog.sh`; `fund_report.py`, `factory_report.py` | pre-market sync + health gate; end-of-day report with the twelve §16 sections |

**Definition of done (§23), tracked item by item**

| # | criterion | state |
|---:|---|---|
| 1 | Open a dashboard and see Stockbot2000 operating live | open |
| 2 | See all five strategy slots | open |
| 3 | See every live position | open |
| 4 | See live P&L | open |
| 5 | See stops and exits | open |
| 6 | See the live event stream | open |
| 7 | See the complete strategy leaderboard | open |
| 8 | See potential replacement strategies | open |
| 9 | See why a strategy was promoted or replaced | open |
| 10 | See research activity occurring in the background | open |
| 11 | New strategies move through the pipeline without manual intervention | partly — factory pipeline in `daily.sh` |
| 12 | Live performance feeds back into strategy evaluation | partly — `ranking.py` shifts to paper/forward evidence per trade |
| 13 | Strategy degradation detected automatically | open |
| 14 | Qualified strategies automatically replace weaker live ones | partly — `slots.py` controlled replacement |
| 15 | Restart and reconcile safely | partly — ledger recovery + per-run reconciliation; §14 verification (N2) open |
| 16 | Live trading isolated from research code | partly — freeze-boundary and eligibility import tests |
| 17 | K, L and M continue progressing | open — Stage M1 is on the VM run list |
| 18 | Operates without manually starting each research/trading cycle | partly — cron; research steps still started by hand |

**End-of-session report format (§24)**: IMPLEMENTED, FILES/MODULES CHANGED,
DATABASE/SCHEMA CHANGES, LIVE COMPONENTS AFFECTED, TESTS RUN, LIVE TESTS RUN,
CURRENT SYSTEM STATUS, CURRENT LIVE STRATEGIES, CURRENT RANKING, NEW RESEARCH
ACTIVITY, BLOCKERS, NEXT AUTOMATIC JOBS, STARTUP/DEPLOYMENT COMMANDS.
