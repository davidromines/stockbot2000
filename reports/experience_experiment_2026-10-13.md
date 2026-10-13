# Phase E3: historical-experience (similarity) experiment, baseline versus analog

Run 2026-10-13 06:35 UTC. Pre-registered as `analog_vs_baseline_2026_10` v1 (registered 2026-10-13T06:32:02+00:00); the spec is locked. Library 1,916,021 stock-days with known outcomes. All figures are net of 0.17 % round-trip cost, next-open entry, 20-session hold, top decile (50 of 500 random liquid names) per query date, query dates 20 sessions apart.

## Validation period (38 query dates, 2020-01-02 to 2022-12-08)

| method | mean net % per selected trade | 10th percentile of trades % | share of trades net positive | worst date % | dates with positive mean |
|---|---:|---:|---:|---:|---:|
| random | +0.55 | -12.87 | 51% | -23.98 | 50% |
| momentum | +0.57 | -15.19 | 49% | -22.03 | 47% |
| analog | +1.03 | -14.89 | 50% | -21.20 | 47% |
| model | +1.27 | -13.84 | 52% | -26.40 | 58% |

Difference in mean net return per trade, analog minus other (percentage points; 95 % bootstrap interval over query dates):

| versus | difference | interval |
|---|---:|---|
| random | +0.49 | -0.57 to +1.58 |
| momentum | +0.47 | -1.02 to +1.96 |
| model | -0.23 | -1.21 to +0.78 |

## Test period (47 query dates, 2023-01-09 to 2026-09-10)

| method | mean net % per selected trade | 10th percentile of trades % | share of trades net positive | worst date % | dates with positive mean |
|---|---:|---:|---:|---:|---:|
| random | +0.96 | -11.46 | 52% | -9.67 | 60% |
| momentum | +1.20 | -14.22 | 51% | -19.61 | 64% |
| analog | +1.44 | -12.60 | 52% | -12.14 | 57% |
| model | +0.92 | -12.51 | 52% | -13.98 | 60% |

Difference in mean net return per trade, analog minus other (percentage points; 95 % bootstrap interval over query dates):

| versus | difference | interval |
|---|---:|---|
| random | +0.48 | -0.18 to +1.21 |
| momentum | +0.24 | -0.87 to +1.34 |
| model | +0.52 | -0.33 to +1.43 |

## Power

In the test period the analog-minus-random difference averages +0.48 points with a standard deviation of 2.4 points across dates; detecting a difference that size at 95 % would take about 95 non-overlapping query dates (there are 47). The point estimates favour the analog method in both periods; the data cannot tell that from noise, and the same sample shows a basic model and a momentum rule are no more distinguishable from random. A larger replication is the only way to resolve it, and Stage P's much larger walk-forward (400,000 predictions) found AUC 0.523.

## Decision

**The analog method does not meet the pre-registered bar** in the test period (it must beat both the no-history baseline and the simple momentum rule with a 95 % lower bound above zero, and beat the model). Consistent with Stage P (walk-forward AUC 0.523 against 0.626 for the classifier). No subsystem is built; the experience-library idea is not expanded.

## What could be wrong with this analysis

- The 2023-onward window was already examined by Stage P's evaluation; this is a chronological test, not an unseen one.
- 500 random names per date and 200 neighbours from a 500,000-row sample of the library are choices made once, in advance; a larger pool or different feature weighting could behave differently (that is a different experiment).
- Library features are cross-sectional percentiles on a 5-session grid; they omit sector, breadth, maximum adverse excursion, gaps and intraday information the addendum lists as candidates.
- Gross outcomes are open to open; the single 0.17 % cost does not vary with liquidity or price.
- Where fundamentals were unavailable (early years) the percentile is a constant 0.5, which weakens the similarity method in those years.
