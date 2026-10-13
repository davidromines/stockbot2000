# Profitability, measured four ways (Addendum F Phase F / H7)

Computed 2026-10-13 06:28 UTC, read-only. Live figures are the real Robinhood account 403446024 since 2026-09-24; research figures are paper funds on the honest basis (next-open fills, modelled costs deducted). Live and research results are kept apart. Denominators are named in every heading.

## 1. The real account (denominator: the account's equity, cash and open positions included)

| measure | value | period / sample |
|---|---:|---|
| equity at first record | $87.71 | 2026-09-24 |
| equity now | $84.12 | 16 sessions |
| change since launch | $-3.59 (-4.10 %) | includes any deposits or withdrawals, which the equity series cannot separate |
| maximum drawdown (daily closes) | 6.5 % | 16 sessions |
| worst / best day | -2.15 % / +2.59 % | |
| realised P&L, closed trades | $+0.37 on $286.33 traded | 16 round trips |
| unrealised P&L, open positions | $-3.97 on $87.95 | 5 positions |
| realised + unrealised | $-3.59 | reconciles to the equity change within $0.00 |

### Real closed round trips (denominator: the trade)

16 trades: win rate 75%, mean +0.35 %, median +0.65 %, average win +1.78 %, average loss -3.93 %, profit factor 1.35; per deployed dollar-session +0.131 % (sessions held approximated as 1 for this line: holds are not stored on the live rows). No interval is meaningful at this sample size.

### Months (denominator: equity at the first and last close of the month)

| month | first close | last close | change | sessions |
|---|---:|---:|---:|---:|
| 2026-09 | $87.66 | $88.18 | +0.59 % | 7 |
| 2026-10 | $88.76 | $84.12 | -5.23 % | 9 |

Annualised return: **not reported** (16 sessions; at least 120 are needed before an annualised figure means anything). A 1 % monthly return would be about +$0.84 on this account; the account has not completed a month.

## 2. Current slot occupants, each since its own assignment (never added together)

| slot | occupant | assigned | closed trades | closed net | open positions (return %, unrealised $) |
|---:|---|---|---:|---:|---|
| 1 | Lab-discovered strategy (56f07a26) | 2026-10-05 | 0 | $+0.00 | WDC -12.85 % / $-2.57 |
| 2 | Lab-discovered strategy (82731d28) | 2026-10-01 | 0 | $+0.00 | CRS -2.76 % / $-0.53 |
| 3 | st_uptrend_pullback v2 (longer_hold) | 2026-10-09 | 0 | $+0.00 | INTC -5.56 % / $-0.97 |
| 4 | st_reversal_1d v3 (trend_filter) | 2026-10-12 | 0 | $+0.00 | AMD -0.02 % / $-0.00 |
| 5 | Lab-discovered strategy (4187611e) | 2026-10-06 | 0 | $+0.00 | FDX +0.92 % / $+0.10 |

## 3. Research families, honest basis (denominators named per column)

Per trade = net % of a trade. Per dollar-session = net dollars / (stake x sessions held), in % per deployed dollar per session. Fund return = median fund equity change per session including idle cash (the portfolio basis). Costs / gross = modelled costs over the gross profit of winning trades. 'Hit 1 %' = share of trades netting at least 1 %. Interval = date-block bootstrap of the per-trade mean.

| family | trades | dates | per trade % | 95% interval | median % | win | avg win % | avg loss % | profit factor | per dollar-session % | fund % per session | fund max dd % | util | hold | hit 1 % |
|---|---:|---:|---:|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| lab_search | 7,941 | 10 | +0.90 | -0.28 to +1.39 | +0.66 | 59% | +3.95 | -3.45 | 1.63 | +0.317 | +0.003 | 1.6 | 61% | 2.8 | 45% |
| momentum | 392 | 18 | +1.71 | -1.11 to +3.83 | +0.71 | 59% | +6.54 | -5.23 | 1.80 | +0.597 | +0.409 | 7.0 | 78% | 2.1 | 47% |
| kf_seasonality | 624 | 8 | +0.11 | -0.67 to +0.64 | +0.40 | 56% | +2.52 | -2.93 | 1.08 | +0.053 | +0.173 | 2.8 | 98% | 2.0 | 39% |
| st_uptrend_pullback | 624 | 8 | +0.19 | -2.46 to +2.02 | +0.17 | 51% | +4.74 | -4.60 | 1.09 | +0.049 | -0.261 | 6.5 | 98% | 3.9 | 43% |
| bollinger_reversion | 370 | 5 | +0.45 | +0.04 to +2.45 | -0.28 | 48% | +3.64 | -2.44 | 1.35 | +0.066 | +0.050 | 1.1 | 99% | 6.8 | 36% |
| kf_mean_reversion | 123 | 7 | +1.71 | -0.74 to +3.08 | +2.01 | 79% | +4.49 | -8.67 | 1.93 | +0.422 | +0.246 | 0.8 | 100% | 4.0 | 67% |
| st_momentum_1d | 1,116 | 10 | -0.39 | -1.27 to +0.41 | -0.18 | 47% | +2.61 | -3.08 | 0.76 | -0.205 | -0.218 | 5.4 | 98% | 1.9 | 34% |
| turn_of_month | 160 | 2 | +1.86 | n/a to n/a | +2.18 | 78% | +3.66 | -4.33 | 2.91 | +0.413 | +0.333 | 0.0 | 38% | 4.5 | 65% |
| ALL FAMILIES (pool) | 18,730 | 18 | -0.45 | -0.86 to +0.08 | -0.13 | 49% | +3.71 | -4.38 | 0.80 | -0.140 | -0.000 | 2.1 | 97% | 3.2 | 37% |

