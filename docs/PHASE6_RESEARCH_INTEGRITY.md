# STOCKBOT2000 — PHASE 6
# RESEARCH INTEGRITY & INDEPENDENT VALIDATION

> **STATUS: PLANNED — NOT IMPLEMENTED.** Added to the project plan 2026-09-22 at
> the user's direction, as a specification only. Nothing in this document has
> been actioned. The plan below is reproduced as written and is not to be
> modified. **This is the new direction; all existing systems integrate into it.**

---

You are continuing development of Stockbot2000.

Read the existing `PROJECT_STATUS.md`, `ARCHITECTURE.md`, README, test suite, and
the latest build record before modifying anything.

The current project state is approximately:

* 165 commits
* 65 modules
* 1,029,805 strategy evaluations
* 35.5M price bars
* 13,121 instruments
* 953 validation survivors
* 284 currently unverified
* 67 assertions/tests in the execution layer
* $96.62 deployed in the Robinhood Agentic account
* zero demonstrated trading strategies
* multiple historical measurement artifacts discovered and corrected

The most important conclusion so far is:

The system has repeatedly produced apparent edges that were later proven to be
measurement artifacts.

Therefore, this phase is NOT primarily about finding another strategy.

This phase is about making it substantially harder for Stockbot2000 to fool
itself.

## OPERATING PRINCIPLE

You are the engineering lead.

Do not spend the project repeatedly explaining that trading is risky or that no
strategy can be guaranteed profitable.

Those facts are already understood.

Your job is to implement the research infrastructure.

If you discover a legitimate technical limitation:

1. identify it;
2. implement everything that does not depend on it;
3. document the exact blocker;
4. continue with the next independent task.

Do not stop the entire project because one component is blocked.

Do not fabricate successful tests.

Do not claim an edge exists unless the evidence supports it.

The system's default assumption must be:

```text
NO EDGE UNTIL PROVEN OTHERWISE
```

## PHASE 6 OBJECTIVES

Build five major improvements:

1. Independent research dataset / truth set
2. Seed-free discovery environment
3. Stronger validation firewall
4. Pre-registered experiment framework
5. Forward-validation program

Do NOT expand the evolutionary search until these components are operational.

## 1. FREEZE OPEN-ENDED STRATEGY SEARCH

Temporarily disable continuous evolutionary strategy discovery.

Do not delete the existing search system.

Preserve all existing results.

Add:

```text
SEARCH_MODE=FROZEN
```

to configuration.

The existing laboratory search should remain available for controlled
experiments but must not continuously consume compute by default.

Update `lab_loop.sh` so that:

```text
SEARCH_MODE=FROZEN
```

prevents new searches.

The watchdog must continue monitoring the process, but it should not restart a
deliberately frozen search.

Document why the search is frozen.

The reason is not "we believe momentum works."

The reason is:

```text
1.03M trials have created a severe multiple-testing burden.
Additional search on the same data currently adds less information than independent forward observation and data-quality improvement.
```

## 2. REMOVE SEED CONTAMINATION

The current search injected a hand-written `momentum_pullback` seed.

This produced a false appearance of independent discovery.

The latest run showed approximately 85% of survivors containing momentum +
pullback, with many carrying the exact constant 40.0 inherited from the seed.

This must be permanently addressed.

Create:

```text
seeds/
    published/
    experimental/
```

and make seed usage explicit.

Configuration:

```yaml
seed_mode: NONE
```

must mean:

```text
NO HUMAN-PROVIDED STRATEGIES
NO HAND-WRITTEN RULES
NO DESCENDANTS OF SEEDED STRATEGIES
```

Create a strategy ancestry record.

Every generated strategy must have:

```text
strategy_id
parent_ids
generation
seed_origin
mutation_history
creation_timestamp
```

A strategy derived from a seed must never be classified as an independent
discovery.

## 3. SEED-FREE CONTROL RUN

