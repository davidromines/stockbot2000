# Addendum A — Autonomous 5-Slot Profitability & Trading System

Supplied by the user on 2026-09-24 and reproduced verbatim below. It defines
the end product and overrides any ambiguity about it elsewhere in the plan.
Integration against the existing system — which existing rules it supersedes,
the reuse map, the build steps and the decisions awaiting review — is in
`ROADMAP_INTEGRATION.md`, Stage I.

**Status: PLANNED — entered 2026-09-24, awaiting the user's review of the
roadmap before any implementation.**

---

STOCKBOT2000 — PROJECT PLAN ADDENDUM
AUTONOMOUS 5-SLOT PROFITABILITY & TRADING SYSTEM
THIS ADDENDUM OVERRIDES ANY AMBIGUITY ABOUT THE END PRODUCT
The purpose of Stockbot2000 is to build a fully automated stock-trading system.
Stockbot2000 is NOT primarily a backtesting project.
Stockbot2000 is NOT primarily a research dashboard.
Stockbot2000 is NOT successful merely because it can prove that strategies do or do not work.
The ultimate product is:
A continuously learning, continuously testing, continuously ranking, fully automated trading system that selects the five best currently eligible trading strategies and automatically uses those five strategies to trade five independent fund slots through Robinhood.
The system must continuously search for better strategies and automatically replace weaker strategies with stronger ones.
1. THE ACTUAL PRODUCT
Stockbot2000 operates one overall trading fund of approximately:
$100 total
Divided into:
5 independent strategy slots
Approximately:
$20 per slot
Conceptually:

```text
                    STOCKBOT2000
                         │
              ┌──────────┴──────────┐
              │                     │
        STRATEGY RESEARCH       LIVE TRADING
              │                     │
       Discover/Test/Rank       $100 Total
              │                     │
              └──────────┬──────────┘
                         │
                 5 LIVE FUND SLOTS
                         │
          ┌──────────────┼──────────────┐
          │              │              │
       SLOT 1         SLOT 2         SLOT 3
       Strategy A     Strategy B     Strategy C
          │              │              │
          └──────────────┼──────────────┘
                         │
                  ┌──────┴──────┐
                  │             │
               SLOT 4        SLOT 5
               Strategy D    Strategy E

```

Each slot is controlled by a different strategy.
The five slots should represent the five best currently eligible strategies, subject to the system's risk and duplication controls.
2. THE SYSTEM MUST BE FULLY AUTOMATIC
The intended final operating model is:

```text
Market Data
     ↓
Strategy Research
     ↓
Strategy Testing
     ↓
Strategy Ranking
     ↓
Select Best 5
     ↓
Generate Orders
     ↓
Risk / Stop-Loss Validation
     ↓
Robinhood
     ↓
Automatic Execution
     ↓
Position Monitoring
     ↓
P&L
     ↓
Strategy Ranking
     ↓
Replace Weak Strategies
     ↓
Back to Research

```

There should be no requirement for the user to manually:

* Select strategies
* Select stocks
* Enter orders
* Exit positions
* Replace strategies
* Move capital
* Monitor stop losses
* Decide which strategy gets a slot

The system must perform these functions automatically.
3. TRADING FREQUENCY
Stockbot2000 is explicitly permitted to trade:
Intraday
Positions can be opened and closed during the same trading session.
Interday / Swing
Positions can remain open overnight and for multiple days.
Day trading
Day trading is permitted.
Longer holding periods
Longer-duration strategies may also be used if they qualify for the appropriate strategy league.
There is no artificial requirement that every strategy hold positions for a particular amount of time.
The strategy determines the appropriate holding period.
4. THE FIVE SLOTS
The five slots are the actual capital-allocation mechanism.
Each slot should have:

```text
slot_id
current_strategy_id
strategy_version
allocated_capital
current_position
entry_price
stop_loss
target/exit logic
unrealized_pnl
realized_pnl
strategy_status
last_signal
last_trade

```

Example:

```text
Slot 1 → Momentum Strategy 27 → $20
Slot 2 → Mean Reversion 14 → $20
Slot 3 → Value/Momentum 8 → $20
Slot 4 → Breakout 31 → $20
Slot 5 → ML Strategy 12 → $20

```

