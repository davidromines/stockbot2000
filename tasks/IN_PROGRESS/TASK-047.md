# TASK-047

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-047
- created: 2026-09-27T05:30:00+00:00
- dependencies: none

## Objective
Create analog_eval.py: the walk-forward test of the analog forecaster (analog.py, Stage P2) — does the share of past analogs that rose predict whether a stock rises, year by year, and does it beat the existing XGBoost classifier on the same stock-days? Plus its regression test.

## Background
analog.py (read it; do not modify it) provides: COLS (feature column names), H = 20, load_library() -> DataFrame with columns ticker, date (ISO str), COLS..., entry_date, exit_date (ISO str or None), fwd_ret (float, NaN when unknown); forecast(lib, queries, as_of, k) -> DataFrame with ticker, date, n, p_up, mean, median, q10, q90, avg_distance for each query row, using ONLY library rows whose exit_date <= as_of (point in time). A library row is itself a query candidate: its fwd_ret is what really happened next. The XGBoost classifier's out-of-sample predictions are in table oos_predictions(ticker, date, fold, score, label) where label = 1 if the stock rose enough over its horizon and score is its predicted probability x 100; ranking skill is compared with AUC on the same (ticker, date) rows. sklearn.metrics.roc_auc_score is available.

## Relevant files
- `analog_eval.py`
- `tests/regression/test_analog_eval.py`
## Requirements
1. evaluate(lib, query_dates, k=200, lib_sample=None, seed=7) -> dict: for each date in query_dates, queries = lib rows on that date with fwd_ret known; forecast(pool, queries, date, k) where pool = lib (optionally a fixed random sample of lib_sample rows, same seed); collect per query row: ticker, date, p_up, mean, fwd_ret.
2. The returned dict has "overall" and "by_year" (year -> same keys): n (rows), auc (roc_auc_score of p_up against fwd_ret > 0; None if one class only), top_decile_ret (mean fwd_ret of rows whose p_up is in the top 10% of THAT date), all_ret (mean fwd_ret of all rows), spread (top_decile_ret - all_ret), and hit_top (share of top-decile rows with fwd_ret > 0).
3. compare_xgb(conn, rows) -> dict: join the evaluated rows to oos_predictions on (ticker, date); on the matched rows only, auc_analog (p_up vs label) and auc_xgb (score vs label) and n_matched; empty dict when the table is missing or nothing matches.
4. query dates: monthly_dates(lib, start="2010-01-01") returns the first library date of each calendar month from start.
5. main(argv=None) with --run [--start 2010-01-01] [--k 200] [--sample 400000]: loads the library, evaluates on monthly dates, compares with XGBoost (sqlite3.connect(load_config()["database"]["market_data_path"]) read-only via "file:...?mode=ro", uri=True), writes data/analog/eval.json, prints a table: year, n, auc, spread (+x.xx%), hit_top, then an overall line and the XGBoost comparison line. Import runtime first; from universe import load_config.

## Constraints
1. Create ONLY analog_eval.py and tests/regression/test_analog_eval.py. Modify nothing else.
2. The test builds a synthetic library in memory (no database, no files): at least 4 query dates, 60+ tickers per date, COLS filled with random numbers, where a hidden feature (use COLS[0]) drives fwd_ret (fwd_ret = 0.1*(COLS[0]-0.5) + small noise) so analogs have real skill, entry_date/exit_date set so earlier rows are known by later dates; call evaluate with k=20.
3. Keep analog_eval.py under 180 lines and the test under 150 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_analog_eval.py exits 0.
2. The test checks: evaluate returns overall and by_year with every key in requirement 2; on the synthetic library with real skill the overall auc > 0.6 and spread > 0; no query row is scored with an analog whose exit_date is after the query date (check by calling forecast directly on a date where the only earlier rows have later exit dates: it returns an empty frame); monthly_dates returns one date per month; compare_xgb returns {} on a connection with no oos_predictions table and matches rows when given an in-memory oos_predictions table.
3. At least 6 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
