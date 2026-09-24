# Phase 13 — Strategy Factory 2.0 + Data Integrity + Continuous Strategy Discovery

Specification supplied by the user on 2026-09-24, reproduced verbatim below.
Integration against the existing system — reuse map, conflicts to resolve, and
the step-by-step status table — is in `ROADMAP_INTEGRATION.md`, Stage H.

**Status: PLANNED — entered 2026-09-24, awaiting the user's review of the
roadmap before implementation begins.**

---

STOCKBOT2000 — PHASE 13
Strategy Factory 2.0 + Data Integrity + Continuous Strategy Discovery
STATUS
This is an implementation phase, not a research phase.
Build the entire phase described below.
Do not stop after implementing one component to test whether it works.
Do not spend the phase proving that existing strategies are profitable or unprofitable.
Do not restart evolutionary searches.
Do not spend large amounts of time investigating whether a single strategy has an edge.
Do not turn this into another backtest experiment.
The objective is to build the infrastructure that allows Stockbot2000 to continuously discover, test, validate, paper-trade, rank, promote, demote, and retire strategies.
If an individual strategy fails, that is expected behavior.
If an entire strategy family fails, record it and continue.
The system itself is the deliverable.
1. CURRENT STATE — ACCEPT THIS AS THE BASELINE
Stockbot2000 already has:

* Historical market data infrastructure
* Approximately 35.5M price bars
* 13,200+ instruments
* Data extending back to 1962
* Point-in-time SEC fundamentals
* Feature generation
* XGBoost modeling
* Strategy genome/evolution infrastructure
* Backtesting
* Walk-forward testing
* Transaction costs
* Slippage
* Liquidity constraints
* Survivorship measurements
* Next-open execution
* Gap-through-stop handling
* Random controls
* Benchmark/null testing
* Strategy promotion pipeline
* Sealed holdout
* Forward paper trading
* Strategy League
* Live/paper reconciliation
* Value Fund
* Crypto paper fund
* Robinhood Agentic integration
* Research library
* Notification/reporting infrastructure

The existing research has already established that:

* Ranking skill is not automatically tradeable edge.
* The XGBoost classifier has shown ranking ability but has not demonstrated a reliable tradeable edge.
* ETF switching strategies have not demonstrated switching alpha versus appropriate buy-and-hold comparisons.
* Existing technical strategy searches have not produced a strategy that has cleared all promotion gates.
* More than 1 million evolutionary trials have already been performed.
* The evolutionary search is currently frozen.
* Survivorship bias remains an important data-quality issue.
* Approximately 7,062 delisted common stocks are not represented adequately in the current price history.
* Existing forward paper funds contain some profitable variants, but the evidence is currently short and insufficient to establish durable edge.
* Accounting/cost treatment has had defects and must be corrected before treating the scoreboard as authoritative.

IMPORTANT
These findings are NOT a reason to stop building.
They are a reason to improve the research architecture.
The objective of Phase 13 is to make Stockbot2000 better at discovering legitimate opportunities rather than simply getting better at rejecting the current set of ideas.
2. PRIMARY OBJECTIVE
Build a universal Strategy Factory.
The Strategy Factory must become the central mechanism through which new investment ideas enter Stockbot2000.
The permanent pipeline must be:

```text
RESEARCH IDEA
      ↓
STRATEGY SPECIFICATION
      ↓
STRATEGY GENERATION
      ↓
BACKTEST
      ↓
VALIDATION
      ↓
ROBUSTNESS TESTS
      ↓
PAPER TRADING
      ↓
STRATEGY LEAGUE
      ↓
ELIGIBILITY
      ↓
RISK / CORRELATION FILTER
      ↓
LIVE CANDIDATE
      ↓
ROBINHOOD AGENTIC
      ↓
LIVE PERFORMANCE
      ↓
PROMOTION / DEMOTION / RETIREMENT
      ↓
RESEARCH FEEDBACK
      ↓
NEW IDEAS

```

This loop must operate continuously.
A failed strategy does not stop the pipeline.
A successful strategy does not stop the pipeline.
3. DO NOT REBUILD THE ENTIRE EXISTING SYSTEM
Reuse the existing infrastructure wherever possible.
Do not rewrite functioning components simply to create a new architecture.
Phase 13 should be an orchestration and expansion layer over the existing system.
Preserve existing:

* Data ingestion
* Feature calculations
* Backtester
* Simulator
* Cost model
* Walk-forward system
* Promotion ladder
* Paper trading
* Strategy League
* Risk controls
* Robinhood abstraction
* Reporting
* Research ledger

Modify existing components only when required to support the new architecture or fix identified correctness problems.
4. STRATEGY FACTORY
Create a new Strategy Factory subsystem.
The factory must be able to generate strategies from multiple independent sources.
Strategy source categories
A. Classical quantitative strategies
Implement generators for:

* Momentum
* Cross-sectional momentum
* Time-series momentum
* Trend following
* Breakouts
* Moving-average systems
* Mean reversion
* RSI
* MACD
* Bollinger Bands
* Volatility breakout
* Volatility contraction
* Relative strength
* Low volatility
* High volatility
* Quality
* Value
* Growth
* Dividend
* Buybacks
* Profitability
* Free cash flow
* ROIC
* Earnings yield
* Cash-flow yield

B. Combination strategies
Automatically generate combinations such as:

* Value + Momentum
* Value + Quality
* Quality + Momentum
* Value + Quality + Momentum
* Momentum + Volatility
* Quality + Low Volatility
* Fundamental Momentum + Price Momentum
* Earnings Revision + Momentum
* FCF + Quality
* ROIC + Valuation
* Growth + Reasonable Valuation

The system must prevent uncontrolled combinatorial explosion.
Use controlled search spaces and predefined combination templates.
5. FUNDAMENTAL STRATEGY FACTORY
Build the fundamental strategy factory as a first-class subsystem.
It must be capable of creating strategies based on:
Profitability

* Gross margin
* Operating margin
* EBITDA margin
* EBIT margin
* Net margin
* ROIC
* ROE
* ROA

Cash flow

* Free cash flow
* FCF yield
* FCF growth
* Operating cash flow
* Cash conversion
* FCF consistency

Valuation

* P/E
* Forward P/E where point-in-time data exists
* EV/EBITDA
* EV/EBIT
* Price/FCF
* FCF yield
* Price/book
* EV/sales
* Earnings yield

Balance sheet

* Debt/equity
* Net debt/EBITDA
* Interest coverage
* Current ratio
* Cash/debt
* Leverage trends

Growth

* Revenue growth
* EPS growth
* EBITDA growth
* FCF growth
* Margin expansion
* Acceleration/deceleration

Fundamental momentum
Generate strategies based on changes in fundamentals:

* Revenue acceleration
* Earnings acceleration
* Margin expansion
* FCF acceleration
* ROIC improvement
* Debt reduction
* Estimate/revision-style signals where legally and historically available

All fundamental strategies MUST obey point-in-time rules.
The system must never use information before it became publicly available.
6. VALUE INTELLIGENCE ENGINE
The existing Value Fund must become part of the universal strategy architecture.
Create a formal Value Strategy Family.
The system should support:

```text
Company
   ↓
Financial statements
   ↓
Quality analysis
   ↓
Growth analysis
   ↓
Cash-flow analysis
   ↓
Balance-sheet analysis
   ↓
Valuation
   ↓
Intrinsic-value estimate
   ↓
Margin of safety
   ↓
Risk assessment
   ↓
Value strategy score
   ↓
Portfolio candidate

```

Support multiple valuation methodologies rather than one permanent formula.
Examples:

* Earnings valuation
* FCF valuation
* DCF
* EV/EBITDA
* EV/EBIT
* Relative valuation
* Asset-based valuation
* Owner-earnings style valuation

The Value Fund must have its own league.
Do NOT require it to meet short-term tactical strategy requirements.
A long-term value strategy should be evaluated according to an appropriate long-term horizon.
7. REAL-WORLD STRATEGY LIBRARY
Expand the existing Research Library.
Every imported strategy must become a hypothesis.
Never assume a published strategy works.
Each research entry must contain:

```text
Strategy ID
Strategy name
Source
Author/researcher
Publication
URL/reference
Strategy family
Economic rationale
Exact rules
Universe
Holding period
Entry conditions
Exit conditions
Position sizing
Risk management
Required data
Publication date
Implementation notes
Known limitations
Backtest status
Replication status
Forward-test status

```

Sources can include:

* Academic papers
* Quantitative research
* Professional investors
* Published systematic strategies
* Books
* Public research
* Institutional research that can be legally used
* Known factor research
* Open-source quant research

