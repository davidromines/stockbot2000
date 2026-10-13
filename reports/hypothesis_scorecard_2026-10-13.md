# Phase E1-E2: the Knowledge Factory audit and the hypothesis scorecard

Computed 2026-10-13 06:30 UTC, read-only except the append-only `hypothesis_scorecard` table. The scorecard orders experiments; it is not evidence that any hypothesis is profitable.

## E1. What the library actually contains

- **4,158 documented ideas**, of which **3,580 are title-only** (no extractable rule): they sit in lineages named `*:untranslated` and cannot be tested. Usable specifications: 407 with a stored genome (32 fully and 351 partly machine-translatable); 57 marked data-available, 87 data-unavailable.
- Those specifications map to **105 distinct lineages** (the unit of an economic hypothesis) and produced **1,086 strategies from 372 entries**; 344 are recorded reproductions of a source rule.

| source | type | entries |
|---|---|---:|
| pwb_papers | ACADEMIC_PAPER | 3,803 |
| jkp | KNOWN_FACTOR | 153 |
| qc_library | PRACTITIONER_RESEARCH | 84 |
| pwb_coded | PRACTITIONER_RESEARCH | 60 |
| stockbot | ACADEMIC_PAPER | 40 |
| opts_literature | ACADEMIC_PAPER | 17 |
| owner | PRACTITIONER_RESEARCH | 1 |

### Strategies by origin (latest version of each; machine search shown for contrast)

| origin | strategies | lineages | strategies per lineage | positive as_is | positive worst case | positive unseen | funds with >= 20 fwd trades | mean fwd honest % (funds with >= 20 trades) | specified before first evaluation |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| CONTROLLED_VARIANT | 618 | 45 | 13.7 | 91% | 57% | 79% | 0 | n/a | 100% |
| MACHINE_GENERATED | 529 | 4 | 132.2 | n/a | n/a | n/a | 83 | +0.25 | n/a |
| HYBRID | 424 | 2 | 212.0 | n/a | n/a | n/a | 19 | +1.02 | n/a |
| TEMPLATE | 388 | 71 | 5.5 | 89% | 67% | 87% | 51 | -0.65 | 77% |
| ORIGINAL_REPRODUCTION | 252 | 93 | 2.7 | 85% | 44% | 85% | 15 | +0.02 | 99% |
| FUND | 22 | 9 | 2.4 | n/a | n/a | n/a | 0 | n/a | n/a |

Outside machine search there are 1,281 strategies in 175 lineages: **7 variants per lineage on average**; the five largest lineages hold 272 strategies (21%): EARNINGS_SURPRISE:sue 87, MOMENTUM:close 62, QUALITY:accruals 54, REVERSAL:close 36, TREND:close 33. Hybrid strategies come from two lineages. The library is therefore ~100 hypotheses represented by ~2,000 strategies, not 2,000 hypotheses; the Phase A4 effective number of independent family tests was about 28.

**Answer to E1:** the factory is mostly reproducing variants of a small set of well-known factors (momentum, earnings surprise, quality/accruals, value, reversal, trend, low volatility), as designed; it is not generating many economically distinct ideas, and 91 % of the documented ideas never reached a testable form. The sound step is to widen distinct lineages (E2 below), not to add parameter variants.

## E2. Scorecard (0 to 2 per dimension; ordering only)

Dimensions: **rationale** = economic rationale stated by the source; **literature** = independent literature support; **data** = data available at decision time; **bias** = survivorship / look-ahead exposure; **cost** = robustness to transaction costs (holding period); **distinct** = distinct from lineages already tested; **feasible** = feasible at the account size (long-only equities); **validation** = clean independent validation still possible.

### Highest-scoring lineages, with what they have shown so far (unscored)

