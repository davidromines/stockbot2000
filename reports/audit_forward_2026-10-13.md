# Forward-family audit (Addendum F, Phase A1-A3)

Computed 2026-10-13 04:51 UTC from `paper_trades` / `paper_runs` / `prices`, read-only. Provisional labels are mechanical; the verdict (A6) is a human decision.

**Two findings about the paper engine come first** (verified in `paper_trading.py` and in the rows below): (1) entries are priced at the CLOSE of the signal session and exits at the close that triggers them, not at the next open (the simulator and backtest were fixed to next-open on 2026-09-15; the paper engine was not); (2) `pnl_pct`, which the funnel and the dossier call net, is the GROSS price move: modelled costs are stored but not deducted from it.

## Summary (basis D unless stated)

| family | trades | funds | unique entries | dup factor | funnel t (iid, gross, same-close) | t after costs + next-open fills (iid) | cluster t D: date / ticker | independent entry dates | n_eff | mean D | 95% boot CI D | provisional label |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
| lab_search | 8,791 | 566 | 2,941 | 2.99 | +18.5 | +11.9 | +2.2 / +4.4 | 10 | 271 | +0.90% | [-0.25%, +1.40%] | Unresolved: only 10 independent entry dates (need 20+) |
| momentum | 416 | 10 | 155 | 2.68 | +4.2 | +2.9 | +1.4 / +2.0 | 18 | 88 | +1.71% | [-1.03%, +3.78%] | Unresolved: only 18 independent entry dates (need 20+) |
| kf_seasonality | 706 | 18 | 259 | 2.73 | +2.8 | +0.7 | +0.3 / +0.3 | 8 | 136 | +0.11% | [-0.70%, +0.62%] | Unresolved: only 8 independent entry dates (need 20+) |
| st_uptrend_pullback | 627 | 15 | 198 | 3.17 | +1.5 | +0.8 | +0.1 / +0.3 | 8 | 23 | +0.19% | [-2.58%, +1.99%] | Unresolved: only 8 independent entry dates (need 20+) |
| bollinger_reversion | 370 | 14 | 78 | 4.74 | +1.9 | +2.2 | +1.1 / +0.9 | 5 | 89 | +0.45% | [+0.03%, +2.45%] | Unresolved: only 5 independent entry dates (need 20+) |
| kf_mean_reversion | 158 | 36 | 57 | 2.77 | +2.2 | +2.8 | +2.4 / +1.3 | 7 | 90 | +1.71% | [-0.70%, +3.12%] | Unresolved: only 7 independent entry dates (need 20+) |
| st_momentum_1d | 1,157 | 12 | 348 | 3.32 | -1.5 | -3.3 | -0.9 / -1.3 | 10 | 86 | -0.39% | [-1.26%, +0.42%] | Unresolved: only 10 independent entry dates (need 20+) |
| turn_of_month | 160 | 8 | 40 | 4.00 | +10.3 | +5.5 | +11.6 / +1.9 | 2 | 713 | +1.86% | [+1.70%, +2.02%] | Unresolved: only 2 independent entry dates (need 20+) |

Noise-only luck thresholds for the largest of N independent t-statistics (95%): N=88 (88 families): 3.25, N=1,405 (1,405 specs): 3.97, N=127,652 (127,652 Lab structures): 4.93.
A label above 'unresolved' also needs at least 20 independent entry dates.

## lab_search

- Rows 8,791 from 566 funds; 2,941 distinct (ticker, entry date) opportunities (each taken by 2.99 funds on average); 1201 tickers; 11 entry dates (2026-09-24 to last exit 2026-10-09).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.178% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 93.8% of rows; exit price equals that day's close on 96.7%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **81 rows**, tickers BTI, CMCSA, CTVA, EIX, FBRT, GNL, NLY, ORC, REFI, THRM, VZ.
- 7,941 of 8,791 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 8,791 | +1.30 | 6.61 | +18.5 | +0.78 / +7.5 / 2,941 | +3.0 (11) | +6.7 (1201) | 38.7 | 227 | [+0.30, +1.90] | 0.003 |
| B. net of modelled costs, same-close fills, all rows | 8,791 | +1.13 | 6.61 | +16.0 | +0.60 / +5.7 / 2,941 | +2.6 (11) | +5.8 (1201) | 38.7 | 227 | [+0.12, +1.72] | 0.010 |
| C. net, same-close fills, rows that have a next-open price | 7,941 | +1.05 | 6.66 | +14.1 | +0.58 / +5.2 / 2,721 | +2.2 (10) | +5.3 (1159) | 41.9 | 190 | [-0.11, +1.69] | 0.038 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 7,941 | +0.90 | 6.73 | +11.9 | +0.50 / +4.5 / 2,721 | +2.2 (10) | +4.4 (1159) | 29.3 | 271 | [-0.25, +1.40] | 0.052 |

