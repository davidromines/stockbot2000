# Addendum F — Independent Profitability Audit and Edge Discovery Improvement

> **Context.** Received from the owner 2026-10-13, in direct response to the reviewer
> dossier published 2026-10-12 (`claude.ai/artifact/3YFiMwNxvpXk3ycNVi2PKt`), which
> reported seven forward-trading families clearing t > 2 for the first time
> (`lab_search`, `momentum`, `kf_mean_reversion`, `bollinger_reversion`,
> `kf_seasonality`, `st_uptrend_pullback`, `st_momentum_1d`). Entered verbatim below,
> per the project's standing convention for owner/reviewer specifications (Addenda
> A–E). **Not yet built.**
>
> **Owner's resolution of the one open question the reviewer flagged (Phase F,
> §3 below), 2026-10-13:** the "at least 1% profitable" target is **not** pinned to
> one denominator. Phase F's reporting framework (net return per trade, per deployed
> dollar, portfolio-level, monthly, annualized where defensible) is built and
> reported **all four ways side by side**; no single acceptance number is set until
> real figures are in front of the owner. Do not collapse this to one metric.
>
> **How this differs from every prior addendum**: A, C, D and E were build
> directives — "build this new capability." This one is an audit directive —
> "distrust what the last audit's own machinery just reported, and prove or
> disprove it independently before building anything new on top of it." Treat it
> accordingly: Phase A (independent reproduction of the seven families) comes
> before any new code.
>
> **A known overlap worth flagging before this is actioned**: §E3 below proposes a
> "Historical Experience Learning Engine" — market situations matched by
> similarity, past-outcome distributions read off the matches. This project
> already has almost exactly that: **Stage P**, `analog.py` (1.9M-stock-day
> library, point-in-time features, nearest-neighbour search) + `analog_eval.py`
> (walk-forward: AUC 0.523, *weaker* than the existing XGBoost classifier's 0.626
> on matched rows) + the paper-tracked `analog_top` family. Stage P already ran
> almost exactly the "required research experiment" §E3 asks for, and got a
> weak result. This does not make §E3 pointless — Stage P's negative result is
> itself exactly the kind of prior evidence §E1–E3 ask to be accounted for before
> building more — but any audit of this addendum should read Stage P's existing
> result first rather than rebuilding the experiment from zero.

---

## 1. Reading the dossier

Where k = 10 and n is the number of closed paper trades. It also states that a
strategy can enter a slot without a minimum forward-evidence requirement.

That creates a problem: a strategy with an attractive backtest and almost no
forward evidence can compete for real money against a strategy with a more
substantial live paper record.

This is not necessarily a reason to stop all trading. It is a reason to
separate two decisions:

1. **Research ranking:** Which strategies are most promising?
2. **Capital eligibility:** Which strategies have earned permission to control
   real money?

Those decisions should not use the same threshold. A strategy can rank highly
as a research candidate while remaining ineligible for a live slot.

For now, I would not allow an unproven strategy to receive real capital simply
because it ranks in the top five. I would also avoid immediately promoting the
seven newly positive families. First audit the evidence; then establish a
controlled promotion process.

### C. The system has repeatedly found profits that weren't real

The dossier's defect ledger is particularly important. It records historical
results invalidated by shuffled time splits, unrealistic fills, filtered-universe
exits, misleading cheap-stock controls, and other measurement defects.

That history changes how we should evaluate the latest results.

We shouldn't ask only, "Does this strategy show a positive return?" We should
ask:

> Could the way Stockbot2000 generates, selects, simulates, or measures this
> strategy have caused it to appear profitable when it isn't?

The current synthetic reconstruction of dead companies is another unresolved
weakness. Five configurations were tried against the same real failures before
the current version was selected, so its apparent validation isn't fully
independent.

The audit should quantify how much the seven positive results change under
different survivorship assumptions. We should not simply accept the current
synthetic model because it passes its own tests.

### D. Fifteen days of real trading cannot settle the question

The account is down $1.75, or approximately 2%, since launch, according to the
report. Three of five current positions are negative, and two are
lab-discovered strategies whose raw rules are difficult to audit.

That does not prove the system cannot become profitable. Fifteen trading days
is a small sample, and open positions are not the same as completed strategy
results.

But it does establish that the current system has not demonstrated
profitability in real trading. The correct response is neither panic nor
optimism. It is to inspect the evidence and make sure new real-money decisions
are justified.

My immediate recommendation is to keep the options and crypto paths disabled,
leave the frozen evolutionary search frozen during the first diagnostic pass,
and avoid expanding real-money exposure while the current results are being
audited.

## 2. The most important investigation: why are the forward returns positive?

I would have Claude investigate the following in order.

1. **Validate the raw data.** Recompute the seven results directly from
   individual paper-trade records, not from pre-aggregated dashboard
   statistics. Verify that trades are closed, returns are calculated
   consistently, and fees and slippage are applied exactly once.
2. **Measure independence.** Calculate how many genuinely independent
   opportunities exist after accounting for ticker/date overlap, shared market
   exposure, correlated strategies, and overlapping holding periods.
3. **Recompute statistical confidence.** Use appropriate time-series and
   clustered uncertainty estimates. Account for the fact that many strategies
   were tested and only positive results are now being highlighted.
4. **Audit strategy enrollment.** Determine whether enrolling nearly 1,000 Lab
   survivors in late September introduced selection bias, a change in strategy
   composition, or any issue in the funnel's calculations.
5. **Reconcile paper and live results.** Establish whether the strategies
   showing positive paper returns could plausibly produce those returns under
   the actual live entry, exit, sizing, cash, and order-fill rules.
6. **Inspect the current ranking and slot logic.** Identify why the system
   continues to allocate real money to strategies with little forward evidence
   and whether the ranking is optimizing the wrong measure.
7. **Find the next best research direction.** If the seven families fail the
   audit, determine which existing research approach has the strongest
   evidence of potential and what experiment would provide the most
   information for the least engineering effort.

The objective is not to prove the seven families are bad. It is to establish
whether any of them can withstand an independent review.

## 3. What should "at least 1% profitable" mean?

I would explicitly tell Claude not to assume that 1% per trade is your
requirement. That would be a major difference from 1% per month, 1% per year,
or a positive return after a complete sequence of trades.

**[Owner's answer, 2026-10-13: report all of the below side by side; no single
one is the acceptance target yet.]**

The system should report all of the following separately:

