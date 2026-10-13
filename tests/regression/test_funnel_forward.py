"""
funnel.forward_families after Addendum F G2/G3: legacy keys keep their meaning, the new keys exist, a family
with few independent entry dates can never be 'significant' however large its iid t, and the report prose
contains no hardcoded conclusions about particular families.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

import funnel

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def make_db(dates_many=30, dates_few=5):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE paper_runs (run_id TEXT, family TEXT)")
    c.execute("CREATE TABLE paper_trades (run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT, entry_price REAL, "
              "exit_price REAL, shares REAL, gross_pnl_usd REAL, costs_usd REAL, net_pnl_usd REAL, pnl_pct REAL, exit_reason TEXT)")
    rng = np.random.default_rng(1)
    for fam, nd in (("many_dates", dates_many), ("few_dates", dates_few)):
        for f in range(3):
            c.execute("INSERT INTO paper_runs VALUES (?,?)", (f"{fam}{f}", fam))
        for d in range(nd):
            day = f"2026-09-{d + 1:02d}" if d < 28 else f"2026-10-{d - 27:02d}"
            for k in range(8):                              # 8 tickers a day
                base = rng.normal(1.0, 3.0)                 # the day's common move + a little noise per ticker
                for f in range(3):                          # three funds take the same trade (duplicates)
                    r = base + rng.normal(0, 0.2)
                    ep = 20.0
                    sh = 1.0
                    c.execute("INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                              (f"{fam}{f}", f"T{k}", day, day, ep, ep * (1 + r / 100), sh, ep * r / 100, 0.04,
                               ep * r / 100 - 0.04, r, "exit_rule"))
    c.commit()
    return c


def main():
    c = make_db()
    rows = {f["family"]: f for f in funnel.forward_families(c)}
    for k in ("mean", "sd", "t_stat", "margin", "ci_lo", "ci_hi", "win_rate", "significant_iid",
              "mean_net", "cluster_t_date", "cluster_t_ticker", "entry_dates", "luck_88", "significant", "label", "mean_basis"):
        check(f"key present: {k}", k in rows["few_dates"], list(rows["few_dates"]))
    few, many = rows["few_dates"], rows["many_dates"]
    check("the iid t is large because trades are triplicated and share days", few["t_stat"] > 2, few["t_stat"])
    check("a family with 5 independent entry dates is never 'significant'", few["significant"] is False and "only 5" in few["label"], few["label"])
    check("net mean is below the gross mean by the modelled cost", abs((few["mean"] - few["mean_net"]) - 0.2) < 0.01, (few["mean"], few["mean_net"]))
    check("entry dates are counted as the independent units", few["entry_dates"] == 5 and many["entry_dates"] == 30, (few["entry_dates"], many["entry_dates"]))
    check("the date-clustered t is smaller than the iid t", abs(few["cluster_t_date"]) < abs(few["t_stat"]), (few["cluster_t_date"], few["t_stat"]))
    check("the 88-family luck level is about 3.25", abs(few["luck_88"] - 3.25) < 0.02, few["luck_88"])
    check("rows are ranked by the basis mean, best first", [r["mean_basis"] for r in funnel.forward_families(c)] == sorted(
        [r["mean_basis"] for r in funnel.forward_families(c)], reverse=True))

    q = funnel.eight_questions({}, {}, {}, {}, list(rows.values()), {})
    prose = " ".join(x["inference"] + x["fact"] for x in q)
    check("the eight-questions prose has no hardcoded family t-statistics", "t=+8.8" not in prose and "t=+4.5" not in prose and "t=+5.1" not in prose)
    check("the eight-questions prose has no unformatted placeholders", "{need_05" not in prose and "{forward_trades" not in prose, prose[:200])

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