Create a reproducible experiment:

```text
experiments/seed_free_search/
```

The experiment must compare:

```text
A = seeded search
B = identical search with seeds disabled
```

Keep all other conditions identical.

Measure:

* number of candidates
* number surviving each validation gate
* structural diversity
* behavioral diversity
* best validation statistic
* median statistic
* maximum statistic
* out-of-sample performance
* forward performance

Do not select the better-looking result.

The purpose is to measure how much the seed changes the search distribution.

## 4. INDEPENDENT TRUTH DATASET

This is one of the highest-priority tasks.

Create a small, independently verified dataset that the strategy system cannot
modify.

Call it:

```text
truth_set
```

The truth set must contain:

```text
ticker
date
open
high
low
close
volume
security_type
listing_status
delisting_date
```

where available.

The key property:

```text
THE BACKTEST ENGINE DOES NOT BUILD THE TRUTH SET.
```

The dataset must be immutable after creation except through an explicit
versioning process.

Create:

```text
truth_set_version
truth_set_manifest
truth_set_hash
```

Every research run records the exact truth-set version.

## 5. POINT-IN-TIME UNIVERSE

The current project has a major known data limitation:

Thousands of delisted companies are represented in registries without
corresponding historical price data.

Do not silently treat these securities as if they were never available.

Create a point-in-time security universe interface:

```python
get_available_securities(date)
```

It must answer:

Which securities could an investor actually have known about on this date?

Not:

Which securities exist in today's database?

Implement:

```text
listing date
delisting date
security type
ticker history where available
exchange
```

Avoid look-ahead.

A security that had not yet listed must not appear.

A security that had already delisted must not appear.

## 6. DATA COMPLETENESS AUDIT

Create:

```text
data_audit.py
```

Run it over the entire research universe.

Report:

```text
total securities
securities with complete price history
securities missing historical periods
delisted securities
delisted securities with prices
delisted securities without prices
listing-date coverage
delisting-date coverage
fundamental-date coverage
```

Produce a machine-readable report:

```text
reports/data_completeness.json
```

and human-readable:

```text
reports/data_completeness.md
```

The report must identify exactly which research periods are affected.

## 7. FUNDAMENTAL DATA POINT-IN-TIME AUDIT

Apply the same discipline to fundamentals.

Every fundamental feature must have:

```text
company
metric
value
period_end
filing_date
available_date
source
```

The model/backtest may only use information whose:

```text
available_date <= decision_date
```

Never use:

```text
period_end
```

as a proxy for when the market knew the information.

The filing date is what matters for point-in-time availability.

Create automated tests for this.

## 8. MARKET-DATA FRESHNESS AUDIT

The previous pipeline contained a circular freshness measurement that allowed
the system to report success while operating a full session behind.

Make freshness a first-class metric.

For every daily run record:

```text
expected_latest_date
actual_latest_date
lag_days
lag_sessions
missing_symbols
```

A run must fail if freshness exceeds the configured threshold.

Do not allow the pipeline to report:

```text
SUCCESS
```

when data freshness is outside the allowed range.

## 9. VALIDATION FIREWALL

Review the existing six-stage validation ladder.

Do not assume that because six gates exist, the methodology is sound.

For every stage document:

```text
INPUT
TRANSFORMATION
OUTPUT
WHAT INFORMATION IT IS ALLOWED TO SEE
WHAT INFORMATION IT MUST NEVER SEE
```

Create:

```text
validation_firewall.md
```

The firewall must explicitly prevent:

```text
future prices
future fundamentals
future universe membership
future delistings
future strategy performance
holdout results
forward results
```

from influencing earlier stages.

## 10. SEALED HOLDOUT

Create a truly sealed holdout dataset.

The holdout must not be readable by:

```text
strategy generation
hyperparameter tuning
feature selection
strategy selection
model selection
threshold optimization
```

until the final evaluation.

