# TASK-053

- component: data
- priority: medium
- state: IN_PROGRESS
- branch: ado/task-053
- created: 2026-09-27T21:00:00+00:00
- dependencies: none

## Objective
Create congress_trades.py (Stage O-pol): load US House members' Periodic Transaction Reports (STOCK Act disclosures) from the House Clerk's official public files, 2013 onward, parse each report's trades, and attach point-in-time "politician buying" columns to the daily panel. Plus its regression test.

## Background
Yearly index: https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{YEAR}FD.zip containing {YEAR}FD.xml with <Member> elements: Prefix, Last, First, Suffix, FilingType (P = periodic transaction report; others ignored), StateDst, Year, FilingDate (M/D/YYYY — the day the report became public), DocID. Report PDF: https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{YEAR}/{DocID}.pdf. Electronically filed reports have 8-digit DocIDs starting with "2" and contain extractable text; others are scanned images and are skipped (logged). Requests must send User-Agent "stockbot2000 research davidromines@gmail.com"; sleep 0.2 s after each request. Text via pypdf: "".join(page.extract_text() for page in PdfReader(BytesIO(content)).pages). A trade in the text looks like (whitespace and line breaks may split it anywhere between tokens):
"SP Albemarle Corporation (ALB) [ST] S 12/21/2023 01/08/2024 $1,001 - $15,000"
"SP Charles Schwab Corporation (SCHW)\n[ST]\nP 12/14/2023 01/08/2024 $50,001 -\n$100,000"
Pattern: optional owner code (SP, JT, DC or none) then asset name, then a ticker in parentheses, then an asset type in brackets ([ST] stock; others like [OP] options, [GS] bonds are kept but flagged), then transaction type P, S, "S (partial)" or E (exchange), transaction date MM/DD/YYYY, notification date MM/DD/YYYY, amount range "$a - $b" (or "Over $50,000,000" -> lo only). Panels use (ticker, date) with ISO date strings; frames passed to attach() carry string columns _t (ticker) and _d (ISO date).

## Relevant files
- `congress_trades.py`
- `tests/regression/test_congress_trades.py`
## Requirements
1. init(conn): CREATE TABLE IF NOT EXISTS congress_trades(doc_id TEXT, seq INTEGER, member TEXT, state_dst TEXT, owner TEXT, ticker TEXT, asset_type TEXT, txn_type TEXT, txn_date TEXT, notif_date TEXT, filed_date TEXT, amount_lo REAL, amount_hi REAL, PRIMARY KEY(doc_id, seq)); CREATE TABLE IF NOT EXISTS congress_docs(doc_id TEXT PRIMARY KEY, year INTEGER, member TEXT, state_dst TEXT, filed_date TEXT, status TEXT, trades INTEGER, fetched_at TEXT).
2. parse_index(xml_text) -> list of dicts {doc_id, year, member ("First Last"), state_dst, filed_date (ISO)} for FilingType P only.
3. parse_trades(text) -> list of dicts {seq, owner, ticker, asset_type, txn_type ("P", "S", "S (partial)", "E"), txn_date (ISO), notif_date (ISO), amount_lo, amount_hi}: normalise all whitespace to single spaces first, then one regex over the whole text; seq is the match order; tickers upper-case; amounts parsed from "$1,001 - $15,000" (hi None for "Over $x").
4. fetch_year(conn, year, get=None) -> dict: get(url) -> (status, bytes) (default requests + UA + 0.2 s sleep); download the year's index, and for each P filing not yet in congress_docs with status 'ok' or 'skipped': skip non-electronic DocIDs (status 'skipped'), else fetch, extract text, parse, INSERT OR REPLACE trades (member, state_dst, filed_date from the index), record congress_docs (status 'ok' with the trade count, or 'error' with 0 on a failed fetch/parse — never raises). Returns {"year", "reports", "ok", "skipped", "errors", "trades"}.
5. run(conn, start=2013, end=None, get=None): fetch_year for each year from start to the current year (end default); the current and previous year are always revisited for new filings.
6. attach(conn, df) -> df with float32 columns congress_buyers_90 (distinct members with a P trade in an [ST] asset of the row's ticker whose first trading session strictly after filed_date is in (date - 90 calendar days, date]) and congress_sellers_90 (same for S / S (partial)). Sessions: SELECT DISTINCT date FROM prices WHERE ticker='SPY'. Tickers with no congress_trades row at all get NaN (never traded by a member, unknown, not zero); others get 0.0 when nothing is in the window; no table -> NaN columns. Work per ticker on sorted arrays (numpy searchsorted), grouping frame rows with pandas groupby indices — never compare the whole frame per ticker.
7. main(argv=None): --fetch [--start 2013], --daily (run for the current and previous year only), --status. Import runtime first; sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60) with from universe import load_config inside main.

## Constraints
1. Create ONLY congress_trades.py and tests/regression/test_congress_trades.py. Modify nothing else.
2. congress_trades.py under 250 lines; test under 170 lines. pandas, numpy, requests, pypdf, xml.etree only.
3. The test never touches the network, pypdf or the real database: test parse_trades on literal text strings (including the two example rows above with their line breaks, an "S (partial)" row, an [OP] option row, and an "Over $50,000,000" amount), parse_index on a small literal XML, fetch_year with a fake get() and a monkeypatched text extractor (make the PDF-to-text step a module function pdf_text(content) so the test can replace it), and attach on an in-memory sqlite3 db.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_congress_trades.py exits 0.
2. The test checks: both example rows parse with ticker, type, ISO dates and amounts despite line breaks; "S (partial)" and the [OP] row parse with their types; "Over" gives hi None; parse_index keeps only P filings with ISO filed dates; fetch_year stores trades, marks a non-electronic DocID skipped, marks a failing fetch 'error' without raising, and a second run does not refetch ok/skipped docs; attach counts a buy from the first session after filed_date (not the filing day), drops it after 90 days, counts two members as 2, gives 0.0 for a ticker with only old trades and NaN for a ticker never traded.
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
