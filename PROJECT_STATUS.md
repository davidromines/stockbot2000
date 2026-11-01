# PROJECT_STATUS

Updated 2026-11-01 (Sunday; figures to Friday 2026-10-30's close unless stated).

Stockbot2000 is a quantitative research and trading system: it ingests prices and point-in-time fundamentals,
generates and evaluates strategies, tracks them through a versioned league, and since 2026-09-24 15:39 UTC trades a
small Robinhood account automatically (LIVE, armed by the owner). Its defining property is that nearly every apparent
edge it has found has turned out to be a measurement artifact, so this page states what the system reports and, as
prominently, what it has **not** established.

**Headline:** the real account is −$4.47 (−5.1%) since launch, but +$1.59 (+1.9%) since the 2026-10-19 changes
that stopped forced selling (SPY +0.8% over the same days). No strategy has demonstrated an edge; three pre-registered
forward tests decide that, the first in about December.

## At a glance

| Measure | Reading |
|---|---|
| Real account | **$83.24** (Fri 10-30 close) against $87.71 at launch: **−$4.47 (−5.1%)**, 31 trading days; peak $90.26, lowest close $81.03; SPY +0.7% over the same days |
| Since the 10-19 changes | **+$1.59 (+1.9%)** over 10 trading days; SPY +0.8% |
| Where the loss is | 20 medium-term trades closed before 10-19: **−$6.79** (mostly sold early by slot reassignment). Runners: 47 trades, −$0.01. Open positions: +$2.33 |
| Holdings | slot 1 OVV +$1.68 (+8.4%) · slot 2 NTLA +$1.56 (+7.8%, stop $9.23) · slot 4 CRM −$0.91 (−4.5%) · slots 3 and 5 = intraday Runners ($5 a trade, flat overnight) |
| Ledger vs Robinhood | Matches to the cent (gap $0.00; 20 days of realised P&L agree) |
| Acceptance checklist | 27 of 27 (2026-11-01) |
| Regression suite | 190 test files, all passing (2026-11-01) |
| Backup | Verified 2026-11-01: forward records 1,874,668 rows / 75 tables; listings snapshot 536,389 rows |
| Search | Frozen by policy since 2026-09-22 (`search.mode: FROZEN`) |
| Options / crypto | Built, switched off (`allow_options` / `allow_crypto` false); the bot's account has no options approval |

## What changed since the last update (2026-10-13)

**Independent audit (Addendum F, 10-13):** phases A–H run. Two engine defects found (paper fills at the signal-day
close; `pnl_pct` gross), a restated record built beside the originals, the funnel's statistics made dependence-aware.
Result: **no strategy family survives as an established edge**; a pre-registered prospective test was registered
(details in `docs/AUDIT_F_FINAL_REPORT.md`).

**Intraday Runners (Addendum G, 10-15 / 10-17):** two of the five live slots trade intraday momentum (stocks; index
bull/inverse ETF pairs), owner-waived evidence gates; $5 a trade since 10-19.

**Stage AD — the profitability plan (Addendum H, owner "go" 10-19/20)** (`docs/STAGE_AD_PROFITABILITY_PLAN.md`):

| Change | State |
|---|---|
| Monthly slot review (first 2026-11-02); between reviews only hard failures release a slot; rule changes grandfathered | LIVE |
| Book beta cap 1.3 (refuses purchases only) | LIVE |
| Live quotes: a fresh, tight bid/ask stands in for Robinhood's lagging last-trade time (it halted the Runner six times and forced one exit on 10-20) | LIVE since 10-21 |
| Split handler: a confirmed split restates the slot position before any stop is checked | LIVE |
| Paper engine: decide on the close, fill at the next open (the simulator's convention); stocks below the $5 purchase floor are stopped on their real close | LIVE since 10-21 |
| **Found by the rehearsal:** the old engine never stopped a held stock below $5 and booked it at its entry after 20 sessions — 35 trades recorded at 0.00% (true −15% to −96%), 701 open positions (median −44%); fixed and booked | done |
| Accounting v2 / v3: open positions on the adjusted series; closed trades from the restated record | LIVE |
| 17 wider-stop (6× ATR) paper strategies, excluded from slots until their own record (owner option (a)) | paper since 10-22 |
| One-page image report to Telegram, evidence lines in the caption | LIVE since 10-21 |
| Basket slots, risk-adjusted ordering, entry-timing experiment, evidence-weighted allocator | shadow / SIMULATION; owner decisions after the 20-session freeze (~11-16) |
| Prediction service, timing dial, live attribution, ledger check, Runner prospective test | daily stages [9k2]–[9k7] |

**Options (owner 10-22):** the $100-per-contract cap was removed (contracts that cheap had a median buy/sell gap of
72% of their price); still one long call or put per trade, short options blocked in code (owner: "I can't do
open-ended losses").

## Research results since 10-19 (all pre-registered; the rule written before any result)

| Experiment | Question | Result |
|---|---|---|
| `alpha_bench_v1` | Do 12 published signals replicate here (long-only, next-open, net)? | 0 validated, 8 replicated |
| `classifier_timing_dial_v1` | Does the classifier's average score time the market? | PASS one look (corr +0.36, t +6.5); prospective shadow running |
| `earnings_skip_v1` | Skip entries within 5 sessions of a report? | **FAIL** — the skipped trades did better (+2.53% vs +1.98%) |
| `stop_width_slots_v1` | Wider or tighter ATR stops? | **Wider wins**: 6× beats the current stop for 19 of 23 strategies (20 of 23 per 20 sessions held); paper-tracked, not live |
| `crypto_swing_v1` | Crypto rules held 12–48 h at Robinhood's prices? | **FAIL** — 0 of 18; Robinhood's crypto buy price is ~1.9% above its sell price, a coin's typical hourly move 0.2–0.5% |
| `options_liquid_v1` | Long calls/puts without the cap, tight gaps only? | **FAIL** — 0 of 10; tight gaps cut losses for 7 of 10; closest: insider-buying call +22%/trade, t 1.9 (needs 2.8) |
| `earnings_itm_call_v1` | Predict an earnings beat, buy an in-the-money call before the report | **FAIL** — the prediction works (69% beat vs 55%) but the stock moves only +0.28% vs SPY around a predicted beat (priced in); the calls lost |

## The tests that decide (pre-registered, prospective)

| Test | Needs | Progress (10-30) | Verdict about |
|---|---|---|---|
| `forward_families_prospective` — 8 strategy families | 20 pooled entry dates, then 15 sessions | 12 of 20 dates | December 2026 |
| `intraday_runner_v0_prospective` — the live Runners' signals | 300 signals over 30 sessions | stock 141 / 9 sessions, mean −0.07% (t −1.2); twin 17, −0.11% | early December |
| `market_timing_dial_shadow_v1` | 120 sessions with outcomes | 9 | April 2027 |

## What has NOT been established

- **No strategy has a demonstrated edge.** The live gains since 10-19 are ten sessions, mostly one stock (NTLA +18% in
  two days).
- The Runners' replay on history was negative (stock −0.11% per signal, t −3.3); their live record is flat.
- Survivorship is handled with a tuned synthetic reconstruction of dead companies, not real delisted prices.
- Earnings "beats" are measured against the same quarter a year earlier; there is no analyst-consensus history.
- The free option data covers ~150 stocks a day, so option tests are small.

## Open decisions and next steps

1. **2026-11-02:** the first monthly slot review (the read-only preview keeps all three holders).
2. **~11-16, after the 20-session freeze:** basket slots in LIVE; risk-adjusted ordering; the entry-timing experiment;
   the allocator from shadow to deciding; the wider-stop variants' record.
3. **Options:** gap limit of 5% for paper (proposed, not yet approved); the account's options approval is the owner's.
4. **Robinhood sign-in** renewal before ~11-04 (the bot warns at 20 days).
5. Item left small on purpose: Kalman pair trades restate one session late (2 trades).

## What is built

| Phase / Stage | Built |
|---|---|
| 6 — Research integrity | Regression suite (190 files), ancestry, search freeze, truth sets, point-in-time universe, freshness gating, sealed holdout, experiment registry, random control, multiple-testing accounting, research integrity report (nightly) |
| 7–11 — League, library, value engine, promotion, operations | Versioned strategy league, scoreboard, research library, Knowledge Factory (Stage O), statement and valuation engines, Value Fund, stop conditions, daily loop, diagnostic funnel (Stage T) |
| 13 — Strategy Factory | Accounting (authoritative P&L, v3), 40+ template families, discovery, robustness, factory pipeline |
| A — Autonomous slots | Slot allocation, mandatory stop plans, slot trader (SIMULATION / SHADOW / LIVE), PDT and settled-funds rules, Robinhood MCP broker, split handler, book beta cap |
| C / M — Survivorship | Synthetic dead companies (generator v5c, graded per exit type), five loader modes, survivorship backtests in the ranking |
| K — Crypto | Trend grid, paper funds, slot trader with a resting stop — built, off |
| R — Options | Data, lab, paper funds, real-order engine for one long call/put — built, off |
| AB — Independent audit | Phases A–H; restated record; dependence-aware statistics; capital gate (shadow) |
| AC — Intraday Runners | Stock momentum and index-ETF twin runners, resident service, stops, prospective test — LIVE at $5 |
| AD — Profitability plan | Monthly review, quote fix, next-open paper engine, accounting v3, alpha bench, prediction service, allocator, timing dial, attribution, ledger check, image report |

## History

The 2026-10-13 audit and its tables (corporate actions, duplicate trades, the seven families recomputed, phases A–H)
are in `docs/AUDIT_F_FINAL_REPORT.md`, `docs/AUDIT_A6_FAMILY_VERDICTS.md`, `docs/AUDIT_BC_FINDINGS.md` and
`docs/AUDIT_D_FINDINGS.md`. The per-day build record is `CLAUDE.md`'s handoff sections and the git log.
