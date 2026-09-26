# TASK-039

- component: data
- priority: high
- state: IN_PROGRESS
- branch: ado/task-039
- created: 2026-09-26T06:30:00+00:00
- dependencies: none

## Objective
Create published_signals.py (Stage L1): import JKP Global Factor Data (US, monthly) and the Open Source Asset Pricing signal documentation into their own tables, and compute, for each of our strategy families that has a published counterpart, the survivorship-free long-leg return before and after publication; plus its regression test.

## Background
Files (already downloaded, never fetched by this module): data/jkp/pf_ew/[usa]_[all_factors]_[monthly]_[ew].csv and data/jkp/pf_vw/[usa]_[all_factors]_[monthly]_[vw_cap].csv with header location,name,pf,n,freq,weighting,date,ret (pf 1.0 low tercile, 2.0 middle, 3.0 high; ret a monthly fraction; date YYYY-MM-DD month end; 1926-2025); data/jkp/ls_vw/[usa]_[all_factors]_[monthly]_[vw_cap].csv with header location,name,freq,weighting,direction,n_stocks,n_stocks_min,date,ret (the long-short factor; direction +1 means the HIGH tercile is the long leg, -1 the LOW tercile); data/jkp/mkt/[usa]_[mkt]_[monthly]_[vw_cap].csv (same header as ls, name "mkt": the US market return); data/osap/SignalDoc.csv (columns include Acronym, Authors, Year, Journal, SampleStartYear, SampleEndYear, Return, T-Stat, LongDescription). These data include delisted companies (CRSP-based): they are the survivorship-free evidence this project otherwise lacks. FAMILY_MAP (family -> (jkp factor name, OSAP acronym)): value_book -> ("be_me", "BM"); earnings_yield -> ("ni_me", "EP"); profitability -> ("gp_at", "GP"); quality_roa -> ("niq_at", "roaq"); quality_piotroski -> ("f_score", "PS"); low_investment -> ("at_gr1", "AssetGrowth"); low_accruals -> ("oaccruals_at", "Accruals"); buyback -> ("chcsho_12m", "ShareIss1Y"); liquidity_premium -> ("ami_126d", "Illiquidity"); small_cap -> ("market_equity", "Size"); xs_momentum -> ("ret_12_1", "Mom12m"); seasonality_12m -> ("seas_1_1an", "MomSeason"); breakout_52w -> ("prc_highprc_252d", "High52"); rsi_reversion -> ("ret_1_0", "STreversal"); low_volatility -> ("ivol_capm_252d", "IdioVol3F"); balance_sheet -> ("o_score", "OScore"). The long leg pf is 3 if the factor's direction is +1 else 1 (read from the ls file; the most frequent direction value for that factor). Publication year = SignalDoc Year for the acronym. "pre" = months in years <= SampleEndYear (in-sample), "post" = months in years > publication Year (out of sample, after publication), "gap" = the years between (excluded from both).

## Relevant files
- `published_signals.py`
- `tests/regression/test_published_signals.py`
## Requirements
1. init(conn) creates published_signals(source TEXT, signal TEXT, acronym TEXT, authors TEXT, year INTEGER, sample_start INTEGER, sample_end INTEGER, op_return REAL, op_tstat REAL, description TEXT, direction INTEGER, PRIMARY KEY (source, signal)), published_returns(source TEXT, signal TEXT, leg TEXT, weighting TEXT, date TEXT, ret REAL, n INTEGER, PRIMARY KEY (source, signal, leg, weighting, date)) where leg is 'pf1', 'pf2', 'pf3', 'ls' or 'mkt', and published_evidence(family TEXT, signal TEXT, weighting TEXT, period TEXT, months INTEGER, mean_long REAL, mean_mkt REAL, mean_excess REAL, tstat_excess REAL, mean_ls REAL, computed_at TEXT, PRIMARY KEY (family, signal, weighting, period)).
2. load_jkp(conn, base="data/jkp") reads the four JKP files with pandas and INSERT OR REPLACEs their rows (all 153 factors) into published_returns (source 'jkp'), and one published_signals row per JKP factor with its direction; returns row counts. load_osap_doc(conn, path="data/osap/SignalDoc.csv") fills acronym, authors, year, sample_start, sample_end, op_return, op_tstat, description onto the published_signals rows of the mapped JKP factors (per FAMILY_MAP) and also inserts one row per SignalDoc acronym with source 'osap'.
3. evidence(conn) computes, for every FAMILY_MAP entry and each weighting in ('ew', 'vw_cap'), for period in ('pre', 'post', 'all'): months, mean monthly long-leg return, mean monthly market return (the mkt series; vw_cap for both weightings), mean excess (long minus market, month by month), its t-statistic (mean / (sd / sqrt(months))), and the mean long-short return; stores the rows in published_evidence (INSERT OR REPLACE) and returns them as a list of dicts.
4. render(rows) returns a text table with one line per family and weighting for period 'post': family, JKP signal, publication year, months, long-leg excess per month in percent (2 decimals), its t-stat (2 decimals), and the pre-publication excess for comparison.
5. main(argv=None) with --load, --evidence, --report; connect with sqlite3.connect(load_config()["database"]["market_data_path"]) (from universe import load_config). Import runtime first.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else. No network.
2. The test writes small synthetic CSV files in a tempfile directory with exactly the headers above and uses sqlite3.connect(":memory:"); it never opens data/market_data.db or the real downloads.
3. Keep published_signals.py under 260 lines and the test under 200 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_published_signals.py exits 0.
2. The test checks: load_jkp stores pf1/pf2/pf3, ls and mkt rows; a factor with direction -1 uses pf1 as its long leg and one with +1 uses pf3; pre/post/gap split follows SampleEndYear and Year (a month in a gap year is in neither pre nor post); mean_excess equals the month-by-month mean of long minus market on a hand-computed example; tstat_excess matches mean/(sd/sqrt(n)); load_osap_doc attaches the paper year to a mapped factor.
3. At least 8 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
