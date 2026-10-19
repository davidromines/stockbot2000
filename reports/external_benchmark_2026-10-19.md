# External benchmark vs JKP — 2026-10-19

Our tercile portfolios (equal-weighted, next-month returns) against JKP's published US series, 2010-01 to 2024-12. The spread (top minus bottom tercile) is the test; raw tercile correlations mostly measure the market.

| signal | months | names / month | corr top tercile | corr bottom | **corr spread** | mean spread ours | mean spread JKP | verdict |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| ret_12_1 | 179 | 1887 | 0.98 | 0.96 | **0.86** | +0.54% | +0.72% | partial: investigate |
| be_me | 180 | 1423 | 0.93 | 0.99 | **0.73** | +0.45% | +0.31% | partial: investigate |

Deviations from JKP: our universe (survivors over-represented), >= $5 and >= $1M/day at formation, all-stock breakpoints, equal weights, adjusted month-end closes. Pass marks stated before running: >= 0.9 faithful, 0.6-0.9 investigate, < 0.6 differs materially. Read-only.
