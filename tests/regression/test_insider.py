"""Regression tests for insider.py. No network, no real database."""
import runtime  # noqa: F401

import os
import sqlite3
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402

import insider  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


SUB_HDR = "ACCESSION_NUMBER\tFILING_DATE\tDOCUMENT_TYPE\tISSUERCIK\tISSUERTRADINGSYMBOL"
TR_HDR = ("ACCESSION_NUMBER\tNONDERIV_TRANS_SK\tSECURITY_TITLE\tTRANS_DATE\t"
          "TRANS_CODE\tTRANS_SHARES\tTRANS_PRICEPERSHARE\tTRANS_ACQUIRED_DISP_CD")
OWN_HDR = "ACCESSION_NUMBER\tRPTOWNERCIK\tRPTOWNERNAME\tRPTOWNER_RELATIONSHIP"

SUBS = [
    "A1\t13-FEB-2023\t4\t111\tAAA",
    "A2\t31-JAN-2024\t3\t111\tAAA",
    "A3\t31-JAN-2024\t4\t222\tBBB",
    "A4\t31-JAN-2024\t4\t333\t",
    "A5\t31-JAN-2024\t4\t444\tCCC",
    "A6\t31-JAN-2022\t4\t222\tBBB",
]
TRS = [
    "A1\t1\tCommon\t15-NOV-2022\tP\t100\t10.0\tA",
    "A1\t2\tCommon\t15-NOV-2022\tS\t50\t11.0\tD",
    "A2\t1\tCommon\t15-NOV-2022\tP\t100\t10.0\tA",
    "A3\t1\tCommon\t15-NOV-2022\tA\t100\t10.0\tA",
    "A4\t1\tCommon\t15-NOV-2022\tP\t100\t10.0\tA",
    "A5\t1\tCommon\t15-NOV-2022\tP\t100\t10.0\tA",
    "A6\t1\tCommon\t20-JAN-2022\tS\t100\t10.0\tD",
]
OWNS = [
    "A1\t900\tAlice\tDirector",
    "A1\t901\tBob\tOfficer",
    "A2\t900\tAlice\tDirector",
    "A3\t902\tCarol\tDirector",
    "A4\t903\tDan\tDirector",
    "A5\t904\tEve\tTenPercentOwner",
    "A6\t905\tFay\tDirector",
]


def build_zip(tmp):
    p = Path(tmp) / "2006q1_form345.zip"
    with zipfile.ZipFile(p, "w") as zf:
        zf.writestr("SUBMISSION.tsv", SUB_HDR + "\n" + "\n".join(SUBS) + "\n")
        zf.writestr("NONDERIV_TRANS.tsv", TR_HDR + "\n" + "\n".join(TRS) + "\n")
        zf.writestr("REPORTINGOWNER.tsv", OWN_HDR + "\n" + "\n".join(OWNS) + "\n")
    return p


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE prices(ticker TEXT, date TEXT)")
    sessions = ["2022-11-14", "2022-11-15", "2022-11-16", "2022-11-17",
                "2023-02-13", "2023-02-14", "2023-02-15", "2023-02-16"]
    conn.executemany("INSERT INTO prices VALUES ('SPY', ?)",
                     [(s,) for s in sessions])
    conn.commit()
    return conn


