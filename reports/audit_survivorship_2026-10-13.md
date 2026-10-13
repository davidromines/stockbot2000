# Phase D1: dependence on the synthetic dead companies

Computed 2026-10-13 06:16 UTC, read-only, from `survivorship_backtests` (generator `synthetic_v5#3674+fundamentals+volume`, factory window 2016-19, 5,000-trade cap per run). Per-trade figures are net, costs deducted.

## 1. What the three treatments do to the ranked set

1,221 strategies with all three modes. Typical strategy: 37% of its trades are in synthetic companies (90th percentile 54%).

| treatment | strategies positive | share |
|---|---:|---:|
| survivors only | 1,150 | 94% |
| with synthetic dead companies (used by the ranking) | 1,078 | 88% |
| worst case: every unpriced death a total loss | 670 | 55% |

- Mean per-trade change: survivors-only to as_is -0.33 points; as_is to worst case -0.74 points.
- Verdict changes: 83 strategies are positive survivors-only and negative as_is; **409 are positive as_is and non-positive in the worst case** (33% of the set) - their verdict rests on the unidentifiable assumption.
- Ordering: rank correlation as_is vs worst case +0.67; survivors-only vs as_is +0.84. Top-50 overlap as_is vs worst case 30/50; survivors-only vs as_is 27/50.
- Of the 50 best-scored strategies in the latest ranking snapshot (40 with survivorship data): 14 are non-positive in the worst case, 0 non-positive as_is.

## 2. By family (medians across the family's strategies)

| family | strategies | survivors only % | as_is % | worst case % | positive as_is | positive worst case | synthetic share of trades |
|---|---:|---:|---:|---:|---:|---:|---:|
| kf_quality | 114 | +1.09 | +0.79 | +0.19 | 92% | 61% | 34% |
| kf_momentum | 109 | +1.05 | +0.73 | -0.63 | 92% | 19% | 40% |
| kf_fundamental | 91 | +1.06 | +0.67 | -0.20 | 86% | 35% | 50% |
| kf_earnings_surprise | 88 | +1.19 | +0.98 | +0.66 | 100% | 100% | 19% |
| kf_factor | 60 | +1.01 | +0.77 | +0.18 | 92% | 58% | 40% |
| kf_low_volatility | 58 | +0.92 | +0.72 | -0.00 | 100% | 50% | 39% |
| kf_mean_reversion | 57 | +1.00 | +0.60 | +0.13 | 96% | 72% | 42% |
| kf_hybrid | 56 | +1.50 | +1.15 | +0.32 | 95% | 73% | 35% |
| kf_reversal | 51 | +1.04 | +0.52 | -0.12 | 75% | 43% | 50% |
| kf_value | 51 | +1.52 | +0.82 | +0.41 | 88% | 59% | 41% |
| kf_seasonality | 48 | +1.10 | +0.82 | +0.14 | 83% | 56% | 39% |
| kf_trend | 43 | +0.75 | +0.30 | -0.30 | 79% | 37% | 38% |
| kf_breakout | 26 | +0.49 | +0.32 | -0.79 | 96% | 27% | 35% |
| kf_size | 15 | +1.54 | +0.95 | -0.14 | 87% | 47% | 0% |
| kf_liquidity | 10 | +1.13 | -1.00 | -2.45 | 10% | 0% | 69% |
| relative_strength | 10 | +0.68 | +0.78 | -1.41 | 100% | 0% | 36% |

The seven forward-positive families plus turn_of_month (`lab_search` funds are paper-only and have no survivorship backtest):

| family | strategies with data | as_is % | worst case % | positive in worst case |
|---|---:|---:|---:|---:|
| lab_search | 0 | n/a | n/a | n/a (not backtested: scored on paper only, or no template) |
| momentum | 2 | +1.44 | +0.86 | 50% |
| kf_seasonality | 48 | +0.82 | +0.14 | 56% |
| st_uptrend_pullback | 6 | +0.18 | +0.04 | 67% |
| bollinger_reversion | 10 | +0.31 | +0.17 | 80% |
| kf_mean_reversion | 57 | +0.60 | +0.13 | 72% |
| st_momentum_1d | 4 | -0.21 | -0.33 | 0% |
| turn_of_month | 0 | n/a | n/a | n/a (not backtested: scored on paper only, or no template) |

## 3. The five slot holders

| slot | strategy | survivors only % | as_is % | worst case % | synthetic share |
|---:|---|---:|---:|---:|---:|
| 1 | paper:61b078a7d01a | n/a | n/a | n/a | n/a |
| 2 | paper:cf4dcce2e2e4 | n/a | n/a | n/a | n/a |
| 3 | fx_st_uptrend_pullback_57ba477365 | +0.32 | +0.46 | +0.16 | 59% |
| 4 | fx_st_reversal_1d_62dc747852 | +0.00 | +0.05 | -0.09 | 58% |
| 5 | paper:4ee3d520751b | n/a | n/a | n/a | n/a |

Holders without numbers are Lab-search funds, which are scored on paper evidence only and have no survivorship backtest.

## 4. Dependence on the generator configuration

Generators tried on the same strategies: synthetic_v4#6974 (260 strategies), synthetic_v5#6784 (276 strategies), synthetic_v5#3674 (284 strategies), synthetic_v5#3674+fundamentals+volume (1327 strategies). 288 strategies have as_is results under two or more: median spread between their lowest and highest per-trade figure +0.31 points, 90th percentile +0.82; **61 (21%) change sign** between configurations; rank correlation first vs latest configuration +0.86. Configurations differ by more than the generator (later ones add dead companies' fundamentals and volume, so fundamental and liquidity strategies can trade them), so this is an upper bound on generator-only sensitivity.

## 5. What the real data can and cannot say

- Twin test (pre-registered, 70 real failures against synthetic twins, 252,069 real vs 258,969 twin trades): mean per trade real -0.45 % vs twin -0.38 %, verdict PASS. It was run after five generator configurations had been looked at on the same 70 companies, so the pass is not an independent confirmation.
- Real dead-company prices exist for about 418 of ~7,500 delisted common stocks, and the 70-80 failures used are the ones that survived into public price histories: a clean acquisition keeps its history and a bankruptcy often does not. The synthetic share of the traded universe peaks near 52 % (2016).
- **Identifiable:** the survivors-only result, the sign and size of the gap to as_is under the stated assumptions, and the worst-case floor. **Not identifiable from available data:** the true return distribution of the unpriced dead companies, hence the true value between the as_is and worst-case columns.

## 6. Would paid point-in-time delisted data change the decision?

It would remove the assumption that separates the as_is and worst-case columns, which is the deciding assumption for 409 of 1,221 strategies (33%) and for 14 of the 40 best-scored strategies that have survivorship data (positive as_is, non-positive in the worst case). But no strategy has reached 20 independent forward entry dates, and every candidate fails on forward evidence long before survivorship is the binding constraint; the data would sharpen the backtest prior, which the audit has found to carry little ranking information. Expected benefit to research integrity: real but second-order now. **Recommendation: do not buy yet.** Revisit if a family passes the prospective test (A6) and its verdict then depends on the survivorship assumption; at that point the data answers a decision that matters.

## What could be wrong with this analysis

- Per-trade figures come from one simulator on one 2016-19 window with a 5,000-trade cap; the synthetic share and gaps differ by window.
- Strategies are compared across generators only where they were re-run; later configurations also changed what the strategy could trade.
- The worst case (every unpriced death total loss) is deliberately extreme; reality is between the columns, and the twin test's pass is not independent.
- Family medians weight each strategy equally, so a family with many near-duplicate variants counts many times.