- Net return per completed trade.
- Net return on deployed capital.
- Total portfolio return, including cash and open positions.
- Monthly and annualized return, where the sample supports a meaningful
  estimate.
- Maximum drawdown.
- Win rate, average win, average loss, and profit factor.
- Transaction costs as a percentage of gross profit.
- Performance by strategy family, individual strategy, market regime, and
  holding period.

A high win rate is not enough. A strategy can win frequently and still lose
money if its losses are sufficiently large.

Likewise, a positive average trade return does not guarantee positive
portfolio performance. Five strategies may be trading the same market
exposure, and frequent trading can erode the edge through costs.

My goal would be to find a repeatable, positive net-return process—not to
force the software to produce a 1% result in a particular report. Once we
establish which return measure you care about most, we can define the formal
acceptance target around it.

## 4. Claude implementation prompt

This prompt asks Claude to review the actual repository and live database,
independently audit the seven apparent positive families, fix verified
defects, improve strategy evaluation, and implement the highest-value
improvements. It also prevents Claude from responding with another lengthy
plan without doing the work.

> **Copy the entire prompt below into Claude.**

### Stockbot2000 — Independent Profitability Audit and Edge Discovery Improvement Phase

#### Mission

You are working on Stockbot2000, an autonomous quantitative trading system
that researches strategies, backtests them, paper-trades them, ranks them, and
deploys five approximately $20 strategy slots into a real Robinhood Agentic
account.

The system is operational, but it has not demonstrated durable profitability.
Your job is to determine why, independently audit the latest evidence, fix
verified defects, and implement the most promising improvements supported by
the evidence.

**This is an implementation assignment, not a request for another roadmap.**

You must inspect the actual repository, code, configuration, database,
experiment records, forward-trading records, accounting, and available live
results. Do not rely exclusively on the project dossier or the system's own
summary reports.

The owner wants to develop a system that can produce positive net returns. A
1% return is a possible benchmark to investigate, but its measurement period
and denominator have not been established. Do not hardcode a 1% return
requirement, manipulate model selection to reach it, or assume that any
historical result proves it is achievable.

Your objective is to identify a credible, repeatable trading edge and improve
the system's ability to discover and retain one.

#### Primary requirements

1. Determine whether any existing strategy has credible evidence of positive
   expected returns after costs.
2. Independently audit the seven forward-positive strategy families reported
   on October 12, 2026.
3. Identify and fix any verified calculation, data, accounting, validation,
   ranking, or execution defects that undermine the results.
4. Determine why Stockbot2000's previous strategy-discovery work has failed to
   establish durable profitability.
5. Improve the process used to discover, evaluate, rank, and promote
   strategies.
6. Investigate whether a historical-experience-learning approach could
   complement the existing research factory.
7. Produce a prioritized implementation of the highest-value improvements.
8. Preserve the integrity of the live trading system and its existing safety
   controls.

Do not manufacture profitability. Find it if the evidence supports it, explain
why it remains elusive if it does not, and build the infrastructure necessary
to improve the odds of finding it.

#### Operating rules

**Rule 1: Inspect before changing.** Read the current project instructions,
architecture, project tracker, relevant source files, configuration, tests,
and database schema before making changes. At a minimum, inspect the
implementations and callers of: `funnel.py`; `ranking.py`; `slots.py`;
`league.py` or the current strategy-identity and lifecycle modules;
`accounting.py`; `simulator.py`; `survivorship_backtest.py`; `costs.py`;
`strategy_factory.py`; `factory_pipeline.py`; `discovery.py`; `robustness.py`;
`strategy_health.py`; `paper_trading` and the current forward-trading
pipeline; the current live feedback, slot assignment, and order-reconciliation
paths; existing statistical validation and multiple-testing controls; the
append-only trial and experiment records; the current strategy enrollment
process. Use the actual module names if they have changed. Trace the relevant
computations from source data through simulated or paper-trade outcomes into
the reports and ranking decisions. Do not assume the documentation describes
the production behavior accurately.

**Rule 2: Protect the existing live system.** Stockbot2000 is already placing
real orders. During the initial investigation: do not change live execution
behavior; do not arm options or crypto; do not unfreeze the evolutionary
search; do not increase the account's capital limit; do not bypass the risk
engine, kill switches, account rules, or broker reconciliation; do not allow
research code to access the broker; do not delete or overwrite historical
experiment records; do not alter past results to make them consistent with
revised calculations. If you identify an active defect that creates a
material risk of unintended orders, duplicate orders, incorrect position
sizing, broken stops, or other unsafe behavior, document the finding and
follow the existing safety procedures. You may fix research and reporting
defects and implement isolated improvements. Changes to live eligibility,
capital allocation, or execution must be staged and tested separately. Do not
activate a material change to real-money trading without the owner's
approval. Keep the existing trading system operational unless a genuine
safety defect or dependency failure requires intervention.

**Rule 3: No more giant searches during the initial audit.** The evolutionary
search is frozen because the project has already accumulated more than 1.05
million evaluations and suffered multiple-testing and measurement failures.
Keep it frozen while investigating the existing evidence. Do not respond to
poor performance by generating another million strategies. First establish
whether the existing system is measuring results correctly, whether it can
distinguish independent evidence from duplicated observations, and whether
its ranking process rewards the right outcomes. After completing the initial
audit, recommend a controlled research experiment. Do not launch a new large
search without evidence that the research process itself is sound.

**Rule 4: Distinguish building from proving.** A completed module, passing
regression tests, a large dataset, a high AUC, or a statistically significant
backtest does not prove profitability. Report separately: what has been
implemented; what has been tested; what has been measured on genuinely
out-of-sample data; what has been demonstrated in prospective paper trading;
what has been demonstrated in real trading; what remains unknown. Do not
describe a strategy as profitable merely because it passes a historical
backtest or a conventional t-statistic threshold.

#### Phase A — Independently audit the seven positive forward families

The October 12 dossier reports these results:

| Family | Reported net return per trade | Reported t-statistic | Reported trades |
|---|---:|---:|---:|
| kf_mean_reversion | +4.86% | 2.9 | 28 |
| momentum | +2.69% | 4.8 | 331 |
| lab_search | +1.51% | 17.2 | 5,560 |
| bollinger_reversion | +1.22% | 3.2 | 150 |
| kf_seasonality | +1.18% | 7.1 | 340 |
| st_uptrend_pullback | +1.13% | 3.7 | 348 |
| st_momentum_1d | +0.47% | 3.4 | 683 |