- Stability (net, same-close): entries before 2026-10-01: mean +1.41% (n 5,971); on or after: +0.52% (n 2,820).
- Fund cohorts (net, same-close): funds created after 09-26: mean +1.13% (n 8,791).
- Exit reasons: {'exit_rule': 6855, 'take_profit': 1541, 'horizon_timeout': 233, 'stop_loss': 162}.
- **Provisional label:** Unresolved: only 10 independent entry dates (need 20+)

## momentum

- Rows 416 from 10 funds; 155 distinct (ticker, entry date) opportunities (each taken by 2.68 funds on average); 63 tickers; 19 entry dates (2026-09-04 to last exit 2026-10-09).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.176% of notional per round trip. Notional min / median / max $10.00 / $20.00 / $20.00.
- Entry price equals that day's close on 99.0% of rows; exit price equals that day's close on 97.1%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **9 rows**, tickers IRD, MRNA, SWVL, TXG, XHLD.
- 392 of 416 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 416 | +2.04 | 9.87 | +4.2 | +1.59 / +2.2 / 155 | +1.5 (19) | +2.3 (63) | 7.9 | 53 | [-0.49, +4.53] | 0.068 |
| B. net of modelled costs, same-close fills, all rows | 416 | +1.86 | 9.87 | +3.8 | +1.38 / +2.0 / 155 | +1.4 (19) | +2.2 (63) | 7.8 | 53 | [-0.65, +4.35] | 0.090 |
| C. net, same-close fills, rows that have a next-open price | 392 | +1.65 | 10.03 | +3.3 | +1.34 / +1.8 / 146 | +1.2 (18) | +1.8 (61) | 7.8 | 50 | [-0.93, +4.18] | 0.138 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 392 | +1.71 | 11.76 | +2.9 | +1.52 / +2.1 / 146 | +1.4 (18) | +2.0 (61) | 4.4 | 88 | [-1.03, +3.78] | 0.105 |

- Stability (net, same-close): entries before 2026-09-25: mean +3.96% (n 204); on or after: -0.16% (n 212).
- Fund cohorts (net, same-close): funds created on or before 09-26: mean +1.86% (n 416).
- Exit reasons: {'exit_rule': 389, 'take_profit': 15, 'stop_loss': 5, 'unpriceable': 4, 'horizon_timeout': 3}.
- **Provisional label:** Unresolved: only 18 independent entry dates (need 20+)

## kf_seasonality

- Rows 706 from 18 funds; 259 distinct (ticker, entry date) opportunities (each taken by 2.73 funds on average); 47 tickers; 9 entry dates (2026-09-28 to last exit 2026-10-09).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.153% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 95.0% of rows; exit price equals that day's close on 95.6%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **0 rows**.
- 624 of 706 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 706 | +0.46 | 4.41 | +2.8 | -0.09 / -0.4 / 259 | +0.8 (9) | +1.2 (47) | 12.6 | 56 | [-0.81, +1.32] | 0.239 |
| B. net of modelled costs, same-close fills, all rows | 706 | +0.31 | 4.41 | +1.9 | -0.24 / -1.0 / 259 | +0.5 (9) | +0.8 (47) | 12.6 | 56 | [-0.97, +1.17] | 0.322 |
| C. net, same-close fills, rows that have a next-open price | 624 | +0.44 | 4.39 | +2.5 | -0.14 / -0.6 / 228 | +0.7 (8) | +1.1 (45) | 14.3 | 44 | [-1.14, +1.41] | 0.286 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 624 | +0.11 | 4.06 | +0.7 | -0.15 / -0.7 / 228 | +0.3 (8) | +0.3 (45) | 4.6 | 136 | [-0.70, +0.62] | 0.399 |

- Stability (net, same-close): entries before 2026-10-02: mean +1.26% (n 394); on or after: -0.90% (n 312).
- Fund cohorts (net, same-close): funds created after 09-26: mean +0.31% (n 706).
- Exit reasons: {'exit_rule': 472, 'horizon_timeout': 220, 'stop_loss': 14}.
- **Provisional label:** Unresolved: only 8 independent entry dates (need 20+)

## st_uptrend_pullback

