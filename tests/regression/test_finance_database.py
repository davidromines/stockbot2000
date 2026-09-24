"""
Regression test for finance_database.py and its use in universe_layer_a.py.

Pinned: column names are matched across releases and a missing one is None,
never a default; the delisted flag is parsed from its text forms; a
FinanceDatabase row attaches to a Layer A company only when ticker AND
normalised name agree — a later company that reuses a dead one's ticker is
NOT matched (the ticker reuse trap); unmatched rows are counted, never added;
a matched delisted row becomes listing evidence; its sector stays in its own
field.

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

import finance_database as fdb
import universe_layer_a as ua

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    raw = pd.DataFrame({"Symbol": [" old ", "NEW", "ACT", ""], "Name": ["Oldco Inc", "Newco Corp", "Activeco", "x"],
                        "Sector": ["Energy", "Tech", None, None], "Exchange": ["NYQ", "NMS", "NYQ", None],
                        "Delisted": ["True", "false", None, None]})
    n = fdb.normalise(raw, "equities.csv")
    check("columns matched case-insensitively; blank symbols dropped", list(n["symbol"]) == ["OLD", "NEW", "ACT"])
    check("delisted flag parsed; missing stays None", list(n["delisted"]) == [True, False, None], list(n["delisted"]))
    check("a column the release lacks is None, not a default", n["cusip"].isna().all())

    tmp = tempfile.mkdtemp()
    os.makedirs(os.path.join(tmp, "database", "equities"))
    raw.to_csv(os.path.join(tmp, "database", "equities", "a.csv"), index=False)
    s = {**fdb.DEFAULTS, "clone_dir": tmp, "out": os.path.join(tmp, "fd.parquet")}
    rep = fdb.import_csvs(s)
    check("import writes the parquet with a report", rep["rows"] == 3 and rep["delisted_true"] == 1, rep)

    # Layer A on a tiny database: OLD is dead Oldco (2001-2010); the ticker OLD
    # now belongs to an unrelated company in FinanceDatabase for one test row.
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE edgar_companies (cik INT, company_name TEXT, ticker TEXT, first_filed TEXT, "
              "last_filed TEXT, n_annual INT, still_filing INT)")
    c.execute("CREATE TABLE sec_filings (cik INT, sic INT, ticker TEXT, filed TEXT)")
    c.execute("CREATE TABLE delistings (symbol TEXT, name TEXT, exchange TEXT, ipo_date TEXT, delisting_date TEXT, "
              "asset_type TEXT)")
    c.execute("CREATE TABLE historical_listings (ticker TEXT, snapshot_date TEXT, name TEXT, exchange TEXT, "
              "security_type TEXT)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    c.execute("CREATE TABLE symbols (ticker TEXT, security_type TEXT)")
    c.execute("CREATE TABLE edgar_events (cik INT, item TEXT, filed TEXT)")
    for cik, name, t, a, b, still in ((1, "OLDCO INC", "OLD", "2001-01", "2010-06", 0),
                                      (2, "NEWCO CORP", "NEW", "2015-01", "2024-06", 1),
                                      (3, "ACTIVECO", "ACT", "2012-01", "2024-06", 1)):
        c.execute("INSERT INTO edgar_companies VALUES (?,?,?,?,?,5,?)", (cik, name, t, a, b, still))
    fd = pd.DataFrame({"symbol": ["OLD", "OLD", "NEW"], "name": ["Oldco Inc", "Totally Different Holdings", "Newco"],
                       "exchange": ["NYQ", "NMS", "NMS"], "sector": ["Energy", "Retail", "Tech"],
                       "industry": ["Oil", "Shops", "Chips"], "delisted": [True, False, False],
                       "isin": ["US1", "US9", "US2"]})
    fd_path = os.path.join(tmp, "fd2.parquet")
    fd.to_parquet(fd_path, index=False)
    cfg = {"universe_reconstruction": {"financedatabase": {"out": fd_path}}}
    df = ua.build(c, cfg, finsaber_db=os.path.join(tmp, "none.db")).set_index("cik")
    check("ticker + name agree -> attached, sector kept in its own field",
          bool(df.at[1, "in_fd"]) and df.at[1, "fd_sector"] == "Energy" and df.at[1, "fd_delisted"] == True,  # noqa: E712
          df.loc[1, ["in_fd", "fd_sector", "fd_delisted"]].to_dict())
    check("same ticker, different company -> NOT attached (reuse trap)", df.at[1, "fd_isin"] == "US1")
    check("NEWCO CORP vs 'Newco' normalise to one name -> attached", bool(df.at[2, "in_fd"]))
    check("a matched delisted row is listing evidence", df.at[1, "listing_evidence"] == "financedatabase",
          df.at[1, "listing_evidence"])
    check("unmatched rows counted, never added as companies",
          ua.build.fd_stats == {"rows": 3, "matched": 2, "unmatched": 1} and len(df) == 3, ua.build.fd_stats)

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