These are leads to investigate, not accepted conclusions. The first task is to
independently reproduce every reported number from the underlying trade
records.

**A1. Trace the raw observations.** For each family, retrieve the individual
trade observations used to calculate its reported results. Establish: which
strategies belong to the family; which strategy versions generated the
trades; when each strategy was created and enrolled; when each trade was
opened and closed; whether a trade is fully closed or still open; how
position sizes are determined; whether the trade was simulated, paper-traded,
or executed with real money; how entry and exit prices were determined; which
costs were applied; how the return denominator is defined; whether multiple
records refer to the same underlying trading opportunity; whether trades from
the same strategy or related strategies overlap in time; whether the family
definition or membership changed during the measurement period. Verify that
paper trades use the intended live-data timing and that every historical
decision uses only information available at that decision time. Recompute the
family-level return from the raw observations. Do not merely call the
existing reporting function and repeat its output.

*Deliverable:* a reproducible audit report containing the reported value,
independently calculated value, discrepancy, root cause, and source records
for each family. If you cannot reproduce a result, identify precisely what is
missing or inconsistent.

**A2. Audit the return calculation.** Determine exactly what the reported
percentages mean. For each trade, inspect: gross dollar P&L; trading costs;
net dollar P&L; gross percentage return; net percentage return; capital or
notional used as the denominator; holding period; exposure over time; whether
capital is reserved for overlapping positions; whether any costs are applied
twice or omitted; whether open positions are excluded from closed-trade
statistics. Pay special attention to whether the percentage return is
measured against: the purchase value of an individual position; the capital
allocated to the strategy; the capital actually deployed; the total portfolio
equity. These measures are not interchangeable. Check for percentage returns
that are inflated by small denominators, incorrect share quantities,
inconsistent capital assumptions, or overlapping trades that could not all
have been funded simultaneously. The +4.86% mean return for
`kf_mean_reversion` and the +2.69% mean for `momentum` are especially
important to reproduce independently. Do not assume those results are wrong.
Determine whether the calculations support them.

**A3. Recalculate statistical significance.** The existing t-statistics must
not be accepted without inspecting their implementation. Determine: what
observation each t-statistic uses; whether the standard error assumes
independent trades; whether overlapping holdings create serial dependence;
whether multiple stocks are responding to the same market move; whether
multiple strategies are producing near-identical trades; whether repeated
trades in one ticker dominate the result; whether the sample includes a broad
range of market conditions; whether the results were selected after examining
many candidate strategies. Implement an independent statistical analysis
appropriate to the actual observations. Where applicable, compare:
conventional trade-level standard errors; time-series or block-bootstrap
confidence intervals; clustered uncertainty estimates by ticker and date;
sensitivity to overlapping holding periods; performance across distinct
calendar periods; performance with highly correlated strategy variants
grouped together. Choose methods that fit the data structure; do not
mechanically apply every method to every dataset. For `lab_search`,
explicitly calculate the number of unique ticker/date opportunities,
overlapping trades, distinct strategy identities, and effective independent
observations. Quantify how much its reported t-statistic changes when
duplicate and correlated exposures are handled appropriately.

*Important:* a t-statistic above 2 is not sufficient by itself. Also evaluate
effect size, uncertainty, economic significance after costs, stability over
time, and the extent of multiple testing.

**A4. Account for multiple testing and selection bias.** Inspect the complete
research history and determine how many candidate strategies and families
were evaluated before these seven results were highlighted. Check whether:
these families were selected because they performed well; other families
with negative results were excluded from the report; strategies share
templates, seeds, parameters, or rule components; hundreds of variants are
effectively tests of the same hypothesis; the current statistical report
ignores the number of hypotheses examined; the existing deflated-Sharpe or
multiple-testing machinery is correctly connected to the forward-trading
pipeline. Use the project's actual experiment ledger. Do not invent a precise
number of independent tests from the raw strategy count. Estimate the degree
of dependence and explain uncertainty. Produce a multiple-testing-aware
assessment of each family. Do not reuse the sealed 2023+ holdout for further
tuning if the project has already consumed it for that strategy. Preserve the
distinction between historical research data and a genuinely prospective
evaluation.

**A5. Investigate the September enrollment event.** The report states that
nearly 1,000 Lab validation survivors were enrolled in late September and
that this materially increased the number of forward observations. Determine
whether this event affected: family composition; strategy-selection bias;
duplicate or correlated trade records; the definition of the forward sample;
the t-statistic calculations; the timing of strategy enrollment; the
interpretation of paper-trading results. Compare the results for strategies
enrolled before and after the event, where the records permit a fair
comparison. Check whether enrollment was based on information that could
itself predict the outcomes being measured. Do not simply exclude
inconvenient trades. Explain the implications of each valid cohort
definition.

**A6. Produce a verdict for each family.** Assign each family a provisional
evidence classification: **Invalid measurement** (the result cannot be
trusted because of a verified defect); **Unresolved** (the evidence is
insufficient or materially dependent on assumptions); **Promising but
unproven** (the result survives the initial audit but lacks adequate
independent confirmation); **Eligible for prospective validation** (the
result passes the research-integrity checks and is suitable for a
controlled, forward-looking evaluation); **Supported by independent
evidence** (multiple genuinely independent tests support positive net
returns). Do not label any family proven profitable merely because it
receives the final classification. Explain the evidence behind every
classification.

#### Phase B — Determine why the system has not established profitability

Do not assume that the problem is simply insufficient data, insufficient
compute, or a lack of strategy ideas. Investigate the complete
discovery-to-trading pipeline.

**B1. Build a quantitative strategy funnel.** Produce counts and performance
statistics for every meaningful stage, including: hypotheses generated;
distinct strategy families represented; distinct strategy identities and
versions; candidates successfully backtested; candidates passing
execution-cost requirements; candidates passing survivorship checks;
candidates passing robustness checks; candidates passing out-of-sample
evaluation; candidates admitted to forward paper trading; candidates with
sufficient forward observations; candidates with positive independently
calculated net returns; candidates that remain positive after correlation and
multiple-testing adjustments; candidates eligible for capital allocation;
candidates assigned to real-money slots; candidates with positive
completed-trade P&L in the real account. Include the number rejected at each
stage and the primary reason for rejection. Report both strategy counts and
family counts. Do not let thousands of parameter variants masquerade as
thousands of independent hypotheses. For each stage, quantify: gross and net
returns; costs; drawdown; trade count; unique ticker/date count; holding
periods; market-regime coverage; the distribution of results, not only the
mean. If the existing data cannot support a particular calculation, identify
the missing fields and implement the necessary instrumentation.

