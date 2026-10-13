"""
audit_forward.py (Addendum F, Phase A1-A3): the statistics and the honest-fill recompute.

No network, no real database. The things that matter: duplicated trades must inflate the iid t but
not the cluster-robust t; the luck threshold must match the known normal-maximum values; a label above
'unresolved' must never come from too few independent dates; and the next-open recompute must use the
open of the session AFTER each recorded date.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import audit_forward as af

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def make_db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE paper_runs (run_id TEXT, family TEXT, created_at TEXT, capital_usd REAL)")
    c.execute("CREATE TABLE paper_trades (run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT, entry_price REAL, "
              "exit_price REAL, shares REAL, gross_pnl_usd REAL, costs_usd REAL, net_pnl_usd REAL, pnl_pct REAL, exit_reason TEXT)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, close REAL)")
    c.execute("INSERT INTO paper_runs VALUES ('r1','fam','2026-09-20',400)")
    dates = [f"2026-09-{d:02d}" for d in range(1, 9)]
    for k in range(12):
        tk = f"T{k}"
        opens = [10, 11, 12, 13, 14, 15, 16, 17]
        closes = [10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5]
        for d, o, cl in zip(dates, opens, closes):
            c.execute("INSERT INTO prices VALUES (?,?,?,?)", (tk, d, o, cl))
        entry, exit_ = dates[1 + k % 3], dates[3 + k % 3]
        ep, xp = closes[1 + k % 3], closes[3 + k % 3]
        shares = 20 / ep
        gross = shares * (xp - ep)
        cost = 0.04
        c.execute("INSERT INTO paper_trades VALUES ('r1',?,?,?,?,?,?,?,?,?,?,?)",
                  (tk, entry, exit_, ep, xp, shares, gross, cost, gross - cost, (xp / ep - 1) * 100, "exit_rule"))
    # a spin-off style trade: recorded entry far above the (adjusted) close that day
    c.execute("INSERT INTO paper_trades VALUES ('r1','T0','2026-09-02','2026-09-04',50,13.5,0.4,-14.6,0.04,-14.64,-73,'exit_rule')")
    # a trade that exits on the last stored bar: its next-open exit price does not exist yet
    c.execute("INSERT INTO paper_trades VALUES ('r1','T2','2026-09-07','2026-09-08',16.5,17.5,1.2,1.2,0.04,1.16,6.06,'exit_rule')")
    c.commit()
    return c


def main():
    # --- pure statistics
    x = np.array([1.0, -1.0, 2.0, 0.0, 3.0, -2.0, 1.5, 0.5])
    s = af.iid_stats(x)
    check("iid t equals mean / (sd / sqrt n)", abs(s["t"] - x.mean() / (x.std(ddof=1) / math.sqrt(len(x)))) < 1e-12, s)

    dates = ["d1", "d1", "d2", "d2", "d3", "d3", "d4", "d4"]
    base_c = af.cluster_stats(x, dates)
    k = 5
    xd = np.repeat(x, k)
    dd = np.repeat(dates, k)
    dup_c = af.cluster_stats(xd, dd)
    check("duplicating every trade 5x leaves the cluster t unchanged", abs(base_c["t"] - dup_c["t"]) < 1e-9, (base_c, dup_c))
    check("...but inflates the iid t by about sqrt(5)",
          abs(af.iid_stats(xd)["t"] / af.iid_stats(x)["t"] - math.sqrt(5)) < 0.2, (af.iid_stats(xd)["t"], af.iid_stats(x)["t"]))

    df = pd.DataFrame({"ticker": ["A", "A", "B"], "entry_date": ["d1", "d1", "d1"], "run_id": ["r1", "r2", "r1"],
                       "pnl_pct": [2.0, 4.0, 1.0]})
    dp = af.dedupe(df).set_index("ticker")
    check("dedupe averages funds on the same (ticker, entry date)", abs(dp.loc["A", "pnl_pct"] - 3.0) < 1e-12 and dp.loc["A", "funds"] == 2, dp)

    b1 = af.bootstrap_by_cluster(x, dates)
    b2 = af.bootstrap_by_cluster(x, dates)
    check("bootstrap is deterministic for a fixed seed", b1 == b2)
    check("bootstrap interval brackets the mean", b1["lo"] <= x.mean() <= b1["hi"], (b1, x.mean()))

    check("luck threshold for 88 tests is about 3.25", abs(af.luck_threshold(88) - 3.25) < 0.02, af.luck_threshold(88))
    check("luck threshold rises with the number of tests", af.luck_threshold(88) < af.luck_threshold(1405) < af.luck_threshold(127652))

    check("too few independent dates gives 'unresolved' even for a huge t",
          af.classify(9.0, 1.0, 10).startswith("Unresolved: only 10"), af.classify(9.0, 1.0, 10))
    check("a strong result over enough dates is only 'promising', never 'eligible' or 'supported'",
          af.classify(5.0, 0.5, 40).startswith("Promising") and "ligible" not in af.classify(5.0, 0.5, 40) and "upported" not in af.classify(5.0, 0.5, 40))
    check("significant but inside the 88-family luck range stays unresolved", af.classify(3.0, 0.2, 40).startswith("Unresolved: significant"))

    # --- database-level
    conn = make_db()
    r = af.audit_family(conn, "fam")
    check("all 14 trades are read", r["n"] == 14, r["n"])
    check("pnl_pct is recognised as the GROSS move, not net", r["pnl_pct_matches_gross"] > 0.9 and r["pnl_pct_matches_net"] < 0.2,
          (r["pnl_pct_matches_gross"], r["pnl_pct_matches_net"]))
    check("entry price equals the close on the entry date for the regular trades", r["entry_equals_close"] > 0.9, r["entry_equals_close"])
    check("the spin-off style trade is flagged as a corporate action", r["ca_flagged"] == 1, r["ca_flagged"])

    d = af.attach_prices(conn, af.load_trades(conn, "fam"))
    row = d[(d["ticker"] == "T1") & (d["entry_date"] == "2026-09-03")].iloc[0]
    # T1: entry on the 3rd (index 2), exit on the 5th (index 4); next opens are the 4th (13) and 6th (15)
    check("next-open entry is the open of the session after the entry date", row["open_next_entry"] == 13, row["open_next_entry"])
    check("next-open exit is the open of the session after the exit date", row["open_next_exit"] == 15, row["open_next_exit"])
    honest = (row["open_next_exit"] / row["open_next_entry"] - 1) * 100
    check("honest gross move 15/13 - 1", abs(honest - (15 / 13 - 1) * 100) < 1e-9, honest)
    check("a trade exiting on the last stored bar has no next-open price and is excluded from basis D", r["honest_rows"] == r["n"] - 1, (r["honest_rows"], r["n"]))
    check("the corrected basis D never reports more rows than basis C", r["bases"][list(r["bases"])[3]]["iid"]["n"] == r["bases"][list(r["bases"])[2]]["iid"]["n"])

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
