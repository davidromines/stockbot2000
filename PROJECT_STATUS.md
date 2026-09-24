# PROJECT_STATUS

Updated 2026-09-24.

Stockbot2000 is a quantitative research system: it ingests prices and
point-in-time fundamentals, generates and evaluates trading strategies, tracks
them through a versioned league, and since 2026-09-24 15:39 UTC trades five
$20 slots in the Robinhood Agentic account automatically (LIVE, armed by the
owner). Its defining property is that
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
| 13 — Strategy Factory | Accounting (authoritative P&L), 40 template families, research queue, discovery, robustness, leagues, factory pipeline to LIVE_CANDIDATE |
| A — Autonomous 5 slots | Slot allocation, mandatory stop plans, slot trader (SIMULATION / SHADOW / LIVE), PDT and settled-funds rules, Robinhood MCP broker; market-cap fallback; ETF switching funds in slots |
| C — Survivorship universe | Layer A 1996-2024, cohorts, synthetic dead companies (fails its realism gate: retest-only), five loader modes |

Phase 6 is complete as of 2026-09-24: baselines per forward fund (§16), model
calibration (§19), rate regimes (§21), the TNON case study (§24), methodology
and protocol docs (§29) and the phase report generator (§31,
`phase6_report.py`). The seed-free control run (§3) is registered and its arms
are running.

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

One account (Agentic, `limited_margin`), about $88 when LIVE was armed on
2026-09-24. **The slot trader places real orders in it automatically**, every
5 minutes in market hours, through the risk engine and kill switches. First
session: SNDK, DELL, MRNA $20 each and TWST $8.45 (the settled cash left);
slot 5 bought nothing. No strategy trading it has demonstrated an edge: four
of five slots are Rising 200 variants, an entry rule the 14-year sweep found
loses net. `touch data/KILL_SWITCH` stops everything and flattens the slots.
