# Addendum E — Knowledge Strategy Factory

**Entered 2026-09-25 by the owner** ("add this to the roadmap").

The specification below is the owner's text, verbatim. The only edit is
markdown heading markers on the section titles; no wording is changed.

**Naming.** The text titles itself "Stage N", but Stage N is already
Addendum D (Live Growth & Continuous Improvement, entered earlier the same
day). In the roadmap this addendum is **Stage O**, and its implementation
steps N1–N13 (§25) are tracked as **O1–O13**, one to one. Integration — what
each item maps to in the existing system, and what is missing — is in
`ROADMAP_INTEGRATION.md`, Stage O.

---

The owner's specification, verbatim:

# Stockbot2000 — Stage N: Knowledge Strategy Factory

## Mission

Stockbot2000 already has a machine-discovery engine capable of generating trading strategies.
That should NOT be our only source of ideas.
There is an enormous existing body of documented trading knowledge in:

* trading books
* academic papers
* quantitative finance research
* practitioner research
* systematic-trading literature
* published factor research
* documented hedge-fund/CTA methodologies
* open-source quantitative research
* published trading systems
* previously replicated strategies
* known technical and fundamental signals

We should use this knowledge as a starting hypothesis library.
The objective of this phase is to build a Knowledge Strategy Factory that systematically converts documented trading ideas into machine-testable Stockbot2000 strategy objects and feeds them into the existing Stockbot2000 discovery → backtest → robustness → paper → forward → eligibility → ranking → live-slot pipeline.
Do NOT create a separate competing trading system.
Build this as another strategy-generation source feeding the existing system.

## 1. CHANGE THE STRATEGY-DISCOVERY MODEL

Stockbot2000 should have two major sources of strategy ideas:

```text
                    STOCKBOT2000
                         │
              ┌──────────┴──────────┐
              │                     │
       KNOWLEDGE FACTORY      MACHINE DISCOVERY
              │                     │
      Human-documented         Evolutionary /
      trading ideas            combinatorial /
              │                machine-generated
              │                     │
              └──────────┬──────────┘
                         │
                  STRATEGY FACTORY
                         │
                  NORMALIZE RULES
                         │
                  BACKTEST ENGINE
                         │
                 ROBUSTNESS TEST
                         │
                  PAPER FORWARD
                         │
                  LIVE ELIGIBILITY
                         │
                     RANKING
                         │
                   FIVE SLOTS

```

The knowledge library supplies hypotheses.
It does NOT supply guaranteed profitable strategies.
Every imported strategy must compete under the same objective testing framework as machine-generated strategies.

## 2. BUILD A KNOWLEDGE STRATEGY LIBRARY

Create a persistent database/library of documented trading ideas.
Each strategy/hypothesis should have structured metadata.
Minimum schema:

```text
strategy_id
strategy_name
strategy_family
source_type
source_title
source_author
source_publication
source_url
source_date
source_page_or_section
original_claim
original_market
original_asset_class
original_time_period
original_frequency
long_short
entry_rules
exit_rules
position_sizing
stop_loss
take_profit
holding_period
rebalance_frequency
required_data
required_indicators
fundamental_inputs
technical_inputs
volatility_inputs
regime_inputs
source_confidence
machine_translatable
translation_notes
provenance

```

The strategy object should retain the original source information.
Never lose the connection between a machine-tested strategy and the source idea from which it originated.

## 3. SOURCE TYPES

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

A strategy created by combining multiple published ideas should be marked:

```text
HYBRID

```

and maintain links to every parent strategy.

## 4. DO NOT ASSUME DOCUMENTED STRATEGIES ARE VALID

This is critical.
A book or paper saying:
"This strategy works"
does NOT mean Stockbot2000 should believe it.
Treat every imported idea as:

```text
HYPOTHESIS

```

The source provides provenance and an initial hypothesis.
Stockbot2000 provides the actual validation.
The strategy must still pass:

