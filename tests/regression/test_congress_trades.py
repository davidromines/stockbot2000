"""Regression tests for congress_trades.py. No network, no pypdf, no real DB."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import congress_trades as ct

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + ("  " + str(detail) if detail else ""))
        FAILED.append(name)


ROW1 = "SP Albemarle Corporation (ALB) [ST] S 12/21/2023 01/08/2024 $1,001 - $15,000"
ROW2 = "SP Charles Schwab Corporation (SCHW)\n[ST]\nP 12/14/2023 01/08/2024 $50,001 -\n$100,000"
ROW3 = "JT Apple Inc. (AAPL) [ST] S (partial) 01/02/2024 01/10/2024 $15,001 - $50,000"
ROW4 = "DC Tesla, Inc. (TSLA) [OP] P 02/01/2024 02/05/2024 Over $50,000,000"

XML = """<FinancialDisclosure>
<Member><Prefix>Hon.</Prefix><Last>Smith</Last><First>Jane</First>
<FilingType>P</FilingType><StateDst>CA12</StateDst><Year>2024</Year>
<FilingDate>1/8/2024</FilingDate><DocID>20012345</DocID></Member>
<Member><Last>Doe</Last><First>John</First><FilingType>O</FilingType>
<StateDst>TX01</StateDst><Year>2024</Year><FilingDate>2/1/2024</FilingDate>
<DocID>10099999</DocID></Member>
</FinancialDisclosure>"""


def test_parse_trades():
    t = ct.parse_trades(ROW1)
    check("row1 parses", len(t) == 1, t)
    check("row1 ticker/type", t[0]["ticker"] == "ALB" and t[0]["txn_type"] == "S", t)
    check("row1 iso dates", t[0]["txn_date"] == "2023-12-21" and t[0]["notif_date"] == "2024-01-08", t)
    check("row1 amounts", t[0]["amount_lo"] == 1001.0 and t[0]["amount_hi"] == 15000.0, t)

    t = ct.parse_trades(ROW2)
    check("row2 parses across line breaks", len(t) == 1 and t[0]["ticker"] == "SCHW", t)
    check("row2 buy and amounts", t[0]["txn_type"] == "P" and t[0]["amount_lo"] == 50001.0
          and t[0]["amount_hi"] == 100000.0, t)

    t = ct.parse_trades(ROW3)
    check("partial sale type", t[0]["txn_type"] == "S (partial)", t)
    check("partial sale owner", t[0]["owner"] == "JT", t)

    t = ct.parse_trades(ROW4)
    check("option row kept and flagged", t[0]["asset_type"] == "OP" and t[0]["txn_type"] == "P", t)
    check("over amount has hi None", t[0]["amount_lo"] == 50000000.0 and t[0]["amount_hi"] is None, t)

    t = ct.parse_trades(ROW1 + "\n" + ROW2)
    check("seq is match order", [x["seq"] for x in t] == [0, 1], t)


def test_parse_index():
    rows = ct.parse_index(XML)
    check("only P filings kept", len(rows) == 1, rows)
    check("member name joined", rows[0]["member"] == "Jane Smith", rows)
    check("filed date iso", rows[0]["filed_date"] == "2024-01-08", rows)
    check("doc id and state", rows[0]["doc_id"] == "20012345" and rows[0]["state_dst"] == "CA12", rows)


def _fake_get(url):
    if url.endswith("FD.zip"):
        import io
        import zipfile
        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w") as z:
            z.writestr("2024FD.xml", XML)
        return 200, buf.getvalue()
    if "20012345" in url:
        return 200, b"%PDF-fake"
    return 404, b""


def test_fetch_year():
    conn = sqlite3.connect(":memory:")
    ct.init(conn)
    orig = ct.pdf_text
    ct.pdf_text = lambda content: ROW1 + "\n" + ROW2
    try:
        s = ct.fetch_year(conn, 2024, get=_fake_get)
        check("fetch_year ok count", s["ok"] == 1, s)
        check("fetch_year trades stored", s["trades"] == 2, s)
        n = conn.execute("SELECT COUNT(*) FROM congress_trades").fetchone()[0]
        check("trades rows inserted", n == 2, n)
        row = conn.execute(
            "SELECT member, filed_date, ticker FROM congress_trades ORDER BY seq").fetchone()
        check("index metadata attached", row == ("Jane Smith", "2024-01-08", "ALB"), row)

        # A non-electronic DocID (not 8 digits starting with 2) is skipped.
        conn.execute("INSERT OR REPLACE INTO congress_docs VALUES "
                     "('10099999',2024,'John Doe','TX01','2024-02-01','skipped',0,'x')")
        conn.commit()
        s2 = ct.fetch_year(conn, 2024, get=_fake_get)
        check("second run refetches nothing", s2["ok"] == 0 and s2["trades"] == 0, s2)
        check("skipped doc not refetched", s2["skipped"] == 0, s2)

        # A failing fetch is recorded as error and never raises.
        conn.execute("DELETE FROM congress_docs WHERE doc_id='20012345'")
        conn.commit()
        s3 = ct.fetch_year(conn, 2024, get=lambda url: (500, b""))
        check("index failure is an error not a raise", s3["errors"] == 1, s3)
        s4 = ct.fetch_year(conn, 2024, get=lambda url: _fake_get(url) if url.endswith("FD.zip") else (500, b""))
        check("pdf failure recorded as error", s4["errors"] == 1, s4)
        st = conn.execute("SELECT status FROM congress_docs WHERE doc_id='20012345'").fetchone()
        check("error status stored", st == ("error",), st)
    finally:
        ct.pdf_text = orig
        conn.close()


def test_attach():
    conn = sqlite3.connect(":memory:")
    ct.init(conn)
    conn.execute("CREATE TABLE prices(ticker TEXT, date TEXT)")
    sessions = ["2023-01-03", "2024-01-05", "2024-01-08", "2024-01-09", "2024-01-10",
                "2024-04-10", "2024-04-11"]
    for d in sessions:
        conn.execute("INSERT INTO prices VALUES ('SPY', ?)", (d,))
    # Filed 2024-01-08 (a session day): knowable from 2024-01-09, not 01-08.
    conn.execute("INSERT INTO congress_trades VALUES "
                 "('20012345',0,'Jane Smith','CA12','','ALB','ST','P','2023-12-21',"
                 "'2024-01-08','2024-01-08',1001.0,15000.0)")
    conn.execute("INSERT INTO congress_trades VALUES "
                 "('20012345',1,'John Doe','TX01','','ALB','ST','P','2023-12-22',"
                 "'2024-01-08','2024-01-08',1001.0,15000.0)")
    conn.execute("INSERT INTO congress_trades VALUES "
                 "('20012345',2,'Jane Smith','CA12','','OLD','ST','P','2023-01-01',"
                 "'2023-01-02','2023-01-02',1001.0,15000.0)")
    conn.execute("INSERT INTO congress_trades VALUES "
                 "('20012345',3,'Jane Smith','CA12','','ALB','ST','S','2023-12-21',"
                 "'2024-01-08','2024-01-08',1001.0,15000.0)")
    conn.commit()

    df = pd.DataFrame({"_t": ["ALB", "ALB", "ALB", "OLD", "NEVER"],
                       "_d": ["2024-01-08", "2024-01-09", "2024-04-11",
                              "2024-01-09", "2024-01-09"]})
    out = ct.attach(conn, df)
    check("filing day not counted", out["congress_buyers_90"].iloc[0] == 0.0,
          out["congress_buyers_90"].tolist())
    check("first session after filing counts", out["congress_buyers_90"].iloc[1] == 2.0,
          out["congress_buyers_90"].tolist())
    check("dropped after 90 days", out["congress_buyers_90"].iloc[2] == 0.0,
          out["congress_buyers_90"].tolist())
    check("old-only ticker is 0.0 not NaN", out["congress_buyers_90"].iloc[3] == 0.0,
          out["congress_buyers_90"].tolist())
    check("never-traded ticker is NaN", np.isnan(out["congress_buyers_90"].iloc[4]),
          out["congress_buyers_90"].tolist())
    check("sellers counted separately", out["congress_sellers_90"].iloc[1] == 1.0,
          out["congress_sellers_90"].tolist())
    check("columns are float32", out["congress_buyers_90"].dtype == np.float32,
          out["congress_buyers_90"].dtype)
    conn.close()

    empty = sqlite3.connect(":memory:")
    df2 = pd.DataFrame({"_t": ["ALB"], "_d": ["2024-01-09"]})
    out2 = ct.attach(empty, df2)
    check("no table gives NaN", np.isnan(out2["congress_buyers_90"].iloc[0]), out2)
    empty.close()


def main():
    test_parse_trades()
    test_parse_index()
    test_fetch_year()
    test_attach()
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
