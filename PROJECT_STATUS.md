# PROJECT_STATUS

Updated 2026-10-13.

Stockbot2000 is a quantitative research system: it ingests prices and
point-in-time fundamentals, generates and evaluates trading strategies, tracks
them through a versioned league, and since 2026-09-24 15:39 UTC trades five
$20 slots in the Robinhood Agentic account automatically (LIVE, armed by the
owner). Its defining property is that every apparent edge it has found so far
turned out to be a measurement artifact, so this page states what the system
currently reports and, at least as prominently, what it has NOT established.

**Every build item on the project's roadmap is now complete.** The two stages
still in progress at the last update (2026-09-29) — Stage O (Knowledge
Strategy Factory) and Stage R (options trading, including the real-money
path) — finished 2026-10-05 and 2026-10-12 respectively. What remains open is
owner-gated arming (`allow_options`, `allow_crypto`, `search.mode: ACTIVE`,
`published_prior`) and whether the first statistically positive forward
signal below is real or this project's next entry in its own defect ledger
(`CLAUDE.md`, "A standing caution").

## What is built

| Phase / Stage | Built |
|---|---|
| 6 — Research integrity | Regression suite (148 test files, all passing), ancestry, search freeze, truth sets, point-in-time universe, freshness gating, validation firewall, sealed holdout, experiment registry, random control, multiple-testing accounting, research integrity report (runs nightly) |
| 7 — Strategy league | Strategy identity, immutable versioning, 10-state lifecycle, scoreboard, degradation tracking, correlation, eligibility |
| 8 — Research library | Governed generation; Knowledge Strategy Factory (Stage O, O1-O13) as a second, documented-evidence source |
| 9 — Fundamental value | Point-in-time filing provenance, industry classification, statement engine, valuation engine, intrinsic value, value score, Value Fund |
| 10 — Promotion | Promotion policy, capital allocation, roster management, live pipeline |
| 11 — Operations | Stop conditions, compute priority, the daily research loop, the diagnostic funnel (Stage T) |
| 13 — Strategy Factory | Accounting (authoritative P&L), 40+ template families, research queue, discovery, robustness, leagues, factory pipeline |
| A — Autonomous 5 slots | Slot allocation, mandatory stop plans, slot trader (SIMULATION / SHADOW / LIVE), PDT and settled-funds rules, Robinhood MCP broker |
| C — Survivorship universe | Layer A, cohorts, synthetic dead companies (generator v5c, evidence-graded per exit type), five loader modes |
| K — Crypto | Trend grid, paper funds, slot trader with a resting stop — built, gated off (`allow_crypto: false`) |
| O — Knowledge Strategy Factory | **Complete 2026-10-05 (O1-O13).** Documented sources (academic papers, published factors) reproduce, vary and queue as governed-mutation seeds; never imports the frozen search directly |
| R — Options trading | **Complete 2026-10-12 (R1-R7).** Real-order engine (`options_live.py`) mirrors a proven paper strategy for real money — built, tested, committed, deliberately inert: no option level on the account, `allow_options: false`, no strategy within 20 closed paper trades of proven (best: 3) |

## What the system says today

| Measure | Current reading |
|---|---|
| Search | Still frozen by policy (`seed_mode: NONE`); not restarted this period |
| Live account | **-$1.75 (-2.0%)** since LIVE armed 2026-09-24, 15 trading days; today +$0.11 |
| Live slots | 5 of 5 filled, cash $0 — WDC, CRS, INTC (+2.8% best), DELL, FDX; 3 of 5 currently negative |
| Acceptance checklist (`acceptance.py`) | 25 of 27 passed (last full read 2026-10-06) — the 2 failures are expected: full suite needs `--suite`, SHADOW track record still accruing |
| Forward families clearing t > 2 | **7, newly observed 2026-10-12** — see below. None promoted; **under independent audit (Addendum F, not yet started)** |
| Regression suite | 148 of 148 test files pass |
| Options paper record | Best is 3 closed trades per strategy, against the 20 needed to arm real orders |

## The headline finding this period — and why it is not a celebration

The nightly diagnostic funnel (Stage T, running since 2026-09-27) has, for the
first time, accumulated enough forward trades for several families to clear a
conventional significance bar:

| Family | Net / trade | t | n (trades) |
|---|---:|---:|---:|
| kf_mean_reversion | +4.86% | 2.9 | 28 |
| momentum | +2.69% | 4.8 | 331 |
| lab_search | +1.51% | 17.2 | 5,560 |
| bollinger_reversion | +1.22% | 3.2 | 150 |
| kf_seasonality | +1.18% | 7.1 | 340 |
| st_uptrend_pullback | +1.13% | 3.7 | 348 |
| st_momentum_1d | +0.47% | 3.4 | 683 |