* point-in-time data controls
* realistic execution
* transaction costs
* slippage
* liquidity rules
* survivorship controls
* out-of-sample testing
* robustness testing
* paper trading
* forward evidence
* existing eligibility rules

Do not promote an imported strategy merely because the original author reported a strong result.

## 5. START WITH MACHINE-TESTABLE SOURCES

Do not begin by trying to ingest millions of books as unstructured text.
Start with sources where strategies can be extracted into explicit rules.
Prioritize:
Tier 1

* quantitative academic papers
* published factor definitions
* systematic trading research
* existing machine-readable strategy repositories
* published signal libraries
* open-source quantitative strategy implementations

Tier 2

* trading books with explicit rules
* practitioner articles
* documented trading systems

Tier 3

* vague discretionary concepts

For Tier 3, do NOT invent arbitrary rules and pretend they came from the source.
Instead mark them:

```text
NON_MACHINE_TESTABLE

```

and preserve the idea for future interpretation.

## 6. USE EXISTING STRATEGY RESEARCH AS AN INITIAL SEED SET

Search for existing collections of documented systematic strategies and research.
One particularly useful starting point is the systematic-trading research ecosystem containing thousands of documented/replicated strategies.
Use available open-source repositories, published research indexes, academic papers, and quantitative strategy collections as seed sources.
Do not manually enter strategies one by one if structured or machine-readable versions already exist.
Build an ingestion/import process.
The goal is to rapidly create a large initial hypothesis population.

## 7. STRATEGY TRANSLATION ENGINE

Build a translator that converts documented strategy descriptions into the Stockbot2000 strategy schema.
For example:

```text
SOURCE IDEA:

Buy stocks with strong 12-month momentum.
Exclude the most recent month.
Hold for one month.

```

becomes:

```text
UNIVERSE:
eligible common stocks

SIGNAL:
12-month return excluding most recent month

RANK:
descending momentum

ENTRY:
top X percentile

HOLD:
1 month

REBALANCE:
monthly

```

The translation must preserve:

* original rule
* translated rule
* assumptions
* ambiguities

If the source does not specify something important, do NOT silently invent it.
Record:

```text
ASSUMPTION_REQUIRED

```

and either:

1. use a clearly defined Stockbot default, or
2. generate multiple explicit interpretations.

## 8. AMBIGUITY HANDLING

Trading literature frequently contains statements like:
"Buy strong stocks."
That is not a machine-testable strategy.
Do not arbitrarily turn that into one implementation.
Instead create explicit interpretations where reasonable:

```text
Momentum = 3 month
Momentum = 6 month
Momentum = 12 month
Momentum = 12-1 month

```

But clearly label these as:

```text
SOURCE_DERIVED_VARIANT

```

rather than claiming the author explicitly specified them.
This distinction must remain in the provenance system.

## 9. STRATEGY GENOME

Extend the existing strategy object into a standardized Strategy Genome.
A genome should encode:

```text
UNIVERSE
SIGNALS
ENTRY
EXIT
HOLDING_PERIOD
POSITION_SIZE
STOP
TAKE_PROFIT
REBALANCE
REGIME
RISK
DATA_REQUIREMENTS

```

This allows Stockbot2000 to compare strategies that came from completely different sources.
Example:

```text
Published Strategy A
        +
Published Strategy B
        ↓
HYBRID STRATEGY
        ↓
Strategy Genome
        ↓
Stockbot testing pipeline

```

## 10. DO NOT JUST TEST EXACT COPIES

For every sufficiently explicit strategy, create three categories:
A. Original
Test the strategy as faithfully as possible to the source.

```text
SOURCE_REPRODUCTION

```

B. Controlled variants
Test limited, explicitly documented variations.
Examples:

* different holding periods
* reasonable parameter ranges
* alternative exits
* volatility filters
* position sizing variants
* stop variants

These must remain linked to the original.
C. Mutations
Allow the existing Stockbot evolutionary/discovery engine to mutate promising concepts.
Example:

```text
12-1 Momentum
       ↓
Momentum + volatility filter
       ↓
Momentum + volatility + regime filter
       ↓
Momentum + earnings surprise

```

This creates a progression:

```text
HUMAN IDEA
    ↓
REPRODUCTION
    ↓
CONTROLLED VARIANTS
    ↓
MACHINE MUTATIONS

```

## 11. PREVENT DATA MINING

This is one of the most important parts of this phase.
The system must distinguish:

```text
ORIGINAL HYPOTHESIS

```

from:

```text
OPTIMIZED VARIANT

```

Do not allow the same historical data to be repeatedly mined until the best-looking version is found and then report it as if the original idea worked.
Track:

* number of variants tested
* parameters tested
* datasets tested
* holdout usage
* research iterations
* source strategy
* parent strategy
* mutation history

The more a strategy is optimized against historical data, the more skepticism should be applied to its historical performance.

## 12. MULTIPLE-TESTING CONTROLS

Stockbot2000 already discovered that large evolutionary searches can produce misleading apparent winners.
Do NOT bypass the existing frozen-search policy.
The Knowledge Factory should inherit the same protections.
Track:

```text
source hypothesis
number of variants
number of descendants
number of tests
selection events
holdout usage

```

A strategy that wins after 50,000 related tests should not be treated the same as an untouched published hypothesis that survives independently.

## 13. SOURCE-LEVEL PERFORMANCE TRACKING

This is an important new capability.
Stockbot2000 should eventually be able to answer:
Where do our successful strategies actually come from?
Track strategy outcomes by:

```text
BOOK
PAPER
FACTOR
PRACTITIONER
OPEN SOURCE
MACHINE GENERATED
HYBRID

```

Measure:

* candidates generated
* backtest admissions
* robustness passes
* paper admissions
* forward passes
* live promotions
* live trades
* live P&L
* drawdown
* longevity
* failure rate

Do not rank the source categories in the UI as "best."
This is research metadata, not a recommendation.

## 14. PUBLISHED STRATEGY VS MACHINE STRATEGY

Every strategy should have:

```text
GENERATION_METHOD

```

Examples:

```text
PUBLISHED_REPRODUCTION
PUBLISHED_VARIANT
PUBLISHED_HYBRID
MACHINE_GENERATED
MACHINE_MUTATION
HUMAN_DEFINED

```

This allows Stockbot2000 to learn whether its own discovery engine is actually adding value beyond existing knowledge.

## 15. KNOWLEDGE GRAPH / PARENTAGE

Where practical, maintain relationships:

```text
Strategy A
   │
   ├── Variant A1
   ├── Variant A2
   └── Hybrid A+B
             │
             ├── Mutation A+B+Volatility
             └── Mutation A+B+Regime

```

Every descendant should retain its ancestry.
Never create an orphan strategy whose origin is unknown.

## 16. PRIORITIZATION

Do not attempt to ingest everything simultaneously.
Prioritize strategies with:

1. explicit rules
2. accessible historical inputs
3. reproducible methodology
4. sufficient historical sample
5. realistic implementation
6. clear provenance
7. applicability to our available market data

Start with high-quality systematic strategies and research.
Then expand.

## 17. INTEGRATE WITH EXISTING STOCKBOT PIPELINE

This is critical.
Do NOT create a second promotion system.
Imported strategies must enter the existing pipeline:

```text
KNOWLEDGE SOURCE
       ↓
INGEST
       ↓
NORMALIZE
       ↓
STRATEGY OBJECT
       ↓
BACKTEST
       ↓
REALISM
       ↓
ROBUSTNESS
       ↓
PAPER
       ↓
FORWARD
       ↓
ELIGIBILITY
       ↓
RANKING
       ↓
LIVE SLOT

```

The existing five-slot live engine remains authoritative.
The Knowledge Factory only increases the supply and diversity of candidates.

## 18. USE THE EXISTING COST / SURVIVORSHIP / REALISM SYSTEM