**B2. Identify the primary failure mode.** Determine which of these
explanations is best supported by the evidence: the research factory
generates weak hypotheses; the research factory repeatedly generates similar
hypotheses; backtests contain residual measurement problems; the market data
or universe is insufficient; survivorship treatment distorts the results;
historical positive results do not survive out-of-sample testing; the
validation process is incorrectly implemented; validation is overly
restrictive or rejects plausible strategies for the wrong reasons; costs
erase otherwise promising gross returns; strategies have a short-lived edge
that decays; strategies only work in specific market regimes; the ranking
function selects strategies that are not the best prospective candidates;
paper trading does not reproduce the real execution process; live position
sizing, capital constraints, or holding periods undermine the apparent edge;
the system's evaluation metrics do not correspond to the owner's actual
objective. Several causes may coexist. Rank the causes by measured impact,
confidence, and cost to address. Do not declare a root cause simply because
it sounds plausible.

**B3. Audit the current ranking formula.** Inspect the actual ranking code
and its production inputs. The documented formula blends backtest and paper
returns using a prior weight of 10: `score = (10 × backtest + n × paper) /
(10 + n)`. Verify that this matches production behavior. Evaluate whether the
formula: treats correlated observations as independent; gives an unproven
backtest too much influence; rewards a high average return from a tiny
sample; ignores uncertainty in the estimated return; compares different
holding periods unfairly; fails to distinguish strategy quality from market
exposure; fails to penalize unstable results or excessive turnover; allows
related variants to occupy multiple slots; rewards results that disappear
under alternative cost assumptions; creates unintended incentives in strategy
discovery. Do not change the ranking simply to favor the seven positive
families. Develop a better selection method based on the evidence. Compare it
against the current formula using chronological evaluation and a clearly
defined objective.

#### Phase C — Improve capital eligibility and portfolio selection

Research ranking and real-money eligibility must be distinct. The research
league should be able to explore promising strategies without automatically
assigning them real capital.

**C1. Design an evidence-based eligibility gate.** Propose and implement a
configurable eligibility framework that considers: correctness of the
underlying data; strategy provenance and version; positive net performance
under realistic execution assumptions; adequate sample size and independent
opportunity count; statistical uncertainty; multiple-testing adjustments;
stability across time periods; sensitivity to costs; sensitivity to
survivorship assumptions; correlation with existing strategies; maximum
drawdown and downside exposure; degradation and decay; out-of-sample and
prospective validation status. Do not make a universal 20-trade threshold the
sole definition of proof. Twenty highly correlated trades may provide less
information than a smaller number of independent observations. Likewise, do
not require an arbitrary number of trades without considering the effect
size and variance. Use configurable requirements supported by statistical
reasoning and the actual risk profile.

*Live deployment restriction:* implement and test the gate in research,
simulation, or shadow mode first. Generate a report showing which current
strategies would qualify and why. Do not silently remove current live
strategies or modify production allocation behavior. Present the proposed
effect on live eligibility for approval.

**C2. Make strategy selection comparable.** The current system compares
strategies with different holding periods. Investigate whether the ranking
function compares a 1-day strategy, a 5-day strategy, a 60-day strategy, and
other strategies on a defensible basis. Report at least: net return per
trade; net return per dollar deployed; return per unit of time or exposure;
drawdown; turnover; costs; capital utilization; risk-adjusted performance,
with appropriate uncertainty; portfolio-level contribution after accounting
for correlation. Do not simply annualize short samples and present the
result as reliable. Develop a common comparison framework that does not
reward a strategy merely because it trades more often or holds more
overlapping positions.

**C3. Introduce correlation-aware slot evaluation.** Analyze the existing
five slots and their current strategies. Determine whether the system is
effectively buying the same underlying exposure five times. Measure
correlations between strategy returns and their holdings, accounting for
overlapping positions and common market exposure. Compare the current slot
selection with a portfolio-aware alternative that considers: expected net
return; return uncertainty; correlation; drawdown; sector and ticker
concentration; holding periods; cash and settled-funds constraints;
execution feasibility. The goal is not to maximize diversification for its
own sake. The goal is to determine whether a portfolio-aware allocation
improves the expected net outcome relative to the current top-five method.
Implement the analysis and a shadow comparison before proposing live changes.

#### Phase D — Reassess survivorship and execution assumptions

**D1. Synthetic dead-company histories.** The project uses synthetic
historical paths for thousands of missing delisted companies. Multiple
generator configurations were tried against the same set of real failures
before the current configuration was selected. Do not assume the synthetic
reconstruction is accurate because it passes its own validation tests.
Determine how much the seven positive families and the current ranking
depend on the synthetic data. Compare, where supported by the code and data:
the available real-price universe; the current synthetic reconstruction; the
existing worst-case treatment; alternative reasonable assumptions for
unavailable histories. Report strategy-level and family-level changes in net
performance, drawdown, ranking, and eligibility. Make explicit where the
conclusions are not identifiable from the available data. Do not invent
historical prices or represent synthetic observations as real market
records. Recommend whether paid point-in-time delisted data would materially
improve the decision. Quantify the expected benefit to research integrity
before recommending the expense.

**D2. Execution and cost realism.** Audit the entire lifecycle: signal
generation → risk approval → order submission → fill confirmation → exit →
accounting → strategy feedback. Check that simulated and paper trades match
the actual live rules for: entry timing; next-open fills; stop orders and
gaps; exit timing; spread; slippage; fees; position sizing; partial fills, if
applicable; unfilled orders; cash availability; overlapping positions; T+1
settlement and account constraints; closed versus open P&L. Check for hidden
lookahead, especially where daily signals are calculated from completed bars
and trades are entered at the next available price. Identify any difference
between the simulator, paper-trading pipeline, and real execution engine that
could materially change the strategy ranking. Fix verified defects with
regression tests.

#### Phase E — Improve discovery rather than just increasing search volume

After the audit identifies the dominant failure modes, improve the research
process. Do not immediately unfreeze evolutionary search.

