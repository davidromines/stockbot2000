# Phase A4-A5: multiple testing and the enrollment event

Computed 2026-10-13 05:22 UTC, read-only, from `paper_trades_restated` (next-open fills, net of modelled costs) joined to `paper_runs` and SPY. 18,730 restated trades, 73 families; 6,288 trades (33.6%) are a retroactive replay (see A5).

## A4. What was looked at, and which count applies

| quantity | value | applies to |
|---|---:|---|
| Lab search trials (append-only counter) | 1,049,975 | backtest evidence of the Lab survivors |
| unique Lab structures | 126,652 | same, structural dedupe |
| effective Lab trials (project estimate, between the two) | 364,666 | same |
| factory / knowledge specs | 1,405 | backtest evidence of factory families |
| families defined | 88 | the pool the funnel draws its forward families from |
| families with >= 20 closed forward trades | 41 | the family-level forward comparison |

The forward window is a fresh sample for strategies fixed before it began, so a forward family-level claim is corrected for the number of families compared, not for the Lab's trial count. (An earlier note in this project said `lab_search`'s relevant luck level was the Lab's 4.4-4.9; that applies only if a best fund inside the family were picked after the fact.) Noise-only 95% t for the best of N independent tests: N=43: 3.04, N=88: 3.25, N=1405: 3.97.

### Effective number of independent family tests (absolute honest net return, prospective trades)

31 families, median pairwise correlation of per-date returns +0.12 over 193 pairs, Nyholt effective tests **28.3**. (Correlations rest on 5-19 shared dates: indicative.)

### Effective number of independent family tests (honest net return minus SPY over the same window, prospective trades)

31 families, median pairwise correlation of per-date returns -0.00 over 193 pairs, Nyholt effective tests **28.4**. (Correlations rest on 5-19 shared dates: indicative.)

### absolute honest net; all restated trades

| family | trades | independent dates | mean % | cluster t | df | p (one-sided) | Holm | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 7,941 | 10 | +0.90 | +2.2 | 9 | 0.028 | 0.744 | 0.744 |
| momentum | 392 | 18 | +1.71 | +1.4 | 17 | 0.095 | 1.000 | 1.000 |
| kf_seasonality | 624 | 8 | +0.11 | +0.3 | 7 | 0.396 | 1.000 | 1.000 |
| st_uptrend_pullback | 624 | 8 | +0.19 | +0.1 | 7 | 0.444 | 1.000 | 1.000 |
| bollinger_reversion | 370 | 5 | +0.45 | +0.9 | 4 | 0.216 | 1.000 | 1.000 |
| kf_mean_reversion | 123 | 7 | +1.71 | +1.3 | 6 | 0.128 | 1.000 | 1.000 |
| st_momentum_1d | 1,116 | 10 | -0.39 | -1.3 | 9 | 0.893 | 1.000 | 1.000 |
| turn_of_month | 160 | 2 | +1.86 | +1.9 | 1 | 0.152 | n/a | n/a |
| kf_reversal | 201 | 9 | +0.74 | +1.1 | 8 | 0.156 | 1.000 | 1.000 |
| st_bollinger_low | 280 | 8 | +0.06 | +0.2 | 7 | 0.433 | 1.000 | 1.000 |
| st_stoch_oversold | 496 | 6 | -0.08 | -0.3 | 5 | 0.601 | 1.000 | 1.000 |
| st_volume_shock | 564 | 10 | -0.45 | -0.8 | 9 | 0.789 | 1.000 | 1.000 |
| st_reversal_1d | 1,271 | 10 | -0.42 | -1.3 | 9 | 0.893 | 1.000 | 1.000 |
| relative_strength | 53 | 8 | -0.81 | -1.6 | 7 | 0.924 | 1.000 | 1.000 |

### excess over SPY; all restated trades