Every external strategy must pass through the same Stockbot2000 testing pipeline.
Never import somebody else's backtest result as evidence.
8. DATA QUALITY UPGRADE — FINSABER
Add the FINSABER dataset as a secondary historical validation dataset.
Repository:
https://huggingface.co/datasets/finsaber-team/FINSABER-reproduce
Primary file:

```text
data/price/all_sp500_prices_2000_2024_delisted_include.csv

```

Expected characteristics:

* Approximately 253 MB
* S&P 500 price history
* 2000–2024
* Includes delisted companies
* Price fields include:
   * date
   * symbol
   * open
   * high
   * low
   * close
   * adjusted_close
   * volume

Do NOT replace the existing Stockbot2000 database with FINSABER.
Instead create a formal:
DATASET VALIDATION LAYER
The system must be able to run appropriate strategies against:

```text
PRIMARY STOCKBOT DATABASE
            +
FINSABER VALIDATION DATASET

```

The purpose is to identify:

* Price discrepancies
* Missing securities
* Missing dates
* Corporate-action differences
* Delisting differences
* Adjusted-price differences
* Volume discrepancies
* Ticker mapping problems
* Universe discrepancies

Generate a dataset comparison report.
The report should include:

```text
Dataset
Date range
Number of securities
Number of bars
Missing bars
Duplicate bars
Price discrepancies
Volume discrepancies
Delisted securities
Ticker changes
Corporate-action differences
Coverage by year
Coverage by security

```

9. IMPORTANT FINSABER LIMITATIONS
Do NOT treat FINSABER as institutional-grade ground truth.
The supplied research indicates:

* It is primarily an S&P 500 dataset.
* It does not provide complete delisting returns.
* It does not replace the broader Stockbot universe.
* It does not provide the full fundamental dataset required by Stockbot2000.

Therefore:
FINSABER = validation dataset
NOT:
FINSABER = new master database
The purpose is independent cross-validation of the historical price engine.
10. OPTIONAL SECONDARY DATA ARCHITECTURE
Design the data layer so that additional datasets can be added later without rewriting the backtester.
The architecture should support:

```text
Data Provider Interface
       ↓
Provider A
Provider B
Provider C
FINSABER
Future paid provider
       ↓
Normalized Market Data Model
       ↓
Backtester

```

Do NOT purchase a data provider as part of this phase.
Build the architecture so a future provider can be plugged in.
Potential future providers may include paid survivorship-aware datasets, but implementation is not required now.
11. SURVIVORSHIP-BIAS VALIDATION
Keep the existing survivorship-bias measurement system.
Improve it so that strategies can be tagged:

```text
SURVIVORSHIP SAFE
SURVIVORSHIP ADJUSTED
SURVIVORSHIP LIMITED
UNKNOWN

```

A strategy that only works on surviving companies must not receive the same validation status as one tested against a survivorship-aware universe.
For the S&P 500 validation subset, compare Stockbot2000 results against FINSABER's delisted-inclusive history.
12. ACCOUNTING CORRECTION — HIGH PRIORITY
Before using the Strategy League as an authoritative ranking system, fix the known cost-accounting problems.
Specifically:

* Opening transaction costs must be charged correctly.
* Paper funds must not defer costs in a way that temporarily inflates equity curves.
* ETF switching funds must include opening and closing costs consistently.
* Value Fund must use the same accounting model.
* Every strategy must use identical cost accounting rules.
* Gross and net P&L must be separately tracked.

The canonical calculation must be:

```text
Gross P&L
- commissions
- spreads
- slippage
- financing costs where applicable
- other modeled trading costs
= Net P&L

```

Never rank strategies using inconsistent accounting.
13. STRATEGY OBJECT MODEL
Every strategy must have a permanent identity.
Required fields:

```text
strategy_id
strategy_version
strategy_family
strategy_source
hypothesis
economic_rationale
universe
data_requirements
features
parameters
entry_rules
exit_rules
position_sizing
risk_rules
holding_period
backtest_period
validation_period
paper_start
paper_days
paper_trades
gross_return
net_return
max_drawdown
Sharpe
Sortino
win_rate
profit_factor
turnover
costs
benchmark_return
correlation
capacity
survivorship_status
data_quality_status
promotion_status
live_status
created_at
updated_at
parent_strategy_id

```

