# Addendum B — Final Build Directive

Supplied by the user on 2026-09-24 and reproduced verbatim below. It resolves
the open decisions in Phase 13 and Addendum A and authorizes construction.
Stage status is tracked in `ROADMAP_INTEGRATION.md`, Stages H and I.

**Status: BUILD NOW — authorized 2026-09-24.**

---

ADDENDUM B — FINAL BUILD DIRECTIVE
Complete the Autonomous Stockbot2000 Product
Status: BUILD NOW
Applies to: Phase 13 — Strategy Factory 2.0 + Data Integrity + Continuous Discovery
Applies to: Addendum A — Autonomous Five-Slot Trading Engine
Purpose: Final implementation directive before construction begins.
B1. Objective
The objective of Phase 13 + Addendum A is to complete the autonomous Stockbot2000 product.
This is now an implementation phase, not another research/proof phase.
Stockbot2000's final product is:
An autonomous trading system that continuously discovers, tests, ranks, paper-trades, and promotes strategies; automatically selects the five best currently eligible strategies; allocates approximately $20 to each selected strategy; executes and manages their trades through Robinhood; continuously monitors performance and risk; and automatically replaces weaker strategies with stronger eligible candidates.
The primary objective is positive trading P&L.
Beating SPY, the S&P 500, or another benchmark is not a requirement for promotion or live eligibility.
B2. BUILD, DON'T WAIT FOR PROOF
Claude must now build the complete system according to the roadmap and stated defaults.
Do not turn the remaining roadmap questions into a sequence of research projects that prevent implementation.
Do not spend the majority of the remaining effort attempting to prove that an existing strategy has a durable edge before building the infrastructure.
Do not restart the frozen evolutionary search.
Do not add another strategy-discovery phase after Phase 13.
Do not stop after implementing only one subsystem.
Do not repeatedly ask the user for approval before proceeding to the next implementation step.
Required behavior
Build the components sequentially and integrate them as you go.
Use the decisions and defaults already established in the roadmap and Addendum A.
If a research result is unfavorable, record it and continue building.
If the current strategy set contains no profitable strategies, that does not mean construction should stop.
The system must be capable of discovering better strategies later.
Only stop when:

1. A genuine external dependency prevents implementation;
2. Required credentials/account authorization are unavailable;
3. A live-trading decision genuinely cannot be made safely without user input; or
4. A technical blocker cannot reasonably be worked around.

Everything else should be implemented using the existing defaults and made configurable where appropriate.
B3. THE FIVE-STRATEGY PIPELINE
The complete selection pipeline must be:
Discovery
→ Specification
→ Backtest
→ Validation
→ Paper
→ Forward Performance
→ Eligibility
→ Ranking
→ Five Live Slots
Historical backtest performance is therefore not sufficient to win a live slot.
A strategy can be historically excellent and still lose its slot if its forward performance deteriorates.
Conversely, the system must be capable of promoting a strategy that was initially unknown but demonstrates sufficient forward evidence.
The live leaderboard must therefore be driven primarily by current forward evidence, subject to minimum eligibility and risk requirements.
B4. "BEST FIVE" DEFINITION
The system must select the five best currently eligible strategies.
"Best" does not mean:

* highest historical return;
* highest backtest Sharpe;
* highest single-period return;
* highest score from the evolutionary search;
* highest theoretical alpha;
* or best benchmark-relative performance.

Instead:
Candidate eligibility comes first.
A strategy must satisfy the required:

* forward evidence;
* minimum trade/session evidence;
* risk limits;
* drawdown limits;
* liquidity requirements;
* data-quality requirements;
* execution requirements;
* stop-loss requirements;
* family/concentration rules;
* and other configured safety gates.

Only eligible strategies enter the live ranking pool.
The system then ranks eligible candidates using current forward performance and risk-adjusted evidence.
B5. GROSS, COSTS, AND NET
The system must continue reporting:
Gross P&L
Trading Costs
Net P&L
These must remain visible side-by-side everywhere relevant.
Positive gross P&L is an important research objective.
However, actual live slot selection must ultimately account for actual trading costs.
Therefore:
Use measured live costs when available, modeled costs when measured costs are unavailable, and rank live strategies using net P&L while continuing to expose gross P&L and costs separately.
This does NOT create a requirement to beat a benchmark.
It simply prevents the live system from selecting a strategy whose apparent gross profitability disappears after actual execution costs.
B6. EMPTY SLOTS ARE VALID
The system must never trade merely to fill all five slots.
If only three strategies satisfy the eligibility requirements:

