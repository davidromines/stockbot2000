# TASK-012

- component: docs
- priority: normal
- state: COMPLETE
- branch: ado/task-012
- created: 2026-09-23T05:58:44+00:00
- dependencies: none

## Objective
Create ARCHITECTURE.md: how the modules fit together, organised by the path data takes from ingestion to an order slate. Phase 6 section 29.

## Background
Phase 6 section 29 asks for ARCHITECTURE.md. It does not exist. CLAUDE.md
lists modules in tables grouped by purpose, which answers "what is this file"
but not "what happens to a price bar between arriving and becoming an order".

The document's job is the second question. Someone should be able to read it
and know where to look when a number is wrong.

**The pipeline, in order.** Each arrow is a real dependency:

    universe.py --record        symbol directory, stamps delistings
      -> backfill.py --top-up   price bars
      -> build_features.py      20 indicators
      -> fundamental_features.py  filings lagged to availability
      -> freshness.py           FAILS the run if any of the above is stale
      -> paper_trading.py       the 16 paper funds step one day
      -> pair_funds.py          the 5 ETF switching funds
      -> value_fund.py          the Value Fund marks to market
      -> daily_picks.py         the daily book
      -> orders.py              the morning slate a human places
      -> [human places orders]
      -> orders.py --record-fills   reconciliation

**The research layer**, which reads the same tables but never writes to the
forward record:

    league.py         identity, immutable versioning, 10-state lifecycle
    scoreboard.py     ranks — and refuses to, below 60 equity marks
    degradation.py    backtest vs forward, per trade
    eligibility.py    correlation and the top-five-eligible rule
    promotion_policy.py  readiness AND eligibility, both required
    allocation.py     dollars per roster slot
    roster.py         who joins, who leaves
    live_pipeline.py  stops at order validation; never transmits

**The data layer:**

    storage.py        owns market_data.db; the only module writing SQL to it
    statements.py     the three financial statements, point-in-time
    valuation.py      multiples, industry-aware
    intrinsic.py      DCF and four other methods, with mandatory sensitivity
    value_score.py    nine dimensions, ranked within industry
    pit_facts.py      "what was knowable on this date"

**Three boundaries that are enforced in code, not convention:**

1. Nothing in the research layer imports `broker` or `execution`. The league
   must not be able to place an order.
2. `storage.py` is the only module that writes SQL to `market_data.db`.
3. The forward record tables (`paper_runs`, `paper_equity`, `paper_trades`,
   `pair_funds`, `value_fund_*`) are written only by their own stepper. The
   league migration reads them and never writes.

**Two stores:** `data/market_data.db` (~9 GB, everything) and
`data/positions.db` (the trade ledger, deliberately separate).

## Relevant files
- `ARCHITECTURE.md`
## Requirements
1. Create `ARCHITECTURE.md`.
2. Open with one paragraph: what the system does, end to end, in plain terms.
3. A "Daily pipeline" section showing the ordered chain above, with one line
4. A "Research layer" section listing those modules and what each decides.
5. A "Data layer" section listing those modules.
6. A "Boundaries" section stating the three enforced boundaries above, and
7. A "Storage" section naming the two databases and why they are separate.
8. A short "Where to look when a number is wrong" section mapping symptoms to
9. > statements.py and pit_facts.py; a suspect ranking -> scoreboard.py and
10. Under 250 lines.
11. Do not invent a module. Every file named must come from the Background

## Constraints
1. Create ONLY `ARCHITECTURE.md`.
2. Do not duplicate CLAUDE.md's module tables — this document is about flow
3. No marketing language.
4. Do not describe anything as validated or proven.

## Acceptance criteria
1. ARCHITECTURE.md` exists, is under 250 lines, and contains the headings
2. It contains at least one fenced code block showing the pipeline order.
3. ./run_tests.sh` reports ALL PASS with 34 files.
4. git status --short` shows exactly one added file.