Never overwrite a strategy.
If the rules change materially:

```text
Strategy A v1
Strategy A v2
Strategy A v3

```

They are separate research objects.
14. STRATEGY STATUS MACHINE
Implement this exact lifecycle:

```text
DISCOVERED
    ↓
SPECIFIED
    ↓
BACKTESTED
    ↓
VALIDATED
    ↓
PROMISING
    ↓
PAPER
    ↓
QUALIFIED
    ↓
LIVE CANDIDATE
    ↓
LIVE

```

Failure states:

```text
REJECTED
DEMOTED
RETIRED

```

A failed strategy is never deleted.
Its result remains available for future research.
15. DO NOT CONFUSE "PROFITABLE" WITH "PROVEN"
The system must distinguish:
PROFITABLE
A strategy currently has positive measured P&L.
PROMISING
A strategy has enough evidence to justify continued testing.
QUALIFIED
A strategy has passed all required validation and paper-trading gates.
LIVE
A strategy is authorized for real-money allocation.
Positive P&L alone must never automatically trigger live trading.
16. STRATEGY LEAGUES
Do not force fundamentally different strategies into one competition.
Create separate leagues:
Tactical / Swing
Days to weeks.
Momentum
Momentum and trend strategies.
Mean Reversion
Short-term reversal strategies.
Fundamental
Value, quality, profitability, balance sheet.
Value
Long-duration value strategies.
ETF / Macro
ETF rotation and macro allocation.
ML
XGBoost and future ML models.
Event
Event-driven strategies.
Crypto
Crypto-specific strategies.
Each league must have appropriate evaluation horizons.
17. GLOBAL STRATEGY SCOREBOARD
Create a global scoreboard that normalizes strategy information.
Do NOT rank simply by raw return.
Display:

```text
Strategy
League
Status
Gross P&L
Net P&L
Return
Max Drawdown
Sharpe
Sortino
Win Rate
Profit Factor
Trades
Turnover
Costs
Paper Duration
Benchmark
Correlation
Data Quality
Survivorship Status
Confidence

```

Use this scoreboard for monitoring.
18. LIVE CAPITAL ALLOCATION
The top five live strategies must NOT simply be:

```text
highest five returns

```

Instead:

```text
Eligible strategies
        ↓
Risk limits
        ↓
Correlation filter
        ↓
Strategy-family concentration limit
        ↓
Liquidity filter
        ↓
Drawdown filter
        ↓
Minimum evidence
        ↓
Top eligible candidates
        ↓
Capital allocation

```

If the top five are five nearly identical Rising 200 variants, they should not automatically consume five independent strategy slots.
Treat them as one strategy family for concentration purposes.
19. RISING 200 STRATEGIES
The current Rising 200 strategies must be retained.
Do not delete them.
Do not declare them proven.
Classify them as:

```text
PROMISING / INSUFFICIENT EVIDENCE

```

They currently provide evidence worth monitoring but have insufficient forward duration to establish durable edge.
Treat different stop widths as related variants of the same family.
20. XGBOOST
Do not discard XGBoost.
Do not keep repeatedly testing it as though another backtest will automatically solve the problem.
Investigate its role as:

* Regime detector
* Risk model
* Probability calibration model
* Position-sizing input
* Trade filtering model
* Ensemble component

The existing finding that ranking skill does not necessarily translate into within-day stock-selection edge must be preserved.
21. STOP SEARCHING THE SAME SPACE
The existing evolutionary search has already exceeded one million trials.
Do NOT restart it as the primary discovery mechanism.
The problem is no longer:
"Can we search more combinations?"
The problem is:
"Are we searching the right investment ideas?"
Phase 13 therefore prioritizes:

```text
Breadth of hypotheses
+
Economic rationale
+
Independent strategy families
+
Robust validation

```

over:

```text
More brute-force parameter optimization

```

22. CONTINUOUS IDEA GENERATION
Build the system so new strategies can continuously enter.
Sources:

```text
Research Library
Academic research
Human-created hypotheses
Fundamental combinations
Technical combinations
Market regimes
ML-generated hypotheses
Previously failed strategies
Variants of promising strategies

```

Every idea must automatically become a Strategy object.
No manual database entry should be required for normal operation.
23. FAILED STRATEGY RECYCLING
A failed strategy should be available for mutation.
Examples:

```text
Change universe
Change holding period
Change entry threshold
Change exit rule
Add volatility filter
Add quality filter
Add value filter
Add momentum confirmation
Change position sizing
Change regime filter
Remove redundant indicator

```

But mutations must be tracked as new strategy versions.
Do not endlessly mutate one failed strategy without limits.
24. EXPERIMENT BUDGET
Prevent the system from wasting compute on one idea family.
Implement configurable budgets:

```text
Maximum variants per hypothesis
Maximum variants per strategy family
Maximum parameter combinations
Maximum compute per research source
Maximum repeated tests

```

Once a family has been sufficiently explored without evidence, reduce its allocation and redirect compute to underexplored families.
25. RESEARCH PRIORITY ENGINE
Build a research-priority mechanism.
The system should prefer:

1. New strategy families
2. Under-tested strategy families
3. Promising strategies requiring more forward evidence
4. Strategies with strong economic rationale but insufficient testing
5. Robust variants of promising strategies
6. Cross-family combinations
7. New external research

It should deprioritize:

* Repeatedly failed hypotheses
* Redundant variants
* Excessive parameter tuning
* Strategies already disproven under multiple independent datasets
* Strategies with no economic rationale

26. PAPER TRADING
Every strategy that survives initial validation enters paper trading automatically.
Paper trading must record:

* Every signal
* Every simulated order
* Entry price
* Exit price
* Gross P&L
* Costs
* Net P&L
* Slippage
* Holding period
* Drawdown
* Exposure
* Benchmark
* Market regime
* Strategy version

Paper results must use the same execution model as live trading.
27. FORWARD-TESTING RULE
Forward testing must be considered independent evidence.
Never change strategy parameters based on forward results without creating a new version.
If a strategy is modified after seeing forward performance:

```text
Original strategy → remains unchanged
New version → starts a new validation cycle

```

This prevents forward-test contamination.
28. MONTE CARLO / ROBUSTNESS
Add robustness analysis to the validation pipeline.
For promising strategies test:

* Trade-order randomization
* Return bootstrapping
* Slippage variation
* Cost variation
* Entry delay
* Exit delay
* Parameter perturbation
* Holding-period perturbation
* Universe perturbation
* Start-date perturbation
* End-date perturbation
* Regime-specific performance

The objective is not to manufacture confidence.
The objective is to identify strategies whose results collapse under small changes.
29. DATA-CROSS-VALIDATION TEST
For strategies where FINSABER applies:

```text
Run Strategy on Stockbot Dataset
             ↓
Run Strategy on FINSABER
             ↓
Compare Results

```

Report:

```text
Return difference
Trade-count difference
Drawdown difference
Sharpe difference
Winning percentage difference
Security coverage difference

```

Large unexplained differences must lower the strategy's data-confidence score.
30. BENCHMARKS
Continue tracking:

* SPY buy-and-hold
* Appropriate sector ETF
* Appropriate factor benchmark
* Cash/T-bill equivalent where appropriate
* Random strategy control
* Strategy-family null benchmark

The system may still pursue strategies that make money without beating SPY.
However, benchmark performance must always be visible.
31. ECONOMIC RATIONALE
Every serious strategy must have an explanation for why it might work.
Examples:

```text
Value → valuation mean reversion
Momentum → behavioral underreaction / trend persistence
Quality → persistent profitability
Low volatility → behavioral / institutional constraints
Mean reversion → temporary price dislocation
Breakout → information diffusion / trend continuation
Fundamental momentum → changing business expectations

```

This rationale does NOT prove the strategy.
It simply prevents the system from treating arbitrary parameter combinations as equally meaningful hypotheses.
32. RESEARCH LIBRARY REQUIREMENT
Expand the current research library beyond its existing approximately 40 entries.
Do not spend this phase manually testing every entry one by one.
Build the ingestion and execution framework first.
The system should be able to queue research entries automatically.
Each research entry should become one or more Strategy objects.
33. VALUE FUND REQUIREMENT
The Value Fund must become a real member of the Strategy Factory architecture.
It must have:

* Historical backtesting
* Point-in-time fundamentals
* Long-duration paper trading
* Separate league
* Value-specific metrics
* Intrinsic value estimates
* Margin of safety
* Portfolio-level risk
* Benchmark
* Live promotion pathway

Do not force the Value Fund through a short-term tactical 60-mark requirement.
Create horizon-appropriate gates.
34. ACCOUNTING / P&L STANDARD
Every report must show:

