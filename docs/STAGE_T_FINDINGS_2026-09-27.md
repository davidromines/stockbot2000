# Stage T — diagnostic findings, 2026-09-27

First pass of `STAGE_T_DIAGNOSTIC_FUNNEL.md`, read-only from `market_data.db`.
It changes nothing. Queries: `promotions`, `evaluations`, `strategy_ancestry`,
`strategy_decisions`, `survivorship_backtests`, `paper_*`, `strategy_meta`.

## 1. The funnels

### A. Evolutionary search (Lab): 2006-2019 search, 2020-2022 validation, 2023+ sealed

| stage | entered | passed | rate |
|---|---:|---:|---:|
| evaluated 2006-19 (survivor data, next-open fills, costs) | 1,039,115 | | |
| gross > 0 | 1,039,115 | 1,027,670 | 98.9% |
| net > 0 after costs | 1,039,115 | 972,297 | 93.6% |
| beats the random-entry null | 1,039,115 | 939,220 | 90.4% |
| shortlist (diversity + behavioural dedup) | | 5,145 | |
| validation 2020-22, out of sample (all runs) | 5,259 | 953 | 18% |
| validation, honest simulator only (runs from 09-16) | 3,362 | **649** | **19%** (noise: 5%) |
| sealed holdout 2023+ | 649 | **0 opened** | — |
| paper trading | 649 | **0** | — |
| ranking / live slots | 649 | **0** | — |

- The validation gate is excess over the null ≥ $2,300 (the 95th percentile of
  random strategies) plus Sharpe and trade minimums. Pure noise passes 5%; the
  shortlist passed 19%, **3.9x the noise rate**.
- Of the 649: 326 independent of the hand-written seed, 323 carry its literal
  constant. 172 distinct rule shapes, dominated by "strong relative strength +
  short-term oversold (RSI below N)".
- Median out-of-sample net per trade of passes: +1.5% (p10 +0.56%, p90 +3.7%).
- **The dominant bottleneck is not a gate: the ladder stops after validation.**
  No survivor was ever opened against the sealed period, paper-traded or
  ranked. The Lab was frozen (multiple testing, seed contamination) and the
  slots were rewired to `ranking.py`, which reads league/factory strategies
  only. The Lab's out-of-sample survivors have no path forward.

Honest-simulator validation failures (2,713), by how close they came:

| outcome | n |
|---|---:|
| net negative out of sample | 1,532 |
| net positive, below the null | 157 |
| excess 0-25% of the gate | 289 |
| excess 25-75% of the gate | 416 |
| excess within 25% of the gate (near miss) | 142 |
| cleared the excess gate, failed Sharpe / trade count (near miss) | 177 |

### B. Strategy Factory (economically motivated templates)

| stage | entered | passed | rate |
|---|---:|---:|---:|
| specified | 386 | 386 | |
| backtested 2016-19 | 386 | 382 | |
| validated (net > 0, validation window) | 382 | 248 | 65% |
| robustness (cost / slippage / period stress) | 248 | 208 | 84% |
| paper | 208 | 208 | 100% |
| qualified (forward evidence) | 208 | 20 | 10% |
| live candidate | 20 | 19 | |

178 rejections: 61 net negative in the backtest, 72 net negative in validation,
41 FRAGILE (mostly failing the 2x cost / slippage stress), 4 no trades.
**The factory admits 54% of what it specifies to paper — not restrictive.**

### C. Survivorship (302 ranked strategies, 2016-19, generator v5c)

| mode | positive | mean net / trade |
|---|---:|---:|
| survivors only | 271 (90%) | +1.03% |
| with synthetic dead companies (ranking uses this) | 238 (79%) | +0.80% |
| every death a total loss (worst case) | 168 (56%) | +0.25% |

Survivorship removes about a fifth of the positive backtests and a quarter of
the average return. It does not eliminate most strategies.

### D. Forward evidence

| | |
|---|---|
| paper funds with any mark | 30 of 536 (447 opened 09-26; first step Monday 09-28) |
| oldest forward record | 10 sessions (opened 09-04) |
| closed paper trades, all funds, ever | 190, from 13 funds |
| first 13 funds (09-04), after 10 sessions | 5 up, 8 down, mean −4.96% |
| crash-buyer family | 17 trades, −13.5% / trade |
| live slot trades | 4 closed, +$2.46 net |
| per-trade standard deviation (paper) | 12.6% |
| trades needed to show +1.0% / trade at t = 2 | ~635 |
| trades needed to show +0.5% / trade at t = 2 | ~2,500 |

## 2. Hypothesis coverage

- Lab: 1.04M trials, but 172 distinct shapes among honest survivors, mostly one
  idea (momentum + pullback). A million trials ≈ a few hundred ideas.
- Factory: 519 template strategies in 63 families. Heavy: momentum, breakout,
  reversion, calendar (12 each). Thin (1 strategy): low volatility, analyst
  revision, dividend, revenue / EPS growth, ROIC. Event-driven: buyback and
  earnings surprise only. Knowledge library: 3,987 entries, 55 linked.

## 3. Answers to the eight questions (§15)

| # | question | fact | inference |
|---|---|---|---|
| 1 | enough distinct hypotheses? | ~500 templates / 63 families + ~170 Lab shapes | adequate for a first pass; thin in low-vol, revisions, events |
| 2 | mostly parameter combinations? | yes for the Lab (1.04M trials → 172 shapes) | the trial count overstates the idea count ~6,000x |
| 3 | documented vs machine | 519 documented templates; Lab machine-generated | — |
| 4 | broad family coverage? | 63 families | broad but uneven |
| 5 | where does it collapse? | Lab: after validation (process stops). Factory: at forward qualification (10%), which has had ≤ 10 sessions | **calendar time, not gates** |
| 6 | what destroys edges? | in-sample → out-of-sample (Lab 19% survive); survivorship ~20%; costs ~6% in-sample | out-of-sample decay is the largest measured cause |
| 7 | small persistent positives? | 649 Lab + ~200 factory strategies positive out of sample / with the dead | yes, in backtests; none forward-proven yet |
| 8 | enough tests to call "no edge" meaningful? | 190 forward trades vs ~635-2,500 needed | **no — the absence of a proven edge is not yet evidence of no edge** |

## 4. Conclusion (§22)

**G — multiple problems, led by E (forward evidence) and a broken hand-off.**

- **FACT:** the validation system is not eliminating most strategies: 94% of Lab
  trials and 79% of ranked strategies are net positive in backtests with costs.
- **FACT:** 649 Lab strategies passed an honest out-of-sample test at 3.9x the
  noise rate and were never paper-traded, sealed-tested or ranked.
- **FACT:** forward evidence is ≤ 10 sessions and 190 trades.
- **INFERENCE:** "no proven edge" means "not yet measured forward", not
  "every idea failed". The main things between the system and a proven edge
  are time and the missing Lab → paper path.
- **UNKNOWN:** whether backtest-positive strategies stay positive forward. The
  only forward sample (13 funds, 10 sessions) is negative on average, which is
  consistent with both noise and decay.

## 5. Recommended next step

1. Paper-track the 649 honest Lab survivors (deduplicated by behaviour) through
   `paper_all.py` — paper costs no sealed-period use and no real money.
2. Let the ranking see them once they have forward trades.
3. Decide separately whether to spend the sealed 2023+ test on a small,
   pre-registered subset.
4. Remaining Stage T items not done in this pass: per-stage drawdown and
   Sharpe distributions, cost/slippage drag split, and a per-strategy failure
   reason table.
