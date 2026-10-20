# Earnings skip and stop widths — 2026-10-20 (Stage AD3.5 / AD3.6)

23 of 23 strategies computed. Backtest window, real plus synthetic dead companies (as_is), next-open fills, net of costs. Research only: nothing live changes from this.

## earnings_skip_v1: skip entries within 5 sessions of a report — **FAIL**

Strategies with >= 30 removed trades: 9. Conditions: a no · b no · c no · d yes.

Mean Sharpe change +0.0005; removed trades +2.526% vs kept +1.982% per trade; by year: 2016 -0.0115, 2017 +0.0048, 2018 -0.0015, 2019 +0.0051

| strategy | covered | skip3 removed / dSharpe | skip5 removed / dSharpe | skip10 removed / dSharpe | pred5 removed / dSharpe |
|---|---:|---:|---:|---:|---:|
| fx_momentum_9_1_6be9694eef@v1 | 1726 | 88 / -0.0059 | 155 / -0.0030 | 302 / -0.0021 | 101 / +0.0047 |
| fx_debt_reduction_4359570578@v1 | 2774 | 119 / +0.0019 | 195 / -0.0014 | 403 / -0.0025 | 141 / +0.0001 |
| fx_debt_reduction_a2ac40f426@v1 | 2774 | 119 / +0.0015 | 195 / -0.0035 | 403 / -0.0070 | 141 / -0.0047 |
| fx_fcf_to_price_1f0e73d4f1@v1 | 2407 | 126 / -0.0054 | 208 / -0.0038 | 431 / +0.0050 | 117 / +0.0006 |
| fx_fcf_to_price_aedd20cf42@v1 | 2490 | 140 / -0.0017 | 228 / -0.0016 | 459 / +0.0048 | 133 / +0.0049 |
| fx_fcf_to_price_ca1145fb34@v1 | 2490 | 140 / +0.0031 | 228 / +0.0048 | 459 / +0.0151 | 133 / +0.0089 |
| fx_kf_factor_fbe86e6e56@v1 | 1942 | 94 / +0.0060 | 156 / +0.0154 | 310 / +0.0415 | 118 / +0.0124 |
| fx_kf_fundamental_83270aca06@v1 | 237 | 20 / -0.0161 | 33 / -0.0293 | 61 / -0.1065 | 13 / -0.0070 |
| fx_kf_quality_511bbd4369@v1 | 409 | 21 / +0.0201 | 35 / +0.0271 | 71 / +0.0454 | 20 / +0.0054 |
| fx_kf_quality_53c233da03@v1 | 121 | 6 / +0.0145 | 10 / +0.0270 | 22 / +0.0514 | 10 / +0.0270 |

## stop_width_slots_v1: ATR stop multiple

Cell = change in net return per trade against the strategy as it is (paired, date-clustered t); adoptable needs t >= 2.58 and a gain in most years.