* Slot 1 → strategy
* Slot 2 → strategy
* Slot 3 → strategy
* Slot 4 → CASH
* Slot 5 → CASH

If only one qualifies, four slots remain cash.
If zero qualify, all five remain cash.
Do not lower eligibility standards simply because capital is available.
Do not manufacture diversification by filling slots with losing strategies.
B7. STRATEGY FAMILY CONCENTRATION
The five slots should represent five eligible strategies, but the system must not artificially fill the portfolio with near-identical copies.
For example, five slightly different parameterizations of the same strategy family should not automatically occupy all five slots.
Apply the family/concentration controls already defined in Phase 13.
The purpose is to prevent the live portfolio from appearing diversified while actually carrying one underlying strategy bet.
If only one strategy family currently contains qualifying strategies, the system may hold fewer than five live positions.
B8. INTRADAY IS FIRST-CLASS
Intraday trading is part of the final product.
The architecture must distinguish three different data requirements:
1. Historical research data
Used for:

* backtesting;
* strategy discovery;
* validation;
* robustness testing;
* walk-forward analysis.

2. Live market data
Used for:

* monitoring held positions;
* stop-loss execution;
* intraday signals;
* replacement decisions;
* execution;
* risk controls.

3. Historical intraday data
Required for eventually discovering and properly backtesting intraday strategies.
The current roadmap's live quote polling is sufficient for building the live monitoring architecture.
However, do not pretend that live quote polling creates historical intraday research capability.
Build the interfaces so a historical intraday provider can be added later without redesigning the trading engine.
Intraday strategies that lack adequate historical data should remain paper/shadow strategies until they can be properly validated.
B9. RESEARCH AND TRADING MUST RUN CONCURRENTLY
The research system and trading system must be separate but integrated.
Architecture:

```text
                         STOCKBOT2000
                              |
             +----------------+----------------+
             |                                 |
      RESEARCH ENGINE                     TRADING ENGINE
       Phase 13                           Addendum A
             |                                 |
     Strategy Factory                  Eligibility Engine
     Research Library                  Live Leaderboard
     Discovery Queue                   Slot Manager
     Backtesting                       Risk Engine
     Validation                        Stop Monitor
     Robustness                        Signal Engine
     Paper Trading                     Execution Engine
     Continuous Discovery              Replacement Engine
             |                                 |
             +----------------+----------------+
                              |
                     FIVE LIVE SLOTS
                       ~$20 EACH

```

The research engine must continue discovering and evaluating candidates while the trading engine manages live positions.
Trading must not stop because research is running.
Research must not stop because trading is running.
B10. CONTINUOUS REPLACEMENT
The system must continuously evaluate whether the current five live strategies remain worthy of their slots.
If:
Current live strategy A
falls below the configured eligibility/ranking threshold and
Candidate strategy B
has sufficient forward evidence and ranks materially higher,
then the system should:

1. identify the replacement;
2. evaluate risk and concentration;
3. close the existing position according to the execution/risk rules;
4. release its capital;
5. activate the replacement;
6. record the reason for replacement;
7. continue monitoring the new strategy.

Replacement must not be based on a single noisy trade.
Use the evidence thresholds already established in Addendum A.
B11. DO NOT OVERFIT THE REPLACEMENT ENGINE
The replacement engine must not churn constantly between strategies.
Use configurable minimum evidence requirements.
Default proposed evidence:

* at least 20 forward sessions;
* at least 10 closed trades;
* positive net P&L;
* drawdown below configured limit.

The 60-session established tier remains useful for higher-confidence classification.
A candidate should not replace a live strategy merely because it has a temporarily higher return over a tiny sample.
B12. ACCOUNT TYPE
The Robinhood account type remains the only major live-execution configuration item that genuinely needs confirmation because it affects:

* day-trading rules;
* settled cash;
* buying power;
* position management;
* replacement frequency;
* and account-rule enforcement.

