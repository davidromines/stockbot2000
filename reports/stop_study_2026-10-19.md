# Stop study — 2026-10-19 (Stage AD3.6)

From the restated forward record (next-open fills; corporate-action trades excluded). Excursions in ATR(14) at entry; negative = against the position.

**Read the win column with care: it counts CLOSED trades only.** After a few weeks, a medium-term family's closed trades are mostly its stop-outs; its winners are still open and are not here. These are not the strategies' win rates, and the loss columns describe the trades that were stopped, not the strategy.

| family | trades | win | winners' MAE p50 | winners' MAE p90 | losers' MFE p50 | configured stop (ATR) | losers beyond p90 | their mean loss |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 11095 | 57% | -0.38 | -1.15 | +0.28 | 4.3 | 29% | -9.21% |
| st_reversal_1d | 1824 | 38% | -0.27 | -0.80 | +0.32 | 2.0 | 52% | -8.10% |
| st_momentum_1d | 1571 | 48% | -0.33 | -0.81 | +0.34 | 2.0 | 54% | -4.93% |
| kf_seasonality | 989 | 41% | -0.27 | -0.72 | +0.27 | 3.0 | 50% | -8.77% |
| st_uptrend_pullback | 863 | 44% | -0.36 | -0.85 | +0.45 | 2.5 | 62% | -8.89% |
| st_reversal_5d | 829 | 37% | -0.37 | -0.92 | +0.29 | 2.5 | 54% | -9.84% |
| st_volume_shock | 787 | 47% | -0.26 | -0.80 | +0.40 | 2.5 | 54% | -7.08% |
| st_stoch_oversold | 694 | 47% | -0.36 | -0.93 | +0.37 | 2.5 | 52% | -3.66% |
| kf_liquidity | 676 | 30% | -0.22 | -0.62 | +0.20 | 3.0 | 52% | -3.73% |
| value_momentum | 564 | 33% | -0.26 | -0.52 | +0.18 | 4.0 | 62% | -4.89% |
| momentum | 476 | 54% | -0.21 | -0.70 | +0.29 | 3.3 | 43% | -9.29% |
| kf_trend | 463 | 5% | -0.46 | -0.83 | +0.42 | 3.0 | 80% | -8.80% |
| volatility_breakout | 461 | 33% | -0.68 | -1.34 | +0.48 | 2.0 | 82% | -13.72% |
| kf_quality | 451 | 28% | -0.35 | -1.31 | +0.26 | 3.0 | 58% | -18.15% |
| kf_reversal | 446 | 41% | -0.36 | -0.98 | +0.44 | 3.0 | 73% | -15.02% |
| macd_cross | 445 | 21% | -0.37 | -1.19 | +0.51 | 2.0 | 56% | -7.70% |
| bollinger_reversion | 445 | 52% | -0.58 | -1.41 | +0.44 | 2.0 | 71% | -2.79% |
| momentum_volume | 408 | 13% | -0.83 | -1.12 | +0.56 | 2.0 | 79% | -11.88% |
| st_bollinger_low | 397 | 49% | -0.32 | -1.05 | +0.46 | 2.5 | 49% | -2.80% |
| rsi_reversion | 389 | 31% | -0.48 | -0.80 | +0.61 | 2.0 | 95% | -7.75% |
| xs_momentum | 373 | 13% | -0.84 | -1.12 | +0.56 | 2.0 | 81% | -12.02% |
| kf_mean_reversion | 313 | 66% | -0.44 | -0.94 | +0.47 | 3.0 | 92% | -14.35% |
| kf_momentum | 307 | 16% | -0.49 | -1.07 | +0.11 | 3.0 | 88% | -18.28% |
| kf_fundamental | 253 | 8% | -0.61 | -1.11 | +0.47 | 3.0 | 95% | -19.32% |
| kf_breakout | 252 | 7% | -0.81 | -1.70 | +0.54 | 2.0 | 36% | -7.75% |
| kf_earnings_surprise | 231 | 24% | -0.47 | -1.67 | +0.44 | 3.0 | 89% | -16.34% |
| kf_low_volatility | 183 | 21% | -0.43 | -1.50 | +0.65 | 3.0 | 95% | -10.72% |
| breakout_52w | 161 | 19% | -0.82 | -1.72 | +1.31 | 2.0 | 85% | -11.40% |
| turn_of_month | 160 | 78% | -0.55 | -0.97 | +0.66 | 2.5 | 56% | -3.59% |
| volatility_contraction | 134 | 33% | -0.96 | -1.75 | +0.26 | 2.0 | 84% | -14.04% |
| quality_momentum | 128 | 12% | -0.54 | -1.02 | +0.91 | 3.5 | 59% | -11.69% |
| kf_factor | 127 | 2% | -0.85 | -1.29 | +0.76 | 3.0 | 94% | -19.00% |
| st_rsi_oversold | 127 | 46% | -0.52 | -0.97 | +0.37 | 2.5 | 76% | -5.39% |
| kf_value | 101 | 22% | -0.61 | -1.29 | +0.56 | 3.0 | 99% | -14.41% |
| kf_hybrid | 94 | 5% | -0.64 | -1.10 | +0.33 | 3.0 | 90% | -16.55% |
| ma_cross | 86 | 17% | -1.01 | -1.91 | +0.39 | 2.0 | 83% | -13.42% |
| relative_strength | 75 | 32% | -0.18 | -0.36 | +0.19 | 2.5 | 92% | -6.45% |
| seasonality_12m | 54 | 0% | n/a | n/a | +0.07 | 3.0 | 0% | n/a |
| ts_momentum | 47 | 4% | -0.03 | -0.03 | +0.26 | 2.5 | 100% | -17.50% |
| earnings_yield | 46 | 52% | -0.41 | -0.63 | +0.26 | 3.0 | 100% | -11.50% |
| analog_top | 46 | 39% | -0.90 | -1.52 | +0.32 | 2.5 | 79% | -5.76% |
| trend_following | 40 | 20% | -0.38 | -0.38 | +0.66 | 3.0 | 100% | -10.56% |
| kf_other | 40 | 15% | -0.43 | -0.89 | +1.09 | 3.0 | 88% | -17.31% |
| fundamental_momentum | 40 | 20% | -0.72 | -0.88 | +0.38 | 3.0 | 88% | -12.90% |
| kf_size | 39 | 0% | n/a | n/a | +0.76 | 3.0 | 0% | n/a |
| low_accruals | 34 | 0% | n/a | n/a | +0.26 | 3.0 | 0% | n/a |
| quality_roa | 30 | 40% | -0.51 | -0.88 | +0.26 | 3.0 | 100% | -23.39% |

Reading: a configured stop wider than the winners' p90 (more negative) leaves losses running that winners never needed; one tighter than the p90 stops out winners. Losers' MFE shows what a trailing stop could have kept. The record is weeks long and short-hold dominated: test any change in a backtest first (exit_sweep.py).
