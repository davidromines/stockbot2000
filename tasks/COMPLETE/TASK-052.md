# TASK-052

- component: data
- priority: high
- state: COMPLETE
- branch: ado/task-052
- created: 2026-09-27T19:30:00+00:00
- dependencies: TASK-049

## Objective
Create edgar_form4.py: a daily feed of Form 4 insider transactions straight from EDGAR, so the insider-buying signal is current instead of lagging up to a quarter behind the SEC's quarterly data sets (insider.py). It writes into the same insider_trades table; when a quarter's official data set is imported, the daily rows for that quarter's accessions are replaced by the official ones. Plus its regression test.

## Background
insider.py (existing; do not modify) owns: insider_trades(accession TEXT, trans_sk TEXT, owner_cik TEXT, ticker TEXT, issuer_cik TEXT, trans_date TEXT, filing_date TEXT, code TEXT, shares REAL, price REAL, value_usd REAL, relationship TEXT, PRIMARY KEY(accession, trans_sk, owner_cik)); insider.init(conn); insider.UA (User-Agent string); dates ISO 'YYYY-MM-DD'; relationship text containing 'Director' / 'Officer' / 'TenPercentOwner' comma-separated.
EDGAR daily form index: https://www.sec.gov/Archives/edgar/daily-index/{YYYY}/QTR{q}/form.{YYYYMMDD}.idx (404 on days with no index, e.g. weekends). After a header ending with a line of dashes, each line is fixed-width: form type, company name, CIK, date filed (YYYYMMDD), file name (e.g. edgar/data/1555279/0001535264-26-000053.txt). Form 4 lines start with "4 " (also "4/A "). Each filing text at https://www.sec.gov/Archives/{file name} contains an XML document between <XML> and </XML> whose root is <ownershipDocument> with: issuer/issuerCik, issuer/issuerTradingSymbol; one or more reportingOwner blocks with reportingOwnerId/rptOwnerCik and reportingOwnerRelationship/isDirector, isOfficer, isTenPercentOwner, isOther (values "1"/"true"/"0"/"false"); nonDerivativeTable/nonDerivativeTransaction blocks with transactionDate/value, transactionCoding/transactionCode, transactionAmounts/transactionShares/value, transactionPricePerShare/value, transactionAmounts/transactionAcquiredDisposedCode/value. The accession is the file name's last part without ".txt". SEC asks for at most 10 requests per second and the User-Agent header on every request.

## Relevant files
- `edgar_form4.py`
- `tests/regression/test_edgar_form4.py`
## Requirements
1. init(conn): insider.init(conn); CREATE TABLE IF NOT EXISTS form4_daily_log(day TEXT PRIMARY KEY, filings INTEGER, rows INTEGER, fetched_at TEXT, note TEXT).
2. parse_index(text) -> list of dicts {form, cik, filed (ISO), path, accession} for lines whose form is "4" or "4/A" (skip header lines until the dashed line).
3. parse_form4(xml_text, accession, filed_iso) -> list of insider_trades row dicts, one per (nonDerivativeTransaction with code P or S) x (reporting owner): trans_sk = "d" + transaction index within the document (e.g. "d0", "d1"; the "d" marks a daily-feed row), ticker upper-cased/stripped, relationship = comma-joined of Director/Officer/TenPercentOwner/Other for flags that are true, value_usd = shares*price (None if either missing). Use xml.etree.ElementTree; tolerate missing optional elements; return [] for unparseable XML or an empty ticker.
4. extract_xml(filing_text) -> str | None: the text between the first <XML> and </XML> (case-insensitive), stripped.
5. fetch_day(conn, day_iso, get=None) -> dict: get(url) -> (status, text) (default: requests with insider.UA, 0.12 s sleep after each request); fetch the day's index, then every Form 4 filing, parse, INSERT OR IGNORE rows into insider_trades, log the day in form4_daily_log; a 404 index logs filings 0 with note "no index"; a failing filing is skipped and counted in note. Returns {"day", "filings", "rows"}.
6. run(conn, days=5, today=None, get=None) -> list: fetch_day for each of the last `days` calendar days (today excluded) not yet logged with filings > 0 — weekends simply log "no index".
7. reconcile(conn) -> int: delete daily-feed rows (trans_sk LIKE 'd%') whose accession also has official rows (trans_sk NOT LIKE 'd%') — the official quarterly data set wins; returns rows deleted.
8. main(argv=None): --daily [--days 5] (run then reconcile), --backfill FROM TO (every day in the ISO range), --status. Import runtime first; sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60) with from universe import load_config inside main; import insider inside functions.

## Constraints
1. Create ONLY edgar_form4.py and tests/regression/test_edgar_form4.py. Modify nothing else.
2. edgar_form4.py under 230 lines; test under 170 lines. Standard library + requests only.
3. The test never touches the network or the real database: a fake get() serves a small index text and two filing texts (one with two reporting owners and one P and one A-code transaction; one with a malformed XML); in-memory sqlite3.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_edgar_form4.py exits 0.
2. The test checks: parse_index keeps only 4 and 4/A lines with ISO dates and accessions; extract_xml finds the XML block; parse_form4 yields one row per P/S transaction per owner (the A-code row dropped), relationship "Director" / "Officer" from the flags, value_usd = shares*price, trans_sk starting with "d"; fetch_day stores rows, logs the day, and skips the malformed filing without raising; a second fetch_day adds nothing (INSERT OR IGNORE); run skips an already-logged day; reconcile deletes a daily row when an official row with the same accession exists and keeps it otherwise; a 404 index logs "no index".
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
