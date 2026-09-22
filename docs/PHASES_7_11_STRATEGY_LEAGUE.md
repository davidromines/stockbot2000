# STOCKBOT2000 — PHASES 7–11
# Continuous Strategy Laboratory, Strategy League & Fundamental Value

> **STATUS: ROADMAP ONLY — NOT IMPLEMENTED.** Added 2026-09-22 at the user's
> direction. **This is the new direction of the project and a full revamp of its
> planning.** All existing systems integrate into it. No code has been written,
> no experiments run, no paper trading started, no broker capability connected,
> no SEC dataset downloaded. The plan below is reproduced as written.
>
> The integration analysis this plan requires as its deliverable — dependencies,
> module reuse, architectural gaps, schema changes, risks, minimum
> infrastructure and implementation order — is in
> **`ROADMAP_INTEGRATION.md`**.

---

## Context and rationale

Stockbot2000 should become a continuous strategy research laboratory +
paper-trading league + promotion pipeline, rather than a system that simply
searches for a historically good backtest.

The current system already has the beginnings of this: 16 forward paper funds,
daily paper trading, generated daily books, and a manual path into the Robinhood
account. It does not yet have the persistent strategy league/promotion system.

There is a substantial body of documented approaches worth turning into explicit
hypotheses for Stockbot2000 to test, including value, profitability/quality,
momentum, earnings momentum, value+momentum, defensive/low-volatility, and
combinations of these. Research has documented value and momentum across
markets, gross profitability as a potential return characteristic, and
interactions between value and momentum. **These should be tested by Stockbot,
not assumed to work.**

For the fundamental-data side, the SEC is an excellent foundation: its EDGAR
APIs provide company submissions and extracted XBRL financial-statement data,
including 10-Q and 10-K filings, updated throughout the day.

### One important architectural change

The rule must **not** simply be:

> "The five strategies with the highest profit get real money."

That could cause five strategies to become highly correlated versions of the
same trade.

Instead:

```text
All strategies compete → paper trade → earn a score → become eligible
→ top 5 eligible strategies receive capital, subject to risk/correlation/
  diversification constraints.
```

Profit should absolutely matter, and beating the S&P should **not** be a
requirement for promotion. But the system should also record:

* absolute return
* excess return
* drawdown
* Sharpe/Sortino
* win rate
* profit factor
* turnover
* transaction costs
* liquidity
* volatility
* correlation with other live strategies
* live-vs-backtest degradation
* minimum number of trades
* minimum forward-testing duration

That gives a self-improving system without allowing five copies of the same
strategy to occupy the five slots.

### Capital allocation, not equal weighting

The real-money system should eventually be capital allocation, not simply "five
strategies each get an equal amount":

```text
Strategy #1 → 30%
Strategy #2 → 25%
Strategy #3 → 20%
Strategy #4 → 15%
Strategy #5 → 10%
```

or whatever allocation the research demonstrates is appropriate. That is a
future research question, not something to implement now. For now, establish the
framework that lets Stockbot discover whether such allocation schemes actually
work.

---

# STOCKBOT2000 — PROJECT PLAN EXPANSION
# Add Future Phases Only — DO NOT IMPLEMENT YET

You are the project manager and lead architect for Stockbot2000.

We are expanding the long-term project roadmap.

**IMPORTANT: DO NOT IMPLEMENT ANY OF THE PHASES IN THIS PROMPT YET.**

Your task right now is ONLY to:

1. Review the requirements below.
2. Add these phases to the Stockbot2000 project plan.
3. Define their objectives, dependencies, architecture, acceptance criteria, and
   future implementation order.
4. Integrate them with the existing Stockbot2000 architecture and the existing
   Phase 6 Research Integrity & Independent Validation plan.
5. Identify conflicts, dependencies, or architectural changes that will
   eventually be required.
6. Do NOT create implementation code.
7. Do NOT modify the production trading system.
8. Do NOT enable live trading.
9. Do NOT start the strategy league.
10. Do NOT download the proposed historical financial database yet.
11. Do NOT execute the proposed experiments yet.

