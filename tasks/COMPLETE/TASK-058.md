# TASK-058

- component: data
- priority: high
- state: COMPLETE
- branch: ado/task-058
- created: 2026-09-29T05:10:00+00:00
- dependencies: none

## Objective
Create edgar_financials.py: a daily feed of new 10-Q / 10-K filings straight from EDGAR into the existing sec_filings / sec_facts tables, so fundamentals and earnings surprises arrive within a day of filing instead of waiting up to three months for the SEC's quarterly Financial Statement Data Sets (owner, 2026-09-29: nothing filed after 2026-06-30 was loaded). Same row formats as sec_fundamentals.py's loader. Plain HTTP + JSON; no model calls. Plus its regression test.

## Background
Existing tables (sec_fundamentals.init creates them): sec_filings(adsh TEXT PK like '0001023731-26-000114', cik INTEGER, name, sic TEXT, form, period TEXT 'YYYYMMDD', fy TEXT, fp TEXT, filed TEXT 'YYYYMMDD', ticker, accepted TEXT like '2026-05-22 17:12:00.0' in America/New_York local time, prevrpt INTEGER, detail INTEGER, ticker_raw, first_tradeable); sec_facts(adsh, tag, ddate TEXT 'YYYYMMDD', qtrs INTEGER, value REAL, PK(adsh,tag,ddate,qtrs)). sec_fundamentals exposes FORMS = {"10-K","10-Q","10-K/A","10-Q/A"}, WANTED (set of us-gaap tag names), UA (User-Agent string) and _ticker_map(conn) -> {cik:int -> ticker}. The filings UPSERT must be exactly sec_fundamentals.load's statement (never overwrite ticker when ticker_raw is set; never touch ticker_raw / first_tradeable).
EDGAR sources (User-Agent header = sec_fundamentals.UA; at most 8 requests per second):
- Daily index: https://www.sec.gov/Archives/edgar/daily-index/{YYYY}/QTR{q}/form.{YYYYMMDD}.idx — fixed-width text; data lines follow a line of dashes; each data line: form type, company name, CIK, date filed (YYYYMMDD), file name like edgar/data/1023731/0001023731-26-000114.txt (the accession number is the file name without ".txt"). 404 on days with no index (weekends, holidays).
- Submissions: https://data.sec.gov/submissions/CIK{cik:010d}.json — keys name, sic, and filings.recent = parallel lists accessionNumber, filingDate ('YYYY-MM-DD'), reportDate ('YYYY-MM-DD'), acceptanceDateTime ('2026-08-05T20:34:35.000Z', which is UTC), form.
- Company facts: https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json — facts["us-gaap"][tag]["units"][unit] = list of dicts with keys start (absent for instant facts), end ('YYYY-MM-DD'), val, accn, fy, fp, form, filed.

## Relevant files
- `edgar_financials.py`
- `tests/regression/test_edgar_financials.py`
## Requirements
1. parse_index(text) -> list of dicts {form, name, cik:int, filed:'YYYYMMDD', adsh} for lines after the dashes line whose form is in sec_fundamentals.FORMS (exact match after stripping); parse by splitting from the right (file name, date, CIK are the last three whitespace-separated fields; the form is the first field; the name is what lies between).
2. et_accepted(iso_utc) -> 'YYYY-MM-DD HH:MM:SS.0' in America/New_York local time (zoneinfo), e.g. '2026-08-05T20:34:35.000Z' -> '2026-08-05 16:34:35.0'; None for empty input.
3. qtrs(start, end) -> 0 when start is None (instant); otherwise round(days/91.31) with a minimum of 1.
4. filing_row(adsh, cik, sub, facts, ticker) -> the 13-tuple for the UPSERT (adsh, cik, name, sic, form, period, fy, fp, filed, ticker, accepted, prevrpt=0, detail=None): form / filed / period / accepted from the submissions entry with that accessionNumber (period = reportDate without dashes, filed = filingDate without dashes, accepted = et_accepted(acceptanceDateTime)); fy / fp from the first companyfacts fact with accn == adsh (str(fy), fp), else None. Returns None if the accession is not in submissions.
5. fact_rows(adsh, facts) -> list of (adsh, tag, ddate 'YYYYMMDD', qtrs, value float) for every us-gaap tag in sec_fundamentals.WANTED, every unit, every fact with accn == adsh; duplicates on (tag, ddate, qtrs) keep the last one.
6. load_filing(conn, entry, get_json, tmap) -> int (facts stored): skip (return 0) when adsh already exists in sec_filings; fetch submissions and companyfacts with get_json(url) (a callable returning parsed JSON or None); cache both per CIK within one run; write the filing (UPSERT) and facts (INSERT OR REPLACE); a filing with zero wanted facts is still recorded; commit per filing.
7. run(conn, days, get_text, get_json, only_ciks=None) -> dict {"days", "filings_seen", "loaded", "facts", "skipped"}: for each date in `days` ('YYYY-MM-DD'), fetch the index with get_text(url) (None = no index); for each parsed entry whose cik is in only_ciks (when given), call load_filing; record each fully processed day in a table edgar_financials_days(day TEXT PRIMARY KEY, filings INTEGER, loaded_at TEXT) created by init(conn).
8. universe_ciks(conn) -> set of CIKs whose _ticker_map ticker is present in symbols.ticker (the priced universe).
9. main(argv=None): --daily [--days 7] processes the last N weekdays up to today (UTC date) that are not in edgar_financials_days, always re-processing today and yesterday; --since YYYY-MM-DD processes every weekday from that date to today not yet recorded; --status prints counts. Uses requests with the UA header, a sleep keeping under 8 requests/second, 3 retries with backoff, and 404 -> None. Import runtime first; storage.connect(load_config()["database"]["market_data_path"]); sec_fundamentals.init(conn); only_ciks = universe_ciks(conn). Prints the run() dict.

## Constraints
1. Create ONLY edgar_financials.py and tests/regression/test_edgar_financials.py. Modify nothing else.
2. edgar_financials.py under 250 lines; test under 180 lines. Standard library, requests, and the project modules named above; no pandas needed.
3. The test uses no network: an in-memory sqlite3 database initialised with sec_fundamentals.init plus a symbols(ticker TEXT) table, a small index text sample (with a non-wanted form and a 10-Q), and hand-written submissions / companyfacts dicts served by fake get_text / get_json callables.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_edgar_financials.py exits 0.
2. The test checks: parse_index keeps 10-Q/10-K rows only and extracts cik, filed and adsh (including a company name with spaces); et_accepted converts UTC to New York time in summer (EDT) and winter (EST); qtrs gives 0 for instants, 1 for a quarter, 4 for a year; fact_rows keeps only WANTED tags with the matching accn and formats ddate as YYYYMMDD; load_filing writes one sec_filings row with accepted in New York time and period/filed without dashes, stores the facts, and returns 0 on a second call (already present); a filing whose ticker_raw is set keeps its ticker after a reload; run() records the processed day and honours only_ciks; a 404 index (None) records nothing for that day.
3. At least 10 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
