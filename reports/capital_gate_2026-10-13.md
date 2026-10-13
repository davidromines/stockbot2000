# Phase C1: shadow eligibility gate for real capital

Computed 2026-10-13 05:49 UTC, SHADOW only: nothing here is read by `slots.py`, the risk engine or the trader. 384 strategies assessed (every fund with >= 20 honest trades, plus the five slot holders). Unknown blocks.

Thresholds (configuration, fixed before the run, not tuned): max_retro_share 0.25; min_dates 20; alpha 0.05; min_weeks 3; min_positive_weeks 0.6; cost_stress 2.0; max_corr 0.7; max_drawdown_pct 20.0; min_trades 20.
Prospective test `forward_families_prospective`: REGISTERED.

## The five current slot holders

| slot | strategy | trades | own dates | honest mean % | verdict | failed | unknown (cannot be assessed yet) |
|---:|---|---:|---:|---:|---|---|---|
| 1 | Lab-discovered strategy | 3 | 1 | +58.64 | NOT ELIGIBLE | C2, C4, C6 | C5, C7, C9, C12, C13 |
| 2 | Lab-discovered strategy | 11 | 4 | +18.35 | NOT ELIGIBLE | C2, C4, C6 | C5, C9, C13 |
| 3 | st_uptrend_pullback v2 (longer_hold) | 20 | 1 | +7.72 | NOT ELIGIBLE | C2, C4, C6 | C5, C7, C13 |
| 4 | st_reversal_1d v3 (trend_filter) | 40 | 2 | +1.80 | NOT ELIGIBLE | C4, C6, C9 | C5, C7, C13 |
| 5 | Lab-discovered strategy | 1 | 1 | +163.85 | NOT ELIGIBLE | C2, C4, C6 | C3, C5, C7, C8, C9, C12, C13 |

## How many strategies pass each criterion

| criterion | PASS | FAIL | UNKNOWN | not reached |
|---|---:|---:|---:|---:|
| C1 data integrity | 379 | 5 | 0 | 0 |
| C2 provenance | 188 | 196 | 0 | 0 |
| C3 net, realistic fills | 169 | 214 | 1 | 0 |
| C4 independent evidence | 0 | 384 | 0 | 0 |
| C5 uncertainty | 40 | 251 | 93 | 0 |
| C6 multiple testing | 0 | 362 | 22 | 0 |
| C7 stability | 100 | 111 | 173 | 0 |
| C8 cost sensitivity | 149 | 234 | 1 | 0 |
| C9 survivorship | 31 | 48 | 305 | 0 |
| C10 correlation | 0 | 0 | 0 | 384 |
| C11 downside | 384 | 0 | 0 | 0 |
| C12 decay | 204 | 178 | 2 | 0 |
| C13 prospective status | 0 | 0 | 384 | 0 |

**Eligible under the gate: 0 of 384. Slot holders eligible: 0 of 5.**

### Which single criterion blocks the most strategies that otherwise look good

Strategies with a positive honest mean and >= 20 trades, by the criteria they fail or cannot yet satisfy:

| criterion | blocks (of 167) |
|---|---:|
| C1 data integrity | 5 |
| C2 provenance | 88 |
| C4 independent evidence | 167 |
| C5 uncertainty | 127 |
| C6 multiple testing | 167 |
| C7 stability | 89 |
| C8 cost sensitivity | 20 |
| C9 survivorship | 156 |
| C12 decay | 35 |
| C13 prospective status | 167 |

## Proposed effect on live eligibility (for the owner's decision; nothing has been changed)

The gate asks for evidence the record cannot yet contain: 20 independent entry dates per strategy and a completed prospective test. Enforced today it would leave all five slots empty, which conflicts with the standing rule that slots are filled from day one and never wait for evidence. Options:

| option | effect | recommended |
|---|---|---|
| A. Keep it shadow only; publish the verdict beside each slot in the daily report | no change to trading; the evidence grade is visible | yes, now |
| B. Enforce only the do-no-harm criteria (C1, C2, C8, C9, C11) now; the evidence criteria stay informational | blocks strategies that are data-suspect, cost-fragile, or fail the worst-case survivorship | consider after A has run 2 weeks |
| C. Enforce the full gate | empties the slots until the prospective test completes (about December) | not before the prospective result |

## What could be wrong with this analysis

- The thresholds are judgement, fixed in advance, and have not been calibrated against any outcome.
- Strategy-level trades are mostly one fund's trades; a fund that trades rarely will fail C4 for a long time whatever its quality.
- C6 uses the family, not the strategy: a good strategy inside a bad family is blocked and a poor one inside a good family is not.
- Slot holders that are stand-ins or pair/value funds have no paper run and are assessed as UNKNOWN throughout.
- Live stops and sizing differ from the paper fund; the gate judges the paper record.
