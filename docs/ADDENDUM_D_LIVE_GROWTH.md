# Addendum D — Live Growth & Continuous Improvement

**Entered 2026-09-25 by the owner** ("add the following items to the roadmap.
do not change them just add them in and integrate them faithfully").

The specification below is the owner's text, verbatim. The only edit is
markdown heading markers on the section titles; no wording is changed.
Integration — what each item maps to in the existing system, and the build
order the spec itself sets (§20) — is in `ROADMAP_INTEGRATION.md`, Stage N.

---

The owner's specification, verbatim:

# Stockbot2000 — Next Phase: Live Growth & Continuous Improvement

## Mission

Stockbot2000 is now a LIVE autonomous trading system.
The objective of this phase is not to redesign the project, restart research, or stop the live system while we work on improvements.
The objective is:
Keep Stockbot2000 trading live while continuously making the system better, more observable, more reliable, and more capable of discovering profitable strategies.
I want to be able to watch the system operate in real time and see:

* what strategies are currently active
* what each strategy is doing
* what positions it owns
* entry prices
* current prices
* unrealized P&L
* realized P&L
* stops
* strategy-level performance
* account-level performance
* why a trade was made
* why a position was sold
* which strategies are being tested
* which strategies are improving
* which strategies are degrading
* which strategies are candidates to replace live strategies
* what the research engine is currently discovering
* what the system plans to do next

At the same time, the research system must continue generating and testing new strategies in the background.

## 1. DO NOT STOP THE LIVE SYSTEM

This is the most important instruction.
Do not take Stockbot2000 offline simply because we are beginning this phase.
The live trading engine should continue operating while development continues.
Development, research, testing, monitoring, and strategy discovery should operate alongside the live trading engine.
If a code change could affect live trading:

1. isolate the change
2. test it
3. deploy it safely
4. verify the live system afterward

Do not casually replace working live components.
If necessary, use versioned modules, feature flags, staging implementations, or shadow mode.
The goal is continuous improvement without repeatedly resetting the system.

## 2. THIS IS NOW A CONTINUOUS EVOLUTION SYSTEM

Do not treat Stockbot2000 as a project that has a final research phase and then stops.
Treat it as a continuously operating system.
The lifecycle should continuously repeat:

```text
LIVE TRADING
      ↓
OBSERVATION
      ↓
PERFORMANCE MEASUREMENT
      ↓
STRATEGY DISCOVERY
      ↓
BACKTEST
      ↓
ROBUSTNESS TESTING
      ↓
PAPER FORWARD TEST
      ↓
LIVE ELIGIBILITY
      ↓
RANKING
      ↓
PROMOTION
      ↓
LIVE TRADING
      ↓
OBSERVATION
      ↓
...

```

Research never permanently ends.
Strategy discovery never permanently ends.
The live system should continuously provide new evidence.

## 3. BUILD A REAL-TIME STOCKBOT2000 CONTROL CENTER

This is the highest-priority deliverable of this phase.
I want an actual live operational view of Stockbot2000.
It should be possible to open the dashboard and immediately understand what the machine is doing.
Dashboard: Account Overview
Show:

* total account equity
* available cash
* settled cash
* invested capital
* unrealized P&L
* realized P&L
* today's P&L
* cumulative live P&L
* gross P&L
* estimated transaction costs
* net P&L
* number of active slots
* number of positions
* last broker synchronization
* last trading-engine heartbeat
* system status

Clearly distinguish:

```text
BROKER ACCOUNT
SIMULATED/PAPER
RESEARCH

```

Never mix these numbers.

## 4. LIVE FIVE-SLOT VIEW

Create a dedicated section showing the five strategy slots.
For every slot display:

```text
Slot #
Strategy
Strategy family
Status
Capital allocated
Current market value
Position
Entry price
Current price
Unrealized P&L
Realized P&L
Stop price
Take-profit price
Hold duration
Number of trades
Win rate
Average trade
Net P&L
Drawdown
Forward-test evidence
Backtest score
Current ranking

```

Also show:

```text
WHY THIS STRATEGY IS IN THE SLOT

```

For example:

```text
Selected because:
Backtest score: X
Forward score: X
Recent net P&L: X
Risk score: X
Rank: #X
Eligible: YES

```

The user should not have to inspect source code to understand why a strategy currently owns a slot.

## 5. LIVE TRADE FEED

Add a real-time event stream.
Every important trading event should appear in chronological order.
Examples:

```text
09:35:01
SLOT 2 — SIGNAL
AAPL
BUY
$20.00 allocation

09:35:02
ORDER SUBMITTED

09:35:03
ORDER FILLED
100 shares @ $X

09:35:03
STOP REGISTERED
$X

09:40:00
POSITION MONITOR
P&L +$0.18

10:05:11
STRATEGY EXIT SIGNAL

10:05:12
SELL ORDER SUBMITTED

10:05:13
SELL FILLED

10:05:14
TRADE CLOSED
NET P&L +$0.31

```

This feed should include:

* signals
* orders
* fills
* stops
* exits
* replacements
* strategy promotions
* strategy demotions
* errors
* warnings
* broker synchronization
* cash settlement events
* system restarts

## 6. STRATEGY RANKING CENTER

Create a continuously updated strategy leaderboard.
Show every eligible strategy, not merely the five currently trading.
For each strategy:

```text
Rank
Strategy
Family
Status
Backtest score
Paper score
Forward score
Live score
Net P&L
Trades
Win rate
Drawdown
Sharpe/other risk metrics
Recent performance
Evidence age
Last updated
Eligibility
Current slot

```

The ranking must make the pipeline visible.
I want to see strategies move.
For example:

```text
#1 Strategy A — LIVE
#2 Strategy B — LIVE
#3 Strategy C — PAPER
#4 Strategy D — PAPER
#5 Strategy E — LIVE
#6 Strategy F — PROMISING
#7 Strategy G — BACKTEST
...

```

If a strategy improves enough to challenge a live strategy, that should be obvious.

## 7. MAKE REPLACEMENT VISIBLE

The autonomous replacement engine is one of the core features of Stockbot2000.
Make it observable.
Create a section:
"NEXT POSSIBLE REPLACEMENTS"
Show:

```text
Current Slot  Candidate Strategy  Current Rank  Candidate Rank  Evidence  Reason

```

Example:

```text
Slot 3
Current: Strategy_X
Candidate: Strategy_Y

Candidate has:
+ better forward P&L
+ lower drawdown
+ sufficient trade count
+ passed robustness tests

Replacement status: ELIGIBLE

```

When a replacement occurs, permanently record:

```text
OLD STRATEGY
NEW STRATEGY
WHY REPLACED
OLD PERFORMANCE
NEW PERFORMANCE
TIME
ACCOUNT EFFECT

```

This gives us a complete audit trail.

## 8. BUILD A STRATEGY JOURNAL

Every strategy should have a persistent history.
The system should record:

* creation date
* strategy family
* generation method
* parameters
* datasets used
* backtest results
* robustness results
* paper results
* forward results
* live results
* promotions
* demotions
* replacements
* failures
* retirement
* reactivation

A strategy should never simply disappear.
Its history should remain available.
This is important because Stockbot2000 should learn from its own history.

## 9. CONTINUOUS STRATEGY DISCOVERY

While the five live slots trade, the research engine should continuously search for better candidates.
Do NOT restart the old frozen evolutionary search.
Use the existing Phase 13 discovery architecture.
Continue expanding:

* strategy families
* entry logic
* exit logic
* holding periods
* market regimes
* instruments
* factor combinations
* technical combinations
* fundamental combinations
* published signals
* external data
* intraday strategies
* interday strategies
* swing strategies
* long strategies
* short strategies where supported
* crypto where the existing risk/data gates permit it

New research should be evaluated through the same promotion pipeline.

## 10. PRIORITIZE ECONOMICALLY USEFUL RESEARCH

Do not generate thousands of arbitrary strategy variations simply because computation is available.
Research should target actual weaknesses in the current system.
Examples:

* poor exits
* excessive drawdowns
* weak performance in certain regimes
* excessive turnover
* poor intraday timing
* weak entry timing
* concentration
* survivorship effects
* transaction costs
* slippage
* stop behavior
* gaps
* liquidity
* strategy correlation
* strategy decay

The objective is not:
"Find a strategy with the highest backtest."
The objective is:
"Find strategies that have a credible path through the entire pipeline and ultimately survive live trading."

## 11. LIVE PERFORMANCE MUST FEED BACK INTO THE RESEARCH SYSTEM

Create a feedback loop.
Live trading results should become training/research information.
Track:

```text
Predicted trade
Actual trade
Expected return
Actual return
Prediction error
Slippage
Execution delay
Exit reason
Market regime
Strategy regime

```

Use this information to determine:

* which strategy types work
* which strategies decay
* which signals fail live
* where backtests are overly optimistic
* where execution differs from simulation
* which market conditions cause failure

Do not automatically modify a live strategy solely because of one bad trade.
Use aggregated evidence and the existing risk/replacement framework.

## 12. STRATEGY DECAY DETECTION

Add explicit strategy-degradation monitoring.
A strategy should be monitored for:

* rolling P&L
* rolling win rate
* rolling expectancy
* drawdown
* performance versus its own historical baseline
* performance versus paper results
* performance versus backtest expectations
* change in trade frequency
* change in execution quality

Flag:

```text
HEALTHY
WATCH
DEGRADING
FAILED

```

These are operational states, not subjective judgments.
A degrading strategy should become easier to replace when a qualified alternative exists.

## 13. DO NOT FORCE FIVE STRATEGIES

The system may have five slots, but it must not manufacture quality merely to keep five positions active.
If insufficient strategies qualify:

```text
SLOT = CASH

```

This remains valid.
The system should optimize for positive trading P&L and controlled risk, not maximum capital deployment.

## 14. LIVE SAFETY REMAINS NON-NEGOTIABLE

Before adding new trading capability, verify:

* position sizing
* stop creation
* stop monitoring
* take-profit handling
* order confirmation
* duplicate-order prevention
* stale-price protection
* stale-data protection
* broker reconciliation
* restart recovery
* partial fills
* rejected orders
* insufficient settled cash
* market closed conditions
* network/API failure
* process failure
* kill switch
* emergency flatten
* logging

The live system must never assume an order happened simply because it requested one.
Broker state is authoritative.

## 15. BUILD A SYSTEM HEALTH MONITOR

Add:

```text
SYSTEM HEALTH

```

Show:

* trading engine heartbeat
* ranking engine heartbeat
* research engine heartbeat
* broker connection
* data connection
* last quote
* last order
* last fill
* last ranking
* last strategy discovery run
* last database write
* last reconciliation
* CPU
* RAM
* disk
* process status
* error count
* warning count

Make failures visually obvious.

## 16. DAILY AUTONOMOUS OPERATING LOOP

Stockbot2000 should eventually operate every day without requiring me to manually kick off the process.
The daily loop should include:
Market preparation

* synchronize account
* synchronize positions
* synchronize cash
* load current universe
* validate data
* validate system health

During market hours

* generate signals
* execute eligible trades
* monitor positions
* monitor stops
* monitor exits
* monitor strategy health
* monitor broker state
* record everything

Continuous research

* generate candidates
* backtest
* robustness test
* paper test
* update rankings

Reassessment

* evaluate live strategies
* evaluate replacement candidates
* replace only when replacement criteria are met

End of day
Produce a complete report:

```text
ACCOUNT
P&L
TRADES
POSITIONS
STRATEGY PERFORMANCE
RANKING
REPLACEMENTS
RESEARCH
NEW CANDIDATES
FAILURES
SYSTEM HEALTH
NEXT ACTIONS

```

## 17. BUILD THE SYSTEM SO IT CAN SCALE BEYOND $100

The current ~$100 live account is the experimental deployment.
Do not hard-code assumptions that make scaling difficult.
Create configuration for:

```text
TOTAL_CAPITAL
NUMBER_OF_SLOTS
CAPITAL_PER_SLOT
MAX_POSITION_SIZE
MAX_DAILY_LOSS
MAX_STRATEGY_LOSS
MAX_DRAWDOWN

```

For now use the existing ~$100 / five-slot configuration.
But the architecture should support changing the capital later without rewriting the trading engine.

## 18. KEEP LIVE TRADING AND RESEARCH DECOUPLED

The research engine must never be able to accidentally place live orders.
Use a strict separation:

```text
RESEARCH
    ↓
CANDIDATE
    ↓
ELIGIBILITY
    ↓
RANKING
    ↓
LIVE ALLOCATION
    ↓
EXECUTION

```

Only the live allocation/execution layer can trade.
Research code must not have direct authority to submit live orders.

## 19. CONTINUE STAGES K, L AND M

Continue the existing roadmap.
Do not abandon:
Stage K
Crypto research and validation.
Stage L
Published signals / Open Source Asset Pricing / Global Factor Data.
Stage M
Realistic dead-company / failure-history reconstruction.
These should run as part of the continuous research program.
Do not allow any of them to unnecessarily interrupt the live system.

## 20. NEXT PRIORITY ORDER

Execute this phase in this order:
Priority 1 — Live visibility
Build the real-time control center.
Priority 2 — Live reliability
Verify every live execution path and reconciliation path.
Priority 3 — Strategy leaderboard
Make the complete strategy population visible.
Priority 4 — Replacement visibility
Make candidate → promotion → live → replacement completely observable.
Priority 5 — Strategy health/decay
Build continuous monitoring.
Priority 6 — Research feedback loop
Feed live results back into research.
Priority 7 — Continuous discovery
Keep generating and evaluating new strategies.
Priority 8 — K/L/M
Continue the existing research roadmap in parallel.
Priority 9 — Scaling architecture
Prepare the system for larger capital without changing the core architecture.

## 21. IMPORTANT: DO NOT TURN THIS INTO ANOTHER PLANNING EXERCISE

Do not respond by creating another giant roadmap and stopping.
Do not ask me to approve each component.
Do not tell me to wait until we have proven profitability before building the infrastructure.
Do not stop because the current strategies are not profitable.
Do not restart the frozen evolutionary search.
Do not replace the existing architecture simply because it isn't perfect.
Build the next useful version.
If a component already exists, improve it instead of duplicating it.
If something is broken, fix it.
If something is missing, implement it.
If something cannot safely be implemented because of a genuine external dependency, document the dependency and continue with everything else.

## 22. THE SYSTEM MUST REMAIN RUNNING WHILE IT IMPROVES

The desired operating model is:

```text
                 ┌─────────────────────┐
                 │   LIVE TRADING      │
                 └──────────┬──────────┘
                            │
                            ▼
                    LIVE PERFORMANCE
                            │
                            ▼
                 ┌─────────────────────┐
                 │  STRATEGY LEARNING  │
                 └──────────┬──────────┘
                            │
                            ▼
                 ┌─────────────────────┐
                 │ NEW STRATEGIES      │
                 └──────────┬──────────┘
                            │
                            ▼
                 BACKTEST / ROBUSTNESS
                            │
                            ▼
                    PAPER / FORWARD
                            │
                            ▼
                     ELIGIBILITY
                            │
                            ▼
                       RANKING
                            │
                            ▼
                 ┌─────────────────────┐
                 │ FIVE LIVE SLOTS     │
                 └─────────────────────┘

```

This is a continuous loop.
The machine should get better while it is running.

## 23. DEFINITION OF DONE

This phase is complete only when:

1. I can open a dashboard and see Stockbot2000 operating live.
2. I can see all five strategy slots.
3. I can see every live position.
4. I can see live P&L.
5. I can see stops and exits.
6. I can see the live event stream.
7. I can see the complete strategy leaderboard.
8. I can see potential replacement strategies.
9. I can see why a strategy was promoted or replaced.
10. I can see research activity occurring in the background.
11. New strategies can move through the pipeline without manual intervention.
12. Live performance feeds back into strategy evaluation.
13. Strategy degradation is detected automatically.
14. Qualified strategies can automatically replace weaker live strategies.
15. The system can restart and reconcile itself safely.
16. The live trading system remains isolated from research code.
17. K, L and M continue progressing.
18. The entire system can continue operating without me manually starting every research/trading cycle.

## 24. FIRST ACTION

Start implementation now.
First inspect the current repository and identify what already exists for:

* live trading
* ranking
* strategy records
* paper trading
* execution
* monitoring
* reports
* dashboards
* logging
* research
* scheduled jobs

Reuse existing infrastructure.
Then implement the Live Control Center first, followed by live reliability and continuous strategy monitoring.
Do not spend the majority of this phase explaining what could be built.
Build it.
Keep Stockbot2000 LIVE.
Keep the research engine running.
Keep improving the machine.
At the end of the implementation session report:

```text
IMPLEMENTED
FILES/MODULES CHANGED
DATABASE/SCHEMA CHANGES
LIVE COMPONENTS AFFECTED
TESTS RUN
LIVE TESTS RUN
CURRENT SYSTEM STATUS
CURRENT LIVE STRATEGIES
CURRENT RANKING
NEW RESEARCH ACTIVITY
BLOCKERS
NEXT AUTOMATIC JOBS
STARTUP/DEPLOYMENT COMMANDS

```

The ultimate goal remains:
Stockbot2000 continuously discovers, tests, ranks, selects, trades, monitors, replaces, and improves strategies autonomously while remaining observable to the operator.
