# Phase B3: audit of the ranking formula

Computed 2026-10-13 05:49 UTC, read-only, from `ranking_history` (12 daily snapshots, 2026-09-24 to 2026-10-09) and `paper_trades_restated` (next-open fills, modelled costs deducted). Nothing here changes a live setting.

## 1. Does production match the documented formula?

Recomputed (10 x backtest + n x forward) / (10 + n) from the stored components for 19,507 rows / 2,013 strategies. The stored score divided by that blend is the hold-length factor 20 / max(hold, 5): stable per strategy across dates for 80% of strategies; median factor 0.77, 10th to 90th percentile 0.16 to 1.67; 5% of rows are scaled by more than 3x (short measured holds scale a noisy per-trade figure up by up to 4x, the floor being 5 sessions).
Production deviates from the documented "starting at the backtest": 21% of rows use the 2023-to-today unseen-window result as the prior instead of the 2016-19 backtest stored in `ranking_history.backtest`, and 41% are Lab-search funds whose prior is zero (paper evidence only). The stored `backtest` column is therefore not what scores.

## 2. What the formula does with small and correlated samples

Of the 50 best-scored gate-passing strategies on each date: median trades counted in `n` (closed plus open positions), share with fewer than 10, and the independent entry dates behind those trades (closed plus open, entered before the date).

| date | median trades | share < 10 trades | median indep. dates | share < 5 dates |
|---|---:|---:|---:|---:|
| 2026-09-24 | 0 | 100% | 0 | 94% |
| 2026-09-25 | 0 | 74% | 0 | 92% |
| 2026-09-28 | 0 | 74% | 0 | 92% |
| 2026-09-29 | 20 | 38% | 1 | 92% |
| 2026-09-30 | 20 | 40% | 1 | 92% |
| 2026-10-01 | 20 | 20% | 1 | 88% |
| 2026-10-02 | 20 | 30% | 1 | 74% |
| 2026-10-05 | 20 | 14% | 1 | 86% |
| 2026-10-06 | 20 | 12% | 1 | 84% |
| 2026-10-07 | 20 | 10% | 1 | 86% |
| 2026-10-08 | 20 | 12% | 1 | 80% |
| 2026-10-09 | 20 | 12% | 1 | 82% |

`n` in the formula is a trade count, so ten trades from two entry dates weigh as much against the backtest prior as ten trades from ten dates.

## 3. Calibration and information value (chronological)

Each daily snapshot is a prediction; the outcome is the mean honest net return of that strategy's trades entered on or after the snapshot date. A strategy needs >= 3 later trades to have an outcome. Funds recur across snapshots, so rows are not independent; the dates are only 1 to 11 sessions of outcome.

| snapshot | funds | stored score rho | 10:n blend rho | backtest rho | forward rho | EB rho | pool mean realised % | top-5 by score % | top-5 by EB % |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2026-09-24 | 122 | +0.24 | +0.24 | +0.25 | n/a | n/a | -3.89 | -0.34 | n/a |
| 2026-09-25 | 377 | -0.09 | +0.25 | +0.39 | -0.04 | +0.35 | +0.02 | +0.28 | +0.68 |
| 2026-09-28 | 356 | -0.08 | +0.23 | +0.38 | -0.05 | +0.35 | -0.15 | +0.27 | +1.53 |
| 2026-09-29 | 271 | +0.13 | +0.30 | +0.27 | +0.11 | +0.45 | +0.30 | +0.73 | +2.09 |
| 2026-09-30 | 241 | +0.06 | +0.18 | +0.28 | +0.05 | +0.46 | +0.22 | -0.80 | +2.09 |
| 2026-10-01 | 219 | +0.10 | +0.18 | +0.31 | +0.07 | +0.45 | -0.13 | -0.77 | +2.24 |
| 2026-10-02 | 165 | +0.10 | +0.18 | +0.24 | +0.08 | +0.31 | -0.42 | -0.48 | +1.92 |
| 2026-10-05 | 110 | +0.08 | +0.23 | -0.14 | +0.17 | +0.04 | -0.94 | -2.21 | -1.78 |
| 2026-10-06 | 84 | -0.19 | -0.17 | +0.07 | -0.18 | +0.16 | +0.46 | +0.79 | +0.50 |
| 2026-10-07 | 53 | -0.09 | -0.13 | +0.09 | -0.13 | +0.04 | +1.12 | +1.63 | +0.78 |

