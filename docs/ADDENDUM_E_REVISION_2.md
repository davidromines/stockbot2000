# Addendum E, revision 2 — Knowledge Strategy Factory

**Entered 2026-09-27 by the owner** ("record for now"). Recorded, not built.

The specification below is the owner's text, verbatim. The only edits are
markdown heading markers on section titles and list markers; no wording is
changed.

**Naming.** As with revision 1 (`ADDENDUM_E_KNOWLEDGE_FACTORY.md`), the text
titles itself "Stage N", but Stage N is Addendum D. This is **Stage O**, and
its implementation steps N1–N12 (§26) map onto O1–O13 — see
`ROADMAP_INTEGRATION.md`, Stage O, "Revision 2". Where this revision and
revision 1 differ, revision 2 is the later statement of the owner's intent.

---

The owner's specification, verbatim:

# Stockbot2000 — Stage N: Knowledge Strategy Factory

## Mission

Implement Stage N — Knowledge Strategy Factory into the existing Stockbot2000 system.
This is an implementation phase, not a planning exercise.
Do not create another proposal for how this could be built. Inspect the existing repository and implement the system directly using the architecture, strategy objects, backtesting engine, validation ladder, ranking engine, paper trading, live slot engine, risk engine, reporting, and research infrastructure that already exist.
The goal is to dramatically improve the quality of Stockbot2000's strategy population by using documented trading knowledge as a source of strategy hypotheses, rather than relying primarily on machine-generated/random evolutionary discovery.
Stockbot2000 should become a system that can learn from:

* Academic research
* Quantitative finance literature
* Trading books
* Published systematic strategies
* Practitioner research
* Open-source quantitative research
* Published factor research
* Known systematic trading methodologies
* Previously validated Stockbot strategies
* Machine-generated strategies
* Hybrid combinations of the above

Human-developed strategies become seed hypotheses, not automatically trusted strategies.
Every imported strategy must still pass the same evidence, realism, robustness, and forward-performance machinery already used by Stockbot2000.

## 1. DO NOT BREAK THE EXISTING TRADING SYSTEM

The current Stockbot2000 live system is operational.
Do NOT:

* Replace the existing backtester.
* Create a second strategy engine.
* Replace the existing ranking engine.
* Replace the existing execution engine.
* Restart the frozen evolutionary search.
* Remove the five-slot live architecture.
* Disable live trading merely because new research is being added.
* Replace existing risk controls.
* Bypass survivorship testing.
* Bypass transaction costs/slippage.
* Bypass paper trading.
* Bypass forward validation.
* Automatically promote imported strategies directly to live trading.

The Knowledge Factory must feed the existing strategy lifecycle.
The architecture should remain:

```text
KNOWLEDGE SOURCES
       ↓
KNOWLEDGE INGESTION
       ↓
STRATEGY EXTRACTION
       ↓
NORMALIZED STRATEGY OBJECT
       ↓
REPRODUCTION
       ↓
REALISM / COST / SURVIVORSHIP
       ↓
ROBUSTNESS
       ↓
PAPER
       ↓
FORWARD EVIDENCE
       ↓
ELIGIBILITY
       ↓
RANKING
       ↓
5 LIVE SLOTS
       ↓
ROBINHOOD EXECUTION
       ↓
LIVE PERFORMANCE
       ↓
FEEDBACK INTO RESEARCH
```

## 2. CORE PRINCIPLE

The system must distinguish between:
A. A documented trading hypothesis
Example:
"A 12-1 momentum strategy historically generated excess returns."
and:
B. A Stockbot2000 strategy
The system must convert the documented hypothesis into an executable, reproducible strategy object.
Then Stockbot2000 determines whether that strategy actually survives:

* Correct data
* Point-in-time constraints
* Survivorship controls
* Transaction costs
* Slippage
* Liquidity
* Realistic fills
* Parameter variation
* Different market periods
* Out-of-sample testing
* Holdout testing
* Paper trading
* Forward performance
* Live performance

The source's reputation must NOT substitute for evidence.
A famous strategy is still only a hypothesis until Stockbot2000 validates it.

## 3. STRATEGY KNOWLEDGE OBJECT

Implement or extend the existing strategy schema so every knowledge-derived strategy preserves its provenance.
Use the existing schema where possible rather than creating an incompatible parallel object.
Each strategy should be capable of storing:

```text
strategy_id

name
family
strategy_type

source_type

source_title
source_author
source_publication
source_url
source_date
source_page
source_section

original_claim

original_market
original_asset_class
original_frequency

original_entry
original_exit
original_holding_period
original_position_sizing
original_stop
original_take_profit
original_rebalance_frequency

required_data

machine_translatable

translation_confidence

implementation_notes

source_provenance

parent_strategy_id

parent_hypothesis_id

research_lineage_id

variant_of

generated_by

creation_timestamp
```

Also preserve:

```text
original_strategy_definition
stockbot_translation
translation_assumptions
ambiguities
missing_information
```

Do NOT silently invent missing rules.
If a source says:
"Buy stocks showing strong momentum."
but does not define the exact ranking window, universe, rebalance schedule, or portfolio construction method, record the ambiguity.
Do not pretend the source specified something it did not.
The implementation may create a clearly labeled Stockbot interpretation, but the original documented rule and the machine interpretation must remain separate.

## 4. SOURCE TYPES

Support at least:

```text
BOOK
ACADEMIC_PAPER
PRACTITIONER_RESEARCH
OPEN_SOURCE
PUBLISHED_SIGNAL
KNOWN_FACTOR
TRADING_SYSTEM
MACHINE_GENERATED
HYBRID
```

The system should be able to distinguish:
Original documented strategy
from:
Stockbot reproduction
from:
Stockbot variant
from:
Machine mutation
from:
Hybrid strategy
This distinction is critical for research attribution.

## 5. KNOWLEDGE LIBRARY

Build a persistent knowledge library.
The library should store the strategy hypothesis, not merely a document.
A single source may contain:

```text
Source
 ├── Strategy A
 ├── Strategy B
 ├── Strategy C
 ├── Factor D
 └── Variant E
```

Therefore the relationship must be:

```text
SOURCE
  ↓
HYPOTHESIS
  ↓
STRATEGY
  ↓
VARIANTS
  ↓
TESTS
  ↓
RESULTS
```

Do not assume one document equals one strategy.

## 6. RESEARCH ANCESTRY / LINEAGE

Implement explicit research lineage.
This is extremely important.
Hundreds of papers may ultimately derive from the same original momentum/value/reversal research.
Therefore Stockbot2000 must not falsely interpret:
500 papers supporting momentum
as:
500 independent discoveries.
Track:

```text
research_lineage_id

parent_hypothesis_id

parent_strategy_id

source_relationship

independent_source
```

Possible relationships:

```text
ORIGINAL
REPLICATION
EXTENSION
VARIANT
DERIVATIVE
COMBINATION
MUTATION
HYBRID
```

Example:

```text
Momentum Original
      ↓
Academic Replication
      ↓
12-1 Momentum Variant
      ↓
Sector Momentum Variant
      ↓
Risk-Adjusted Momentum
      ↓
Stockbot Hybrid
```

All descendants must retain ancestry.

## 7. SOURCE INDEPENDENCE

Implement the ability to distinguish:
Independent evidence
from:
Derivative evidence.
For example:

```text
Paper A
Paper B → cites A
Paper C → cites A and B
Paper D → uses same dataset/methodology
```

These should not automatically count as four independent confirmations.
Create metadata allowing the system to record:

```text
independence_status
source_parent
citation_relationship
dataset_overlap
methodology_overlap
```

Do not over-engineer this into a full academic citation graph if that would delay implementation.
The minimum useful implementation is enough to prevent obvious double-counting of related research.

## 8. MACHINE TRANSLATION

Build a translation layer:

```text
DOCUMENTED STRATEGY
        ↓
EXTRACTED RULES
        ↓
NORMALIZED STRATEGY
        ↓
EXECUTABLE STOCKBOT STRATEGY
```

The translator should identify:

* Universe
* Entry condition
* Exit condition
* Ranking
* Lookback
* Holding period
* Rebalance frequency
* Position sizing
* Long/short
* Stop
* Take profit
* Risk rules
* Required data
* Regime filters
* Liquidity requirements

If the source does not specify something, preserve the uncertainty.
Use explicit fields such as:

```text
unspecified
unknown
requires_interpretation
```

rather than fabricating precision.

## 9. REPRODUCTION FIRST

Every imported documented strategy should first receive an:
ORIGINAL REPRODUCTION
Attempt to reproduce the strategy as close as possible to the source.
Do NOT immediately optimize it.
Record:

```text
source_version
stockbot_version
data_version
implementation_version
reproduction_assumptions
```

Then test it through the existing realism pipeline.
Only after the reproduction exists should Stockbot generate variants.

