# Shadow: backtest-first slot selection (nothing changed)

627 strategies are eligible (gate passed, worst case positive, unseen window positive where tested, a backtest exists).

## Would hold the slots

| # | strategy | family | backtest % | unseen 2023+ % | worst case % | per 20 sessions % | forward trades | forward (ranking basis) % |
|---:|---|---|---:|---:|---:|---:|---:|---:|
| 1 | The Stock Market Valuation of Research and Dev | kf_fundamental | +4.05 | +5.23 | +3.91 | +2.42 | 20 | -10.44 |
| 2 | A Tale of Two Strategies: Cash Flow, Accruals  | kf_quality | +2.34 | n/a | +1.88 | +2.22 | 1 | -0.15 |
| 3 | Earnings Surprise age=10 hold=60 q=0.9 | earnings_surprise | +1.52 | +4.99 | +1.39 | +2.06 | 1 | -1.67 |
| 4 | Price and Earning Momentum · reproduction | kf_momentum | +1.39 | +4.00 | +1.08 | +1.87 | 21 | +2.58 |
| 5 | Teaching Slides on Short and Long Horizon Beha | kf_hybrid | +0.65 | +1.81 | +0.65 | +1.86 | 2 | +2.56 |

## Holding the slots now

| slot | strategy | family | backtest % | unseen % | worst case % | forward trades |
|---:|---|---|---:|---:|---:|---:|
| 1 | Lab 56f07a: ((rank(chaikin_osc) > 0.6404 and p | lab_56f07a:_((rank(chaikin_osc)_>_0.6404_and_pct_off_52w_low | +1.84 | n/a | n/a | 23 |
| 2 | Lab 82731d: ((rank(macd_hist) > 0.438 and pct_ | lab_82731d:_((rank(macd_hist)_>_0.438_and_pct_off_52w_low_> | +1.69 | n/a | n/a | 36 |
| 3 | st_uptrend_pullback v2 (longer_hold) | st_uptrend_pullback | +0.46 | +0.04 | +0.16 | 40 |
| 4 | st_reversal_1d v3 (trend_filter) | st_reversal_1d | +0.05 | n/a | -0.09 | 60 |
| 5 | Lab 418761: ((rank(adx_14) > 0.7 and pct_off_5 | lab_418761:_((rank(adx_14)_>_0.7_and_pct_off_52w_low_>_0.5) | +0.91 | n/a | n/a | 21 |