| family | trades | independent dates | mean % | cluster t | df | p (one-sided) | Holm | BH q |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 7,941 | 10 | +0.60 | +1.6 | 9 | 0.073 | 1.000 | 1.000 |
| momentum | 392 | 18 | +1.74 | +1.3 | 17 | 0.106 | 1.000 | 1.000 |
| kf_seasonality | 624 | 8 | -0.25 | -1.0 | 7 | 0.817 | 1.000 | 1.000 |
| st_uptrend_pullback | 624 | 8 | -0.20 | -0.3 | 7 | 0.613 | 1.000 | 1.000 |
| bollinger_reversion | 370 | 5 | -0.31 | -0.9 | 4 | 0.791 | 1.000 | 1.000 |
| kf_mean_reversion | 123 | 7 | +1.10 | +0.8 | 6 | 0.218 | 1.000 | 1.000 |
| st_momentum_1d | 1,116 | 10 | -0.61 | -2.1 | 9 | 0.965 | 1.000 | 1.000 |
| turn_of_month | 160 | 2 | +0.51 | +0.5 | 1 | 0.346 | n/a | n/a |
| kf_reversal | 201 | 9 | +0.05 | +0.1 | 8 | 0.472 | 1.000 | 1.000 |
| st_bollinger_low | 280 | 8 | -0.23 | -1.1 | 7 | 0.846 | 1.000 | 1.000 |
| st_volume_shock | 564 | 10 | -0.61 | -1.1 | 9 | 0.860 | 1.000 | 1.000 |
| st_stoch_oversold | 496 | 6 | -0.37 | -1.7 | 5 | 0.924 | 1.000 | 1.000 |
| kf_low_volatility | 31 | 4 | -6.26 | -2.1 | 3 | 0.935 | n/a | n/a |
| quality_momentum | 57 | 6 | -1.75 | -1.9 | 5 | 0.944 | 1.000 | 1.000 |

### absolute honest net; prospective trades only (retroactive replay removed)

| family | trades | independent dates | mean % | cluster t | df | p (one-sided) | Holm | BH q | max-T adj p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 5,055 | 9 | +0.48 | +1.0 | 8 | 0.163 | 1.000 | 1.000 | 1.000 |
| momentum | 321 | 17 | +0.70 | +0.7 | 16 | 0.251 | 1.000 | 1.000 | 0.996 |
| kf_seasonality | 604 | 8 | +0.03 | +0.1 | 7 | 0.473 | 1.000 | 1.000 | 1.000 |
| st_uptrend_pullback | 391 | 7 | -1.38 | -1.9 | 6 | 0.944 | 1.000 | 1.000 | 1.000 |
| bollinger_reversion | 130 | 4 | +1.30 | +2.0 | 3 | 0.067 | n/a | n/a | 0.149 |
| kf_mean_reversion | 120 | 6 | +1.85 | +1.4 | 5 | 0.109 | 1.000 | 1.000 | 0.943 |
| st_momentum_1d | 916 | 9 | -0.25 | -0.9 | 8 | 0.797 | 1.000 | 1.000 | 1.000 |
| turn_of_month | 160 | 2 | +1.86 | +1.9 | 1 | 0.152 | n/a | n/a | n/a |
| kf_reversal | 181 | 8 | +0.70 | +1.0 | 7 | 0.169 | 1.000 | 1.000 | 0.955 |
| st_stoch_oversold | 316 | 5 | +0.45 | +1.0 | 4 | 0.189 | 1.000 | 1.000 | 1.000 |
| st_bollinger_low | 160 | 7 | +0.24 | +0.5 | 6 | 0.307 | 1.000 | 1.000 | 1.000 |
| st_volume_shock | 420 | 9 | +0.26 | +0.4 | 8 | 0.366 | 1.000 | 1.000 | 1.000 |
| st_reversal_1d | 1,031 | 9 | +0.03 | +0.1 | 8 | 0.457 | 1.000 | 1.000 | 1.000 |
| quality_momentum | 24 | 5 | -0.08 | -0.1 | 4 | 0.531 | 1.000 | 1.000 | 1.000 |

### excess over SPY; prospective trades only (retroactive replay removed)

| family | trades | independent dates | mean % | cluster t | df | p (one-sided) | Holm | BH q | max-T adj p |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 5,055 | 9 | +0.19 | +0.5 | 8 | 0.321 | 1.000 | 1.000 | 1.000 |
| momentum | 321 | 17 | +0.56 | +0.6 | 16 | 0.287 | 1.000 | 1.000 | 0.989 |
| kf_seasonality | 604 | 8 | -0.31 | -1.3 | 7 | 0.882 | 1.000 | 1.000 | 1.000 |
| st_uptrend_pullback | 391 | 7 | -2.00 | -2.7 | 6 | 0.982 | 1.000 | 1.000 | 1.000 |
| bollinger_reversion | 130 | 4 | +0.41 | +0.8 | 3 | 0.234 | n/a | n/a | 0.622 |
| kf_mean_reversion | 120 | 6 | +1.25 | +1.0 | 5 | 0.186 | 1.000 | 1.000 | 0.980 |
| st_momentum_1d | 916 | 9 | -0.57 | -2.0 | 8 | 0.960 | 1.000 | 1.000 | 1.000 |
| turn_of_month | 160 | 2 | +0.51 | +0.5 | 1 | 0.346 | n/a | n/a | n/a |
| st_volume_shock | 420 | 9 | -0.03 | -0.1 | 8 | 0.522 | 1.000 | 1.000 | 1.000 |
| kf_reversal | 181 | 8 | -0.02 | -0.1 | 7 | 0.529 | 1.000 | 1.000 | 1.000 |
| quality_momentum | 24 | 5 | -0.28 | -0.3 | 4 | 0.614 | 1.000 | 1.000 | 1.000 |
| st_stoch_oversold | 316 | 5 | -0.18 | -0.7 | 4 | 0.750 | 1.000 | 1.000 | 1.000 |
| st_reversal_1d | 1,031 | 9 | -0.31 | -1.1 | 8 | 0.857 | 1.000 | 1.000 | 1.000 |
| rsi_reversion | 96 | 5 | -2.18 | -1.4 | 4 | 0.890 | 1.000 | 1.000 | 1.000 |