## 10. CONTROLLED VARIANTS

For every viable imported strategy, allow controlled variants.
Examples:

```text
Momentum:
12-month → 9-month
12-month → 6-month
12-month → 3-month

Rebalance:
monthly
weekly
daily

Exit:
fixed holding
signal reversal
trailing stop
ATR stop

Universe:
large cap
mid cap
liquid stocks
sector neutral

Position sizing:
equal weight
volatility scaled
risk scaled
```

But do NOT create uncontrolled combinatorial explosions.
Every variant must have:

```text
parent_strategy_id
mutation_type
mutation_parameters
```

Track the number of tests performed.

## 11. MULTIPLE-TESTING CONTROL

This is mandatory.
The system already learned that massive historical search can produce apparent edges through multiple testing.
The Knowledge Factory must not recreate that problem under a different name.
For every source lineage maintain:

```text
hypothesis_count
variant_count
test_count
holdout_tests
successful_variants
failed_variants
selection_events
```

Do not hide failed variants.
Failed experiments are valuable research information.
A strategy that survives after 500 failed variants is different evidence from a strategy that worked on its first test.

## 12. EXISTING VALIDATION PIPELINE

Every knowledge-derived strategy must use the existing Stockbot pipeline.
At minimum:

```text
SOURCE
↓
STRATEGY OBJECT
↓
BACKTEST
↓
COSTS
↓
SLIPPAGE
↓
REALISTIC FILLS
↓
SURVIVORSHIP
↓
ROBUSTNESS
↓
HOLDOUT
↓
PAPER
↓
FORWARD
↓
ELIGIBILITY
↓
RANKING
↓
LIVE
```

Do not create shortcuts for famous strategies.
Do not allow:

```text
"Published strategy"
        ↓
"Trusted"
        ↓
"Live"
```

The source only determines the hypothesis.
Evidence determines promotion.

## 13. COST AND EXECUTION REALISM

Use the existing realistic execution framework.
Knowledge-derived strategies must be evaluated using the same:

* Transaction costs
* Slippage
* Next-open fills
* Gap-through-stop handling
* Liquidity floors
* Position sizing constraints
* Cash constraints
* Survivorship controls

already implemented by Stockbot2000.
Do not allow a published strategy to bypass these because the original paper used different assumptions.

## 14. SURVIVORSHIP

Use the existing survivorship framework.
Where applicable, evaluate:

```text
current universe
historically correct universe
dead companies
delistings
buyouts
bankruptcies
delisting outcomes
```

Continue using the existing synthetic-dead-company system where currently configured, but preserve provenance and clearly distinguish:

```text
real historical data
synthetic historical data
imputed data
stress-test data
```

Do not silently represent synthetic data as real historical prices.

## 15. STRATEGY FAMILY CLASSIFICATION

Classify imported strategies into families such as:

```text
MOMENTUM
TREND
MEAN_REVERSION
VALUE
QUALITY
LOW_VOLATILITY
SIZE
REVERSAL
EARNINGS_SURPRISE
ANALYST_REVISION
SEASONALITY
BREAKOUT
VOLATILITY
LIQUIDITY
PAIRS
RELATIVE_VALUE
FACTOR
REGIME
EVENT
FUNDAMENTAL
HYBRID
OTHER
```

Reuse existing family definitions if they already exist.
Do not create duplicate taxonomy systems.

## 16. KNOWLEDGE FACTORY INPUTS

Design the system so future knowledge sources can be added.
Potential inputs include:

Academic

* Published factor research
* Quantitative finance papers
* Replication studies
* Asset-pricing research

Books

* Systematic trading books
* Quantitative investing books
* Market-timing research
* Trend-following research
* Value/momentum research

Practitioner research

* Research reports
* Public systematic strategy descriptions
* Quant newsletters where methodology is explicit
* CTA/systematic strategy descriptions

Open source

* GitHub implementations
* QuantConnect strategies
* Backtrader strategies
* Zipline strategies
* Academic code repositories
* Public research notebooks

Existing Stockbot knowledge

* Previous successful strategies
* Previous failed strategies
* Machine-discovered strategies
* Hybrid strategies

## 17. DO NOT TRY TO INGEST MILLIONS OF BOOKS IMMEDIATELY

The architecture should support enormous knowledge volumes eventually.
But implementation should begin with a clean, machine-testable ingestion architecture.
Prioritize sources containing explicit, reproducible rules.
The objective is not:
"Download every trading book."
The objective is:
"Turn documented trading knowledge into structured, testable strategy hypotheses."

