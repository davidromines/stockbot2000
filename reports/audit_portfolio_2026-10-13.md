# Phase C2-C3: comparable metrics and the five-slot portfolio

Computed 2026-10-13 05:49 UTC, read-only. Honest basis: next-open fills, modelled costs deducted. 284 funds with >= 20 trades.

## C2. Are strategies compared on a defensible basis?

The ranking scales each strategy's per-trade figure to 20 sessions using that strategy's own holding period (floor 5). Four bases for the same funds:

- **per trade**: mean net return of a trade;
- **per holding session**: per-trade mean divided by mean sessions held;
- **per 20 sessions**: the ranking's basis (per trade x 20 / max(hold, 5));
- **per fund session**: what the whole fund earned per session including idle cash (the dollar actually available to the owner earns this).

Rank correlation between the bases (Spearman, across funds):

| | per_trade | per_session | per_20 | fund_per_session |
|---|---:|---:|---:|---:|
| per_trade | +1.00 | +0.94 | +1.00 | +0.64 |
| per_session | +0.94 | +1.00 | +0.96 | +0.66 |
| per_20 | +1.00 | +0.96 | +1.00 | +0.65 |
| fund_per_session | +0.64 | +0.66 | +0.65 | +1.00 |

Overlap of each basis's top 10 with the per-trade top 10: per_trade 10/10, per_session 4/10, per_20 10/10, fund_per_session 3/10.

Holding period (sessions) across funds: median 3.0, 10th to 90th percentile 1.0 to 8.0; capital utilisation (positions / equity) median 97%; turnover median 3.0 trades per session of fund life; cost per trade median 0.15 %.

The five best funds on each basis (honest net, with the date-block interval of the per-trade mean):

| basis | fund family | trades | dates | per trade % | 95% interval | hold | per session % | per 20 % | util |
|---|---|---:|---:|---:|---|---:|---:|---:|---:|
| per_trade | st_uptrend_pullback | 20 | 1 | +7.72 | n/a to n/a | 10.0 | +0.77 | +15.43 | 99% |
| per_trade | kf_reversal | 20 | 1 | +4.69 | n/a to n/a | 5.0 | +0.94 | +18.75 | 98% |
| per_trade | st_uptrend_pullback | 20 | 1 | +4.64 | n/a to n/a | 6.0 | +0.77 | +15.48 | 98% |
| per_trade | lab_search | 27 | 10 | +3.58 | -2.34 to +7.39 | 2.1 | +1.72 | +14.31 | 88% |
| per_trade | kf_reversal | 20 | 1 | +3.28 | n/a to n/a | 5.0 | +0.66 | +13.10 | 98% |
| per_20 | kf_reversal | 20 | 1 | +4.69 | n/a to n/a | 5.0 | +0.94 | +18.75 | 98% |
| per_20 | st_uptrend_pullback | 20 | 1 | +4.64 | n/a to n/a | 6.0 | +0.77 | +15.48 | 98% |
| per_20 | st_uptrend_pullback | 20 | 1 | +7.72 | n/a to n/a | 10.0 | +0.77 | +15.43 | 99% |
| per_20 | lab_search | 27 | 10 | +3.58 | -2.34 to +7.39 | 2.1 | +1.72 | +14.31 | 88% |
| per_20 | kf_reversal | 20 | 1 | +3.28 | n/a to n/a | 5.0 | +0.66 | +13.10 | 98% |
| fund_per_session | st_uptrend_pullback | 20 | 1 | +7.72 | n/a to n/a | 10.0 | +0.77 | +15.43 | 99% |
| fund_per_session | momentum | 88 | 18 | +1.55 | -0.60 to +3.32 | 1.6 | +0.95 | +6.20 | 86% |
| fund_per_session | momentum | 41 | 15 | +2.57 | -1.59 to +4.80 | 2.1 | +1.21 | +10.28 | 62% |
| fund_per_session | momentum | 50 | 15 | +3.01 | -1.81 to +7.76 | 2.4 | +1.24 | +12.02 | 74% |
| fund_per_session | momentum | 80 | 18 | +1.36 | -0.53 to +2.86 | 1.5 | +0.90 | +5.43 | 83% |

