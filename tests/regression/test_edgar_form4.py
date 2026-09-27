import runtime  # noqa: F401

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import edgar_form4  # noqa: E402
import insider  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


INDEX_TEXT = """Description:           Daily Index of EDGAR Dissemination Feed
Form Type   Company Name                          CIK         Date Filed  File Name
-------------------------------------------------------------------------------
4           ACME CORP                             123456      20260115    edgar/data/123456/0001-26-000001.txt
4/A         ACME CORP                             123456      20260115    edgar/data/123456/0001-26-000002.txt
10-K        OTHER INC                             999999      20260115    edgar/data/999999/0009-26-000001.txt
4           BETA CORP                             654321      20260115    edgar/data/654321/0002-26-000001.txt
"""

GOOD_XML = """<?xml version="1.0"?>
<ownershipDocument>
  <issuer>
    <issuerCik>0001234567</issuerCik>
    <issuerTradingSymbol>acme</issuerTradingSymbol>
  </issuer>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>111</rptOwnerCik></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>1</isDirector><isOfficer>0</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <reportingOwner>
    <reportingOwnerId><rptOwnerCik>222</rptOwnerCik></reportingOwnerId>
    <reportingOwnerRelationship><isDirector>false</isDirector><isOfficer>true</isOfficer></reportingOwnerRelationship>
  </reportingOwner>
  <nonDerivativeTable>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-14</value></transactionDate>
      <transactionCoding><transactionCode>P</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>100</value></transactionShares>
        <transactionPricePerShare><value>10.5</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
    <nonDerivativeTransaction>
      <transactionDate><value>2026-01-14</value></transactionDate>
      <transactionCoding><transactionCode>A</transactionCode></transactionCoding>
      <transactionAmounts>
        <transactionShares><value>50</value></transactionShares>
        <transactionPricePerShare><value>1.0</value></transactionPricePerShare>
      </transactionAmounts>
    </nonDerivativeTransaction>
  </nonDerivativeTable>
</ownershipDocument>
"""

BAD_XML = "<ownershipDocument><issuer><issuerTradingSymbol>BROKEN"

FILING_GOOD = "<SEC-DOCUMENT>\n<XML>\n%s\n</XML>\n</SEC-DOCUMENT>" % GOOD_XML
FILING_BAD = "<SEC-DOCUMENT>\n<XML>\n%s\n</XML>\n</SEC-DOCUMENT>" % BAD_XML


def make_get(index_text=INDEX_TEXT, filings=None):
    filings = filings or {}
    calls = []

    def get(url):
        calls.append(url)
        if url.endswith(".idx"):
            return 200, index_text
        for key, text in filings.items():
            if key in url:
                return 200, text
        return 404, ""
    get.calls = calls
    return get


def fresh_conn():
    conn = sqlite3.connect(":memory:")
    edgar_form4.init(conn)
    return conn


def test_parse_index():
    rows = edgar_form4.parse_index(INDEX_TEXT)
    forms = [r["form"] for r in rows]
    check("parse_index keeps only 4 and 4/A", forms == ["4", "4/A", "4"], forms)
    check("parse_index ISO dates", all(r["filed"] == "2026-01-15" for r in rows))
    check("parse_index accessions", rows[0]["accession"] == "0001-26-000001", rows[0]["accession"])


def test_extract_xml():
    x = edgar_form4.extract_xml(FILING_GOOD)
    check("extract_xml finds block", x is not None and "ownershipDocument" in x)
    check("extract_xml none when absent", edgar_form4.extract_xml("no xml here") is None)


