"""
Regression test for model_calibration.py (Phase 6 §19).

Pinned: a calibrated forecast scores ECE ~0 and positive Brier skill; an
overconfident one with the SAME ranking keeps its AUC but fails calibration —
ranking skill and calibration are separate; bands are fixed, not quantiles;
returns are measured from the NEXT open; costs are charged, and unknown
liquidity pays the widest spread, never zero.

Plain script, no pytest — matches the other tests in tests/regression.
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

import costs as costs_mod
import model_calibration as mc

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    rng = np.random.default_rng(7)
    p = rng.uniform(0.02, 0.6, 200_000)
    y = (rng.uniform(size=p.size) < p).astype(float)
    good = mc.skill_and_calibration(p, y)
    check("calibrated forecast: ECE ~ 0", good["ece"] < 0.01, good["ece"])
    check("calibrated forecast: beats the base-rate Brier and log loss",
          good["brier_skill"] > 0 and good["log_loss"] < good["log_loss_base_rate"], good)
    over = mc.skill_and_calibration(np.clip(p * 1.6, 0, 0.999), y)
    check("same ranking, overconfident: AUC unchanged", abs(over["auc"] - good["auc"]) < 1e-9)
    check("... but calibration fails (ECE up, Brier skill down)",
          over["ece"] > 0.1 and over["brier_skill"] < good["brier_skill"], over)
    check("reliability uses fixed 10% bands", [t["band"] for t in good["reliability"]][:3] == ["0%-10%", "10%-20%", "20%-30%"])
    check("0-100 scores are rescaled", mc.probabilities(pd.Series([25.0, 50.0])).tolist() == [0.25, 0.5])

    cfg = {"costs": {}}
    cm = costs_mod.CostModel(cfg)
    f = pd.DataFrame({"p": [0.05, 0.05, 0.95, 0.95], "label": [0, 0, 1, 1],
                      "ret": [-0.01, -0.01, 0.03, 0.03], "dv": [1e9, None, 1e9, 1e9]})
    e = mc.economic(f, cm)
    b = {x["band"]: x for x in e["buckets"]}
    check("precision by band = hit rate", b["0%-10%"]["precision"] == 0 and b["90%-100%"]["precision"] == 1)
    check("net = gross - cost, cost > 0", b["90%-100%"]["net_mean"] < b["90%-100%"]["gross_mean"]
          and b["90%-100%"]["cost_mean"] > 0)
    unk = cm.round_trip(20.0, dollar_volume=0.0) / 20
    liq = cm.round_trip(20.0, dollar_volume=1e9) / 20
    check("unknown liquidity pays the widest spread, never zero", unk > liq)

    # End to end on a tiny database: returns from the NEXT open.
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE oos_predictions (ticker TEXT, date TEXT, fold TEXT, score REAL, label INTEGER)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL)")
    days = pd.bdate_range("2024-01-01", periods=30).strftime("%Y-%m-%d")
    for t, drift in (("UP", 1.01), ("DN", 0.99)):
        for i, d in enumerate(days):
            c.execute("INSERT INTO prices VALUES (?,?,?)", (t, d, 100 * drift ** i))
            c.execute("INSERT INTO features VALUES (?,?,1e9)", (t, d))
            if i < 20:
                c.execute("INSERT INTO oos_predictions VALUES (?,?,'f',?,?)",
                          (t, d, 0.9 if t == "UP" else 0.1, 1 if t == "UP" else 0))
    r = mc.measure(c, {"labeling": {"horizon_days": 5}, "costs": {}}, sample=None)
    top = [x for x in r["economic"]["buckets"] if x["band"] == "90%-100%"][0]
    check("next-open -> open+5 return (1.01^5 - 1)", abs(top["gross_mean"] - (1.01 ** 5 - 1)) < 1e-9, top)
    check("verdict answers all four questions separately", set(r["verdict"]) ==
          {"classification_skill", "calibration", "economic_value", "trading_performance"}, r["verdict"])
    print(mc.render(r))

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
