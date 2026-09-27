"""Regression test for analog_eval.py. Plain script, no pytest."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from analog import COLS, forecast  # noqa: E402
import analog_eval  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def make_lib(seed=7):
    """Synthetic library where COLS[0] drives the forward return."""
    rng = np.random.default_rng(seed)
    dates = ["2011-01-03", "2011-02-01", "2011-03-01", "2011-04-01", "2011-05-02"]
    rows = []
    for i, d in enumerate(dates):
        for t in range(70):
            feats = {c: float(rng.random()) for c in COLS}
            fwd = 0.1 * (feats[COLS[0]] - 0.5) + float(rng.normal(0, 0.002))
            rows.append({
                "ticker": f"T{t:03d}", "date": d, **feats,
                "entry_date": d, "exit_date": dates[min(i + 1, len(dates) - 1)],
                "fwd_ret": fwd,
            })
    return pd.DataFrame(rows)


def main():
    lib = make_lib()
    dates = analog_eval.monthly_dates(lib, start="2011-01-01")
    check("monthly_dates one per month", len(dates) == 5, str(dates))

    res = analog_eval.evaluate(lib, dates, k=20)
    keys = {"n", "auc", "top_decile_ret", "all_ret", "spread", "hit_top"}
    check("overall keys", keys <= set(res["overall"]), str(set(res["overall"])))
    check("by_year present", len(res["by_year"]) >= 1, str(res["by_year"].keys()))
    check("by_year keys", all(keys <= set(v) for v in res["by_year"].values()))
    check("overall auc > 0.6", (res["overall"]["auc"] or 0) > 0.6,
          str(res["overall"]["auc"]))
    check("overall spread > 0", (res["overall"]["spread"] or 0) > 0,
          str(res["overall"]["spread"]))

    # Point-in-time: a query date whose only earlier rows exit later must score
    # nothing, because forecast may only use rows already exited by that date.
    pit = lib.copy()
    pit["exit_date"] = "2099-01-01"
    q = pit[pit["date"] == "2011-05-02"]
    fc = forecast(pit, q, "2011-05-02", 20)
    check("no future analogs used", fc is None or len(fc) == 0,
          f"rows={0 if fc is None else len(fc)}")

    conn = sqlite3.connect(":memory:")
    check("compare_xgb empty without table", analog_eval.compare_xgb(conn, res["rows"]) == {})
    conn.execute("CREATE TABLE oos_predictions (ticker TEXT, date TEXT, fold INT, "
                 "score REAL, label INT)")
    rows = res["rows"][:50]
    for r in rows:
        conn.execute("INSERT INTO oos_predictions VALUES (?,?,?,?,?)",
                     (r["ticker"], r["date"], 1, r["p_up"] * 100,
                      1 if r["fwd_ret"] > 0 else 0))
    conn.commit()
    cmp = analog_eval.compare_xgb(conn, res["rows"])
    check("compare_xgb matches rows", cmp.get("n_matched") == len(rows), str(cmp))
    check("compare_xgb aucs present",
          cmp.get("auc_analog") is not None and cmp.get("auc_xgb") is not None, str(cmp))
    conn.close()

    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        sys.exit(1)
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