## A5. The enrollment event

Lab survivors were enrolled on 2026-09-27 with their start date set to 2026-09-24 (the LIVE start). The paper engine entered the 09-24 signals at the 09-24 close when the funds were created, three days after the fact. Those entries use only data through 09-24 (no feature look-ahead), and the survivor list was fixed by the 2020-2022 validation gate, not by anything after 09-24; but the trades are a replay and the funds were created knowing the outcome window. Trades dated before the first completed session on or before the fund's creation date are flagged retroactive.

| family | funds created | trades | retroactive | retro share | retro mean % | prospective trades | prospective dates | prospective mean % | prospective mean minus SPY % |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 2026-09-27 | 7,941 | 2,886 | 36.3% | +1.63 | 5,055 | 9 | +0.48 | +0.19 |
| momentum | 2026-09-12, 2026-09-13, 2026-09-25 | 392 | 71 | 18.1% | +6.27 | 321 | 17 | +0.70 | +0.56 |
| kf_seasonality | 2026-09-28, 2026-09-29, 2026-10-01 | 624 | 20 | 3.2% | +2.58 | 604 | 8 | +0.03 | -0.31 |
| st_uptrend_pullback | 2026-09-27, 2026-09-28 | 624 | 233 | 37.3% | +2.84 | 391 | 7 | -1.38 | -2.00 |
| bollinger_reversion | 2026-09-26, 2026-09-27, 2026-09-28 | 370 | 240 | 64.9% | -0.01 | 130 | 4 | +1.30 | +0.41 |
| kf_mean_reversion | 2026-09-28, 2026-10-02, 2026-10-05 | 123 | 3 | 2.4% | -4.07 | 120 | 6 | +1.85 | +1.25 |
| st_momentum_1d | 2026-09-27, 2026-09-28 | 1,116 | 200 | 17.9% | -1.05 | 916 | 9 | -0.25 | -0.57 |
| turn_of_month | 2026-09-26, 2026-09-27 | 160 | 0 | 0.0% | n/a | 160 | 2 | +1.86 | +0.51 |

### lab_search by entry date (honest net %, SPY over the same windows)

| entry date | trades | mean net % | mean SPY % | retroactive |
|---|---:|---:|---:|---|
| 2026-09-24 | 2,886 | +1.63 | +0.31 | yes |
| 2026-09-25 | 692 | +1.01 | +0.01 |  |
| 2026-09-28 | 703 | +1.23 | +0.21 |  |
| 2026-09-29 | 689 | +0.28 | +0.20 |  |
| 2026-09-30 | 684 | +1.55 | +0.99 |  |
| 2026-10-01 | 561 | +0.81 | +0.11 |  |
| 2026-10-02 | 522 | +0.88 | +1.06 |  |
| 2026-10-05 | 454 | -3.77 | -0.32 |  |
| 2026-10-06 | 379 | +0.08 | -0.10 |  |
| 2026-10-07 | 371 | +1.03 | +0.18 |  |

## What could be wrong with this analysis

- 5-19 independent entry dates in one market regime: t-distribution p-values with 4-18 degrees of freedom are fragile, and a family-level correlation from the same few dates is a rough guide only.
- The max-T sign-flip null assumes per-date family means are symmetric about zero; an absolute-return null is rejected by market drift alone, which is why the excess-over-SPY version is shown. SPY is a crude benchmark for a stock-picking family (beta and sector are not removed).
- 'Retroactive' uses the last completed session at creation; a fund created before the open could be argued either way by one session.
- The restated table excludes trades that exit on the newest stored bar (mostly stop-outs), which flatters every family until those trades can be restated.
- Choosing which families to test (families with >= 20 trades) is itself a data-dependent choice.