```text
Gross P&L
Trading Costs
Net P&L

```

For every:

* Trade
* Strategy
* Strategy version
* Fund
* League
* Entire portfolio

The system must be able to reconcile:

```text
Starting Capital
+
Gross Trading P&L
-
Costs
=
Ending Equity

```

No unexplained difference is acceptable.
35. CURRENT P&L MUST BE PRESERVED
The current research snapshot should remain available for historical comparison.
Current supplied results:
Paper funds
Gross:
+$0.14
Costs:
-$6.81
Net:
-$6.67
ETF switching
Gross:
+$3.73
Costs:
-$1.02
Net:
+$2.71
Value Fund
Gross:
$0.00
Costs:
-$0.56
Net:
-$0.56
Crypto
No trades.
All 23 simulated funds
Gross:
+$3.87
Costs:
-$8.39
Net:
-$4.52
Real-money Agentic account
Latest supplied snapshot:
-$7.25
These are historical snapshots, not permanent truth.
Once the accounting defect is fixed, the system must restate affected historical results.
36. REPORTING
Create an automated daily research report containing:
Strategy Discovery

* New strategies
* New variants
* New research sources

Backtesting

* Completed backtests
* Promising candidates
* Failed candidates

Paper Trading

* New trades
* Strategy returns
* Drawdowns
* League movement

Live

* Current live strategies
* Capital
* P&L
* Risk
* Drawdowns

Data

* Data errors
* Missing data
* Provider discrepancies
* FINSABER comparison

Research

* Strategy families explored
* Strategy families ignored
* Compute allocation
* Discovery diversity

37. AUTOMATED DECISION STATES
Implement explicit machine-readable decisions.
Example:

```text
CONTINUE
PROMOTE
DEMOTE
RETIRE
RESEARCH_MORE
DATA_PROBLEM
ACCOUNTING_PROBLEM
INSUFFICIENT_SAMPLE

```

This allows Claude or another orchestration layer to understand exactly why a strategy moved.
38. WHAT CLAUDE MUST NOT DO
During implementation, do NOT:

* Stop to prove that a single strategy works.
* Stop because current strategies are unprofitable.
* Restart the million-trial evolutionary search.
* Spend the majority of the phase tuning XGBoost.
* Spend the majority of the phase tuning Rising 200.
* Spend the majority of the phase proving ETF switching fails.
* Declare the project unsuccessful because no strategy currently has proven edge.
* Delete failed strategies.
* Replace the entire database with FINSABER.
* Treat FINSABER as ground truth.
* Change strategy parameters after seeing forward results without versioning.
* Create arbitrary strategies solely because they produce attractive backtests.
* Optimize for backtest return.
* Stop after implementing only the data layer.
* Stop after implementing only the Strategy Factory.
* Ask the user whether to proceed to the next phase after each component.

39. IMPLEMENTATION ORDER
Build in this exact order.
STEP 1 — Audit existing architecture
Identify the existing modules that correspond to:

* Strategy
* Backtest
* Validation
* Paper trading
* Strategy League
* Research Library
* Fundamentals
* Data
* Costs
* Promotion
* Live execution

DO NOT rewrite them.
Produce a short mapping internally/document it.
Then continue.
STEP 2 — Fix accounting
Make gross/net/cost accounting authoritative.
Test reconciliation.
Then continue.
STEP 3 — Build the Strategy Factory
Create the strategy object model.
Create strategy lifecycle.
Create strategy family definitions.
Create strategy generators.
Then continue.
STEP 4 — Build the Research Library integration
Create the research-source schema.
Create automatic strategy generation from research entries.
Then continue.
STEP 5 — Build the Fundamental Strategy Factory
Integrate point-in-time fundamentals.
Build value/quality/growth/FCF/ROIC/valuation strategy generators.
Then continue.
STEP 6 — Build FINSABER integration
Download/import:

```text
all_sp500_prices_2000_2024_delisted_include.csv

```

Normalize it.
Index it.
Validate it.
Do not replace the primary database.
Then continue.
STEP 7 — Build cross-dataset validation
Run representative strategies across both datasets.
Create discrepancy reports.
Then continue.
STEP 8 — Build strategy leagues
Separate:

* Tactical
* Momentum
* Mean Reversion
* Fundamental
* Value
* ETF/Macro
* ML
* Event
* Crypto