- Rows 627 from 15 funds; 198 distinct (ticker, entry date) opportunities (each taken by 3.17 funds on average); 139 tickers; 9 entry dates (2026-09-24 to last exit 2026-10-09).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.162% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 99.8% of rows; exit price equals that day's close on 100.0%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **0 rows**.
- 624 of 627 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 627 | +0.36 | 6.22 | +1.5 | -0.56 / -1.4 / 198 | +0.3 (9) | +0.6 (139) | 21.1 | 30 | [-2.05, +1.93] | 0.411 |
| B. net of modelled costs, same-close fills, all rows | 627 | +0.20 | 6.22 | +0.8 | -0.72 / -1.8 / 198 | +0.2 (9) | +0.3 (139) | 21.1 | 30 | [-2.21, +1.77] | 0.465 |
| C. net, same-close fills, rows that have a next-open price | 624 | +0.21 | 6.23 | +0.9 | -0.68 / -1.7 / 196 | +0.2 (8) | +0.4 (137) | 21.3 | 29 | [-2.25, +1.81] | 0.464 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 624 | +0.19 | 6.25 | +0.8 | -0.48 / -1.3 / 196 | +0.1 (8) | +0.3 (137) | 27.5 | 23 | [-2.58, +1.99] | 0.478 |

- Stability (net, same-close): entries before 2026-10-01: mean +1.46% (n 444); on or after: -2.87% (n 183).
- Fund cohorts (net, same-close): funds created after 09-26: mean +0.20% (n 627).
- Exit reasons: {'horizon_timeout': 622, 'stop_loss': 5}.
- **Provisional label:** Unresolved: only 8 independent entry dates (need 20+)

## bollinger_reversion

- Rows 370 from 14 funds; 78 distinct (ticker, entry date) opportunities (each taken by 4.74 funds on average); 68 tickers; 5 entry dates (2026-09-24 to last exit 2026-10-08).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.153% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 85.4% of rows; exit price equals that day's close on 98.4%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **0 rows**.
- 370 of 370 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 370 | +0.39 | 3.92 | +1.9 | +1.07 / +2.5 / 78 | +1.0 (5) | +0.8 (68) | 3.8 | 97 | [-0.01, +2.25] | 0.032 |
| B. net of modelled costs, same-close fills, all rows | 370 | +0.24 | 3.92 | +1.2 | +0.91 / +2.1 / 78 | +0.6 (5) | +0.5 (68) | 3.8 | 97 | [-0.16, +2.09] | 0.178 |
| C. net, same-close fills, rows that have a next-open price | 370 | +0.24 | 3.92 | +1.2 | +0.91 / +2.1 / 78 | +0.6 (5) | +0.5 (68) | 3.8 | 97 | [-0.16, +2.09] | 0.178 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 370 | +0.45 | 3.93 | +2.2 | +1.24 / +2.9 / 78 | +1.1 (5) | +0.9 (68) | 4.2 | 89 | [+0.03, +2.45] | 0.004 |

- Stability (net, same-close): entries before 2026-09-30: mean +0.09% (n 280); on or after: +0.72% (n 90).
- Fund cohorts (net, same-close): funds created after 09-26: mean +0.78% (n 90); funds created on or before 09-26: mean +0.07% (n 280).
- Exit reasons: {'horizon_timeout': 284, 'exit_rule': 82, 'stop_loss': 4}.
- **Provisional label:** Unresolved: only 5 independent entry dates (need 20+)

## kf_mean_reversion

- Rows 158 from 36 funds; 57 distinct (ticker, entry date) opportunities (each taken by 2.77 funds on average); 42 tickers; 8 entry dates (2026-09-25 to last exit 2026-10-09).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.157% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 88.0% of rows; exit price equals that day's close on 99.4%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **8 rows**, tickers VZ.
- 123 of 158 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 158 | +1.22 | 7.11 | +2.2 | -0.00 / -0.0 / 57 | +1.1 (8) | +0.9 (42) | 3.9 | 41 | [-1.92, +3.19] | 0.156 |
| B. net of modelled costs, same-close fills, all rows | 158 | +1.06 | 7.11 | +1.9 | -0.16 / -0.2 / 57 | +1.0 (8) | +0.8 (42) | 3.9 | 41 | [-2.07, +3.04] | 0.178 |
| C. net, same-close fills, rows that have a next-open price | 123 | +2.04 | 6.63 | +3.4 | +0.07 / +0.1 / 48 | +3.1 (7) | +1.6 (36) | 1.2 | 100 | [+0.20, +3.69] | 0.021 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 123 | +1.71 | 6.65 | +2.8 | +0.42 / +0.4 / 48 | +2.4 (7) | +1.3 (36) | 1.4 | 90 | [-0.70, +3.12] | 0.048 |

- Stability (net, same-close): entries before 2026-10-02: mean +1.11% (n 66); on or after: +1.03% (n 92).
- Fund cohorts (net, same-close): funds created after 09-26: mean +1.06% (n 158).
- Exit reasons: {'exit_rule': 120, 'stop_loss': 38}.
- **Provisional label:** Unresolved: only 7 independent entry dates (need 20+)

## st_momentum_1d