| strategy | own stop | base/trade | 1.5x | 2.0x | 3.0x | 4.0x | 6.0x | adoptable |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| fx_momentum_9_1_6be9694eef@v1 | 4 | +0.889% | -0.387% (t -6.2) | -0.231% (t -5.0) | -0.045% (t -2.1) | — | +0.097% (t +5.2) | 6.0x |
| fx_debt_reduction_4359570578@v1 | 5 | +1.512% | -0.700% (t -6.9) | -0.568% (t -6.9) | -0.325% (t -6.1) | -0.144% (t -4.8) | +0.132% (t +5.4) | 6.0x |
| fx_debt_reduction_a2ac40f426@v1 | 5 | +2.163% | -1.082% (t -8.0) | -0.900% (t -7.9) | -0.545% (t -6.9) | -0.247% (t -5.4) | +0.230% (t +6.0) | 6.0x |
| fx_earnings_surprise_256905046a@v1 | 3 | +1.322% | -0.453% (t -4.4) | -0.221% (t -3.4) | — | +0.206% (t +3.6) | +0.367% (t +4.4) | 4.0x, 6.0x |
| fx_earnings_surprise_6c4be67022@v1 | 3 | +1.100% | -0.466% (t -5.7) | -0.232% (t -4.7) | — | +0.216% (t +5.0) | +0.440% (t +6.6) | 4.0x, 6.0x |
| fx_earnings_surprise_a3aaef9318@v1 | 3 | +1.389% | -0.396% (t -5.3) | -0.267% (t -5.4) | — | +0.213% (t +5.9) | +0.382% (t +6.9) | 4.0x, 6.0x |
| fx_earnings_surprise_a3b8ebfe6f@v1 | 3 | +1.436% | -0.677% (t -5.8) | -0.376% (t -4.8) | — | +0.245% (t +4.3) | +0.582% (t +5.9) | 4.0x, 6.0x |
| fx_earnings_surprise_bca872a46e@v1 | 3 | +1.495% | -0.663% (t -6.8) | -0.383% (t -6.1) | — | +0.281% (t +6.3) | +0.595% (t +7.2) | 4.0x, 6.0x |
| fx_earnings_surprise_ca5b972d65@v1 | 3 | +1.606% | -0.687% (t -5.0) | -0.403% (t -4.3) | — | +0.178% (t +2.5) | +0.427% (t +3.8) | 6.0x |
| fx_earnings_surprise_df32f2eb93@v2 | 3 | +1.495% | -0.663% (t -6.8) | -0.383% (t -6.1) | — | +0.281% (t +6.3) | +0.595% (t +7.2) | 4.0x, 6.0x |
| fx_earnings_surprise_e6229d3e21@v1 | 3 | +1.596% | -0.603% (t -6.1) | -0.411% (t -6.0) | — | +0.247% (t +5.0) | +0.493% (t +5.9) | 4.0x, 6.0x |
| fx_fcf_to_price_1f0e73d4f1@v1 | 5 | +1.569% | -0.862% (t -11.1) | -0.677% (t -10.6) | -0.381% (t -9.7) | -0.174% (t -7.5) | +0.121% (t +6.6) | 6.0x |
| fx_fcf_to_price_aedd20cf42@v1 | 5 | +1.735% | -0.872% (t -10.6) | -0.722% (t -10.3) | -0.417% (t -9.2) | -0.184% (t -7.0) | +0.103% (t +5.5) | 6.0x |
| fx_fcf_to_price_ca1145fb34@v1 | 5 | +2.135% | -1.087% (t -11.3) | -0.894% (t -10.8) | -0.534% (t -9.3) | -0.260% (t -7.8) | +0.166% (t +6.4) | 6.0x |
| fx_kf_earnings_surprise_40ad0c0c8e@v1 | 3 | +0.628% | -0.186% (t -4.2) | -0.104% (t -3.5) | — | +0.071% (t +3.4) | +0.083% (t +2.5) | 4.0x |
| fx_kf_earnings_surprise_4e1b6156d7@v1 | 3 | +0.691% | -0.215% (t -4.6) | -0.123% (t -4.0) | — | +0.072% (t +3.3) | +0.078% (t +2.3) | 4.0x |
| fx_kf_earnings_surprise_5daa1772d5@v1 | 3 | +0.656% | -0.214% (t -4.7) | -0.129% (t -4.2) | — | +0.052% (t +2.5) | +0.048% (t +1.4) | none |
| fx_kf_factor_fbe86e6e56@v1 | 3 | +0.553% | -0.400% (t -6.7) | -0.310% (t -7.1) | — | +0.145% (t +4.7) | +0.187% (t +4.8) | 6.0x |
| fx_kf_fundamental_83270aca06@v1 | 3 | +4.048% | -1.513% (t -6.6) | -0.964% (t -5.1) | — | +0.116% (t +1.0) | +0.190% (t +1.1) | none |
| fx_kf_hybrid_b7d7f1dcf3@v1 | 3 | +0.646% | -0.153% (t -3.3) | -0.076% (t -2.2) | — | +0.017% (t +0.7) | -0.016% (t -0.4) | none |
| fx_kf_momentum_55af4d55e8@v1 | 3 | +1.319% | -0.705% (t -5.9) | -0.468% (t -5.3) | — | +0.224% (t +3.0) | +0.513% (t +4.3) | none |
| fx_kf_quality_511bbd4369@v1 | 3 | +2.213% | -0.449% (t -7.6) | -0.225% (t -5.1) | — | +0.176% (t +4.6) | +0.352% (t +6.1) | 4.0x, 6.0x |
| fx_kf_quality_53c233da03@v1 | 3 | +2.335% | -0.614% (t -7.3) | -0.368% (t -5.6) | — | +0.140% (t +3.4) | +0.404% (t +6.5) | 4.0x, 6.0x |

Adoptable: fx_momentum_9_1_6be9694eef@v1: 6.0x; fx_debt_reduction_4359570578@v1: 6.0x; fx_debt_reduction_a2ac40f426@v1: 6.0x; fx_earnings_surprise_256905046a@v1: 4.0x, 6.0x; fx_earnings_surprise_6c4be67022@v1: 4.0x, 6.0x; fx_earnings_surprise_a3aaef9318@v1: 4.0x, 6.0x; fx_earnings_surprise_a3b8ebfe6f@v1: 4.0x, 6.0x; fx_earnings_surprise_bca872a46e@v1: 4.0x, 6.0x; fx_earnings_surprise_ca5b972d65@v1: 6.0x; fx_earnings_surprise_df32f2eb93@v2: 4.0x, 6.0x; fx_earnings_surprise_e6229d3e21@v1: 4.0x, 6.0x; fx_fcf_to_price_1f0e73d4f1@v1: 6.0x; fx_fcf_to_price_aedd20cf42@v1: 6.0x; fx_fcf_to_price_ca1145fb34@v1: 6.0x; fx_kf_earnings_surprise_40ad0c0c8e@v1: 4.0x; fx_kf_earnings_surprise_4e1b6156d7@v1: 4.0x; fx_kf_factor_fbe86e6e56@v1: 6.0x; fx_kf_quality_511bbd4369@v1: 4.0x, 6.0x; fx_kf_quality_53c233da03@v1: 4.0x, 6.0x