This is a ROADMAP/ARCHITECTURE task only.

## PROJECT VISION

Stockbot2000 should eventually become a continuously operating quantitative
research laboratory.

The long-term system should:

* continuously generate investment ideas
* test historical hypotheses
* backtest strategies
* validate them against Stockbot's research-integrity controls
* forward-test them with paper money
* continuously grade their performance
* maintain a permanent strategy leaderboard
* promote successful strategies
* demote unsuccessful strategies
* continually test new ideas
* continually retest old ideas
* maintain historical performance records
* identify the best currently eligible strategies
* allocate real capital to a small number of proven strategies
* continuously monitor those live strategies
* automatically demote strategies when evidence deteriorates
* replace them with stronger paper-tested strategies
* keep the research process running continuously

The goal is NOT to find one permanent "perfect strategy."

The goal is to create a system in which strategies compete continuously and
evidence determines which strategies receive capital.

## IMPORTANT PRINCIPLE

A strategy does NOT need to beat the S&P 500 to be considered useful.

Stockbot should record:

* absolute return
* benchmark-relative return
* risk-adjusted return
* drawdown
* volatility
* turnover
* transaction costs
* liquidity
* consistency
* forward performance
* live performance

However, beating SPY must NOT be a mandatory promotion criterion.

A strategy producing positive, repeatable, risk-adjusted returns may have
economic value even if it does not outperform SPY.

The benchmark remains a measurement/reference point, not an automatic pass/fail
requirement.

---

# NEW PHASE 7
# CONTINUOUS STRATEGY LABORATORY & PAPER TRADING LEAGUE

## Objective

Transform the existing collection of backtests and paper funds into a persistent
strategy competition.

Every strategy becomes a first-class object with a permanent identity and
lifecycle.

Conceptually:

```text
IDEA
→ BACKTEST
→ VALIDATION
→ PAPER TRADING
→ ELIGIBILITY
→ RANKING
→ LIVE CANDIDATE
→ LIVE
→ MONITORING
→ PROMOTION / DEMOTION / RETIREMENT
```

## Strategy Object

Define a future standardized strategy schema.

Every strategy should eventually have:

* unique strategy ID
* strategy name
* strategy version
* strategy family
* author/source
* creation timestamp
* parent strategy
* ancestry
* hypothesis
* universe
* entry rules
* exit rules
* position sizing
* holding period
* required data
* parameters
* backtest results
* validation results
* paper results
* live results
* transaction costs
* risk metrics
* correlation metrics
* status
* rank
* promotion history
* demotion history
* retirement reason

**Never overwrite historical strategy versions.** If a strategy changes
materially, create a new version.

## Strategy Lifecycle

Define explicit future states:

```text
DISCOVERED
BACKTESTING
VALIDATING
PAPER
ELIGIBLE
LIVE_CANDIDATE
LIVE
DEMOTED
SUSPENDED
RETIRED
```

Define the state-transition rules during implementation.

## PAPER TRADING ARENA

Stockbot already has forward paper funds, but the current system is not yet the
full persistent strategy league envisioned here.

The existing 16 strategy paper funds should become the foundation for this
future architecture.

The new system should eventually support hundreds or thousands of
simultaneously tracked paper strategies without mixing their results.

Every strategy receives a virtual portfolio.

Each strategy must have:

* virtual starting capital
* positions
* orders
* fills
* cash
* P&L
* realized P&L
* unrealized P&L
* drawdown
* trade history
* daily equity curve
* transaction costs
* slippage
* exposure
* turnover

Paper trading must use the same execution assumptions as realistically possible.

## BACKTEST + FORWARD TEST CONTINUITY

A strategy should not be considered successful simply because its backtest is
good.

The future system should explicitly track:

```text
BACKTEST
→ OUT-OF-SAMPLE
→ PAPER
→ LIVE
```

and measure degradation at each stage.

Create future metrics such as:

```text
backtest_return
validation_return
paper_return
live_return
```

and:

```text
paper_vs_backtest_degradation
live_vs_paper_degradation
live_vs_backtest_degradation
```

