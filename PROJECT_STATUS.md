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
| Live account | **-$3.59 (-4.1%)** since LIVE armed 2026-09-24, 16 trading days ($84.12 at Monday 2026-10-12's close); peak $90.26, now 6.8% below it, worst 7.2%; Monday -$0.62 |
| Live slots | 5 of 5 filled, cash $0 — WDC, CRS, INTC, AMD (new 10-12, replaced DELL), FDX; 3 of 5 currently negative |
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
was armed on 2026-09-24 — **-$3.59 net (-4.1%), 16 trading days**, as of Monday's close. The slot trader
places real orders in it automatically, every 5 minutes in market hours,
through the risk engine and kill switches. Current slots (each scoped to its
own assignment — a slot's P&L never carries a previous occupant's trades):
WDC -12.8%, CRS -2.8%, INTC -5.6%, AMD 0.0% (just assigned), FDX +0.9%. `touch
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
| Funnel vs raw data | Checked and **retracted**: the funnel's formula equals a plain recompute; the earlier figures I compared were a week-old snapshot. The reported set did move in a week (see the first-pass table below) |
| Statistics | The funnel's t-statistic treats trades as independent; deflation / multiple-testing code exists only in the frozen Lab ladder, not in the funnel, ranking or slots |
| Luck threshold | Noise alone gives a best t of 2.5-4.9 depending on how many independent tests are assumed (88 families to 1M trials); two to three of the seven families (t 2.9-3.4) sit inside that range even at the generous end |
| Data | No option expiries beyond 77 days, so LEAPS cannot be tested |

Status of the seven families therefore: **unresolved** — not promoted, not dismissed.

**First pass of the audit (Phase A1-A3, `audit_forward.py`, 2026-10-13; read-only; `reports/audit_forward_2026-10-13.md`).** Two new findings:
the paper engine **fills at the signal-day close** (entries and exits both; the simulator and backtest were moved to next-open fills on
2026-09-15, the paper engine was not), and **`pnl_pct` is the gross price move**, so the "net per trade" figures in the funnel and the
10-12 dossier are gross (modelled costs are 0.15-0.18% of notional per round trip). Recomputed with costs and next-open fills on
adjusted prices, and with entry dates as the unit of independence:

| family | reported | honest net mean | date-cluster t | independent entry dates | 95% date-block bootstrap |
|---|---:|---:|---:|---:|---|
| lab_search | +1.30% (t 18.5) | +0.90% | +2.2 | 10 | [-0.25%, +1.40%] |
| momentum | +2.04% (t 4.2) | +1.71% | +1.4 | 18 | [-1.03%, +3.78%] |
| kf_mean_reversion | +1.22% (t 2.2) | +1.71% | +2.4 | 7 | [-0.70%, +3.12%] |
| bollinger_reversion | +0.39% (t 1.9) | +0.45% | +1.1 | 5 | [+0.03%, +2.45%] |
| kf_seasonality | +0.46% (t 2.8) | +0.11% | +0.3 | 8 | [-0.70%, +0.62%] |
| st_uptrend_pullback | +0.36% (t 1.5) | +0.19% | +0.1 | 8 | [-2.58%, +1.99%] |
| st_momentum_1d | -0.20% (t -1.5) | -0.39% | -0.9 | 10 | [-1.26%, +0.42%] |

All provisionally **Unresolved: fewer than 20 independent entry dates**. `lab_search`'s effective sample is about 270 trades, not
7,941. Early positives faded (`momentum`: +3.96% before 09-25, -0.16% after). Proposed fixes (not done, need your go-ahead):
next-open fills in the paper engine as a restatement beside the originals, label `pnl_pct` gross and report net, and run the funnel's
statistics through the clustered calculation.

**Approved 2026-10-13 and done:** (G1) `restate_paper.py` stores every closed paper trade at next-open fills in
`paper_trades_restated` (version `v2_next_open`) beside the unchanged originals, run daily before the funnel (18,730 of 20,294
restated; the rest exit on the newest bar and wait for a next-session open); (G2/G3) `funnel.py` now reports gross, net,
next-open and clustered statistics (shared module `forward_stats.py`), requires 20 independent entry dates, and its hard-coded
conclusions about named families are replaced by data-driven text. Under the corrected test **no family is positive** (0 of 43);
the old iid-on-gross test still flags 6.

**Drawdown tiers (approved 2026-10-13): MERGED to main 05:15 UTC and live.** A Telegram
notice at 10% from the peak, new entries refused at 20% (exits still go), the 35% kill switch unchanged; 22 tests; touches
`risk_engine.py` and `slot_trader.py`. The daily image now shows the drawdown from peak. Acceptance checklist: 27/27.

**Phase A4-A6 (2026-10-13, read-only).** `audit_selection.py` applies multiple-testing adjustments (Holm, Benjamini-Hochberg, max-T sign-flip on excess over SPY;
about 28 effective independent tests across 31 families) and separates the retroactive replay: the Lab survivors were enrolled 09-27 with start date 09-24, so 2,886 of
`lab_search`'s 7,941 trades are a replay (+1.63 % vs +0.48 % on the prospective trades, +0.19 % over SPY). Enrollment did not depend on outcomes (all validation passes
dated 09-22 or earlier). No family survives adjustment; none has a max-T adjusted p below 0.14 once the replay is removed. Verdicts: six Unresolved, two (`st_uptrend_pullback`,
`st_momentum_1d`) provisionally Not supported, none Promising (`docs/AUDIT_A6_FAMILY_VERDICTS.md`). A pre-registered prospective test
(`forward_families_prospective` v1, locked in the experiment registry, entries from 2026-10-12, 20 independent dates + 15 sessions, expected about December) is the
test that can change this; progress via `./venv/bin/python prospective_eval.py`.

**Phases B and C (2026-10-13, read-only / shadow; `docs/AUDIT_BC_FINDINGS.md`).** Funnel to real money: 2,233 strategy identities, 1,005 positive with the dead companies, 205 positive on the
unseen window, 168 with >= 20 honest forward trades, 82 positive, **0 with 20 independent entry dates of their own**; the pool of honest forward trades nets -0.45 % per trade; the real account is 16 closed
trades, +$0.37. Ranking audit: `n` counts open positions (the top-50 median is 20 trades from one entry date), the stored score ranks later returns worse than the backtest or a date-counting estimate, and one
shared trade (KOD, +163.85 %) sits in the paper funds of three of the five slots. Shadow capital gate (13 criteria, unknown blocks, daily stage `[9k1]`): 0 of 384 eligible, 0 of 5 slot holders. Portfolio: the five live
positions have an equal-weight beta of 2.27 to SPY (WDC, INTC, AMD at 2.9 to 3.2) and a diversification ratio of 1.41 against 2.24 for five independent bets. Five decisions are waiting for the owner; nothing live changed.

## Housekeeping

Data backup run 2026-10-13 04:41 UTC and verified (forward records: 408,131 rows, 62 tables;
listings snapshot 536,291 rows). Regression suite: 148 test files pass (last full run 2026-10-12).

## Not yet live: a redesigned daily report

The owner asked for a single one-page image (big P&L number, a sparkline per
slot, no jargon) to replace the current 17-section Telegram text report.
Built (`daily_snapshot.py`), tested (13 new regression checks, full suite
passing), rendered against the real account and shown to the owner — paused
before cron/Telegram wiring until the design is confirmed.
