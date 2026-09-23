# PROJECT_STATUS

Updated 2026-09-23.

Stockbot2000 is a quantitative research system: it ingests prices and
point-in-time fundamentals, generates and evaluates trading strategies, tracks
them through a versioned league, and produces orders that a human places by
hand. It has never transmitted an order itself. Its defining property is that
every apparent edge it has found so far turned out to be a measurement
artifact, so this page states what the system currently reports and, at least
as prominently, what it has NOT established.

## What is built

| Phase | Built |
|---|---|
| 6 — Research integrity | Regression suite (34 test files), ancestry, search freeze, truth sets, point-in-time universe, freshness gating, validation firewall, sealed holdout, experiment registry, random control, multiple-testing accounting, research integrity report |
| 7 — Strategy league | Strategy identity, immutable versioning, 10-state lifecycle, 21 migrated funds, scoreboard, degradation tracking, correlation, eligibility |
| 8 — Research library | 35 entries, governed generation |
| 9 — Fundamental value | Point-in-time filing provenance, industry classification, statement engine, valuation engine, intrinsic value, value score, Value Fund |
| 10 — Promotion | Promotion policy, capital allocation, roster management, live pipeline |
| 11 — Operations | Stop conditions, compute priority, the daily research loop |

## What the system says today

| Measure | Current reading |
|---|---|
| Search | DO NOT SEARCH, COLLECT MORE FORWARD DATA — 1,049,967 cumulative trials against a 1,000,000 threshold; universe coverage unmeasurable at the search window start |
| Promotion readiness | NOT READY — 4 of 15 prerequisites VERIFIED |
| Eligible strategies | 0 of 21 |
| Rankable strategies | 0 of 21 — median 7 equity marks against a floor of 60 |
| Measurable correlation pairs | 0 of 210 |
| Live slate | NO ORDERS |
| Research library | 0 of 35 entries SUPPORTED |
| Random control | 0 of 325 random strategies cleared the validation gate; the best made $10,980 with a Sharpe of 1.14 |

## What has NOT been established

- No strategy has demonstrated an edge.
- The classifier is gross NEGATIVE under next-open fills: -0.279% per trade
  over 1,053 trades.
- ETF switching loses to buy-and-hold on every pair tested.
- 0 of 20 published rules cleared the promotion gate.
- Survivorship bias: 22.6% of the knowable 2008 universe is priceable here,
  rising to 83.7% by 2024.
- Debt is tagged for only 38% of filers, so EV multiples cover a minority of
  the universe, and that minority is 2.5x larger by median market cap.

## Real money

One account, roughly $89. It is traded by a human placing orders the system
generates. No module transmits an order.
