# TASK-045

- component: data
- priority: high
- state: TODO
- branch: ado/task-045
- created: 2026-09-26T09:30:00+00:00
- dependencies: none

## Objective
Create sue_features.py: standardized unexpected earnings (SUE) per quarterly filing, matched to the SAME fiscal quarter a year earlier by period date, scaled by the volatility of PRIOR surprises only, and projected point-in-time onto a daily table daily_sue(ticker, date, sue, sue_age); plus its regression test.

## Background
pead.py's build_sue compared each filing with the one four rows earlier, which silently compares the wrong quarters whenever a quarter is missing (10-Ks often report no qtrs=1 EPS), and its denominator included the current surprise. Data: sec_filings(adsh, cik, ticker, form, period, filed, ...) where period and filed are YYYYMMDD text (period = fiscal period end); sec_facts(adsh, tag, ddate, qtrs, value): quarterly basic EPS is tag 'EarningsPerShareBasic' with qtrs = 1 (if a filing has several such rows, use the one whose ddate is the latest). Rules: for each ticker, quarterly EPS observations (form in 10-Q, 10-K, 10-Q/A, 10-K/A; for amendments keep only the latest filing per (ticker, period)); the year-ago observation of a quarter with period P is the same ticker's observation whose period is between P - 380 days and P - 350 days (the closest to P - 365 days if several); delta = eps - eps_year_ago; sd = the sample standard deviation of that ticker's PREVIOUS deltas (by period order, excluding the current one), using at most the last 8 and at least 4 (fewer -> no SUE); sue = delta / sd (no SUE when sd is 0 or missing). Availability: a SUE is usable from filed + LAG_DAYS calendar days (import fundamental_features and use ff.LAG_DAYS), as-of joined backwards onto that ticker's trading dates from prices(ticker, date, ...) with date >= "2009-01-01"; sue_age = calendar days from filed to the date; rows with sue_age > MAX_AGE_DAYS (63) are not written, so a stale surprise never looks fresh. daily_sue(ticker TEXT, date TEXT, sue REAL, sue_age INTEGER, PRIMARY KEY (ticker, date)).

## Relevant files
- `sue_features.py`
- `tests/regression/test_sue_features.py`
## Requirements
1. quarterly_eps(conn, tickers=None) returns a DataFrame (ticker, period, filed, eps) following the Background (latest amendment per (ticker, period); latest ddate per filing).
2. compute_sue(eps_df) returns (ticker, period, filed, eps, delta, sue) per the Background rules, only rows with a SUE.
3. init(conn) creates daily_sue; project(conn, sue_df, start="2009-01-01") INSERT OR REPLACEs daily rows per the availability rule and returns the count; build(conn, tickers=None) runs all three in ticker batches of 500 (memory), committing per batch, and returns {"tickers", "surprises", "daily_rows"}.
4. main(argv=None) with --build and --coverage (count of daily_sue rows and distinct tickers, and the share of 2016-2019 price rows that have a SUE); connect with storage.connect(load_config()["database"]["market_data_path"]) (from universe import load_config). Import runtime first; pandas and numpy allowed.

## Constraints
1. Create ONLY sue_features.py and tests/regression/test_sue_features.py. Do not modify pead.py or any other file.
2. No network; the test uses sqlite3.connect(":memory:") with hand-made sec_filings, sec_facts and prices tables; never opens data/market_data.db.
3. Keep sue_features.py under 240 lines and the test under 180 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_sue_features.py exits 0.
2. The test checks: with a MISSING quarter in the series, a quarter is still compared with the same quarter a year earlier (period-date match), not with the observation four rows back; an amended filing replaces the original for its period; the standard deviation uses only previous deltas (changing the current delta does not change sd); fewer than 4 prior deltas -> no SUE; nothing is available before filed + LAG_DAYS; sue_age counts calendar days from filed; rows older than 63 days are not written.
3. At least 8 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