**E1. Audit the existing knowledge factory.** The Knowledge Strategy Factory
is now complete and contains documented strategies and published factors.
Determine whether it is generating genuinely different economic hypotheses or
mostly reproducing variants of the same factors. For each candidate, track:
original source; economic rationale; exact reproduced rule; differences from
the original; data availability at decision time; known limitations; related
strategy families; research lineage; prior testing history; whether the
hypothesis was specified before evaluation. Prioritize candidates that are
economically distinct, implementable, and testable with existing data. Avoid
generating large numbers of nearly identical parameter variants merely to
increase the apparent size of the research library.

**E2. Build a research hypothesis scorecard.** Implement a scorecard that
helps determine which research ideas deserve testing. Possible dimensions
include: economic rationale; evidence in prior literature; data availability
and quality; likelihood of survivorship or lookahead bias; sensitivity to
transaction costs; distinctiveness from existing hypotheses; feasibility at
the current account size; expected holding period; data requirements; ease of
independent validation. The scorecard must not substitute for empirical
validation. Use it to prioritize experiments and explain why a hypothesis was
selected, rather than to claim it is profitable.

**E3. Investigate the Historical Experience Learning Engine.** Evaluate the
following proposed approach as a complementary research method. *(See the
context note at the top of this document: Stage P / `analog.py` /
`analog_eval.py` already built and ran a close version of this and found it
weak — AUC 0.523, worse than the existing classifier's 0.626 on matched
rows. Read that result before re-running the experiment from scratch.)* The
system would: construct historical market observations at particular dates;
record the stock's state using only information available at that date;
simulate a predefined trade with realistic entry, exit, and costs; record
both profitable and unprofitable outcomes; find historical situations similar
to current market conditions; estimate the distribution of subsequent returns
for those situations; test whether those historical analogues improve
out-of-sample trading decisions. The experience library should contain
historical context, not just chart images. Candidate features include:
multi-period price returns; trend and moving-average relationships;
volatility; volume and liquidity; gaps; drawdown; market and sector
conditions; market breadth, where available; point-in-time fundamental
information, where appropriate; entry conditions; simulated exit outcomes;
net return; maximum adverse excursion; maximum favorable excursion; holding
period. Do not assume that visually similar charts imply the same expected
return.

*Required research experiment:* before building a large subsystem, implement
a small, reproducible experiment using existing data and infrastructure.
Compare: a simple baseline that does not use historical similarity; a
similarity-based method that searches past observations; if justified, a
basic predictive model using the same information. Use chronological
train/validation/test boundaries. Do not randomly split overlapping
observations across training and test sets. Prevent future information from
entering historical feature vectors. Apply realistic costs and
next-available entry prices. Include losing historical outcomes, not only
successful trades. Measure whether the similarity method improves
out-of-sample net returns, uncertainty, and risk relative to the baseline.
If it does not, explain why and do not expand the subsystem merely because
the concept is appealing. Reuse the existing market data, simulator,
accounting, and validation infrastructure wherever possible.

#### Phase F — Define profitability measurements correctly

The owner has expressed a desire to find a strategy capable of producing at
least a simple 1% profit, but the intended measurement period and denominator
have not been finalized. **Resolved 2026-10-13: report all four below side by
side; do not pin the acceptance criteria to one until real figures are seen.**
Do not assume that 1% per trade, per month, per year, or per deployed dollar
are interchangeable.

Implement or verify a reporting framework that separately measures: net
return per completed trade; net return on deployed capital; net portfolio
return, including cash and open positions; monthly returns; annualized
returns where statistically defensible; maximum drawdown; win rate; average
win and average loss; profit factor; trading costs relative to gross profit;
turnover and capital utilization; performance by strategy, family, and market
regime.

Use the same accounting definitions throughout backtesting, paper trading,
and live reporting. Clearly label each result with its denominator,
measurement period, sample size, and uncertainty. The system must never
optimize for a positive percentage without considering whether the resulting
trades could have been funded and executed under the actual portfolio
constraints. Do not manipulate the strategy selection process to reach a
target. If the evidence suggests that a 1% return is unsupported under the
tested conditions, report that honestly and identify the most promising next
experiment.

#### Phase G — Fix verified defects and implement the highest-value improvements

Once the initial audit is complete, rank the identified improvements by:
expected impact on decision quality; confidence in the diagnosis; engineering
effort; data requirements; risk of disrupting existing behavior; ability to
validate the change independently. Then implement the highest-value items
that can be safely completed now. Do not stop after producing a list of
recommendations.

*Required implementation principles:* reuse existing architecture; avoid
duplicate backtesting, ranking, accounting, and risk systems; preserve
append-only historical records; version changes to evaluation methods;
record the provenance of every strategy and its results; add regression tests
for every verified defect; add tests for realistic edge cases, not just
successful examples; keep new research isolated from broker access; make new
selection methods shadow-only until their value has been demonstrated; do
not weaken existing research-integrity checks to increase the number of
accepted strategies; do not make unapproved live-trading changes. If an
existing module is correct, do not rewrite it simply to create visible
activity. If an apparent defect cannot be reproduced, document it as
unresolved rather than changing code speculatively.

#### Phase H — Deliverables

Produce the following artifacts in the project repository, adapting filenames
to the project's existing conventions.

1. **Independent profitability audit** — the independently reproduced results
   for all seven families; any discrepancies in return calculations;
   corrected uncertainty estimates; correlation and effective-sample-size
   findings; multiple-testing considerations; the impact of September
   enrollment; survivorship sensitivity; execution and cost discrepancies;
   the evidence classification for each family.
2. **Root-cause analysis** — a ranked explanation of why the current system
   has not demonstrated profitability. For each finding: evidence; root cause
   or uncertainty; financial or research impact; confidence; recommended
   corrective action; whether the action was implemented.
3. **Research funnel report** — a reproducible report showing candidate
   counts, rejection reasons, and performance at every stage from hypothesis
   generation through real trading.
4. **Ranking and eligibility assessment** — a comparison of the current
   ranking method with the proposed improvements, including a shadow-mode
   report showing how strategy selection would change.
5. **Historical Experience Learning Engine experiment** — a small reproducible
   baseline-versus-similarity experiment with chronological evaluation,
   realistic costs, and a clear decision on whether the approach merits
   further investment.
6. **Implemented fixes** — code changes, database changes if required,
   configuration changes, and regression tests for the highest-priority
   verified defects.
7. **Updated operational report** — current live account state; current open
   positions and their actual unrealized P&L; realized P&L; total equity
   change since launch; results by current strategy assignment; research
   results separately from live results; any differences between the latest
   dossier and the current database. Do not add the P&L of unrelated slot
   assignments together in a way that misrepresents the performance of the
   current occupants. Also provide the actual account-level performance,
   because the owner needs to understand the fund's total outcome in addition
   to individual strategy results.
