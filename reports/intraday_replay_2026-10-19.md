# Intraday replays — 2026-10-19

Read-only research (Stage AD7). Nothing here changes a rule or places an order.

## 1. v0 Runner rules on free 1-minute history (20 sessions, 210 names)

| Runner | signals | sessions | mean net | median | win | t (by day) | random-time control | vs control (t) | 30-min vs SPY |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| stock | 302 | 19 | -0.107% | -0.180% | 36% | -3.34 | +0.120% | -0.227% (-6.72) | +0.011% |
| twin | 54 | 17 | -0.140% | -0.105% | 28% | -3.27 | -0.058% | -0.082% (-1.22) | -0.067% |

Net = after the scanner's spread estimate and 2 bps slippage per side, exits by the configured stop, 60-minute limit or 15:45 flatten, one bar of latency. Each name's first signal per session; the population, not the cash-limited book. A replay on ~20 sessions is weak evidence either way.

- stock exits: maximum holding time 196, trailing stop 96, initial stop 10
- twin exits: maximum holding time 28, trailing stop 21, initial stop 5

## 2. Market intraday momentum (first period -> last half-hour)

| bars | index | days | corr | t | hit rate | timed long-only net / day | t | always-long net / day |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| 30m | IWM | 59 | +0.006 | +0.04 | 44% | -0.072% | -3.08 | -0.124% |
| 30m | QLD | 59 | +0.139 | +1.06 | 44% | -0.048% | -0.77 | -0.192% |
| 30m | QQQ | 59 | +0.151 | +1.15 | 44% | -0.066% | -2.18 | -0.136% |
| 30m | SPY | 59 | -0.015 | -0.11 | 39% | -0.096% | -4.92 | -0.135% |
| 30m | SSO | 59 | -0.026 | -0.20 | 37% | -0.099% | -2.49 | -0.179% |
| 60m | IWM | 717 | -0.001 | -0.03 | 51% | -0.082% | -9.02 | -0.091% |
| 60m | QLD | 717 | -0.004 | -0.11 | 48% | -0.094% | -4.81 | -0.077% |
| 60m | QQQ | 717 | -0.001 | -0.02 | 49% | -0.095% | -9.59 | -0.083% |
| 60m | SPY | 717 | -0.033 | -0.87 | 50% | -0.095% | -11.77 | -0.088% |
| 60m | SSO | 717 | -0.026 | -0.70 | 50% | -0.088% | -5.53 | -0.085% |

30m: first half-hour (previous close -> 10:00) vs 15:30-16:00. 60m: first hour (previous close -> 10:30) vs the 15:30-16:00 bar. Timed = buy the bull ETF at 15:30 if the first return is up, the inverse ETF if down, sell at the close, net of modelled spread + slippage. The configured twin Runner cannot take this trade (entries end 14:30, flat by 15:45).

## 3. Prospective: the live Runners' logged signals (pre-registered `intraday_runner_v0_prospective`)

No signals since 2026-10-20 yet.

