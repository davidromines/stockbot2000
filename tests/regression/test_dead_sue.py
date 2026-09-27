"""
Earnings surprise for the dead companies (synthetic_fundamentals via sue_features):
EPS read by CIK from sec_filings/sec_facts, SUE from the company's own history, projected
onto its dates with the live rule (usable LAG_DAYS after filing, newest wins, stale after
MAX_AGE_DAYS). In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math
import os
import sqlite3
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import fundamental_features as ff
import pandas as pd
import sue_features as sfe

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE sec_filings (adsh TEXT, cik INTEGER, ticker TEXT, form TEXT, period TEXT, filed TEXT)")
    conn.execute("CREATE TABLE sec_facts (adsh TEXT, tag TEXT, qtrs INTEGER, ddate TEXT, value REAL)")
    q = date(2012, 3, 31)
    for i in range(12):                                   # 12 quarters, EPS rising, last one jumps
        p = q + timedelta(days=91 * i)
        filed = p + timedelta(days=30)
        eps = 1.0 + 0.01 * i + (0.02 if i % 3 else 0.0) + (0.5 if i == 11 else 0.0)   # deltas must vary
        a = f"a{i}"
        conn.execute("INSERT INTO sec_filings VALUES (?,?,?,?,?,?)",
                     (a, 777, None, "10-Q", p.strftime("%Y%m%d"), filed.strftime("%Y%m%d")))
        conn.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)", (a, "EarningsPerShareBasic", 1, p.strftime("%Y%m%d"), eps))
    eps = sfe.quarterly_eps_by_cik(conn, [777])
    check("EPS read by CIK for a company with no ticker", len(eps) == 12 and set(eps["ticker"]) == {"777"}, len(eps))
    sue = sfe.compute_sue(eps)
    check("SUE computed from the company's own history", len(sue) > 0 and sue["sue"].iloc[-1] > 2, sue.tail(2))
    last = sue.iloc[-1]
    filed = sfe._d(last["filed"])
    days = [(filed + timedelta(days=k)).isoformat() for k in (0, ff.LAG_DAYS - 1, ff.LAG_DAYS, 30, sfe.MAX_AGE_DAYS,
                                                                 sfe.MAX_AGE_DAYS + 1)]
    pr = sfe.project_dates(sue, days)
    v = pr.set_index("date")["sue"]
    check("not usable before the filing lag", math.isnan(v[days[0]]) or v[days[0]] != last["sue"])
    check("usable from filed + LAG_DAYS", v[days[2]] == last["sue"], pr)
    check("age counted from the filing date", pr.set_index("date")["sue_age"][days[3]] == 30)
    check("stale after MAX_AGE_DAYS", math.isnan(v[days[5]]) and v[days[4]] == last["sue"], pr)
    check("no surprises -> all NaN", pr.shape[0] == 6 and sfe.project_dates(pd.DataFrame(), days)["sue"].isna().all())
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