- Rows 1,157 from 12 funds; 348 distinct (ticker, entry date) opportunities (each taken by 3.32 funds on average); 197 tickers; 11 entry dates (2026-09-24 to last exit 2026-10-09).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.153% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 97.0% of rows; exit price equals that day's close on 97.1%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **0 rows**.
- 1,116 of 1,157 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 1,157 | -0.20 | 4.59 | -1.5 | -0.34 / -1.5 / 348 | -0.2 (11) | -0.6 (197) | 43.4 | 27 | [-2.03, +1.27] | 0.595 |
| B. net of modelled costs, same-close fills, all rows | 1,157 | -0.35 | 4.59 | -2.6 | -0.50 / -2.2 / 348 | -0.4 (11) | -1.1 (197) | 43.4 | 27 | [-2.19, +1.12] | 0.658 |
| C. net, same-close fills, rows that have a next-open price | 1,116 | -0.31 | 4.61 | -2.2 | -0.48 / -2.0 / 320 | -0.3 (10) | -1.0 (182) | 42.6 | 26 | [-2.11, +1.17] | 0.652 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 1,116 | -0.39 | 4.00 | -3.3 | -0.53 / -2.3 / 320 | -0.9 (10) | -1.3 (182) | 12.9 | 86 | [-1.26, +0.42] | 0.829 |

- Stability (net, same-close): entries before 2026-10-01: mean +0.52% (n 662); on or after: -1.52% (n 495).
- Fund cohorts (net, same-close): funds created after 09-26: mean -0.35% (n 1,157).
- Exit reasons: {'horizon_timeout': 1131, 'stop_loss': 26}.
- **Provisional label:** Unresolved: only 10 independent entry dates (need 20+)

## turn_of_month

- Rows 160 from 8 funds; 40 distinct (ticker, entry date) opportunities (each taken by 4.00 funds on average); 20 tickers; 2 entry dates (2026-09-29 to last exit 2026-10-06).
- What `pnl_pct` is: equals the gross price move on 100.0% of rows and net P&L / notional on 0.0%. Mean modelled cost 0.153% of notional per round trip. Notional min / median / max $20.00 / $20.00 / $20.00.
- Entry price equals that day's close on 95.0% of rows; exit price equals that day's close on 95.0%.
- Corporate-action check (recorded entry or exit price more than 1.5% from the adjusted close on that date): **0 rows**.
- 160 of 160 rows have a next-session open for both legs (trades exiting on the last stored bar do not).

| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |
|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|
| A. as reported: GROSS, same-close fills, all rows | 160 | +3.81 | 4.72 | +10.2 | +3.81 / +5.1 / 40 | +84.6 (2) | +3.6 (20) | 0.0 | 10949 | [+3.77, +3.86] | 0.000 |
| B. net of modelled costs, same-close fills, all rows | 160 | +3.66 | 4.72 | +9.8 | +3.66 / +4.9 / 40 | +81.2 (2) | +3.4 (20) | 0.0 | 10949 | [+3.61, +3.71] | 0.000 |
| C. net, same-close fills, rows that have a next-open price | 160 | +3.66 | 4.72 | +9.8 | +3.66 / +4.9 / 40 | +81.2 (2) | +3.4 (20) | 0.0 | 10949 | [+3.61, +3.71] | 0.000 |
| D. net, NEXT-OPEN fills on adjusted prices, same rows as C | 160 | +1.86 | 4.28 | +5.5 | +1.86 / +2.7 / 40 | +11.6 (2) | +1.9 (20) | 0.2 | 713 | [+1.70, +2.02] | 0.000 |

- Stability (net, same-close): entries before 2026-09-30: mean +3.71% (n 80); on or after: +3.61% (n 80).
- Fund cohorts (net, same-close): funds created after 09-26: mean +3.66% (n 80); funds created on or before 09-26: mean +3.66% (n 80).
- Exit reasons: {'exit_rule': 160}.
- **Provisional label:** Unresolved: only 2 independent entry dates (need 20+)

## What could be wrong with this audit

- The window is about 16 sessions of one market; any family's mean can move with the next week of trades, and the entry dates are too few to treat as independent draws of the market.
- Basis D uses the adjusted price series for both legs, which also corrects spin-offs and splits; a dividend adjustment is small but not zero. Next-open prices are the best available proxy for a real fill, not a fill.
- Clustering by entry date or ticker handles a shared market move and repeated tickers, not every dependence (overlapping holds, correlated strategies on different tickers).
- The modelled round-trip cost (about 0.15-0.18% of notional) is the engine's own number, not measured fills.
- Luck thresholds assume independent tests and a known N; both are uncertain.
- The funnel's t is the same formula as the iid column here; differences between them are a different data snapshot.
