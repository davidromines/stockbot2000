"""
synthetic_fundamentals.py: a dead company's own filings, priced off its synthetic
path, projected with the real panel's lag. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import fundamental_features as ff
import synthetic_fundamentals as sf
import value_metrics as vm

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    dates = pd.bdate_range("2012-01-02", "2013-12-31").strftime("%Y-%m-%d")
    rng = np.random.default_rng(3)
    px = pd.Series(20 * np.exp(np.cumsum(rng.normal(0, 0.02, len(dates)))), index=dates)
    spy = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(dates)))), index=dates)

    # The series helper must equal value_metrics._market_context on the same prices.
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    c.executemany("INSERT INTO prices VALUES ('X', ?, ?)", list(zip(dates, px)))
    c.executemany("INSERT INTO prices VALUES ('SPY', ?, ?)", list(zip(dates, spy)))
    a = vm._market_context(c, "X", "20130315")
    b = sf.market_context_from(px, spy, "2013-03-15")
    check("market context from a series == value_metrics._market_context",
          a.keys() == b.keys() and all(abs(a[k] - b[k]) < 1e-12 for k in a), (a, b))

    c.execute("CREATE TABLE sec_facts (adsh TEXT, tag TEXT, ddate TEXT, qtrs INTEGER, value REAL)")
    facts = {"Assets": 1000.0, "StockholdersEquity": 400.0, "NetIncomeLoss": 50.0, "Revenues": 800.0,
             "CommonStockSharesOutstanding": 10.0, "Liabilities": 600.0}
    for adsh, scale in (("A1", 1.0), ("A2", 1.1)):
        for tag, v in facts.items():
            c.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)", (adsh, tag, "20121231", 4 if tag in
                      ("NetIncomeLoss", "Revenues") else 0, v * scale))
    f = sf.company_metrics(c, 1, px, spy, [("A1", "20130301"), ("A2", "20130601")])
    check("one metrics row per filing with facts", len(f) == 2, f)
    close = float(px[px.index <= "2013-03-01"].iloc[-1])
    if "book_to_market" in f and f["book_to_market"].notna().any():
        want = 400.0 / (close * 10.0)
        check("book_to_market priced off the synthetic close x filed shares",
              abs(f["book_to_market"].iloc[0] - want) < 1e-6 * max(1, want), (f["book_to_market"].iloc[0], want))
    else:
        check("book_to_market resolved from the fixture facts", False, f.to_dict())
    d = sf.project(pd.Index(dates), f)
    first = d["date"].min() if len(d) else None
    check("no fundamentals before filed + LAG_DAYS",
          first is not None and first >= (pd.Timestamp("2013-03-01") + pd.Timedelta(days=ff.LAG_DAYS)).strftime("%Y-%m-%d"),
          first)
    row = d[d["date"] == "2013-06-05"]
    check("after the second filing the second filing's values apply",
          len(row) == 1 and int(row["days_since_filing"].iloc[0]) == 4, row.to_dict())
    early = sf.project(pd.Index(pd.bdate_range("2008-06-02", "2008-12-31").strftime("%Y-%m-%d")),
                       pd.DataFrame([{"filed": "20080601", **{k: 1.0 for k in ff.FUNDAMENTAL_COLS}}]))
    check("nothing before 2009 (where the real panel starts)", early.empty)
    check("no filing -> no fundamentals", sf.project(pd.Index(dates), pd.DataFrame()).empty)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
