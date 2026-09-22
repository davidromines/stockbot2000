# TASK-002

- component: data
- priority: high
- state: COMPLETE
- branch: ado/task-002
- created: 2026-09-22
- dependencies: none

## Objective
Create `fundamental_audit.py`, which verifies that every fundamental fact carries
the dates needed to answer "was this public on the decision date", and reports
where that information is missing.

## Background
Phase 6 section 7. A fundamental value may only be used when its available date
is at or before the decision date. The period end — when the quarter closed — is
NOT when the market knew, and using it is look-ahead. This project already lags
filings into daily_fundamentals, but nothing verifies the lag is present and
correct across the whole table, and nothing reports which periods are unsafe.

## Relevant files
- `fundamental_audit.py`
## Requirements
1. Import runtime as the first import, before pandas or numpy.
2. Read config via universe.load_config(); connect via storage.connect() using config["database"]["market_data_path"].
3. Report total rows in fundamentals and how many have a non-null filed date.
4. Report rows in fundamentals where filed is NULL — these cannot be used point-in-time at all.
5. Report the lag in days between period and filed for fundamentals: min, median, max, and the count where the lag is negative.
6. A NEGATIVE lag means a filing dated before the period it reports, which is impossible and indicates corrupt data. Report these separately and prominently.
7. Report total rows in daily_fundamentals and the min and max days_since_filing.
8. Report the count of daily_fundamentals rows where days_since_filing is negative or NULL. These are the look-ahead cases.
9. Report per-year coverage for fundamentals: year of filed, number of rows, number of distinct tickers.
10. Write machine-readable output to reports/fundamental_availability.json.
11. Write human-readable output to reports/fundamental_availability.md.
12. Create reports/ if absent. Provide main() and an --out-dir argument defaulting to reports.
13. Exit non-zero if any negative lag or negative days_since_filing is found, because those are correctness failures rather than statistics.

## Constraints
1. Do not modify any other file.
2. Read-only against the database. Do not write to any table.
3. Use aggregate SQL. Do not load fundamentals into pandas.
4. Dates are ISO YYYY-MM-DD TEXT, except fundamentals.filed which may be YYYYMMDD. Handle both.
5. Comments explain why, not what.

## Acceptance criteria
1. python fundamental_audit.py runs to completion.
2. reports/fundamental_availability.json exists and parses as JSON.
3. reports/fundamental_availability.md exists and is non-empty.
4. The JSON contains keys fundamentals_total, fundamentals_with_filed, fundamentals_missing_filed, negative_lag_count, daily_fundamentals_total, daily_negative_or_null_lag.
5. ./run_tests.sh still passes.

## Testing requirements
1. Runs against the real database without error.
2. fundamentals_with_filed + fundamentals_missing_filed == fundamentals_total.

## Deliverables
1. fundamental_audit.py