Reading: the ranking's basis (per 20 sessions) is rank-identical to per trade (Spearman +1.00, top-10 overlap 10/10) because most holds are shorter than its 5-session floor, so it multiplies every such fund by the same constant and the holding-period adjustment does nothing for them. Per holding session keeps 4 of the per-trade top 10; per fund session (idle cash included) keeps 3. The intervals around the top funds cross zero, and several top funds have a single entry date (no interval possible). A common framework reports all four bases and an interval beside each other; ranking on one of them is a decision for after the prospective test (A6).

## C3. Are the five slots five different bets?

Live positions now:

| slot | symbol | entry | mark since entry % | industry division | beta |
|---:|---|---:|---:|---|---:|
| 1 | WDC | 443.92 | -10.51 | Manufacturing | 2.88 |
| 2 | CRS | 388.88 | -0.79 | Manufacturing | 1.55 |
| 3 | INTC | 107.32 | -2.44 | Manufacturing | 2.88 |
| 4 | AMD | 594.59 | +2.27 | Manufacturing | 3.15 |
| 5 | FDX | 289.47 | +0.77 | Transportation, Communications, Utilities | 0.90 |

Over the last year of daily closes (274 sessions): average pairwise correlation of the five holdings +0.31; equal-weight beta to SPY 2.27; diversification ratio 1.41 (1.00 = one bet, 2.24 = five independent bets of equal risk). Mean beta of the five holdings 2.27.

| | AMD | CRS | FDX | INTC | WDC |
|---|---:|---:|---:|---:|---:|
| AMD | +1.00 | +0.29 | +0.14 | +0.57 | +0.45 |
| CRS | +0.29 | +1.00 | +0.26 | +0.25 | +0.32 |
| FDX | +0.14 | +0.26 | +1.00 | +0.15 | +0.23 |
| INTC | +0.57 | +0.25 | +0.15 | +1.00 | +0.46 |
| WDC | +0.45 | +0.32 | +0.23 | +0.46 | +1.00 |

Strategy-level correlation of the five holders (stored weekly series 2023 to today, `strategy_correlation`):

| slot pair | correlation |
|---|---:|
| 1-2 | +0.47 |
| 1-3 | +0.42 |
| 1-4 | +0.41 |
| 1-5 | +0.47 |
| 2-3 | +0.38 |
| 2-4 | +0.42 |
| 2-5 | +0.40 |
| 3-4 | +0.56 |
| 3-5 | +0.57 |
| 4-5 | +0.25 |

## Shadow comparison: current top-five rule vs a portfolio-aware alternative

Both pick five funds per snapshot with one-per-family and the 0.7 correlation veto where a correlation is stored. They differ in the estimate they sort by: the stored score (current) or the empirical-Bayes estimate that shrinks each fund toward the pool by its date-based uncertainty (alternative). Realised = later honest net mean of the chosen funds, %, average of the five.

| snapshot | funds | current | alternative | pool mean |
|---|---:|---:|---:|---:|
| 2026-09-24 | 100 | -2.53 | -2.54 | -3.21 |
| 2026-09-25 | 324 | +0.02 | +0.45 | +0.47 |
| 2026-09-28 | 304 | -0.12 | -1.16 | +0.29 |
| 2026-09-29 | 235 | +1.23 | +1.23 | +0.62 |
| 2026-09-30 | 209 | -0.08 | +0.14 | +0.50 |
| 2026-10-01 | 188 | +1.71 | +0.77 | +0.14 |
| 2026-10-02 | 144 | -0.40 | +0.30 | -0.21 |
| 2026-10-05 | 95 | -2.25 | -2.39 | -0.83 |
| 2026-10-06 | 71 | +0.03 | -0.09 | +0.54 |
| 2026-10-07 | 47 | +1.43 | +1.56 | +1.17 |

Mean over 10 snapshots: current -0.10 %, alternative -0.17 %, pool -0.05 %; the alternative was at least as good on 5 of 10 snapshots.

## What could be wrong with this analysis

- Outcomes are 1 to 11 sessions long and from one regime; snapshots overlap heavily, so the comparison has fewer independent observations than rows.
- Holdings correlation uses a year of daily closes of five names: it describes the exposure the positions carry, not the strategies' signals.
- Sector and beta are heuristics (SIC division from the latest filing; monthly beta); the diversification ratio assumes equal weights.
- The alternative is a shadow estimator only; it ignores the cash and settled-funds constraints, and it is not recommended for live use on this evidence.
- Funds with fewer than 20 honest trades are excluded from C2; stand-in, pair and value slot holders have no paper run.
