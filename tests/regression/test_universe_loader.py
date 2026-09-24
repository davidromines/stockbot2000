"""
Regression tests for universe_loader (Addendum C Stage 4) and the FINSABER
anomaly flag.

Pinned: real rows pass through untouched; synthetic rows are tagged; `zero`
puts every synthetic delisting bar at 0 and `optimistic` at the previous
close; a synthetic ticker that collides with a real one trades under its
company_id; a symbol alternating between two price levels is flagged and
excluded from the FINSABER provider.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
import tempfile

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import finsaber
import universe_loader as ul

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    tmp = tempfile.mkdtemp()
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, "
              "source TEXT)")
    c.execute("CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT)")
    c.executemany("INSERT INTO symbols VALUES (?,?,NULL)", [("REAL", "common_stock"), ("DUP", "common_stock")])
    c.executemany("INSERT INTO prices VALUES (?,?,1,1,1,?,100,'t')",
                  [("REAL", "2016-01-04", 10.0), ("REAL", "2016-01-05", 11.0)])
    syn = pd.DataFrame({"company_id": ["AV:X", "AV:X", "AV:X", "CIK1", "CIK1"],
                        "ticker": ["DEADX", "DEADX", "DEADX", "DUP", "DUP"],
                        "date": ["2016-01-04", "2016-01-05", "2016-01-06", "2016-01-04", "2016-01-05"],
                        "open": [5.0, 5.0, 4.0, 3.0, 3.0], "high": [5.0, 5.0, 4.0, 3.0, 3.0],
                        "low": [5.0, 4.0, 1.0, 3.0, 3.0], "close": [5.0, 4.0, 2.0, 3.0, 3.0],
                        "volume": [None] * 5, "is_delisting_bar": [False, False, True, False, False],
                        "is_synthetic": True, "data_source": "synthetic_v2", "cohort_id": "all",
                        "synthetic_reason": "drawn:performance"})
    ul.SYNTH = os.path.join(tmp, "s.parquet")
    syn.to_parquet(ul.SYNTH, index=False)

    ex = ul.load_backtest_data(c, "2016-01-01", "2016-01-31", "exclude")
    check("exclude = real rows only", set(ex["ticker"]) == {"REAL"} and not ex["is_synthetic"].any())
    a = ul.load_backtest_data(c, "2016-01-01", "2016-01-31", "as_is")
    check("real rows untouched in as_is", a[a.ticker == "REAL"]["close"].tolist() == [10.0, 11.0])
    check("synthetic rows tagged", a[a.is_synthetic]["data_source"].str.startswith("synthetic").all())
    check("colliding ticker trades under its company_id", "CIK1" in set(a["ticker"]) and
          not ((a["ticker"] == "DUP") & a["is_synthetic"]).any())
    z = ul.load_backtest_data(c, "2016-01-01", "2016-01-31", "zero")
    check("zero: delisting bar at 0", z[(z.company_id == "AV:X") & z.is_delisting_bar]["close"].iloc[0] == 0.0)
    o = ul.load_backtest_data(c, "2016-01-01", "2016-01-31", "optimistic")
    check("optimistic: delisting at the previous close",
          o[(o.company_id == "AV:X") & o.is_delisting_bar]["close"].iloc[0] == 4.0)
    try:
        ul.load_backtest_data(c, "2016-01-01", "2016-01-31", "bogus")
        check("unknown mode refused", False)
    except ValueError:
        check("unknown mode refused", True)

    f = sqlite3.connect(os.path.join(tmp, "f.db"))
    finsaber.init(f)
    rows = [("GOOD", f"2016-01-{d:02d}", 1, 1, 1, 10 + d * 0.1, 10 + d * 0.1, 1) for d in range(1, 21)]
    rows += [("FLIP", f"2016-01-{d:02d}", 1, 1, 1, 1, 170.0 if d % 2 else 0.005, 1) for d in range(1, 21)]
    f.executemany("INSERT INTO finsaber_prices VALUES (?,?,?,?,?,?,?,?)", rows)
    f.commit()
    q = finsaber.flag_anomalies(f)
    check("alternating-price symbol flagged, clean one not", finsaber.flagged(f) == {"FLIP"}, q)
    bars = finsaber.FinsaberProvider(os.path.join(tmp, "f.db")).adjusted_bars(None, "2016-01-01", "2016-01-31")
    check("provider excludes the flagged symbol", set(bars["ticker"]) == {"GOOD"}, set(bars["ticker"]))

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