def main():
    tmp = tempfile.mkdtemp()
    path = build_zip(tmp)
    df = insider.parse_zip(path)

    check("parse keeps P and S from Form 4",
          set(df["code"]) == {"P", "S"}, str(set(df["code"])))
    check("parse drops Form 3 row", "A2" not in set(df["accession"]))
    check("parse drops grant (A) row", "A3" not in set(df["accession"]))
    check("parse drops empty ticker", "A4" not in set(df["accession"]))
    check("dates become ISO",
          set(df["trans_date"]) == {"2022-11-15", "2022-01-20"} and
          set(df["filing_date"]) == {"2023-02-13", "2024-01-31", "2022-01-31"}, str(df["trans_date"].tolist()))
    check("value_usd = shares*price",
          float(df[df["trans_sk"] == "1"]["value_usd"].iloc[0]) == 1000.0)
    a1 = df[df["accession"] == "A1"]
    check("one row per owner when two owners (2 transactions x 2 owners)",
          len(a1) == 4 and set(a1["owner_cik"]) == {"900", "901"}, str(len(a1)))

    conn = make_conn()
    insider.init(conn)
    rows = [tuple(None if (isinstance(v, float) and np.isnan(v)) else v
                  for v in r) for r in df.itertuples(index=False, name=None)]
    conn.executemany(
        "INSERT OR REPLACE INTO insider_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows)
    conn.commit()

    p = insider.purchases(conn)
    check("purchases excludes TenPercentOwner-only buyer",
          "CCC" not in set(p["ticker"]), str(set(p["ticker"])))
    check("purchases keeps Director/Officer buyers",
          set(p["ticker"]) == {"AAA"}, str(set(p["ticker"])))

    # Routine: owner 900 bought AAA in Nov 2022; add Nov 2019/2020/2021 history.
    for y in (2019, 2020, 2021):
        conn.execute("INSERT OR REPLACE INTO insider_trades VALUES "
                     "(?,?,?,?,?,?,?,?,?,?,?,?)",
                     (f"H{y}", "1", "900", "AAA", "111", f"{y}-11-10",
                      f"{y}-11-12", "P", 1.0, 1.0, 1.0, "Director"))
    conn.commit()
    p = insider.purchases(conn)
    r900 = p[(p["owner_cik"] == "900") & (p["trans_date"] == "2022-11-15")]
    check("routine True when traded same month 3 prior years",
          bool(r900["routine"].iloc[0]) is True)
    r901 = p[p["owner_cik"] == "901"]
    check("routine False when a prior year is missing",
          bool(r901["routine"].iloc[0]) is False)

    sessions = ["2022-11-14", "2022-11-15", "2022-11-16"]
    ft = insider.first_tradeable(["2022-11-15", "2022-11-16", "2022-11-17"],
                                 sessions)
    check("first_tradeable skips the filing date itself",
          ft[0] == "2022-11-16", str(ft))
    check("first_tradeable returns None past the last session",
          ft[2] is None, str(ft))

    # attach: purchase filed 2023-02-13 -> first tradeable 2023-02-14; the joint
    # filing (two owners, one $1,000 purchase) counts its dollars once.
    frame = pd.DataFrame({
        "_t": ["AAA", "AAA", "AAA", "AAA", "BBB", "ZZZ"],
        "_d": ["2023-02-13", "2023-02-14", "2023-02-15", "2023-05-20",
               "2023-02-14", "2023-02-14"],
    })
    out = insider.attach(conn, frame)
    check("attach gives purchase on first tradeable session",
          float(out["insider_buy_usd_90"].iloc[1]) == 1000.0,
          str(out["insider_buy_usd_90"].tolist()))
    check("attach not before first tradeable session",
          float(out["insider_buy_usd_90"].iloc[0]) == 0.0)
    check("attach drops purchase after 90 calendar days",
          float(out["insider_buy_usd_90"].iloc[3]) == 0.0)
    check("attach counts two distinct buyers as 2",
          float(out["insider_buyers_90"].iloc[1]) == 2.0,
          str(out["insider_buyers_90"].tolist()))
    check("attach gives 0.0 for Form-4 filer with no recent buys",
          float(out["insider_buy_usd_90"].iloc[4]) == 0.0)
    check("attach gives NaN for ticker never seen",
          np.isnan(out["insider_buy_usd_90"].iloc[5]))
    check("attach columns are float32",
          all(out[c].dtype == np.float32 for c in
              ("insider_buy_usd_90", "insider_buyers_90", "opp_buyers_90")))

    bare = sqlite3.connect(":memory:")
    bare.execute("CREATE TABLE prices(ticker TEXT, date TEXT)")
    bare.execute("INSERT INTO prices VALUES ('SPY','2023-02-14')")
    out2 = insider.attach(bare, frame.copy())
    check("attach without table gives NaN columns",
          bool(out2["insider_buy_usd_90"].isna().all()))

    print()
    if FAILED:
        print(f"{len(FAILED)} FAILED")
        sys.exit(1)
    print("ALL PASS")


if __name__ == "__main__":
    main()