def test_parse_form4():
    rows = edgar_form4.parse_form4(GOOD_XML, "0001-26-000001", "2026-01-15")
    check("parse_form4 one row per P/S per owner", len(rows) == 2, len(rows))
    check("parse_form4 drops A code", all(r["code"] == "P" for r in rows))
    check("parse_form4 ticker upper", all(r["ticker"] == "ACME" for r in rows))
    check("parse_form4 relationship Director", rows[0]["relationship"] == "Director", rows[0]["relationship"])
    check("parse_form4 relationship Officer", rows[1]["relationship"] == "Officer", rows[1]["relationship"])
    check("parse_form4 value_usd", rows[0]["value_usd"] == 100 * 10.5, rows[0]["value_usd"])
    check("parse_form4 trans_sk d-prefix", all(r["trans_sk"].startswith("d") for r in rows))
    check("parse_form4 bad xml empty", edgar_form4.parse_form4(BAD_XML, "x", "2026-01-15") == [])


def test_fetch_day():
    conn = fresh_conn()
    get = make_get(filings={"0001-26-000001": FILING_GOOD, "0002-26-000001": FILING_BAD})
    res = edgar_form4.fetch_day(conn, "2026-01-15", get=get)
    check("fetch_day returns rows", res["rows"] == 2, res)
    n = conn.execute("SELECT COUNT(*) FROM insider_trades").fetchone()[0]
    check("fetch_day stored rows", n == 2, n)
    logged = conn.execute("SELECT filings, rows FROM form4_daily_log WHERE day='2026-01-15'").fetchone()
    check("fetch_day logged day", logged is not None and logged[0] == 2, logged)
    check("fetch_day skips malformed", "failed" in (conn.execute(
        "SELECT note FROM form4_daily_log WHERE day='2026-01-15'").fetchone()[0] or ""))
    res2 = edgar_form4.fetch_day(conn, "2026-01-15", get=get)
    n2 = conn.execute("SELECT COUNT(*) FROM insider_trades").fetchone()[0]
    check("fetch_day idempotent", n2 == 2, n2)


def test_run_skips_logged():
    conn = fresh_conn()
    get = make_get(filings={"0001-26-000001": FILING_GOOD, "0002-26-000001": FILING_BAD})
    edgar_form4.fetch_day(conn, "2026-01-15", get=get)
    out = edgar_form4.run(conn, days=1, today="2026-01-16", get=get)
    check("run skips logged day", out == [], out)


def test_reconcile():
    conn = fresh_conn()
    conn.execute(
        "INSERT INTO insider_trades(accession, trans_sk, owner_cik, ticker, trans_date,"
        " filing_date, code, shares, price, value_usd, relationship)"
        " VALUES('ACC1','d0','1','X','2026-01-14','2026-01-15','P',1,1,1,'Director')")
    conn.execute(
        "INSERT INTO insider_trades(accession, trans_sk, owner_cik, ticker, trans_date,"
        " filing_date, code, shares, price, value_usd, relationship)"
        " VALUES('ACC1','o0','1','X','2026-01-14','2026-01-15','P',1,1,1,'Director')")
    conn.execute(
        "INSERT INTO insider_trades(accession, trans_sk, owner_cik, ticker, trans_date,"
        " filing_date, code, shares, price, value_usd, relationship)"
        " VALUES('ACC2','d0','1','Y','2026-01-14','2026-01-15','P',1,1,1,'Director')")
    conn.commit()
    deleted = edgar_form4.reconcile(conn)
    check("reconcile deletes covered daily row", deleted == 1, deleted)
    remaining = conn.execute("SELECT accession, trans_sk FROM insider_trades ORDER BY accession, trans_sk").fetchall()
    check("reconcile keeps official and uncovered", remaining == [("ACC1", "o0"), ("ACC2", "d0")], remaining)


def test_404_index():
    conn = fresh_conn()

    def get(url):
        return 404, ""
    res = edgar_form4.fetch_day(conn, "2026-01-17", get=get)
    check("404 index logs no index", res["filings"] == 0)
    note = conn.execute("SELECT note FROM form4_daily_log WHERE day='2026-01-17'").fetchone()[0]
    check("404 index note", note == "no index", note)


def main():
    test_parse_index()
    test_extract_xml()
    test_parse_form4()
    test_fetch_day()
    test_run_skips_logged()
    test_reconcile()
    test_404_index()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