Costs relative to gross profit (research table only): lab_search 7%, momentum 4%, kf_seasonality 10%, st_uptrend_pullback 6%, bollinger_reversion 8%, kf_mean_reversion 4%, st_momentum_1d 12%, turn_of_month 5%, ALL FAMILIES (pool) 9%.

### By market regime (SPY up or down between the trade's two next-open fills)

| family | market up: trades | net % | market down: trades | net % |
|---|---:|---:|---:|---:|
| lab_search | 3,916 | +1.88 | 4,025 | -0.05 |
| momentum | 168 | +3.33 | 224 | +0.50 |
| kf_seasonality | 348 | +0.48 | 276 | -0.36 |
| st_uptrend_pullback | 467 | +0.16 | 157 | +0.28 |
| bollinger_reversion | 365 | +0.45 | 5 | +0.04 |
| kf_mean_reversion | 96 | +2.45 | 27 | -0.94 |
| st_momentum_1d | 570 | -0.32 | 546 | -0.47 |
| turn_of_month | 160 | +1.86 | 0 | n/a |
| ALL FAMILIES (pool) | 10,608 | -0.16 | 8,122 | -0.82 |

## 4. Where the 1 % target stands, on each basis

| basis | what 1 % would mean | what the record shows |
|---|---|---|
| per completed trade, research pool | mean net >= 1 % | pool -0.45 % (interval -0.86 to +0.08); 37% of trades reach 1 % |
| per completed trade, research families | mean net >= 1 % | momentum +1.71 % (-1.11 to +3.83, 18 dates); kf_mean_reversion +1.71 % (-0.74 to +3.08, 7 dates); turn_of_month +1.86 % (n/a to n/a, 2 dates) |
| per completed trade, real account | mean net >= 1 % | 16 trades, mean +0.35 %: no interval is meaningful |
| per deployed dollar per session | about 0.05 % (1 % over 21 sessions) | pool -0.140 %; families from -0.205 to +0.597 % |
| portfolio, cash included, real account | account grows 1 % in a calendar month | -4.10 % over 16 sessions; no full month yet |
| portfolio, cash included, paper funds | median fund grows 1 % in 21 sessions | the fund columns above come from the paper engine's own equity curve (same-close fills, not restated, replay included): pool median fund -0.000 % per session, so treat family differences there as the same unresolved record seen through a less honest lens |
| annualised | 12 % or more a year | not reportable |

Reading: the pool of research trades is negative on every basis. Three families average above 1 % per trade, each with an interval that includes zero and between 2 and 18 independent entry dates. The real account's closed trades are positive and its open positions are negative, netting to the equity change. Nothing here supports or refutes a 1 % monthly return; the most promising next experiment is the pre-registered prospective test (`prospective_eval.py`), the only measurement that cannot be inflated by how the candidates were found.

## What could be wrong with this analysis

- The account equity series includes any deposits or withdrawals; the check against realised + unrealised trade P&L above is what shows whether they matter.
- Paper funds hold up to 20 positions with $400; their portfolio basis is not the slot's one-position basis.
- The regime split uses SPY over each trade's hold; it describes the market while held, not a forecastable state, and the sample is one regime.
- Honest-basis trades exclude those that exit on the newest bar (mostly stop-outs).
- Live per-dollar-session uses one session per round trip because holds are not stored on live rows.