Build the account-rule abstraction now.
Do not allow the missing final account-type selection to block construction of the rest of the system.
The system must support the appropriate cash/margin behavior once the account type is configured.
B13. LIVE TRADING SAFETY
The existing execution and risk architecture remains authoritative.
Phase 13/H13 must connect candidates into the existing execution/risk layer.
Do not create a competing execution or risk system.
Addendum A must provide:

* mandatory stop plans;
* position monitoring;
* intraday monitoring;
* execution confirmation;
* retry/recovery;
* reconciliation;
* global kill switch;
* per-strategy kill switch;
* account-rule guard;
* stale-data protection;
* duplicate-order protection;
* restart recovery;
* position-state reconciliation.

Risk controls override strategy signals.
A strategy may request a trade.
The risk engine has final authority over whether that trade is permitted.
B14. PAPER → SHADOW → LIVE
The final live system must follow:
SIMULATION
→ SHADOW
→ LIVE
The live execution layer must be fully implemented and tested before activation.
The system should be capable of running the complete autonomous loop in simulation/shadow mode before real money is enabled.
Real-money activation remains an explicit user authorization event.
After activation, normal operation should be autonomous.
B15. DO NOT REQUIRE CURRENT STRATEGIES TO WORK
The current roadmap has already established that several apparently promising strategies do not survive honest testing.
That is valuable information.
It is not a reason to stop building the system.
The system's purpose is not:
"Find proof that today's strategies work."
Its purpose is:
"Create a machine that can continuously discover, test, reject, promote, trade, monitor, and replace strategies."
The Strategy Factory therefore needs to be built even if today's scoreboard is weak.
A weak current strategy set means the factory has more work to do; it does not invalidate the factory.
B16. EXISTING FROZEN SEARCH REMAINS FROZEN
The existing evolutionary search remains frozen according to the roadmap.
Do not restart it.
Do not expand it simply because current strategies are unprofitable.
Phase 13 should instead add economically motivated strategy generation through the Strategy Factory.
The new factory should generate strategies from:

* momentum;
* trend;
* breakout;
* mean reversion;
* moving averages;
* RSI;
* MACD;
* Bollinger;
* volatility;
* relative strength;
* quality;
* value;
* growth;
* dividend;
* buyback;
* profitability;
* FCF;
* ROIC;
* earnings yield;
* cash-flow yield;
* fundamental momentum;
* earnings revisions;
* value + momentum;
* value + quality;
* quality + momentum;
* value + quality + momentum;
* momentum + volatility;
* quality + low volatility;
* FCF + quality;
* ROIC + valuation;
* growth + valuation;
* and other economically motivated combinations already specified in Phase 13.

The factory must generate specified, testable strategy objects, not vague ideas.
B17. CONTINUOUS DISCOVERY
The Strategy Factory must operate continuously.
The loop should be approximately:

```text
Generate Candidate
      ↓
Specify Rules
      ↓
Backtest
      ↓
Validate
      ↓
Robustness Tests
      ↓
Paper Enrollment
      ↓
Forward Observation
      ↓
Eligibility Evaluation
      ↓
Live Candidate
      ↓
Live Slot
      ↓
Monitor
      ↓
Promote / Demote / Replace
      ↓
Return Results to Discovery System
      ↓
Generate Next Candidates

```

Failed strategies should not simply disappear.
Record:

* why they failed;
* which family they belonged to;
* which parameters failed;
* which regimes failed;
* what data was involved;
* and whether the failure suggests a useful future hypothesis.

Use this information to improve future candidate generation.
B18. ACCOUNTING MUST BE AUTHORITATIVE
The accounting correction from Phase 13 is mandatory.
There must be one authoritative definition of:
gross P&L + costs = net P&L
The system must correctly account for:

* opening transaction costs;
* closing transaction costs;
* commissions/fees where applicable;
* modeled slippage;
* actual execution costs;
* realized P&L;
* unrealized P&L;
* open-position closing costs;
* strategy-level P&L;
* portfolio-level P&L.

Historical curves affected by known accounting defects should be:

1. preserved;
2. clearly marked as original;
3. restated using corrected accounting;
4. never silently overwritten.

B19. DATA INTEGRITY REMAINS A FIRST-CLASS REQUIREMENT
The existing data-integrity work must remain part of the build.
Maintain explicit tracking of:

* survivorship;
* instrument coverage;
* point-in-time correctness;
* missing data;
* data freshness;
* delisted securities;
* corporate actions;
* provider discrepancies;
* universe availability;
* historical intraday availability.

FINSABER remains a secondary validation dataset, not a replacement for the primary database.
Do not allow discrepancies between datasets to silently disappear.
B20. BENCHMARKS ARE INFORMATIONAL
SPY and other benchmarks may continue to be reported.
They are useful for understanding strategy behavior.
They are not promotion gates.
Do not reject a profitable strategy solely because it does not beat SPY.
Do not require the system to maximize alpha relative to a benchmark.
The objective is positive trading P&L subject to risk and execution constraints.
B21. NO ARTIFICIAL STOPPING POINT
Do not finish Phase 13 after:

* creating a database table;
* creating a few strategy templates;
* generating a report;
* implementing one strategy family;
* or completing a research experiment.

Phase 13 is complete only when the complete factory-to-live-candidate pipeline exists.
Likewise, Addendum A is complete only when the five-slot autonomous trading architecture exists end-to-end.
The two systems must be integrated.
B22. FINAL DEFINITION OF DONE
The build is complete when Stockbot2000 can autonomously execute this complete lifecycle:

```text
DISCOVER
   ↓
GENERATE
   ↓
SPECIFY
   ↓
BACKTEST
   ↓
VALIDATE
   ↓
ROBUSTNESS TEST
   ↓
PAPER TRADE
   ↓
MEASURE FORWARD PERFORMANCE
   ↓
DETERMINE ELIGIBILITY
   ↓
RANK
   ↓
SELECT BEST CURRENT CANDIDATES
   ↓
APPLY RISK / LIQUIDITY / CONCENTRATION RULES
   ↓
ASSIGN FIVE ~$20 SLOTS
   ↓
EXECUTE THROUGH ROBINHOOD
   ↓
MONITOR CONTINUOUSLY
   ↓
ENFORCE STOPS
   ↓
MEASURE GROSS / COST / NET
   ↓
DETECT DEGRADATION
   ↓
REASSESS
   ↓
REPLACE WEAKER STRATEGIES
   ↓
RETURN RESULTS TO RESEARCH ENGINE
   ↓
DISCOVER NEW CANDIDATES
   ↓
REPEAT

```

This is the product.
B23. IMPLEMENTATION ORDER
Claude should implement in the existing roadmap order.
Phase 13

1. Architecture audit
2. Accounting correction
3. Strategy object model
4. Research library
5. Strategy Factory
6. Fundamental Strategy Factory
7. FINSABER/provider interface
8. Cross-dataset validation
9. Strategy leagues
10. Continuous discovery
11. Robustness
12. Automatic paper enrollment
13. Promotion pipeline
14. Daily factory/scoreboard reporting
15. End-to-end tests

Addendum A
Then implement:

1. Five-slot model
2. Slot allocation
3. Central replacement engine
4. P&L leaderboard
5. Mandatory stop plans
6. Intraday monitoring
7. Intraday signal engine
8. Live execution/reconciliation
9. Kill switches
10. Daily reassessment
11. Always-on services
12. Account-rule guard
13. Reporting
14. SIMULATION → SHADOW → LIVE readiness

Where practical, integrate each subsystem immediately rather than creating isolated prototypes.
B24. FINAL CLAUDE DIRECTIVE
Build Stockbot2000 now.
Do not treat the current lack of a proven profitable strategy as a reason to delay implementation.
Do not restart the evolutionary search.
Do not create another research phase.
Do not stop to prove every component independently before building the next component.
Do not repeatedly ask for permission.
Use the roadmap's stated defaults.
Make uncertain values configurable.
Continue through the entire Phase 13 + Addendum A implementation.
Only stop for genuine external blockers or decisions that cannot safely be made without user authorization.
At the end of each major implementation stage, report:

* modules/files created or modified;
* database/schema changes;
* integrations completed;
* tests executed;
* test results;
* remaining blockers;
* configuration values requiring user input;
* startup/service commands;
* and what the next implementation step is.

The goal is not to prove that the current strategies are good.
The goal is to build the machine that continuously finds out which strategies are good enough to trade.
Once built and authorized, that machine must be capable of operating Stockbot2000 autonomously.
