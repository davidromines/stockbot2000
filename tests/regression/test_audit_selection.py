"""
Addendum F A4-A5: the multiple-testing helpers (Holm, Benjamini-Hochberg, Nyholt, max-T sign-flip) against known
values and known behaviour, the retroactive-replay flag, and the SPY excess calculation. Synthetic data only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import audit_selection as a4
import forward_stats as fs

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    p = [0.01, 0.04, 0.03, 0.005]
    h = fs.holm(p)
    check("Holm matches the hand calculation", np.allclose(h, [0.03, 0.06, 0.06, 0.02]), h)
    bh = fs.benjamini_hochberg(p)
    check("Benjamini-Hochberg matches the hand calculation", np.allclose(bh, [0.02, 0.04, 0.04, 0.02]), bh)
    check("adjusted p-values are never below the raw p", all(x >= y for x, y in zip(h, p)) and all(x >= y for x, y in zip(bh, p)))
    check("NaN p-values stay NaN and are not counted", math.isnan(fs.holm([0.01, float("nan")])[1]) and fs.holm([0.01, float("nan")])[0] == 0.01)

    check("Nyholt: independent tests give M", abs(fs.nyholt_meff(np.eye(6)) - 6) < 1e-9)
    check("Nyholt: perfectly correlated tests give 1", abs(fs.nyholt_meff(np.ones((6, 6))) - 1) < 1e-9)
    check("a t of 0 has a one-sided p of 0.5", abs(fs.t_pvalue_one_sided(0.0, 9) - 0.5) < 1e-12)
    check("a large t has a small p and fewer df make it larger", fs.t_pvalue_one_sided(3.0, 20) < fs.t_pvalue_one_sided(3.0, 3) < 0.1)

    rng = np.random.default_rng(5)
    noise = pd.DataFrame(rng.normal(0, 1, (30, 12)), index=[f"d{i:02d}" for i in range(30)], columns=[f"f{i}" for i in range(12)])
    r = fs.maxt_signflip(noise, reps=4000)
    check("pure noise: no family is significant after the max-T adjustment", r["p_maxT"].min() > 0.05, r["p_maxT"].min())
    sig = noise.copy()
    sig["f0"] = sig["f0"] + 1.5
    r2 = fs.maxt_signflip(sig, reps=4000)
    check("a real effect in one family survives the max-T adjustment", r2.loc["f0", "p_maxT"] < 0.01, r2.loc["f0"].to_dict())
    check("the max-T adjusted p is never below the family's own sign-flip p", bool((r2["p_maxT"] >= r2["p_own"] - 1e-12).all()))
    sparse = noise.copy()
    sparse.iloc[:, 3] = np.nan
    sparse.iloc[:2, 3] = 1.0
    check("a family with fewer than 3 dates is not tested", math.isnan(fs.maxt_signflip(sparse, reps=500).loc["f3", "p_maxT"]))

    sess = ["2026-09-23", "2026-09-24", "2026-09-25", "2026-09-28", "2026-09-29"]
    df = pd.DataFrame({"created": ["2026-09-27"] * 3, "entry_date": ["2026-09-24", "2026-09-25", "2026-09-28"]})
    out = a4.retro_flag(df, sess)
    check("an entry before the last completed session at creation is retroactive; the first normal step is not",
          out["retro"].tolist() == [True, False, False], out[["entry_date", "first_session", "retro"]].values.tolist())

    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, close REAL)")
    for d, o in zip(sess, [100, 101, 102, 103, 104]):
        c.execute("INSERT INTO prices VALUES ('SPY',?,?,?)", (d, o, o))
    tr = pd.DataFrame({"entry_date": ["2026-09-23"], "exit_date": ["2026-09-25"], "net_pct": [5.0]})
    ex = a4.add_spy(c, tr, sess)
    # next opens: entry -> 09-24 (101), exit -> 09-28 (103): SPY +1.98%
    check("SPY return uses the same next-session opens as the restatement", abs(ex["spy_pct"].iloc[0] - (103 / 101 - 1) * 100) < 1e-9, ex["spy_pct"].iloc[0])
    check("excess = net minus SPY", abs(ex["excess_pct"].iloc[0] - (5.0 - (103 / 101 - 1) * 100)) < 1e-9)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