## 18. KNOWLEDGE FACTORY DASHBOARD / REPORTING

Extend the existing reporting system.
The daily/periodic research report should be capable of showing:

```text
Knowledge strategies imported
Strategies successfully translated
Strategies requiring interpretation
Original reproductions tested
Variants generated
Variants tested
Strategies rejected
Strategies entering paper
Strategies with forward evidence
Strategies eligible for ranking
Knowledge-derived strategies currently ranked
Knowledge-derived strategies currently live
```

Also report ancestry:

```text
Family
Source
Research lineage
Parent strategy
Variant
Current status
```

Do not create a second dashboard system if the existing reporting infrastructure can be extended.

## 19. COMPARE KNOWLEDGE VS MACHINE DISCOVERY

Add metadata allowing Stockbot2000 to eventually measure:

```text
SOURCE_TYPE
```

for every strategy.
For example:

```text
ACADEMIC
BOOK
PRACTITIONER
OPEN_SOURCE
MACHINE
HYBRID
```

This is for research analysis, not for automatically declaring one category superior.
Eventually the system should be able to answer questions such as:

* How many ideas came from each source?
* How many survived?
* How many reached paper?
* How many reached forward testing?
* How many reached live?
* How long did they survive?
* What was their realized P&L?
* How many variants were required?
* How much testing was required per survivor?

Do not create a source-category ranking or use source category alone as a promotion rule.

## 20. KNOWLEDGE + MACHINE DISCOVERY

The Knowledge Factory does NOT replace machine discovery.
Instead:

```text
HUMAN KNOWLEDGE
      ↓
SEED STRATEGIES
      ↓
CONTROLLED VARIANTS
      ↓
MACHINE MUTATIONS
      ↓
HYBRID STRATEGIES
```

At the same time:

```text
MACHINE DISCOVERY
      ↓
NOVEL STRATEGIES
      ↓
ROBUSTNESS
      ↓
PAPER
```

Both populations feed the same validation system.
The long-term goal is to determine whether:

```text
Human-derived
Machine-derived
Hybrid
```

strategies produce durable survivors.
Do not assume the answer beforehand.

## 21. IMPORTANT: DO NOT RESTART THE FROZEN EVOLUTIONARY SEARCH

The existing evolutionary search has already been frozen because of multiple-testing concerns.
Leave its historical results intact.
Do not restart another giant million-trial optimization simply because the Knowledge Factory has been added.
The Knowledge Factory should create a much more economically meaningful hypothesis population.
The system should prefer:

```text
documented hypothesis
+
controlled variation
+
strong validation
```

over:

```text
millions of random parameter combinations
```

## 22. DO NOT OVERFIT THE KNOWLEDGE FACTORY

A famous strategy that performs badly in Stockbot2000 is allowed to fail.
A famous strategy that performs exceptionally well is NOT automatically promoted.
A machine-generated strategy that performs exceptionally well is NOT automatically trusted either.
The system's job is to determine what survives realistic testing.

## 23. FUTURE PORTFOLIO INTELLIGENCE

Do NOT implement full portfolio optimization as part of this stage unless the existing architecture already requires a small compatibility change.
The current product remains:

```text
Five live strategy slots
approximately $20 each
```

However, make the strategy metadata sufficient for a future portfolio layer to understand:

```text
strategy family
factor exposure
asset exposure
correlation
volatility
drawdown
liquidity
market exposure
regime
```

Future architecture may eventually evolve from:

```text
FIVE BEST STRATEGIES
```

toward:

```text
BEST COMBINATION OF INDEPENDENT SIGNALS / STRATEGIES
```

Do not implement that redesign now.

## 24. LIVE TRADING SAFETY

Knowledge Factory changes must never bypass:

* Global kill switch
* Strategy kill switch
* Stop-loss engine
* Position reconciliation
* Duplicate-order protection
* Settled-cash enforcement
* Live order sizing
* Live sell sizing
* Restart reconciliation
* Five-minute monitoring
* Existing slot replacement logic

A newly discovered strategy cannot directly place a live order.
It must first become eligible through the existing lifecycle.

## 25. RESEARCH LOOP

Implement the persistent loop:

```text
DISCOVER
   ↓
INGEST
   ↓
NORMALIZE
   ↓
REPRODUCE
   ↓
TEST
   ↓
VARIATE
   ↓
ROBUSTNESS
   ↓
PAPER
   ↓
FORWARD
   ↓
PROMOTE / REJECT
   ↓
LIVE
   ↓
MONITOR
   ↓
LEARN
   ↓
NEW HYPOTHESES
```