This should allow Stockbot to learn how predictive its own backtests are.

## STRATEGY SCOREBOARD

Create a future persistent leaderboard.

Every strategy should have a current ranking plus complete historical ranking.

Potential metrics:

* cumulative return
* annualized return
* Sharpe
* Sortino
* maximum drawdown
* Calmar
* win rate
* profit factor
* expectancy
* volatility
* turnover
* transaction costs
* liquidity
* number of trades
* duration of paper record
* live performance
* benchmark-relative performance
* correlation to existing live strategies

**Do not define the final weighting yet.** Phase 7 should establish the
architecture for testing different scoring formulas.

## TOP-5 LIVE STRATEGY PIPELINE

Create the future concept of a `LIVE STRATEGY ROSTER`.

The default future objective is to maintain approximately five live strategies.

However, "top five" must mean:

```text
TOP FIVE ELIGIBLE STRATEGIES AFTER RISK AND CORRELATION CONSTRAINTS
```

rather than simply the five highest raw-return strategies.

This prevents five nearly identical strategies from consuming the entire live
portfolio.

The future promotion engine should consider:

* profitability
* minimum forward sample
* drawdown
* consistency
* transaction costs
* liquidity
* strategy correlation
* live/backtest degradation
* operational health
* risk limits

The exact formula should be researched and experimentally validated before
implementation.

## CONTINUOUS PROMOTION / DEMOTION

The strategy league must never be static.

New strategies enter. Existing strategies continue paper trading. Existing
strategies can rise. Existing strategies can fall. Live strategies can be
demoted. Paper strategies can replace live strategies. Retired strategies remain
in the historical database.

**Nothing should disappear simply because it performed badly.**

## STRATEGY MEMORY

Stockbot must maintain a permanent strategy history.

For every strategy:

* why it was created
* what hypothesis it tested
* what data it used
* what version it was
* what it predicted
* how it performed
* why it was promoted
* why it was demoted
* why it was retired

This creates a permanent research memory.

## Phase 8 architecture diagram (Continuous Strategy Arena)

```text
                    STRATEGY FACTORY
                          │
            ┌─────────────┴─────────────┐
            │                           │
       HUMAN IDEAS                 MACHINE IDEAS
            │                           │
            └─────────────┬─────────────┘
                          ↓
                    BACKTEST LAB
                          ↓
                 VALIDATION GATES
                          ↓
                PAPER TRADING ARENA
                          ↓
                 STRATEGY SCOREBOARD
                          ↓
             ┌────────────┴────────────┐
             │                         │
         PROMOTION                 DEMOTION
             │                         │
             ↓                         ↓
       LIVE CANDIDATES             PAPER LAB
             │
             ↓
        RISK / CORRELATION
             │
             ↓
        TOP 5 LIVE STRATEGIES
             │
             ↓
        ROBINHOOD AGENTIC
             │
             ↓
       LIVE PERFORMANCE
             │
             └──────────→ SCOREBOARD
```

Example permanent scoreboard record:

```text
Strategy: Value + Quality v17

Created: 2026-09-22

Backtest:
Return:              +18.4%
SPY:                 +11.2%
Max Drawdown:        -9.3%
Sharpe:               1.41

Forward paper:
Return:               +7.2%
Trades:                   43
Profit factor:          1.62
Max DD:               -4.8%

Live:
Capital:             $2,000
Return:                +3.7%
Trades:                   11
Current rank:             #3

Status:
LIVE
```

**Never overwrite the history.** If Strategy v17 gets modified, that becomes
v18. This prevents the system from quietly changing a strategy while pretending
its historical record belongs to the original.

---

# NEW PHASE 8
# CONTINUOUS STRATEGY DISCOVERY & REAL-WORLD STRATEGY LIBRARY

The system should eventually combine:

1. Machine-generated ideas
2. Human-generated ideas
3. Published academic research
4. Documented professional investment methodologies
5. Existing Stockbot strategies
6. Combinations of existing strategies

**All external strategies must be treated as HYPOTHESES.** Never assume a
published strategy works in Stockbot's universe. Every strategy must pass the
same research-integrity framework.

