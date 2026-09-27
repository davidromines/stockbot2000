# Stage T — Diagnostic Phase: Why Can't We Find a Durable Trading Edge?

**Entered 2026-09-27 by the owner** ("add this to the tracker"). Recorded,
not built.

The specification below is the owner's text, verbatim. The only edits are
markdown heading markers on section titles and list markers; no wording is
changed. Tracked in the roadmap as **Stage T** (the next free letter).

---

The owner's specification, verbatim:

# Stockbot2000 — Diagnostic Phase: Why Can't We Find a Durable Trading Edge?

## Mission

We need to answer a fundamental question about Stockbot2000:
Is the system actually unable to find simple, positive trading performance — or is it finding apparent performance and then correctly rejecting it as non-robust?
Do NOT assume the answer.
Do NOT assume that we need a 1%, 3%, 10%, or any other arbitrary return target.
Do NOT redesign the system yet.
This phase is specifically intended to diagnose where the strategy population is failing.
The objective is to determine whether the problem is:

1. insufficient strategy hypotheses,
2. insufficient diversity of hypotheses,
3. poor search methodology,
4. excessive parameter optimization,
5. overly aggressive validation,
6. unrealistic execution assumptions,
7. survivorship problems,
8. overfitting,
9. insufficient forward evidence,
10. weak strategy ideas,
11. or some combination of these.

## 1. THE CORE QUESTION

Stockbot2000 has already demonstrated that it can discover historical strategies with apparent positive performance.
The evolutionary search ran approximately 1,049,967 trials.
There have also been strategies whose apparent profits disappeared when more realistic assumptions were introduced.
Therefore the question is NOT:
"Can the system find something profitable in a backtest?"
We already know it can.
The real question is:
At what stage does apparent performance disappear, and why?
We need to measure this explicitly.

## 2. DO NOT CHANGE THE TRADING SYSTEM YET

This is a diagnostic implementation phase.
Do NOT:

* restart the frozen evolutionary search;
* create another million-trial parameter search;
* loosen validation gates merely to produce profitable results;
* tighten validation gates merely because results are disappointing;
* change the live five-slot architecture;
* change live risk controls;
* change the Robinhood execution system;
* introduce an arbitrary return threshold;
* declare the current system successful or unsuccessful without evidence.

Do not optimize the answer.
Find the answer.

## 3. BUILD THE STRATEGY FUNNEL

Create a complete diagnostic funnel showing how many strategies survive each stage.
The fundamental funnel should be:

```text
ALL STRATEGY HYPOTHESES
        ↓
BACKTESTED
        ↓
POSITIVE BACKTEST
        ↓
POSITIVE AFTER COSTS
        ↓
POSITIVE AFTER SLIPPAGE / REALISTIC FILLS
        ↓
POSITIVE AFTER SURVIVORSHIP
        ↓
ROBUST
        ↓
OUT-OF-SAMPLE POSITIVE
        ↓
HOLDOUT POSITIVE
        ↓
PAPER ELIGIBLE
        ↓
FORWARD POSITIVE
        ↓
LIVE ELIGIBLE
        ↓
LIVE
```

Use the actual stages already implemented by Stockbot2000.
Do not invent a parallel validation system.

## 4. MEASURE THE COLLAPSE AT EACH STAGE

For every stage calculate:

```text
strategies_entering
strategies_surviving
strategies_rejected
survival_rate
median_return
median_net_return
best_return
worst_return
median_drawdown
median_trade_count
```

Where the existing data permits, also calculate:

```text
mean_return
median_return
distribution
win_rate
expectancy
Sharpe
Sortino
profit_factor
turnover
cost_drag
slippage_drag
survivorship_drag
```

The most important output is:
How much of the strategy population disappears at each stage?

## 5. IDENTIFY THE BOTTLENECK

Determine where the largest collapse occurs.
For example:

```text
100,000 hypotheses
↓
20,000 backtested
↓
5,000 positive
↓
2,000 after costs
↓
400 after survivorship
↓
30 robust
↓
5 holdout
↓
1 paper
↓
0 forward
```

That tells us something completely different from:

```text
100,000 hypotheses
↓
50 positive
↓
0 after costs
```

The system must explicitly identify the dominant bottleneck.

## 6. DISTINGUISH "NO EDGE" FROM "NO GOOD HYPOTHESES"

This is critical.
If Stockbot has tested only a small number of genuinely distinct trading ideas, we cannot conclude that durable trading edges are rare.
We need to distinguish:

Scenario A

```text
Very few meaningful hypotheses tested
→ no survivors
```

from:

Scenario B

```text
Thousands of diverse hypotheses tested
→ many historical positives
→ nearly all fail realistic validation
```

from:

Scenario C

```text
Many strategies survive backtesting
→ realistic testing removes most
→ several survive holdout
→ forward testing kills them
```

These represent very different problems.

## 7. COUNT DISTINCT HYPOTHESES

Do not count every parameter combination as a separate strategy idea.
For example:

```text
Momentum 3 months
Momentum 4 months
Momentum 5 months
Momentum 6 months
```

may represent one underlying hypothesis:
momentum.
Measure both:
Raw strategy count
and:
Distinct hypothesis count.
Report:

```text
total strategies
unique hypotheses
strategy families
variants per hypothesis
tests per hypothesis
```

This prevents a million parameter combinations from being mistaken for a million independent ideas.

## 8. ANALYZE STRATEGY FAMILY COVERAGE

Determine how broadly Stockbot has searched the strategy space.
Report the number of tested hypotheses in areas such as:

```text
Momentum
Trend
Mean Reversion
Value
Quality
Low Volatility
Size
Reversal
Breakout
Seasonality
Earnings
Analyst Revision
Volatility
Liquidity
Relative Value
Pairs
Fundamental
Event Driven
Regime
Factor
Hybrid
Machine Generated
```

Use existing taxonomy where available.
Do not create duplicate categories.
The question is:
Are we failing because the machine is bad at discovering strategies, or because we haven't given it enough economically meaningful ideas to investigate?

## 9. ANALYZE THE EXISTING MILLION-TRIAL SEARCH

Do NOT restart it.
Use its historical results as evidence.
Determine:

* How many trials were actually unique hypotheses?
* How many were parameter mutations?
* How many produced positive gross returns?
* How many produced positive net returns?
* How many survived realistic fills?
* How many survived survivorship?
* How many survived robustness?
* How many reached holdout?
* How many survived holdout?
* What happened to the strongest candidates afterward?

Determine exactly what the million-trial search taught us.
Do not simply report:
"1,049,967 trials were run."
That number alone is not useful.
We need to know the effective research population.

## 10. INVESTIGATE THE XGBOOST RESULT

Use the existing XGBoost findings as another diagnostic example.
The project has already documented:

* approximately 0.63 AUC across 31 folds;
* 1,062 OOS trades;
* approximately 40.3% win rate;
* realistic next-open gross P&L of approximately -$82.54;
* realistic net P&L of approximately -$226.11;
* subsequent decay analysis suggesting the ranking was largely related to dates rather than identifying better stocks within the same day.

Analyze this case as an example of:

```text
Predictive signal
        ≠
Tradable edge
```

Determine where the conversion failed.
The goal is not to criticize XGBoost.
The goal is to understand how a statistically meaningful relationship can fail to become profitable trading performance.

## 11. INVESTIGATE SURVIVORSHIP

Use the project's existing survivorship results.
The tracker has already shown examples where apparent profitability changed dramatically after dead companies were introduced.
Analyze:

```text
current universe
vs
historical universe
vs
dead-company inclusion
vs
worst-case death treatment
```

Determine:

* how many candidates are materially affected;
* whether survivorship is eliminating most apparent strategies;
* whether the synthetic-dead-company data is responsible for unusual results;
* whether the current synthetic data quality could itself be distorting the research;
* whether the issue is primarily data quality or genuine survivorship bias.

Do NOT assume either explanation.
Measure it.

## 12. TEST WHETHER VALIDATION IS TOO STRICT

This is NOT permission to loosen the validation system.
Instead, perform a diagnostic analysis.
For strategies that fail:

* costs
* survivorship
* robustness
* holdout
* paper
* forward

determine how close they were to passing.
For example:

```text
Passed by large margin
Barely failed
Failed moderately
Failed catastrophically
```

If hundreds of strategies consistently miss a gate by tiny amounts, that tells us something different from almost every strategy failing catastrophically.
Report the distributions.

## 13. LOOK FOR "SMALL POSITIVE" STRATEGIES

Do not establish a target return.
Instead, inspect whether the current system is finding strategies with:

* small positive expectancy;
* small positive net return;
* positive median period performance;
* modest drawdown;
* stable performance across periods;
* reasonable trade frequency.

The question is simply:
Do small positive edges exist anywhere in the current research population?
If they do, identify where they occur in the pipeline.
Do not automatically promote them.
Do not automatically reject them.

## 14. DISTINGUISH PERFORMANCE FROM PERFORMANCE QUALITY

For every promising strategy, examine:

```text
Return
Drawdown
Trade count
Win rate
Expectancy
Profit factor
Turnover
Costs
Slippage
Period stability
Parameter stability
Market-regime stability
Survivorship sensitivity
Out-of-sample performance
Forward performance
```

A strategy with:

```text
+50% return
```

may be less informative than one with:

```text
+4% return
```

if the second result is much more stable.
But do not encode this as a new ranking rule yet.
This is diagnostic analysis.

## 15. DETERMINE WHETHER WE HAVE A HYPOTHESIS PROBLEM

At the end of the analysis, answer:

Question 1
Do we have enough distinct economically motivated trading hypotheses?

Question 2
Have we mostly been testing parameter combinations of a relatively small number of ideas?

Question 3
How many strategies originated from documented trading knowledge versus machine discovery?

Question 4
Does the existing system have broad coverage across established strategy families?