Research must continue while the live system trades.
Do not make live trading and research mutually exclusive.

## 26. IMPLEMENTATION PRIORITY

Implement in this order:

N1 — Schema
Extend the existing strategy object with source/provenance/lineage fields.

N2 — Knowledge Library
Create persistent storage for sources, hypotheses, and extracted strategies.

N3 — Strategy Extraction
Create the ingestion/normalization interface.

N4 — Reproduction Engine
Connect extracted strategies to the existing backtester.

N5 — Variant Generator
Create controlled, provenance-preserving variants.

N6 — Lineage
Implement parent/child strategy ancestry and research lineage.

N7 — Multiple Testing Tracking
Track tests, variants, selection, holdout usage and failed experiments.

N8 — Validation Integration
Connect all knowledge strategies to the existing promotion ladder.

N9 — Reporting
Add Knowledge Factory statistics to the existing reports.

N10 — Existing Strategy Import
Import a useful initial seed population using strategies already present in the repository and any existing research-library data.

N11 — Automated Research Loop
Make the Knowledge Factory capable of continuously processing new strategy hypotheses without manual intervention.

N12 — Testing
Add unit, integration, lineage, provenance and end-to-end tests.

## 27. INITIAL STRATEGY FAMILIES

Use existing implementations wherever available.
Where additional seed strategies are needed, prioritize well-documented families:

1. Momentum
2. Trend following
3. Mean reversion
4. Value
5. Quality
6. Low volatility
7. Size
8. Reversal
9. Earnings surprise
10. Analyst revisions
11. Seasonality
12. Breakouts
13. Volatility
14. Liquidity
15. Relative value
16. Factor strategies
17. Regime strategies
18. Fundamental strategies
19. Event-driven strategies
20. Hybrid strategies

Do not optimize these families merely because they are listed.
They are an initial research universe.

## 28. ACCEPTANCE CRITERIA

Stage N is complete when:

Architecture

* Knowledge Factory exists.
* Existing strategy system remains authoritative.
* Existing backtester remains authoritative.
* Existing promotion ladder remains authoritative.
* Existing execution/risk system remains authoritative.

Provenance
Every knowledge strategy has:

* Source
* Strategy identity
* Family
* Parent/lineage where applicable
* Original definition
* Stockbot interpretation
* Variant ancestry

Testing
Every knowledge-derived strategy can flow through:

```text
Backtest
→ realism
→ robustness
→ paper
→ forward
→ eligibility
→ ranking
```

Research integrity
The system tracks:

* Number of variants
* Number of tests
* Failed tests
* Holdout usage
* Parent strategy
* Research lineage

Live safety
No imported strategy can bypass the existing live safeguards.

Reporting
The system reports the Knowledge Factory's activity and status.

Automation
The factory can continue processing hypotheses without requiring manual approval for every strategy.

## 29. OPERATING RULE

You are now in implementation mode.
Do not spend the majority of the task writing a plan.
Do not ask me whether I want each component.
Do not stop after creating schemas.
Do not stop after creating a database.
Do not stop after creating an ingestion interface.
Continue through the entire implementation sequence.
Reuse existing infrastructure aggressively.
If an existing module already performs the required function, extend it instead of creating a duplicate.
If an architectural decision is necessary and the choice is obvious from the existing codebase, make the decision and continue.
If a research question remains unresolved, implement the infrastructure so it can be resolved later.
Only stop if a genuine external dependency makes implementation impossible.

## 30. FINAL DELIVERABLE

At the end, report:

```text
STAGE N STATUS

Implemented:
- ...

Modified:
- ...

New modules:
- ...

Database/schema changes:
- ...

Strategy objects added:
- ...

Knowledge sources supported:
- ...

Lineage support:
- ...

Multiple-testing controls:
- ...

Validation integration:
- ...

Reporting:
- ...

Tests:
- ...

Test results:
- ...

Known limitations:
- ...

External dependencies:
- ...

Next executable step:
- ...
```

Most importantly:
Build the Knowledge Strategy Factory into Stockbot2000.
Do not build another research prototype.
Do not build another dashboard.
Do not create a disconnected strategy database.
Build the actual subsystem that turns existing trading knowledge into testable Stockbot strategies and feeds those strategies into the same evidence-based pipeline that ultimately controls the five live trading slots.