Create a separate evaluation process:

```text
evaluate_holdout.py
```

The normal research process should not import the holdout dataset.

Ideally enforce this through filesystem/database permissions rather than merely
developer discipline.

The holdout should be versioned and hashed.

## 11. EXPERIMENT REGISTRY

Create:

```text
experiments/
experiment_registry.py
```

Every formal experiment must receive:

```text
experiment_id
hypothesis
start_date
researcher
data_version
universe_version
features
strategy
parameters
primary_metric
secondary_metrics
stopping_rule
sample_size
holdout_policy
status
```

The experiment definition must be written BEFORE results are calculated.

## 12. PRE-REGISTRATION

Implement a mechanism where an experiment is locked before execution.

Example:

```text
experiment status:

DRAFT
REGISTERED
RUNNING
COMPLETE
REJECTED
```

Once:

```text
REGISTERED
```

the following cannot be changed without creating a new experiment version:

```text
primary metric
holding period
entry rule
exit rule
universe
cost assumptions
evaluation period
```

This prevents "researcher degrees of freedom."

## 13. STOP-WIDTH EXPERIMENT

Run the existing:

```text
stop_sweep.py
```

BUT do not turn it into open-ended optimization.

Pre-register the experiment first.

The purpose is to answer:

Is the apparent relationship between stop width and forward performance robust
enough to justify further investigation?

Do NOT optimize the stop to maximize the existing 14-day result.

Use predefined stop values.

Use a predefined evaluation period.

Record all results, not merely the best result.

Report:

```text
mean
median
dispersion
confidence interval
number of trades
maximum drawdown
cost-adjusted return
```

Then let the forward record continue.

Do not promote a stop rule merely because it wins the sweep.

## 14. FORWARD EXPERIMENT PROGRAM

The current paper funds are the most valuable measurement mechanism because they
operate forward in time.

Expand this architecture.

Create a fixed set of forward experimental portfolios.

DO NOT continuously replace underperforming strategies with newly optimized
ones.

Once a strategy enters a forward experiment:

```text
FREEZE IT
```

Record:

```text
strategy version
features
parameters
creation date
entry rules
exit rules
risk rules
```

Never modify it retrospectively.

If it fails, record the failure.

## 15. FORWARD SCOREBOARD

Create:

```text
forward_scoreboard.py
```

It must track:

```text
strategy
inception
days forward
trades
return
benchmark return
excess return
volatility
drawdown
Sharpe
win rate
profit factor
turnover
costs
```

Most importantly:

```text
TIME IN FORWARD TEST
```

must be prominent.

Do not allow a 10-day return to look equivalent to a 2-year record.

## 16. BASELINE PORTFOLIOS

Every strategy should be compared against appropriate baselines.

At minimum:

```text
cash
SPY buy-and-hold
relevant sector/index ETF
random entry/exit control
matched-universe null
```

The matched-universe null is critical.

If the strategy trades small-cap stocks, do not compare only against SPY.

Compare against the universe the strategy actually had access to.

## 17. RANDOM CONTROL

Preserve the existing random-genome control.

Expand it.

Generate a sufficiently large collection of random strategies passing through
the same pipeline.

Measure:

```text
distribution of returns
distribution of Sharpe
distribution of drawdown
distribution of win rate
distribution of turnover
```

The objective is to estimate:

How impressive can random strategies look after passing through this exact
research pipeline?

Use that distribution as a calibration tool.

## 18. MULTIPLE-TESTING ACCOUNTING

Create:

```text
multiple_testing.py
```

Track cumulative research trials.

Every time a strategy, parameter set, feature combination, or model is
evaluated, record the trial count.

The system should report:

```text
total_trials
unique_structures
unique_parameter_sets
effective_trials
```

Do not allow the system to present an ordinary Sharpe threshold without
displaying the research multiplicity context.

## 18a. THE TRIAL COUNTER IS APPEND-ONLY

