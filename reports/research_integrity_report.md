# Research integrity report

Generated 2026-09-24T07:48:06+00:00 from the live database. Every figure is
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
| **total trials** | **1,049,968** |
| unique structures | 126,652 |
| effective (estimate) | 364,665 |

**The best of pure noise at this count scores about 5.27 standard errors.** A survivor must clear that, not
merely be positive. No survivor currently does.

### What random strategies actually look like here

That bar is theoretical — it assumes the trial statistics are standard normal, which Sharpes computed off a few hundred trades
are not. So the same question is also asked empirically, by running never-evolved random genomes through the identical panel, cost
model, null surface and gate a real candidate faces.

| | |
|---|---:|
| random genomes measured | 350 |
| passed the validation gate | 0 (0.0%) |
| best Sharpe achieved by noise | **1.14** |
| best P&L achieved by noise | **$10,980** |
| 95th percentile Sharpe | 0.20 |

The best of 350 strategies known to be worthless made $10,980 in this simulator. That figure is the reason
no backtest number in this document should be read as a finding on its own.

Search mode is **FROZEN**.

## What is in forward testing, and for how long

26 strategy funds and 5 pair funds, 174 closed paper trades.

| fund | family | started | return |
|---|---|---|---:|
| Rising 200 · Stop 2.5 | momentum | 2026-09-04 | +13.31% |
| Rising 200 · Stop 3.3 | momentum | 2026-09-04 | +8.75% |
| Rising 200 · Stop 2.6 | momentum | 2026-09-04 | +6.59% |
| Rising 200 · Stop 5.0 a | momentum | 2026-09-04 | +1.90% |
| Rising 200 · Stop 5.0 b | momentum | 2026-09-04 | +1.52% |
| MACD Pullback | momentum | 2026-09-11 | +0.65% |
| fundamental_price_momentum v1 | fundamental_price_momentum | 2026-09-22 | +0.00% |
| fundamental_price_momentum v1 | fundamental_price_momentum | 2026-09-22 | +0.00% |
| growth_valuation v1 | growth_valuation | 2026-09-22 | +0.00% |
| growth_valuation v1 | growth_valuation | 2026-09-22 | +0.00% |
| quality_momentum v1 | quality_momentum | 2026-09-22 | +0.00% |
| quality_momentum v1 | quality_momentum | 2026-09-22 | +0.00% |
| value_quality v1 | value_quality | 2026-09-22 | +0.00% |
| value_quality v1 | value_quality | 2026-09-22 | +0.00% |
| value_quality_momentum v1 | value_quality_momentum | 2026-09-22 | +0.00% |
| value_quality_momentum v1 | value_quality_momentum | 2026-09-22 | +0.00% |
| Rising 200 · Stop 5.0 c | momentum | 2026-09-04 | -1.19% |
| Crash Buyer 20d a | crash | 2026-09-04 | -8.09% |
| Rising 50 | momentum | 2026-09-04 | -8.16% |
| Crash Buyer 20d b | crash | 2026-09-04 | -9.37% |
| Crash Buyer 10d | crash | 2026-09-04 | -17.18% |
| Crash Buyer 20d c | crash | 2026-09-04 | -17.28% |
| XGBoost Classifier | model | 2026-09-04 | -20.12% |
| Crash Buyer 5d | crash | 2026-09-04 | -29.73% |

**Stalled and excluded from the count** (last marked 2026-09-21, others 2026-09-23): Deep Value screen, Quality Value screen

6 of 24 are up. **These records are days old, not years.**
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