| lineage | total / 16 | entries | strategies | rationale | literature | data | bias | cost | distinct | feasible | validation | as_is % | worst case % | fwd funds >= 20 trades |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| VALUE:earnings_yield | 11 | 9 | 5 | 1 | 0 | 1 | 2 | 2 | 1 | 2 | 2 | +1.17 | +0.44 | 0 |
| FUNDAMENTAL:piotroski_f | 11 | 2 | 2 | 1 | 0 | 1 | 2 | 2 | 1 | 2 | 2 | +1.61 | +0.99 | 0 |
| REVERSAL:market_cap | 11 | 2 | 2 | 1 | 0 | 2 | 2 | 1 | 1 | 2 | 2 | +0.36 | +0.11 | 0 |
| HYBRID:fcf_to_price | 11 | 1 | 1 | 1 | 0 | 1 | 2 | 2 | 1 | 2 | 2 | +1.47 | +0.85 | 0 |
| QUALITY:roa | 10 | 4 | 10 | 1 | 0 | 2 | 2 | 1 | 1 | 2 | 1 | +0.72 | +0.43 | 0 |
| FUNDAMENTAL:rd_to_assets | 10 | 3 | 9 | 1 | 0 | 1 | 2 | 2 | 1 | 2 | 1 | +3.01 | +2.86 | 0 |
| QUALITY:book_to_market | 10 | 3 | 2 | 1 | 0 | 1 | 2 | 1 | 1 | 2 | 2 | +1.31 | +1.03 | 0 |
| FUNDAMENTAL:cash_to_assets | 10 | 2 | 1 | 1 | 0 | 1 | 2 | 1 | 1 | 2 | 2 | +1.39 | +0.64 | 0 |
| MOMENTUM:vol_ratio | 10 | 2 | 2 | 1 | 0 | 2 | 0 | 2 | 1 | 2 | 2 | +1.15 | -1.31 | 0 |
| REVERSAL:returns | 10 | 2 | 1 | 1 | 0 | 1 | 2 | 1 | 1 | 2 | 2 | +0.19 | +0.44 | 0 |
| VALUE:debt_to_equity | 10 | 2 | 2 | 1 | 0 | 1 | 1 | 2 | 1 | 2 | 2 | -0.28 | -0.72 | 0 |
| VALUE:piotroski_f | 10 | 2 | 2 | 1 | 0 | 1 | 1 | 2 | 1 | 2 | 2 | +1.29 | +0.36 | 0 |
| FACTOR:asset_growth | 10 | 1 | 8 | 1 | 0 | 1 | 2 | 2 | 1 | 2 | 1 | +1.93 | +0.90 | 0 |
| FACTOR:market_cap | 10 | 1 | 1 | 1 | 0 | 1 | 2 | 1 | 1 | 2 | 2 | +0.59 | +0.04 | 0 |
| HYBRID:accruals | 10 | 1 | 8 | 1 | 0 | 1 | 2 | 2 | 1 | 2 | 1 | +1.19 | +0.68 | 0 |

### Why the top five were selected

- **VALUE:earnings_yield** (11/16): bias: 80% positive in the worst case; cost: median hold 42 sessions; feasible: long-only or long leg encodable; validation: 20 prior tests in this lineage.
- **FUNDAMENTAL:piotroski_f** (11/16): bias: 100% positive in the worst case; cost: median hold 41 sessions; feasible: long-only or long leg encodable; validation: 6 prior tests in this lineage.
- **REVERSAL:market_cap** (11/16): data: 50% of entries data-available; 2 strategies built; bias: 100% positive in the worst case; feasible: long-only or long leg encodable; validation: 8 prior tests in this lineage.
- **HYBRID:fcf_to_price** (11/16): bias: 100% positive in the worst case; cost: median hold 45 sessions; feasible: long-only or long leg encodable; validation: 8 prior tests in this lineage.
- **QUALITY:roa** (10/16): data: 50% of entries data-available; 10 strategies built; bias: 90% positive in the worst case; feasible: long-only or long leg encodable.

### Lowest-scoring lineages (deprioritised)

| lineage | total | main weaknesses |
|---|---:|---|
| MOMENTUM:price_above_sma200 | 7 | literature: 1 independent source(s); bias: 0% positive in the worst case; distinct: median cross-lineage correlation 0.80 |
| OTHER:roc_10 | 7 | literature: 1 independent source(s); bias: 0% positive in the worst case |
| SEASONALITY:cal_dom | 7 | literature: 1 independent source(s); bias: 0% positive in the worst case; cost: median hold 1 sessions |
| REVERSAL:close | 6 | literature: 1 independent source(s); distinct: median cross-lineage correlation 0.85; validation: 132 prior tests in this lineage |
| FUNDAMENTAL:book_to_market | 6 | rationale: practitioner source or no stated claim; literature: 1 independent source(s); bias: 0% positive in the worst case; distinct: median cross-lineage correlation 0.76 |
| MOMENTUM:close | 5 | literature: 1 independent source(s); bias: 8% positive in the worst case; distinct: median cross-lineage correlation 0.69; validation: 245 prior tests in this lineage |

### How the scorecard is to be used

1. It prioritises which lineage to specify and test next; it never promotes, ranks for capital, or changes a lifecycle state.
2. A new test starts from a pre-registered one-paragraph specification (hypothesis, rule, window, what would count as failure) in `experiment_registry`, not from a new batch of parameter variants.
3. Every market or window tried is added to the trial ledger, so the multiple-testing denominator stays honest.

## What could be wrong with this analysis

- Lineage assignment is the factory's own (keyword and rule based): two lineages may be one idea and one lineage several; lineage counts are an estimate of distinct hypotheses, not a count.
- The `bias` dimension uses the worst-case survivorship backtest as an exposure proxy, so the order is not independent of backtests; results are shown beside the score, not in it, for the other columns.
- Dimension scores are coarse thresholds on stored fields (stated in the code); they do not capture economic quality, which needs a reader.
- 'Specified before first evaluation' compares the provenance record time with the first stored metric date, at day resolution.
- Strategies of machine origin are one lineage by construction (`MACHINE:search`), so per-lineage figures for them are not comparable.