## RESEARCH LIBRARY

Create a future structured strategy library: `strategy_library`

Each imported strategy should contain:

* strategy name
* original author/researcher
* source
* publication/book/paper
* original hypothesis
* original universe
* original time period
* original metrics
* required data
* implementation interpretation
* Stockbot implementation
* known biases
* limitations
* results
* validation status

## INITIAL STRATEGY FAMILIES TO RESEARCH

### VALUE

* book-to-market
* earnings yield
* free-cash-flow yield
* EV/EBITDA
* EV/EBIT
* price/free cash flow
* EV/sales
* dividend yield
* shareholder yield
* Graham-style measures
* net-net concepts where applicable

Greenblatt's documented approach is particularly straightforward to encode:
earnings yield for cheapness and return on capital for quality.

### QUALITY

* ROIC
* ROE
* ROA
* ROCE
* gross profitability
* operating margin
* free cash flow quality
* earnings stability
* balance-sheet quality
* leverage
* accruals

Gross profitability is especially interesting because Novy-Marx's research found
gross profits/assets to have predictive power comparable to book-to-market in
cross-sectional tests.

### MOMENTUM

* 3-month momentum
* 6-month momentum
* 9-month momentum
* 12-month momentum
* 12-1 momentum
* relative strength
* trend following
* breakouts
* moving-average systems

Momentum has a substantial academic literature, including work examining both
price and earnings momentum.

### FUNDAMENTAL MOMENTUM

* EPS acceleration
* revenue acceleration
* margin expansion
* improving ROIC
* improving free cash flow
* earnings surprises
* fundamental revisions

### VALUE + MOMENTUM

Explicitly test combinations of value and momentum. There is published research
specifically examining the interaction between value and momentum, so Stockbot
should test combinations rather than treating them as completely independent
ideas.

### VALUE + QUALITY

Explicitly test combinations of cheapness and financial quality:

```text
Cheap
+
Profitable
+
Low leverage
+
Positive FCF
```

### DEFENSIVE

* low volatility
* low beta
* quality + low volatility
* stable earnings
* strong balance sheet

### EVENT-DRIVEN

* earnings announcements
* earnings surprises
* post-earnings drift
* insider activity
* buybacks
* dividend changes
* corporate actions
* spin-offs

### TECHNICAL / QUANTITATIVE

* mean reversion
* trend following
* RSI
* MACD
* moving averages
* Bollinger-style systems
* breakouts
* volatility contraction

### MACHINE LEARNING

* XGBoost
* LightGBM
* CatBoost
* logistic regression
* random forests
* ensemble models
* regime models
* neural approaches where justified

Every strategy must pass the same anti-leakage, transaction-cost, point-in-time,
and forward-testing framework.

Each one becomes a **hypothesis, not a belief.** That fits what Stockbot has
already learned: seemingly impressive strategies can be artifacts.

---

# NEW PHASE 9
# FUNDAMENTAL VALUE INTELLIGENCE ENGINE

This should become a major independent Stockbot subsystem, not just another
feature in the existing strategy generator.

Its purpose is to identify potentially undervalued public companies using their
actual reported financial information, and to answer:

> What companies appear fundamentally undervalued based on their publicly
> reported financial information?

The system should eventually produce a long-term value-investment universe
independent of the short-term strategy league.

## PRIMARY DATA SOURCE

Research and plan integration with SEC EDGAR, which provides APIs for:

* company submissions
* filing history
* extracted XBRL financial data
* 10-K
* 10-Q
* 8-K
* 20-F
* 40-F
* 6-K
* related filing information

Use official SEC data as the primary source wherever practical. Design the
architecture so additional providers can eventually supplement SEC data.

## FUNDAMENTAL DATA PIPELINE

```text
SEC EDGAR
   ↓
Filing ingestion
   ↓
Raw filing archive
   ↓
XBRL extraction
   ↓
Normalized financial statements
   ↓
Point-in-time financial database
   ↓
Financial analysis engine
   ↓
Valuation engine
   ↓
Quality engine
   ↓
Risk engine
   ↓
Value ranking
   ↓
Long-term watchlist
   ↓
Future Value Fund
```

