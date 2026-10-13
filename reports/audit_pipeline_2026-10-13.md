# Phase B1-B2: the funnel to real money, and why no edge is established

Computed 2026-10-13 05:49 UTC, read-only, from the league tables, survivorship backtests (latest generator), the unseen-window results, `paper_trades_restated` (next-open fills, costs deducted) and `live_pnl`. Facts, inferences and unknowns are in separate sections.

## B1. Funnel (each stage requires the previous one)

| stage | strategies | families | typical result at this stage | lost vs previous |
|---|---:|---:|---:|---:|
| Documented hypotheses (knowledge library) | 4,158 |  |  |  |
| Strategy identities in the league (latest version each) | 2,233 | 99 |  |  |
| Backtested with survivorship modes (latest generator) or a stored backtest | 1,163 | 82 |  | 1,070 |
| Positive net backtest, survivors only, costs deducted | 1,092 | 77 | +1.10% per trade | 71 |
| Positive with the synthetic dead companies (as_is) | 1,005 | 72 | +0.87% per trade | 87 |
| Positive in the worst-case survivorship mode (zero) | 642 | 60 | +0.60% per trade | 363 |
| Positive on the unseen 2023-today window | 205 | 46 | +1.30% per trade | 437 |
| FORWARD CHAIN starts from every strategy with a paper fund (enrolled whatever its backtest said) | 2,191 | 94 |  |  |
| Forward honest record with >= 20 trades | 168 | 24 | -0.05% | 2,023 |
| ... and a positive honest net mean | 82 | 12 | +1.09% | 86 |
| ... and >= 20 independent entry dates of its own | 0 | 0 |  | 82 |
| Assigned to a real-money slot at least once | 18 | | | |
| Positive completed real-account P&L | strategies cannot be isolated: 16 closed live trades, 12 winners, net $+0.37 on $286 deployed | | | |

Parameter variants are not independent hypotheses: 99 families hold the strategy identities (42% of them `lab_search`), 1,039,345 Lab evaluations reduce to ~127,000 distinct structures, and the number of effectively independent family-level tests is about 28 (Phase A4).

### Distribution of results at the stages that have a per-trade number

- Survivors-only backtests: 95% positive of 1,136; with the synthetic dead companies (as_is) 89% of 1,136; worst-case treatment (zero) 57% of 1,136; unseen 2023-today window 86% of 337.
- Forward, all 18,730 honest-basis trades: mean gross -0.27 %, costs +0.18 %, net -0.45 % per trade.

Weekly entry cohorts (honest net %, all funds pooled):

| entry week | trades | mean net % |
|---|---:|---:|
| 2026-08-31/2026-09-06 | 102 | -4.28 |
| 2026-09-07/2026-09-13 | 50 | +3.54 |
| 2026-09-14/2026-09-20 | 50 | +0.98 |
| 2026-09-21/2026-09-27 | 7,046 | -0.50 |
| 2026-09-28/2026-10-04 | 8,909 | -0.21 |
| 2026-10-05/2026-10-11 | 2,573 | -1.06 |

SPY over the forward window (2026-09-24 to 2026-10-09): +1.48 %.

## B2. Candidate causes, with the measurement behind each

| cause | measured here | what it says |
|---|---|---|
| Backtests contain residual measurement problems | paper fills were at the signal-day close and `pnl_pct` was gross (A1); honest recompute cut `lab_search` +1.30 % to +0.90 % and `momentum` +2.04 % to +1.71 % | present and now corrected in the funnel; the ranking was already net but still same-close |
| Historical positives do not survive forward testing | forward pool mean -0.45 % per trade honest-net vs +0.08 % as_is backtest on the same 66 funds (-0.50 % forward) | large gap: backtests predict a level far above what is realised |
| Backtests do not rank strategies | rank correlation of backtest with later forward mean, funds with >= 20 trades: exclude -0.18 (n 66), as_is +0.10 (n 66), unseen window n/a (n 27) | weak or no ordering power in 3 weeks of one regime; cannot be called either way |
| Survivorship treatment distorts results | 89% positive as_is vs 57% in the worst case vs 95% survivors-only | the verdict on a strategy depends on an unidentifiable assumption about companies we cannot price |
| Costs erase gross returns | mean gross -0.27 % minus costs +0.18 % | gross is already negative at the pool level, so costs are not what decides the pool result |
| Hypotheses are redundant | 88-99 families, 1.05 M trials -> ~127,000 structures, ~28 effective independent tests | the searchable space is explored many times over by near-identical rules |
| Validation is overly restrictive | 94 % of backtests are net positive; validation passes 953 of ~5,200 Lab shortlisted | the gate is not what stops candidates: positives are plentiful and uninformative (Stage T) |
| Ranking selects the wrong candidates | Phase B3: top-quintile stored score realised below the middle quintile; top-50 funds rest on a median of 20 trades from one entry date | substantial, and addressable at low cost |
| The time series is too short | 12 trading sessions of entries, 0 strategies with >= 20 independent entry dates of their own, one market regime | the dominant limit on what can be concluded either way |
| Paper does not reproduce real execution | live 16 closed trades net $+0.37; the slot adds stops and ATR sizing that the paper fund does not | not measurable yet: too few live trades per strategy |
| Metrics do not match the owner's objective | per-trade vs per-dollar vs portfolio return are not yet reported together (Phase F) | owner ruling 2026-10-13: report all four side by side |

### Ranking of causes (judgement, from the measurements above)

| rank | cause | impact | confidence | cost to address |
|---:|---|---|---|---|
| 1 | Too few independent observations (dates, regimes) for any claim | decisive | high | time only; cannot be bought |
| 2 | Ranking promotes unproven strategies on counts of correlated trades (n = open positions from one date) | high: it chooses the live slots | high on the mechanism, medium on the size | low: a shadow gate (Phase C1) and an estimator that counts dates |
| 3 | Backtest-to-forward gap (survivorship, fills, selection among thousands) | high | medium | medium: already partly corrected; prospective test (A6) measures it |
| 4 | Redundant hypotheses inflate apparent breadth | medium | high | low: report families not variants; Phase E |
| 5 | Measurement defects (same-close fills, gross-as-net, replay) | was high, now corrected in the funnel and restated | high | done (G1-G3) |
| 6 | Regime and decay | unknown | low: one regime observed | needs time; regime descriptions only |
| 7 | Costs | low at pool level | medium | n/a |

## Facts, inferences, unknowns

- FACT: no strategy has 20 independent entry dates of its own on the honest basis; no family survives multiple-testing adjustment; the real account is $-3.59 from its first recorded equity.
- INFERENCE: the dominant reason no edge is established is sample size and the way sample size is counted, not a shortage of ideas or of compute.
- UNKNOWN: whether any family has an edge; whether the survivorship assumption helps or hurts; how the live slots' stops change a paper rule's result.

## What could be wrong with this analysis

- The funnel's stage definitions are mine; a different threshold changes the counts (the cumulative structure does not change the conclusion).
- `holdout_results` and `survivorship_backtests` exist only for strategies that reached those stages, so 'positive' shares are of the tested subset.
- Forward honest records omit trades that exit on the newest bar.
- The ranking of causes is a judgement; the measured numbers beside it are the evidence, the order is not a computed result.