Question 5
Where does the strategy population collapse?

Question 6
Are apparent edges primarily being destroyed by:

* costs,
* slippage,
* survivorship,
* robustness,
* holdout,
* or forward testing?

Question 7
Do any strategies demonstrate small but persistent positive performance?

Question 8
Are we testing enough independent hypotheses to conclude that the absence of durable edges is meaningful?

## 16. DO NOT JUMP TO THE CONCLUSION

The final report must explicitly distinguish between:
What the data demonstrates
and:
What we infer.
For example:

```text
FACT:
2,000 strategies reached realistic backtesting.

FACT:
17 survived holdout.

FACT:
0 have demonstrated positive forward performance.

INFERENCE:
The current strategy-generation process may be producing
historical patterns that do not generalize.

UNKNOWN:
Whether a different strategy population would produce durable
forward performance.
```

Do not turn an unknown into a conclusion.

## 17. OUTPUT: STRATEGY FUNNEL REPORT

Create a report similar to:

```text
STOCKBOT2000 STRATEGY FUNNEL

Stage                         Entered    Passed    Rate

Hypotheses
Backtests
Positive gross
Positive net
Realistic execution
Survivorship
Robustness
OOS
Holdout
Paper
Forward
Live eligible
Live
```

Then:

```text
TOP BOTTLENECKS

1.
2.
3.
```

Then:

```text
HYPOTHESIS COVERAGE

Family                     Hypotheses    Variants    Tests

Momentum
Trend
Mean Reversion
Value
...
```

Then:

```text
PERFORMANCE DISTRIBUTION

Stage
Median
25th percentile
75th percentile
Best
Worst
```

Where data supports these statistics.

## 18. CREATE A "WHY DID THIS STRATEGY FAIL?" VIEW

For rejected promising strategies, create a structured failure reason.
Examples:

```text
FAILED_COSTS
FAILED_SLIPPAGE
FAILED_LIQUIDITY
FAILED_SURVIVORSHIP
FAILED_ROBUSTNESS
FAILED_HOLDOUT
FAILED_PAPER
FAILED_FORWARD
INSUFFICIENT_TRADES
DATA_QUALITY
EXECUTION_ASSUMPTION
```

A strategy can have multiple reasons.
This is extremely important because we want Stockbot2000 to learn from failure.

## 19. CREATE A "NEAR MISS" REPORT

Identify strategies that:

* were positive historically;
* survived realistic execution;
* failed later;
* but failed by a relatively small margin.

These are near misses, not winners.
Track them separately.
This may reveal whether the system is close to finding useful edges or whether the apparent performance is systematically disappearing.

## 20. DO NOT CHANGE LIVE TRADING

The live five-slot system continues operating.
Do not modify:

* live ranking;
* slot allocation;
* stops;
* execution;
* Robinhood integration;
* cash controls;
* kill switches.

unless a genuine bug is discovered.
If a bug is discovered, fix it and document it.

## 21. DO NOT TURN THIS INTO ANOTHER SEARCH

This phase is complete when we understand the research funnel.
Do NOT respond to poor results by immediately launching:

```text
1 million more trials
```

Do NOT optimize parameters simply because we found a promising candidate.
First determine what the current system is actually doing.

## 22. AFTER THE DIAGNOSTIC

At the end, provide a recommended next step based strictly on the evidence.
Possible conclusions include:

A
We need substantially more distinct hypotheses.

B
We have enough hypotheses, but realistic execution destroys the apparent edge.

C
Survivorship/data quality is the primary problem.

D
Robustness/holdout is eliminating overfit strategies.

E
Forward testing is the bottleneck.

F
The validation system appears excessively restrictive and requires further investigation.

G
Multiple problems exist.

Do NOT choose one in advance.
Let the evidence determine the conclusion.

## 23. FINAL REPORT

At completion provide:

```text
DIAGNOSTIC STATUS

Primary finding:
...

Where the funnel collapses:
...

Number of distinct hypotheses:
...

Number of strategy families:
...

Most heavily tested families:
...

Least tested families:
...

Backtest-positive strategies:
...

Realistic-positive strategies:
...

Robust strategies:
...

Holdout survivors:
...

Paper survivors:
...

Forward survivors:
...

Small-positive candidates:
...

Near misses:
...

Primary failure modes:
...

Data problems:
...

Methodology problems:
...

Evidence that the search space is insufficient:
...

Evidence that the validation system is eliminating false positives:
...

Evidence that we have a genuine lack of durable edge:
...

Unknowns:
...

Recommended next phase:
...
```

## Final instruction

Do not try to make Stockbot2000 look successful.
Do not try to make it look unsuccessful either.
The purpose of this phase is to answer one question honestly:
Is Stockbot2000 failing to find a simple durable trading edge because such an edge is difficult to find, because our strategy search is insufficient, because our data is insufficient, because our validation is eliminating too much, or because we are testing the wrong kinds of hypotheses?
Find out where the problem actually is before changing the system.
