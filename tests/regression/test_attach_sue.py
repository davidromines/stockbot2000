"""storage.attach_fundamentals joins daily_sue (sue, sue_age) beside the fundamentals, by
(ticker, date) exactly — a day without a usable surprise stays NaN, never zero."""
import runtime  # noqa: F401  — must precede numpy/pandas
import math
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import storage

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    cols = ", ".join(f"{x} REAL" for x in storage.FUNDAMENTAL_PANEL_COLS)
    c.execute(f"CREATE TABLE daily_fundamentals (ticker TEXT, date TEXT, has_fundamentals INTEGER, "
              f"days_since_filing INTEGER, {cols})")
    c.execute("CREATE TABLE daily_sue (ticker TEXT, date TEXT, sue REAL, sue_age INTEGER)")
    c.execute("INSERT INTO daily_fundamentals (ticker, date, has_fundamentals, roa) VALUES ('A','2020-05-07',1,0.1)")
    c.execute("INSERT INTO daily_sue VALUES ('A','2020-05-07',2.5,2)")
    df = pd.DataFrame({"ticker": ["A", "A", "B"], "date": pd.to_datetime(["2020-05-07", "2020-05-06", "2020-05-07"])})
    out = storage.attach_fundamentals(c, df)
    a = out[(out.ticker == "A") & (out.date == "2020-05-07")].iloc[0]
    check("sue and sue_age joined on the exact (ticker, date)", a["sue"] == 2.5 and a["sue_age"] == 2, a.to_dict())
    check("fundamentals still joined", abs(a["roa"] - 0.1) < 1e-6)
    b = out[(out.ticker == "A") & (out.date == "2020-05-06")].iloc[0]
    check("a day without a surprise is NaN, not zero", math.isnan(b["sue"]))
    check("row count and order preserved", len(out) == 3 and list(out.ticker) == ["A", "A", "B"])
    c2 = sqlite3.connect(":memory:")
    c2.execute(f"CREATE TABLE daily_fundamentals (ticker TEXT, date TEXT, has_fundamentals INTEGER, "
               f"days_since_filing INTEGER, {cols})")
    out2 = storage.attach_fundamentals(c2, df)
    check("no daily_sue table -> fundamentals only, no error", "sue" not in out2.columns and len(out2) == 3)
    print("\n  " + ("ALL PASS" if not FAILED else f"{len(FAILED)} FAILED"))
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
