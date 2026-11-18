# Research integrity report

Generated 2026-11-12T08:08:49+00:00 from the live database. Every figure is
queried, not remembered.

---

## What Stockbot2000 can currently prove

**Very little, and that is the honest headline.**

It can prove things about *itself*: that its simulator fills at the next
open, that its null matches its simulator's fill convention, that its
risk engine rejects unmeasured values, that eleven historical measurement
bugs do not recur. Those are real and they are verified by a regression
suite that has been shown to fail when a defect is reintroduced.

It cannot prove that any strategy makes money.

## What it cannot prove

| Claim | Status |
|---|---|
| Any strategy has a tradeable edge | **unproven** |
| The classifier's AUC 0.63 converts to profit | **refuted** — gross negative under next-open fills |
| ETF switching beats holding | **refuted** — loses to buy-and-hold on every index pair |
| Published technical rules beat the null | **refuted** — 0 of 20 |
| Fundamental screens beat the index | **refuted** — best is 7 of 15 windows |
| Crash-buying works | **refuted** — 5 of 5 forward funds negative |

## Biases that remain

**Survivorship, measured per date rather than estimated:**

| date | knowable | priced | coverage |
|---|---:|---:|---:|
| 2008-06-30 | 3,000 | 679 | **22.6%** |
| 2012-06-29 | 2,487 | 831 | 33.4% |
| 2016-06-30 | 2,490 | 1,035 | 41.6% |
| 2020-06-30 | 2,568 | 1,436 | 55.9% |
| 2024-06-28 | 2,133 | 1,786 | **83.7%** |

Of 9,464 delisted listings on record, 553 have price data. The rest are invisible to every backtest here.

The monotonic climb toward the present is the signature of the bias:
survivors keep their history, the dead do not.

**Seed contamination.** Of the validation survivors classified so far,
**423 of 950 (44.5%)** carry a
hand-written seed's discriminating constant and are therefore not
independent discoveries.

## How many research trials have occurred

| | |
|---|---:|
| evaluations | 1,039,345 |
| promotion decisions | 10,619 |
| backtest runs | 1 |
| **total trials** | **1,049,983** |
| unique structures | 126,652 |
| effective (estimate) | 364,668 |

**The best of pure noise at this count scores about 5.27 standard errors.** A survivor must clear that, not
merely be positive. No survivor currently does.

### What random strategies actually look like here

That bar is theoretical — it assumes the trial statistics are standard normal, which Sharpes computed off a few hundred trades
are not. So the same question is also asked empirically, by running never-evolved random genomes through the identical panel, cost
model, null surface and gate a real candidate faces.

| | |
|---|---:|
| random genomes measured | 1,225 |
| passed the validation gate | 3 (0.2%) |
| best Sharpe achieved by noise | **1.14** |
| best P&L achieved by noise | **$11,145** |
| 95th percentile Sharpe | 0.19 |

The best of 1,225 strategies known to be worthless made $11,145 in this simulator. That figure is the reason
no backtest number in this document should be read as a finding on its own.

Search mode is **FROZEN**.

## What is in forward testing, and for how long

2925 strategy funds and 5 pair funds, 85,489 closed paper trades.