## CRITICAL POINT-IN-TIME REQUIREMENT

This subsystem MUST NOT use today's financial database to reconstruct what
investors supposedly knew in the past.

A financial number cannot simply be stored as:

```text
AAPL revenue = $X
```

It needs something more like:

```text
AAPL
Metric: Revenue
Value: $X
Fiscal Period: Q2 2026
Filed: 2026-07-30
Available to Market: 2026-07-31
Source: 10-Q
Accession: XXXXX
```

Every financial fact must eventually retain:

* company
* CIK
* ticker
* metric
* value
* fiscal period
* filing date
* accepted date/time
* source filing
* accession number
* amendment status
* data provenance

The backtester must be able to answer:

> "What financial information was publicly available as of this exact decision
> date?"

rather than:

> "What does the database know today?"

This requirement is mandatory because Stockbot has already experienced
data-freshness and look-ahead problems.

## FINANCIAL STATEMENT ANALYSIS

### INCOME STATEMENT

revenue · revenue growth · gross profit · gross margin · EBITDA · EBITDA margin ·
EBIT · EBIT margin · operating income · operating margin · net income · EPS ·
EPS growth · earnings stability · R&D · SG&A · operating leverage

### BALANCE SHEET

cash · net cash · debt · net debt · debt/equity · debt/EBITDA · current ratio ·
quick ratio · working capital · book value · tangible book value · goodwill ·
intangible assets · asset growth

### CASH FLOW

operating cash flow · capital expenditures · free cash flow · FCF margin ·
FCF yield · FCF growth · cash conversion · FCF/net income

### PROFITABILITY / RETURNS

ROE · ROA · ROIC · ROCE · gross profitability · asset turnover ·
capital efficiency

## VALUATION ENGINE

P/E · forward P/E where reliable data exists · P/B · P/S · EV/Sales · EV/EBITDA ·
EV/EBIT · FCF yield · earnings yield · dividend yield · shareholder yield ·
PEG where appropriate

**Do NOT assume any one metric works for every industry.** A bank, software
company, REIT, manufacturer and oil company have very different economics. The
eventual system should support industry-aware valuation.

## INTRINSIC VALUE ENGINE

Plan future support for multiple independent valuation methodologies.

### DCF

```text
Revenue
 ↓
Operating margins
 ↓
EBIT
 ↓
Taxes
 ↓
NOPAT
 ↓
+ D&A
- CapEx
- Change in NWC
 ↓
Free Cash Flow
 ↓
Discount rate
 ↓
Terminal value
 ↓
Enterprise value
 ↓
Equity value
```

### EARNINGS VALUATION

Compare normalized earnings with historical multiples, industry multiples,
sector multiples and market multiples.

### FREE CASH FLOW VALUATION

Estimate intrinsic value using sustainable FCF.

### RELATIVE VALUATION

```text
Company
vs
Industry
vs
Sector
vs
Market
```

### ASSET-BASED VALUATION

Where appropriate for asset-heavy companies.

## VALUE SCORE

Eventually create a multi-dimensional fundamental score. Potential components:

```text
VALUE
QUALITY
PROFITABILITY
GROWTH
BALANCE SHEET
CASH FLOW
MANAGEMENT/CAPITAL ALLOCATION
RISK
MARGIN OF SAFETY
```

**Do NOT finalize the scoring formula now.** The scoring system itself must
eventually become an experiment.

## VALUE WATCHLIST

Eventually produce a continuously updated list of long-term candidates:

```text
VALUE RANKING

Ticker   Value   Quality   Growth   Balance Sheet   FCF   Intrinsic Value
---------------------------------------------------------------------------
ABC       94       87        71          91          95       $142
XYZ       91       92        63          88          89       $87
DEF       88       81        84          94          91       $64
```

Then:

```text
Current price
      ↓
Intrinsic value
      ↓
Margin of safety
      ↓
Risk adjustment
      ↓
Long-term candidate
```