Caveats: one window (2016-2019) with synthetic dead companies; report dates exist for a minority of tickers, so the earnings test covers those ticker-years only; a stop change is a different strategy and would need its own paper record before any live use.

## Diagnostic beside the stop test (not part of it): per 20 sessions held

The registered metric is return per trade; a wider stop also holds longer, and 2016-2019 rose. Normalised per 20 sessions held, 6x still beats the strategy as it is for 20 of 23; holds lengthen modestly. What changes is the stop-out rate: today's stops close 15-48% of trades, 6x closes 4-21%.

| strategy | own stop | per trade | hold | per 20 sessions | stopped | 6x per trade | hold | per 20 sessions | stopped |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| fx_momentum_9_1_6be9694eef@v1 | 4 | +0.889% | 19.7 | +0.905% | 15% | +0.986% | 20.5 | +0.962% | 5% |
| fx_debt_reduction_4359570578@v1 | 5 | +1.512% | 36.5 | +0.829% | 19% | +1.644% | 37.7 | +0.872% | 13% |
| fx_debt_reduction_a2ac40f426@v1 | 5 | +2.163% | 51.8 | +0.836% | 27% | +2.393% | 54.2 | +0.882% | 21% |
| fx_earnings_surprise_256905046a@v1 | 3 | +1.322% | 34.6 | +0.764% | 28% | +1.689% | 38.8 | +0.870% | 7% |
| fx_earnings_surprise_6c4be67022@v1 | 3 | +1.100% | 34.3 | +0.642% | 29% | +1.540% | 38.8 | +0.794% | 7% |
| fx_earnings_surprise_a3aaef9318@v1 | 3 | +1.389% | 34.5 | +0.806% | 29% | +1.772% | 38.8 | +0.912% | 8% |
| fx_earnings_surprise_a3b8ebfe6f@v1 | 3 | +1.436% | 47.5 | +0.605% | 39% | +2.018% | 56.7 | +0.712% | 14% |
| fx_earnings_surprise_bca872a46e@v1 | 3 | +1.495% | 47.3 | +0.632% | 40% | +2.090% | 56.6 | +0.738% | 14% |
| fx_earnings_surprise_ca5b972d65@v1 | 3 | +1.606% | 48.0 | +0.669% | 38% | +2.034% | 56.8 | +0.717% | 14% |
| fx_earnings_surprise_df32f2eb93@v2 | 3 | +1.495% | 47.3 | +0.632% | 40% | +2.090% | 56.6 | +0.738% | 14% |
| fx_earnings_surprise_e6229d3e21@v1 | 3 | +1.596% | 47.7 | +0.669% | 39% | +2.089% | 56.7 | +0.737% | 15% |
| fx_fcf_to_price_1f0e73d4f1@v1 | 5 | +1.569% | 34.9 | +0.900% | 15% | +1.690% | 35.9 | +0.943% | 10% |
| fx_fcf_to_price_aedd20cf42@v1 | 5 | +1.735% | 35.0 | +0.991% | 16% | +1.839% | 36.0 | +1.022% | 11% |
| fx_fcf_to_price_ca1145fb34@v1 | 5 | +2.135% | 49.0 | +0.872% | 22% | +2.301% | 51.0 | +0.903% | 16% |
| fx_kf_earnings_surprise_40ad0c0c8e@v1 | 3 | +0.628% | 18.0 | +0.699% | 21% | +0.710% | 19.5 | +0.729% | 5% |
| fx_kf_earnings_surprise_4e1b6156d7@v1 | 3 | +0.691% | 19.0 | +0.729% | 22% | +0.769% | 20.6 | +0.745% | 5% |
| fx_kf_earnings_surprise_5daa1772d5@v1 | 3 | +0.656% | 18.9 | +0.694% | 22% | +0.704% | 20.6 | +0.682% | 5% |
| fx_kf_factor_fbe86e6e56@v1 | 3 | +0.553% | 18.7 | +0.590% | 23% | +0.739% | 20.6 | +0.717% | 5% |
| fx_kf_fundamental_83270aca06@v1 | 3 | +4.048% | 43.7 | +1.851% | 46% | +4.238% | 55.8 | +1.520% | 18% |
| fx_kf_hybrid_b7d7f1dcf3@v1 | 3 | +0.646% | 19.0 | +0.678% | 21% | +0.630% | 20.7 | +0.609% | 5% |
| fx_kf_momentum_55af4d55e8@v1 | 3 | +1.319% | 43.5 | +0.606% | 48% | +1.832% | 54.4 | +0.674% | 21% |
| fx_kf_quality_511bbd4369@v1 | 3 | +2.213% | 18.8 | +2.354% | 22% | +2.565% | 20.6 | +2.491% | 4% |
| fx_kf_quality_53c233da03@v1 | 3 | +2.335% | 18.8 | +2.481% | 22% | +2.739% | 20.7 | +2.650% | 4% |

Not decided here: a wider stop is a different strategy. Per the plan (AD6) it changes live only after its own paper record and the owner's decision; per-trade losses when wrong are larger (a 6x stop on a volatile name is close to no stop).
