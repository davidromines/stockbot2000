# Roadmap integration — Phases 6–11

The deliverable required by `PHASES_7_11_STRATEGY_LEAGUE.md`. Ten items, in the
order that document asks for them.

**Nothing here is implemented.** This is the architecture and ordering analysis
that precedes implementation.

---

## 1. The project plan, updated

Six phases now define the direction. Phases 1–5 (data, pipeline, environment,
smoke test, migration) and the numbered phases 06–15 already in `ROADMAP.md`
describe what was built; these describe where it goes.

| Phase | Name | Status |
|---|---|---|
| 6 | Research Integrity & Independent Validation | planned — `PHASE6_RESEARCH_INTEGRITY.md` |
| 7 | Continuous Strategy Laboratory & Paper Trading League | planned |
| 8 | Continuous Strategy Discovery & Real-World Strategy Library | planned |
| 9 | Fundamental Value Intelligence Engine | planned |
| 10 | Live Capital Allocation & Strategy Promotion | planned |
| 11 | Continuous Research Loop | planned |

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

Stage A is complete except the seed-free comparison, which is pre-registered
and whose two arms are running. Nothing in Stage A produced a positive
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
| 30 | Value Fund architecture, paper only | not started |

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
| 38 | Crypto market data into its own table | not started |
| 39 | Decide the session and fill convention explicitly | not started |
| 40 | Crypto paper fund, separate from the equity league | not started |
| 41 | Crypto strategies via the research library | not started |
| 42 | Crypto order slate — human places | not started |

Spec in `docs/PHASE12_CRYPTO_FUND.md`. **The source article's execution layer —
an LLM placing orders on an exchange — is explicitly out of scope**, both
because Claude does not execute financial transactions and because this
project's own record says autonomous execution of an unproven strategy
automates the losses.

Item 39 blocks everything after it. Crypto has no close and no next open, so
the next-open fill convention cannot be inherited unmodified — and getting a
fill convention wrong is the defect that cost this project its largest single
correction.

**Two ordering constraints worth stating plainly.** Stage A item 1 comes first
because every later stage adds surface area to a codebase with a documented
history of silent measurement defects. And Stage B item 13 comes before item 14
because the existing forward record is the most valuable and least replaceable
data in the project — migrate it before changing the thing that writes it.