Fields: Ticker · Value Score · Quality Score · Growth Score · Balance Sheet
Score · FCF Score · Estimated Intrinsic Value · Current Price · Margin of
Safety · Risk · Industry · Financial Data Date · Last Filing Date

**The system should explain WHY each company receives its ranking.**

## FUTURE VALUE FUND

Reserve architecture for a future independent portfolio: **STOCKBOT VALUE FUND**

This should be separate from the tactical strategy league.

* The tactical system asks: "Which strategies are currently producing attractive
  trading results?"
* The value system asks: "Which companies appear fundamentally undervalued based
  on their financial statements and valuation?"

The two systems may eventually interact, but they should remain independently
measurable.

Eventually:

* **Stockbot Tactical Fund** — top 5 continuously selected strategies
* **Stockbot Value Fund** — long-term fundamentally selected companies

Two completely different investment philosophies running through the same
research infrastructure.

---

# NEW PHASE 10
# LIVE CAPITAL ALLOCATION & STRATEGY PROMOTION ENGINE

Architecture:

```text
STRATEGY LAB
↓
PAPER TRADING
↓
ELIGIBILITY
↓
RANKING
↓
RISK ENGINE
↓
CORRELATION CHECK
↓
CAPITAL ALLOCATION
↓
ORDER VALIDATION
↓
ROBINHOOD AGENTIC
↓
RECONCILIATION
↓
LIVE PERFORMANCE
↓
STRATEGY SCOREBOARD
```

The Robinhood integration must remain behind the existing execution/risk
architecture. **The strategy layer should never directly place arbitrary
orders.**

## LIVE STRATEGY REPLACEMENT

```text
Strategy A enters top five
↓
receives capital
↓
underperforms
↓
falls below promotion threshold
↓
risk engine evaluates
↓
strategy is demoted
↓
capital becomes available
↓
best eligible paper strategy becomes candidate
↓
promotion process
↓
new strategy receives capital
```

All decisions must be logged.

## NO AUTOMATIC LIVE DEPLOYMENT YET

This project-plan phase must NOT enable automatic live promotion.

Before live promotion exists, the project must separately establish:

* minimum paper-testing period
* minimum number of trades
* risk limits
* maximum position size
* maximum portfolio exposure
* correlation limits
* liquidity limits
* kill switches
* operational health checks
* broker reconciliation
* strategy degradation rules
* emergency demotion rules
* human override
* complete audit logging

---

# PHASE 11
# CONTINUOUS RESEARCH LOOP

Eventually Stockbot should operate as a perpetual research system.

EVERY DAY:

1. ingest new market data
2. ingest new SEC filings
3. update fundamentals
4. update paper portfolios
5. update strategy scores
6. evaluate live strategies
7. discover new hypotheses
8. run eligible research
9. update strategy rankings
10. check promotion/demotion conditions
11. generate reports
12. preserve all historical results

**The research loop should never overwrite previous experiments.**

## STRATEGY GENERATION SOURCES

1. existing Stockbot strategies
2. evolutionary search
3. ML discovery
4. human hypotheses
5. academic research
6. documented professional methodologies
7. combinations of existing strategies
8. modifications of existing strategies
9. fundamental research
10. event-driven research

Every idea enters the same research pipeline.

## RESEARCH GOVERNANCE

Do NOT allow the continuous discovery system to recreate the problems Stockbot
has already encountered.

Every strategy must have:

* unique identity
* ancestry
* source
* hypothesis
* timestamp
* immutable results
* data version
* code version
* parameter version
* validation version

**Seeded strategies must be clearly distinguished from machine-discovered
strategies. Seed contamination must remain impossible to hide.**

## MULTIPLE TESTING

The continuous research system must explicitly track:

* total strategies tested
* total variants tested
* total experiments
* total hypotheses
* effective trials where measurable
* survivors
* failures
* retired strategies
* strategies promoted
* strategies demoted
* false discoveries
* paper-to-live degradation

**A strategy leaderboard must never be interpreted independently from the number
of strategies tested.**

## FORWARD PERFORMANCE IS THE FINAL ARBITER