Then continue.
STEP 9 — Build continuous discovery
Implement research queue.
Implement experiment budgets.
Implement strategy-family allocation.
Implement failed-strategy recycling.
Implement discovery diversity.
Then continue.
STEP 10 — Build robustness testing
Add:

* Monte Carlo
* Parameter perturbation
* Cost stress
* Slippage stress
* Date perturbation
* Universe perturbation
* Regime analysis

Then continue.
STEP 11 — Integrate paper trading
Automatically move eligible strategies into paper trading.
Record all required metrics.
Then continue.
STEP 12 — Integrate promotion
Connect:

```text
Strategy Factory
→ Validation
→ Paper
→ League
→ Risk
→ Live Candidate

```

Then continue.
STEP 13 — Integrate live allocation
Connect qualified candidates to the existing Robinhood Agentic execution architecture.
Do not bypass risk controls.
Do not allow individual strategy code to place arbitrary orders.
All orders must pass through the central execution/risk layer.
STEP 14 — Build reporting
Build the daily Strategy Factory report.
Build the global scoreboard.
Build data-quality reporting.
Build research coverage reporting.
STEP 15 — End-to-end test
Run the entire pipeline:

```text
Idea
→ Strategy
→ Backtest
→ Validation
→ Robustness
→ Paper
→ League
→ Eligibility
→ Risk
→ Live Candidate

```

Use a small number of representative strategies for the end-to-end integration test.
Do NOT use the end-to-end test as an excuse to launch another giant research experiment.
40. DEFINITION OF DONE
Phase 13 is NOT complete when:

* One strategy works.
* One backtest finishes.
* FINSABER downloads.
* The Value Fund backtests.
* Claude finds a profitable strategy.
* A paper fund makes money.

Phase 13 IS complete when:
Strategy Factory
New strategy ideas can automatically enter the system.
Research Library
External strategies can automatically become testable hypotheses.
Fundamental Engine
Value/quality/fundamental strategies are first-class citizens.
Data
FINSABER is available as an independent historical validation source.
Accounting
Gross/net/cost accounting is consistent.
Validation
Strategies automatically progress through validation.
Paper Trading
Eligible strategies automatically enter appropriate leagues.
Ranking
Strategies are continuously evaluated.
Risk
Correlation and concentration are considered before promotion.
Live
Qualified strategies can enter the existing Robinhood Agentic pipeline.
Research Loop
The system continuously creates and evaluates new hypotheses.
Failure Handling
Failed strategies remain recorded and do not stop discovery.
41. MOST IMPORTANT DESIGN PRINCIPLE
Stockbot2000's problem is NOT that it has failed to test enough strategies.
It has already performed more than one million evolutionary trials.
The problem is that the system has become much better at answering:
"Does this particular strategy survive our tests?"
than:
"What other economically sensible strategies should we test next?"
Phase 13 fixes that.
The goal is to transform Stockbot2000 from:

```text
Backtesting Engine

```

into:

```text
Continuous Investment Research Laboratory

```

The system should continuously:

```text
LEARN
→ GENERATE
→ TEST
→ VALIDATE
→ PAPER TRADE
→ RANK
→ PROMOTE
→ MONITOR
→ DEMOTE
→ RETIRE
→ LEARN

```

42. FINAL INSTRUCTION TO CLAUDE
Build this phase completely.
Do not wait for additional approval between steps.
Do not turn implementation into an extended discussion about whether the strategies work.
Do not substitute more research for implementation.
Do not optimize the current strategy set instead of building the Strategy Factory.
Do not stop when an individual test fails.
Do not declare the absence of a proven edge to mean the system has nothing to build.
When an implementation choice is required, choose the simplest architecture that satisfies the requirements above and continue.
When something cannot be implemented because of a genuine technical dependency, document the dependency, implement everything that does not depend on it, and continue.
At completion, provide:

1. Files/modules created
2. Files/modules modified
3. Database/schema changes
4. New Strategy Factory capabilities
5. New research-library capabilities
6. FINSABER integration status
7. Accounting corrections
8. New strategy leagues
9. New validation/robustness capabilities
10. New automated workflows
11. Tests performed
12. Any remaining blockers
13. Exact command(s) required to start the continuous research pipeline

Do not provide a proposal for what you could build next. Build the complete phase described above.