8. **Implementation handoff** — update the project tracker and relevant
   documentation. List: files created; files modified; database schema
   changes; tests added; tests executed and results; verified defects fixed;
   findings still unresolved; commands to reproduce the audit; commands to
   run the new experiment; any scheduled jobs that need to be configured; any
   remaining manual approval steps; any changes that would affect live
   trading and therefore require owner approval. Use one commit per coherent
   change, following the existing project conventions. Do not use
   `git commit -a`.

#### Acceptance criteria

This phase is complete only when the following conditions are met.

**A.** The seven forward-positive families have been independently audited.
Their reported results can either be reproduced or the discrepancies are
documented and explained.

**B.** The statistical evidence is more defensible. The analysis accounts for
correlated observations, multiple testing, and the actual structure of the
forward-trading sample.

**C.** The root causes are prioritized by evidence. The project has a
quantitative explanation for where strategy candidates are being lost, why
the previous discovery process failed to establish profitability, and which
problem should be addressed first.

**D.** The system can distinguish research promise from live eligibility. The
proposed eligibility framework is implemented and tested in isolation or
shadow mode, with no unapproved change to production allocation.

**E.** At least one concrete improvement has been implemented. The phase must
deliver verified code, tests, reporting, or experimental infrastructure—not
only recommendations.

**F.** The historical-experience approach has been evaluated fairly. The
initial experiment is reproducible and uses chronological validation,
realistic costs, and an appropriate baseline.

**G.** The existing safety architecture remains intact. No unapproved
options, crypto, evolutionary-search, capital-limit, risk-engine, or
execution changes have been activated.

**H.** The final report is candid. If none of the strategies survives the
audit, say so. If one or more appear promising, explain exactly what evidence
supports that conclusion and what remains unproven. Do not claim success
merely because tests pass or because the research process produces a
positive number.

#### Final instruction

Work in two passes:

**Pass 1 — Audit:** Independently reproduce the current results, identify the
dominant failure modes, and establish which findings are credible.

**Pass 2 — Improve:** Fix verified defects and implement the highest-value
improvements supported by Pass 1.

Do not ask the owner to choose between technical approaches that you can
evaluate from the repository and available data. Make the best evidence-based
decision, implement what can be done safely, and clearly identify any
decision that genuinely requires owner approval.

The ultimate objective is to improve Stockbot2000's ability to discover and
exploit a repeatable trading edge—not to produce more strategies, more
infrastructure, or more optimistic reports.

## 5. Reviewer's recommendation for what comes after this phase

I would make the next decision based on three outcomes:

| Audit outcome | What we should do next |
|---|---|
| One or more families retain positive net performance after the independent audit | Put the strongest candidates through a controlled prospective validation process, then consider evidence-based promotion. |
| The reported profits largely disappear after correcting calculations or accounting for dependence | Fix the underlying measurement problem and rebuild the research funnel before searching for more strategies. |
| The numbers are calculated correctly, but candidates consistently fail out-of-sample | Change the hypothesis-generation and evaluation process. Investigate whether the system is mostly finding market exposure, short-lived patterns, or noise. |

I would not unfreeze evolutionary search simply because the audit finds no
surviving edge. I would first want to know whether the Knowledge Strategy
Factory, the existing conventional strategies, or the proposed Historical
Experience Learning Engine offers the most promising next experiment.

And I would not immediately promote the seven positive families based on
their reported t-statistics.

### One important distinction

There is a difference between saying "the system has not found a profitable
strategy yet" and saying "the system cannot find a profitable strategy." The
current results establish the former, not the latter.

The way forward is to make each experiment more informative: fewer redundant
hypotheses, stronger independent evaluation, accurate accounting, and a
selection process that rewards evidence of prospective net profitability
rather than historical backtest performance.

The next milestone should not be another completed project phase. It should
be the first strategy whose positive performance survives independent
scrutiny and continues to hold up in prospective evaluation.

---

## Appendix — additions from the ideas review (Claude, 2026-10-13; NOT part of the reviewer's text above)