```text
BACKTEST ≠ PROOF
VALIDATION ≠ PROOF
PAPER ≠ PROOF
```

Backtests generate hypotheses. Validation provides evidence. Paper trading
provides forward evidence. Live trading provides real-world evidence.

LIVE PERFORMANCE is the strongest operational evidence available to Stockbot,
while recognizing that live samples remain noisy and limited.

## RESEARCH SOURCES TO INCORPORATE

Create a research backlog for documented strategies and academic findings.
Potential starting areas:

value · momentum · value + momentum · profitability · quality · defensive
equity · earnings momentum · fundamental momentum · transaction-cost-aware
anomaly research · shareholder yield · accruals · financial statement quality ·
capital allocation · insider activity · event-driven strategies

**Important:** do not assume published findings remain profitable after
Stockbot's universe, transaction costs, liquidity constraints, execution model,
point-in-time data, delisting treatment, holding periods, tax assumptions and
capital constraints.

Every external strategy must be independently tested.

Transaction costs should remain **inside** the competition. Research on
anomalies finds that costs materially reduce profitability, particularly for
higher-turnover strategies — consistent with what Stockbot has already learned
from its own next-open and cost corrections.

## ARCHITECTURAL PRINCIPLE

Stockbot2000 should eventually have three distinct layers:

1. **RESEARCH FACTORY** — creates and tests ideas.
2. **STRATEGY LEAGUE** — continuously paper-trades and ranks ideas.
3. **CAPITAL DEPLOYMENT** — deploys capital only to strategies that satisfy the
   promotion and risk requirements.

**Do not collapse these layers.**

---

# FUTURE PROJECT ROADMAP

```text
Phase 6   Research Integrity & Independent Validation
Phase 7   Continuous Strategy Laboratory & Paper Trading League
Phase 8   Continuous Strategy Discovery & Real-World Strategy Library
Phase 9   Fundamental Value Intelligence Engine
Phase 10  Live Capital Allocation & Strategy Promotion
Phase 11  Continuous Research Loop
```

These phases are ROADMAP ITEMS ONLY. Do not implement them during this task.

# DELIVERABLE REQUIRED NOW

1. Update the project plan/documentation with Phases 7–11.
2. Show dependencies between Phase 6 and these new phases.
3. Identify any existing Stockbot modules that will eventually be reused.
4. Identify architectural gaps that must eventually be addressed.
5. Identify database/schema changes that will eventually be required.
6. Identify which components should remain independent.
7. Identify risks with continuously promoting strategies.
8. Identify risks with using raw profitability as the only ranking metric.
9. Identify the minimum infrastructure required before Phase 7 can begin.
10. Create a proposed implementation order.

```text
DO NOT IMPLEMENT.
DO NOT RUN EXPERIMENTS.
DO NOT START PAPER TRADING.
DO NOT CHANGE LIVE TRADING.
DO NOT CONNECT NEW BROKER CAPABILITIES.
DO NOT DOWNLOAD THE SEC DATASET.
```

Only update the roadmap and architecture.

The objective of this task is to make Stockbot2000's future direction explicit
before implementation begins.

---

## Why these phases fit Stockbot's current state

The existing build record already shows the pieces beginning to converge:
forward paper funds, a daily paper process, a signal/risk/execution layer, and
the beginnings of a real-money path. **The missing piece is the persistent
competition and promotion layer connecting all of those components.**

The value system should be a genuinely separate pillar. Stockbot's own research
already discovered that value rankings were unintentionally acting partly as
size rankings — exactly the sort of thing the new fundamental engine should be
designed to prevent.

The external research suggests a particularly interesting initial library:
value + quality/profitability + momentum, rather than treating "value" as simply
buying the lowest P/E stocks.

The eventual architecture:

```text
Thousands of ideas → rigorous backtesting → hundreds of paper strategies
→ continuously ranked strategy league → risk-filtered top 5
→ Robinhood Agentic → live results feed back into the league → repeat forever.
```

And alongside that:

```text
SEC filings → fundamental intelligence → intrinsic-value analysis
→ long-term value candidates → eventually a separate Value Fund.
```