This is read from the same funnel that has, until now, consistently and
correctly reported "no edge." Two mechanical reasons the sample is suddenly
large enough to compute a t-stat at all: nearly a thousand Lab validation
survivors that had never been paper-traded were all enrolled in late
September, and three more weeks of calendar time have passed. Neither reason
implies the signal is real. `lab_search`'s huge n is also the most suspect:
roughly half its trades share a ticker and date with another fund, which
deflates the effective sample size below what 5,560 suggests. **None of these
seven are promoted, gated into a slot preferentially, or treated as anything
but a result to watch** — this project's own history (the defect ledger in
`CLAUDE.md`) is a long list of exactly this shape of finding turning out to
be a measurement artifact.

## What has NOT been established

- No strategy has been promoted or confirmed to have a durable edge; the
  table above is forward signal, not a demonstrated one.
- 3 of 5 current slot holders are Lab-discovered strategies whose only
  "name" is the raw rule they evolved to — unauditable by a person at a
  glance, even though this is exactly the family with the largest forward
  sample above.
- Survivorship bias is handled with a tuned synthetic reconstruction (five
  generator configurations were tried on the same real failures before the
  one in use was adopted), not real delisted price data.
- Debt is tagged for only a minority of filers, so EV-based multiples cover
  a minority of the universe.

## Real money

One account (Agentic, `limited_margin`), ~$86 today against ~$88 when LIVE
was armed on 2026-09-24 — **-$1.75 net, 15 trading days**. The slot trader
places real orders in it automatically, every 5 minutes in market hours,
through the risk engine and kill switches. Current slots (each scoped to its
own assignment — a slot's P&L never carries a previous occupant's trades):
WDC -10.5%, CRS -0.6%, INTC -2.5%, DELL +2.8%, FDX +0.9%. `touch
data/KILL_SWITCH` stops everything and flattens the slots. A second
real-money path (options, R7) is built and committed but inert — see the
Stage R row above.

## Independent review and the audit that follows (2026-10-13)

An independent reviewer read the 2026-10-12 dossier and asked for an audit before any of
the seven positive families is trusted (`docs/ADDENDUM_F_PROFITABILITY_AUDIT.md`, Stage AB;
**entered, not yet built**). Its core points: separate *research ranking* from *live-capital
eligibility*; recompute the seven families from raw trades with dependence-aware statistics
and a multiple-testing correction; find where candidates are lost between hypothesis and
real money; keep live execution, options, crypto and the frozen search untouched.
Owner ruling: the "1%" target is not tied to one denominator; per-trade, per-deployed-dollar,
portfolio and monthly/annualized returns are reported side by side, with no target set yet.

Checks made while reviewing sixteen outside ideas (`docs/IDEAS_LOG.md`; most declined)
already produced verified leads, none acted on:

| Lead | Finding |
|---|---|
| Corporate actions | 4 `CTVA` paper trades show about -84% because an unadjusted entry price is compared with a back-adjusted exit (likely a spin-off) |
| Duplicates | The same ticker-and-date trade appears once per fund (`lab_search`: 8,791 trades in 566 funds) |
| Funnel vs raw data | A plain recompute gives momentum +2.04% (funnel +2.69%) and `st_uptrend_pullback` +0.36% (funnel +1.13%); cause not yet found |
| Statistics | The funnel's t-statistic treats trades as independent; deflation / multiple-testing code exists only in the frozen Lab ladder, not in the funnel, ranking or slots |
| Luck threshold | Noise alone gives a best t of 2.5-4.9 depending on how many independent tests are assumed (88 families to 1M trials); two to three of the seven families (t 2.9-3.4) sit inside that range even at the generous end |
| Data | No option expiries beyond 77 days, so LEAPS cannot be tested |

Status of the seven families therefore: **unresolved, pending Phase A** — not promoted, not
dismissed.

## Housekeeping

Data backup run 2026-10-13 04:41 UTC and verified (forward records: 408,131 rows, 62 tables;
listings snapshot 536,291 rows). Regression suite: 148 test files pass (last full run 2026-10-12).

## Not yet live: a redesigned daily report

The owner asked for a single one-page image (big P&L number, a sparkline per
slot, no jargon) to replace the current 17-section Telegram text report.
Built (`daily_snapshot.py`), tested (13 new regression checks, full suite
passing), rendered against the real account and shown to the owner — paused
before cron/Telegram wiring until the design is confirmed.