> **AMENDMENT — added 2026-09-22 at the user's direction.** Not part of the
> original specification text above; recorded here because it governs §18.

```text
The cumulative trial count is append-only and is never reset, including when
strategies are archived or retired.
```

The reason is that deleting records does not delete the selection pressure that
produced them. 1,037,005 evaluations have already happened; removing the rows
would not un-run the searches, it would only destroy the denominator the
deflated-Sharpe correction depends on.

A counter that reset on cleanup would make the next survivor appear to have
cleared a bar of one trial when it actually cleared a bar of a million. The
system would look cleaner and be measurably more dangerous.

This is the file-drawer problem. Discarding the failed experiments is not a fix
for multiple testing — it is multiple testing with the evidence removed.

Consequences:

* Archiving, retiring or invalidating a strategy **never** decrements the count.
* Marking a population invalid — the 284 pre-fill-fix survivors, the 231
  seed-descended ones — is a **label**, not a deletion.
* Any future database migration, rebuild or cleanup must carry the cumulative
  count forward explicitly. A rebuilt database starting from zero is a
  regression, and should be caught by a test.

---

## 19. MODEL SEARCH SEPARATION

The XGBoost classifier currently has:

```text
AUC ≈ 0.63
```

but negative gross trading performance under realistic next-open fills.

Do not automatically interpret AUC as trading edge.

Separate:

```text
classification skill
forecast calibration
economic value
trading performance
```

Measure each independently.

Add:

```text
calibration
Brier score
log loss
precision by confidence bucket
return by confidence bucket
```

The question is not merely:

Can the model predict the label?

It is:

Does the prediction contain economically useful information after realistic
execution costs?

## 20. SIGNAL DECAY TEST

For each model, measure whether predictive power survives by horizon.

For example:

```text
1 day
2 days
5 days
10 days
20 days
```

This will determine whether the model's information is:

```text
short-lived
medium-term
persistent
nonexistent
```

Do not assume the original target horizon is optimal.

However, do not optimize the horizon on the same holdout.

## 21. REGIME ANALYSIS

Do not search for a strategy that works only because of one unusual market
regime.

Break forward/backtest results down by:

```text
bull
bear
high volatility
low volatility
high-rate
low-rate
crisis
normal
```

Use predefined regime definitions.

Do not cherry-pick regimes after seeing results.

## 22. STRATEGY PROMOTION RULES

Create an explicit promotion policy.

A strategy cannot move from:

```text
RESEARCH
```

to:

```text
FORWARD
```

unless it passes documented validation.

A strategy cannot move from:

```text
FORWARD
```

to:

```text
LIVE
```

merely because it has a positive return.

Require:

```text
data integrity
no leakage
no seed contamination
cost-adjusted performance
appropriate baseline
sufficient forward observations
risk compliance
stable implementation
```

The exact thresholds should be configurable rather than hard-coded.

## 23. LIVE TRADING REMAINS DISABLED

Keep:

```text
MODE=SIMULATION
```

or:

```text
MODE=SHADOW
```

as the default.

Do not connect new experimental strategies directly to the Robinhood execution
engine.

The existing $96.62 account remains an execution/integration test environment.

Do not increase capital allocation because of short-term forward performance.

## 24. CURRENT REAL-MONEY TRADE

The TNON trade exposed a genuine data-quality problem.

Do not use the −29% result to prove that the strategy is bad.

Do not use it to prove that the strategy is good.

Use it as a case study.

Create:

```text
case_studies/TNON.md
```

Document:

```text
what the system knew
what it failed to know
why the position passed
which data field was missing
which control should have rejected it
whether the new control catches equivalent securities
```

Then create a regression test from the failure.

## 25. MEASUREMENT BUG REGRESSION SUITE

Every historical measurement bug must become a permanent test.

Create:

```text
tests/regression/
```

Include tests for:

