# TASK-048

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-048
- created: 2026-09-27T17:00:00+00:00
- dependencies: none

## Objective
Create composite.py: the Stage S multi-signal composite. Combine eight weak stock signals into one score per stock per day, weighted by each signal's recent out-of-sample information coefficient (IC) with a covariance correction so signals that repeat each other do not double-count (Kakushadze & Yu 2016). Point in time throughout. Plus its regression test.

## Background
The daily panel is built by storage.load_training_frame(conn, feature_cols, types=..., start_date=..., end_date=..., min_price=..., min_dollar_volume=...) which returns a DataFrame with columns ticker (categorical), date (ISO str 'YYYY-MM-DD'), close (float, split/dividend adjusted), and the feature_cols; then storage.attach_fundamentals(conn, df) adds float columns including book_to_market, earnings_yield, fcf_to_price, gross_profitability, sue, short_volume_ratio_20, analog_p_up (NaN where unknown; never fill NaN with 0). cfg = universe.load_config(); cfg["universe"]["tradeable_types"], cfg["risk"]["min_price"], cfg["risk"]["min_dollar_volume"], cfg["database"]["market_data_path"]. Do not import storage or universe at module top level (import inside build/main) so the test can run without the database.

## Relevant files
- `composite.py`
- `tests/regression/test_composite.py`
## Requirements
1. SIGNALS = dict name -> sign: book_to_market +1, earnings_yield +1, fcf_to_price +1, gross_profitability +1, mom_9_1 +1, sue +1, analog_p_up +1, short_volume_ratio_20 -1. HORIZON = 20 (sessions). LOOKBACK = 252 (sessions of IC used for weights). MIN_SIGNALS = 3. RIDGE = 0.5.
2. add_momentum(df) -> df with mom_9_1 = close shifted 21 sessions / close shifted 210 sessions - 1, computed per ticker in date order (groupby ticker, shift); NaN when history is short.
3. add_forward(df, horizon=HORIZON) -> df with fwd_ret = close shifted -horizon / close - 1 per ticker (NaN at the end).
4. cross_ranks(df) -> DataFrame (same index) with one column per SIGNALS name: per date, percentile rank (rank(pct=True)) of sign*value minus 0.5, so ranks lie in (-0.5, 0.5]; NaN stays NaN; a signal column missing from df gives an all-NaN column.
5. daily_ic(df, ranks) -> DataFrame indexed by date (sorted), one column per signal: per date, Spearman correlation between the signal rank and fwd_ret over rows where both are present; NaN when fewer than 30 such rows.
6. weights(ic, horizon=HORIZON, lookback=LOOKBACK, ridge=RIDGE) -> DataFrame indexed like ic, one column per signal. For the row at position t use ONLY ic rows at positions <= t - horizon - 1 (an IC at date d is known only after its forward return has closed), the last `lookback` of those; mu = column means (skip NaN), S = covariance of those rows (pandas cov, min_periods=20) with NaN entries set to 0 and diagonal NaN set to the column variance or 1e-4; w = solve(S + ridge * diag(diag(S)) + 1e-8*I, mu) over signals with non-NaN mu; negative weights set to 0; divide by the sum. If the sum is 0 or fewer than 60 usable ic rows exist, the whole row is NaN.
7. composite_scores(df, ranks, w) -> DataFrame with ticker, date, composite, n_signals: per row, sum over signals of w[date, s] * rank[s] where rank is present and weight > 0, divided by the sum of those weights; n_signals = count of signals used; composite NaN when n_signals < MIN_SIGNALS or the date's weights are NaN.
8. init(conn): CREATE TABLE IF NOT EXISTS daily_composite(ticker TEXT, date TEXT, composite REAL, n_signals INTEGER, PRIMARY KEY(ticker, date)) and composite_ic(date TEXT, signal TEXT, ic REAL, PRIMARY KEY(date, signal)) and composite_weights(date TEXT, signal TEXT, weight REAL, PRIMARY KEY(date, signal)).
9. build(conn, cfg, start="2008-01-01", end=None, chunk_years=1): pass 1, year by year from start to end (default MAX(date) in prices): load the panel from (chunk start - 330 calendar days) to (chunk end + 45 calendar days) with feature_cols ["roc_10"], attach fundamentals, add_momentum, add_forward, cross_ranks, daily_ic; keep only IC dates inside the chunk; INSERT OR REPLACE into composite_ic. Then read ALL composite_ic, compute weights, INSERT OR REPLACE composite_weights (skip NaN). Pass 2, year by year again: load the panel (330-day warmup, no forward extension), ranks, composite_scores for dates inside the chunk using the stored weights, INSERT OR REPLACE daily_composite (skip NaN composite). Commit after each chunk. Log progress with logging. Return {"ic_dates": n, "weight_dates": n, "rows": n}.
10. update(conn, cfg): the daily increment. Rebuild the chunk from (MAX(date) in composite_ic minus 60 calendar days) to the newest price date with the same two passes (pass 1 only for that range, weights recomputed from all stored IC, pass 2 for dates after MAX(date) in daily_composite minus 5 days). Idempotent.
11. attach(conn, df) -> df: adds composite (float32) to a frame that has _t (ticker str) and _d (date str) columns by an exact left merge on daily_composite for the frame's date range and tickers (query in chunks of 900 tickers); when the table does not exist add an all-NaN composite column.
12. main(argv=None): --build [--start], --update, --status (prints IC mean per signal over the last 252 IC dates and the newest weights). Import runtime first; logging.basicConfig INFO.

## Constraints
1. Create ONLY composite.py and tests/regression/test_composite.py. Modify nothing else.
2. composite.py under 280 lines; test under 170 lines. Use numpy/pandas only (no scipy, no sklearn).
3. Never fill a missing signal with 0 or a mean; missing stays NaN and is excluded.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed. The test uses synthetic in-memory DataFrames and an in-memory sqlite3 connection only.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_composite.py exits 0.
2. The test builds a synthetic panel of 80 tickers x 400 sessions with all eight signal columns random, except that book_to_market drives fwd_ret (make close follow a random walk whose next-20-session return is 0.05*(book_to_market rank - 0.5) + noise), and short_volume_ratio_20 drives it NEGATIVELY; it checks: cross_ranks are within (-0.5, 0.5] and NaN is preserved; daily_ic of book_to_market has mean > 0.1 and short_volume_ratio_20 (after its -1 sign) mean > 0; weights at a row use no IC from the last horizon+1 dates (change the IC values of those rows and the weight row is unchanged); weights are >= 0 and sum to 1 where not NaN; the first rows (fewer than 60 usable IC rows) are NaN; composite_scores gives NaN when fewer than 3 signals are present; the composite's own IC on the later half is > 0; init + attach round-trip on an in-memory db returns the stored composite and NaN for a missing row; attach on a db without the table returns an all-NaN composite column.
3. At least 9 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