These are examples only.
The actual five strategies must be selected dynamically by the system.
5. WHAT "BEST" MEANS
The system must NOT interpret "best" as:
Highest historical backtest return.
The system must determine the best strategies based on current evidence.
The primary objective is:
Positive trading profitability.
The system should therefore prioritize strategies demonstrating actual positive performance while considering:

* Net/gross P&L
* Forward performance
* Paper performance
* Live performance
* Drawdown
* Trade count
* Stability
* Recent performance
* Strategy degradation
* Data quality
* Liquidity
* Correlation/duplication
* Risk

However:
IMPORTANT PRIORITY
The user does NOT require:

* Beating SPY
* Beating the S&P 500
* Maximum Sharpe
* Institutional-style factor superiority
* Market outperformance

The primary objective is:
MAKE MONEY
A strategy producing positive P&L can be useful even if the market produced a higher return.
Benchmark performance should still be measured and displayed, but it is not the primary promotion requirement.
6. PROFITABILITY-FIRST OBJECTIVE
The primary objective function is:

```text
POSITIVE TRADING P&L

```

not:

```text
BEAT THE MARKET

```

not:

```text
MAXIMIZE BACKTEST SHARPE

```

not:

```text
MAXIMIZE PREDICTION ACCURACY

```

not:

```text
MAXIMIZE AUC

```

A strategy that predicts stocks correctly but loses money is not a successful trading strategy.
A strategy that produces positive P&L without beating SPY can still be a successful Stockbot2000 strategy.
7. COSTS
The system must still calculate and report:

* Commissions
* Spread
* Slippage
* Other execution costs

But costs are NOT the primary optimization target.
The user explicitly prioritizes:
Positive gross trading P&L.
Therefore the system should display both:

```text
Gross P&L
Costs
Net P&L

```

but should not reject an otherwise profitable strategy merely because it does not outperform a benchmark after an overly conservative hypothetical cost model.
Actual execution costs must be measured separately from modeled costs.
The system must never hide costs.
8. AUTOMATIC STRATEGY REPLACEMENT
This is one of the most important requirements.
Every slot is continuously evaluated.
If the strategy currently occupying a slot becomes inferior to another eligible strategy, Stockbot2000 must be able to replace it automatically.
Example:

```text
MONDAY

Slot 1 → Strategy A
Slot 2 → Strategy B
Slot 3 → Strategy C
Slot 4 → Strategy D
Slot 5 → Strategy E

```

Research discovers Strategy F.
After validation:

```text
Strategy F > Strategy E

```

The system automatically:

```text
1. Mark Strategy F eligible
2. Identify Strategy E as the weakest slot
3. Exit Strategy E's position according to its exit/risk rules
4. Remove Strategy E from Slot 5
5. Allocate Slot 5 to Strategy F
6. Execute Strategy F's trade
7. Record the replacement

```

No human intervention should be required.
9. REPLACEMENT MUST BE CONTROLLED
"Replace the loser" does NOT mean constantly churn strategies every few minutes.
Implement configurable replacement rules.
A replacement should require sufficient evidence.
Examples:

```text
Minimum strategy score advantage
Minimum evidence
Minimum paper/forward history
Minimum trade count
Risk eligibility
Liquidity eligibility
No active kill switch

```

The exact thresholds should be configurable.
Do NOT hard-code them into individual strategies.
The replacement engine should be centralized.
10. STRATEGY LEADERBOARD
Create a continuously updated leaderboard.
Example:

```text
RANK | STRATEGY | STATUS | P&L | DRAWDOWN | TRADES
----------------------------------------------------
1    | Strategy A | LIVE | +$8.42 | 4.2% | 31
2    | Strategy F | ELIGIBLE | +$7.81 | 3.8% | 44
3    | Strategy C | LIVE | +$6.12 | 5.1% | 28
4    | Strategy K | PAPER | +$5.88 | 6.2% | 67
5    | Strategy D | LIVE | +$5.21 | 7.0% | 35
...

```

The leaderboard must continuously update.
11. FIVE-SLOT SELECTION ENGINE
Create a dedicated:
LIVE SLOT ALLOCATION ENGINE
Its job is to determine:
Which five strategies should control the five live slots RIGHT NOW?
The engine should:

1. Gather all eligible strategies.
2. Remove strategies failing minimum requirements.
3. Remove strategies under kill conditions.
4. Apply liquidity rules.
5. Apply risk rules.
6. Apply strategy-family concentration rules.
7. Rank remaining strategies.
8. Select the five best eligible strategies.
9. Compare them against current live slots.
10. Replace weaker strategies when replacement criteria are satisfied.
11. Maintain five independent strategy assignments whenever capital/execution constraints permit.

12. STRATEGY DIVERSITY
The five slots should use five distinct strategy identities.
Avoid:

```text
Slot 1 → Rising 200 Stop 2.5
Slot 2 → Rising 200 Stop 2.6
Slot 3 → Rising 200 Stop 3.0
Slot 4 → Rising 200 Stop 3.3
Slot 5 → Rising 200 Stop 5.0

```

if these are effectively the same strategy family.
These should be recognized as correlated variants.
The system should prefer genuine strategy diversity when the evidence supports it.
However:
IMPORTANT
Do NOT force artificial diversification if only one strategy is currently profitable.
The system should not intentionally select bad strategies merely to make the portfolio look diverse.
13. IF ONLY ONE STRATEGY IS PROFITABLE
The system must handle this condition correctly.
If only one strategy is currently qualified:

```text
Slot 1 → profitable strategy
Slot 2 → available cash / inactive
Slot 3 → available cash / inactive
Slot 4 → available cash / inactive
Slot 5 → available cash / inactive

```

Do NOT automatically put money into losing strategies simply because five slots exist.
The goal is profitability, not filling five slots at any cost.
As additional strategies qualify, they can automatically receive slots.
14. CAPITAL ALLOCATION
Default configuration:

```text
Total Fund ≈ $100

Slot 1 ≈ $20
Slot 2 ≈ $20
Slot 3 ≈ $20
Slot 4 ≈ $20
Slot 5 ≈ $20

```

This is the default allocation.
Build the allocation system so these values are configurable.
Do not hard-code $20 into strategy logic.
15. STOP LOSSES ARE MANDATORY
Every live strategy must have a defined risk/exit mechanism.
A strategy cannot enter a live position without a valid risk plan.
The system must support:

* Fixed percentage stops
* ATR-based stops
* Volatility-based stops
* Strategy-specific stops
* Trailing stops
* Time-based exits
* Emergency exits

The strategy may determine which mechanism is appropriate.
16. STOP-LOSS EXECUTION MUST BE FAST
The stop-loss engine must monitor live positions continuously during market hours.
Do not rely solely on a once-per-day batch process.
Architecture:

```text
LIVE MARKET DATA
      ↓
POSITION MONITOR
      ↓
STOP/RISK ENGINE
      ↓
STOP TRIGGER
      ↓
ORDER GENERATION
      ↓
ROBINHOOD
      ↓
EXECUTION CONFIRMATION

```

The system should react as quickly as the available market-data and broker interfaces permit.
If an order fails:

```text
Retry / alternate permitted order mechanism
        ↓
Escalate
        ↓
Emergency risk handling

```

All failures must be logged.
17. STRATEGY EXIT VS STOP LOSS
These are different mechanisms.
Strategy exit
The strategy determines that its thesis is no longer valid.
Stop loss
Risk management determines that the position must be reduced or exited.
The stop-loss system overrides the strategy.
Example:

```text
Strategy says HOLD
Risk Engine says STOP
→ SELL

```

Risk controls always have priority over strategy signals.
18. INTRADAY SIGNAL ENGINE
Stockbot2000 must support continuous signal evaluation during market hours.
Do not design the system around:

```text
Run once every evening.

```

Instead support:

```text
Pre-market
Market open
Intraday monitoring
Intraday signals
Stop monitoring
Position updates
End-of-day reconciliation
After-hours research

```

The exact polling/streaming frequency should be determined by available Robinhood and market-data capabilities.
19. RESEARCH NEVER STOPS
While the five live slots are trading, the research engine continues operating.
Example:

```text
LIVE TRADING
      │
      ├── Strategy A
      ├── Strategy B
      ├── Strategy C
      ├── Strategy D
      └── Strategy E

              +

CONTINUOUS RESEARCH
      │
      ├── New strategy ideas
      ├── New research
      ├── New data
      ├── New combinations
      ├── Backtests
      ├── Walk-forward tests
      ├── Paper trading
      └── Strategy ranking

```

Trading must NOT pause simply because research is occurring.
20. CONTINUOUS PROMOTION
The pipeline should be:

```text
IDEA
 ↓
BACKTEST
 ↓
VALIDATION
 ↓
PAPER
 ↓
ELIGIBLE
 ↓
RANKED
 ↓
LIVE CANDIDATE
 ↓
LIVE

```

The system should continuously promote good strategies upward.
21. CONTINUOUS DEMOTION
Likewise:

```text
LIVE
 ↓
PERFORMANCE DEGRADATION
 ↓
LOWER RANK
 ↓
REVIEW
 ↓
DEMOTION
 ↓
REPLACEMENT

```

A strategy that stops working should not remain in a slot simply because it was once successful.
22. CONTINUOUS LEARNING LOOP
The final system should behave like:

```text
             ┌────────────────────────────┐
             │                            │
             ▼                            │
        GENERATE IDEAS                    │
             │                            │
             ▼                            │
        TEST STRATEGIES                   │
             │                            │
             ▼                            │
        VALIDATE                          │
             │                            │
             ▼                            │
        PAPER TRADE                       │
             │                            │
             ▼                            │
        RANK                              │
             │                            │
             ▼                            │
       SELECT BEST 5                      │
             │                            │
             ▼                            │
       TRADE AUTOMATICALLY                │
             │                            │
             ▼                            │
       MEASURE RESULTS                    │
             │                            │
             ▼                            │
       DEMOTE LOSERS                      │
             │                            │
             ▼                            │
       PROMOTE WINNERS                    │
             │                            │
             └────── NEW RESEARCH ────────┘

```

This loop is the actual Stockbot2000 product.
23. FULL AUTOMATION REQUIREMENT
The finished system must automatically perform:
Research

* Generate ideas
* Import research
* Create strategy variants
* Backtest
* Validate
* Paper trade
* Rank

Selection

* Determine eligible strategies
* Select five
* Detect replacements

Trading

* Determine positions
* Determine entries
* Determine exits
* Determine stops
* Submit orders
* Monitor orders
* Confirm execution

Risk

* Monitor positions
* Trigger stops
* Enforce limits
* Handle failures
* Kill strategies when required

Capital management

* Allocate approximately $20 per slot
* Reallocate when strategies change
* Maintain available cash

Monitoring

* P&L
* Strategy performance
* Drawdown
* Execution
* Slippage
* Strategy degradation

Replacement

* Remove weak strategy
* Close its position
* Promote stronger strategy
* Allocate new capital
* Begin trading

Reporting

* Daily performance
* Strategy ranking
* Slot assignments
* Trades
* P&L
* Risk events
* Replacements

The user should not have to manually perform any of these routine operations.
24. HUMAN INTERVENTION
The system should require human intervention only for:

* Initial configuration
* Capital funding
* Security/account authorization
* System maintenance
* Explicit emergency shutdown
* Changing system-level parameters

Normal daily trading decisions should not require human approval.
25. EMERGENCY KILL SWITCH
Full automation requires a hard emergency stop.
Implement:

```text
GLOBAL KILL SWITCH

```

When activated:

```text
STOP NEW ORDERS
CANCEL PERMITTED OPEN ORDERS
EXIT POSITIONS ACCORDING TO EMERGENCY POLICY
FREEZE STRATEGY PROMOTIONS
ALERT USER

```

Also support strategy-level kill switches.
Example:

```text
GLOBAL SYSTEM → ON

Strategy A → ON
Strategy B → ON
Strategy C → OFF
Strategy D → ON
Strategy E → ON

```

26. AUTOMATIC DAILY REBALANCING
At least once each trading day, Stockbot2000 must perform a formal:
FIVE-SLOT REASSESSMENT
Process:

```text
1. Update all strategy results
2. Update rankings
3. Update paper strategies
4. Update live strategies
5. Check strategy degradation
6. Check risk
7. Check new eligible strategies
8. Compare current slots to candidates
9. Determine replacements
10. Close displaced positions where appropriate
11. Allocate replacement capital
12. Record decisions

```

This is in addition to continuous intraday risk monitoring.
27. DO NOT WAIT FOR LONG BACKTESTS TO FINISH
The research engine must operate asynchronously.
Trading continues while research continues.
For example:

```text
Process A → Live trading
Process B → Backtesting
Process C → Paper trading
Process D → Data ingestion
Process E → Strategy ranking
Process F → Research discovery

```

The architecture should support this separation.
28. SUCCESS CRITERION
The ultimate success metric is NOT:
"Did we find a strategy that beats the S&P?"
It is:
Can Stockbot2000 continuously identify strategies with positive trading performance and automatically deploy the strongest currently eligible strategies into the five live slots?
The long-term objective is:

```text
Positive P&L
+
Continuous improvement
+
Automatic replacement
+
Automatic execution
+
Automatic risk management

```

29. WHAT MUST NOT HAPPEN
Do NOT turn Stockbot2000 into a system that:

* Only produces signals for a human to trade.
* Requires the user to select the five strategies.
* Requires the user to manually enter orders.
* Requires the user to manually sell losing positions.
* Only trades once per day.
* Refuses day trading.
* Refuses intraday strategies.
* Requires every strategy to beat SPY.
* Requires every strategy to have institutional-level Sharpe.
* Keeps a strategy simply because it was historically successful.
* Fills empty slots with losing strategies.
* Stops researching while live strategies are trading.
* Stops trading while research is running.
* Uses backtest performance alone to select live strategies.
* Ignores live degradation.
* Allows a strategy to bypass the central risk engine.
* Relies on the user to watch stop losses.

30. IMPORTANT DISTINCTION: RESEARCH VS PRODUCT
The research system exists to feed the trading system.
The hierarchy is:

```text
                STOCKBOT2000
                     │
        ┌────────────┴────────────┐
        │                         │
  RESEARCH ENGINE            TRADING ENGINE
        │                         │
  Find strategies             Trade strategies
        │                         │
  Test strategies             Manage positions
        │                         │
  Rank strategies             Manage stops
        │                         │
        └───────────┬─────────────┘
                    │
             CAPITAL ALLOCATION
                    │
              FIVE LIVE SLOTS

```

The research engine is subordinate to the ultimate objective:
AUTOMATED PROFITABLE TRADING
31. FINAL PRODUCT DEFINITION
When someone asks:
"What is Stockbot2000?"
The answer should be:
Stockbot2000 is an autonomous algorithmic trading system that continuously discovers, tests, ranks, and paper-trades investment strategies, automatically selects the five best currently eligible strategies, allocates approximately $20 to each strategy, and automatically executes and manages their trades through Robinhood. It continuously monitors performance, risk, and strategy degradation and automatically replaces weaker strategies with stronger candidates.
That is the product.
32. CLAUDE'S IMPLEMENTATION DIRECTIVE
Treat this addendum as a hard product requirement.
Do not reinterpret the objective as "build a better backtester."
Do not reinterpret the objective as "prove whether existing strategies have alpha."
Do not spend the next phase primarily testing the existing Rising 200, XGBoost, ETF, MACD, or other strategies.
Do not stop after building the research components.
Build the complete system connecting:

```text
STRATEGY DISCOVERY
→
TESTING
→
RANKING
→
FIVE-SLOT SELECTION
→
RISK
→
STOP LOSS
→
ROBINHOOD
→
AUTOMATIC EXECUTION
→
MONITORING
→
AUTOMATIC REPLACEMENT
→
CONTINUOUS RESEARCH

```

The final system must be capable of operating without daily human intervention.
If an existing component already performs part of this function, integrate it rather than rebuilding it.
If an existing component is incomplete, finish it.
If an existing component conflicts with this product definition, modify it.
Do not ask the user to approve every implementation step.
Do not stop because current strategies are unprofitable.
Do not stop because backtests fail.
Do not stop because a research hypothesis fails.
Failures are inputs to the continuous research engine.
The finished system must continue searching for better strategies while the current five slots are trading.
Build the product, not another experiment.