Every imported strategy must use the same:

* realistic fills
* next-open logic
* transaction costs
* slippage
* liquidity floors
* stop-gap handling
* survivorship controls
* point-in-time fundamentals
* existing accounting

Do not create a simplified backtester for literature strategies.
That would make comparisons meaningless.

## 19. SOURCE CLAIM VS STOCKBOT RESULT

The dashboard and reports should clearly separate:

```text
ORIGINAL SOURCE CLAIM

```

from:

```text
STOCKBOT REPLICATION RESULT

```

Example:

```text
SOURCE:
Author X
Published 1998

CLAIM:
Strategy produced X% annualized return.

STOCKBOT REPLICATION:
1998–2010
Net return: X%
Max drawdown: X%
Trades: X

OUT-OF-SAMPLE:
X%

PAPER:
X trades

LIVE:
X trades
P&L: $X

```

Never merge the two.

## 20. KNOWLEDGE FACTORY DASHBOARD

Add a section to the existing control center:
KNOWLEDGE FACTORY
Display:

```text
Sources
Strategies imported
Strategies successfully translated
Non-machine-testable ideas
Original reproductions
Controlled variants
Machine mutations
Currently testing
Backtest survivors
Robustness survivors
Paper candidates
Forward candidates
Live candidates

```

Also show:

```text
Recent imports
Recent strategy discoveries
Recent source reproductions
Recent failures

```

## 21. STARTING LIBRARY

Build an initial library around major systematic strategy families.
At minimum investigate:

```text
MOMENTUM
TREND FOLLOWING
MEAN REVERSION
VALUE
QUALITY
LOW VOLATILITY
SIZE
REVERSAL
EARNINGS SURPRISE
ANALYST REVISION
SEASONALITY
BREAKOUT
VOLATILITY
LIQUIDITY
PAIRS / RELATIVE VALUE
FACTOR COMBINATIONS
REGIME STRATEGIES

```

Do not assume any of these are profitable today.
They are simply research starting points.

## 22. KEEP MACHINE DISCOVERY

Do NOT replace the existing random/evolutionary discovery system.
Instead:

```text
KNOWLEDGE
+
MACHINE DISCOVERY

```

should compete in the same arena.
This gives Stockbot2000 the ability to discover whether:

* known ideas work
* known ideas can be improved
* combinations work
* machine-generated ideas work
* hybrid ideas work
* certain ideas only work in certain regimes
* published ideas have decayed
* apparently successful published ideas fail under realistic testing

## 23. FUTURE CAPABILITY: KNOWLEDGE → MUTATION

Eventually allow Stockbot to automatically take successful concepts and create related hypotheses.
For example:

```text
Published Momentum
       ↓
Momentum + volatility
       ↓
Momentum + market regime
       ↓
Momentum + fundamentals
       ↓
Momentum + volatility + regime

```

But maintain complete ancestry.
This turns the literature into a starting genetic population for the existing evolutionary system.

## 24. DO NOT LET THIS BLOCK LIVE TRADING

Stockbot2000 is already LIVE.
Do not shut down the live system to build this.
The Knowledge Factory is a research subsystem.
Build it alongside:

* live trading
* monitoring
* strategy ranking
* replacement
* K
* L
* M

The live five-slot engine remains operational.

## 25. IMPLEMENTATION ORDER

Build this sequentially:
N1 — Strategy knowledge schema
Create the database/model for source strategies and provenance.
N2 — Source ingestion
Create import infrastructure.
N3 — Strategy normalization
Convert documented ideas into Stockbot strategy objects.
N4 — Translation/ambiguity system
Handle incomplete or ambiguous descriptions without fabricating source claims.
N5 — Strategy genome
Connect imported strategies to the existing strategy object model.
N6 — Reproduction engine
Run faithful implementations of documented strategies.
N7 — Controlled variant engine
Generate bounded variants while preserving parentage.
N8 — Provenance / multiple-testing controls
Track research history and selection bias.
N9 — Knowledge dashboard
Expose the library and pipeline.
N10 — Initial seed library
Import a substantial initial population of machine-testable strategies.
N11 — Existing pipeline integration
Send all candidates through the existing Stockbot pipeline.
N12 — Hybrid/mutation engine
Allow successful documented concepts to feed machine discovery.
N13 — Continuous ingestion
Allow new research and strategies to be added without redesigning the system.

