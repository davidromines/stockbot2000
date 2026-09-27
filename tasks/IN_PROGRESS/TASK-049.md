# TASK-049

- component: data
- priority: high
- state: IN_PROGRESS
- branch: ado/task-049
- created: 2026-09-27T17:20:00+00:00
- dependencies: none

## Objective
Create insider.py: load SEC Form 4 insider transactions (the SEC's quarterly "Insider Transactions Data Sets", 2006 onward) and attach point-in-time insider-buying columns to the daily panel, including Cohen, Malloy & Pomorski (2012) "opportunistic" buying (routine traders excluded). Plus its regression test.

## Background
Each quarter is a zip at https://www.sec.gov/files/structureddata/data/insider-transactions-data-sets/{YYYY}q{N}_form345.zip (2006q1 to the current quarter; a quarter not yet published returns HTTP 404). Requests must send the header User-Agent: "stockbot2000 research davidromines@gmail.com" and stay under 10 requests/second. Each zip holds tab-separated files with a header row; the ones needed:
SUBMISSION.tsv: ACCESSION_NUMBER, FILING_DATE (e.g. 31-JAN-2024), DOCUMENT_TYPE ('4', '4/A', '3', '5', ...), ISSUERCIK, ISSUERTRADINGSYMBOL.
NONDERIV_TRANS.tsv: ACCESSION_NUMBER, NONDERIV_TRANS_SK, SECURITY_TITLE, TRANS_DATE (15-NOV-2022), TRANS_CODE ('P' open-market purchase, 'S' open-market sale, others), TRANS_SHARES, TRANS_PRICEPERSHARE, TRANS_ACQUIRED_DISP_CD ('A' or 'D').
REPORTINGOWNER.tsv: ACCESSION_NUMBER, RPTOWNERCIK, RPTOWNERNAME, RPTOWNER_RELATIONSHIP (text such as 'Director', 'Officer', 'TenPercentOwner', or several comma-separated).
Point in time: the data sets carry only a filing DATE, not an acceptance time, so a filing is first usable on the first trading session strictly AFTER its FILING_DATE. Panels use (ticker, date) with ISO date strings; frames passed to attach() carry string columns _t (ticker) and _d (ISO date).

## Relevant files
- `insider.py`
- `tests/regression/test_insider.py`
## Requirements
1. Constants: URL template, UA string above, DATA_DIR = Path("data/insider"), WINDOW_DAYS = 90, ROUTINE_YEARS = 3.
2. init(conn): CREATE TABLE IF NOT EXISTS insider_trades(accession TEXT, trans_sk TEXT, owner_cik TEXT, ticker TEXT, issuer_cik TEXT, trans_date TEXT, filing_date TEXT, code TEXT, shares REAL, price REAL, value_usd REAL, relationship TEXT, PRIMARY KEY(accession, trans_sk, owner_cik)); CREATE TABLE IF NOT EXISTS insider_fetch_log(quarter TEXT PRIMARY KEY, status INTEGER, rows INTEGER, fetched_at TEXT).
3. quarters(start="2006q1", end=None) -> list of 'YYYYqN' strings from start to end (default: the current quarter, from today's UTC date).
4. fetch(quarter, session=None) -> Path | None: download to DATA_DIR/{quarter}_form345.zip unless it already exists; on 404 return None; sleep 0.2 s after each request; use requests.
5. parse_zip(path) -> DataFrame with the insider_trades columns: rows of NONDERIV_TRANS with TRANS_CODE in ('P','S'), joined to SUBMISSION on ACCESSION_NUMBER (DOCUMENT_TYPE in ('4','4/A') only) and to REPORTINGOWNER on ACCESSION_NUMBER (one row per owner); ticker = ISSUERTRADINGSYMBOL upper-cased and stripped (rows with an empty ticker dropped); dates converted to ISO 'YYYY-MM-DD' (format '%d-%b-%Y'; unparseable dropped); value_usd = shares * price (NaN when either is missing); relationship = RPTOWNER_RELATIONSHIP. Read the tsv files with pandas (sep='\t', dtype=str, quoting=3, on_bad_lines='skip').
6. import_quarter(conn, quarter) -> int: fetch + parse + INSERT OR REPLACE into insider_trades; write insider_fetch_log; returns rows. run(conn, start="2006q1", refresh_last=2) imports every quarter not yet logged with status 200, plus always re-imports the newest `refresh_last` quarters (the current quarter's file grows).
7. purchases(conn, tickers=None) -> DataFrame of code 'P' rows whose relationship mentions 'Director' or 'Officer' (case-insensitive) and value_usd > 0, with a boolean column routine: an owner-ticker purchase is routine when the same owner traded (code P or S) that ticker in the same calendar month in EACH of the ROUTINE_YEARS prior calendar years; opportunistic = not routine.
8. first_tradeable(filing_dates, sessions) -> list: for each ISO filing date, the first session in the sorted session list strictly after it (None when none).
9. attach(conn, df) -> df with three float32 columns: insider_buy_usd_90 (sum of purchase value_usd), insider_buyers_90 (number of distinct owners who bought), opp_buyers_90 (distinct opportunistic buyers), each over purchases whose first tradeable session is in (date - WINDOW_DAYS calendar days, date]. Sessions come from SELECT DISTINCT date FROM prices WHERE ticker='SPY'. Rows with no purchase in the window get 0.0 for the dollar sum and 0.0 counts ONLY when the ticker has any insider_trades row at all (the company files Form 4s); tickers never seen in insider_trades get NaN. When the insider_trades table does not exist, all three columns are NaN. Must be efficient for 1M+ frame rows: work per ticker on sorted arrays (numpy searchsorted), not a Python loop over frame rows.
10. main(argv=None): --fetch [--start 2006q1] (run), --daily (run with only the newest two quarters refreshed and nothing else re-fetched), --status (quarters logged, rows, purchase rows, newest filing_date). Import runtime first; from universe import load_config; logging INFO.

## Constraints
1. Create ONLY insider.py and tests/regression/test_insider.py. Modify nothing else.
2. insider.py under 260 lines; test under 170 lines. pandas, numpy, requests only.
3. The test never touches the network or the real database: build a small zip in a temp dir with the three tsv files (write them with the exact header names above) and an in-memory sqlite3 connection with a prices table holding SPY sessions.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_insider.py exits 0.
2. The test checks: parse_zip keeps P and S from Form 4 and drops a Form 3 row, an 'A'-code (grant) row and a row with an empty ticker; dates become ISO; value_usd = shares*price; one row per owner when a filing has two owners; purchases() excludes a TenPercentOwner-only buyer; routine is True for an owner who traded the ticker in the same month in each of the 3 prior years and False when one year is missing; first_tradeable skips the filing date itself (a filing on a session date is usable the NEXT session); attach gives the purchase on its first tradeable session and not the session before, drops it after 90 calendar days, counts two distinct buyers as 2, gives 0.0 for a Form-4 filer with no recent buys and NaN for a ticker never seen; attach without the table gives NaN columns.
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