```text
close-fill leakage
filtered-panel exit pricing
price-floor benchmark contamination
staleness circularity
seed contamination
fundamental look-ahead
time-shuffled model leakage
structural duplicate rules
dead branches
unknown market-cap acceptance
liquidity-floor omission
```

The test suite must fail if any of these conditions return.

This is one of the most important deliverables of this phase.

## 26. RESEARCH INTEGRITY REPORT

Create:

```text
reports/research_integrity_report.md
```

It must answer:

```text
What can Stockbot2000 currently prove?

What can it not prove?

What biases remain?

What datasets are incomplete?

How many research trials have occurred?

What strategies are currently in forward testing?

How long have they been forward tested?

Which apparent findings were invalidated?

Why were they invalidated?

What evidence would be required to promote a strategy?
```

Do not make claims stronger than the evidence.

## 27. STOP CONDITIONS FOR SEARCH

Implement automatic search-stop conditions.

Stop additional optimization when:

```text
trial count exceeds configured threshold
```

or:

```text
research has reached diminishing returns
```

or:

```text
data quality is insufficient
```

or:

```text
validation failures exceed configured threshold
```

The system should be able to say:

```text
DO NOT SEARCH
COLLECT MORE FORWARD DATA
```

This is a legitimate output.

## 28. COMPUTE ALLOCATION

Change the default compute allocation.

Prioritize:

```text
1. Data integrity
2. Forward testing
3. Regression tests
4. Independent validation
5. Backtesting
6. Strategy search
```

Do not spend the majority of compute on evolutionary search while the
data-quality problem remains unresolved.

## 29. DOCUMENTATION

Update:

```text
README.md
ARCHITECTURE.md
PROJECT_STATUS.md
CHANGELOG.md
```

Add:

```text
RESEARCH_METHODOLOGY.md
VALIDATION_FIREWALL.md
DATA_DICTIONARY.md
EXPERIMENT_PROTOCOL.md
```

## 30. REQUIRED TESTS

Before declaring Phase 6 complete:

```text
[ ] Seed-free search works
[ ] Seed ancestry tracked
[ ] Truth set immutable
[ ] Truth set versioned
[ ] Truth set hashed
[ ] Point-in-time universe works
[ ] Fundamental availability dates enforced
[ ] Data freshness audit works
[ ] Validation firewall documented
[ ] Sealed holdout inaccessible to research
[ ] Experiment registry works
[ ] Experiments can be preregistered
[ ] Registered experiments cannot silently mutate
[ ] Stop sweep works
[ ] Forward scoreboard works
[ ] Matched-universe null works
[ ] Random control works
[ ] Multiple-testing counter works
[ ] XGBoost calibration metrics work
[ ] Signal decay analysis works
[ ] Regime analysis works
[ ] TNON regression test works
[ ] Historical measurement bug tests pass
[ ] Live mode remains disabled
```

## 31. FINAL PHASE REPORT

When complete, produce:

```text
STOCKBOT2000 PHASE 6 REPORT

STATUS:

DATA INTEGRITY:
Truth set:
Point-in-time universe:
Delisting coverage:
Fundamental availability:
Freshness:

RESEARCH:
Trials:
Seed-free search:
Multiple-testing accounting:

VALIDATION:
Holdout:
Firewall:
Random control:
Matched null:

FORWARD TESTING:
Active funds:
Days forward:
Total trades:

EXECUTION:
Simulation:
Shadow:
Live:

REGRESSION:
Tests:
Pass:
Fail:

REMAINING RISKS:

NEXT RECOMMENDED ENGINEERING PHASE:
```

Do not call the project successful merely because the infrastructure works.

The goal of Phase 6 is not to find a profitable strategy.

The goal is to make Stockbot2000 a research system whose positive result would be
substantially harder to dismiss as an artifact.

Once Phase 6 is complete, stop and report the evidence.

Do not automatically launch another million-strategy search.
