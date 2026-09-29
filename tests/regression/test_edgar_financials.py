"""
edgar_financials.py (TASK-058): the daily EDGAR 10-Q/10-K feed. No network — fake
get_text / get_json; in-memory database initialised with sec_fundamentals.init.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import edgar_financials as ef
import sec_fundamentals as sf

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


INDEX = """Description:           Daily Index of EDGAR Dissemination Feed by Form Type
Form Type   Company Name                                                  CIK         Date Filed  File Name
---------------------------------------------------------------------------------------------------------------
1-A              Naoris Quantum Protocol Inc.                                  2145466     20260805    edgar/data/2145466/0001213900-26-085345.txt
10-Q             8X8 INC /DE/                                                  1023731     20260805    edgar/data/1023731/0001023731-26-000114.txt
10-K/A           Big Co Holdings Inc                                           555         20260805    edgar/data/555/0000000555-26-000001.txt
"""
ADSH = "0001023731-26-000114"
SUB = {"name": "8X8 INC /DE/", "sic": "7374", "filings": {"recent": {
    "accessionNumber": ["0001023731-26-000099", ADSH],
    "filingDate": ["2026-05-22", "2026-08-05"], "reportDate": ["2026-03-31", "2026-06-30"],
    "acceptanceDateTime": ["2026-05-22T21:12:00.000Z", "2026-08-05T20:34:35.000Z"],
    "form": ["10-K", "10-Q"]}}}
FACTS = {"facts": {"us-gaap": {
    "Assets": {"units": {"USD": [
        {"end": "2026-03-31", "val": 662821000, "accn": ADSH, "fy": 2027, "fp": "Q1", "form": "10-Q"},
        {"end": "2026-06-30", "val": 672806000, "accn": ADSH, "fy": 2027, "fp": "Q1", "form": "10-Q"},
        {"end": "2025-06-30", "val": 1, "accn": "other", "fy": 2026, "fp": "Q1", "form": "10-Q"}]}},
    "NetIncomeLoss": {"units": {"USD": [
        {"start": "2026-04-01", "end": "2026-06-30", "val": -5000000, "accn": ADSH, "fy": 2027, "fp": "Q1"}]}},
    "SomethingUnwanted": {"units": {"USD": [{"end": "2026-06-30", "val": 9, "accn": ADSH}]}}}}}

rows = ef.parse_index(INDEX)
check("parse_index keeps 10-Q / 10-K forms only", [r["form"] for r in rows] == ["10-Q", "10-K/A"], rows)
check("parse_index extracts cik, filed and adsh",
      rows[0]["cik"] == 1023731 and rows[0]["filed"] == "20260805" and rows[0]["adsh"] == ADSH, rows[0])
check("company name with spaces kept whole", rows[1]["name"] == "Big Co Holdings Inc", rows[1])

check("UTC -> New York in summer (EDT)", ef.et_accepted("2026-08-05T20:34:35.000Z") == "2026-08-05 16:34:35.0",
      ef.et_accepted("2026-08-05T20:34:35.000Z"))
check("UTC -> New York in winter (EST)", ef.et_accepted("2026-01-15T22:05:00.000Z") == "2026-01-15 17:05:00.0",
      ef.et_accepted("2026-01-15T22:05:00.000Z"))
check("empty acceptance -> None", ef.et_accepted("") is None)

check("qtrs: instant 0, quarter 1, year 4",
      (ef.qtrs(None, "2026-06-30"), ef.qtrs("2026-04-01", "2026-06-30"), ef.qtrs("2025-07-01", "2026-06-30")) == (0, 1, 4))

fr = ef.fact_rows(ADSH, FACTS["facts"])
check("fact_rows: wanted tags, matching accn, YYYYMMDD dates",
      sorted(fr) == sorted([(ADSH, "Assets", "20260331", 0, 662821000.0), (ADSH, "Assets", "20260630", 0, 672806000.0),
                            (ADSH, "NetIncomeLoss", "20260630", 1, -5000000.0)]), fr)

conn = sqlite3.connect(":memory:")
sf.init(conn)
conn.execute("CREATE TABLE symbols (ticker TEXT)")
conn.execute("INSERT INTO symbols VALUES ('EGHT')")
sf._ticker_map = lambda c: {1023731: "EGHT", 555: "BIG"}
calls = []


def get_json(url):
    calls.append(url)
    return SUB if "submissions" in url else FACTS


entry = {"form": "10-Q", "name": "8X8", "cik": 1023731, "filed": "20260805", "adsh": ADSH}
n = ef.load_filing(conn, entry, get_json, {1023731: "EGHT"})
row = conn.execute("SELECT form, period, filed, accepted, fy, fp, ticker FROM sec_filings WHERE adsh=?", (ADSH,)).fetchone()
check("load_filing writes the filing in New York time, dates without dashes",
      row == ("10-Q", "20260630", "20260805", "2026-08-05 16:34:35.0", "2027", "Q1", "EGHT"), row)
check("load_filing stores the facts", n == 3 and conn.execute("SELECT COUNT(*) FROM sec_facts").fetchone()[0] == 3, n)
check("second call is a no-op (already present)", ef.load_filing(conn, entry, get_json, {1023731: "EGHT"}) == 0)

conn.execute("UPDATE sec_filings SET ticker='EGHT-X', ticker_raw='EGHT-PA' WHERE adsh=?", (ADSH,))
conn.execute(ef.FILING_UPSERT, ef.filing_row(ADSH, 1023731, SUB, FACTS["facts"], "EGHT"))
check("a repaired ticker survives a reload",
      conn.execute("SELECT ticker FROM sec_filings WHERE adsh=?", (ADSH,)).fetchone()[0] == "EGHT-X")

conn2 = sqlite3.connect(":memory:")
sf.init(conn2)
conn2.execute("CREATE TABLE symbols (ticker TEXT)")
conn2.execute("INSERT INTO symbols VALUES ('EGHT')")
texts = {"20260805": INDEX}
stats = ef.run(conn2, ["2026-08-05", "2026-08-08"],
               lambda url: next((t for d, t in texts.items() if d in url), None), get_json,
               only_ciks=ef.universe_ciks(conn2))
days = [r[0] for r in conn2.execute("SELECT day FROM edgar_financials_days")]
check("run records the processed day; a missing index records nothing", days == ["2026-08-05"], days)
check("run honours only_ciks (BIG not in the priced universe)",
      stats["filings_seen"] == 1 and stats["loaded"] == 1, stats)

sys.exit(1 if FAILED else 0)