The owner shared sixteen outside posts, papers and prompts on 2026-10-13. Each is
reviewed in `docs/IDEAS_LOG.md` (numbered #1-#16); most were declined. What was
adopted is listed here, attached to the phase it belongs to. Everything is read-only
or shadow-only, gates nothing, changes no live behaviour and consumes the trial ledger
honestly (every extra variant or market counts). **Nothing below is built.**

### Leads found while reviewing (inputs to Phase A, verified by a query, not yet fixed)

| # | Lead | Evidence | Phase |
|---|---|---|---|
| L1 | **Corporate actions booked as losses.** Paper entry prices are stored as traded; the prices table is later back-adjusted, so a spin-off or split during a hold produces a phantom move | 4 `CTVA` trades in 4 funds, entry 78.5-79.5, exit 12.57 within a week (about -84%); prices table shows 11.7 on 09-28 | A1, A2, D2 |
| L2 | **Duplicate observations.** One trade per fund for the same ticker and dates | `KOD` +170% (09-24 to 09-28) appears 3 times in `lab_search` alone; `lab_search` is now 8,791 trades in 566 funds | A3 |
| L3 | ~~Recompute does not match the funnel~~ **RETRACTED 2026-10-13.** The funnel's formula is identical to a plain recompute (`funnel.forward_families` reproduces momentum +2.04%, n 416, t +4.2 exactly). The figures first compared were a week-old snapshot (momentum n was 331 then). The real finding: the reported set moved in a week as trades accumulated (kf_seasonality +1.18% t 7.1 -> +0.46% t 2.8; st_uptrend_pullback t 3.7 -> 1.5; bollinger_reversion t 3.2 -> 1.9; st_momentum_1d t 3.4 -> -1.5; turn_of_month new at t 10.3) | A1 |
| L4 | **No deflation outside the frozen Lab ladder.** `promote.py` and `multiple_testing.py` hold the maths; `funnel.py`, `ranking.py`, `slots.py`, `factory_pipeline.py`, `strategy_health.py` use none | grep, entry #8 | A4, B3 |
| L5 | **t-statistic assumes independent trades** (`funnel.py` line ~450: mean / (sd / sqrt n)) | code | A3 |
| L6 | Noise-only 95% t thresholds: 3.25 (N = 88 families), 3.43 (170), 3.97 (1,405), 4.93 (127,652 unique Lab structures), 5.32 (1M). Of the seven reported t (2.9, 3.2, 3.4, 3.7, 4.8, 7.1, 17.2) two or three sit inside the luck range even at N = 88, before the dependence correction | computed, entry #8 | A4 |
| L7 | **No LEAP-length option data**: the longest expiry in `option_quotes` is 77 days | query, entry #9 | D, E |
| L8 | Breakout-on-volume families are the most negative forward group (-4% to -5% per trade, t -7 to -19, iid so overstated); the closest "tight base" family is also negative (-3.4%) | query, entries #4, #5 | A, E |

### Additions by phase (P1 = fold into the first audit pass; P2 = after the audit; P3 = only if the evidence asks for it)

| Phase | Addition | Source | Priority |
|---|---|---|---|
| A1-A2 | Recompute from raw `paper_trades`; check corporate actions (L1), duplicates (L2), and why the funnel differs (L3) | #4 | P1 |
| A3 | Clustered / block-bootstrap uncertainty; effective n via `multiple_testing.effective`; Monte Carlo reshuffle of each family's trade order | #8 | P1 |
| A4 | A **deflation column** (not a gate) in funnel and ranking reports for three values of N; deflate on per-period returns with skew and kurtosis from the same series; clean the data first (L1), because the tail terms are meaningless with corporate-action artefacts | #8 | P1 |
| A4 | **Pass-rate sanity line**: share of strategies passing next to the share a random-rule control passes (`random_control.py`) | #2 | P1 |
| B3 | **Calibration of the ranking**: predicted per-20-session return vs realised, as reliability bins plus a Brier-style score; extend `degradation.py`, `live_feedback.py`, `model_calibration.py` | #1 | P1 |
| F | Maximum drawdown beside every return measure; **ask the owner once for the drawdown they can tolerate** (today only the 35% kill switch and $15 / 15% daily loss exist). No return target set, per the 2026-10-13 ruling | #14 | P1 |
| H | Report rules: every figure with its source query and date; facts, inferences and unknowns in separate labelled sections; a closing **"What could be wrong"** section; nightly review stays measure-only, never auto-rewrites live logic | #1, #12 | P1 |
| D1 | **Credit-event survivability**: each slot holder and the seven families under the existing worst-case survivorship mode (`zero`) beside the as-is score | #3 | P2 |
| D2 | Intraday simulation rules for `intraday.py` (limit fills only on a trade-through, adverse move first inside a bar, slippage on stops and market exits) before any same-day result is believed | #7 | P2 |
| F / regimes | Descriptive regime reports, no gating: 10-year-yield trend and dollar trend (free FRED series); SPY above its 21 and 50 EMA; 15-day Kaufman efficiency ratio (choppy <= 0.35). Few independent episodes: read as description only | #3, #5, #7 | P2 |
| G | **Drawdown playbook + stress replay**: write what the system does at SPY -10 / -20 / -30% and replay the five slots through 2008, 2020, 2022 with existing windows | #3 | P2 |
| E | Count each documented strategy's **publication year** in `knowledge_library`; one pre-declared out-of-universe replication per post-publication pass, every market tried added to the trial ledger | #2 | P2 |
| E | One pre-declared reproduction of a daily-bar momentum-breakout (above 21 and 50 EMA, ATR contraction, close above prior N-day high on volume, exit on a close below the 21 EMA); needs EMA features on the daily panel first | #5 | P3 |
| E | Closing-basis EMA-trail exits added to `exit_rules`, same adoption rule as P2 | #5 | P3 |
| E | Limit-entry experiment on the reversion families (prior close - k x ATR, filled only on a trade-through, missed trades counted, one pre-declared k) | #7 | P3 |
| E | Single pre-declared hypotheses, no variants: "chip" volume-at-price cost clustering; mega-cap leadership breakdown | #3, #4 | P3 |
| E3 | The Historical Experience Learning Engine: read Stage P's result (AUC 0.523) first; write up rather than rebuild | #1, reviewer | P3 |
| Data | LEAP-length option chains and an ETF fund-flow source, only after the underlying stock signal has an audited edge | #4, #9 | P3 |
| If search is ever unfrozen | Niche quotas by structure family, adverse-first intrabar ordering, a one-look holdout instead of a reused split | #11 | P3 |

### Declined (reasons in the ideas log)
Futures and intraday trading (no futures access; 3 day trades per 5 sessions), limit orders on fractional shares (dollar orders are market-only), LEAPS and Kelly sizing now, crypto research and crypto strategies (`allow_crypto` off, ~1.9% round trip), theme and stock picks, nightly self-rewrite of live logic, LLM-generated backtests or performance numbers, running outside open-source trading code, paid courses, third-party plugins (`tradingkit`, AgentKit).

### Suggested order
1. Phase A1-A3 for `lab_search` and `momentum` as one read-only script (recompute, dedupe, clustered t, effective n), including L1-L3.
2. A4 deflation columns and B3 calibration, then the Phase F reporting framework.
3. C1 eligibility gate in shadow mode; D1 and the regime reports.
4. Phase E items only after the audit says which of the reviewer's three outcomes applies.


### First pass of Phase A1-A3 (2026-10-13, `audit_forward.py`, read-only; full tables in `reports/audit_forward_2026-10-13.md`)

New verified findings (each reproduced by a query or by reading the code; none acted on):

| # | Finding | Evidence |
|---|---|---|
| V1 | **The paper engine fills at the signal-day close.** A position is entered at `row["close"]` of the session that produced the signal and exits are booked at the close that triggers them (`paper_trading.py` lines 616 and 564). The simulator and backtest moved to next-open fills on 2026-09-15; the paper engine did not. Entry price equals that day's close on 88-99% of rows | code; rows |
| V2 | **`pnl_pct` is the GROSS price move.** It equals (exit / entry - 1) on 100% of rows and net P&L / notional on 0%. Modelled costs (0.15-0.18% of notional per round trip) are stored but not deducted, so every "net per trade" figure in the funnel and the 10-12 dossier is gross | rows |
| V3 | **Few independent days.** The seven families have 5-19 distinct entry dates (`lab_search` 10, `momentum` 18) in about 16 sessions of one market; with a date-block bootstrap no family supports a label above "unresolved" | script |
| V4 | **Early positives faded.** `momentum` entries before 09-25: +3.96% (n 204), on or after: -0.16% (n 212); `lab_search` before 10-01: +1.41%, after: +0.52% (net, same-close) | script |
| V5 | **Corporate actions confirmed, smaller than first feared.** With the corrected check (recorded price vs adjusted close on that date, > 1.5%): `lab_search` 81 of 8,791 rows (CTVA among them; dividend-sized adjustments such as VZ, CMCSA also trip it), `momentum` 9 of 416, others 0-11 | script |

Honest-fill recompute (net of modelled cost, next-open entry and exit on adjusted prices, rows that have a next-open price):

| family | reported (gross, same-close) | honest net, mean | iid t (funnel -> honest) | date-cluster t / ticker-cluster t | independent entry dates | 95% date-block bootstrap |
|---|---:|---:|---|---|---:|---|
| lab_search | +1.30% | +0.90% | +18.5 -> +11.9 | +2.2 / +4.4 | 10 | [-0.25%, +1.40%] |
| momentum | +2.04% | +1.71% | +4.2 -> +2.9 | +1.4 / +2.0 | 18 | [-1.03%, +3.78%] |
| kf_mean_reversion | +1.22% | +1.71% | +2.2 -> +2.8 | +2.4 / +1.3 | 7 | [-0.70%, +3.12%] |
| bollinger_reversion | +0.39% | +0.45% | +1.9 -> +2.2 | +1.1 / +0.9 | 5 | [+0.03%, +2.45%] |
| kf_seasonality | +0.46% | +0.11% | +2.8 -> +0.7 | +0.3 / +0.3 | 8 | [-0.70%, +0.62%] |
| st_uptrend_pullback | +0.36% | +0.19% | +1.5 -> +0.8 | +0.1 / +0.3 | 8 | [-2.58%, +1.99%] |
| st_momentum_1d | -0.20% | -0.39% | -1.5 -> -3.3 | -0.9 / -1.3 | 10 | [-1.26%, +0.42%] |
| turn_of_month (new at t 10.3) | +3.81% | +1.86% | +10.3 -> +5.5 | not meaningful | 2 | not meaningful |

Provisional label for all eight: **Unresolved (fewer than 20 independent entry dates)**. The effective sample for `lab_search` is
about 270 trades, not 7,941 (design effect ~29), and its t falls from 18.5 to about 2.2 once entry dates are treated as the unit.
Not a verdict that the families are noise: a result that survives next-open fills, costs and clustering over a longer window would still count.

**Phase G items from this pass — APPROVED and DONE 2026-10-13 (G1-G3), drawdown tiers built on a branch:** see the status line after the list.

**Phase G items proposed from this pass:**
G1 add next-open fills to the paper engine as a restatement beside the originals (accounting version bump), never overwriting;
G2 label `pnl_pct` as gross everywhere and report net in `funnel.py`, the dossier and the daily report;
G3 route the funnel's family statistics through the clustered / deduplicated calculation and show the deflation column.

**Done 2026-10-13 (owner approved):**
G1 `restate_paper.py` writes `paper_trades_restated` (version `v2_next_open`; next-open entry and exit on the adjusted series, minus the engine's modelled
round-trip cost) beside the unchanged `paper_trades`; idempotent; wired into `daily.sh` as stage `[9k0/10]`; 18,730 of 20,294 closed trades restated, the rest
exit on the newest bar and wait. G2/G3 `funnel.py` `forward_families` now returns gross, net, honest, date- and ticker-clustered t, independent entry dates,
bootstrap interval, the 88-family luck level and a label (statistics in the new `forward_stats.py`, shared with `audit_forward.py`); `significant` requires a
clustered t >= 2 over >= 20 entry dates; the hard-coded conclusions in `eight_questions` (named families and t-statistics written into the code, plus unformatted
`{need_05}` placeholders) are replaced by text computed from the data. Result on today's data: 0 of 43 families pass; the iid-on-gross test passes 6.
Caveat recorded in the report: trades that exit on the newest stored bar have no next-open price yet and are mostly stop-outs, so a thin honest column is
biased upward until they can be restated (e.g. `earnings_yield`: gross -3.80%, honest +1.34% on 32 of 46 rows).
**Drawdown tiers** (owner-approved 10/20/35): `drawdown_tiers.py`, `config/risk.yaml` keys `drawdown_notice_percent` and `drawdown_review_percent`, an entries-only
check in `risk_engine.py`, a once-a-day-per-tier Telegram message from the LIVE heartbeat in `slot_trader.py`; 22 tests; **merged to main 2026-10-13 05:15 UTC**
(owner-approved; checks run after the merge; acceptance checklist 27/27). The 35% kill switch is unchanged.

**Phase A4-A6 done 2026-10-13 (owner: "Phase a go"; read-only).** A4: `audit_selection.py` shows the count that applies to a forward family claim is the number of
families compared (88 defined, 41 with >= 20 trades, about 28 effective independent tests), not the Lab's 1.05 M trials; Holm / Benjamini-Hochberg / max-T leave no family
significant. A5: the Lab survivors were enrolled 09-27 with start date 09-24 (a replay of the 09-24 signals using only data through 09-24); enrollment did not depend on
outcomes, but 2,886 `lab_search` trades are replay (+1.63 % vs +0.48 % prospective). A6: per-family verdicts in `docs/AUDIT_A6_FAMILY_VERDICTS.md`; the locked prospective
test is `forward_families_prospective` v1 (`prospective_eval.py`). Full tables: `reports/audit_selection_2026-10-13.md`.

**Phases B and C done 2026-10-13 (owner: "Do phase b and c"; read-only / shadow).** B1/B2 `audit_pipeline.py`: the funnel to real money and ranked causes (too few independent observations first). B3 `audit_ranking.py`:
production matches the 10:n blend in structure but uses the unseen-window result as the prior for 21 % of rows and zero for the 41 % that are Lab-search funds; `n` counts open positions (median 20 trades from one entry date among the top 50);
the stored score ranks later returns worse than the backtest or a date-counting estimator; one shared +163.85 % trade (KOD) sits in three slots' paper funds. C1 `capital_gate.py`: a 13-criterion shadow gate, 0 of 384 eligible;
daily stage `[9k1]`. C2/C3 `audit_portfolio.py`: the 20-session scaling is rank-identical to per-trade return; the five live positions have a beta of 2.27 and a diversification ratio of 1.41; shadow top-five selection
is indistinguishable from the pool. Findings and the owner's decisions: `docs/AUDIT_BC_FINDINGS.md`.