| fund | family | started | return |
|---|---|---|---:|
| Lab 94f5c5: ((rank(roc_10) > 0.4248 and atr_14 > 0.5) and rs | lab_search | 2026-09-24 | +18.68% |
| Lab f6960c: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +17.95% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-29 | +16.68% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-29 | +16.68% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-29 | +16.41% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-25 | +16.26% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-09-25 | +16.26% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-25 | +15.95% |
| Lab 11d6be: ((rank(roc_10) > 0.5295 and price_above_sma200 < | lab_search | 2026-09-24 | +15.56% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-29 | +14.82% |
| Lab e0d647: ((rank(roc_10) > 0.7 or crosses_below(atr_14, 0. | lab_search | 2026-09-24 | +13.88% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +13.67% |
| Lab 8747c2: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +13.22% |
| Lab ee213f: ((rank(roc_10) > 0.5459 and price_above_sma200 < | lab_search | 2026-09-24 | +13.00% |
| Lab ce5b8a: ((rank(macd) > 0.7 and price_above_sma200 < 0.5) | lab_search | 2026-09-24 | +12.66% |
| rsi_oversold · reproduction · universe large_cap | kf_mean_reversion | 2026-10-02 | +12.66% |
| Lab 849cdc: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +12.63% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | +12.33% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +12.33% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +12.33% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +12.33% |
| rsi_oversold · reproduction · exit 3.0 | kf_mean_reversion | 2026-10-02 | +12.25% |
| rsi_oversold · reproduction · universe liquid | kf_mean_reversion | 2026-10-02 | +12.25% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +12.09% |
| Lab c3ad60: ((rank(roc_10) > 0.7 or crosses_above(price_abov | lab_search | 2026-09-24 | +11.80% |
| Lab 418761: ((rank(adx_14) > 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | +11.69% |
| Lab 992c0b: ((rank(roc_10) > 0.3247 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +11.49% |
| Rising 200 · Stop 2.5 | momentum | 2026-09-04 | +11.24% |
| rsi_oversold · reproduction · stop 1.0 | kf_mean_reversion | 2026-10-02 | +11.04% |
| Lab f41676: ((rank(roc_10) > 0.5009 and atr_14 > 0.5) and rs | lab_search | 2026-09-24 | +10.67% |
| Lab 5e13ad: ((rank(roc_10) > 0.7 and vol_ratio > 0.5) and rs | lab_search | 2026-09-24 | +10.54% |
| Asset growth effect · reproduction · stop 1.0 | kf_fundamental | 2026-09-25 | +10.47% |
| Lab b64eeb: ((rank(roc_10) > 0.7 and atr_14 > 0.5) and rsi_1 | lab_search | 2026-09-24 | +10.45% |
| Lab 6d874e: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +10.31% |
| rsi_oversold · reproduction · holding_period 2.0 | kf_mean_reversion | 2026-10-02 | +10.09% |
| rsi_oversold · reproduction · stop -1.0 | kf_mean_reversion | 2026-10-02 | +10.09% |
| Lab 50504c: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +9.96% |
| Lab 67f06d: ((rank(roc_10) > 0.7 and vol_ratio > 0.5) and rs | lab_search | 2026-09-24 | +9.94% |
| Lab 599684: ((rank(roc_10) > 0.6246 and atr_14 > 0.5) and rs | lab_search | 2026-09-24 | +9.92% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +9.88% |
| Lab ceef9a: ((rank(pct_of_52w_high) > 0.6337 and price_above | lab_search | 2026-09-24 | +9.70% |
| Lab 9ca03b: ((rank(stoch_d) > 0.7 and vol_ratio > 0.5) and r | lab_search | 2026-09-24 | +9.55% |
| bollinger_reversion · reproduction · holding_period 2.0 | kf_mean_reversion | 2026-10-05 | +9.46% |
| Lab c6d07c: ((rank(obv_rising) > 0.4238 and drawdown_200 > 0 | lab_search | 2026-09-24 | +8.86% |
| Asset growth effect · reproduction · stop -1.0 | kf_fundamental | 2026-09-25 | +8.81% |
| kf_hybrid v2 (longer_hold) | kf_hybrid | 2026-09-29 | +8.75% |
| Analog Top hold=20 q=0.95 stop=2.5 | analog_top | 2026-09-24 | +8.72% |
| Lab dbc90f: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +8.67% |
| Lab f1392a: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +8.49% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +8.45% |
| Lab 7a74b7: ((rank(dollar_volume_20) > 0.7 and price_above_s | lab_search | 2026-09-24 | +8.42% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +8.36% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +8.36% |
| Lab a33230: ((rank(roc_10) > 0.678 and price_above_sma200 <  | lab_search | 2026-09-24 | +8.33% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-10-08 | +8.27% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-09-25 | +8.25% |
| Lab a5f26c: ((rank(roc_10) > 0.5226 and price_above_sma200 < | lab_search | 2026-09-24 | +8.12% |
| Asset growth effect · reproduction · exit 3.0 | kf_fundamental | 2026-09-25 | +8.11% |
| Asset growth effect · reproduction · holding_period 0.5 | kf_fundamental | 2026-09-25 | +8.11% |
| kf_value v2 (longer_hold) | kf_value | 2026-09-25 | +8.11% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-10-14 | +8.01% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-10-14 | +8.01% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction | kf_value | 2026-09-25 | +7.98% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-11-02 | +7.94% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +7.92% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +7.92% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +7.92% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +7.92% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +7.92% |
| Defensive · reproduction | kf_low_volatility | 2026-09-25 | +7.88% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-29 | +7.79% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-10-14 | +7.77% |
| An Investment-Based Investigation of Mutual Fund Performance | kf_factor | 2026-09-30 | +7.68% |
| Lab 234240: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +7.57% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-10-14 | +7.53% |
| Value book to market factor · reproduction | kf_value | 2026-09-25 | +7.53% |
| Fundamental Momentum hold=40 n=63 stop=3 | fundamental_momentum | 2026-09-24 | +7.50% |
| Fundamental Momentum hold=60 n=63 stop=3 | fundamental_momentum | 2026-09-24 | +7.50% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +7.46% |
| Lab 87bcf2: ((rank(roc_10) > 0.6438 and vol_ratio > 0.5) and | lab_search | 2026-09-24 | +7.42% |
| Lab 36c09a: ((rank(roc_10) > 0.7667 and vol_ratio > 0.5) and | lab_search | 2026-09-24 | +7.38% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +7.32% |
| Lab 181cc9: ((rank(roc_10) > 0.7 and atr_14 > 0.5) and rsi_1 | lab_search | 2026-09-24 | +7.22% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | +7.21% |
| MACD Pullback | momentum | 2026-09-11 | +7.16% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | +7.04% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +7.02% |
| The Value of Low Volatility · reproduction · lookback 0.5 | kf_low_volatility | 2026-09-30 | +6.95% |
| Defensive · reproduction · universe liquid | kf_low_volatility | 2026-10-01 | +6.88% |
| Analog Stop hold=20 q=0.95 stop=3 | analog_stop | 2026-09-25 | +6.82% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +6.81% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +6.81% |
| bollinger_reversion · reproduction · universe large_cap | kf_mean_reversion | 2026-10-05 | +6.75% |
| Lab 68d491: ((rank(rsi_14) > 0.7 and price_above_sma50 < 0.5 | lab_search | 2026-09-24 | +6.65% |
| The Magic Formula: Value, Profitability, and the Cross Secti | kf_hybrid | 2026-09-25 | +6.64% |
| Lab 82731d: ((rank(macd_hist) > 0.438 and pct_off_52w_low >  | lab_search | 2026-09-24 | +6.63% |
| macd_trend_confirmed · reproduction | kf_trend | 2026-09-25 | +6.62% |
| Lab fdb493: ((rank(roc_10) > 0.7 and atr_14 > 0.5) and rsi_1 | lab_search | 2026-09-24 | +6.61% |
| Product market competition, R&D investment, and stock return | kf_fundamental | 2026-09-25 | +6.60% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | +6.57% |
| Lab 58897c: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +6.57% |
| The Value of Low Volatility · reproduction · lookback 1.5 | kf_low_volatility | 2026-09-30 | +6.53% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | +6.47% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-09-29 | +6.44% |
| Agency Theory of Overvalued Equity as an · reproduction · un | kf_fundamental | 2026-09-28 | +6.40% |
| Asset growth effect · reproduction · universe large_cap | kf_fundamental | 2026-09-25 | +6.35% |
| Value Quality hold=60 q=0.7 stop=3 | value_quality | 2026-09-24 | +6.30% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +6.22% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | +6.18% |
| The Value of Low Volatility · reproduction · holding_period  | kf_low_volatility | 2026-09-30 | +6.15% |
| Lab 768ac5: ((rank(roc_10) > 0.484 and golden_cross < 0.5) a | lab_search | 2026-09-24 | +6.10% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-10-08 | +6.10% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-10-08 | +6.10% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +6.05% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +6.01% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +6.01% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +6.01% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +6.01% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +6.00% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +5.99% |
| macd_trend_confirmed · reproduction · exit 3.0 | kf_trend | 2026-10-19 | +5.95% |
| macd_trend_confirmed · reproduction · holding_period 0.5 | kf_trend | 2026-10-19 | +5.95% |
| macd_trend_confirmed · reproduction · holding_period 2.0 | kf_trend | 2026-10-19 | +5.95% |
| macd_trend_confirmed · reproduction · stop -1.0 | kf_trend | 2026-10-19 | +5.95% |
| macd_trend_confirmed · reproduction · stop 1.0 | kf_trend | 2026-10-19 | +5.95% |
| macd_trend_confirmed · reproduction · universe liquid | kf_trend | 2026-10-19 | +5.95% |
| bollinger_reversion · reproduction · stop 1.0 | kf_mean_reversion | 2026-10-05 | +5.88% |
| Value Quality hold=40 q=0.8 stop=3 | value_quality | 2026-09-24 | +5.85% |
| Value Quality hold=60 q=0.8 stop=3 | value_quality | 2026-09-24 | +5.85% |
| Lab 18bbaf: ((rank(price_above_sma50) > 0.4634 or crosses_be | lab_search | 2026-09-24 | +5.83% |
| Lab cfb634: ((rank(roc_10) > 0.7 and atr_14 > 0.4193) and rs | lab_search | 2026-09-24 | +5.83% |
| Lab 0328d1: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | +5.83% |
| macd_trend_confirmed · reproduction · universe large_cap | kf_trend | 2026-10-19 | +5.75% |
| kf_fundamental v1 | kf_fundamental | 2026-09-24 | +5.72% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +5.72% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +5.72% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +5.72% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +5.70% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-10-15 | +5.69% |
| Lab d47b08: ((rank(stoch_d) > 0.7 and price_above_sma200 < 0 | lab_search | 2026-09-24 | +5.69% |
| Buyback hold=40 iss=-0.03 stop=3 | buyback | 2026-09-24 | +5.69% |
| Buyback hold=60 iss=-0.03 stop=3 | buyback | 2026-09-24 | +5.69% |
| buyback v2 (longer_hold) | buyback | 2026-09-24 | +5.69% |
| buyback v2 (longer_hold) | buyback | 2026-09-24 | +5.69% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +5.59% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +5.59% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +5.53% |
| Standardized Unexpected Earnings · reproduction · holding_pe | kf_earnings_surprise | 2026-09-25 | +5.53% |
| Lab 3e7597: ((rank(roc_10) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +5.45% |
| Buffett’s Alpha · reproduction · holding_period 0.5 | kf_quality | 2026-10-20 | +5.43% |
| Lab 335d14: ((rank(roc_10) > 0.7 or crosses_above(macd, 0.5) | lab_search | 2026-09-24 | +5.40% |
| Factoring Profitability · reproduction · holding_period 0.5 | kf_quality | 2026-09-30 | +5.40% |
| bollinger_reversion · reproduction · exit 3.0 | kf_mean_reversion | 2026-10-05 | +5.35% |
| Lab c66329: ((rank(roc_10) > 0.7 and roc_10 < 0.5) and rsi_1 | lab_search | 2026-09-24 | +5.34% |
| DO MOVING AVERAGE RULES MAKE PROFITS? A STUDY USING THE MADR | kf_trend | 2026-09-25 | +5.31% |
| Trading Volume Effects of Moving Average Heuristics · reprod | kf_trend | 2026-09-25 | +5.31% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-09-28 | +5.31% |
| kf_liquidity v1 | kf_liquidity | 2026-09-24 | +5.29% |
| Value Quality Momentum hold=20 q=0.7 stop=3 | value_quality_momentum | 2026-09-24 | +5.28% |
| Lab 78693d: ((rank(roc_10) > 0.4603 and golden_cross < 0.647 | lab_search | 2026-09-24 | +5.26% |
| Buyback hold=40 iss=-0.03 stop=5 | buyback | 2026-09-24 | +5.22% |
| Buyback hold=60 iss=-0.03 stop=5 | buyback | 2026-09-24 | +5.22% |
| buyback v2 (longer_hold) | buyback | 2026-09-24 | +5.22% |
| buyback v2 (longer_hold) | buyback | 2026-09-24 | +5.22% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | +5.22% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-10-15 | +5.16% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +5.16% |
| Analog Top hold=10 q=0.95 stop=2.5 | analog_top | 2026-09-24 | +5.15% |
| bollinger_breakout · reproduction · universe large_cap | kf_breakout | 2026-10-01 | +5.12% |
| Factor investing: get your exposures right! · reproduction | kf_factor | 2026-09-25 | +5.11% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-09-25 | +5.11% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | +5.10% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | +5.10% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | +5.10% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | +5.10% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | +5.10% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | +5.08% |
| Lab 0ec62b: ((rank(bb_pct) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +5.06% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-29 | +4.99% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +4.96% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-10-15 | +4.96% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-10-15 | +4.96% |
| Multi Signal hold=20 q=0.95 stop=4 | multi_signal | 2026-09-25 | +4.91% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-10-15 | +4.88% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-09-25 | +4.82% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-09-25 | +4.82% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-12 | +4.77% |
| rsi_reversion v3 (trend_filter) | rsi_reversion | 2026-09-25 | +4.74% |
| Earnings Yield hold=40 q=0.9 stop=5 | earnings_yield | 2026-09-24 | +4.71% |
| Earnings Yield hold=60 q=0.9 stop=5 | earnings_yield | 2026-09-24 | +4.71% |
| Agency Theory of Overvalued Equity as an · reproduction · st | kf_fundamental | 2026-09-28 | +4.70% |
| Multi Signal hold=20 q=0.95 stop=3 | multi_signal | 2026-09-25 | +4.68% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-10-15 | +4.63% |
| Defensive · reproduction · exit 3.0 | kf_low_volatility | 2026-10-01 | +4.63% |
| Defensive · reproduction · holding_period 0.5 | kf_low_volatility | 2026-10-01 | +4.63% |
| Defensive · reproduction · holding_period 2.0 | kf_low_volatility | 2026-10-01 | +4.63% |
| Fundamental Momentum hold=40 n=63 stop=5 | fundamental_momentum | 2026-09-24 | +4.61% |
| Fundamental Momentum hold=60 n=63 stop=5 | fundamental_momentum | 2026-09-24 | +4.61% |
| Low Investment hold=40 q=0.1 stop=3 | low_investment | 2026-09-24 | +4.61% |
| Low Investment hold=60 q=0.1 stop=3 | low_investment | 2026-09-24 | +4.61% |
| bollinger_reversion · reproduction · universe liquid | kf_mean_reversion | 2026-10-05 | +4.57% |
| Price Earnings Anomaly · reproduction | kf_value | 2026-09-25 | +4.57% |
| Lab fe79c0: not((rank(willr_14) < 0.805 or (crosses_above(cc | lab_search | 2026-09-24 | +4.55% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-10-15 | +4.54% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +4.54% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-30 | +4.54% |
| Value + quality · reproduction · stop -1.0 | kf_quality | 2026-10-22 | +4.51% |
| Lab d41f47: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | +4.51% |
| Lab 27540c: ((rank(stoch_k) > 0.7 and atr_14 > 0.3281) and r | lab_search | 2026-09-24 | +4.50% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-10-21 | +4.48% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-10-21 | +4.48% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-10-21 | +4.48% |
| Lab 2cc415: ((rank(rsi_14) > 0.7 and price_above_sma50 < 0.5 | lab_search | 2026-09-24 | +4.47% |
| Lab 0dd70b: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | +4.46% |
| fundamental_price_momentum v1 | fundamental_price_momentum | 2026-09-22 | +4.45% |
| Defensive · reproduction · stop 1.0 | kf_low_volatility | 2026-10-01 | +4.40% |
| Earnings, Business Cycle and Stock Returns · reproduction | kf_earnings_surprise | 2026-09-25 | +4.39% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-30 | +4.37% |
| Value Quality Momentum hold=40 q=0.7 stop=3 | value_quality_momentum | 2026-09-24 | +4.36% |
| Value Quality hold=40 q=0.8 stop=5 | value_quality | 2026-09-24 | +4.33% |
| Value Quality hold=60 q=0.8 stop=5 | value_quality | 2026-09-24 | +4.33% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-11-03 | +4.33% |
| Asset growth effect · reproduction · universe liquid | kf_fundamental | 2026-09-25 | +4.31% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-10-08 | +4.30% |
| Value + quality · reproduction · stop 1.0 | kf_quality | 2026-10-22 | +4.30% |
| Lab 127fc3: ((rank(pct_of_52w_high) > 0.6582 and price_above | lab_search | 2026-09-24 | +4.26% |
| Lab b6655c: ((rank(price_above_sma50) > 0.427 or roc_10 > 0. | lab_search | 2026-09-24 | +4.21% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | +4.20% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-10-15 | +4.20% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-10-15 | +4.20% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-10-15 | +4.20% |
| Lab a6ebf0: ((rank(pct_of_52w_high) > 0.7 and price_above_sm | lab_search | 2026-09-24 | +4.19% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-09-25 | +4.18% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-10-15 | +4.16% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-10-15 | +4.16% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-10-15 | +4.16% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +4.16% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +4.16% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +4.16% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | +4.15% |
| Lab 4a391c: crosses_above(pct_change(golden_cross, 50), bb_p | lab_search | 2026-09-24 | +4.14% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-13 | +4.13% |
| Rsi Reversion hold=10 rsi=30 stop=2 | rsi_reversion | 2026-09-25 | +4.12% |
| MACD Pullback · exit tp=- trail=- | momentum | 2026-09-23 | +4.12% |
| Lab 759c4e: ((rank(obv_rising) > 0.3368 and pct_off_52w_low  | lab_search | 2026-09-24 | +4.12% |
| rsi_oversold · reproduction · holding_period 0.5 | kf_mean_reversion | 2026-10-02 | +4.10% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-10-13 | +4.09% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-10-13 | +4.09% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-10-13 | +4.09% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-30 | +4.08% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-30 | +4.08% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-30 | +4.08% |
| Low Investment hold=40 q=0.1 stop=5 | low_investment | 2026-09-24 | +4.06% |
| Low Investment hold=60 q=0.1 stop=5 | low_investment | 2026-09-24 | +4.06% |
| Lab 30da7c: ((rank(bb_pct) > 0.6915 and atr_14 > 0.6782) and | lab_search | 2026-09-24 | +4.05% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-10-21 | +4.04% |
| Lab 6a764a: ((rank(pct_of_52w_high) > 0.6932 and price_above | lab_search | 2026-09-24 | +4.03% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | +4.02% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | +4.01% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | +4.01% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | +4.01% |
| kf_earnings_surprise v1 | kf_earnings_surprise | 2026-09-24 | +4.01% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +3.97% |
| Lab 096254: ((rank(pct_of_52w_high) > 0.7 and price_above_sm | lab_search | 2026-09-24 | +3.97% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-09-28 | +3.96% |
| Value + quality · reproduction · exit 3.0 | kf_quality | 2026-10-22 | +3.94% |
| Value + quality · reproduction · holding_period 0.5 | kf_quality | 2026-10-22 | +3.94% |
| Value + quality · reproduction · universe liquid | kf_quality | 2026-10-22 | +3.94% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +3.92% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +3.92% |
| Lab 58438d: ((rank(bb_pct) > 0.7084 and atr_14 > 0.4989) and | lab_search | 2026-09-24 | +3.91% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | +3.89% |
| Lab 51db4a: not(((chaikin_osc > -1.16441e+06 or willr_14 > - | lab_search | 2026-09-24 | +3.88% |
| Agency Theory of Overvalued Equity as an · reproduction | kf_fundamental | 2026-09-25 | +3.87% |
| Agency Theory of Overvalued Equity as an · reproduction · ex | kf_fundamental | 2026-09-28 | +3.87% |
| Agency Theory of Overvalued Equity as an · reproduction · ho | kf_fundamental | 2026-09-28 | +3.87% |
| Agency Theory of Overvalued Equity as an · reproduction · un | kf_fundamental | 2026-09-28 | +3.87% |
| Fundamental momentum · reproduction · universe large_cap | kf_earnings_surprise | 2026-10-16 | +3.83% |
| Post-earnings announcement drift · reproduction · universe l | kf_earnings_surprise | 2026-10-16 | +3.83% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-10-21 | +3.83% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-10-15 | +3.81% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | +3.80% |
| Lab bc1f23: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | +3.79% |
| Earnings Yield hold=40 q=0.9 stop=3 | earnings_yield | 2026-09-24 | +3.77% |
| Earnings Yield hold=60 q=0.9 stop=3 | earnings_yield | 2026-09-24 | +3.77% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-10-15 | +3.77% |
| VALUE PREMIUMS AND THE JANUARY EFFECT: INTERNATIONAL EVIDENC | kf_seasonality | 2026-10-15 | +3.77% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +3.75% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | +3.73% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | +3.73% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | +3.73% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-09-25 | +3.73% |
| kf_earnings_surprise v1 | kf_earnings_surprise | 2026-09-24 | +3.73% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +3.72% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +3.72% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +3.67% |
| Lab 6a5727: ((rank(roc_10) > 0.561 and price_above_sma200 <  | lab_search | 2026-09-24 | +3.59% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-10-15 | +3.58% |
| Analog Top hold=20 q=0.9 stop=2.5 | analog_top | 2026-09-24 | +3.57% |
| Lab 757dd5: ((rank(rsi_14) > 0.7 and price_above_sma50 < 0.5 | lab_search | 2026-09-24 | +3.55% |
| Payday Anomaly · reproduction | kf_seasonality | 2026-09-25 | +3.55% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | +3.53% |
| Lab b1784b: ((rank(pct_of_52w_high) > 0.7 and obv_rising < 0 | lab_search | 2026-09-24 | +3.52% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-09-25 | +3.52% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-09-25 | +3.52% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +3.48% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +3.45% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | +3.44% |
| Buffett’s Alpha · reproduction · stop -1.0 | kf_quality | 2026-10-20 | +3.43% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +3.41% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +3.41% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-10-23 | +3.40% |
| Value Quality Momentum hold=40 q=0.6 stop=3 | value_quality_momentum | 2026-09-24 | +3.38% |
| Value Quality Momentum hold=40 q=0.7 stop=4 | value_quality_momentum | 2026-09-24 | +3.37% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-10-21 | +3.35% |
| fcf_to_price v1 | fcf_to_price | 2026-09-24 | +3.30% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +3.28% |
| Factoring Profitability · reproduction · stop -1.0 | kf_quality | 2026-09-30 | +3.27% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +3.19% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +3.19% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +3.19% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | +3.19% |
| Value Quality Momentum hold=20 q=0.7 stop=4 | value_quality_momentum | 2026-09-24 | +3.16% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +3.14% |
| quality_value · reproduction | kf_quality | 2026-09-25 | +3.14% |
| Multi Signal hold=20 q=0.9 stop=4 | multi_signal | 2026-09-25 | +3.14% |
| Book-to-Market Value Anomaly · reproduction · stop 1.0 | kf_value | 2026-09-25 | +3.13% |
| Lab 6bef5d: ((rank(roc_10) > 0.2336 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +3.13% |
| Deflating Profitability · reproduction | kf_quality | 2026-09-25 | +3.13% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +3.13% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-09-25 | +3.13% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-25 | +3.13% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-09-25 | +3.13% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +3.12% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +3.12% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +3.12% |
| bollinger_reversion · reproduction · stop -1.0 | kf_mean_reversion | 2026-10-05 | +3.11% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +3.10% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +3.10% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +3.10% |
| kf_value v2 (longer_hold) | kf_value | 2026-10-02 | +3.09% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-10-13 | +3.08% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-09-25 | +3.07% |
| rsi_oversold_uptrend · reproduction | kf_mean_reversion | 2026-09-25 | +3.06% |
| Lab 114a22: not((rank(stoch_k) < 0.6134 or (crosses_below(cc | lab_search | 2026-09-24 | +3.05% |
| Factoring Profitability · reproduction | kf_quality | 2026-09-25 | +3.03% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +3.03% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +3.03% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +3.03% |
| multi_signal v1 | multi_signal | 2026-09-24 | +3.02% |
| Lab 43c98e: ((rank(golden_cross) > 0.7 and price_above_sma20 | lab_search | 2026-09-24 | +3.00% |
| Lab 23d03e: (rsi_14 < 33.7551 and pct_off_52w_low > 0.3877) | lab_search | 2026-09-24 | +2.99% |
| Lab 17cb9e: ((rank(pct_off_52w_low) > 0.9258 and atr_14 > 0. | lab_search | 2026-09-24 | +2.98% |
| Value Quality hold=60 q=0.7 stop=5 | value_quality | 2026-09-24 | +2.96% |
| kf_low_volatility v2 (longer_hold) | kf_low_volatility | 2026-11-06 | +2.94% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +2.93% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +2.87% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +2.87% |
| Lab 482b66: (((log_dollar_volume > 7.229 and chaikin_osc < - | lab_search | 2026-09-24 | +2.87% |
| Lab aab714: ((rank(pct_of_52w_high) > 0.7 and price_above_sm | lab_search | 2026-09-24 | +2.87% |
| Value + quality · reproduction · universe large_cap | kf_quality | 2026-10-22 | +2.86% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-10-14 | +2.85% |
| trend_following_adx · reproduction · exit 3.0 | kf_trend | 2026-10-19 | +2.84% |
| trend_following_adx · reproduction · holding_period 0.5 | kf_trend | 2026-10-19 | +2.84% |
| trend_following_adx · reproduction · holding_period 2.0 | kf_trend | 2026-10-19 | +2.84% |
| trend_following_adx · reproduction · universe liquid | kf_trend | 2026-10-19 | +2.84% |
| Factoring Profitability · reproduction · exit 3.0 | kf_quality | 2026-09-30 | +2.84% |
| Factoring Profitability · reproduction · universe large_cap | kf_quality | 2026-09-30 | +2.84% |
| Factoring Profitability · reproduction · universe liquid | kf_quality | 2026-09-30 | +2.84% |
| Defensive · reproduction · stop -1.0 | kf_low_volatility | 2026-10-01 | +2.82% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +2.82% |
| kf_mean_reversion v2 (longer_hold) | kf_mean_reversion | 2026-10-06 | +2.82% |
| Value + momentum · reproduction · lookback 0.5 | kf_hybrid | 2026-10-01 | +2.79% |
| Lab d31437: ((rank(bb_pct) > 0.4672 and bb_pct < 0.4846) and | lab_search | 2026-09-24 | +2.78% |
| Lab 64fab4: ((rank(bb_pct) > 0.5461 and chaikin_osc < 0.4734 | lab_search | 2026-09-24 | +2.77% |
| Lab e95a8a: ((rank(rsi_14) > 0.4688 and price_above_sma200 < | lab_search | 2026-09-24 | +2.76% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +2.76% |
| kf_mean_reversion v1 | kf_mean_reversion | 2026-09-24 | +2.75% |
| Lab 2948e1: ((rank(roc_10) > 0.7 and atr_14 > 0.5) and rsi_1 | lab_search | 2026-09-24 | +2.73% |
| Lab 6ca468: ((rank(drawdown_200) < 0.7 and pct_off_52w_low > | lab_search | 2026-09-24 | +2.72% |
| Earnings management and the post-earnings announcement drift | kf_earnings_surprise | 2026-10-06 | +2.69% |
| Short- and Long-Horizon Behavioral Factors · reproduction | kf_factor | 2026-09-25 | +2.67% |
| Lab 1dedae: ((rank(pct_of_52w_high) > 0.7 and price_above_sm | lab_search | 2026-09-24 | +2.66% |
| Fcf To Price hold=40 q=0.9 stop=5 · stop 6x ATR | fcf_to_price_stop6x | 2026-10-20 | +2.66% |
| Fcf To Price hold=60 q=0.9 stop=5 · stop 6x ATR | fcf_to_price_stop6x | 2026-10-20 | +2.66% |
| Book-to-Market Value Anomaly · reproduction · stop -1.0 | kf_value | 2026-09-25 | +2.61% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +2.60% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | +2.59% |
| Lab f8bcb7: (crosses_above(rank(vol_ratio), cci_20) and not( | lab_search | 2026-09-24 | +2.59% |
| Tax expense momentum · reproduction · universe large_cap | kf_earnings_surprise | 2026-10-07 | +2.59% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-11-04 | +2.57% |
| Lab 6a893f: ((rank(roc_10) > 0.3613 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +2.56% |
| Book-to-Market Value Anomaly · reproduction · exit 3.0 | kf_value | 2026-09-25 | +2.56% |
| Book-to-Market Value Anomaly · reproduction · holding_period | kf_value | 2026-09-25 | +2.56% |
| Book-to-Market Value Anomaly · reproduction · universe liqui | kf_value | 2026-09-25 | +2.56% |
| Buffett’s Alpha · reproduction · exit 3.0 | kf_quality | 2026-10-20 | +2.54% |
| Buffett’s Alpha · reproduction · holding_period 2.0 | kf_quality | 2026-10-20 | +2.54% |
| Buffett’s Alpha · reproduction · stop 1.0 | kf_quality | 2026-10-20 | +2.54% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +2.54% |
| Lab 6ac2aa: ((rank(obv_rising) > 0.3415 and pct_off_52w_low  | lab_search | 2026-09-24 | +2.53% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-10-12 | +2.52% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-10-12 | +2.52% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-10-12 | +2.52% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-10-12 | +2.52% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +2.52% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +2.52% |
| rsi_reversion v3 (trend_filter) | rsi_reversion | 2026-09-25 | +2.52% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +2.49% |
| Lab 783471: (crosses_above(pct_change(close, 50), pct_change | lab_search | 2026-09-24 | +2.49% |
| Lab 5bf2b8: ((rank(rsi_14) > 0.7 and price_above_sma50 < 0.5 | lab_search | 2026-09-24 | +2.48% |
| The Value of Low Volatility · reproduction · stop 1.0 | kf_low_volatility | 2026-09-30 | +2.48% |
| Fundamental momentum · reproduction · universe liquid | kf_earnings_surprise | 2026-10-16 | +2.48% |
| Post-earnings announcement drift · reproduction · universe l | kf_earnings_surprise | 2026-10-16 | +2.48% |
| Rsi Reversion hold=10 rsi=30 stop=2 | rsi_reversion | 2026-09-24 | +2.45% |
| Lab 883165: (((log_dollar_volume > 7.229 and chaikin_osc < - | lab_search | 2026-09-24 | +2.44% |
| trend_following_adx · reproduction · stop 1.0 | kf_trend | 2026-10-19 | +2.41% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-30 | +2.40% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | +2.40% |
| Lab 160c3d: ((rank(rsi_14) > 0.3097 and golden_cross < 0.5)  | lab_search | 2026-09-24 | +2.39% |
| Buffett’s Alpha · reproduction | kf_quality | 2026-09-25 | +2.39% |
| stochastic_crossover · reproduction | kf_momentum | 2026-09-25 | +2.39% |
| kf_trend v3 (trend_filter) | kf_trend | 2026-10-23 | +2.37% |
| Lab a71528: ((rank(adx_14) > 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | +2.36% |
| Earnings Surprise age=5 hold=40 q=0.8 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | +2.35% |
| Earnings Surprise age=5 hold=60 q=0.8 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | +2.35% |
| Lab da19a8: ((not(sma_200 > 43.3409) and (obv_rising < 1 and | lab_search | 2026-09-24 | +2.35% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-10-23 | +2.34% |
| multi_signal v1 | multi_signal | 2026-09-24 | +2.32% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-09-25 | +2.31% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | +2.29% |
| Lab 911880: ((rank(pct_of_52w_high) > 0.7 and price_above_sm | lab_search | 2026-09-24 | +2.28% |
| Fundamental momentum · reproduction · exit 3.0 | kf_earnings_surprise | 2026-10-16 | +2.27% |
| Fundamental momentum · reproduction · holding_period 0.5 | kf_earnings_surprise | 2026-10-16 | +2.27% |
| Fundamental momentum · reproduction · holding_period 2.0 | kf_earnings_surprise | 2026-10-16 | +2.27% |
| Post-earnings announcement drift · reproduction · exit 3.0 | kf_earnings_surprise | 2026-10-16 | +2.27% |
| Post-earnings announcement drift · reproduction · holding_pe | kf_earnings_surprise | 2026-10-16 | +2.27% |
| Post-earnings announcement drift · reproduction · holding_pe | kf_earnings_surprise | 2026-10-16 | +2.27% |
| Earnings Quality Factor · reproduction | kf_quality | 2026-09-25 | +2.24% |
| kf_quality v2 (longer_hold) | kf_quality | 2026-09-25 | +2.24% |
| Lab 90357b: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +2.24% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-10-15 | +2.23% |
| Breakout 52W hold=20 near=0.97 stop=3 | breakout_52w | 2026-09-24 | +2.23% |
| breakout_52w v2 (longer_hold) | breakout_52w | 2026-09-24 | +2.23% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-10-23 | +2.22% |
| Extrapolators at the Gate: Market-wide Misvaluation and the  | kf_value | 2026-10-14 | +2.22% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-30 | +2.21% |
| Lab f62609: ((rank(rsi_14) > 0.4573 and chaikin_osc < 0.5) a | lab_search | 2026-09-24 | +2.19% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | +2.18% |
| Lab 2d2dbe: ((rank(log_dollar_volume) > 0.6404 and vol_ratio | lab_search | 2026-09-24 | +2.17% |
| kf_quality v1 | kf_quality | 2026-09-24 | +2.15% |
| COMBINING VALUE AND MOMENTUM · reproduction · holding_period | kf_hybrid | 2026-09-25 | +2.15% |
| Book-to-Market Value Anomaly · reproduction · universe large | kf_value | 2026-09-25 | +2.15% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-30 | +2.14% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-09-25 | +2.12% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-10-09 | +2.12% |
| Lab 7f2aff: ((rank(bb_pct) > 0.4717 and golden_cross < 0.5)  | lab_search | 2026-09-24 | +2.12% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +2.11% |
| An Alternative Three-Factor Model · reproduction | kf_factor | 2026-09-25 | +2.10% |
| On the Performance of Cyclically Adjusted Valuation Measures | kf_value | 2026-10-14 | +2.08% |
| Does return dispersion explain the accrual and investment an | kf_factor | 2026-09-25 | +2.08% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | +2.08% |
| Tax expense momentum · reproduction · stop 1.0 | kf_earnings_surprise | 2026-10-07 | +2.07% |
| Lab c9270c: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +2.05% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +2.05% |
| Lab 1d7e19: ((rank(rsi_14) > 0.7467 and price_above_sma200 < | lab_search | 2026-09-24 | +2.04% |
| Lab 129ea6: ((rank(rsi_14) > 0.6701 and price_above_sma200 < | lab_search | 2026-09-24 | +2.03% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-10-13 | +2.02% |
| Costly External Finance: · reproduction | kf_fundamental | 2026-09-25 | +2.02% |
| Multifactor Asset Pricing Analysis of International Value In | kf_value | 2026-09-25 | +2.01% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-09-25 | +2.01% |
| The Sophisticated and the Simple: the profitability of contr | kf_reversal | 2026-09-25 | +2.01% |
| Value vs. Growth: What Drives the Value Premium? · reproduct | kf_value | 2026-09-25 | +2.01% |
| Lab 127f18: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | +2.00% |
| Lab d3f498: ((rank(bb_pct) > 0.3415 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +1.99% |
| Lab e6a72a: ((rank(log_dollar_volume) > 0.7374 and pct_off_5 | lab_search | 2026-09-24 | +1.99% |
| multi_signal v1 | multi_signal | 2026-09-24 | +1.99% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-09-25 | +1.98% |
| Lab 559d7e: ((rank(rsi_14) > 0.3436 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | +1.98% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +1.98% |
| Analog Stop hold=20 q=0.9 stop=3 | analog_stop | 2026-09-25 | +1.97% |
| Lab 10d988: ((rank(roc_10) > 0.2326 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +1.96% |
| Costly External Finance: · reproduction · universe liquid | kf_fundamental | 2026-10-08 | +1.95% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +1.92% |
| Psychological Barriers, Expectational Errors, and Underreact | kf_earnings_surprise | 2026-09-25 | +1.91% |
| Evaluating the Seasonality and Persistence of ETFs Performan | kf_seasonality | 2026-09-25 | +1.90% |
| The Optimism Cycle: Sell in May · reproduction | kf_seasonality | 2026-09-25 | +1.90% |
| The Optimism Cycle: Sell in May · reproduction · exit 3.0 | kf_seasonality | 2026-10-13 | +1.90% |
| The Optimism Cycle: Sell in May · reproduction · holding_per | kf_seasonality | 2026-10-13 | +1.90% |
| The Optimism Cycle: Sell in May · reproduction · holding_per | kf_seasonality | 2026-10-13 | +1.90% |
| The Optimism Cycle: Sell in May · reproduction · universe li | kf_seasonality | 2026-10-13 | +1.90% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-10-12 | +1.90% |
| Defensive · reproduction · universe large_cap | kf_low_volatility | 2026-10-01 | +1.89% |
| Trend Following hold=20 stop=3.5 | trend_following | 2026-09-24 | +1.89% |
| Rsi Reversion hold=10 rsi=30 stop=3 | rsi_reversion | 2026-09-25 | +1.86% |
| Costly External Finance: · reproduction · universe large_cap | kf_fundamental | 2026-10-08 | +1.86% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-10-23 | +1.86% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-10-23 | +1.86% |
| Portfolio constituency rules and the value premium in the sm | kf_value | 2026-10-23 | +1.86% |
| Factoring Profitability · reproduction · stop 1.0 | kf_quality | 2026-09-30 | +1.86% |
| The Joint Distribution of Value and Profitability: Internati | kf_hybrid | 2026-09-29 | +1.85% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +1.83% |
| golden_cross · reproduction | kf_trend | 2026-09-25 | +1.83% |
| Value Quality Momentum hold=40 q=0.6 stop=4 | value_quality_momentum | 2026-09-24 | +1.83% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +1.79% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +1.78% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +1.78% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +1.78% |
| bollinger_breakout · reproduction · holding_period 2.0 | kf_breakout | 2026-10-01 | +1.77% |
| Lab ae7ebc: ((rank(rsi_14) > 0.4983 or crosses_above(price_a | lab_search | 2026-09-24 | +1.77% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +1.76% |
| Why do Predicted Stock Issuers Earn Low · reproduction · exi | kf_fundamental | 2026-10-07 | +1.75% |
| Why do Predicted Stock Issuers Earn Low · reproduction · hol | kf_fundamental | 2026-10-07 | +1.75% |
| Why do Predicted Stock Issuers Earn Low · reproduction · hol | kf_fundamental | 2026-10-07 | +1.75% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +1.75% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +1.75% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +1.75% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +1.75% |
| golden_cross · reproduction · universe liquid | kf_trend | 2026-10-20 | +1.75% |
| kf_factor v2 (longer_hold) | kf_factor | 2026-09-30 | +1.75% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-09-25 | +1.72% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-10-22 | +1.70% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-10-22 | +1.70% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-10-22 | +1.70% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-10-22 | +1.70% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +1.69% |
| Fundamental momentum · reproduction · stop 1.0 | kf_earnings_surprise | 2026-10-16 | +1.68% |
| Post-earnings announcement drift · reproduction · stop 1.0 | kf_earnings_surprise | 2026-10-16 | +1.68% |
| Lab f74ac2: ((rank(roc_10) > 0.3368 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +1.66% |
| Lab ba1546: ((rank(cci_20) > 0.69 and bb_pct < 0.5) and rsi_ | lab_search | 2026-09-24 | +1.66% |
| bollinger_breakout · reproduction | kf_breakout | 2026-09-25 | +1.65% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | +1.64% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +1.63% |
| kf_trend v3 (trend_filter) | kf_trend | 2026-10-26 | +1.62% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | +1.61% |
| Why do Predicted Stock Issuers Earn Low · reproduction · sto | kf_fundamental | 2026-10-07 | +1.61% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | +1.60% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | +1.60% |
| Lab e7ebbf: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +1.60% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-16 | +1.59% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction · | kf_value | 2026-10-21 | +1.57% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-10-09 | +1.57% |
| “Sell in May and Go Away” Just Won’t Go Away · reproduction | kf_seasonality | 2026-09-25 | +1.57% |
| Costly External Finance: · reproduction · exit 3.0 | kf_fundamental | 2026-10-08 | +1.57% |
| Costly External Finance: · reproduction · holding_period 0.5 | kf_fundamental | 2026-10-08 | +1.57% |
| Market Power, Technology Shocks, and the Profitability Premi | kf_quality | 2026-09-25 | +1.56% |
| buyback v3 (trend_filter) | buyback | 2026-09-25 | +1.55% |
| Lab f2bdc1: not((rank(stoch_d) < 0.5451 or (crosses_below(cc | lab_search | 2026-09-24 | +1.53% |
| Lab b3299a: (((log_dollar_volume < 8.3866 and chaikin_osc <  | lab_search | 2026-09-24 | +1.53% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +1.52% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +1.52% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-10-15 | +1.51% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction · | kf_value | 2026-10-21 | +1.49% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction · | kf_value | 2026-10-21 | +1.49% |
| Growth Valuation hold=40 q=0.7 stop=5 | growth_valuation | 2026-09-24 | +1.46% |
| Growth Valuation hold=60 q=0.7 stop=5 | growth_valuation | 2026-09-24 | +1.46% |
| Lab 207a79: ((crosses_above(rank(rsi_14), 0.7) or pct_off_52 | lab_search | 2026-09-24 | +1.43% |
| trend_following_adx · reproduction · stop -1.0 | kf_trend | 2026-10-19 | +1.42% |
| Lab c76e27: ((rank(rsi_14) > 0.4244 and atr_14 > 0.3952) and | lab_search | 2026-09-24 | +1.41% |
| An Alternative Three-Factor Model · reproduction · exit 3.0 | kf_factor | 2026-10-08 | +1.39% |
| An Alternative Three-Factor Model · reproduction · stop -1.0 | kf_factor | 2026-10-08 | +1.39% |
| Combining fundamental fscore and equity short term reversals | kf_reversal | 2026-09-25 | +1.39% |
| Multi Signal hold=60 q=0.9 stop=4 | multi_signal | 2026-09-25 | +1.37% |
| Costly External Finance: · reproduction · stop 1.0 | kf_fundamental | 2026-10-08 | +1.36% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction · | kf_value | 2026-10-21 | +1.35% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +1.35% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-15 | +1.34% |
| Lab 9a7404: (crosses_below(rsi_14, 35.3472) and pct_off_52w_ | lab_search | 2026-09-24 | +1.34% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +1.34% |
| Factoring Profitability · reproduction · holding_period 2.0 | kf_quality | 2026-09-30 | +1.34% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-30 | +1.34% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-30 | +1.34% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-30 | +1.34% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-30 | +1.34% |
| Debt Reduction hold=40 n=63 stop=5 · stop 6x ATR | debt_reduction_stop6x | 2026-10-20 | +1.33% |
| Debt Reduction hold=60 n=63 stop=5 · stop 6x ATR | debt_reduction_stop6x | 2026-10-20 | +1.33% |
| ON THE PROFITABILITY OF 12 FUNDAMENTAL ANALYSIS STRATEGIES O | kf_value | 2026-09-25 | +1.33% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-10-22 | +1.32% |
| An Alternative Three-Factor Model · reproduction · stop 1.0 | kf_factor | 2026-10-08 | +1.30% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | +1.29% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | +1.29% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | +1.29% |
| Tax expense momentum · reproduction · exit 3.0 | kf_earnings_surprise | 2026-10-07 | +1.28% |
| Tax expense momentum · reproduction · holding_period 0.5 | kf_earnings_surprise | 2026-10-07 | +1.28% |
| Tax expense momentum · reproduction · holding_period 2.0 | kf_earnings_surprise | 2026-10-07 | +1.28% |
| Tax expense momentum · reproduction · universe liquid | kf_earnings_surprise | 2026-10-07 | +1.28% |
| buyback v3 (trend_filter) | buyback | 2026-09-25 | +1.27% |
| buyback v3 (trend_filter) | buyback | 2026-09-25 | +1.27% |
| An Alternative Three-Factor Model · reproduction · holding_p | kf_factor | 2026-10-08 | +1.27% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +1.27% |
| Market Timing with Moving Averages · reproduction | kf_trend | 2026-09-25 | +1.24% |
| kf_other v2 (longer_hold) | kf_other | 2026-10-16 | +1.24% |
| Value Investing: Investing for Grown Ups? · reproduction | kf_value | 2026-09-25 | +1.24% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-28 | +1.22% |
| Lab eac05b: ((rank(price_above_sma50) > 0.3395 and pct_off_5 | lab_search | 2026-09-24 | +1.20% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-10-13 | +1.19% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-10-13 | +1.19% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-10-13 | +1.18% |
| Trend Following hold=20 stop=2.5 | trend_following | 2026-09-24 | +1.17% |
| turtle_with_volume · reproduction | kf_breakout | 2026-09-25 | +1.15% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | +1.14% |
| Lab 8373f2: ((rank(roc_10) > 0.5106 and atr_14 > 0.5) and rs | lab_search | 2026-09-24 | +1.14% |
| kf_quality v3 (trend_filter) | kf_quality | 2026-10-26 | +1.10% |
| Fundamental momentum · reproduction · stop -1.0 | kf_earnings_surprise | 2026-10-16 | +1.08% |
| Post-earnings announcement drift · reproduction · stop -1.0 | kf_earnings_surprise | 2026-10-16 | +1.08% |
| Lab 60b66d: ((rank(bb_pct) > 0.2664 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +1.08% |
| The Profitability Premium: Macroeconomic Risks or Expectatio | kf_quality | 2026-10-14 | +1.08% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-11-02 | +1.08% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | +1.07% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | +1.05% |
| The Optimism Cycle: Sell in May · reproduction · stop 1.0 | kf_seasonality | 2026-10-13 | +1.05% |
| Lab 7e4022: ((rank(dollar_volume_20) > 0.7 and cci_20 < 0.5) | lab_search | 2026-09-24 | +1.04% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | +1.04% |
| Lab 6354ef: ((rank(dollar_volume_20) > 0.7 and atr_14 > 0.5) | lab_search | 2026-09-24 | +1.04% |
| An Alternative Three-Factor Model · reproduction · holding_p | kf_factor | 2026-10-08 | +1.03% |
| Lab 87abb2: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | +1.02% |
| Lab fb9275: ((rank(macd) > 0.7 and price_above_sma200 < 0.5) | lab_search | 2026-09-24 | +1.01% |
| Factor investing: get your exposures right! · reproduction · | kf_factor | 2026-10-07 | +1.00% |
| Lab db0c37: ((rank(bb_pct) > 0.56 and chaikin_osc < 0.4734)  | lab_search | 2026-09-24 | +0.99% |
| Lab d88629: ((rank(bb_pct) > 0.7 and roc_10 < 0.5) and rsi_1 | lab_search | 2026-09-24 | +0.98% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-10-13 | +0.98% |
| Lab 98ac86: (rsi_14 < 34.3515 and pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | +0.97% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-11-09 | +0.97% |
| bollinger_breakout · reproduction · exit 3.0 | kf_breakout | 2026-10-01 | +0.95% |
| bollinger_breakout · reproduction · stop -1.0 | kf_breakout | 2026-10-01 | +0.95% |
| bollinger_breakout · reproduction · stop 1.0 | kf_breakout | 2026-10-01 | +0.95% |
| bollinger_breakout · reproduction · universe liquid | kf_breakout | 2026-10-01 | +0.95% |
| Deflating Profitability · reproduction · stop 1.0 | kf_quality | 2026-10-13 | +0.94% |
| kf_mean_reversion v2 (longer_hold) | kf_mean_reversion | 2026-11-04 | +0.93% |
| Lab 93d65a: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.93% |
| The Value of Low Volatility · reproduction · stop -1.0 | kf_low_volatility | 2026-09-30 | +0.92% |
| ACCRUAL ANOMALY AND IDIOSYNCRATIC RISK: INTERNATIONAL EVIDEN | kf_quality | 2026-09-25 | +0.90% |
| Agency Theory of Overvalued Equity as an · reproduction · st | kf_fundamental | 2026-09-28 | +0.90% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | +0.90% |
| The role of accruals in predicting future cash flows and sto | kf_quality | 2026-09-25 | +0.90% |
| Lab 89f6c3: ((not(price_above_sma200 < 0) and crosses_below( | lab_search | 2026-09-24 | +0.90% |
| Lab 5c753c: ((rank(drawdown_200) < 0.7 and pct_off_52w_low > | lab_search | 2026-09-24 | +0.88% |
| Earnings Surprise age=10 hold=40 q=0.8 | earnings_surprise | 2026-09-24 | +0.87% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | +0.87% |
| earnings_surprise v2 (longer_hold) | earnings_surprise | 2026-09-24 | +0.87% |
| The Value of Low Volatility · reproduction · exit 3.0 | kf_low_volatility | 2026-09-30 | +0.86% |
| The Value of Low Volatility · reproduction · universe liquid | kf_low_volatility | 2026-09-30 | +0.86% |
| Lab d42ad7: ((rank(rsi_14) > 0.4788 and chaikin_osc < 0.4258 | lab_search | 2026-09-24 | +0.85% |
| Standardized Unexpected Earnings · reproduction · stop -1.0 | kf_earnings_surprise | 2026-09-25 | +0.84% |
| Lab afaa51: ((rank(price_above_sma50) > 0.429 and bb_pct < 0 | lab_search | 2026-09-24 | +0.84% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +0.84% |
| Discussion of Value Investing: The Use of Historical Financi | kf_fundamental | 2026-09-25 | +0.84% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-10-12 | +0.84% |
| Lab 669077: ((rank(price_above_sma50) > 0.4314 and obv_risin | lab_search | 2026-09-24 | +0.84% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | +0.84% |
| Rsi Reversion hold=10 rsi=25 stop=2 | rsi_reversion | 2026-09-25 | +0.83% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | +0.80% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | +0.80% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | +0.80% |
| piotroski_value · reproduction · stop 1.0 | kf_quality | 2026-10-23 | +0.79% |
| Costly External Finance: · reproduction · stop -1.0 | kf_fundamental | 2026-10-08 | +0.79% |
| chaikin_oscillator · reproduction | kf_momentum | 2026-09-25 | +0.77% |
| kf_trend v3 (trend_filter) | kf_trend | 2026-11-09 | +0.77% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-10-29 | +0.76% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | +0.76% |
| Lab 55cc79: ((rank(price_above_sma50) > 0.4844 and pct_off_5 | lab_search | 2026-09-24 | +0.75% |
| Value Investing: Investing for Grown Ups? · reproduction · u | kf_value | 2026-10-19 | +0.74% |
| Lab 7e8abb: ((rank(roc_10) > 0.7 and roc_10 < 0.5) and rsi_1 | lab_search | 2026-09-24 | +0.73% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | +0.72% |
| Standardized Unexpected Earnings · reproduction · stop 1.0 | kf_earnings_surprise | 2026-09-25 | +0.72% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-10-22 | +0.72% |
| Lab dbe19d: ((rank(rsi_14) > 0.4564 and price_above_sma200 < | lab_search | 2026-09-24 | +0.72% |
| Analog Top hold=10 q=0.9 stop=2.5 | analog_top | 2026-09-24 | +0.72% |
| Rsi Reversion hold=10 rsi=25 stop=3 | rsi_reversion | 2026-09-25 | +0.71% |
| Deflating Profitability · reproduction · exit 3.0 | kf_quality | 2026-10-13 | +0.71% |
| Deflating Profitability · reproduction · holding_period 0.5 | kf_quality | 2026-10-13 | +0.71% |
| Deflating Profitability · reproduction · universe large_cap | kf_quality | 2026-10-13 | +0.71% |
| Deflating Profitability · reproduction · universe liquid | kf_quality | 2026-10-13 | +0.71% |
| Lab e48b1d: not(((chaikin_osc > -952682 or willr_14 > -86.53 | lab_search | 2026-09-24 | +0.71% |
| Lab de9248: ((rank(rsi_14) > 0.5282 and price_above_sma200 < | lab_search | 2026-09-24 | +0.71% |
| kf_hybrid v2 (longer_hold) | kf_hybrid | 2026-11-05 | +0.70% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-10-22 | +0.70% |
| Lab 7d7309: ((rank(price_above_sma50) > 0.429 and obv_rising | lab_search | 2026-09-24 | +0.69% |
| The Long and Short of the Accrual Anomaly · reproduction | kf_quality | 2026-09-25 | +0.69% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | +0.69% |
| Lab 79e0f8: not((rank(stoch_d) < 0.5353 or (crosses_below(bb | lab_search | 2026-09-24 | +0.68% |
| trend_following_adx · reproduction · universe large_cap | kf_trend | 2026-10-19 | +0.68% |
| The Cross-Section of Stock Returns: Rank-Based, Linear, and  | kf_quality | 2026-10-09 | +0.67% |
| Why do Predicted Stock Issuers Earn Low · reproduction · sto | kf_fundamental | 2026-10-07 | +0.67% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | +0.66% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-10-13 | +0.66% |
| The Halloween Effect in US Sectors · reproduction · stop 1.0 | kf_seasonality | 2026-09-25 | +0.64% |
| multi_signal v1 | multi_signal | 2026-09-24 | +0.64% |
| Lab b0c3dd: ((rank(rsi_14) > 0.2688 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | +0.64% |
| Lab b9e50d: ((rank(rsi_14) > 0.4532 and price_above_sma200 < | lab_search | 2026-09-24 | +0.63% |
| Lab 105c2c: (rsi_14 < 34.6622 and pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | +0.63% |
| Lab dd3160: (rsi_14 < 34.5694 and pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | +0.61% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +0.61% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +0.61% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +0.61% |
| Analysis of the Bollinger bands and Ornstein-Uhlenbeck Model | kf_mean_reversion | 2026-09-25 | +0.61% |
| Lab 3cd695: ((rank(rsi_14) > 0.8594 and price_above_sma50 <  | lab_search | 2026-09-24 | +0.61% |
| Lab e26331: ((rank(rsi_14) > 0.7 and chaikin_osc < 0.5) and  | lab_search | 2026-09-24 | +0.61% |
| Factoring in the Low-Volatility Factor · reproduction · stop | kf_low_volatility | 2026-09-30 | +0.61% |
| The Optimism Cycle: Sell in May · reproduction · stop -1.0 | kf_seasonality | 2026-10-13 | +0.60% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | +0.60% |
| Lab 5918e2: ((rank(rsi_14) > 0.4593 and price_above_sma200 < | lab_search | 2026-09-24 | +0.58% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | +0.56% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +0.54% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-10-12 | +0.54% |
| Lab 7c203f: ((rank(adx_14) > 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | +0.54% |
| quality_value · reproduction · stop -1.0 | kf_quality | 2026-10-22 | +0.53% |
| COMBINING VALUE AND MOMENTUM · reproduction · exit 3.0 | kf_hybrid | 2026-09-25 | +0.51% |
| Standardized Unexpected Earnings · reproduction · universe l | kf_earnings_surprise | 2026-09-25 | +0.51% |
| COMBINING VALUE AND MOMENTUM · reproduction · universe liqui | kf_hybrid | 2026-09-25 | +0.50% |
| The Halloween Effect in US Sectors · reproduction · stop -1. | kf_seasonality | 2026-09-25 | +0.49% |
| Lab 5fe0e3: ((rank(pct_of_52w_high) > 0.7 or crosses_above(g | lab_search | 2026-09-24 | +0.49% |
| Investment momentum: A two-dimensional behavioural strategy  | kf_momentum | 2026-09-25 | +0.48% |
| quality_value · reproduction · exit 3.0 | kf_quality | 2026-10-22 | +0.47% |
| quality_value · reproduction · holding_period 0.5 | kf_quality | 2026-10-22 | +0.47% |
| quality_value · reproduction · stop 1.0 | kf_quality | 2026-10-22 | +0.47% |
| Lab becd46: ((rank(price_above_sma50) > 0.4477 and vol_ratio | lab_search | 2026-09-24 | +0.47% |
| Volatility Breakout hold=5 stop=2 vr=1.5 | volatility_breakout | 2026-09-24 | +0.46% |
| kf_hybrid v2 (longer_hold) | kf_hybrid | 2026-09-30 | +0.46% |
| Lab 68bfa9: ((rank(cci_20) > 0.4968 and drawdown_200 > 0.401 | lab_search | 2026-09-24 | +0.46% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | +0.45% |
| The Other Side of Value: The Gross Profitability Premium · r | kf_quality | 2026-09-30 | +0.45% |
| Lab 5a8cea: ((rank(price_above_sma50) > 0.4014 and obv_risin | lab_search | 2026-09-24 | +0.45% |
| piotroski_value · reproduction · exit 3.0 | kf_quality | 2026-10-23 | +0.45% |
| piotroski_value · reproduction · holding_period 0.5 | kf_quality | 2026-10-23 | +0.45% |
| The Conservative Formula: Quantitative Investing Made Easy · | kf_hybrid | 2026-09-25 | +0.44% |
| kf_breakout v2 (longer_hold) | kf_breakout | 2026-10-01 | +0.44% |
| Value + quality · reproduction | kf_quality | 2026-09-25 | +0.44% |
| Breakout 52W hold=20 near=0.97 stop=2 | breakout_52w | 2026-09-24 | +0.43% |
| breakout_52w v2 (longer_hold) | breakout_52w | 2026-09-24 | +0.43% |
| Lab c8e85a: ((rank(price_above_sma50) > 0.427 and vol_ratio  | lab_search | 2026-09-24 | +0.43% |
| rsi_oversold · reproduction | kf_mean_reversion | 2026-09-25 | +0.43% |
| Rsi Reversion hold=10 rsi=30 stop=3 | rsi_reversion | 2026-09-24 | +0.42% |
| Lab 8d7742: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | +0.42% |
| Lab a1477e: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | +0.42% |
| Lab 3b4485: ((rank(price_above_sma50) > 0.4314 and cci_20 <  | lab_search | 2026-09-24 | +0.41% |
| Turnover: Liquidity or Uncertainty? · reproduction · univers | kf_liquidity | 2026-09-25 | +0.41% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | +0.41% |
| The Volatility Effect Revisited · reproduction | kf_low_volatility | 2026-09-25 | +0.40% |
| Lab ea3656: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.40% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | +0.39% |
| Lab dc6193: not(((chaikin_osc > -952682 or willr_14 > -86.53 | lab_search | 2026-09-24 | +0.39% |
| Breakout 52W hold=20 near=0.99 stop=3 | breakout_52w | 2026-09-24 | +0.38% |
| breakout_52w v2 (longer_hold) | breakout_52w | 2026-09-24 | +0.38% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | +0.38% |
| Lab 2dbd3f: not((rank(stoch_k) < 0.6134 or (crosses_above(cc | lab_search | 2026-09-24 | +0.37% |
| kf_kalman_e | - | 2026-10-02 | +0.36% |
| Lab a213d2: ((rank(price_above_sma200) > 0.4638 and golden_c | lab_search | 2026-09-24 | +0.36% |
| Lab 532e6b: ((rank(rsi_14) > 0.7 and macd < 0.5068) and rsi_ | lab_search | 2026-09-24 | +0.35% |
| Earnings Surprise age=10 hold=60 q=0.8 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | +0.35% |
| earnings_surprise v2 (longer_hold) · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | +0.35% |
| The Optimism Cycle: Sell in May · reproduction · universe la | kf_seasonality | 2026-10-13 | +0.34% |
| piotroski_value · reproduction · universe large_cap | kf_quality | 2026-10-23 | +0.34% |
| An Alternative Three-Factor Model · reproduction · stop 6x A | kf_factor_stop6x | 2026-10-20 | +0.34% |
| Lab cde706: ((rank(price_above_sma50) > 0.4241 and obv_risin | lab_search | 2026-09-24 | +0.33% |
| Lab 8792bb: ((rank(price_above_sma50) > 0.4267 and obv_risin | lab_search | 2026-09-24 | +0.31% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | +0.30% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-10-22 | +0.30% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-10-22 | +0.30% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | +0.29% |
| breakout_52w v2 (longer_hold) | breakout_52w | 2026-09-24 | +0.29% |
| Lab f5be7b: ((rank(price_above_sma50) > 0.4241 and bb_pct <  | lab_search | 2026-09-24 | +0.28% |
| Lab 9cb46c: ((rank(price_above_sma50) > 0.4314 and obv_risin | lab_search | 2026-09-24 | +0.28% |
| kf_other v2 (longer_hold) | kf_other | 2026-10-19 | +0.28% |
| COMBINING VALUE AND MOMENTUM · reproduction · stop 1.0 | kf_hybrid | 2026-09-25 | +0.27% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-10-12 | +0.27% |
| Identifying Expectation Errors in Value/Glamour Strategies:  | kf_value | 2026-10-12 | +0.27% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-10-12 | +0.27% |
| Lab 354ee8: ((rank(price_above_sma50) > 0.427 and bb_pct < 0 | lab_search | 2026-09-24 | +0.27% |
| Equity Book-to-Market Ratios Above One and Recession Risk ·  | kf_value | 2026-09-25 | +0.27% |
| Lab feafce: ((rank(price_above_sma50) > 0.443 and golden_cro | lab_search | 2026-09-24 | +0.25% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-10-22 | +0.25% |
| Lab 3f9d31: not((rank(obv_rising) < 0.805 or (crosses_above( | lab_search | 2026-09-24 | +0.24% |
| Lab b4519d: ((rank(rsi_14) > 0.7 and macd < 0.5806) and rsi_ | lab_search | 2026-09-24 | +0.23% |
| Lab db235d: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.23% |
| Lab bd7dc4: ((rank(dollar_volume_20) > 0.8594 and chaikin_os | lab_search | 2026-09-24 | +0.22% |
| Lab 2ce57b: ((rank(price_above_sma50) > 0.4241 and bb_pct <  | lab_search | 2026-09-24 | +0.22% |
| Lab ea2ffd: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.22% |
| Why do Predicted Stock Issuers Earn Low · reproduction · uni | kf_fundamental | 2026-10-07 | +0.22% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-14 | +0.22% |
| Lab 4e2510: ((rank(chaikin_osc) < 0.7 and pct_off_52w_low >  | lab_search | 2026-09-24 | +0.22% |
| The Long and Short of the Accrual Anomaly · reproduction · h | kf_quality | 2026-10-15 | +0.21% |
| The Halloween Effect in US Sectors · reproduction · exit 3.0 | kf_seasonality | 2026-09-25 | +0.20% |
| The Halloween Effect in US Sectors · reproduction · holding_ | kf_seasonality | 2026-09-25 | +0.20% |
| The Halloween Effect in US Sectors · reproduction · holding_ | kf_seasonality | 2026-09-25 | +0.20% |
| The Halloween Effect in US Sectors · reproduction · universe | kf_seasonality | 2026-09-25 | +0.20% |
| kf_seasonality v1 | kf_seasonality | 2026-09-24 | +0.20% |
| kf_value v1 | kf_value | 2026-09-24 | +0.20% |
| Lab 103d4b: ((rank(price_above_sma50) > 0.424 and roc_10 < 0 | lab_search | 2026-09-24 | +0.19% |
| Lab 34a19c: not(((chaikin_osc > -920228 or willr_14 > -86.53 | lab_search | 2026-09-24 | +0.18% |
| An Alternative Three-Factor Model · reproduction · universe  | kf_factor | 2026-10-08 | +0.18% |
| Lab 8d0ec9: ((rank(rsi_14) > 0.2378 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +0.18% |
| Quality Piotroski f=8 hold=40 stop=3 | quality_piotroski | 2026-09-24 | +0.17% |
| Quality Piotroski f=8 hold=60 stop=3 | quality_piotroski | 2026-09-24 | +0.17% |
| Lab 56f07a: ((rank(chaikin_osc) > 0.6404 and pct_off_52w_low | lab_search | 2026-09-24 | +0.17% |
| Lab b834e1: not((rank(cci_20) < 0.805 or (cci_20 > macd_hist | lab_search | 2026-09-24 | +0.17% |
| Rsi Reversion hold=5 rsi=30 stop=2 | rsi_reversion | 2026-09-24 | +0.15% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | +0.15% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | +0.15% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | +0.15% |
| Lab a4cec6: ((rank(price_above_sma50) > 0.4155 and cci_20 <  | lab_search | 2026-09-24 | +0.15% |
| Lab ce82ab: ((rank(price_above_sma50) > 0.429 and cci_20 < 0 | lab_search | 2026-09-24 | +0.15% |
| Lab b898b4: ((rank(rsi_14) > 0.2326 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | +0.14% |
| bollinger_breakout · reproduction · holding_period 0.5 | kf_breakout | 2026-10-01 | +0.14% |
| Lab e83a04: ((rank(price_above_sma50) > 0.429 and roc_10 < 0 | lab_search | 2026-09-24 | +0.14% |
| Value + momentum · reproduction · universe liquid | kf_hybrid | 2026-10-01 | +0.13% |
| etf_rotation_sectors v1 | etf_rotation_sectors | 2026-09-24 | +0.12% |
| etf_rotation_sectors v1 | etf_rotation_sectors | 2026-09-24 | +0.12% |
| Lab 9c8710: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.11% |
| Lab 45c4cb: ((rank(price_above_sma50) > 0.438 and pct_off_52 | lab_search | 2026-09-24 | +0.11% |
| golden_cross · reproduction · universe large_cap | kf_trend | 2026-10-20 | +0.11% |
| An Alternative Three-Factor Model · reproduction · universe  | kf_factor | 2026-10-08 | +0.09% |
| Lab bd298b: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.08% |
| Lab 499255: ((rank(price_above_sma50) > 0.4844 and obv_risin | lab_search | 2026-09-24 | +0.08% |
| Lab 835fe8: ((rank(price_above_sma50) > 0.4291 and pct_off_5 | lab_search | 2026-09-24 | +0.08% |
| Lab 9664c6: ((rank(price_above_sma50) > 0.4209 and pct_off_5 | lab_search | 2026-09-24 | +0.08% |
| Lab cabca0: (((pct_off_52w_low > 0.1661 or chaikin_osc > -2. | lab_search | 2026-09-24 | +0.08% |
| Lab d3cf75: ((rank(rsi_14) > 0.451 and chaikin_osc < 0.4258) | lab_search | 2026-09-24 | +0.07% |
| Earnings Surprise age=5 hold=40 q=0.9 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | +0.06% |
| Earnings Surprise age=5 hold=60 q=0.9 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | +0.06% |
| etf_rotation_sectors v1 | etf_rotation_sectors | 2026-09-24 | +0.06% |
| etf_rotation_sectors v1 | etf_rotation_sectors | 2026-09-24 | +0.06% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality_stop6x | 2026-10-20 | +0.06% |
| Lab 2730d9: ((rank(price_above_sma50) > 0.4291 and price_abo | lab_search | 2026-09-24 | +0.04% |
| COMBINING VALUE AND MOMENTUM · reproduction · stop -1.0 | kf_hybrid | 2026-09-25 | +0.03% |
| etf_rotation_sectors v1 | etf_rotation_sectors | 2026-09-24 | +0.03% |
| Lab 428fae: ((rank(cci_20) > 0.4678 and crosses_below(vol_ra | lab_search | 2026-09-24 | +0.03% |
| Lab 1b65b4: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | +0.02% |
| Lab 786f06: ((rank(price_above_sma50) > 0.438 and pct_off_52 | lab_search | 2026-09-24 | +0.02% |
| Lab c3f910: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | +0.01% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-09-25 | +0.00% |
| macd_crossover · reproduction | kf_trend | 2026-09-25 | +0.00% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | +0.00% |
| A December Effect with Tax-Gain Selling? · reproduction | kf_seasonality | 2026-09-25 | +0.00% |
| A Trend Factor: Any Economic Gains from Using Information ov | kf_trend | 2026-09-25 | +0.00% |
| Buffett’s Alpha · reproduction · universe large_cap | kf_quality | 2026-10-20 | +0.00% |
| Buffett’s Alpha · reproduction · universe liquid | kf_quality | 2026-10-20 | +0.00% |
| COMBINING VALUE AND MOMENTUM · reproduction · lookback 1.5 | kf_hybrid | 2026-09-25 | +0.00% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | +0.00% |
| Company-Size Effect on the Polish Stock Market · reproductio | kf_size | 2026-09-25 | +0.00% |
| Daily Winners and Losers · reproduction | kf_reversal | 2026-09-25 | +0.00% |
| Daily Winners and Losers · reproduction · exit 3.0 | kf_reversal | 2026-10-15 | +0.00% |
| Daily Winners and Losers · reproduction · holding_period 0.5 | kf_reversal | 2026-10-15 | +0.00% |
| Daily Winners and Losers · reproduction · holding_period 2.0 | kf_reversal | 2026-10-15 | +0.00% |
| Daily Winners and Losers · reproduction · stop -1.0 | kf_reversal | 2026-10-15 | +0.00% |
| Daily Winners and Losers · reproduction · stop 1.0 | kf_reversal | 2026-10-15 | +0.00% |
| Daily Winners and Losers · reproduction · universe large_cap | kf_reversal | 2026-10-15 | +0.00% |
| Daily Winners and Losers · reproduction · universe liquid | kf_reversal | 2026-10-15 | +0.00% |
| Discovery of a 13-Sharpe OOS Factor: Drift Regimes Unlock Hi | kf_regime | 2026-09-25 | +0.00% |
| Equity factor investing: Historical perspective of recent pe | kf_factor | 2026-09-25 | +0.00% |
| Exploring the Growth Value Equity Valuation Model with Data  | kf_value | 2026-09-25 | +0.00% |
| Fama French Five Factors · reproduction | kf_factor | 2026-09-25 | +0.00% |
| Forecasting Stock Returns in Good and Bad Times: The Role of | kf_regime | 2026-09-25 | +0.00% |
| Free Cash Flows and Price Momentum · reproduction · lookback | kf_momentum | 2026-10-21 | +0.00% |
| Fundamental Factor Long Short Strategy · reproduction | kf_factor | 2026-09-25 | +0.00% |
| Insider Buying buyers=1 hold=20 stop=3 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=1 hold=20 stop=4 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=1 hold=60 stop=3 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=1 hold=60 stop=4 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=2 hold=20 stop=3 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=2 hold=20 stop=4 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=2 hold=60 stop=3 | insider_buying | 2026-09-25 | +0.00% |
| Insider Buying buyers=2 hold=60 stop=4 | insider_buying | 2026-09-25 | +0.00% |
| Is Momentum an Echo? · reproduction | kf_momentum | 2026-09-25 | +0.00% |
| Is the January Effect Economically Exploitable? - Evidence f | kf_seasonality | 2026-09-25 | +0.00% |
| January Effect in Stocks · reproduction · universe large_cap | kf_seasonality | 2026-09-25 | +0.00% |
| Lab 005a34: ((rank(rsi_14) > 0.5483 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 01080e: ((rank(price_above_sma50) > 0.4494 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 0279ac: crosses_below(rank(price_above_sma50), 0.077) | lab_search | 2026-09-24 | +0.00% |
| Lab 02f2cb: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab 0388d8: ((rank(price_above_sma200) > 0.478 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 075986: ((rank(rsi_14) > 0.5009 and drawdown_200 > 0.427 | lab_search | 2026-09-24 | +0.00% |
| Lab 09cd38: (((roc_10 < -2.9715 or price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab 0a076b: ((rank(rsi_14) > 0.5991 and golden_cross < 0.5)  | lab_search | 2026-09-24 | +0.00% |
| Lab 0a3f30: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 0c52e1: ((rank(rsi_14) > 0.6368 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 0f7738: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab 0fa997: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 1102a3: ((rank(rsi_14) > 0.4929 and atr_14 > 0.5) and rs | lab_search | 2026-09-24 | +0.00% |
| Lab 1103d2: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 1151e6: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab 129fe4: ((rank(golden_cross) > 0.8166 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 12d301: ((rank(rsi_14) > 0.6055 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 132fa8: rank(golden_cross) > 0.8528 | lab_search | 2026-09-24 | +0.00% |
| Lab 164a4d: rank(obv_rising) < 0.105 | lab_search | 2026-09-24 | +0.00% |
| Lab 17ad9a: (((roc_10 < -2.9715 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab 18e210: ((rank(golden_cross) > 0.8445 and chaikin_osc <  | lab_search | 2026-09-24 | +0.00% |
| Lab 19021b: ((rank(rsi_14) > 0.4593 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 192d07: (((roc_10 < -2.9715 or price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab 1b5335: not((rank(cci_20) < 0.805 or (cci_20 > macd or s | lab_search | 2026-09-24 | +0.00% |
| Lab 1c952c: (((roc_10 < -2.9715 or price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab 1e7aa1: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 1fc704: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 1fe341: ((rank(price_above_sma200) > 0.8819 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 210424: ((rank(price_above_sma200) > 0.4548 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 22295e: rank(obv_rising) < 0.0946 | lab_search | 2026-09-24 | +0.00% |
| Lab 245d02: ((rank(price_above_sma50) > 0.4494 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 24adb0: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 261aee: (((roc_10 < -2.9715 or crosses_above(price_above | lab_search | 2026-09-24 | +0.00% |
| Lab 27d232: ((rank(price_above_sma50) > 0.4435 and macd < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 27d952: ((rank(price_above_sma50) > 0.4414 and golden_cr | lab_search | 2026-09-24 | +0.00% |
| Lab 281747: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 285fb3: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 294cbb: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 2962c5: (((roc_10 < -2.9715 or crosses_below(atr_14, 1)) | lab_search | 2026-09-24 | +0.00% |
| Lab 2a29f4: (((roc_10 < -2.9715 or chaikin_osc < 1) and rank | lab_search | 2026-09-24 | +0.00% |
| Lab 2a39d6: (((crosses_below(roc_10, -2.9715) or atr_14 > 1) | lab_search | 2026-09-24 | +0.00% |
| Lab 2a7895: ((rank(golden_cross) > 0.8445 and vol_ratio > 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 2b1923: (((roc_10 < -2.9715 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab 2be386: ((rank(price_above_sma50) > 0.4481 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab 2d70a2: ((rank(bb_pct) > 0.7 and obv_rising < 0.5) and r | lab_search | 2026-09-24 | +0.00% |
| Lab 2edc69: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 2fbbf3: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 2ff4f9: (((roc_10 < -3.2322 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab 320133: ((rank(price_above_sma50) > 0.4238 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab 338c8e: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 348163: ((rank(golden_cross) > 0.8445 and vol_ratio > 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 353579: (((cci_20 < -2.9715 and chaikin_osc < 1) and ran | lab_search | 2026-09-24 | +0.00% |
| Lab 3546f3: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 3826e4: ((rank(golden_cross) > 0.8445 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 386c83: ((rank(golden_cross) > 0.8445 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 38d651: ((rank(price_above_sma50) > 0.4343 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab 3b9067: ((rank(rsi_14) > 0.627 and price_above_sma200 <  | lab_search | 2026-09-24 | +0.00% |
| Lab 3db19e: ((rank(price_above_sma200) > 0.4424 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 3eb124: crosses_below(rank(obv_rising), 0.1009) | lab_search | 2026-09-24 | +0.00% |
| Lab 40040c: not((rank(stoch_d) < 0.6072 or (crosses_below(cc | lab_search | 2026-09-24 | +0.00% |
| Lab 4191e9: ((rank(price_above_sma200) > 0.429 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 41ff50: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 477105: (((roc_10 < -2.9715 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab 4939d8: ((rank(price_above_sma50) > 0.4314 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 49e197: ((rank(golden_cross) > 0.8594 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 4aa629: ((rank(golden_cross) > 0.8445 and chaikin_osc <  | lab_search | 2026-09-24 | +0.00% |
| Lab 4c3d36: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 5030c4: (((roc_10 < -2.9715 or macd < 1) and rank(golden | lab_search | 2026-09-24 | +0.00% |
| Lab 507de5: ((rank(price_above_sma200) > 0.4632 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 52a036: (((roc_10 < -2.9715 or price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab 536fd2: ((rank(price_above_sma50) > 0.4494 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 538bb1: crosses_below(rank(obv_rising), 0.104) | lab_search | 2026-09-24 | +0.00% |
| Lab 55a3e3: not((rank(stoch_d) < 0.6149 or (crosses_above(cc | lab_search | 2026-09-24 | +0.00% |
| Lab 56c21e: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Lab 5781c2: ((rank(price_above_sma200) > 0.8819 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 57fa72: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab 58be39: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 591639: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 5cb78f: ((rank(price_above_sma50) > 0.4414 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 5e1c41: ((rank(rsi_14) > 0.7183 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 5e5918: ((rank(golden_cross) > 0.8445 and vol_ratio > 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 62532b: ((rank(price_above_sma50) > 0.4812 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 62b7a1: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 646715: ((rank(golden_cross) > 0.8445 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 654f54: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 67c433: ((rank(rsi_14) > 0.5253 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 697130: (((cci_20 < -2.9715 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab 6988de: ((rank(price_above_sma200) > 0.4738 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 6d4947: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Lab 70130c: ((rank(rsi_14) > 0.471 and price_above_sma200 <  | lab_search | 2026-09-24 | +0.00% |
| Lab 701bb5: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Lab 753ef9: (((roc_10 < -2.9715 or macd < 1) and rank(golden | lab_search | 2026-09-24 | +0.00% |
| Lab 7559c5: ((rank(rsi_14) > 0.4858 and pct_off_52w_low < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 76491a: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 77afdc: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab 790d74: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab 79101b: ((rank(price_above_sma50) > 0.4634 and pct_off_5 | lab_search | 2026-09-24 | +0.00% |
| Lab 7a5d3c: ((rank(golden_cross) > 0.8445 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 7bf410: ((rank(price_above_sma200) > 0.4694 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 7c6769: ((rank(rsi_14) > 0.7 and macd_signal < 0.5) and  | lab_search | 2026-09-24 | +0.00% |
| Lab 7cf159: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 7d4824: ((rank(price_above_sma50) > 0.4343 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab 7de3e7: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab 7ff71f: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 8420df: ((rank(rsi_14) > 0.4303 and bb_pct < 0.5) and rs | lab_search | 2026-09-24 | +0.00% |
| Lab 84623b: crosses_below(rank(obv_rising), 0.1033) | lab_search | 2026-09-24 | +0.00% |
| Lab 874d38: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Lab 87987f: ((rank(price_above_sma50) > 0.4634 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 87f34a: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | +0.00% |
| Lab 882b08: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab 88a1ff: ((rank(golden_cross) > 0.8445 and price_above_sm | lab_search | 2026-09-24 | +0.00% |
| Lab 88e1e2: ((rank(golden_cross) > 0.8445 and chaikin_osc <  | lab_search | 2026-09-24 | +0.00% |
| Lab 88f921: not((rank(stoch_d) < 0.5693 or (cci_20 > vol_rat | lab_search | 2026-09-24 | +0.00% |
| Lab 8c307f: ((rank(rsi_14) > 0.5756 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab 8c3b8c: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 8e5462: ((rank(rsi_14) > 0.6162 and atr_14 > 1.0863) and | lab_search | 2026-09-24 | +0.00% |
| Lab 8f8d16: ((rank(price_above_sma200) > 0.429 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 9051ab: ((rank(price_above_sma50) > 0.4844 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab 90599a: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | +0.00% |
| Lab 91dc1c: ((rank(price_above_sma200) > 0.4546 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 9858b1: rank(obv_rising) < 0.0877 | lab_search | 2026-09-24 | +0.00% |
| Lab 9936b1: ((rank(golden_cross) > 0.8445 and macd < 0.5) an | lab_search | 2026-09-24 | +0.00% |
| Lab 9c2500: ((rank(price_above_sma50) > 0.424 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Lab 9e22b2: ((rank(price_above_sma50) > 0.4494 and pct_off_5 | lab_search | 2026-09-24 | +0.00% |
| Lab 9f60d6: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab 9fff08: (((roc_10 < -3.6649 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab a01fd2: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab a1ab78: ((rank(price_above_sma50) > 0.4494 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab a21fac: ((rank(golden_cross) > 0.8445 and chaikin_osc <  | lab_search | 2026-09-24 | +0.00% |
| Lab a26754: ((rank(rsi_14) > 0.5173 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab a4784c: ((rank(price_above_sma200) > 0.4746 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab a8a8d5: ((rank(rsi_14) > 0.5989 and atr_14 > 0.7414) and | lab_search | 2026-09-24 | +0.00% |
| Lab a9d1bd: ((rank(rsi_14) > 0.7 and chaikin_osc < 0.5) and  | lab_search | 2026-09-24 | +0.00% |
| Lab aa283b: ((rank(price_above_sma50) > 0.4314 and vol_ratio | lab_search | 2026-09-24 | +0.00% |
| Lab abbbd7: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab abde91: (((roc_10 < -3.6409 or crosses_below(price_above | lab_search | 2026-09-24 | +0.00% |
| Lab aca047: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab adb231: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab af54d9: ((rank(rsi_14) > 0.5009 and golden_cross < 0.5)  | lab_search | 2026-09-24 | +0.00% |
| Lab b41393: ((rank(price_above_sma50) > 0.4628 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab b4271a: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab b46512: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab b66baf: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab b68436: (((roc_10 < -2.376 and price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab b891ee: ((rank(rsi_14) > 0.38 and drawdown_200 > 0.3668) | lab_search | 2026-09-24 | +0.00% |
| Lab ba2f8e: ((rank(golden_cross) > 0.8445 and vol_ratio > 0. | lab_search | 2026-09-24 | +0.00% |
| Lab ba3acb: ((rank(price_above_sma200) > 0.8819 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab bab81f: ((rank(price_above_sma50) > 0.429 and macd < 0.5 | lab_search | 2026-09-24 | +0.00% |
| Lab bb7c17: ((rank(rsi_14) > 0.5282 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab bb878f: ((rank(price_above_sma50) > 0.4343 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab bbf384: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab bcf035: ((rank(price_above_sma50) > 0.456 and macd < 0.5 | lab_search | 2026-09-24 | +0.00% |
| Lab bd178f: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab bf4db5: ((rank(price_above_sma50) > 0.4844 and macd < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab c07745: (((roc_10 < -2.9715 or price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab c2f07a: ((rank(golden_cross) > 0.8445 and vol_ratio > 0. | lab_search | 2026-09-24 | +0.00% |
| Lab c32a79: ((rank(rsi_14) > 0.6008 and price_above_sma200 < | lab_search | 2026-09-24 | +0.00% |
| Lab c437e2: (((crosses_below(roc_10, -2.9715) or vol_ratio < | lab_search | 2026-09-24 | +0.00% |
| Lab c4f668: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab c582b2: (((cci_20 < -2.9715 and price_above_sma50 < 1) a | lab_search | 2026-09-24 | +0.00% |
| Lab c6553d: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab c73a6e: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab ce3913: ((rank(price_above_sma200) > 0.4551 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab d06f46: ((rank(price_above_sma200) > 0.478 and golden_cr | lab_search | 2026-09-24 | +0.00% |
| Lab d2c102: crosses_above(rank(obv_rising), 0.0854) | lab_search | 2026-09-24 | +0.00% |
| Lab d37dba: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab d47e80: ((rank(price_above_sma50) > 0.443 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Lab d49098: (((roc_10 < -2.9715 or price_above_sma50 < 1) an | lab_search | 2026-09-24 | +0.00% |
| Lab d5329f: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab d5b1d4: crosses_below(rank(obv_rising), 0.1048) | lab_search | 2026-09-24 | +0.00% |
| Lab d7d233: crosses_below(rank(obv_rising), 0.1069) | lab_search | 2026-09-24 | +0.00% |
| Lab d96f23: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab da5668: ((rank(rsi_14) > 0.4307 and cci_20 < 0.5) and rs | lab_search | 2026-09-24 | +0.00% |
| Lab dcd9df: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab dd6493: (((crosses_below(roc_10, -2.9715) or price_above | lab_search | 2026-09-24 | +0.00% |
| Lab dd8d31: rank(obv_rising) < 0.0961 | lab_search | 2026-09-24 | +0.00% |
| Lab df0b48: ((rank(rsi_14) > 0.4238 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | +0.00% |
| Lab e24880: (((roc_10 < -2.9715 or obv_rising < 1) and rank( | lab_search | 2026-09-24 | +0.00% |
| Lab e4b6e0: crosses_above(rank(price_above_sma50), 0.077) | lab_search | 2026-09-24 | +0.00% |
| Lab e6579b: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab e84d79: ((rank(rsi_14) > 0.7 and golden_cross < 0.5) and | lab_search | 2026-09-24 | +0.00% |
| Lab e9123b: rank(obv_rising) < 0.1058 | lab_search | 2026-09-24 | +0.00% |
| Lab ea4764: rank(obv_rising) < 0.1011 | lab_search | 2026-09-24 | +0.00% |
| Lab eb2c87: ((rank(golden_cross) > 0.8445 and chaikin_osc <  | lab_search | 2026-09-24 | +0.00% |
| Lab ec8f05: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | +0.00% |
| Lab ee2b7a: ((rank(price_above_sma200) > 0.8819 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab ef7060: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab f0fb0a: ((rank(price_above_sma50) > 0.4657 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab f10a90: ((rank(golden_cross) > 0.8445 and macd < 0.5) an | lab_search | 2026-09-24 | +0.00% |
| Lab f21310: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | +0.00% |
| Lab f3e4b1: not((rank(stoch_d) < 0.5893 or (cci_20 > roc_10  | lab_search | 2026-09-24 | +0.00% |
| Lab f46383: (((cci_20 < -2.9715 or crosses_below(price_above | lab_search | 2026-09-24 | +0.00% |
| Lab f52fcb: not((rank(stoch_d) < 0.6626 or (cci_20 > macd or | lab_search | 2026-09-24 | +0.00% |
| Lab f5f05c: ((rank(golden_cross) > 0.8445 and vol_ratio > 0. | lab_search | 2026-09-24 | +0.00% |
| Lab f6eea5: (((crosses_below(roc_10, -2.9715) or atr_14 > 1) | lab_search | 2026-09-24 | +0.00% |
| Lab f724b2: ((rank(price_above_sma200) > 0.4638 and price_ab | lab_search | 2026-09-24 | +0.00% |
| Lab f7a5b4: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab f99315: ((rank(price_above_sma50) > 0.4414 and golden_cr | lab_search | 2026-09-24 | +0.00% |
| Lab fa547c: ((rank(price_above_sma50) > 0.4343 and atr_14 >  | lab_search | 2026-09-24 | +0.00% |
| Lab faf9c7: ((rank(price_above_sma50) > 0.4494 and pct_off_5 | lab_search | 2026-09-24 | +0.00% |
| Lab fc5899: ((rank(price_above_sma200) > 0.4638 and golden_c | lab_search | 2026-09-24 | +0.00% |
| Lab fdf5e0: ((rank(golden_cross) > 0.8445 and golden_cross > | lab_search | 2026-09-24 | +0.00% |
| Lab ff9ebd: ((rank(price_above_sma50) > 0.478 and price_abov | lab_search | 2026-09-24 | +0.00% |
| Momentum and Insider Trading · reproduction | kf_momentum | 2026-09-25 | +0.00% |
| Pre Holiday hold=1 stop=2 | pre_holiday | 2026-09-24 | +0.00% |
| Pre Holiday hold=1 stop=3 | pre_holiday | 2026-09-24 | +0.00% |
| Pre Holiday hold=2 stop=2 | pre_holiday | 2026-09-24 | +0.00% |
| Pre Holiday hold=2 stop=3 | pre_holiday | 2026-09-24 | +0.00% |
| Predicting Stock Returns of Past-Winner Stocks and Bond Retu | kf_breakout | 2026-09-25 | +0.00% |
| Price Momentum and Trading Volume · reproduction | kf_momentum | 2026-09-25 | +0.00% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-10-16 | +0.00% |
| Size Matters, if You Control Your Junk · reproduction · univ | kf_size | 2026-10-02 | +0.00% |
| Streaks in Daily Returns · reproduction | kf_reversal | 2026-09-25 | +0.00% |
| The Efficiency of Linear Value Models for Stock Selection ac | kf_value | 2026-09-25 | +0.00% |
| The Long-Term Price-Earnings Ratio · reproduction | kf_value | 2026-09-25 | +0.00% |
| The Momentum Gap and Return Predictability · reproduction | kf_momentum | 2026-09-25 | +0.00% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-10-08 | +0.00% |
| Value + momentum · reproduction · lookback 1.5 | kf_hybrid | 2026-10-01 | +0.00% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-10-12 | +0.00% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | +0.00% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | +0.00% |
| january_illiquid v1 | january_illiquid | 2026-09-24 | +0.00% |
| january_illiquid v1 | january_illiquid | 2026-09-24 | +0.00% |
| january_illiquid v1 | january_illiquid | 2026-09-24 | +0.00% |
| january_illiquid v1 | january_illiquid | 2026-09-24 | +0.00% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-11-10 | +0.00% |
| kf_hybrid v2 (longer_hold) | kf_hybrid | 2026-10-28 | +0.00% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-19 | +0.00% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-26 | +0.00% |
| kf_quality v2 (longer_hold) | kf_quality | 2026-11-10 | +0.00% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-11-10 | +0.00% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-10-09 | +0.00% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-02 | +0.00% |
| kf_value v2 (longer_hold) | kf_value | 2026-10-01 | +0.00% |
| kf_value v2 (longer_hold) | kf_value | 2026-10-05 | +0.00% |
| magic_formula · reproduction | kf_quality | 2026-09-25 | +0.00% |
| pre_holiday v2 (longer_hold) | pre_holiday | 2026-09-24 | +0.00% |
| pre_holiday v2 (longer_hold) | pre_holiday | 2026-09-24 | +0.00% |
| pre_holiday v2 (longer_hold) | pre_holiday | 2026-09-24 | +0.00% |
| pre_holiday v2 (longer_hold) | pre_holiday | 2026-09-24 | +0.00% |
| quality_value · reproduction · universe large_cap | kf_quality | 2026-10-22 | +0.00% |
| quality_value · reproduction · universe liquid | kf_quality | 2026-10-22 | +0.00% |
| Tax expense momentum · reproduction | kf_earnings_surprise | 2026-09-25 | -0.02% |
| Lab 1f7ce8: ((rank(price_above_sma50) > 0.4238 and pct_off_5 | lab_search | 2026-09-24 | -0.02% |
| Lab 46879d: ((rank(price_above_sma50) > 0.4314 and pct_off_5 | lab_search | 2026-09-24 | -0.02% |
| Lab c0988d: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.03% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction · | kf_value | 2026-10-21 | -0.03% |
| Lab 37b67b: ((rank(rsi_14) > 0.7 and cci_20 < 0.3381) and rs | lab_search | 2026-09-24 | -0.03% |
| kf_other v2 (longer_hold) | kf_other | 2026-10-19 | -0.04% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -0.04% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -0.04% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -0.04% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -0.04% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -0.04% |
| Lab 0ce541: ((rank(price_above_sma200) < 0.7 and pct_off_52w | lab_search | 2026-09-24 | -0.04% |
| Lab b312da: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.04% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-10-13 | -0.04% |
| COMBINING VALUE AND MOMENTUM · reproduction · holding_period | kf_hybrid | 2026-09-25 | -0.04% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-10-22 | -0.05% |
| Lab 28fb7f: ((rank(price_above_sma50) > 0.4449 and pct_off_5 | lab_search | 2026-09-24 | -0.05% |
| Value Investing: Investing for Grown Ups? · reproduction · e | kf_value | 2026-10-19 | -0.05% |
| Value Investing: Investing for Grown Ups? · reproduction · h | kf_value | 2026-10-19 | -0.05% |
| Value Investing: Investing for Grown Ups? · reproduction · u | kf_value | 2026-10-19 | -0.05% |
| Returns to Value Investing: Fundamentals or Limits to Arbitr | kf_fundamental | 2026-10-13 | -0.05% |
| piotroski_value · reproduction · stop -1.0 | kf_quality | 2026-10-23 | -0.06% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | -0.08% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | -0.08% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | -0.08% |
| kf_hybrid v2 (longer_hold) | kf_hybrid | 2026-10-30 | -0.08% |
| Lab a3c02b: ((rank(price_above_sma50) > 0.4435 and obv_risin | lab_search | 2026-09-24 | -0.08% |
| Lab a3fb2a: ((rank(price_above_sma50) > 0.4435 and bb_pct <  | lab_search | 2026-09-24 | -0.08% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | -0.09% |
| Lab 06e4d5: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Lab 1c1a7e: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Lab 399866: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Lab f9c85e: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Lab 9519c4: ((rank(price_above_sma50) > 0.424 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Lab aa25df: ((rank(price_above_sma50) > 0.4435 and pct_off_5 | lab_search | 2026-09-24 | -0.09% |
| Lab aba110: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Lab ad31e2: ((rank(price_above_sma50) > 0.4414 and pct_off_5 | lab_search | 2026-09-24 | -0.09% |
| Lab d8fb7b: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -0.09% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | -0.10% |
| Lab b98ec5: not((rank(macd) < 0.805 or (cci_20 > macd_hist o | lab_search | 2026-09-24 | -0.10% |
| Lab e4e511: ((rank(price_above_sma50) > 0.4414 and pct_off_5 | lab_search | 2026-09-24 | -0.10% |
| Lab 2b472d: ((rank(price_above_sma50) > 0.4241 and pct_off_5 | lab_search | 2026-09-24 | -0.11% |
| Lab 4d2b90: ((rank(price_above_sma50) > 0.4241 and pct_off_5 | lab_search | 2026-09-24 | -0.11% |
| Lab d676d4: ((rank(price_above_sma50) > 0.4241 and pct_off_5 | lab_search | 2026-09-24 | -0.11% |
| bollinger_reversion · reproduction | kf_mean_reversion | 2026-09-25 | -0.11% |
| Lab dcedd0: ((rank(price_above_sma50) > 0.2787 and pct_off_5 | lab_search | 2026-09-24 | -0.11% |
| Lab 638832: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.12% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | -0.13% |
| Lab 53c0ae: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5225) | lab_search | 2026-09-24 | -0.13% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | -0.14% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | -0.14% |
| Factoring in the Low-Volatility Factor · reproduction · exit | kf_low_volatility | 2026-09-30 | -0.14% |
| Factoring in the Low-Volatility Factor · reproduction · univ | kf_low_volatility | 2026-09-30 | -0.14% |
| ACCRUALS, CASH FLOWS AND THE POST-EARNINGS ANNOUNCEMENT DRIF | kf_earnings_surprise | 2026-09-25 | -0.14% |
| Lab a05464: ((rank(rsi_14) > 0.4233 and price_above_sma200 < | lab_search | 2026-09-24 | -0.15% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-10-22 | -0.16% |
| Lab 09e42a: not((rank(stoch_d) < 0.5384 or (cci_20 > vol_rat | lab_search | 2026-09-24 | -0.17% |
| Lab cae5fe: not(((chaikin_osc > -919416 or willr_14 > -94.59 | lab_search | 2026-09-24 | -0.20% |
| Relative Strength hold=40 q=0.85 stop=2.5 | relative_strength | 2026-09-24 | -0.21% |
| Lab ce07eb: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.23% |
| Tax expense momentum · reproduction · stop -1.0 | kf_earnings_surprise | 2026-10-07 | -0.24% |
| piotroski_value · reproduction · universe liquid | kf_quality | 2026-10-23 | -0.24% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | -0.25% |
| Lab 673ea6: ((rank(dollar_volume_20) > 0.5705 and price_abov | lab_search | 2026-09-24 | -0.28% |
| kf_hybrid v1 | kf_hybrid | 2026-09-24 | -0.29% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | -0.30% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality_stop6x | 2026-10-20 | -0.30% |
| Fcf To Price hold=40 q=0.8 stop=5 · stop 6x ATR | fcf_to_price_stop6x | 2026-10-20 | -0.30% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-11-06 | -0.30% |
| Lab 3b641b: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.31% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -0.31% |
| rsi_reversion v2 (longer_hold) | rsi_reversion | 2026-09-24 | -0.32% |
| Finding Consistent Trends with Strong Momentum – Rsi for Tre | kf_momentum | 2026-09-25 | -0.32% |
| THE VALUE IN FUNDAMENTAL ACCOUNTING INFORMATION · reproducti | kf_value | 2026-10-20 | -0.33% |
| Lab 8ba724: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.34% |
| Lab 78c9a0: not(((chaikin_osc > -952682 or willr_14 > -82.26 | lab_search | 2026-09-24 | -0.34% |
| etf_rotation_assets v1 | etf_rotation_assets | 2026-09-24 | -0.35% |
| etf_rotation_assets v1 | etf_rotation_assets | 2026-09-24 | -0.35% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | -0.35% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | -0.35% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | -0.35% |
| Lab e42be1: ((rank(dollar_volume_20) > 0.7 and price_above_s | lab_search | 2026-09-24 | -0.36% |
| Teaching Slides on Short and Long Horizon Behavioral Factors | kf_hybrid | 2026-10-01 | -0.36% |
| Is the Growth-value Anomaly Related to the Asset Growth Anom | kf_value | 2026-10-22 | -0.37% |
| Lab 95b1ea: ((rank(rsi_14) > 0.7 and chaikin_osc < 0.5) and  | lab_search | 2026-09-24 | -0.37% |
| Value Investing: Investing for Grown Ups? · reproduction · s | kf_value | 2026-10-19 | -0.37% |
| Volatility Breakout hold=5 stop=3 vr=1.5 | volatility_breakout | 2026-09-24 | -0.37% |
| Value Investing: Investing for Grown Ups? · reproduction · s | kf_value | 2026-10-19 | -0.37% |
| Lab 973ca5: ((rank(dollar_volume_20) > 0.6096 and price_abov | lab_search | 2026-09-24 | -0.38% |
| kf_low_volatility v1 | kf_low_volatility | 2026-09-24 | -0.39% |
| Lab 33fff7: (((log_dollar_volume < 8.3238 and chaikin_osc <  | lab_search | 2026-09-24 | -0.39% |
| Why do Predicted Stock Issuers Earn Low · reproduction | kf_fundamental | 2026-09-25 | -0.39% |
| Lab 3a34b4: not(((chaikin_osc > -952682 or willr_14 > -86.53 | lab_search | 2026-09-24 | -0.40% |
| Lab 3f12ab: not(((chaikin_osc > -952682 or willr_14 > -86.53 | lab_search | 2026-09-24 | -0.40% |
| Lab 5022e0: ((rank(bb_pct) > 0.7 and vol_ratio > 0.5) and rs | lab_search | 2026-09-24 | -0.40% |
| st_volume_shock v2 (longer_hold) | st_volume_shock | 2026-09-24 | -0.41% |
| etf_rotation_sectors v1 | etf_rotation_sectors | 2026-09-24 | -0.42% |
| Lab 8ef456: ((rank(rsi_14) > 0.4238 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -0.42% |
| High Volatility q=0.2 | high_volatility | 2026-09-24 | -0.43% |
| Low Volatility q=0.2 | low_volatility | 2026-09-24 | -0.43% |
| Lab 819a39: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.44% |
| kf_analyst_revision v1 | kf_analyst_revision | 2026-09-24 | -0.44% |
| Deflating Profitability · reproduction · stop -1.0 | kf_quality | 2026-10-13 | -0.45% |
| etf_rotation_assets v1 | etf_rotation_assets | 2026-09-24 | -0.46% |
| Lab e5191d: not(((chaikin_osc > -952682 or willr_14 > -86.53 | lab_search | 2026-09-24 | -0.48% |
| Rsi Reversion hold=5 rsi=25 stop=2 | rsi_reversion | 2026-09-24 | -0.48% |
| Factoring in the Low-Volatility Factor · reproduction · stop | kf_low_volatility | 2026-09-30 | -0.49% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | -0.49% |
| COMBINING VALUE AND MOMENTUM · reproduction · universe large | kf_hybrid | 2026-09-25 | -0.50% |
| Factoring in the Low-Volatility Factor · reproduction · univ | kf_low_volatility | 2026-09-30 | -0.51% |
| Breakout 52W hold=10 near=0.97 stop=3 | breakout_52w | 2026-09-24 | -0.52% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | -0.53% |
| The Valuation of Loss Firms: A Stock Market Perspective · re | kf_value | 2026-10-01 | -0.54% |
| Lab c1bb1c: ((rank(adx_14) > 0.5361 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -0.55% |
| Using Firm Level Leverage as an Investment Strategy · reprod | kf_value | 2026-09-25 | -0.55% |
| Lab ad7e58: ((rank(cci_20) > 0.3368 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -0.55% |
| Lab 675592: ((rank(rsi_14) > 0.6587 and price_above_sma200 < | lab_search | 2026-09-24 | -0.57% |
| Free Cash Flows and Price Momentum · reproduction · universe | kf_momentum | 2026-10-21 | -0.58% |
| Free Cash Flows and Price Momentum · reproduction · universe | kf_momentum | 2026-10-21 | -0.58% |
| Market Timing with Moving Averages · reproduction | kf_trend | 2026-09-25 | -0.60% |
| Lab c9e472: ((rank(sma_50) < 0.7 and pct_off_52w_low > 0.535 | lab_search | 2026-09-24 | -0.60% |
| Why do Predicted Stock Issuers Earn Low · reproduction · uni | kf_fundamental | 2026-10-07 | -0.61% |
| Value + momentum · reproduction · universe large_cap | kf_hybrid | 2026-10-01 | -0.62% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | -0.63% |
| Rsi Reversion hold=5 rsi=25 stop=3 | rsi_reversion | 2026-09-24 | -0.66% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -0.66% |
| Lab d1a7ca: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -0.67% |
| Lab a51233: ((rank(rsi_14) > 0.7 and price_above_sma50 < 0.5 | lab_search | 2026-09-24 | -0.67% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-09-25 | -0.67% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-11-02 | -0.68% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | -0.69% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-10-08 | -0.70% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | -0.76% |
| The Value of Low Volatility · reproduction · universe large_ | kf_low_volatility | 2026-09-30 | -0.80% |
| etf_rotation_assets v1 | etf_rotation_assets | 2026-09-24 | -0.80% |
| Corporate investment, short-term return reversal, and stock  | kf_reversal | 2026-09-25 | -0.80% |
| Lab 84e6ff: ((rank(pct_of_52w_high) > 0.7 and pct_off_52w_lo | lab_search | 2026-09-24 | -0.81% |
| etf_rotation_assets v1 | etf_rotation_assets | 2026-09-24 | -0.82% |
| Lab 497688: ((rank(price_above_sma50) > 0.429 and bb_pct < 0 | lab_search | 2026-09-24 | -0.82% |
| Lab b01158: (((log_dollar_volume < 8.2379 and chaikin_osc <  | lab_search | 2026-09-24 | -0.84% |
| Lab ce4e82: ((rank(roc_10) < 0.6511 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -0.84% |
| Lab e63306: ((rank(bb_pct) > 0.3415 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -0.84% |
| rsi_reversion v2 (longer_hold) | rsi_reversion | 2026-09-24 | -0.85% |
| Value Book hold=60 q=0.8 stop=5 | value_book | 2026-09-24 | -0.86% |
| value_book v1 | value_book | 2026-09-24 | -0.86% |
| Lab f4ac61: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -0.86% |
| Rsi Reversion hold=5 rsi=30 stop=3 | rsi_reversion | 2026-09-24 | -0.86% |
| Profitability hold=40 q=0.9 stop=3 | profitability | 2026-09-24 | -0.88% |
| Profitability hold=60 q=0.9 stop=3 | profitability | 2026-09-24 | -0.88% |
| Standardized Unexpected Earnings · reproduction · universe l | kf_earnings_surprise | 2026-09-25 | -0.88% |
| ma_cross v2 (longer_hold) | ma_cross | 2026-09-24 | -0.90% |
| payday v2 (longer_hold) | payday | 2026-09-24 | -0.92% |
| Lab 76c19a: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -0.94% |
| Debt Reduction hold=40 n=63 stop=3 | debt_reduction | 2026-09-24 | -0.94% |
| Debt Reduction hold=60 n=63 stop=3 | debt_reduction | 2026-09-24 | -0.94% |
| Lab 4b918a: ((rank(price_above_sma50) > 0.4775 and macd_sign | lab_search | 2026-09-24 | -0.94% |
| breakout_52w v2 (longer_hold) | breakout_52w | 2026-09-24 | -0.95% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-10-21 | -0.97% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-10-21 | -0.97% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-10-21 | -0.97% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-10-21 | -0.97% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-10-21 | -0.97% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-10-21 | -0.97% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-10-21 | -0.97% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-10-21 | -0.97% |
| kf_volatility v3 (trend_filter) | kf_volatility | 2026-10-15 | -0.98% |
| Politician Buying buyers=2 hold=60 stop=3 | politician_buying | 2026-09-25 | -0.98% |
| Further Evidence on Analyst and Investor Mis-Weighting of  P | kf_analyst_revision | 2026-09-25 | -1.01% |
| Lab 5bb901: not(((chaikin_osc > -952682 or crosses_above(cha | lab_search | 2026-09-24 | -1.02% |
| The Halloween Effect in US Sectors · reproduction · universe | kf_seasonality | 2026-09-25 | -1.02% |
| Lab a7226c: ((rank(rsi_14) > 0.2241 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -1.02% |
| etf_rotation_assets v1 | etf_rotation_assets | 2026-09-24 | -1.02% |
| Lab a8fc55: ((rank(pct_off_52w_low) > 0.7 or crosses_above(g | lab_search | 2026-09-24 | -1.03% |
| cci_extreme · reproduction · holding_period 2.0 | kf_mean_reversion | 2026-10-01 | -1.04% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | -1.06% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | -1.06% |
| St Momentum 1D hold=2 q=0.95 stop=2 | st_momentum_1d | 2026-09-24 | -1.06% |
| st_momentum_1d v2 (longer_hold) | st_momentum_1d | 2026-09-24 | -1.06% |
| payday v2 (longer_hold) | payday | 2026-09-24 | -1.06% |
| kf_quality v2 (longer_hold) | kf_quality | 2026-10-16 | -1.07% |
| Lab 8f8d77: ((rank(log_dollar_volume) < 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -1.07% |
| The Market Timing Power of Moving Averages: · reproduction | kf_trend | 2026-09-25 | -1.08% |
| Lab 139405: (roc_10 < -10.9569 and crosses_above(pct_change( | lab_search | 2026-09-24 | -1.08% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | -1.08% |
| Lab eec4e9: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | -1.09% |
| Lab 2c9d40: ((delta(macd, 5) < -0.1815 and lag(cci_20, 10) < | lab_search | 2026-09-24 | -1.09% |
| obv_accumulation · reproduction · stop -1.0 | kf_momentum | 2026-11-03 | -1.11% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | -1.11% |
| Lab e99b03: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5575) | lab_search | 2026-09-24 | -1.13% |
| Lab 8ea2ee: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -1.14% |
| Lab 3d273d: ((rank(rsi_14) > 0.4864 and chaikin_osc < 0.5) a | lab_search | 2026-09-24 | -1.14% |
| Lab d9b55f: ((rank(dollar_volume_20) > 0.6284 and price_abov | lab_search | 2026-09-24 | -1.15% |
| Lab cf4532: ((rank(dollar_volume_20) > 0.7 and price_above_s | lab_search | 2026-09-24 | -1.16% |
| Breakout 52W hold=10 near=0.97 stop=2 | breakout_52w | 2026-09-24 | -1.21% |
| Standardized Unexpected Earnings · reproduction · exit 3.0 | kf_earnings_surprise | 2026-09-25 | -1.21% |
| kf_earnings_surprise v1 | kf_earnings_surprise | 2026-09-24 | -1.21% |
| Lab a36adc: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.24% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | -1.24% |
| Lab 08feca: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.25% |
| Lab dcb7df: ((rank(roc_10) < 0.7 and pct_off_52w_low > 0.500 | lab_search | 2026-09-24 | -1.25% |
| Quality Piotroski f=8 hold=40 stop=5 | quality_piotroski | 2026-09-24 | -1.26% |
| Quality Piotroski f=8 hold=60 stop=5 | quality_piotroski | 2026-09-24 | -1.26% |
| obv_accumulation · reproduction · stop 1.0 | kf_momentum | 2026-11-03 | -1.26% |
| Rsi Reversion hold=10 rsi=25 stop=2 | rsi_reversion | 2026-09-24 | -1.29% |
| rsi_reversion v2 (longer_hold) | rsi_reversion | 2026-09-24 | -1.29% |
| Lab 55718e: not((rank(stoch_d) < 0.5555 or (cci_20 > bb_pct  | lab_search | 2026-09-24 | -1.31% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-10-08 | -1.32% |
| Lab 6373a1: ((rank(rsi_14) > 0.484 and golden_cross < 0.5) a | lab_search | 2026-09-24 | -1.33% |
| Free Cash Flows and Price Momentum · reproduction · lookback | kf_momentum | 2026-10-21 | -1.35% |
| Lab ad2231: ((rank(rsi_14) > 0.4238 and drawdown_200 > 0.251 | lab_search | 2026-09-24 | -1.35% |
| Lab 3202cd: ((rank(price_above_sma50) > 0.4844 and chaikin_o | lab_search | 2026-09-24 | -1.35% |
| Lab 185b6f: ((rank(price_above_sma50) > 0.3368 and pct_off_5 | lab_search | 2026-09-24 | -1.36% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -1.36% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -1.36% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -1.36% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -1.36% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -1.36% |
| Lab aadfc9: pct_change(sma_50, 3) < -0.0236 | lab_search | 2026-09-24 | -1.37% |
| Buyback hold=40 iss=-0.01 stop=3 | buyback | 2026-09-24 | -1.37% |
| Buyback hold=60 iss=-0.01 stop=3 | buyback | 2026-09-24 | -1.37% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | -1.38% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | -1.38% |
| earnings_surprise v1 | earnings_surprise | 2026-09-24 | -1.38% |
| obv_accumulation · reproduction · universe large_cap | kf_momentum | 2026-11-03 | -1.39% |
| Lab a48ee7: (rsi_14 < 36.8731 and pct_off_52w_low > 0.6912) | lab_search | 2026-09-24 | -1.40% |
| obv_accumulation · reproduction · exit 3.0 | kf_momentum | 2026-11-03 | -1.41% |
| obv_accumulation · reproduction · holding_period 0.5 | kf_momentum | 2026-11-03 | -1.41% |
| obv_accumulation · reproduction · holding_period 2.0 | kf_momentum | 2026-11-03 | -1.41% |
| obv_accumulation · reproduction · universe liquid | kf_momentum | 2026-11-03 | -1.41% |
| Lab 202482: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5038) | lab_search | 2026-09-24 | -1.42% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -1.42% |
| Lab 3adc0f: ((rank(obv_rising) > 0.3247 and pct_off_52w_low  | lab_search | 2026-09-24 | -1.43% |
| Value + momentum · reproduction | kf_hybrid | 2026-09-25 | -1.43% |
| Lab 8de481: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.43% |
| IMPACT OF CASH HOLDINGS ON INVESTMENT VALUE · reproduction · | kf_value | 2026-10-21 | -1.44% |
| Do Investors Overvalue Firms with Bloated Balance Sheets? ·  | kf_value | 2026-09-25 | -1.44% |
| Trend Following hold=40 stop=3.5 | trend_following | 2026-09-24 | -1.46% |
| trend_following v2 (longer_hold) | trend_following | 2026-09-24 | -1.46% |
| trend_following v2 (longer_hold) | trend_following | 2026-09-24 | -1.46% |
| Lab 59c1b9: (rsi_14 < 35.821 and pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | -1.47% |
| Lab 178add: ((rank(log_dollar_volume) > 0.7 and atr_14 > 0.5 | lab_search | 2026-09-24 | -1.47% |
| kf_breakout v1 | kf_breakout | 2026-09-24 | -1.47% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-10-09 | -1.48% |
| Earnings Surprise age=10 hold=40 q=0.9 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | -1.48% |
| Earnings Surprise age=10 hold=60 q=0.9 · stop 6x ATR | earnings_surprise_stop6x | 2026-10-20 | -1.48% |
| Lab 9d5174: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5396) | lab_search | 2026-09-24 | -1.50% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-10-21 | -1.51% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-10-21 | -1.51% |
| Lab 315b9e: (rsi_14 < 33.7551 and pct_off_52w_low > 0.4963) | lab_search | 2026-09-24 | -1.51% |
| Lab 24c66e: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -1.52% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | -1.52% |
| Lab 1b7b56: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.52% |
| Free Cash Flows and Price Momentum · reproduction · exit 3.0 | kf_momentum | 2026-10-21 | -1.52% |
| Free Cash Flows and Price Momentum · reproduction · holding_ | kf_momentum | 2026-10-21 | -1.52% |
| Free Cash Flows and Price Momentum · reproduction · holding_ | kf_momentum | 2026-10-21 | -1.52% |
| Free Cash Flows and Price Momentum · reproduction · stop -1. | kf_momentum | 2026-10-21 | -1.52% |
| Lab e372d2: ((rank(rsi_14) > 0.2712 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -1.53% |
| Value Book hold=60 q=0.8 stop=3 | value_book | 2026-09-24 | -1.53% |
| value_book v1 | value_book | 2026-09-24 | -1.53% |
| Relative Strength hold=20 q=0.95 stop=3.5 | relative_strength | 2026-09-25 | -1.54% |
| piotroski_value · reproduction | kf_quality | 2026-09-25 | -1.54% |
| Lab 2b72d7: ((rank(dollar_volume_20) > 0.9499 and price_abov | lab_search | 2026-09-24 | -1.55% |
| Lab 5d9801: not(((chaikin_osc > -919416 or crosses_above(wil | lab_search | 2026-09-24 | -1.56% |
| Lab b71ef8: ((rank(rsi_14) > 0.8594 and macd_signal < 0.5) a | lab_search | 2026-09-24 | -1.58% |
| Lab 54ef0c: pct_change(sma_50, 3) < -0.0264 | lab_search | 2026-09-24 | -1.58% |
| Factoring in the Low-Volatility Factor · reproduction · hold | kf_low_volatility | 2026-09-30 | -1.58% |
| Trend Following hold=40 stop=2.5 | trend_following | 2026-09-24 | -1.59% |
| trend_following v2 (longer_hold) | trend_following | 2026-09-24 | -1.59% |
| trend_following v2 (longer_hold) | trend_following | 2026-09-24 | -1.59% |
| Lab 220ec3: ((rank(rsi_14) > 0.3711 and drawdown_200 > 0.427 | lab_search | 2026-09-24 | -1.60% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -1.60% |
| Lab aaa868: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.61% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -1.62% |
| Lab fc6f3e: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.63% |
| Free Cash Flows and Price Momentum · reproduction | kf_momentum | 2026-09-25 | -1.64% |
| Lab 0d7883: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.66% |
| Lab 94209b: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5907) | lab_search | 2026-09-24 | -1.70% |
| Lab 8af704: ((rank(roc_10) < 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | -1.71% |
| Free Cash Flows and Price Momentum · reproduction · stop 1.0 | kf_momentum | 2026-10-21 | -1.72% |
| Lab 259b4c: ((rank(log_dollar_volume) > 0.9258 and atr_14 >  | lab_search | 2026-09-24 | -1.73% |
| Volatility Breakout hold=5 stop=3 vr=2 | volatility_breakout | 2026-09-24 | -1.74% |
| Relative Strength hold=20 q=0.95 stop=2.5 | relative_strength | 2026-09-24 | -1.75% |
| Lab 69b433: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.75% |
| Lab 331406: ((rank(golden_cross) > 0.7 and vol_ratio > 0.5)  | lab_search | 2026-09-24 | -1.76% |
| The Greater Market Mis-valuation of Accruals when the Stock  | kf_quality | 2026-09-25 | -1.77% |
| St Rsi Oversold hold=3 rsi=25 stop=2.5 | st_rsi_oversold | 2026-09-24 | -1.78% |
| Relative Strength hold=40 q=0.85 stop=3.5 | relative_strength | 2026-09-24 | -1.79% |
| Bollinger Reversion band=0.05 hold=5 stop=3 | bollinger_reversion | 2026-09-25 | -1.83% |
| Lab ca1a53: ((rank(willr_14) > 0.3415 and pct_off_52w_low >  | lab_search | 2026-09-24 | -1.84% |
| Volatility Contraction hold=20 stop=3 zc=-1.5 | volatility_contraction | 2026-09-24 | -1.86% |
| Size Matters, if You Control Your Junk · reproduction · stop | kf_size | 2026-10-02 | -1.91% |
| Size Matters, if You Control Your Junk · reproduction · stop | kf_size | 2026-10-02 | -1.91% |
| Lab 6bc783: (not((crosses_above(price_above_sma50, macd_sign | lab_search | 2026-09-24 | -1.93% |
| Short- and Long-Horizon Behavioral Factors · reproduction ·  | kf_factor | 2026-10-08 | -1.94% |
| Lab fc629b: ((rank(rsi_14) < 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | -1.94% |
| Price and Earning Momentum · reproduction · stop -1.0 | kf_momentum | 2026-09-28 | -1.95% |
| Standardized Unexpected Earnings · reproduction · holding_pe | kf_earnings_surprise | 2026-09-25 | -1.95% |
| Lab c5b122: ((rank(macd) > 0.7 and roc_10 < 0.5) and rsi_14  | lab_search | 2026-09-24 | -1.99% |
| Lab e15007: ((rank(cci_20) > 0.7 and vol_ratio > 0.5) and rs | lab_search | 2026-09-24 | -1.99% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-20 | -1.99% |
| Lab bd38e9: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -1.99% |
| Relative Strength hold=20 q=0.85 stop=2.5 | relative_strength | 2026-09-24 | -2.00% |
| Lab 306c6c: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.00% |
| Short Interest q=0.1 | short_interest | 2026-09-24 | -2.00% |
| Short Interest q=0.1 | short_interest | 2026-09-24 | -2.00% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -2.01% |
| Lab 8aaea8: (dollar_volume_20 > 1.69446e+07 and (crosses_bel | lab_search | 2026-09-24 | -2.01% |
| Lab a8a693: ((rank(rsi_14) > 0.7 or pct_off_52w_low > 0.5) a | lab_search | 2026-09-24 | -2.02% |
| Lab fa551a: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.02% |
| Lab 710fdc: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.04% |
| Lab afe7b4: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.04% |
| Lab 7c43d1: not((rank(stoch_d) < 0.5615 or (cci_20 > macd_hi | lab_search | 2026-09-24 | -2.04% |
| Lab 236b16: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.07% |
| Lab 00efc7: ((rank(price_above_sma50) > 0.4241 or pct_off_52 | lab_search | 2026-09-24 | -2.07% |
| January Effect in Stocks · reproduction · universe liquid | kf_seasonality | 2026-09-25 | -2.07% |
| Equity Performance of Zero Debt Firms vis-àvis Their Leverag | kf_quality | 2026-09-25 | -2.08% |
| rsi_reversion v2 (longer_hold) | rsi_reversion | 2026-09-24 | -2.08% |
| A Tale of Two Strategies: Cash Flow, Accruals and the · repr | kf_quality | 2026-09-25 | -2.08% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -2.09% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -2.09% |
| Lab 2b13bf: ((rank(bb_pct) > 0.2818 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -2.11% |
| Lab 388dea: (rsi_14 < 30 and pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | -2.12% |
| Lab d80cd9: ((rank(price_above_sma50) > 0.2628 and pct_off_5 | lab_search | 2026-09-24 | -2.12% |
| Ma Cross hold=20 stop=2 | ma_cross | 2026-09-24 | -2.13% |
| ma_cross v2 (longer_hold) | ma_cross | 2026-09-24 | -2.13% |
| Macd Cross hold=5 stop=3 | macd_cross | 2026-09-24 | -2.14% |
| Lab 4c208f: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.18% |
| Lab 6e7954: ((rank(price_above_sma50) > 0.4314 or pct_off_52 | lab_search | 2026-09-24 | -2.18% |
| Lab 0317bd: ((rank(rsi_14) > 0.7 or pct_off_52w_low > 0.5) a | lab_search | 2026-09-24 | -2.20% |
| Breakout 52W hold=10 near=0.99 stop=3 | breakout_52w | 2026-09-24 | -2.21% |
| Lab 2f660d: ((rank(price_above_sma50) > 0.4634 and price_abo | lab_search | 2026-09-24 | -2.22% |
| Rising 200 · Stop 5.0 b | momentum | 2026-09-04 | -2.24% |
| Relative Strength hold=20 q=0.95 stop=2.5 | relative_strength | 2026-09-25 | -2.24% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | -2.25% |
| Lab 174283: not(((chaikin_osc > -952682 or willr_14 > -94.59 | lab_search | 2026-09-24 | -2.25% |
| Earnings Yield hold=60 q=0.8 stop=5 | earnings_yield | 2026-09-24 | -2.26% |
| earnings_yield v1 | earnings_yield | 2026-09-24 | -2.26% |
| Growth Valuation hold=40 q=0.6 stop=5 | growth_valuation | 2026-09-24 | -2.26% |
| Growth Valuation hold=60 q=0.6 stop=5 | growth_valuation | 2026-09-24 | -2.26% |
| Value + momentum · reproduction · exit 3.0 | kf_hybrid | 2026-10-01 | -2.27% |
| Value + momentum · reproduction · holding_period 0.5 | kf_hybrid | 2026-10-01 | -2.27% |
| Value + momentum · reproduction · holding_period 2.0 | kf_hybrid | 2026-10-01 | -2.27% |
| Rsi Reversion hold=10 rsi=25 stop=3 | rsi_reversion | 2026-09-24 | -2.28% |
| rsi_reversion v2 (longer_hold) | rsi_reversion | 2026-09-24 | -2.28% |
| Factoring in the Low-Volatility Factor · reproduction · hold | kf_low_volatility | 2026-09-30 | -2.29% |
| Dividend q=0.8 | dividend | 2026-09-24 | -2.30% |
| Earnings Revision q=0.8 | earnings_revision | 2026-09-24 | -2.30% |
| Eps Growth q=0.8 | eps_growth | 2026-09-24 | -2.30% |
| Fcf Yield q=0.8 | fcf_yield | 2026-09-24 | -2.30% |
| Revenue Growth q=0.8 | revenue_growth | 2026-09-24 | -2.30% |
| Roic q=0.8 | roic | 2026-09-24 | -2.30% |
| Earnings Quality, Insider Trading, and Cost of Capital · rep | kf_quality | 2026-09-25 | -2.31% |
| Quality Momentum hold=20 q=0.7 stop=3.5 | quality_momentum | 2026-09-24 | -2.33% |
| Lab 8bea1b: ((rank(log_dollar_volume) > 0.6829 and pct_off_5 | lab_search | 2026-09-24 | -2.33% |
| kf_value v2 (longer_hold) | kf_value | 2026-10-02 | -2.37% |
| Lab fefab7: ((rank(dollar_volume_20) > 0.8927 and price_abov | lab_search | 2026-09-24 | -2.38% |
| Value + momentum · reproduction · stop -1.0 | kf_hybrid | 2026-10-01 | -2.38% |
| St Rsi Oversold hold=5 rsi=25 stop=2.5 | st_rsi_oversold | 2026-09-24 | -2.39% |
| rsi_reversion v3 (trend_filter) | rsi_reversion | 2026-09-25 | -2.39% |
| Lab c9b889: ((rank(rsi_14) > 0.7 and chaikin_osc < 0.4538) a | lab_search | 2026-09-24 | -2.40% |
| Payday hold=3 stop=3 | payday | 2026-09-24 | -2.42% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -2.43% |
| R&D Alpha: Investment Intensity and Long-Term Stock Returns  | kf_fundamental | 2026-09-25 | -2.47% |
| Turnover: Liquidity or Uncertainty? · reproduction · exit 3. | kf_liquidity | 2026-09-25 | -2.48% |
| Turnover: Liquidity or Uncertainty? · reproduction · holding | kf_liquidity | 2026-09-25 | -2.48% |
| Turnover: Liquidity or Uncertainty? · reproduction · holding | kf_liquidity | 2026-09-25 | -2.48% |
| Turnover: Liquidity or Uncertainty? · reproduction · univers | kf_liquidity | 2026-09-25 | -2.48% |
| Lab 99a69b: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.50% |
| Lab e0f581: ((rank(stoch_d) > 0.7 and price_above_sma200 < 0 | lab_search | 2026-09-24 | -2.55% |
| Lab ef9984: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -2.59% |
| St Momentum 1D hold=2 q=0.9 stop=2 | st_momentum_1d | 2026-09-24 | -2.60% |
| st_momentum_1d v2 (longer_hold) | st_momentum_1d | 2026-09-24 | -2.60% |
| Payday hold=3 stop=2 | payday | 2026-09-24 | -2.62% |
| Do Earnings Explain the January Effect? · reproduction · sto | kf_seasonality | 2026-10-13 | -2.62% |
| Lab 532093: ((rank(macd_signal) > 0.7 and vol_ratio > 0.5) a | lab_search | 2026-09-24 | -2.62% |
| Bollinger Reversion band=0.05 hold=10 stop=3 | bollinger_reversion | 2026-09-24 | -2.63% |
| bollinger_reversion v2 (longer_hold) | bollinger_reversion | 2026-09-24 | -2.63% |
| Volatility Breakout hold=10 stop=3 vr=1.5 | volatility_breakout | 2026-09-25 | -2.63% |
| Ma Cross hold=10 stop=2 | ma_cross | 2026-09-24 | -2.63% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-09-25 | -2.64% |
| Lab 79aeac: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.65% |
| Lab a437d7: ((rank(roc_10) < 0.7535 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -2.65% |
| Lab 1bfc79: ((rank(dollar_volume_20) > 0.7 and golden_cross  | lab_search | 2026-09-24 | -2.66% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-09-25 | -2.68% |
| 52 weeks high effect in stocks · reproduction · exit 3.0 | kf_breakout | 2026-09-25 | -2.69% |
| 52 weeks high effect in stocks · reproduction · holding_peri | kf_breakout | 2026-09-25 | -2.69% |
| 52 weeks high effect in stocks · reproduction · holding_peri | kf_breakout | 2026-09-25 | -2.69% |
| 52 weeks high effect in stocks · reproduction · universe liq | kf_breakout | 2026-09-25 | -2.69% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -2.69% |
| Rising 200 · Stop 5.0 a | momentum | 2026-09-04 | -2.70% |
| momentum_pullback · reproduction · stop 1.0 | kf_momentum | 2026-10-30 | -2.71% |
| Lab 169568: ((rank(willr_14) < 0.7 and pct_off_52w_low > 0.5 | lab_search | 2026-09-24 | -2.72% |
| Lab a45806: not(((chaikin_osc > -1.18925e+06 or willr_14 > - | lab_search | 2026-09-24 | -2.76% |
| Lab 15eb09: ((rank(log_dollar_volume) > 0.796 and pct_off_52 | lab_search | 2026-09-24 | -2.78% |
| Lab 073e58: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -2.79% |
| The returns of US capital market in the first days of purcha | kf_seasonality | 2026-09-25 | -2.80% |
| Lab 442667: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -2.81% |
| kf_seasonality v3 (trend_filter) | kf_seasonality | 2026-10-21 | -2.82% |
| st_momentum_1d v3 (trend_filter) | st_momentum_1d | 2026-09-25 | -2.85% |
| st_bollinger_low v2 (longer_hold) | st_bollinger_low | 2026-09-24 | -2.86% |
| st_bollinger_low v3 (trend_filter) | st_bollinger_low | 2026-09-24 | -2.86% |
| Lab 37a2df: not((rank(stoch_d) < 0.5082 or (cci_20 > rsi_14  | lab_search | 2026-09-24 | -2.86% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-01 | -2.87% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | -2.88% |
| Lab a72b1a: ((rank(price_above_sma50) > 0.3679 and pct_off_5 | lab_search | 2026-09-24 | -2.92% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -2.92% |
| Do Earnings Explain the January Effect? · reproduction · hol | kf_seasonality | 2026-10-13 | -2.92% |
| Value Book hold=40 q=0.9 stop=5 | value_book | 2026-09-24 | -2.94% |
| Value Book hold=60 q=0.9 stop=5 | value_book | 2026-09-24 | -2.94% |
| Earnings, Business Cycle and Stock Returns · reproduction ·  | kf_earnings_surprise | 2026-10-02 | -2.94% |
| Lab a874d3: ((rank(price_above_sma50) > 0.424 and chaikin_os | lab_search | 2026-09-24 | -2.94% |
| The Volatility Effect Revisited · reproduction · lookback 1. | kf_low_volatility | 2026-09-29 | -2.95% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-10-16 | -2.95% |
| Lab 26a349: ((rank(dollar_volume_20) > 0.8412 and price_abov | lab_search | 2026-09-24 | -2.96% |
| St Stoch Oversold hold=3 k=20 stop=2.5 | st_stoch_oversold | 2026-09-24 | -2.96% |
| Tax expense momentum · reproduction · lookback 1.5 | kf_earnings_surprise | 2026-10-07 | -2.96% |
| Lab 529335: (chaikin_osc < -2.24838e+06 and (rank(price_abov | lab_search | 2026-09-24 | -2.97% |
| Lab 557cc1: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -2.98% |
| Lab 4fbdc8: ((rank(rsi_14) > 0.2884 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -3.00% |
| Earnings Surprise q=0.8 | earnings_surprise | 2026-09-24 | -3.00% |
| Lab 0cee71: ((rank(dollar_volume_20) > 0.8803 and price_abov | lab_search | 2026-09-24 | -3.01% |
| Relative Strength hold=20 q=0.95 stop=3.5 | relative_strength | 2026-09-24 | -3.07% |
| Price and Earning Momentum · reproduction | kf_momentum | 2026-09-25 | -3.07% |
| Price and Earning Momentum · reproduction · exit 3.0 | kf_momentum | 2026-09-28 | -3.07% |
| Price and Earning Momentum · reproduction · holding_period 0 | kf_momentum | 2026-09-28 | -3.07% |
| Price and Earning Momentum · reproduction · holding_period 2 | kf_momentum | 2026-09-28 | -3.07% |
| Price and Earning Momentum · reproduction · universe liquid | kf_momentum | 2026-09-28 | -3.07% |
| Relative Strength hold=40 q=0.95 stop=2.5 | relative_strength | 2026-09-24 | -3.10% |
| relative_strength v2 (longer_hold) | relative_strength | 2026-09-24 | -3.10% |
| Tax expense momentum · reproduction · lookback 0.5 | kf_earnings_surprise | 2026-10-07 | -3.11% |
| Lab ec9ddb: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -3.12% |
| Price and Earning Momentum · reproduction · stop 1.0 | kf_momentum | 2026-09-28 | -3.12% |
| Lab f36e61: (((log_dollar_volume < 8.3238 and chaikin_osc <  | lab_search | 2026-09-24 | -3.13% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -3.14% |
| Lab 80a6b4: ((rank(stoch_d) > 0.3379 and pct_off_52w_low > 0 | lab_search | 2026-09-24 | -3.15% |
| Lab 06670a: ((rank(drawdown_200) < 0.7886 and pct_off_52w_lo | lab_search | 2026-09-24 | -3.16% |
| 52 weeks high effect in stocks · reproduction · stop -1.0 | kf_breakout | 2026-09-25 | -3.16% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-10-05 | -3.17% |
| Immediate and Subsequent Market Responses to Earnings Announ | kf_earnings_surprise | 2026-09-25 | -3.19% |
| Breakout 52W hold=20 near=0.99 stop=2 | breakout_52w | 2026-09-24 | -3.20% |
| breakout_52w v2 (longer_hold) | breakout_52w | 2026-09-24 | -3.20% |
| Lab 9d224f: ((rank(golden_cross) > 0.7 and price_above_sma20 | lab_search | 2026-09-24 | -3.23% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-09-25 | -3.24% |
| Driven to Distraction: Extraneous Events and Underreaction t | kf_earnings_surprise | 2026-09-25 | -3.24% |
| Fundamental momentum · reproduction | kf_earnings_surprise | 2026-09-25 | -3.24% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-09-25 | -3.24% |
| Post-earnings announcement drift · reproduction | kf_earnings_surprise | 2026-09-25 | -3.24% |
| Lab 3e6b96: ((rank(price_above_sma50) > 0.4238 and macd < 0. | lab_search | 2026-09-24 | -3.24% |
| Buyback hold=40 iss=-0.01 stop=5 | buyback | 2026-09-24 | -3.25% |
| Buyback hold=60 iss=-0.01 stop=5 | buyback | 2026-09-24 | -3.25% |
| Low Investment hold=40 q=0.2 stop=3 | low_investment | 2026-09-24 | -3.25% |
| Low Investment hold=60 q=0.2 stop=3 | low_investment | 2026-09-24 | -3.25% |
| Relative Strength hold=20 q=0.85 stop=3.5 | relative_strength | 2026-09-24 | -3.25% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-10-08 | -3.25% |
| kf_other v2 (longer_hold) | kf_other | 2026-10-20 | -3.27% |
| Rising 200 · Stop 5.0 c | momentum | 2026-09-04 | -3.31% |
| Lab 9be917: ((rank(price_above_sma50) > 0.4634 and vol_ratio | lab_search | 2026-09-24 | -3.32% |
| Lab 4b1705: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -3.33% |
| Lab be0486: ((rank(price_above_sma50) > 0.2785 and pct_off_5 | lab_search | 2026-09-24 | -3.33% |
| Lab e712ba: ((rank(price_above_sma50) > 0.3075 and pct_off_5 | lab_search | 2026-09-24 | -3.33% |
| The Acceleration Effect and Gamma Factor in Asset Pricing ·  | kf_momentum | 2026-09-25 | -3.33% |
| CONSERVATISM AND CROSS-SECTIONAL VARIATION IN THE POST-EARNI | kf_earnings_surprise | 2026-10-01 | -3.33% |
| volatility_breakout v3 (trend_filter) | volatility_breakout | 2026-09-25 | -3.33% |
| Debt Reduction hold=40 n=63 stop=5 | debt_reduction | 2026-09-24 | -3.33% |
| Debt Reduction hold=60 n=63 stop=5 | debt_reduction | 2026-09-24 | -3.33% |
| Lab d0fe10: ((rank(golden_cross) > 0.7 and price_above_sma20 | lab_search | 2026-09-24 | -3.34% |
| Macd Cross hold=5 stop=2 | macd_cross | 2026-09-24 | -3.34% |
| Changes in Price-Earnings Ratios and Excess Returns on the   | kf_value | 2026-10-19 | -3.38% |
| Lab 376d42: ((rank(price_above_sma50) > 0.349 and pct_off_52 | lab_search | 2026-09-24 | -3.41% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -3.41% |
| st_bollinger_low v2 | st_bollinger_low | 2026-09-24 | -3.42% |
| Lab 316b3e: ((rank(price_above_sma50) > 0.427 and chaikin_os | lab_search | 2026-09-24 | -3.43% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-09-25 | -3.43% |
| Bollinger Reversion band=0.05 hold=5 stop=2 | bollinger_reversion | 2026-09-25 | -3.43% |
| 52 weeks high effect in stocks · reproduction · universe lar | kf_breakout | 2026-09-25 | -3.43% |
| Lab a7ca04: ((rank(macd) < 0.7 and pct_off_52w_low > 0.5) an | lab_search | 2026-09-24 | -3.43% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-22 | -3.45% |
| Lab 562cb5: ((rank(macd) > 0.7 and price_above_sma200 < 0.5) | lab_search | 2026-09-24 | -3.45% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-10-09 | -3.46% |
| Lab 1f0f68: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -3.46% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -3.47% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -3.48% |
| Do Earnings Explain the January Effect? · reproduction | kf_seasonality | 2026-09-25 | -3.51% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-10-09 | -3.54% |
| Lab 2e2e6d: ((rank(price_above_sma50) > 0.3736 and pct_off_5 | lab_search | 2026-09-24 | -3.55% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -3.56% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -3.56% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -3.56% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -3.56% |
| Lab 0c3f21: ((rank(golden_cross) > 0.7 and bb_pct < 0.7128)  | lab_search | 2026-09-24 | -3.57% |
| Lab e8a236: not(((chaikin_osc > -952682 or willr_14 > -60.09 | lab_search | 2026-09-24 | -3.58% |
| Lab 4cd8ca: ((rank(sma_200) > 0.7 and price_above_sma200 > 0 | lab_search | 2026-09-24 | -3.59% |
| volatility_breakout v3 (trend_filter) | volatility_breakout | 2026-09-25 | -3.61% |
| Does Trend Following Work on Stocks · reproduction · stop -1 | kf_trend | 2026-10-14 | -3.61% |
| Lab 5b33f5: ((rank(price_above_sma50) > 0.3758 and pct_off_5 | lab_search | 2026-09-24 | -3.62% |
| St Stoch Oversold hold=2 k=20 stop=2.5 | st_stoch_oversold | 2026-09-24 | -3.64% |
| Lab 548bf0: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -3.66% |
| Lab cb8d58: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -3.67% |
| ma_cross v2 (longer_hold) | ma_cross | 2026-09-24 | -3.67% |
| Lab 4d7af7: ((rank(price_above_sma50) > 0.4695 and chaikin_o | lab_search | 2026-09-24 | -3.68% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-25 | -3.69% |
| Lab 00e0bb: ((rank(price_above_sma50) > 0.4435 and macd < 0. | lab_search | 2026-09-24 | -3.71% |
| Value Book hold=40 q=0.9 stop=3 | value_book | 2026-09-24 | -3.71% |
| Value Book hold=60 q=0.9 stop=3 | value_book | 2026-09-24 | -3.71% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -3.72% |
| Lab fc442d: (((pct_off_52w_low > 0.1661 or chaikin_osc > -1. | lab_search | 2026-09-24 | -3.73% |
| trend_following_adx · reproduction | kf_trend | 2026-09-25 | -3.74% |
| cci_extreme · reproduction · holding_period 0.5 | kf_mean_reversion | 2026-10-01 | -3.75% |
| Lab 83a930: ((rank(pct_off_52w_low) > 0.7 and macd < 0.5) an | lab_search | 2026-09-24 | -3.76% |
| Lab 2bea0a: ((rank(price_above_sma200) < 0.9258 and pct_off_ | lab_search | 2026-09-24 | -3.76% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | -3.77% |
| Lab dccd58: ((rank(price_above_sma50) > 0.438 and vol_ratio  | lab_search | 2026-09-24 | -3.78% |
| Value + momentum · reproduction · stop 1.0 | kf_hybrid | 2026-10-01 | -3.79% |
| Lab 2a148c: ((rank(dollar_volume_20) > 0.8623 and atr_14 > 0 | lab_search | 2026-09-24 | -3.81% |
| Do Investors Under-React to ROE? · reproduction · universe l | kf_quality | 2026-10-16 | -3.81% |
| Lab 1fed70: ((rank(dollar_volume_20) > 0.9538 and golden_cro | lab_search | 2026-09-24 | -3.81% |
| Lab 8e10e6: ((rank(price_above_sma50) > 0.4414 and pct_off_5 | lab_search | 2026-09-24 | -3.81% |
| Lab ac2ec4: ((rank(price_above_sma50) > 0.4634 and macd < 0. | lab_search | 2026-09-24 | -3.82% |
| Lab c10853: ((rank(price_above_sma50) > 0.4238 and bb_pct <  | lab_search | 2026-09-24 | -3.84% |
| Lab 76421f: ((rank(price_above_sma50) > 0.4665 and atr_14 >  | lab_search | 2026-09-24 | -3.84% |
| The Value of Low Volatility · reproduction · holding_period  | kf_low_volatility | 2026-09-30 | -3.84% |
| Lab 9b46ea: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -3.85% |
| Lab db85e9: not(((chaikin_osc > -952682 or willr_14 > -70.01 | lab_search | 2026-09-24 | -3.86% |
| Lab 474902: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5298) | lab_search | 2026-09-24 | -3.87% |
| Price and Earning Momentum · reproduction · universe large_c | kf_momentum | 2026-09-28 | -3.87% |
| Lab aec70b: ((rank(price_above_sma50) > 0.4775 and price_abo | lab_search | 2026-09-24 | -3.88% |
| Operating Hedge and Gross Profitability Premium · reproducti | kf_quality | 2026-10-21 | -3.88% |
| Why does operating profitability predict returns? New eviden | kf_quality | 2026-10-21 | -3.88% |
| Lab da0f82: pct_change(pct_of_52w_high, 5) < -0.1596 | lab_search | 2026-09-24 | -3.89% |
| Lab a68c4d: ((rank(price_above_sma50) > 0.4665 and vol_ratio | lab_search | 2026-09-24 | -3.89% |
| Lab dbe8a6: ((rank(roc_10) < 0.4786 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -3.90% |
| Size Matters, if You Control Your Junk · reproduction · univ | kf_size | 2026-10-02 | -3.90% |
| momentum_pullback · reproduction · exit 3.0 | kf_momentum | 2026-10-30 | -3.90% |
| momentum_pullback · reproduction · holding_period 0.5 | kf_momentum | 2026-10-30 | -3.90% |
| momentum_pullback · reproduction · holding_period 2.0 | kf_momentum | 2026-10-30 | -3.90% |
| momentum_pullback · reproduction · universe liquid | kf_momentum | 2026-10-30 | -3.90% |
| Does Trend Following Work on Stocks · reproduction · exit 3. | kf_trend | 2026-10-14 | -3.91% |
| Does Trend Following Work on Stocks · reproduction · holding | kf_trend | 2026-10-14 | -3.91% |
| Does Trend Following Work on Stocks · reproduction · univers | kf_trend | 2026-10-14 | -3.91% |
| Lab 093693: ((rank(log_dollar_volume) > 0.8819 and price_abo | lab_search | 2026-09-24 | -3.92% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -3.92% |
| Volatility Contraction hold=20 stop=2 zc=-1.5 | volatility_contraction | 2026-09-24 | -3.94% |
| volatility_contraction v2 (longer_hold) | volatility_contraction | 2026-09-24 | -3.94% |
| Lab c875c0: ((rank(price_above_sma50) > 0.3963 and pct_off_5 | lab_search | 2026-09-24 | -3.95% |
| Quality Momentum hold=40 q=0.7 stop=2.5 | quality_momentum | 2026-09-24 | -3.96% |
| Lab fd2638: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -3.98% |
| macd_cross v3 (trend_filter) | macd_cross | 2026-09-25 | -3.99% |
| Why is the Accrual Anomaly not Arbitraged Away? · reproducti | kf_fundamental | 2026-09-25 | -3.99% |
| Why is the Accrual Anomaly not Arbitraged Away? · reproducti | kf_fundamental | 2026-09-25 | -3.99% |
| Why is the Accrual Anomaly not Arbitraged Away? · reproducti | kf_fundamental | 2026-09-25 | -3.99% |
| Why is the Accrual Anomaly not Arbitraged Away? · reproducti | kf_fundamental | 2026-09-25 | -3.99% |
| Lab 1745d9: ((rank(macd) > 0.7 and atr_14 > 0.5) and rsi_14  | lab_search | 2026-09-24 | -3.99% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -4.00% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -4.00% |
| Lab 22b0ba: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.01% |
| Lab 469060: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.02% |
| Lab e11e17: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.02% |
| Lab b2f3c1: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.02% |
| Lab d2e5c9: ((rank(price_above_sma50) > 0.429 and vol_ratio  | lab_search | 2026-09-24 | -4.02% |
| Lab 3f9124: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.03% |
| Lab e48689: not(((chaikin_osc > -952682 or willr_14 > -73.04 | lab_search | 2026-09-24 | -4.03% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -4.06% |
| Lab bda11e: ((rank(price_above_sma50) > 0.443 and atr_14 > 0 | lab_search | 2026-09-24 | -4.07% |
| kf_breakout v1 | kf_breakout | 2026-09-24 | -4.08% |
| Lab 595d14: ((rank(price_above_sma50) > 0.4314 or pct_off_52 | lab_search | 2026-09-24 | -4.08% |
| momentum_pullback · reproduction · universe large_cap | kf_momentum | 2026-10-30 | -4.09% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-10-16 | -4.11% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-10-16 | -4.11% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-10-16 | -4.11% |
| Do Investors Under-React to ROE? · reproduction · exit 3.0 | kf_quality | 2026-10-16 | -4.11% |
| Do Investors Under-React to ROE? · reproduction · holding_pe | kf_quality | 2026-10-16 | -4.11% |
| Do Investors Under-React to ROE? · reproduction · holding_pe | kf_quality | 2026-10-16 | -4.11% |
| Do Investors Under-React to ROE? · reproduction · universe l | kf_quality | 2026-10-16 | -4.11% |
| Lab f1d94c: ((rank(rsi_14) > 0.7 or pct_off_52w_low > 0.5) a | lab_search | 2026-09-24 | -4.11% |
| Does Trend Following Work on Stocks · reproduction · stop 1. | kf_trend | 2026-10-14 | -4.11% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -4.13% |
| Lab 8d2d67: ((rank(dollar_volume_20) > 0.7208 and price_abov | lab_search | 2026-09-24 | -4.13% |
| Lab 2009a0: ((rank(rsi_14) > 0.8594 and price_above_sma200 < | lab_search | 2026-09-24 | -4.15% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -4.16% |
| Lab 5ea000: ((rank(dollar_volume_20) > 0.6638 and price_abov | lab_search | 2026-09-24 | -4.17% |
| Lab a4256e: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.19% |
| Lab 517825: ((rank(price_above_sma50) > 0.4634 and vol_ratio | lab_search | 2026-09-24 | -4.20% |
| kf_quality v2 (longer_hold) | kf_quality | 2026-10-19 | -4.20% |
| Lab afb147: ((rank(price_above_sma50) > 0.3619 and pct_off_5 | lab_search | 2026-09-24 | -4.20% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -4.21% |
| Lab 5f70ae: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.21% |
| Lab 1759e0: ((rank(price_above_sma50) > 0.2774 and pct_off_5 | lab_search | 2026-09-24 | -4.22% |
| Lab 0dcfbe: ((rank(price_above_sma50) > 0.4361 and atr_14 >  | lab_search | 2026-09-24 | -4.22% |
| Lab ceb4fd: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -4.23% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -4.23% |
| Lab 430883: ((rank(bb_pct) > 0.694 and golden_cross < 0.5) a | lab_search | 2026-09-24 | -4.23% |
| Lab c13726: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -4.23% |
| Lab 981a83: ((rank(price_above_sma50) > 0.4494 and atr_14 >  | lab_search | 2026-09-24 | -4.24% |
| Lab eca6cc: ((rank(price_above_sma50) > 0.424 and atr_14 > 0 | lab_search | 2026-09-24 | -4.25% |
| Lab 0e72c2: ((rank(price_above_sma50) > 0.4314 and vol_ratio | lab_search | 2026-09-24 | -4.26% |
| Lab 1d3621: ((rank(price_above_sma50) > 0.443 and price_abov | lab_search | 2026-09-24 | -4.26% |
| Lab 98fb7c: crosses_below(pct_of_52w_high, rank(close)) | lab_search | 2026-09-24 | -4.27% |
| Lab ec24a7: ((rank(dollar_volume_20) > 0.7 and pct_off_52w_l | lab_search | 2026-09-24 | -4.27% |
| Lab 4ebd1b: ((rank(price_above_sma50) > 0.4675 and price_abo | lab_search | 2026-09-24 | -4.27% |
| Lab 716ea0: ((rank(price_above_sma50) > 0.4435 and price_abo | lab_search | 2026-09-24 | -4.27% |
| Lab 9ed0b2: ((rank(price_above_sma50) > 0.443 and golden_cro | lab_search | 2026-09-24 | -4.27% |
| Lab 3ab133: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.28% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-10-16 | -4.29% |
| Lab 650a37: ((rank(price_above_sma50) > 0.355 and chaikin_os | lab_search | 2026-09-24 | -4.29% |
| Relative Strength hold=40 q=0.95 stop=3.5 | relative_strength | 2026-09-24 | -4.30% |
| relative_strength v2 (longer_hold) | relative_strength | 2026-09-24 | -4.30% |
| kf_earnings_surprise v2 (longer_hold) | kf_earnings_surprise | 2026-10-01 | -4.30% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -4.31% |
| Lab 2fff85: ((rank(price_above_sma50) > 0.4512 and atr_14 >  | lab_search | 2026-09-24 | -4.31% |
| Lab cd855b: ((rank(dollar_volume_20) > 0.7477 and price_abov | lab_search | 2026-09-24 | -4.31% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -4.31% |
| Lab d8eed8: ((rank(stoch_d) > 0.3415 and pct_off_52w_low > 0 | lab_search | 2026-09-24 | -4.32% |
| Lab 16569d: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.33% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-10-08 | -4.33% |
| Lab bf5efd: ((rank(price_above_sma50) > 0.4414 and atr_14 >  | lab_search | 2026-09-24 | -4.34% |
| Lab 3fb684: ((rank(willr_14) > 0.6462 and drawdown_200 > 0.3 | lab_search | 2026-09-24 | -4.34% |
| Lab 943dd7: ((rank(rsi_14) > 0.4238 and drawdown_200 > 0.395 | lab_search | 2026-09-24 | -4.36% |
| Lab 2cd56a: ((rank(price_above_sma50) > 0.4414 and pct_off_5 | lab_search | 2026-09-24 | -4.37% |
| Lab 2ec418: ((rank(price_above_sma50) > 0.4185 and vol_ratio | lab_search | 2026-09-24 | -4.37% |
| Lab 189966: ((rank(dollar_volume_20) > 0.7 and price_above_s | lab_search | 2026-09-24 | -4.37% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -4.37% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -4.37% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -4.37% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -4.37% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -4.37% |
| Lab eb5a4f: ((rank(macd) > 0.7 and price_above_sma200 < 0.5) | lab_search | 2026-09-24 | -4.38% |
| Lab 5cbf57: ((rank(price_above_sma50) > 0.4291 and willr_14  | lab_search | 2026-09-24 | -4.38% |
| Lab acefab: ((rank(price_above_sma50) > 0.4494 and atr_14 >  | lab_search | 2026-09-24 | -4.38% |
| Lab 0099cb: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -4.39% |
| Lab 28f412: (rsi_14 < 33.7551 and pct_off_52w_low > 0.5389) | lab_search | 2026-09-24 | -4.39% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-10-08 | -4.39% |
| Lab 549467: ((rank(dollar_volume_20) > 0.8523 and price_abov | lab_search | 2026-09-24 | -4.40% |
| Lab 806b6f: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -4.41% |
| Lab 2b333a: ((rank(price_above_sma50) > 0.443 and vol_ratio  | lab_search | 2026-09-24 | -4.43% |
| Lab 6d3352: ((rank(price_above_sma50) > 0.4241 and pct_off_5 | lab_search | 2026-09-24 | -4.43% |
| Lab 5465a8: ((rank(price_above_sma50) > 0.4291 and pct_off_5 | lab_search | 2026-09-24 | -4.45% |
| Lab 5fde29: ((rank(price_above_sma50) > 0.4238 and atr_14 >  | lab_search | 2026-09-24 | -4.45% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-10-08 | -4.45% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-10-08 | -4.45% |
| Lab b25b52: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.48% |
| Lab e8d613: ((rank(price_above_sma50) > 0.3893 and atr_14 >  | lab_search | 2026-09-24 | -4.48% |
| Lab f8edc5: ((rank(price_above_sma50) > 0.3501 and pct_off_5 | lab_search | 2026-09-24 | -4.48% |
| Lab b33f84: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -4.49% |
| Lab 90189c: (pct_change(sma_200, 20) < -0.0964 or crosses_be | lab_search | 2026-09-24 | -4.49% |
| Lab e9cd0a: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -4.49% |
| Breakout 52W hold=20 near=0.97 stop=2 | breakout_52w | 2026-09-25 | -4.49% |
| Lab c1f386: ((rank(price_above_sma50) > 0.429 and macd < 0.3 | lab_search | 2026-09-24 | -4.49% |
| Lab 1ed6bd: ((rank(price_above_sma50) > 0.3138 and pct_off_5 | lab_search | 2026-09-24 | -4.52% |
| Lab a6d0b1: ((rank(price_above_sma50) > 0.4435 and price_abo | lab_search | 2026-09-24 | -4.53% |
| Lab a2b277: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -4.54% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -4.55% |
| The 52-week High Strategy and Information Uncertainty · repr | kf_breakout | 2026-09-25 | -4.55% |
| Accruals, Investment, and the Accrual Anomaly · reproduction | kf_quality | 2026-09-25 | -4.56% |
| Lab 04bf2f: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.56% |
| Lab a1fa73: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -4.56% |
| Lab c01e0d: ((rank(price_above_sma50) > 0.427 and atr_14 > 0 | lab_search | 2026-09-24 | -4.57% |
| Lab b1ac04: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.57% |
| Payday hold=2 stop=2 | payday | 2026-09-24 | -4.58% |
| Payday hold=2 stop=3 | payday | 2026-09-24 | -4.58% |
| kf_momentum v1 | kf_momentum | 2026-09-24 | -4.59% |
| Lab 3dcfd0: ((rank(price_above_sma50) > 0.3971 and atr_14 >  | lab_search | 2026-09-24 | -4.59% |
| Lab d86bb9: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.59% |
| Lab e92e62: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.59% |
| The Long and Short of the Accrual Anomaly · reproduction · s | kf_quality | 2026-10-15 | -4.60% |
| cci_extreme · reproduction · exit 3.0 | kf_mean_reversion | 2026-10-01 | -4.60% |
| cci_extreme · reproduction · universe liquid | kf_mean_reversion | 2026-10-01 | -4.60% |
| Lab 0fa2b8: ((rank(price_above_sma50) > 0.4241 and pct_off_5 | lab_search | 2026-09-24 | -4.61% |
| Overreaction Evidence from Large-Cap Stocks · reproduction | kf_reversal | 2026-09-25 | -4.61% |
| Lab 02efc5: ((rank(price_above_sma50) > 0.427 and vol_ratio  | lab_search | 2026-09-24 | -4.61% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -4.62% |
| Lab 74dd77: ((rank(price_above_sma50) > 0.4038 and price_abo | lab_search | 2026-09-24 | -4.62% |
| Lab 7942ac: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | -4.62% |
| Trading volume, Price Momentum, and the 52-week High Price M | kf_momentum | 2026-10-20 | -4.63% |
| Lab 307d3c: ((rank(pct_off_52w_low) > 0.8594 and macd < 0.5) | lab_search | 2026-09-24 | -4.63% |
| Lab b5aa62: ((rank(price_above_sma50) > 0.4238 and atr_14 >  | lab_search | 2026-09-24 | -4.63% |
| Lab 18338f: not(((chaikin_osc > -952682 or chaikin_osc > -10 | lab_search | 2026-09-24 | -4.63% |
| Lab ff214f: not(((chaikin_osc > -919416 or crosses_above(wil | lab_search | 2026-09-24 | -4.63% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-28 | -4.64% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-25 | -4.64% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-28 | -4.64% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-28 | -4.64% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-28 | -4.64% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-28 | -4.64% |
| Lab f08b07: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -4.65% |
| Lab 5dc066: (((log_dollar_volume > 7.229 and chaikin_osc < - | lab_search | 2026-09-24 | -4.67% |
| golden_cross · reproduction · stop 1.0 | kf_trend | 2026-10-20 | -4.68% |
| Lab 42f799: ((rank(log_dollar_volume) > 0.7876 and pct_off_5 | lab_search | 2026-09-24 | -4.68% |
| Lab 727c7e: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.68% |
| Lab 16a314: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | -4.69% |
| bollinger_reversion · reproduction · holding_period 0.5 | kf_mean_reversion | 2026-10-05 | -4.69% |
| Pre-Election Drift in the Stock Market · reproduction | kf_seasonality | 2026-09-25 | -4.70% |
| Lab 82df98: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -4.71% |
| politician_buying v3 (trend_filter) | politician_buying | 2026-10-06 | -4.71% |
| politician_buying v2 (longer_hold) | politician_buying | 2026-10-05 | -4.71% |
| Quality Momentum hold=20 q=0.8 stop=3.5 | quality_momentum | 2026-09-24 | -4.71% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-09-25 | -4.72% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -4.72% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -4.72% |
| The Value of Low Volatility · reproduction | kf_low_volatility | 2026-09-25 | -4.72% |
| golden_cross · reproduction · exit 3.0 | kf_trend | 2026-10-20 | -4.72% |
| golden_cross · reproduction · holding_period 0.5 | kf_trend | 2026-10-20 | -4.72% |
| Lab c23439: not((rank(stoch_k) < 0.6134 or (crosses_below(cc | lab_search | 2026-09-24 | -4.72% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-09-25 | -4.72% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-28 | -4.72% |
| The Persistence of the Accruals Anomaly · reproduction · sto | kf_mean_reversion | 2026-09-25 | -4.72% |
| Lab 7c4e90: ((rank(price_above_sma50) > 0.4361 and atr_14 >  | lab_search | 2026-09-24 | -4.72% |
| Lab 8c8b83: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | -4.73% |
| Lab e3c18c: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -4.73% |
| Lab 6d2829: ((rank(log_dollar_volume) > 0.9258 and golden_cr | lab_search | 2026-09-24 | -4.74% |
| Lab 9551d6: ((rank(price_above_sma50) > 0.4514 and price_abo | lab_search | 2026-09-24 | -4.74% |
| Lab 2f31b0: ((rank(golden_cross) > 0.7 and price_above_sma20 | lab_search | 2026-09-24 | -4.74% |
| Lab 78095b: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -4.75% |
| Quality Piotroski f=7 hold=60 stop=3 | quality_piotroski | 2026-09-24 | -4.75% |
| quality_piotroski v1 | quality_piotroski | 2026-09-24 | -4.75% |
| Replicating Private Equity with Value Investing, Homemade Le | kf_value | 2026-09-25 | -4.75% |
| Lab 907f7b: ((rank(price_above_sma50) > 0.4494 and vol_ratio | lab_search | 2026-09-24 | -4.76% |
| Lab 2ffed9: ((rank(price_above_sma50) > 0.427 and golden_cro | lab_search | 2026-09-24 | -4.76% |
| Lab 63e841: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | -4.76% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -4.76% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -4.76% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -4.76% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -4.76% |
| Lab 5545ba: ((rank(price_above_sma50) > 0.4414 and vol_ratio | lab_search | 2026-09-24 | -4.76% |
| Lab 791ce7: ((rank(price_above_sma50) > 0.2925 and pct_off_5 | lab_search | 2026-09-24 | -4.77% |
| Lab 0b5f03: ((rank(price_above_sma50) > 0.4238 and price_abo | lab_search | 2026-09-24 | -4.77% |
| Lab 434a29: ((rank(price_above_sma50) > 0.424 and price_abov | lab_search | 2026-09-24 | -4.77% |
| Lab b427a0: ((rank(price_above_sma50) > 0.4291 and price_abo | lab_search | 2026-09-24 | -4.77% |
| Quality Momentum hold=40 q=0.8 stop=2.5 | quality_momentum | 2026-09-24 | -4.78% |
| Size Matters, if You Control Your Junk · reproduction · exit | kf_size | 2026-10-02 | -4.79% |
| Lab 83f0f5: ((rank(price_above_sma50) > 0.4845 and price_abo | lab_search | 2026-09-24 | -4.79% |
| Lab 89e17a: ((rank(price_above_sma50) > 0.4435 and price_abo | lab_search | 2026-09-24 | -4.79% |
| Lab be86fb: ((rank(price_above_sma50) > 0.4498 and price_abo | lab_search | 2026-09-24 | -4.79% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -4.79% |
| Factoring in the Low-Volatility Factor · reproduction | kf_low_volatility | 2026-09-25 | -4.80% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-09-25 | -4.80% |
| Do Investors Under-React to ROE? · reproduction · stop 1.0 | kf_quality | 2026-10-16 | -4.81% |
| Lab 04e5a6: ((rank(price_above_sma50) > 0.4414 and price_abo | lab_search | 2026-09-24 | -4.81% |
| Lab 13ba29: ((rank(price_above_sma50) > 0.443 and price_abov | lab_search | 2026-09-24 | -4.81% |
| Lab 1efb7e: ((rank(price_above_sma50) > 0.4688 and price_abo | lab_search | 2026-09-24 | -4.81% |
| Lab 53acb3: ((rank(price_above_sma50) > 0.4494 and golden_cr | lab_search | 2026-09-24 | -4.81% |
| Lab c2c7a8: ((rank(price_above_sma50) > 0.4414 and price_abo | lab_search | 2026-09-24 | -4.81% |
| Lab cb6e77: ((rank(price_above_sma50) > 0.3978 and price_abo | lab_search | 2026-09-24 | -4.81% |
| Lab e221d9: ((rank(price_above_sma50) > 0.3867 and price_abo | lab_search | 2026-09-24 | -4.81% |
| Lab 2f8a4b: ((rank(price_above_sma50) > 0.4241 and golden_cr | lab_search | 2026-09-24 | -4.82% |
| Lab 4184d6: ((rank(price_above_sma50) > 0.424 and price_abov | lab_search | 2026-09-24 | -4.82% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -4.82% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -4.83% |
| Lab 7bc7e1: ((rank(price_above_sma50) > 0.4314 and price_abo | lab_search | 2026-09-24 | -4.83% |
| Lab 290d13: ((rank(price_above_sma50) > 0.4634 and price_abo | lab_search | 2026-09-24 | -4.83% |
| Lab 34e48e: ((rank(price_above_sma50) > 0.4795 and golden_cr | lab_search | 2026-09-24 | -4.83% |
| Lab 35447f: ((rank(price_above_sma50) > 0.4634 and golden_cr | lab_search | 2026-09-24 | -4.83% |
| Lab 99e3a9: ((rank(price_above_sma50) > 0.437 and price_abov | lab_search | 2026-09-24 | -4.83% |
| Lab 9bdf34: ((rank(price_above_sma50) > 0.4449 and price_abo | lab_search | 2026-09-24 | -4.83% |
| Lab c756f9: ((rank(price_above_sma50) > 0.4238 and price_abo | lab_search | 2026-09-24 | -4.83% |
| Lab 3238c6: ((rank(price_above_sma50) > 0.4704 and golden_cr | lab_search | 2026-09-24 | -4.84% |
| Lab 46ac4c: ((rank(price_above_sma50) > 0.4414 and golden_cr | lab_search | 2026-09-24 | -4.84% |
| Lab 569173: ((rank(price_above_sma50) > 0.427 and price_abov | lab_search | 2026-09-24 | -4.84% |
| Lab ca484f: ((rank(price_above_sma50) > 0.4494 and price_abo | lab_search | 2026-09-24 | -4.84% |
| Lab d69c19: ((rank(price_above_sma50) > 0.478 and price_abov | lab_search | 2026-09-24 | -4.84% |
| rsi_reversion v3 (trend_filter) | rsi_reversion | 2026-09-25 | -4.85% |
| Lab c212d0: ((rank(price_above_sma50) > 0.4494 and price_abo | lab_search | 2026-09-24 | -4.85% |
| Lab 957113: (((log_dollar_volume > 7.229 and chaikin_osc < - | lab_search | 2026-09-24 | -4.85% |
| Lab 9ffb66: ((rank(dollar_volume_20) > 0.424 and price_above | lab_search | 2026-09-24 | -4.85% |
| Lab 00db7c: ((rank(price_above_sma50) > 0.4414 and price_abo | lab_search | 2026-09-24 | -4.85% |
| Lab bd95cd: ((rank(price_above_sma50) > 0.4494 and golden_cr | lab_search | 2026-09-24 | -4.85% |
| Lab 0210d3: ((rank(price_above_sma50) > 0.443 and price_abov | lab_search | 2026-09-24 | -4.86% |
| Lab 365d31: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | -4.86% |
| Lab 22f26c: ((rank(price_above_sma50) > 0.4146 and price_abo | lab_search | 2026-09-24 | -4.87% |
| kf_quality v2 (longer_hold) | kf_quality | 2026-10-20 | -4.88% |
| Lab d060fa: ((rank(log_dollar_volume) > 0.5645 and pct_off_5 | lab_search | 2026-09-24 | -4.89% |
| Lab 0235ee: ((rank(log_dollar_volume) > 0.6761 and pct_off_5 | lab_search | 2026-09-24 | -4.90% |
| momentum_pullback · reproduction · stop -1.0 | kf_momentum | 2026-10-30 | -4.90% |
| Lab f6f019: ((rank(log_dollar_volume) > 0.4995 and pct_off_5 | lab_search | 2026-09-24 | -4.91% |
| Lab ded2b6: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -4.91% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -4.92% |
| Lab da02f3: ((rank(sma_200) > 0.511 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -4.92% |
| Lab af69dd: ((rank(price_above_sma50) > 0.424 and macd_signa | lab_search | 2026-09-24 | -4.93% |
| Lab 528ec9: ((rank(price_above_sma50) > 0.4238 and atr_14 >  | lab_search | 2026-09-24 | -4.93% |
| Optimal Trend Following Rules in Two-State Regime-Switching  | kf_trend | 2026-09-25 | -4.94% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -4.94% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -4.94% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -4.94% |
| Lab 417044: ((rank(stoch_d) > 0.3247 and pct_off_52w_low > 0 | lab_search | 2026-09-24 | -4.95% |
| Lab c2aa7b: ((rank(price_above_sma50) > 0.4675 and vol_ratio | lab_search | 2026-09-24 | -4.96% |
| Lab f8f8cd: ((rank(price_above_sma50) > 0.4291 and macd_sign | lab_search | 2026-09-24 | -4.97% |
| Lab 91790f: (roc_10 < -10.9569 and crosses_above(pct_change( | lab_search | 2026-09-24 | -4.98% |
| Lab 834981: ((rank(price_above_sma50) > 0.4435 and price_abo | lab_search | 2026-09-24 | -5.01% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-09-30 | -5.02% |
| Lab a795b8: (chaikin_osc < -1.4965e+06 and (rank(price_above | lab_search | 2026-09-24 | -5.04% |
| Lab e9e4b0: ((rank(price_above_sma50) > 0.3187 and atr_14 >  | lab_search | 2026-09-24 | -5.06% |
| Lab dfd371: ((rank(price_above_sma50) > 0.4842 and vol_ratio | lab_search | 2026-09-24 | -5.07% |
| Balance Sheet hold=40 q=0.3 stop=3 | balance_sheet | 2026-09-24 | -5.07% |
| Balance Sheet hold=60 q=0.3 stop=3 | balance_sheet | 2026-09-24 | -5.07% |
| Can the representativeness heuristic explain the asset growt | kf_fundamental | 2026-09-29 | -5.08% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -5.08% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -5.08% |
| Turn Of Month last=2 stop=2 | turn_of_month | 2026-09-24 | -5.09% |
| turn_of_month v2 (longer_hold) | turn_of_month | 2026-09-24 | -5.09% |
| Lab db64a5: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -5.10% |
| Lab baee3b: ((rank(pct_off_52w_low) > 0.7 or pct_off_52w_low | lab_search | 2026-09-24 | -5.11% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-10-21 | -5.12% |
| Lab 19a283: (not(not(stoch_k < 9.3633)) or ((chaikin_osc > 3 | lab_search | 2026-09-24 | -5.13% |
| Lab 225c83: (((log_dollar_volume > 7.229 and chaikin_osc < - | lab_search | 2026-09-24 | -5.13% |
| The Stock Market Valuation of Research and Development Expen | kf_fundamental | 2026-09-25 | -5.14% |
| Stock market anomalies: What can we learn from repurchases   | kf_hybrid | 2026-09-25 | -5.15% |
| Lab 315b74: ((rank(price_above_sma50) > 0.344 and pct_off_52 | lab_search | 2026-09-24 | -5.16% |
| Lab aece8e: ((rank(price_above_sma50) > 0.4238 and price_abo | lab_search | 2026-09-24 | -5.16% |
| Politician Buying buyers=2 hold=20 stop=3 | politician_buying | 2026-09-25 | -5.18% |
| Profitability hold=40 q=0.9 stop=5 | profitability | 2026-09-24 | -5.19% |
| Profitability hold=60 q=0.9 stop=5 | profitability | 2026-09-24 | -5.19% |
| Breakout 52W hold=10 near=0.99 stop=2 | breakout_52w | 2026-09-24 | -5.20% |
| Lab cb9e05: ((rank(rsi_14) > 0.4263 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -5.21% |
| A New Anomaly: The Cross-Sectional Profitability of Technica | kf_volatility | 2026-09-25 | -5.21% |
| kf_volatility v2 (longer_hold) | kf_volatility | 2026-09-25 | -5.21% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-28 | -5.22% |
| The Persistence of the Accruals Anomaly · reproduction · uni | kf_mean_reversion | 2026-09-25 | -5.22% |
| The Long and Short of the Accrual Anomaly · reproduction · e | kf_quality | 2026-10-15 | -5.23% |
| The Long and Short of the Accrual Anomaly · reproduction · h | kf_quality | 2026-10-15 | -5.23% |
| The Long and Short of the Accrual Anomaly · reproduction · u | kf_quality | 2026-10-15 | -5.23% |
| Lab a50d97: not(((chaikin_osc > -1.18213e+06 or crosses_abov | lab_search | 2026-09-24 | -5.23% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -5.25% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -5.26% |
| Debt Reduction hold=40 n=126 stop=5 | debt_reduction | 2026-09-24 | -5.27% |
| Debt Reduction hold=60 n=126 stop=5 | debt_reduction | 2026-09-24 | -5.27% |
| Lab 12ef5e: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -5.28% |
| rsi_reversion v2 (longer_hold) | rsi_reversion | 2026-09-24 | -5.30% |
| Breakout 52W hold=20 near=0.99 stop=2 | breakout_52w | 2026-09-25 | -5.31% |
| Lab 4feff8: ((rank(log_dollar_volume) > 0.8863 and price_abo | lab_search | 2026-09-24 | -5.31% |
| Lab c295cf: (((close < 11.2649 and chaikin_osc < -955749) an | lab_search | 2026-09-24 | -5.32% |
| St Bollinger Low hold=3 stop=2.5 | st_bollinger_low | 2026-09-24 | -5.34% |
| Lab 6de693: not(((chaikin_osc > -1.04255e+06 or willr_14 > - | lab_search | 2026-09-24 | -5.35% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-28 | -5.36% |
| The Persistence of the Accruals Anomaly · reproduction · uni | kf_mean_reversion | 2026-09-25 | -5.36% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-28 | -5.36% |
| The Persistence of the Accruals Anomaly · reproduction · sto | kf_mean_reversion | 2026-09-25 | -5.36% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-09-25 | -5.39% |
| golden_cross · reproduction · stop -1.0 | kf_trend | 2026-10-20 | -5.40% |
| Growth Valuation hold=40 q=0.6 stop=3 | growth_valuation | 2026-09-24 | -5.41% |
| Growth Valuation hold=60 q=0.6 stop=3 | growth_valuation | 2026-09-24 | -5.41% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -5.41% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -5.41% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -5.41% |
| Low Investment hold=40 q=0.2 stop=5 | low_investment | 2026-09-24 | -5.42% |
| Low Investment hold=60 q=0.2 stop=5 | low_investment | 2026-09-24 | -5.42% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -5.43% |
| Lab 32d01e: ((rank(rsi_14) < 0.529 and pct_off_52w_low > 0.5 | lab_search | 2026-09-24 | -5.44% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -5.44% |
| Earnings Yield hold=60 q=0.8 stop=3 | earnings_yield | 2026-09-24 | -5.45% |
| earnings_yield v1 | earnings_yield | 2026-09-24 | -5.45% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -5.47% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-10-19 | -5.48% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-10-19 | -5.48% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-10-19 | -5.48% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-10-19 | -5.48% |
| williams_r_oversold · reproduction · holding_period 0.5 | kf_mean_reversion | 2026-10-02 | -5.53% |
| Lab 0ee23a: ((rank(dollar_volume_20) > 0.8727 and price_abov | lab_search | 2026-09-24 | -5.53% |
| Ma Cross hold=20 stop=3 | ma_cross | 2026-09-24 | -5.55% |
| ma_cross v2 (longer_hold) | ma_cross | 2026-09-24 | -5.55% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -5.55% |
| The Volatility Effect Revisited · reproduction · universe la | kf_low_volatility | 2026-09-29 | -5.55% |
| Lab 6b39de: ((rank(dollar_volume_20) > 0.5906 and price_abov | lab_search | 2026-09-24 | -5.55% |
| Volatility Breakout hold=10 stop=2 vr=1.5 | volatility_breakout | 2026-09-25 | -5.56% |
| cci_extreme · reproduction · universe large_cap | kf_mean_reversion | 2026-10-01 | -5.57% |
| COMBINING VALUE AND MOMENTUM · reproduction · lookback 0.5 | kf_hybrid | 2026-09-25 | -5.58% |
| Lab a8cc0a: (((log_dollar_volume < 7.8318 and chaikin_osc <  | lab_search | 2026-09-24 | -5.58% |
| Lab dc098d: ((rank(price_above_sma50) > 0.424 and price_abov | lab_search | 2026-09-24 | -5.59% |
| Accrual anomaly · reproduction | kf_quality | 2026-09-25 | -5.61% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-25 | -5.61% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-28 | -5.61% |
| Relevansi Informasi Anomali Akrual dalam Pembentukan Portofo | kf_fundamental | 2026-09-28 | -5.61% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-25 | -5.61% |
| The Persistence of the Accruals Anomaly · reproduction · exi | kf_mean_reversion | 2026-09-25 | -5.61% |
| The Persistence of the Accruals Anomaly · reproduction · hol | kf_mean_reversion | 2026-09-25 | -5.61% |
| Lab f1af25: ((rank(bb_pct) > 0.6337 and price_above_sma200 < | lab_search | 2026-09-24 | -5.62% |
| Lab d6d7e3: ((rank(dollar_volume_20) > 0.8099 and price_abov | lab_search | 2026-09-24 | -5.64% |
| Information in Accruals about the Quality of Earnings · repr | kf_quality | 2026-09-25 | -5.64% |
| Lab 95656c: ((rank(stoch_d) > 0.8323 or pct_off_52w_low > 0. | lab_search | 2026-09-24 | -5.64% |
| Turn Of Month last=1 stop=2 | turn_of_month | 2026-09-24 | -5.64% |
| turn_of_month v2 (longer_hold) | turn_of_month | 2026-09-24 | -5.64% |
| Lab 1a9b7e: not(((chaikin_osc > -1.18213e+06 or crosses_abov | lab_search | 2026-09-24 | -5.65% |
| Lab 381fba: roc_10 < -9.1019 | lab_search | 2026-09-24 | -5.65% |
| Lab 0515a0: (pct_change(sma_200, 20) < -0.0964 or stoch_d <  | lab_search | 2026-09-24 | -5.65% |
| Lab 0aca85: (pct_change(sma_200, 20) < -0.0964 or sma_50 < p | lab_search | 2026-09-24 | -5.65% |
| Does Trend Following Work on Stocks · reproduction · univers | kf_trend | 2026-10-14 | -5.66% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-10-19 | -5.67% |
| Quality Momentum hold=40 q=0.7 stop=3.5 | quality_momentum | 2026-09-24 | -5.68% |
| The Information Content of Changes in Financial Leverage · r | kf_fundamental | 2026-09-25 | -5.68% |
| Dissecting Anomalies · reproduction · lookback 1.5 | kf_factor | 2026-09-29 | -5.72% |
| st_stoch_oversold v3 (trend_filter) | st_stoch_oversold | 2026-09-25 | -5.73% |
| Testing the accruals anomaly based on the speed of price adj | kf_quality | 2026-09-29 | -5.74% |
| 52 weeks high effect in stocks · reproduction · stop 1.0 | kf_breakout | 2026-09-25 | -5.75% |
| Company-Size Effect on the Polish Stock Market · reproductio | kf_size | 2026-09-25 | -5.75% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -5.75% |
| Lab c4e3ea: ((rank(chaikin_osc) < 0.7 and pct_off_52w_low >  | lab_search | 2026-09-24 | -5.80% |
| Does Trend Following Work on Stocks · reproduction · holding | kf_trend | 2026-10-14 | -5.80% |
| Lab 7c034b: ((rank(rsi_14) > 0.3143 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -5.81% |
| Lab 29908c: ((rank(close) > 0.7 and price_above_sma200 > 0.5 | lab_search | 2026-09-24 | -5.81% |
| Stock Price Anchoring · reproduction · universe large_cap | kf_reversal | 2026-09-30 | -5.81% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -5.83% |
| Lab 223c1a: ((rank(roc_10) < 0.8066 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -5.84% |
| Lab 002b3c: ((rank(dollar_volume_20) > 0.9258 and atr_14 > 0 | lab_search | 2026-09-24 | -5.85% |
| The Volatility Effect Revisited · reproduction · stop 1.0 | kf_low_volatility | 2026-09-29 | -5.86% |
| Lab 4b23c2: ((rank(dollar_volume_20) > 0.8408 and price_abov | lab_search | 2026-09-24 | -5.90% |
| Turn Of Month last=1 stop=3 | turn_of_month | 2026-09-24 | -5.92% |
| turn_of_month v2 (longer_hold) | turn_of_month | 2026-09-24 | -5.92% |
| dual_momentum · reproduction | kf_momentum | 2026-09-25 | -5.92% |
| Price and Earning Momentum · reproduction · lookback 0.5 | kf_momentum | 2026-09-28 | -5.95% |
| Lab a6126b: ((rank(sma_50) > 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | -5.96% |
| Lab 0b37ef: not(((chaikin_osc > -952682 or crosses_above(wil | lab_search | 2026-09-24 | -5.96% |
| Do Investors Under-React to ROE? · reproduction · stop -1.0 | kf_quality | 2026-10-16 | -5.97% |
| Lab 8685a7: ((rank(price_above_sma50) > 0.4634 and price_abo | lab_search | 2026-09-24 | -5.99% |
| Lab 1ead34: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -6.00% |
| Lab 1f793a: ((rank(bb_pct) > 0.7183 and chaikin_osc < 0.5) a | lab_search | 2026-09-24 | -6.01% |
| Why momentum concentrates among overvalued stocks · reproduc | kf_momentum | 2026-10-15 | -6.02% |
| Volatility Breakout hold=10 stop=3 vr=2 | volatility_breakout | 2026-09-24 | -6.02% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -6.02% |
| Lab 3bf2c1: ((rank(chaikin_osc) < 0.7 and pct_off_52w_low >  | lab_search | 2026-09-24 | -6.03% |
| St Rsi Oversold hold=5 rsi=30 stop=2.5 | st_rsi_oversold | 2026-09-24 | -6.05% |
| Momentum Volume hold=20 q=0.8 stop=3 | momentum_volume | 2026-09-25 | -6.06% |
| Volatility Breakout hold=5 stop=2 vr=2 | volatility_breakout | 2026-09-24 | -6.07% |
| Lab 02ee6b: ((rank(price_above_sma50) > 0.4414 or pct_off_52 | lab_search | 2026-09-24 | -6.07% |
| Lab 94f083: ((rank(log_dollar_volume) > 0.571 and price_abov | lab_search | 2026-09-24 | -6.11% |
| St Stoch Oversold hold=2 k=10 stop=2.5 | st_stoch_oversold | 2026-09-24 | -6.11% |
| Lab df8d32: ((rank(price_above_sma50) > 0.4844 and macd < 0. | lab_search | 2026-09-24 | -6.12% |
| rd_intensity v3 (trend_filter) | rd_intensity | 2026-09-24 | -6.14% |
| Roa effect within stocks · reproduction · holding_period 0.5 | kf_quality | 2026-09-25 | -6.17% |
| Short-sellers, fundamental analysis and stock returns · repr | kf_fundamental | 2026-09-25 | -6.17% |
| Lab 2e23fe: (dollar_volume_20 > 1.69446e+07 and (crosses_bel | lab_search | 2026-09-24 | -6.18% |
| Volatility Breakout hold=10 stop=3 vr=2 | volatility_breakout | 2026-09-25 | -6.21% |
| Turnover: Liquidity or Uncertainty? · reproduction · stop -1 | kf_liquidity | 2026-09-25 | -6.21% |
| Lab 358491: ((rank(price_above_sma50) > 0.4238 and price_abo | lab_search | 2026-09-24 | -6.22% |
| Quality Momentum hold=40 q=0.8 stop=3.5 | quality_momentum | 2026-09-24 | -6.25% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -6.25% |
| Lab da7c48: ((rank(price_above_sma50) > 0.4248 or price_abov | lab_search | 2026-09-24 | -6.25% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | -6.26% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -6.27% |
| Lab c44f57: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -6.27% |
| Lab 887628: ((rank(price_above_sma50) > 0.443 and price_abov | lab_search | 2026-09-24 | -6.28% |
| Lab fb58a5: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -6.29% |
| kf_liquidity v3 (trend_filter) | kf_liquidity | 2026-09-25 | -6.30% |
| Lab f90164: ((rank(price_above_sma50) > 0.2686 and pct_off_5 | lab_search | 2026-09-24 | -6.31% |
| The Long and Short of the Accrual Anomaly · reproduction · s | kf_quality | 2026-10-15 | -6.34% |
| macd_cross v3 (trend_filter) | macd_cross | 2026-09-25 | -6.34% |
| Lab c9fb52: ((rank(price_above_sma50) > 0.4314 and atr_14 >  | lab_search | 2026-09-24 | -6.35% |
| Lab 381464: (roc_10 < -10.9569 and crosses_below(pct_change( | lab_search | 2026-09-24 | -6.35% |
| Momentum Volume hold=20 q=0.8 stop=3 | momentum_volume | 2026-09-24 | -6.36% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -6.36% |
| Lab 4d0ee7: ((crosses_above(rank(atr_14), 0.7) or pct_off_52 | lab_search | 2026-09-24 | -6.36% |
| Debt Reduction hold=40 n=126 stop=3 | debt_reduction | 2026-09-24 | -6.38% |
| Debt Reduction hold=60 n=126 stop=3 | debt_reduction | 2026-09-24 | -6.38% |
| Do Earnings Explain the January Effect? · reproduction · exi | kf_seasonality | 2026-10-13 | -6.39% |
| Do Earnings Explain the January Effect? · reproduction · hol | kf_seasonality | 2026-10-13 | -6.39% |
| Do Earnings Explain the January Effect? · reproduction · uni | kf_seasonality | 2026-10-13 | -6.39% |
| Do Earnings Explain the January Effect? · reproduction · uni | kf_seasonality | 2026-10-13 | -6.39% |
| Lab 21a4ce: (not(not(chaikin_osc < -2.07956e+06)) and (cross | lab_search | 2026-09-24 | -6.39% |
| Lab e146f9: ((rank(rsi_14) < 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | -6.41% |
| Lab 9613d1: ((rank(rsi_14) > 0.2676 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -6.43% |
| Company-Size Effect on the Polish Stock Market · reproductio | kf_size | 2026-09-25 | -6.44% |
| Lab fedb19: (((log_dollar_volume < 8.3926 and chaikin_osc <  | lab_search | 2026-09-24 | -6.44% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | -6.45% |
| Lab 976f08: ((rank(dollar_volume_20) > 0.6574 and price_abov | lab_search | 2026-09-24 | -6.45% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-10-13 | -6.47% |
| Balance Sheet hold=60 q=0.2 stop=3 | balance_sheet | 2026-09-24 | -6.47% |
| balance_sheet v1 | balance_sheet | 2026-09-24 | -6.47% |
| The Volatility Effect Revisited · reproduction · stop -1.0 | kf_low_volatility | 2026-09-29 | -6.50% |
| st_momentum_1d v2 (longer_hold) | st_momentum_1d | 2026-09-24 | -6.51% |
| Lab b1b21f: ((rank(rsi_14) > 0.529 or pct_off_52w_low > 0.5) | lab_search | 2026-09-24 | -6.51% |
| Turn Of Month last=2 stop=3 | turn_of_month | 2026-09-24 | -6.51% |
| turn_of_month v2 (longer_hold) | turn_of_month | 2026-09-24 | -6.51% |
| st_stoch_oversold v2 (longer_hold) | st_stoch_oversold | 2026-09-24 | -6.52% |
| Lab daa581: ((rank(price_above_sma50) > 0.429 and price_abov | lab_search | 2026-09-24 | -6.53% |
| Lab 6f2892: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -6.53% |
| kf_factor v1 | kf_factor | 2026-09-24 | -6.54% |
| st_volume_shock v3 (trend_filter) | st_volume_shock | 2026-09-24 | -6.55% |
| Lab b728d5: not(((crosses_above(dollar_volume_20, 1.69167e+0 | lab_search | 2026-09-24 | -6.55% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -6.57% |
| Volatility Contraction hold=10 stop=2 zc=-1 | volatility_contraction | 2026-09-24 | -6.57% |
| Lab 3a26ae: ((rank(bb_pct) < 0.6404 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -6.57% |
| Value Momentum hold=40 q=0.7 stop=3 | value_momentum | 2026-09-25 | -6.58% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -6.59% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -6.59% |
| Timing the Market with a Combination of Moving Averages · re | kf_trend | 2026-09-28 | -6.60% |
| The Long and Short of the Accrual Anomaly · reproduction · u | kf_quality | 2026-10-15 | -6.61% |
| Company Fundamentals and Equity Returns in India · reproduct | kf_value | 2026-09-25 | -6.61% |
| kf_regime v3 (trend_filter) | kf_regime | 2026-10-15 | -6.61% |
| The Rehabilitation of Glidepath Investing · reproduction | kf_trend | 2026-09-25 | -6.64% |
| Lab 9e40bd: ((rank(price_above_sma50) > 0.4314 and vol_ratio | lab_search | 2026-09-24 | -6.65% |
| Lab 946b6e: ((rank(dollar_volume_20) > 0.8962 and price_abov | lab_search | 2026-09-24 | -6.66% |
| Lab e748a8: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -6.66% |
| Lab 643589: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -6.67% |
| Momentum Volume hold=10 q=0.8 stop=2 | momentum_volume | 2026-09-24 | -6.69% |
| Fundamental Price Momentum hold=40 n=63 q=0.8 stop=3 | fundamental_price_momentum | 2026-09-24 | -6.72% |
| Lab c0528d: (((chaikin_osc < 7.229 and chaikin_osc < -955749 | lab_search | 2026-09-24 | -6.74% |
| Lab 2a330c: ((rank(price_above_sma50) > 0.4238 and bb_pct <  | lab_search | 2026-09-24 | -6.75% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-10-23 | -6.76% |
| Xs Momentum hold=20 q=0.8 stop=3 | xs_momentum | 2026-09-24 | -6.76% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -6.76% |
| Value Momentum hold=40 q=0.7 stop=4 | value_momentum | 2026-09-25 | -6.76% |
| Lab 7203e4: (((log_dollar_volume < 8.3148 and chaikin_osc <  | lab_search | 2026-09-24 | -6.78% |
| Volatility Contraction hold=10 stop=3 zc=-1 | volatility_contraction | 2026-09-24 | -6.80% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -6.80% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -6.80% |
| Balance Sheet hold=40 q=0.3 stop=5 | balance_sheet | 2026-09-24 | -6.80% |
| Balance Sheet hold=60 q=0.3 stop=5 | balance_sheet | 2026-09-24 | -6.80% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -6.81% |
| Price and Earning Momentum · reproduction · lookback 1.5 | kf_momentum | 2026-09-28 | -6.83% |
| Lab 2c8d41: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -6.84% |
| Lab 9fdf7a: ((rank(price_above_sma50) > 0.3346 and pct_off_5 | lab_search | 2026-09-24 | -6.86% |
| Turnover: Liquidity or Uncertainty? · reproduction · stop 1. | kf_liquidity | 2026-09-25 | -6.86% |
| Lab 727f99: ((rank(dollar_volume_20) > 0.8277 and price_abov | lab_search | 2026-09-24 | -6.86% |
| Lab d2076e: ((rank(price_above_sma50) > 0.424 and atr_14 > 0 | lab_search | 2026-09-24 | -6.87% |
| cci_extreme · reproduction | kf_mean_reversion | 2026-09-25 | -6.87% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-09-25 | -6.87% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -6.88% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -6.88% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -6.88% |
| Lab 1e420a: ((rank(price_above_sma50) > 0.35 and pct_off_52w | lab_search | 2026-09-24 | -6.89% |
| value_momentum v3 (trend_filter) | value_momentum | 2026-09-25 | -6.89% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -6.93% |
| st_volume_shock v2 (longer_hold) | st_volume_shock | 2026-09-24 | -6.94% |
| Lab 5b41fa: ((rank(price_above_sma200) > 0.4238 and drawdown | lab_search | 2026-09-24 | -6.94% |
| Lab 65b7b9: ((rank(dollar_volume_20) > 0.7 and price_above_s | lab_search | 2026-09-24 | -6.95% |
| Lab f95ab4: ((rank(price_above_sma50) > 0.443 and atr_14 > 0 | lab_search | 2026-09-24 | -6.96% |
| Lab 543212: ((rank(price_above_sma50) > 0.2711 and pct_off_5 | lab_search | 2026-09-24 | -6.97% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -6.98% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -6.98% |
| Lab c4099f: (pct_change(sma_200, 20) < -0.1747 or crosses_ab | lab_search | 2026-09-24 | -6.98% |
| Lab 7721c2: ((rank(price_above_sma50) > 0.4241 and pct_off_5 | lab_search | 2026-09-24 | -6.98% |
| Lab b7892e: ((rank(price_above_sma200) > 0.6404 and pct_off_ | lab_search | 2026-09-24 | -6.99% |
| Lab f9e829: ((rank(macd) > 0.5898 and golden_cross < 0.5) an | lab_search | 2026-09-24 | -7.03% |
| St Rsi Oversold hold=3 rsi=30 stop=2.5 | st_rsi_oversold | 2026-09-24 | -7.03% |
| quality_momentum v1 | quality_momentum | 2026-09-22 | -7.04% |
| Bollinger Reversion band=0 hold=5 stop=2 | bollinger_reversion | 2026-09-24 | -7.05% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -7.06% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -7.06% |
| Lab 6bdd78: not((rank(bb_pct) < 0.805 or (crosses_below(cci_ | lab_search | 2026-09-24 | -7.09% |
| Lab 317410: ((rank(price_above_sma50) > 0.2901 and pct_off_5 | lab_search | 2026-09-24 | -7.16% |
| Momentum and Reversal Combined with Volatility Effect in Sto | kf_momentum | 2026-09-25 | -7.17% |
| Lab c75b9c: ((rank(price_above_sma50) > 0.438 and pct_off_52 | lab_search | 2026-09-24 | -7.20% |
| Lab e764f7: (rsi_14 < 35.821 and pct_off_52w_low > 0.5907) | lab_search | 2026-09-24 | -7.20% |
| Lab 453bda: ((rank(rsi_14) > 0.4238 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -7.21% |
| Why is the Accrual Anomaly not Arbitraged Away? · reproducti | kf_fundamental | 2026-09-25 | -7.22% |
| quality_momentum v1 | quality_momentum | 2026-09-22 | -7.22% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -7.26% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -7.26% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -7.26% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -7.26% |
| Size Matters, if You Control Your Junk · reproduction · hold | kf_size | 2026-10-02 | -7.28% |
| macd_cross v2 (longer_hold) | macd_cross | 2026-09-24 | -7.29% |
| Momentum Volume hold=10 q=0.8 stop=3 | momentum_volume | 2026-09-24 | -7.30% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-21 | -7.30% |
| Fundamental Momentum hold=40 n=126 stop=5 | fundamental_momentum | 2026-09-24 | -7.30% |
| Fundamental Momentum hold=60 n=126 stop=5 | fundamental_momentum | 2026-09-24 | -7.30% |
| Bollinger Reversion band=0 hold=10 stop=3 | bollinger_reversion | 2026-09-24 | -7.31% |
| bollinger_reversion v2 (longer_hold) | bollinger_reversion | 2026-09-24 | -7.31% |
| Fundamental Price Momentum hold=40 n=63 q=0.7 stop=3 | fundamental_price_momentum | 2026-09-24 | -7.31% |
| Lab 2fe738: ((rank(log_dollar_volume) > 0.754 and price_abov | lab_search | 2026-09-24 | -7.34% |
| payday v2 (longer_hold) | payday | 2026-09-24 | -7.34% |
| Lab 5924db: (((chaikin_osc < 7.229 and chaikin_osc < -955749 | lab_search | 2026-09-24 | -7.34% |
| Absolute Momentum: A Simple Rule-Based Strategy and Universa | kf_trend | 2026-09-25 | -7.36% |
| Lab 2a40b3: ((crosses_above(rank(roc_10), 0.7) or pct_off_52 | lab_search | 2026-09-24 | -7.36% |
| Lab ee0632: ((rank(dollar_volume_20) > 0.6044 and price_abov | lab_search | 2026-09-24 | -7.37% |
| Lab b615d2: ((rank(price_above_sma50) > 0.4291 or pct_off_52 | lab_search | 2026-09-24 | -7.38% |
| Why is the Accrual Anomaly not Arbitraged Away? · reproducti | kf_fundamental | 2026-09-25 | -7.39% |
| Quality Piotroski f=7 hold=60 stop=5 | quality_piotroski | 2026-09-24 | -7.41% |
| quality_piotroski v1 | quality_piotroski | 2026-09-24 | -7.41% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -7.44% |
| Lab a4ba8a: ((rank(close) > 0.7 and price_above_sma200 > 0.5 | lab_search | 2026-09-24 | -7.45% |
| Lab 073b3c: ((rank(price_above_sma50) > 0.2694 and pct_off_5 | lab_search | 2026-09-24 | -7.45% |
| Lab f9a02c: ((rank(atr_14) > 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | -7.47% |
| Lab 8e20ab: ((rank(rsi_14) > 0.3341 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -7.48% |
| Lab 0e3bfe: ((rank(price_above_sma50) > 0.424 and pct_off_52 | lab_search | 2026-09-24 | -7.50% |
| Xs Momentum hold=20 q=0.8 stop=3 | xs_momentum | 2026-09-25 | -7.51% |
| value_momentum v3 (trend_filter) | value_momentum | 2026-09-25 | -7.51% |
| Lab 776276: (dollar_volume_20 > 1.69446e+07 and (crosses_bel | lab_search | 2026-09-24 | -7.52% |
| Lab 826f90: ((rank(dollar_volume_20) > 0.8452 and price_abov | lab_search | 2026-09-24 | -7.55% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -7.55% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-10-16 | -7.56% |
| payday v2 (longer_hold) | payday | 2026-09-24 | -7.57% |
| Momentum Volume hold=20 q=0.8 stop=2 | momentum_volume | 2026-09-25 | -7.57% |
| Company-Size Effect on the Polish Stock Market · reproductio | kf_size | 2026-09-25 | -7.57% |
| Company-Size Effect on the Polish Stock Market · reproductio | kf_size | 2026-09-25 | -7.57% |
| The Volatility Effect Revisited · reproduction · lookback 0. | kf_low_volatility | 2026-09-29 | -7.60% |
| Crisis-Proof Alpha Portfolio Dynamic Sector Rotation Strateg | kf_momentum | 2026-09-25 | -7.61% |
| Bollinger Reversion band=0 hold=10 stop=2 | bollinger_reversion | 2026-09-24 | -7.61% |
| bollinger_reversion v2 (longer_hold) | bollinger_reversion | 2026-09-24 | -7.61% |
| Value Momentum hold=40 q=0.7 stop=4 | value_momentum | 2026-09-24 | -7.62% |
| value_momentum v2 (longer_hold) | value_momentum | 2026-09-24 | -7.62% |
| value_momentum v2 (longer_hold) | value_momentum | 2026-09-24 | -7.62% |
| Lab b20a4c: ((rank(macd_signal) > 0.5009 and drawdown_200 >  | lab_search | 2026-09-24 | -7.64% |
| Lab 9a9842: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -7.70% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -7.71% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -7.71% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -7.72% |
| Lab a4b55f: ((rank(rsi_14) < 0.7 and pct_off_52w_low > 0.5)  | lab_search | 2026-09-24 | -7.73% |
| The Low Volatility Anomaly in Equity Sectors – 10 Years Late | kf_low_volatility | 2026-09-25 | -7.73% |
| Bollinger Reversion band=0 hold=5 stop=3 | bollinger_reversion | 2026-09-24 | -7.74% |
| Lab 32e3e6: ((rank(dollar_volume_20) > 0.7451 and price_abov | lab_search | 2026-09-24 | -7.74% |
| Bollinger Reversion band=0.05 hold=10 stop=2 | bollinger_reversion | 2026-09-24 | -7.76% |
| bollinger_reversion v2 (longer_hold) | bollinger_reversion | 2026-09-24 | -7.76% |
| Xs Momentum hold=20 q=0.8 stop=2 | xs_momentum | 2026-09-25 | -7.80% |
| Lab cefc6a: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -7.82% |
| Rising 200 · Stop 3.3 | momentum | 2026-09-04 | -7.83% |
| Value Momentum hold=40 q=0.7 stop=3 | value_momentum | 2026-09-24 | -7.83% |
| value_momentum v2 (longer_hold) | value_momentum | 2026-09-24 | -7.83% |
| value_momentum v2 (longer_hold) | value_momentum | 2026-09-24 | -7.83% |
| williams_r_oversold · reproduction · exit 3.0 | kf_mean_reversion | 2026-10-02 | -7.85% |
| williams_r_oversold · reproduction · holding_period 2.0 | kf_mean_reversion | 2026-10-02 | -7.85% |
| williams_r_oversold · reproduction · universe liquid | kf_mean_reversion | 2026-10-02 | -7.85% |
| Do Earnings Explain the January Effect? · reproduction · sto | kf_seasonality | 2026-10-13 | -7.88% |
| Lab 32aa9c: ((rank(pct_off_52w_low) > 0.7 and roc_10 < 0.5)  | lab_search | 2026-09-24 | -7.89% |
| Lab d90e41: ((rank(price_above_sma50) > 0.3577 and pct_off_5 | lab_search | 2026-09-24 | -7.90% |
| Lab e364e1: ((rank(price_above_sma50) > 0.3524 and pct_off_5 | lab_search | 2026-09-24 | -7.90% |
| The Value Relevance of Changes in Financial Leverage · repro | kf_value | 2026-09-25 | -7.95% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -7.95% |
| Lab 674040: ((rank(price_above_sma50) > 0.427 or pct_off_52w | lab_search | 2026-09-24 | -7.98% |
| St Bollinger Low hold=2 stop=2.5 | st_bollinger_low | 2026-09-24 | -7.99% |
| St Volume Shock hold=3 stop=2.5 | st_volume_shock | 2026-09-24 | -8.00% |
| cci_extreme · reproduction · stop 1.0 | kf_mean_reversion | 2026-10-01 | -8.00% |
| Lab b5482a: ((rank(dollar_volume_20) > 0.6006 and price_abov | lab_search | 2026-09-24 | -8.02% |
| Lab 7caea5: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -8.03% |
| Size Matters, if You Control Your Junk · reproduction · hold | kf_size | 2026-10-02 | -8.03% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-10-07 | -8.03% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-09-25 | -8.04% |
| Lab eb97c7: ((rank(golden_cross) > 0.7 and atr_14 > 0.3523)  | lab_search | 2026-09-24 | -8.05% |
| Inflation Illusion and Post-earnings-announcement Drift · re | kf_earnings_surprise | 2026-10-02 | -8.09% |
| Fundamental Momentum hold=40 n=126 stop=3 | fundamental_momentum | 2026-09-24 | -8.09% |
| Fundamental Momentum hold=60 n=126 stop=3 | fundamental_momentum | 2026-09-24 | -8.09% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -8.09% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -8.09% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -8.09% |
| Lab ef6c8d: ((rank(dollar_volume_20) > 0.7704 and price_abov | lab_search | 2026-09-24 | -8.10% |
| The Volatility Effect Revisited · reproduction · holding_per | kf_low_volatility | 2026-09-29 | -8.12% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -8.13% |
| Lab d837e1: (((cci_20 < 7.229 and chaikin_osc < -955749) and | lab_search | 2026-09-24 | -8.14% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-10-20 | -8.18% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-27 | -8.20% |
| st_stoch_oversold v2 (longer_hold) | st_stoch_oversold | 2026-09-24 | -8.21% |
| Macd Cross hold=20 stop=2 | macd_cross | 2026-09-25 | -8.22% |
| Lab c5a6e1: (not((crosses_above(macd, macd_signal) or crosse | lab_search | 2026-09-24 | -8.26% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -8.27% |
| momentum_volume v3 (trend_filter) | momentum_volume | 2026-09-25 | -8.29% |
| Rising 200 · Stop 2.5 · exit tp=20.0 trail=- | momentum | 2026-09-23 | -8.32% |
| Bollinger Reversion band=0.05 hold=5 stop=2 | bollinger_reversion | 2026-09-24 | -8.32% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -8.36% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | -8.40% |
| Lab 060e78: ((rank(price_above_sma50) > 0.427 or pct_off_52w | lab_search | 2026-09-24 | -8.40% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -8.42% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -8.43% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -8.43% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -8.43% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -8.43% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -8.43% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -8.44% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -8.44% |
| obv_accumulation · reproduction | kf_momentum | 2026-09-25 | -8.47% |
| cci_extreme · reproduction · stop -1.0 | kf_mean_reversion | 2026-10-01 | -8.48% |
| Lab 98c9bd: ((rank(rsi_14) > 0.7 or pct_off_52w_low > 0.5) a | lab_search | 2026-09-24 | -8.49% |
| An Anatomy of Calendar Effects · reproduction · exit 3.0 | kf_seasonality | 2026-10-14 | -8.50% |
| An Anatomy of Calendar Effects · reproduction · holding_peri | kf_seasonality | 2026-10-14 | -8.50% |
| An Anatomy of Calendar Effects · reproduction · universe liq | kf_seasonality | 2026-10-14 | -8.50% |
| Momentum Volume hold=20 q=0.8 stop=2 | momentum_volume | 2026-09-24 | -8.52% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -8.52% |
| Lab 24c393: ((rank(log_dollar_volume) > 0.8478 and price_abo | lab_search | 2026-09-24 | -8.53% |
| Volatility Breakout hold=10 stop=3 vr=1.5 | volatility_breakout | 2026-09-24 | -8.53% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -8.53% |
| Lab cb2afd: ((rank(log_dollar_volume) > 0.8819 and price_abo | lab_search | 2026-09-24 | -8.55% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-28 | -8.58% |
| Bollinger Reversion band=0.05 hold=5 stop=3 | bollinger_reversion | 2026-09-24 | -8.58% |
| Xs Momentum hold=10 q=0.8 stop=3 | xs_momentum | 2026-09-24 | -8.62% |
| williams_r_oversold · reproduction · stop 1.0 | kf_mean_reversion | 2026-10-02 | -8.64% |
| The pricing of accruals for profit and loss firms · reproduc | kf_quality | 2026-10-19 | -8.64% |
| Low-risk effect: evidence, explanations and approaches to en | kf_low_volatility | 2026-09-25 | -8.65% |
| Quality Roa hold=40 q=0.9 stop=5 | quality_roa | 2026-09-24 | -8.66% |
| Quality Roa hold=60 q=0.9 stop=5 | quality_roa | 2026-09-24 | -8.66% |
| Lab f1c96c: ((rank(price_above_sma50) > 0.4241 and price_abo | lab_search | 2026-09-24 | -8.67% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | -8.67% |
| williams_r_oversold · reproduction · universe large_cap | kf_mean_reversion | 2026-10-02 | -8.69% |
| St Volume Shock hold=2 stop=2.5 | st_volume_shock | 2026-09-24 | -8.71% |
| st_volume_shock v2 (longer_hold) | st_volume_shock | 2026-09-24 | -8.71% |
| Lab a7d5e9: ((rank(log_dollar_volume) > 0.5645 and pct_off_5 | lab_search | 2026-09-24 | -8.71% |
| momentum_pullback · reproduction | kf_momentum | 2026-09-25 | -8.71% |
| Momentum in Mutual Fund Returns · reproduction · lookback 0. | kf_momentum | 2026-09-25 | -8.71% |
| Value Momentum hold=40 q=0.8 stop=4 | value_momentum | 2026-09-24 | -8.73% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -8.73% |
| Volatility Breakout hold=10 stop=2 vr=2 | volatility_breakout | 2026-09-25 | -8.76% |
| Consistent momentum strategy · reproduction · lookback 0.5 | kf_momentum | 2026-09-25 | -8.78% |
| st_momentum_1d v3 (trend_filter) | st_momentum_1d | 2026-09-25 | -8.80% |
| Lab ffeacf: ((rank(price_above_sma200) > 0.4843 and pct_off_ | lab_search | 2026-09-24 | -8.85% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -8.87% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -8.87% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -8.87% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -8.87% |
| Implications of Transaction Costs for the Post-Earnings-Anno | kf_earnings_surprise | 2026-10-05 | -8.87% |
| Lab d506e5: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -8.88% |
| macd_cross v2 (longer_hold) | macd_cross | 2026-09-24 | -8.90% |
| Lab 3f0e2a: ((rank(price_above_sma50) > 0.3309 and pct_off_5 | lab_search | 2026-09-24 | -8.91% |
| Momentum Volume hold=20 q=0.9 stop=2 | momentum_volume | 2026-09-25 | -8.92% |
| Volatility Breakout hold=10 stop=2 vr=1.5 | volatility_breakout | 2026-09-24 | -8.92% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -8.92% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -8.92% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-22 | -8.96% |
| The Volatility Effect Revisited · reproduction · exit 3.0 | kf_low_volatility | 2026-09-29 | -8.96% |
| The Volatility Effect Revisited · reproduction · universe li | kf_low_volatility | 2026-09-29 | -8.96% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -8.96% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-10-23 | -9.01% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-10-14 | -9.02% |
| January Effect in Stocks · reproduction · holding_period 2.0 | kf_seasonality | 2026-09-25 | -9.02% |
| Lab 4a6a4c: ((rank(macd_signal) > 0.7 or crosses_above(price | lab_search | 2026-09-24 | -9.02% |
| Quality Roa hold=40 q=0.8 stop=5 | quality_roa | 2026-09-24 | -9.04% |
| Quality Roa hold=60 q=0.8 stop=5 | quality_roa | 2026-09-24 | -9.04% |
| Value Momentum hold=40 q=0.8 stop=3 | value_momentum | 2026-09-24 | -9.05% |
| Xs Momentum hold=20 q=0.8 stop=2 | xs_momentum | 2026-09-24 | -9.06% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -9.06% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -9.11% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -9.17% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | -9.17% |
| kf_other v1 | kf_other | 2026-09-24 | -9.19% |
| St Stoch Oversold hold=3 k=10 stop=2.5 | st_stoch_oversold | 2026-09-24 | -9.20% |
| Value Momentum hold=20 q=0.7 stop=4 | value_momentum | 2026-09-24 | -9.21% |
| Lab 47bf48: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -9.26% |
| Xs Momentum hold=10 q=0.8 stop=2 | xs_momentum | 2026-09-24 | -9.30% |
| Lab c9f4fc: ((rank(log_dollar_volume) > 0.7742 and price_abo | lab_search | 2026-09-24 | -9.34% |
| Lab 4d5230: ((rank(price_above_sma50) > 0.427 and pct_off_52 | lab_search | 2026-09-24 | -9.37% |
| kf_factor v3 (trend_filter) | kf_factor | 2026-10-23 | -9.37% |
| Xs Momentum hold=20 q=0.9 stop=2 | xs_momentum | 2026-09-24 | -9.37% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -9.37% |
| Lab caa303: ((rank(dollar_volume_20) > 0.7 and pct_off_52w_l | lab_search | 2026-09-24 | -9.40% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-29 | -9.43% |
| Balance Sheet hold=60 q=0.2 stop=5 | balance_sheet | 2026-09-24 | -9.44% |
| balance_sheet v1 | balance_sheet | 2026-09-24 | -9.44% |
| Momentum Volume hold=20 q=0.9 stop=2 | momentum_volume | 2026-09-24 | -9.47% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -9.47% |
| Value Momentum hold=20 q=0.7 stop=3 | value_momentum | 2026-09-24 | -9.47% |
| kf_quality v2 (longer_hold) | kf_quality | 2026-10-14 | -9.51% |
| An Anatomy of Calendar Effects · reproduction · universe lar | kf_seasonality | 2026-10-14 | -9.51% |
| Lab 1c647b: ((rank(dollar_volume_20) > 0.7979 and price_abov | lab_search | 2026-09-24 | -9.52% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -9.52% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -9.53% |
| Volatility Breakout hold=10 stop=2 vr=2 | volatility_breakout | 2026-09-24 | -9.53% |
| volatility_breakout v2 (longer_hold) | volatility_breakout | 2026-09-24 | -9.53% |
| Lab fd5140: ((crosses_above(rank(macd_signal), 0.7) or pct_o | lab_search | 2026-09-24 | -9.54% |
| Short-sellers, fundamental analysis and stock returns · repr | kf_fundamental | 2026-09-25 | -9.55% |
| st_reversal_1d v2 (longer_hold) | st_reversal_1d | 2026-09-24 | -9.55% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-10-12 | -9.59% |
| Ma Cross hold=10 stop=3 | ma_cross | 2026-09-24 | -9.60% |
| Low Accruals hold=40 q=0.1 stop=5 | low_accruals | 2026-09-24 | -9.61% |
| Low Accruals hold=60 q=0.1 stop=5 | low_accruals | 2026-09-24 | -9.61% |
| Quality Roa hold=40 q=0.8 stop=3 | quality_roa | 2026-09-24 | -9.66% |
| Quality Roa hold=60 q=0.8 stop=3 | quality_roa | 2026-09-24 | -9.66% |
| Lab 6120b9: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -9.68% |
| Size Matters, if You Control Your Junk · reproduction | kf_size | 2026-09-25 | -9.68% |
| Momentum Volume hold=10 q=0.9 stop=2 | momentum_volume | 2026-09-24 | -9.69% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -9.70% |
| liquidity_premium v1 | liquidity_premium | 2026-09-24 | -9.70% |
| Lab 62fd61: ((rank(roc_10) < 0.6138 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -9.70% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -9.73% |
| Macd Cross hold=10 stop=3 | macd_cross | 2026-09-24 | -9.73% |
| macd_cross v2 (longer_hold) | macd_cross | 2026-09-24 | -9.73% |
| Short Term Reversal · reproduction | kf_reversal | 2026-09-25 | -9.74% |
| Roa effect within stocks · reproduction · exit 3.0 | kf_quality | 2026-09-25 | -9.76% |
| Roa effect within stocks · reproduction · universe liquid | kf_quality | 2026-09-25 | -9.76% |
| Lab 28accc: (roc_10 < -10.9569 or crosses_above(pct_change(m | lab_search | 2026-09-24 | -9.76% |
| Fcf Quality q=0.8 | fcf_quality | 2026-09-24 | -9.79% |
| Quality Low Volatility q=0.8 | quality_low_volatility | 2026-09-24 | -9.79% |
| Roic Valuation q=0.8 | roic_valuation | 2026-09-24 | -9.79% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -9.84% |
| Momentum Volume hold=20 q=0.9 stop=3 | momentum_volume | 2026-09-24 | -9.86% |
| momentum_volume v2 (longer_hold) | momentum_volume | 2026-09-24 | -9.86% |
| St Bollinger Low hold=5 stop=2.5 | st_bollinger_low | 2026-09-24 | -9.86% |
| st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | 2026-09-24 | -9.89% |
| Are Institutions Momentum Traders? · reproduction · lookback | kf_momentum | 2026-10-23 | -9.91% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -9.92% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-09-25 | -9.95% |
| Lab 8afa25: (roc_10 < -10.9569 or crosses_above(pct_change(m | lab_search | 2026-09-24 | -9.95% |
| st_stoch_oversold v2 (longer_hold) | st_stoch_oversold | 2026-09-24 | -9.97% |
| st_stoch_oversold v3 (trend_filter) | st_stoch_oversold | 2026-09-24 | -9.97% |
| Lab 991aae: (rsi_14 < 34.6622 and pct_off_52w_low > 0.7108) | lab_search | 2026-09-24 | -9.98% |
| Roa effect within stocks · reproduction · universe large_cap | kf_quality | 2026-09-25 | -9.99% |
| mean_reversion_to_sma · reproduction · stop 1.0 | kf_mean_reversion | 2026-10-05 | -10.00% |
| Another look at trading costs and short-term reversal profit | kf_reversal | 2026-09-25 | -10.00% |
| Are Institutions Momentum Traders? · reproduction · lookback | kf_momentum | 2026-10-23 | -10.01% |
| Lab 982b9e: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -10.02% |
| kf_low_volatility v1 | kf_low_volatility | 2026-09-24 | -10.02% |
| Lab 7a255d: (rsi_14 < 32.5959 and pct_off_52w_low > 0.7341) | lab_search | 2026-09-24 | -10.03% |
| Value Momentum hold=20 q=0.8 stop=3 | value_momentum | 2026-09-24 | -10.03% |
| Low Accruals hold=40 q=0.2 stop=3 | low_accruals | 2026-09-24 | -10.04% |
| Low Accruals hold=60 q=0.2 stop=3 | low_accruals | 2026-09-24 | -10.04% |
| Macd Cross hold=20 stop=3 | macd_cross | 2026-09-24 | -10.05% |
| macd_cross v2 (longer_hold) | macd_cross | 2026-09-24 | -10.05% |
| Value Momentum hold=20 q=0.8 stop=4 | value_momentum | 2026-09-24 | -10.06% |
| Xs Momentum hold=20 q=0.9 stop=3 | xs_momentum | 2026-09-25 | -10.07% |
| An Anatomy of Calendar Effects · reproduction · holding_peri | kf_seasonality | 2026-10-14 | -10.09% |
| Short Interest q=0.2 | short_interest | 2026-09-24 | -10.10% |
| Short Interest q=0.2 | short_interest | 2026-09-24 | -10.10% |
| The Volatility Effect Revisited · reproduction · holding_per | kf_low_volatility | 2026-09-29 | -10.11% |
| williams_r_oversold · reproduction · stop -1.0 | kf_mean_reversion | 2026-10-02 | -10.12% |
| Momentum Volume hold=20 q=0.9 stop=3 | momentum_volume | 2026-09-25 | -10.14% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -10.15% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -10.15% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -10.15% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -10.15% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -10.16% |
| Volatility Contraction hold=10 stop=3 zc=-1.5 | volatility_contraction | 2026-09-24 | -10.19% |
| Xs Momentum hold=20 q=0.9 stop=2 | xs_momentum | 2026-09-25 | -10.21% |
| kf_mean_reversion v1 | kf_mean_reversion | 2026-09-24 | -10.21% |
| value_quality v1 | value_quality | 2026-09-22 | -10.23% |
| Lab 3722ff: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -10.23% |
| Optimal trading with a trailing stop · reproduction · holdin | kf_other | 2026-09-25 | -10.23% |
| Lab 403de7: (rsi_14 < 33.7551 and pct_off_52w_low > 0.7037) | lab_search | 2026-09-24 | -10.25% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-10-12 | -10.27% |
| mean_reversion_to_sma · reproduction · universe large_cap | kf_mean_reversion | 2026-10-05 | -10.28% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-09-25 | -10.32% |
| Roa effect within stocks · reproduction · stop 1.0 | kf_quality | 2026-09-25 | -10.35% |
| Optimal trading with a trailing stop · reproduction · univer | kf_other | 2026-09-25 | -10.38% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -10.39% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -10.39% |
| Optimal trading with a trailing stop · reproduction · stop - | kf_other | 2026-09-25 | -10.41% |
| St Reversal 5D hold=3 q=0.05 stop=2.5 | st_reversal_5d | 2026-09-24 | -10.45% |
| Momentum and reversal combined with volatility effect in sto | kf_momentum | 2026-09-25 | -10.45% |
| Are Institutions Momentum Traders? · reproduction | kf_momentum | 2026-09-25 | -10.45% |
| Momentum in Mutual Fund Returns · reproduction · stop -1.0 | kf_momentum | 2026-09-25 | -10.49% |
| mean_reversion_to_sma · reproduction | kf_mean_reversion | 2026-09-25 | -10.50% |
| Left-Tail Momentum: Underreaction to Bad News, Costly Arbitr | kf_reversal | 2026-10-13 | -10.50% |
| Xs Momentum hold=20 q=0.9 stop=3 | xs_momentum | 2026-09-24 | -10.51% |
| xs_momentum v2 (longer_hold) | xs_momentum | 2026-09-24 | -10.51% |
| Lab 92e4d6: (not((crosses_above(price_above_sma200, macd_sig | lab_search | 2026-09-24 | -10.52% |
| kf_fundamental v2 (longer_hold) | kf_fundamental | 2026-10-12 | -10.59% |
| kf_seasonality v3 (trend_filter) | kf_seasonality | 2026-10-27 | -10.59% |
| Lab 08f84a: stoch_k < 14.2013 | lab_search | 2026-09-24 | -10.60% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -10.61% |
| Company-Size Effect on the Polish Stock Market · reproductio | kf_size | 2026-09-25 | -10.63% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-10-07 | -10.65% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -10.65% |
| Macd Cross hold=10 stop=2 | macd_cross | 2026-09-24 | -10.66% |
| macd_cross v2 (longer_hold) | macd_cross | 2026-09-24 | -10.66% |
| St Momentum 1D hold=1 q=0.9 stop=2 | st_momentum_1d | 2026-09-24 | -10.67% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -10.67% |
| Lab 82a944: (((log_dollar_volume < 8.2105 and chaikin_osc <  | lab_search | 2026-09-24 | -10.68% |
| Momentum 9 1 q=0.8 stop=4 · stop 6x ATR | momentum_9_1_stop6x | 2026-10-20 | -10.73% |
| Lab 580984: pct_change(sma_200, 3) > 0.0199 | lab_search | 2026-09-24 | -10.77% |
| Lab 1dc1b6: pct_change(sma_200, 3) > 0.0263 | lab_search | 2026-09-24 | -10.80% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | -10.84% |
| Are Institutions Momentum Traders? · reproduction · stop -1. | kf_momentum | 2026-10-23 | -10.84% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -10.85% |
| Short-sellers, fundamental analysis and stock returns · repr | kf_fundamental | 2026-09-25 | -10.86% |
| Short-sellers, fundamental analysis and stock returns · repr | kf_fundamental | 2026-09-25 | -10.86% |
| Short-sellers, fundamental analysis and stock returns · repr | kf_fundamental | 2026-09-25 | -10.86% |
| volatility_breakout v3 (trend_filter) | volatility_breakout | 2026-09-25 | -10.89% |
| Macd Cross hold=20 stop=3 | macd_cross | 2026-09-25 | -10.89% |
| Rankings of published price-earnings ratios and value invest | kf_value | 2026-09-25 | -10.90% |
| Lab 067153: ((rank(price_above_sma50) > 0.3519 and pct_off_5 | lab_search | 2026-09-24 | -10.93% |
| st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | 2026-09-24 | -11.00% |
| Profitability hold=40 q=0.8 stop=5 | profitability | 2026-09-24 | -11.02% |
| Profitability hold=60 q=0.8 stop=5 | profitability | 2026-09-24 | -11.02% |
| Volatility Contraction hold=20 stop=2 zc=-1 | volatility_contraction | 2026-09-24 | -11.04% |
| volatility_contraction v2 (longer_hold) | volatility_contraction | 2026-09-24 | -11.04% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -11.05% |
| Roa effect within stocks · reproduction · stop -1.0 | kf_quality | 2026-09-25 | -11.10% |
| Lab 90e85f: ((crosses_above(rank(price_above_sma200), 0.7) o | lab_search | 2026-09-24 | -11.11% |
| Lab cdad29: ((rank(pct_of_52w_high) < 0.7 and pct_off_52w_lo | lab_search | 2026-09-24 | -11.14% |
| Lab 47cfc9: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -11.16% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-10-15 | -11.21% |
| Lab 0eb4fe: chaikin_osc < -1.3828e+06 | lab_search | 2026-09-24 | -11.23% |
| Lab 878ac0: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -11.24% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-10-12 | -11.28% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-10-12 | -11.28% |
| Rising 200 · Stop 2.6 | momentum | 2026-09-04 | -11.30% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-10-13 | -11.30% |
| Roa effect within stocks · reproduction · holding_period 2.0 | kf_quality | 2026-09-25 | -11.35% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -11.37% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-09-28 | -11.38% |
| Politician Buying buyers=1 hold=60 stop=3 | politician_buying | 2026-09-25 | -11.40% |
| st_momentum_1d v3 (trend_filter) | st_momentum_1d | 2026-09-24 | -11.42% |
| Are Institutions Momentum Traders? · reproduction · stop 1.0 | kf_momentum | 2026-10-23 | -11.42% |
| January Effect in Stocks · reproduction · stop -1.0 | kf_seasonality | 2026-09-25 | -11.45% |
| Lab ef58ab: roc_10 < -9.0847 | lab_search | 2026-09-24 | -11.45% |
| St Reversal 5D hold=5 q=0.1 stop=2.5 | st_reversal_5d | 2026-09-24 | -11.45% |
| Volatility Contraction hold=20 stop=3 zc=-1 | volatility_contraction | 2026-09-24 | -11.46% |
| volatility_contraction v2 (longer_hold) | volatility_contraction | 2026-09-24 | -11.46% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | -11.48% |
| value_quality_momentum v1 | value_quality_momentum | 2026-09-22 | -11.48% |
| williams_r_oversold · reproduction | kf_mean_reversion | 2026-09-25 | -11.51% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -11.53% |
| Xs Momentum hold=10 q=0.9 stop=2 | xs_momentum | 2026-09-24 | -11.57% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -11.63% |
| Lab bc9393: ((rank(log_dollar_volume) > 0.7146 and pct_off_5 | lab_search | 2026-09-24 | -11.66% |
| Lab f2704b: (roc_10 < -10.9569 and pct_change(macd, 10) < ra | lab_search | 2026-09-24 | -11.66% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -11.67% |
| Lab d10844: (((chaikin_osc < 7.229 and chaikin_osc < -955749 | lab_search | 2026-09-24 | -11.68% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-16 | -11.70% |
| st_reversal_5d v2 (longer_hold) | st_reversal_5d | 2026-09-24 | -11.71% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | -11.76% |
| Do Investors Under-React to ROE? · reproduction | kf_quality | 2026-09-25 | -11.79% |
| Lab 19994f: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -11.81% |
| kf_reversal v3 (trend_filter) | kf_reversal | 2026-10-21 | -11.82% |
| Are Institutions Momentum Traders? · reproduction · universe | kf_momentum | 2026-10-23 | -11.83% |
| Are Institutions Momentum Traders? · reproduction · exit 3.0 | kf_momentum | 2026-10-23 | -11.87% |
| Are Institutions Momentum Traders? · reproduction · holding_ | kf_momentum | 2026-10-23 | -11.87% |
| Are Institutions Momentum Traders? · reproduction · holding_ | kf_momentum | 2026-10-23 | -11.87% |
| Are Institutions Momentum Traders? · reproduction · universe | kf_momentum | 2026-10-23 | -11.87% |
| Low Accruals hold=40 q=0.2 stop=5 | low_accruals | 2026-09-24 | -11.90% |
| Low Accruals hold=60 q=0.2 stop=5 | low_accruals | 2026-09-24 | -11.90% |
| Lab 15894a: ((rank(rsi_14) > 0.7 and price_above_sma200 < 0. | lab_search | 2026-09-24 | -11.91% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -11.94% |
| Value and Size Puzzles: A Commented Survey · reproduction ·  | kf_value | 2026-10-05 | -11.95% |
| An Anatomy of Calendar Effects · reproduction · stop 1.0 | kf_seasonality | 2026-10-14 | -11.96% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-27 | -11.99% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.01% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-10-12 | -12.01% |
| Lab f1c848: ((rank(price_above_sma50) > 0.438 or pct_off_52w | lab_search | 2026-09-24 | -12.02% |
| Lab 9a5e9b: not((crosses_above(rank(willr_14), 0.805) or (cr | lab_search | 2026-09-24 | -12.04% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.05% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.05% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.05% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.05% |
| Lab 446925: (roc_10 < -10.9569 or crosses_above(pct_change(m | lab_search | 2026-09-24 | -12.06% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -12.12% |
| Does Trend Following Work on Stocks · reproduction | kf_trend | 2026-09-25 | -12.14% |
| Optimal trading with a trailing stop · reproduction · exit 3 | kf_other | 2026-09-25 | -12.14% |
| Optimal trading with a trailing stop · reproduction · univer | kf_other | 2026-09-25 | -12.14% |
| Momentum in Mutual Fund Returns · reproduction · universe la | kf_momentum | 2026-09-25 | -12.15% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -12.16% |
| Momentum in Mutual Fund Returns · reproduction · exit 3.0 | kf_momentum | 2026-09-25 | -12.16% |
| Momentum in Mutual Fund Returns · reproduction · holding_per | kf_momentum | 2026-09-25 | -12.16% |
| Momentum in Mutual Fund Returns · reproduction · holding_per | kf_momentum | 2026-09-25 | -12.16% |
| Momentum in Mutual Fund Returns · reproduction · universe li | kf_momentum | 2026-09-25 | -12.16% |
| An Anatomy of Calendar Effects · reproduction · stop -1.0 | kf_seasonality | 2026-10-14 | -12.16% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -12.17% |
| Decomposing Momentum Spread · reproduction · lookback 0.5 | kf_momentum | 2026-10-13 | -12.19% |
| Why Does an Equal-Weighted Portfolio Outperform Value- and P | kf_factor | 2026-09-25 | -12.21% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.21% |
| Lab 3df36f: (pct_change(sma_200, 10) < -0.063 or crosses_abo | lab_search | 2026-09-24 | -12.22% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -12.25% |
| Rd Intensity q=0.8 | rd_intensity | 2026-09-24 | -12.25% |
| rd_intensity v2 (longer_hold) | rd_intensity | 2026-09-24 | -12.25% |
| Lab e01601: ((rank(log_dollar_volume) > 0.7 and pct_off_52w_ | lab_search | 2026-09-24 | -12.26% |
| mean_reversion_to_sma · reproduction · holding_period 0.5 | kf_mean_reversion | 2026-10-05 | -12.28% |
| kf_reversal v1 | kf_reversal | 2026-09-24 | -12.30% |
| Lab 900674: pct_change(sma_200, 3) > 0.024 | lab_search | 2026-09-24 | -12.36% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -12.38% |
| fundamental_price_momentum v1 | fundamental_price_momentum | 2026-09-22 | -12.39% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -12.41% |
| kf_quality v1 | kf_quality | 2026-09-24 | -12.41% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-09-29 | -12.42% |
| Lab e4785f: ((rank(price_above_sma50) > 0.424 or pct_off_52w | lab_search | 2026-09-24 | -12.43% |
| Lab c0a0df: (not((crosses_above(price_above_sma200, macd_sig | lab_search | 2026-09-24 | -12.46% |
| The Enduring Effect of Time-Series Momentum on Stock Returns | kf_momentum | 2026-09-25 | -12.46% |
| Momentum Volume hold=10 q=0.9 stop=3 | momentum_volume | 2026-09-24 | -12.47% |
| seasonality_12m v2 (longer_hold) | seasonality_12m | 2026-09-24 | -12.50% |
| Lab 08d0a4: ((rank(price_above_sma50) > 0.427 or pct_off_52w | lab_search | 2026-09-24 | -12.50% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-10-07 | -12.51% |
| 12 Month Cycle in Cross-Section of Stocks Returns · reproduc | kf_seasonality | 2026-09-25 | -12.52% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-09-25 | -12.52% |
| Lab 86f85e: ((rank(rsi_14) > 0.4743 and pct_off_52w_low > 0. | lab_search | 2026-09-24 | -12.53% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -12.56% |
| Crash Buyer 20d b | crash | 2026-09-04 | -12.56% |
| Macd Cross hold=20 stop=2 | macd_cross | 2026-09-24 | -12.57% |
| macd_cross v2 (longer_hold) | macd_cross | 2026-09-24 | -12.57% |
| Politician Buying buyers=1 hold=20 stop=3 | politician_buying | 2026-09-25 | -12.59% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -12.63% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -12.63% |
| Lab 37c34e: (not((crosses_above(price_above_sma200, macd_sig | lab_search | 2026-09-24 | -12.63% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-25 | -12.63% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -12.63% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -12.63% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -12.63% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -12.63% |
| Equity Returns at the Turn of the Month · reproduction | kf_seasonality | 2026-09-25 | -12.64% |
| Lab fda710: (roc_10 < -10.9569 and pct_change(stoch_k, 10) < | lab_search | 2026-09-24 | -12.65% |
| Lab a8935a: (roc_10 < -10.9569 or crosses_above(pct_change(m | lab_search | 2026-09-24 | -12.74% |
| The predictive power of investment and accruals · reproducti | kf_quality | 2026-10-08 | -12.76% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | -12.85% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | -12.85% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | -12.85% |
| Value and Size Effect: Now You See It, Now You Don’t · repro | kf_value | 2026-09-25 | -12.85% |
| Short-sellers, fundamental analysis and stock returns · repr | kf_fundamental | 2026-09-25 | -12.87% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.88% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -12.91% |
| st_momentum_1d v2 (longer_hold) | st_momentum_1d | 2026-09-24 | -12.95% |
| Lab 308218: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -13.00% |
| January Effect in Stocks · reproduction · exit 3.0 | kf_seasonality | 2026-09-25 | -13.00% |
| Low Accruals hold=40 q=0.1 stop=3 | low_accruals | 2026-09-24 | -13.01% |
| Low Accruals hold=60 q=0.1 stop=3 | low_accruals | 2026-09-24 | -13.01% |
| Quality Roa hold=40 q=0.9 stop=3 | quality_roa | 2026-09-24 | -13.06% |
| Quality Roa hold=60 q=0.9 stop=3 | quality_roa | 2026-09-24 | -13.06% |
| Lab f99ecd: pct_change(sma_200, 3) > 0.0266 | lab_search | 2026-09-24 | -13.12% |
| Lab 7eb6cd: ((rank(rsi_14) > 0.7 or pct_off_52w_low > 0.5) a | lab_search | 2026-09-24 | -13.13% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -13.15% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-10-07 | -13.17% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -13.20% |
| Short term reversal in stocks · reproduction | kf_reversal | 2026-09-25 | -13.21% |
| Lab 775598: pct_change(sma_200, 3) > 0.0232 | lab_search | 2026-09-24 | -13.22% |
| St Momentum 1D hold=1 q=0.95 stop=2 | st_momentum_1d | 2026-09-24 | -13.24% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -13.25% |
| Crash Buyer 20d a | crash | 2026-09-04 | -13.25% |
| An Anatomy of Calendar Effects · reproduction | kf_seasonality | 2026-09-25 | -13.26% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -13.28% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -13.29% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -13.34% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -13.34% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -13.34% |
| Momentum in Mutual Fund Returns · reproduction · stop 1.0 | kf_momentum | 2026-09-25 | -13.34% |
| Volatility Contraction hold=10 stop=2 zc=-1.5 | volatility_contraction | 2026-09-24 | -13.34% |
| kf_quality v1 | kf_quality | 2026-09-24 | -13.35% |
| Optimal trading with a trailing stop · reproduction · stop 1 | kf_other | 2026-09-25 | -13.38% |
| January Effect in Stocks · reproduction · stop 1.0 | kf_seasonality | 2026-09-25 | -13.39% |
| Stock Price Anchoring · reproduction · exit 3.0 | kf_reversal | 2026-09-30 | -13.42% |
| Stock Price Anchoring · reproduction · holding_period 0.5 | kf_reversal | 2026-09-30 | -13.42% |
| Stock Price Anchoring · reproduction · universe liquid | kf_reversal | 2026-09-30 | -13.42% |
| Value and Size Puzzles: A Commented Survey · reproduction | kf_value | 2026-09-25 | -13.43% |
| Lab c887db: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -13.46% |
| kf_hybrid v1 | kf_hybrid | 2026-09-24 | -13.47% |
| mean_reversion_to_sma · reproduction · stop -1.0 | kf_mean_reversion | 2026-10-05 | -13.50% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-10-07 | -13.62% |
| Knowledge is Power: A Field Experiment in the Chinese and US | kf_fundamental | 2026-10-07 | -13.62% |
| st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | 2026-09-24 | -13.62% |
| Lab b219ef: pct_change(sma_200, 3) > 0.0257 | lab_search | 2026-09-24 | -13.66% |
| Skewness, Individual Investor Preference, and the Cross-Sect | kf_reversal | 2026-10-13 | -13.68% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -13.71% |
| Xs Momentum hold=10 q=0.9 stop=3 | xs_momentum | 2026-09-24 | -13.72% |
| Lab 835874: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -13.80% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -13.82% |
| st_reversal_1d v2 (longer_hold) | st_reversal_1d | 2026-09-24 | -13.86% |
| kf_fundamental v1 | kf_fundamental | 2026-09-24 | -13.86% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -13.89% |
| Lab 7e5397: pct_change(sma_200, 3) > 0.0221 | lab_search | 2026-09-24 | -13.89% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -14.00% |
| Lab d56cb8: not((not(cci_20 < 154.905) or pct_change(sma_200 | lab_search | 2026-09-24 | -14.05% |
| Lab 988e3c: (pct_change(sma_200, 20) < -0.1277 or crosses_ab | lab_search | 2026-09-24 | -14.05% |
| st_reversal_5d v2 (longer_hold) | st_reversal_5d | 2026-09-24 | -14.05% |
| st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | 2026-09-24 | -14.13% |
| kf_size v3 (trend_filter) | kf_size | 2026-10-15 | -14.17% |
| st_stoch_oversold v2 | st_stoch_oversold | 2026-09-24 | -14.18% |
| Profitability hold=40 q=0.8 stop=3 | profitability | 2026-09-24 | -14.20% |
| Profitability hold=60 q=0.8 stop=3 | profitability | 2026-09-24 | -14.20% |
| st_volume_shock v3 (trend_filter) | st_volume_shock | 2026-09-24 | -14.36% |
| January Effect in Stocks · reproduction · holding_period 0.5 | kf_seasonality | 2026-09-25 | -14.39% |
| Decomposing the accrual premium: The evidence from two marke | kf_quality | 2026-10-07 | -14.40% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -14.43% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -14.43% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -14.43% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -14.57% |
| Lab e1963e: ((rank(log_dollar_volume) > 0.7 and price_above_ | lab_search | 2026-09-24 | -14.59% |
| Stock Price Anchoring · reproduction · stop 1.0 | kf_reversal | 2026-09-30 | -14.63% |
| st_volume_shock v3 (trend_filter) | st_volume_shock | 2026-09-24 | -14.69% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -14.70% |
| Decomposing Momentum Spread · reproduction · stop -1.0 | kf_momentum | 2026-10-13 | -14.73% |
| St Volume Shock hold=1 stop=2.5 | st_volume_shock | 2026-09-24 | -14.76% |
| Connecting book rate of return to risk and return: the infor | kf_value | 2026-09-25 | -14.83% |
| BREAKING INTO THE BLACKBOX: Trend Following, Stop Losses, an | kf_trend | 2026-09-25 | -14.87% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-09-25 | -14.87% |
| Turn of the Month in Equity Indexes · reproduction | kf_seasonality | 2026-09-25 | -14.87% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -14.91% |
| Small Cap q=0.2 | small_cap | 2026-09-24 | -14.94% |
| kf_low_volatility v2 (longer_hold) | kf_low_volatility | 2026-09-29 | -14.94% |
| st_reversal_1d v3 (trend_filter) | st_reversal_1d | 2026-09-25 | -14.96% |
| st_reversal_1d v2 (longer_hold) | st_reversal_1d | 2026-09-24 | -14.99% |
| Turn of the month in equity indexes · reproduction | kf_seasonality | 2026-09-25 | -15.06% |
| Lab 8f1143: pct_change(sma_200, 3) > 0.0216 | lab_search | 2026-09-24 | -15.07% |
| kf_trend v2 (longer_hold) | kf_trend | 2026-10-12 | -15.16% |
| st_reversal_1d v2 (longer_hold) | st_reversal_1d | 2026-09-24 | -15.16% |
| Liquidity Effect in Stocks · reproduction | kf_liquidity | 2026-09-25 | -15.19% |
| kf_liquidity v2 (longer_hold) | kf_liquidity | 2026-09-25 | -15.19% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -15.29% |
| momentum_12_1 v2 (longer_hold) | momentum_12_1 | 2026-09-24 | -15.45% |
| Short-Term Reversal Strategy in Stocks · reproduction | kf_reversal | 2026-09-25 | -15.45% |
| kf_factor v2 (longer_hold) | kf_factor | 2026-09-25 | -15.47% |
| Optimal Trend-Following in a Markov Switching Model · reprod | kf_trend | 2026-10-02 | -15.51% |
| Lab b7fcb0: (roc_10 < -10.9569 and pct_change(macd, 10) < ra | lab_search | 2026-09-24 | -15.64% |
| st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | 2026-09-24 | -15.64% |
| mean_reversion_to_sma · reproduction · exit 3.0 | kf_mean_reversion | 2026-10-05 | -15.67% |
| mean_reversion_to_sma · reproduction · universe liquid | kf_mean_reversion | 2026-10-05 | -15.67% |
| value_quality_momentum v1 | value_quality_momentum | 2026-09-22 | -15.69% |
| Optimal trading with a trailing stop · reproduction · holdin | kf_other | 2026-09-25 | -15.76% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -15.86% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -15.86% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -15.86% |
| st_reversal_1d v3 (trend_filter) | st_reversal_1d | 2026-09-25 | -15.86% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -15.87% |
| Lab 87d69e: (pct_change(sma_200, 20) < -0.1277 or sma_50 < p | lab_search | 2026-09-24 | -15.93% |
| Lab 5c6786: (not(not(chaikin_osc < -2.07956e+06)) and (cross | lab_search | 2026-09-24 | -15.98% |
| Momentum Effect in REITs · reproduction | kf_momentum | 2026-09-25 | -15.99% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-09-25 | -15.99% |
| ROA Effect within Stocks · reproduction | kf_quality | 2026-09-25 | -16.03% |
| kf_fundamental v1 | kf_fundamental | 2026-09-24 | -16.04% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-10-01 | -16.18% |
| Can Book-to-Market, Size and Momentum Be Risk Factors That P | kf_factor | 2026-09-25 | -16.21% |
| Momentum 12 1 q=0.8 stop=3 | momentum_12_1 | 2026-09-24 | -16.27% |
| Decomposing Momentum Spread · reproduction · universe large_ | kf_momentum | 2026-10-13 | -16.29% |
| mean_reversion_to_sma · reproduction · holding_period 2.0 | kf_mean_reversion | 2026-10-05 | -16.33% |
| A Structural Model of Short-term Reversals · reproduction | kf_reversal | 2026-09-25 | -16.36% |
| st_reversal_5d v2 (longer_hold) | st_reversal_5d | 2026-09-24 | -16.36% |
| St Reversal 5D hold=3 q=0.1 stop=2.5 | st_reversal_5d | 2026-09-24 | -16.39% |
| st_momentum_1d v3 (trend_filter) | st_momentum_1d | 2026-09-24 | -16.45% |
| Decomposing Momentum Spread · reproduction · exit 3.0 | kf_momentum | 2026-10-13 | -16.45% |
| Decomposing Momentum Spread · reproduction · holding_period  | kf_momentum | 2026-10-13 | -16.45% |
| Decomposing Momentum Spread · reproduction · holding_period  | kf_momentum | 2026-10-13 | -16.45% |
| Decomposing Momentum Spread · reproduction · universe liquid | kf_momentum | 2026-10-13 | -16.45% |
| kf_fundamental v1 | kf_fundamental | 2026-09-24 | -16.46% |
| St Reversal 5D hold=5 q=0.05 stop=2.5 | st_reversal_5d | 2026-09-24 | -16.55% |
| Lab 2cf2b9: ((rank(rsi_14) > 0.4238 and drawdown_200 > 0.326 | lab_search | 2026-09-24 | -16.58% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -16.58% |
| Predicting Stock Returns Using Industry-Relative Firm Charac | kf_momentum | 2026-10-08 | -16.59% |
| Household wealth and portfolio choice when tail events are s | kf_regime | 2026-09-25 | -16.59% |
| kf_regime v2 (longer_hold) | kf_regime | 2026-09-25 | -16.59% |
| Momentum in Mutual Fund Returns · reproduction · lookback 1. | kf_momentum | 2026-09-25 | -16.62% |
| st_uptrend_pullback v3 (trend_filter) | st_uptrend_pullback | 2026-09-25 | -16.64% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -16.65% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-08 | -16.70% |
| Acceleration Strategies · reproduction | kf_momentum | 2026-09-25 | -16.79% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -16.83% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -16.83% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-10-26 | -16.84% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-09-28 | -16.94% |
| momentum_12_1 v2 (longer_hold) | momentum_12_1 | 2026-09-24 | -16.96% |
| Momentum 12 1 q=0.8 stop=4 | momentum_12_1 | 2026-09-24 | -16.99% |
| st_reversal_5d v2 (longer_hold) | st_reversal_5d | 2026-09-24 | -16.99% |
| Stock Price Anchoring · reproduction · stop -1.0 | kf_reversal | 2026-09-30 | -17.00% |
| seasonality_12m v2 (longer_hold) | seasonality_12m | 2026-09-24 | -17.00% |
| Firm’s Cash Holdings and the Cross–Section of · reproduction | kf_fundamental | 2026-09-25 | -17.03% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -17.04% |
| St Uptrend Pullback hold=5 q=0.1 stop=2.5 | st_uptrend_pullback | 2026-09-24 | -17.04% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-09-25 | -17.04% |
| Abnormal Returns with Momentum/Contrarian Strategies Using E | kf_reversal | 2026-09-28 | -17.13% |
| Lab 5ae059: not((not(cci_20 < 179.864) or pct_change(sma_200 | lab_search | 2026-09-24 | -17.17% |
| Quality Minus Junk · reproduction | kf_quality | 2026-09-25 | -17.27% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-14 | -17.34% |
| Stock Price Anchoring · reproduction | kf_reversal | 2026-09-25 | -17.35% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-10-01 | -17.45% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-10-01 | -17.45% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-10-01 | -17.45% |
| Lab b6250d: (not(not(chaikin_osc < -2.07956e+06)) and (cross | lab_search | 2026-09-24 | -17.47% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -17.62% |
| Profitability Anomaly and Aggregate Volatility Risk · reprod | kf_quality | 2026-09-25 | -17.72% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -17.82% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-10-01 | -17.82% |
| Rising 50 | momentum | 2026-09-04 | -17.82% |
| kf_seasonality v1 | kf_seasonality | 2026-09-24 | -17.89% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-07 | -17.90% |
| Stock Selection Strategy Based on Fundamental Factors · repr | kf_fundamental | 2026-09-25 | -17.99% |
| Does Probability Weighting Drive Skewness Preferences? · rep | kf_reversal | 2026-10-12 | -18.00% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-09-29 | -18.09% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -18.09% |
| What makes investors overreact in the short-run? · reproduct | kf_reversal | 2026-10-14 | -18.14% |
| Lab 2309cc: ((rank(pct_off_52w_low) > 0.7 and price_above_sm | lab_search | 2026-09-24 | -18.15% |
| Seasonality 12M q=0.9 stop=3 | seasonality_12m | 2026-09-24 | -18.21% |
| Decomposing Momentum Spread · reproduction · lookback 1.5 | kf_momentum | 2026-10-13 | -18.25% |
| Leverage for the Long Run: A Systematic Approach to Managing | kf_trend | 2026-10-01 | -18.26% |
| st_reversal_5d v2 (longer_hold) | st_reversal_5d | 2026-09-24 | -18.40% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-09-25 | -18.43% |
| St Reversal 1D hold=1 q=0.1 stop=2 | st_reversal_1d | 2026-09-24 | -18.51% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-09-25 | -18.52% |
| Lab 50237e: pct_change(sma_200, 3) > 0.0199 | lab_search | 2026-09-24 | -18.58% |
| St Reversal 1D hold=1 q=0.05 stop=2 | st_reversal_1d | 2026-09-24 | -18.61% |
| Capm Alpha q=0.8 | capm_alpha | 2026-09-24 | -18.71% |
| Capm Alpha q=0.8 | capm_alpha | 2026-09-24 | -18.71% |
| St Uptrend Pullback hold=3 q=0.1 stop=2.5 | st_uptrend_pullback | 2026-09-24 | -18.74% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-13 | -18.75% |
| kf_reversal v2 (longer_hold) | kf_reversal | 2026-10-09 | -18.76% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-25 | -18.88% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -18.89% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -18.89% |
| Lab b71720: not((rank(bb_pct) > 0.805 or (crosses_below(cci_ | lab_search | 2026-09-24 | -18.93% |
| Crash Buyer 20d c | crash | 2026-09-04 | -19.07% |
| Lab 5ec095: not((not(cci_20 < 179.864) or pct_change(sma_200 | lab_search | 2026-09-24 | -19.18% |
| Lab 2d1483: (((close < 11.2649 and chaikin_osc < -955749) an | lab_search | 2026-09-24 | -19.25% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -19.39% |
| Sector momentum rotational system · reproduction | kf_momentum | 2026-09-25 | -19.41% |
| Decomposing Momentum Spread · reproduction · stop 1.0 | kf_momentum | 2026-10-13 | -19.41% |
| Reversal of 3-Day Losers and Continuation of 3-Day Winners o | kf_reversal | 2026-09-25 | -19.49% |
| Seasonality 12M q=0.9 stop=4 | seasonality_12m | 2026-09-24 | -19.66% |
| st_reversal_5d v3 (trend_filter) | st_reversal_5d | 2026-09-25 | -19.68% |
| Seasonality 12M q=0.95 stop=3 | seasonality_12m | 2026-09-24 | -19.83% |
| Combining Momentum Effect with Volume · reproduction | kf_momentum | 2026-09-25 | -19.87% |
| momentum_9_1 v1 | momentum_9_1 | 2026-09-24 | -19.90% |
| Size and Momentum Profitability in International Stock Marke | kf_momentum | 2026-09-25 | -19.90% |
| Asset Class Momentum · reproduction | kf_momentum | 2026-09-25 | -19.91% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-06 | -19.94% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -19.94% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-10-07 | -19.97% |
| St Uptrend Pullback hold=3 q=0.05 stop=2.5 | st_uptrend_pullback | 2026-09-24 | -20.00% |
| momentum_12_1 v2 (longer_hold) | momentum_12_1 | 2026-09-24 | -20.01% |
| momentum_12_1 v2 (longer_hold) | momentum_12_1 | 2026-09-24 | -20.06% |
| st_reversal_1d v3 (trend_filter) | st_reversal_1d | 2026-09-25 | -20.32% |
| seasonality_12m v2 (longer_hold) | seasonality_12m | 2026-09-24 | -20.32% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-12 | -20.45% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-25 | -20.64% |
| St Reversal 1D hold=3 q=0.1 stop=2 | st_reversal_1d | 2026-09-24 | -20.72% |
| st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | 2026-09-24 | -20.76% |
| Lab f58102: pct_change(sma_200, 3) > 0.0266 | lab_search | 2026-09-24 | -20.81% |
| Dissecting Anomalies · reproduction · stop 1.0 | kf_factor | 2026-09-29 | -20.90% |
| momentum_9_1 v1 | momentum_9_1 | 2026-09-24 | -20.92% |
| cross_sectional_momentum · reproduction | kf_momentum | 2026-09-25 | -20.93% |
| value_quality v1 | value_quality | 2026-09-22 | -20.94% |
| kf_size v2 (longer_hold) | kf_size | 2026-09-25 | -21.11% |
| Contraction Options: Implications for the Profitability-Retu | kf_momentum | 2026-09-25 | -21.12% |
| st_reversal_1d v3 (trend_filter) | st_reversal_1d | 2026-09-25 | -21.17% |
| Hot Potatoes: Underpricing of Stocks following Extreme Negat | kf_reversal | 2026-09-25 | -21.21% |
| St Reversal 5D hold=2 q=0.1 stop=2.5 | st_reversal_5d | 2026-09-24 | -21.32% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -21.34% |
| XGBoost Classifier | model | 2026-09-04 | -21.50% |
| seasonality_12m v2 (longer_hold) | seasonality_12m | 2026-09-24 | -21.50% |
| Ts Momentum hold=20 slope=0.02 stop=4 | ts_momentum | 2026-09-24 | -21.73% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -21.81% |
| Consistent momentum strategy · reproduction · stop -1.0 | kf_momentum | 2026-09-25 | -21.88% |
| kf_size v1 | kf_size | 2026-09-24 | -22.00% |
| growth_valuation v1 | growth_valuation | 2026-09-22 | -22.08% |
| growth_valuation v1 | growth_valuation | 2026-09-22 | -22.08% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -22.23% |
| Consistent momentum strategy · reproduction · exit 3.0 | kf_momentum | 2026-09-25 | -22.29% |
| Consistent momentum strategy · reproduction · holding_period | kf_momentum | 2026-09-25 | -22.29% |
| Consistent momentum strategy · reproduction · holding_period | kf_momentum | 2026-09-25 | -22.29% |
| Consistent momentum strategy · reproduction · universe liqui | kf_momentum | 2026-09-25 | -22.29% |
| Seasonality 12M q=0.95 stop=4 | seasonality_12m | 2026-09-24 | -22.31% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -22.37% |
| Lab 19d6fe: (pct_change(sma_200, 20) < -0.1941 or crosses_ab | lab_search | 2026-09-24 | -22.38% |
| Consistent momentum strategy · reproduction · universe large | kf_momentum | 2026-09-25 | -22.59% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -22.73% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -22.73% |
| Frog in the Pan: Continuous Information and Momentum · repro | kf_momentum | 2026-09-25 | -22.74% |
| Momentum factor effect in stocks · reproduction | kf_momentum | 2026-09-25 | -22.77% |
| Persistency of the Momentum Effect · reproduction | kf_momentum | 2026-09-25 | -22.79% |
| Dissecting Anomalies · reproduction · lookback 0.5 | kf_factor | 2026-09-29 | -22.82% |
| 12 month cycle in cross section of stocks returns · reproduc | kf_seasonality | 2026-09-25 | -22.83% |
| kf_seasonality v2 (longer_hold) | kf_seasonality | 2026-09-25 | -22.83% |
| st_uptrend_pullback v3 (trend_filter) | st_uptrend_pullback | 2026-09-25 | -22.87% |
| Lab 7347e3: (pct_change(sma_200, 10) < -0.0594 or sma_50 < p | lab_search | 2026-09-24 | -23.09% |
| Dissecting Anomalies · reproduction · holding_period 0.5 | kf_factor | 2026-09-29 | -23.22% |
| Ts Momentum hold=40 slope=0.02 stop=4 | ts_momentum | 2026-09-24 | -23.25% |
| St Reversal 5D hold=2 q=0.05 stop=2.5 | st_reversal_5d | 2026-09-24 | -23.26% |
| Momentum 12 1 q=0.9 stop=3 | momentum_12_1 | 2026-09-24 | -23.38% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-09 | -23.43% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-09 | -23.43% |
| Decomposing Momentum Spread · reproduction | kf_momentum | 2026-09-25 | -23.45% |
| Return-based Investment Strategies in the New Zealand Stock  | kf_momentum | 2026-09-25 | -23.45% |
| The Global Relation Between Financial Distress and Equity Re | kf_factor | 2026-09-25 | -23.46% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-06 | -23.48% |
| Consistent momentum strategy · reproduction · stop 1.0 | kf_momentum | 2026-09-25 | -23.49% |
| International Momentum Strategies · reproduction | kf_momentum | 2026-09-25 | -23.53% |
| Momentum Effect in Stocks in Small Portfolios · reproduction | kf_momentum | 2026-09-25 | -23.53% |
| Momentum · reproduction | kf_momentum | 2026-09-25 | -23.53% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-09-25 | -23.53% |
| Momentum 12 1 q=0.9 stop=4 | momentum_12_1 | 2026-09-24 | -23.74% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -24.17% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -24.17% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -24.17% |
| St Reversal 1D hold=2 q=0.1 stop=2 | st_reversal_1d | 2026-09-24 | -24.21% |
| st_reversal_1d v2 (longer_hold) | st_reversal_1d | 2026-09-24 | -24.21% |
| Ts Momentum hold=40 slope=0.01 stop=2.5 | ts_momentum | 2026-09-24 | -24.41% |
| Dissecting Anomalies · reproduction · universe large_cap | kf_factor | 2026-09-29 | -24.41% |
| Predicting Equity Returns in Emerging Markets · reproduction | kf_momentum | 2026-09-25 | -24.45% |
| st_reversal_1d v3 (trend_filter) | st_reversal_1d | 2026-09-25 | -24.52% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-14 | -24.53% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-09-28 | -24.54% |
| Ts Momentum hold=20 slope=0.02 stop=2.5 | ts_momentum | 2026-09-24 | -24.64% |
| St Uptrend Pullback hold=5 q=0.05 stop=2.5 | st_uptrend_pullback | 2026-09-24 | -24.65% |
| momentum_9_1 v1 | momentum_9_1 | 2026-09-24 | -24.69% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -24.71% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -24.71% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -24.71% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -24.71% |
| Ts Momentum hold=40 slope=0.01 stop=4 | ts_momentum | 2026-09-24 | -24.78% |
| St Reversal 1D hold=3 q=0.05 stop=2 | st_reversal_1d | 2026-09-24 | -24.80% |
| Lab 3b4fb8: pct_change(sma_200, 3) > 0.0221 | lab_search | 2026-09-24 | -24.83% |
| What's the Best Way to Trade Using the January Barometer? ·  | kf_seasonality | 2026-09-30 | -24.92% |
| Ts Momentum hold=40 slope=0.02 stop=2.5 | ts_momentum | 2026-09-24 | -24.96% |
| ts_momentum v2 (longer_hold) | ts_momentum | 2026-09-24 | -24.96% |
| The Role of Beta and Size in the Cross-Section of European S | kf_size | 2026-09-25 | -25.05% |
| Lab 3782ba: (pct_change(sma_200, 10) < -0.1774 or sma_50 < p | lab_search | 2026-09-24 | -25.05% |
| Lab d10765: not((not(cci_20 < 179.864) or pct_change(sma_200 | lab_search | 2026-09-24 | -25.09% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-07 | -25.31% |
| Consistent momentum strategy · reproduction · lookback 1.5 | kf_momentum | 2026-09-25 | -25.35% |
| momentum_9_1 v1 | momentum_9_1 | 2026-09-24 | -25.39% |
| kf_momentum v2 (longer_hold) | kf_momentum | 2026-10-12 | -25.40% |
| St Reversal 1D hold=2 q=0.05 stop=2 | st_reversal_1d | 2026-09-24 | -25.43% |
| st_reversal_1d v2 (longer_hold) | st_reversal_1d | 2026-09-24 | -25.43% |
| Momentum and Style Rotation Effect · reproduction | kf_momentum | 2026-09-25 | -25.60% |
| Lab de24f6: pct_change(sma_200, 3) > 0.0221 | lab_search | 2026-09-24 | -25.66% |
| Decile-Based Quantitative Portfolio Strategies from SEC Fund | kf_hybrid | 2026-09-30 | -25.72% |
| Dissecting Anomalies · reproduction · exit 3.0 | kf_factor | 2026-09-29 | -25.73% |
| Dissecting Anomalies · reproduction · universe liquid | kf_factor | 2026-09-29 | -25.73% |
| Momentum is Really Short-term Momentum · reproduction | kf_momentum | 2026-09-25 | -25.83% |
| Lab 4d6645: pct_change(sma_200, 3) > 0.0199 | lab_search | 2026-09-24 | -26.07% |
| Momentum Effect in Stocks · reproduction | kf_momentum | 2026-09-25 | -26.09% |
| Lab f7613f: pct_change(sma_200, 3) > 0.0257 | lab_search | 2026-09-24 | -26.14% |
| Dissecting Anomalies · reproduction · stop -1.0 | kf_factor | 2026-09-29 | -26.30% |
| Dissecting Anomalies · reproduction · holding_period 2.0 | kf_factor | 2026-09-29 | -26.38% |
| Taming Momentum Crashes: A Simple Stop-Loss Strategy · repro | kf_momentum | 2026-09-25 | -26.49% |
| Lab da7e5b: pct_change(sma_200, 3) > 0.0234 | lab_search | 2026-09-24 | -26.67% |
| Cross-Sectional and Time-Series Momentum Returns and Market  | kf_momentum | 2026-09-25 | -27.11% |
| St Uptrend Pullback hold=2 q=0.1 stop=2.5 | st_uptrend_pullback | 2026-09-24 | -27.18% |
| Asymmetric Momentum Effects Under Uncertainty · reproduction | kf_momentum | 2026-09-25 | -27.31% |
| Can exchange traded funds be used to exploit  country and in | kf_momentum | 2026-09-25 | -27.31% |
| Cross-Sectional and Time-Series Momentum Returns: Are Islami | kf_momentum | 2026-09-25 | -27.31% |
| Momentum factor and style rotation effect · reproduction | kf_momentum | 2026-09-25 | -27.31% |
| The Seasonality of Momentum: Analysis of Tradability · repro | kf_seasonality | 2026-09-25 | -27.31% |
| Two Centuries of Price Return Momentum · reproduction | kf_momentum | 2026-09-25 | -27.31% |
| kf_momentum v1 | kf_momentum | 2026-09-24 | -27.58% |
| st_uptrend_pullback v3 (trend_filter) | st_uptrend_pullback | 2026-09-25 | -27.81% |
| Dissecting Anomalies · reproduction | kf_factor | 2026-09-25 | -28.08% |
| Lab 48a282: (pct_change(sma_200, 10) < -0.0964 or crosses_ab | lab_search | 2026-09-24 | -28.31% |
| Maximizing Momentum with Double-Sorting · reproduction | kf_momentum | 2026-09-25 | -28.56% |
| St Uptrend Pullback hold=2 q=0.05 stop=2.5 | st_uptrend_pullback | 2026-09-24 | -29.64% |
| ts_momentum v1 | ts_momentum | 2026-09-23 | -29.93% |
| st_reversal_5d v3 (trend_filter) | st_reversal_5d | 2026-09-25 | -30.31% |
| Lab 9f4f01: (((close < 7.229 and chaikin_osc < -955749) and  | lab_search | 2026-09-24 | -30.43% |
| Crash Buyer 10d | crash | 2026-09-04 | -30.45% |
| Lab 2ac5ef: (pct_change(sma_200, 10) < -0.0693 or crosses_ab | lab_search | 2026-09-24 | -30.54% |
| Lab fbb335: (pct_change(sma_200, 10) < -0.07 or crosses_abov | lab_search | 2026-09-24 | -30.54% |
| Lab 8f544b: (pct_change(sma_200, 20) < -0.1164 or crosses_ab | lab_search | 2026-09-24 | -32.47% |
| Lab 72cb92: (pct_change(sma_200, 20) < -0.1271 or crosses_be | lab_search | 2026-09-24 | -33.15% |
| ts_momentum v1 | ts_momentum | 2026-09-23 | -35.91% |
| Crash Buyer 5d | crash | 2026-09-04 | -43.68% |
| Lab adf2bc: (pct_change(sma_200, 20) < -0.2732 or crosses_ab | lab_search | 2026-09-24 | -47.25% |

**Stalled and excluded from the count** (last marked 2026-11-09, others 2026-11-11): Deep Value screen, Quality Value screen

832 of 2923 are up. **These records are days old, not years.**
A fourteen-day return is not evidence of an edge; it is the beginning of
the only measurement here with no survivorship bias and no look-ahead.

## Which apparent findings were invalidated, and why

| Finding | Why it was withdrawn |
|---|---|
| 97.9% win rate over 47 trades | shuffled train/test split over time-ordered rows |
| 66 validation survivors | market-wide null paid them for buying cheap stocks |
| 71% of Lab profit | tradeability floors were pricing exits, not just entries |
| +0.43%/trade classifier edge | close fills; gross is negative at next-open |
| momentum+pullback convergence | 231 of 455 survivors inherited a seed's constant |
| 4 searches' worth of results | each found its answer in the scoreboard, not the market |

## What evidence would be required to promote a strategy

Not yet formalised — Phase 7 defines the promotion policy. On the
evidence above, the minimum would have to include:

1. A pre-registered hypothesis, locked before the test ran.
2. Classification as INDEPENDENT by `ancestry.py` — not seed-descended.
3. Performance clearing the noise bar of ~5.3 SE, not merely positive.
4. Forward months, not days, with the strategy frozen on entry.
5. A matched-universe null, not SPY alone.
6. Costs charged inside the measurement.
7. Survivorship exposure stated for the period tested.

**No strategy in this system currently meets any of these except the last.**