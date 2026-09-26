import runtime  # noqa: F401
from datetime import date, timedelta

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

import fundamental_features as ff
import sue_features as sf

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + ("  " + str(detail) if detail else ""))
        FAILED.append(name)


def _conn():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE sec_filings (adsh TEXT, cik INTEGER, ticker TEXT, form TEXT, period TEXT, filed TEXT)")
    c.execute("CREATE TABLE sec_facts (adsh TEXT, tag TEXT, ddate TEXT, qtrs INTEGER, value REAL)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    return c


def _filing(c, adsh, ticker, form, period, filed, eps, ddate=None):
    c.execute("INSERT INTO sec_filings VALUES (?,?,?,?,?,?)", (adsh, 1, ticker, form, period, filed))
    c.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)",
              (adsh, "EarningsPerShareBasic", ddate or period, 1, eps))


def _series(c, ticker, quarters):
    # quarters: list of (period, filed, eps); a gap is expressed by omitting a period.
    for i, (period, filed, eps) in enumerate(quarters):
        _filing(c, "%s-%d" % (ticker, i), ticker, "10-Q", period, filed, eps)


def test_year_ago_match_with_gap():
    c = _conn()
    # Quarter ends 2016Q1..2021Q1 with 2020Q3 MISSING; EPS varies so deltas vary (sd > 0).
    ends = ["0331", "0630", "0930", "1231"]
    rows, k = [], 0
    for y in range(2016, 2022):
        for e in ends:
            if (y, e) == (2020, "0930") or (y == 2021 and e != "0331"):
                continue
            k += 1
            rows.append((f"{y}{e}", f"{y}{e[:2]}28" if e != "1231" else f"{y + 1}0201", 1.0 + 0.1 * k + 0.05 * (k % 3)))
    _series(c, "AAA", rows)
    eps = dict((r[0], r[2]) for r in rows)
    sue = sf.compute_sue(sf.quarterly_eps(c, ["AAA"]))
    row = sue[sue["period"] == "20210331"]
    want = eps["20210331"] - eps["20200331"]            # same quarter a year earlier
    four_back = eps["20210331"] - eps["20191231"]       # what a 4-row shift would compare
    check("year-ago match by period date with a gap",
          len(row) == 1 and abs(row.iloc[0]["delta"] - want) < 1e-9 and abs(want - four_back) > 1e-9,
          (row.to_dict("records"), want, four_back))

def test_amendment_replaces():
    c = _conn()
    _filing(c, "A1", "BBB", "10-Q", "20200331", "20200501", 1.0)
    _filing(c, "A2", "BBB", "10-Q/A", "20200331", "20200601", 9.0)
    eps = sf.quarterly_eps(c, ["BBB"])
    check("amendment replaces original for its period",
          len(eps) == 1 and abs(eps.iloc[0]["eps"] - 9.0) < 1e-9, eps.to_dict("records"))


def _long_series(c, ticker, last_eps):
    """Quarters 2016Q1..2020Q1 with varying EPS (so prior deltas have sd > 0); the last is set."""
    ends = ["0331", "0630", "0930", "1231"]
    rows, k = [], 0
    for y in range(2016, 2021):
        for e in ends:
            if y == 2020 and e != "0331":
                continue
            k += 1
            eps = last_eps if (y, e) == (2020, "0331") else 1.0 + 0.1 * k + 0.07 * (k % 3)
            end = date(y, int(e[:2]), int(e[2:]))
            rows.append((end.strftime("%Y%m%d"), (end + timedelta(days=35)).strftime("%Y%m%d"), eps))
    _series(c, ticker, rows)
    return dict((r[0], r[2]) for r in rows)


def test_sd_uses_prior_only():
    c = _conn()
    eps_a = _long_series(c, "CCC", 5.0)
    sue_a = sf.compute_sue(sf.quarterly_eps(c, ["CCC"]))
    c2 = _conn()
    _long_series(c2, "CCC", 50.0)
    sue_b = sf.compute_sue(sf.quarterly_eps(c2, ["CCC"]))
    a = sue_a[sue_a["period"] == "20200331"].iloc[0]
    b = sue_b[sue_b["period"] == "20200331"].iloc[0]
    sd_a, sd_b = a["delta"] / a["sue"], b["delta"] / b["sue"]
    # Changing only the current quarter moves the numerator, never the denominator.
    check("sd uses only previous deltas", abs(sd_a - sd_b) < 1e-9 and abs(b["delta"] - a["delta"] - 45.0) < 1e-9,
          (sd_a, sd_b, a["delta"], b["delta"]))


def test_fewer_than_four_prior():
    c = _conn()
    _series(c, "DDD", [
        ("20190331", "20190501", 1.0),
        ("20190630", "20190801", 2.0),
        ("20190930", "20191101", 3.0),
        ("20191231", "20200201", 4.0),
    ])
    sue = sf.compute_sue(sf.quarterly_eps(c, ["DDD"]))
    check("fewer than 4 prior deltas -> no SUE", sue.empty, sue.to_dict("records"))


def test_availability_and_age():
    c = _conn()
    _long_series(c, "EEE", 5.0)                       # 2020Q1 (period 2020-03-31) filed 2020-05-05
    # Real prices store ISO dates (YYYY-MM-DD).
    for d in ["2020-04-01", "2020-05-05", "2020-05-06", "2020-05-07", "2020-06-01", "2020-07-07",
              "2020-07-08", "2020-09-01"]:
        c.execute("INSERT INTO prices VALUES (?,?,?)", ("EEE", d, 10.0))
    sf.init(c)
    n = sf.project(c, sf.compute_sue(sf.quarterly_eps(c, ["EEE"])))
    rows = dict(c.execute("SELECT date, sue_age FROM daily_sue WHERE ticker='EEE'").fetchall())
    avail = (date(2020, 5, 5) + timedelta(days=ff.LAG_DAYS)).isoformat()
    check("ISO price dates are projected (not silently skipped)", len(rows) > 0, rows)
    # On the filing day the new surprise is not yet usable (and the previous one is > 63 days
    # old); two days later it is. 2020-04-01 carries the PREVIOUS quarter's surprise (57 days).
    check("nothing before filed + LAG_DAYS", "2020-05-05" not in rows and "2020-05-06" not in rows
          and rows.get("2020-05-07") == 2 and rows.get("2020-04-01") == 57, rows)
    check("sue_age counts calendar days from filed", rows.get("2020-06-01") == 27, rows)
    check("rows older than 63 days not written",
          all(v <= sf.MAX_AGE_DAYS for v in rows.values()) and "2020-07-08" not in rows
          and "2020-09-01" not in rows, rows)
    check("project returns row count", n == len(rows), (n, len(rows)))

def test_build_and_coverage():
    c = _conn()
    _long_series(c, "FFF", 5.0)
    for d in ["2020-06-01", "2020-06-02"]:
        c.execute("INSERT INTO prices VALUES (?,?,?)", ("FFF", d, 10.0))
    res = sf.build(c, ["FFF"])
    check("build returns tickers/surprises/daily_rows",
          res["tickers"] == 1 and res["surprises"] >= 1 and res["daily_rows"] == 2, res)
    cov = sf.coverage(c)
    check("coverage reports rows and tickers", cov["rows"] >= 1 and cov["tickers"] == 1, cov)


def main():
    test_year_ago_match_with_gap()
    test_amendment_replaces()
    test_sd_uses_prior_only()
    test_fewer_than_four_prior()
    test_availability_and_age()
    test_build_and_coverage()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