| predictor | mean rank correlation over snapshots | snapshots with rho > 0 | mean realised % of its top 5 |
|---|---:|---:|---:|
| stored score | +0.026 | 6 of 10 | -0.09 |
| 10:n blend | +0.149 | 8 of 10 | +1.19 |
| backtest only | +0.212 | 9 of 10 | -1.13 |
| forward only | +0.008 | 5 of 9 | +0.17 |
| empirical Bayes on dates | +0.291 | 9 of 9 | +1.12 |

Pool mean realised: -0.34 % per trade. The top-5 columns are the realised mean of the five best-scored gate-passing strategies at each snapshot (each snapshot a different mix; the same fund can appear on several).

Reliability, stored score in quintiles (mean over snapshots; predicted is per 20 sessions, realised is per trade):

| quintile | predicted % | realised % | snapshots |
|---:|---:|---:|---:|
| 1 | -3.46 | -1.03 | 10 |
| 2 | -0.85 | -0.20 | 10 |
| 3 | -0.22 | +0.35 | 10 |
| 4 | +0.16 | -0.40 | 10 |
| 5 | +1.62 | -0.42 | 10 |

## 3b. Dependence on a single shared trade

The largest honest trade in the restated record is KOD entered 2026-09-24 at +163.85 % net, and it is recorded in 3 different funds (a fund per rule that signalled it). Among the 50 best-scored gate-passing funds on 2026-10-09, 14% have a mean at or below zero once their single best trade is removed.

| slot | trades | honest mean % | best trade % | mean without best % | holds the shared big trade |
|---:|---:|---:|---:|---:|---|
| 1 | 3 | +58.64 | +163.85 | +6.04 | yes |
| 2 | 11 | +18.35 | +163.85 | +3.80 | yes |
| 3 | 39 | +0.21 | +14.47 | -0.16 | no |
| 4 | 96 | -0.74 | +8.21 | -0.84 | no |
| 5 | 1 | +163.85 | +163.85 | n/a | yes |

## 4. Did the controlled replacements pick better strategies?

| date | slot | claimed | dropped: later trades | dropped: honest net % | added: later trades | added: honest net % |
|---|---:|---|---:|---:|---:|---:|
| 2026-09-28 | 5 | MACD Pullback predicted to lose (-0.69%  | 2 | -0.54 | 0 | n/a |
| 2026-09-28 | 5 | top strategy (+2.48%, 5 paper trades) wa | 0 | n/a | 0 | n/a |
| 2026-10-05 | 1 | +8.09%/trade vs +0.91%/trade | 0 | n/a | 0 | n/a |
| 2026-10-05 | 3 | +7.56%/trade vs +2.06%/trade | 0 | n/a | 0 | n/a |
| 2026-10-06 | 4 | +6.00%/trade vs +5.52%/trade | 6 | +1.21 | 8 | +1.30 |
| 2026-10-06 | 5 | +6.50%/trade vs +2.01%/trade | 0 | n/a | 0 | n/a |
| 2026-10-09 | 3 | +6.08%/trade vs +0.64%/trade | 0 | n/a | 0 | n/a |
| 2026-10-12 | 4 | +5.89%/trade vs +4.86%/trade | 0 | n/a | 0 | n/a |

1 swaps with outcomes for both sides: added strategy beat the dropped one in 1; mean difference +0.09 points per trade.

Slot releases to date: 13 (ranking swaps 6, ineligible 5, owner 2).

## What could be wrong with this analysis

- 1 to 11 sessions of outcome after each snapshot and one market regime: rank correlations of a few hundredths are noise.
- The outcome is the paper fund's trades; the live slot trades the same rule with a stop plan and ATR sizing, so slot results can differ.
- The restated table leaves out trades exiting on the newest bar (mostly stop-outs), which flatters every predictor equally but not necessarily the same.
- The empirical-Bayes estimator is a candidate replacement evaluated on the same short window it was designed on; it is not adopted and nothing is tuned to it.
- Only funds with a paper run are scored; crypto, pair, option and value funds are outside this calibration.