## 26. IMPORTANT IMPLEMENTATION RULES

This is an implementation phase.
Do not stop and ask me whether the concept is worthwhile.
It is worthwhile.
Build it.
Do not create another giant planning document instead of implementing it.
Do not redesign the existing live trading system.
Do not restart the frozen evolutionary search.
Do not replace the existing ranking/promotion architecture.
Do not create a second backtester.
Reuse the existing infrastructure wherever possible.
If an external data source requires credentials, build the interface and continue implementing everything that does not require credentials.
If a source cannot be reliably translated into machine-testable rules, record it as non-machine-testable rather than inventing rules.
If a strategy is unprofitable, that is a valid result. Keep the research record.
The goal is not to make every documented strategy profitable.
The goal is to create a massive, diverse, provenance-aware hypothesis population and let Stockbot2000 determine what survives.

## 27. DEFINITION OF DONE

This phase is complete when:

1. Stockbot2000 has a persistent Knowledge Strategy Library.
2. Strategies retain complete source provenance.
3. Published ideas can be converted into Stockbot strategy objects.
4. Original reproductions are distinguishable from variants.
5. Variants retain parentage.
6. Machine-generated strategies retain their own generation metadata.
7. Hybrid strategies retain all parent strategies.
8. Multiple-testing history is tracked.
9. Imported strategies use the existing realistic backtester.
10. Imported strategies use existing survivorship controls.
11. Imported strategies use existing cost/slippage models.
12. Imported strategies enter the existing promotion pipeline.
13. The existing five-slot live system remains unchanged as the final allocator.
14. Knowledge-derived and machine-generated strategies compete under the same eligibility/ranking framework.
15. The dashboard shows where strategies came from.
16. The system can continuously add new documented strategies.
17. Promising documented strategies can become inputs to machine mutation.
18. Live trading continues while all of this is being built.

## 28. FINAL OBJECTIVE

The long-term Stockbot2000 strategy engine should look like this:

```text
             EXISTING HUMAN KNOWLEDGE
                       │
        ┌──────────────┼──────────────┐
        │              │              │
      BOOKS          PAPERS       RESEARCH
        │              │              │
        └──────────────┼──────────────┘
                       ↓
                KNOWLEDGE FACTORY
                       │
                       ↓
               STRATEGY GENOMES
                       │
                       ↓
              CONTROLLED VARIANTS
                       │
                       ↓
                 MACHINE MUTATION
                       │
                       ├───────────────┐
                       │               │
                 MACHINE DISCOVERY     │
                       │               │
                       └───────┬───────┘
                               ↓
                         STOCKBOT ARENA
                               ↓
                         BACKTEST
                               ↓
                       ROBUSTNESS TEST
                               ↓
                         PAPER TEST
                               ↓
                       FORWARD EVIDENCE
                               ↓
                          ELIGIBILITY
                               ↓
                            RANKING
                               ↓
                       FIVE LIVE SLOTS
                               ↓
                         REAL TRADING
                               ↓
                       LIVE PERFORMANCE
                               ↓
                    FEEDBACK INTO RESEARCH
                               ↓
                              LOOP

```

This is the objective:
Stockbot2000 should not rely solely on random invention to discover trading strategies. It should systematically ingest the world's documented trading knowledge, reproduce it, test it under Stockbot's realistic conditions, mutate promising concepts, combine them with machine-generated ideas, and continuously allow the evidence to determine which strategies advance toward live trading.
Build this now and integrate it into the existing Stockbot2000 system.
