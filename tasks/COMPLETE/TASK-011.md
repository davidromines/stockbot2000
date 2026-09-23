# TASK-011

- component: docs
- priority: normal
- state: COMPLETE
- branch: ado/task-011
- created: 2026-09-23T05:56:06+00:00
- dependencies: none

## Objective
Create PROJECT_STATUS.md fresh: a single-page status of what is built, what it reports, and what it has NOT established. Phase 6 section 29.

## Background
Phase 6 section 29 asks for documentation to be updated. `PROJECT_STATUS.md`
exists but predates Phases 6 to 11, which are now all built.

The document's job is to let someone — a reviewer, or this project six months
from now — see in one page what exists, what it currently says, and above all
what it has NOT established. This project's defining characteristic is that
every apparent edge so far turned out to be a measurement artifact, and a
status page that lists capabilities without that context misleads by omission.

The facts below are measured, not estimated. Use them exactly.

**Built, Phases 6-11:**
- Phase 6: regression suite (34 test files), ancestry, search freeze, truth
  sets, point-in-time universe, freshness gating, validation firewall, sealed
  holdout, experiment registry, random control, multiple-testing accounting,
  research integrity report
- Phase 7: strategy league (identity, immutable versioning, 10-state
  lifecycle), 21 migrated funds, scoreboard, degradation tracking,
  correlation, eligibility
- Phase 8: research library (35 entries), governed generation
- Phase 9: point-in-time filing provenance, industry classification, statement
  engine, valuation engine, intrinsic value, value score, Value Fund
- Phase 10: promotion policy, capital allocation, roster management, live
  pipeline
- Phase 11: stop conditions, compute priority, the daily research loop

**What the system reports today:**
- search: DO NOT SEARCH, COLLECT MORE FORWARD DATA (1,049,967 cumulative
  trials against a 1,000,000 threshold; universe coverage unmeasurable at the
  search window start)
- promotion readiness: NOT READY, 4 of 15 prerequisites VERIFIED
- eligible strategies: 0 of 21
- rankable strategies: 0 of 21 (median 7 equity marks against a floor of 60)
- measurable correlation pairs: 0 of 210
- live slate: NO ORDERS
- research library: 0 of 35 entries SUPPORTED
- random control: 0 of 325 random strategies cleared the validation gate; the
  best made $10,980 with a Sharpe of 1.14

**What has NOT been established:**
- no strategy has demonstrated an edge
- the classifier is gross NEGATIVE under next-open fills (-0.279% per trade
  over 1,053 trades)
- ETF switching loses to buy-and-hold on every pair tested
- 0 of 20 published rules cleared the promotion gate
- survivorship bias: 22.6% of the knowable 2008 universe is priceable here,
  rising to 83.7% by 2024
- debt is tagged for only 38% of filers, so EV multiples cover a minority of
  the universe and that minority is 2.5x larger by median market cap

**Real money:** one account, ~$89, traded by a human placing orders the system
generates. No module transmits an order.

## Relevant files
- `PROJECT_STATUS.md`
## Requirements
1. Rewrite `PROJECT_STATUS.md` completely. Do not preserve its current
2. Open with a single paragraph stating what the system is and, plainly, that
3. Include a "What is built" section organised by phase, using the list above.
4. Include a "What the system says today" section as a two-column table, using
5. Include a "What has NOT been established" section using the list above.
6. Include a "Real money" section stating the account size and that no module
7. State the date as 2026-09-23.
8. Keep the whole document under 200 lines. It is a status page, not a manual.
9. Use GitHub-flavoured markdown. Tables where figures are compared.
10. Do not invent any figure. Every number must come from the Background

## Constraints
1. Modify ONLY `PROJECT_STATUS.md`.
2. Do not add a "next steps" or "roadmap" section — `docs/ROADMAP_INTEGRATION.md
3. Do not use marketing language. No "powerful", "robust", "comprehensive".
4. Do not claim any capability is proven or validated.

## Acceptance criteria
1. PROJECT_STATUS.md` exists, is under 200 lines, and contains the headings
2. The file contains the strings "DO NOT SEARCH", "NOT READY", "0 of 21" and
3. The file contains no "next steps" or "roadmap" heading.
4. ./run_tests.sh` reports ALL PASS with 34 files.
5. git status --short` shows exactly one modified file.
