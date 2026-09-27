"""analog.py: exact nearest neighbours, no analog whose outcome was unknown at the
query date, outcome summary, and the score attach (newest score, at most 10 days old)."""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import analog

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    rng = np.random.default_rng(1)
    lib_x = rng.random((500, 5)).astype(np.float32)
    q = rng.random((7, 5)).astype(np.float32)
    idx, dist = analog.neighbours(lib_x, q, k=10, chunk=3)
    brute = np.argsort(((q[:, None, :] - lib_x[None]) ** 2).sum(2), 1)[:, :10]
    check("nearest neighbours match brute force", (idx == brute).all())
    check("distances ascending", (np.diff(dist, axis=1) >= -1e-6).all())

    n = 300
    lib = pd.DataFrame({c: rng.random(n).astype(np.float32) for c in analog.COLS})
    lib["ticker"] = [f"T{i}" for i in range(n)]
    lib["date"] = "2020-01-02"
    lib["exit_date"] = ["2020-02-03"] * 150 + ["2020-06-01"] * 150
    lib["fwd_ret"] = np.where(np.arange(n) < 150, 0.05, -0.05).astype(np.float32)
    qry = lib.iloc[:5].copy()
    qry["date"] = "2020-03-02"
    f = analog.forecast(lib, qry, "2020-03-02", k=50)
    check("only analogs whose outcome was known by the query date (all +5%)",
          (f["p_up"] == 1.0).all() and (f["n"] == 50).all(), f[["p_up", "n"]].to_dict())
    check("no known analogs -> empty", analog.forecast(lib, qry, "2020-01-15", k=50).empty)
    s = analog.summarize(np.array([0.1, -0.1, 0.2, np.nan, 0.05], dtype=float))
    check("summary ignores unknown outcomes", s["n"] == 4 and s["p_up"] == 0.75, s)

    tmp = Path(tempfile.mkdtemp()) / "scores.parquet"
    real = analog.SCORES
    analog.SCORES = tmp
    pd.DataFrame({"ticker": ["AAA", "AAA"], "date": ["2024-01-02", "2024-01-09"],
                  "analog_p_up": [0.6, 0.7], "analog_mean": [0.01, 0.02], "analog_q10": [-0.05, -0.04],
                  "analog_n": [200, 200]}).to_parquet(tmp, index=False)
    df = pd.DataFrame({"_t": ["AAA", "AAA", "AAA", "BBB"], "_d": ["2024-01-05", "2024-01-10", "2024-01-25", "2024-01-10"]})
    out = analog.attach(df, "2024-01-05", "2024-01-25", ["AAA", "BBB"])
    v = out["analog_p_up"].tolist()
    check("attach: newest score at or before each date; stale (>10 days) and unscored -> NaN",
          abs(v[0] - 0.6) < 1e-6 and abs(v[1] - 0.7) < 1e-6 and np.isnan(v[2]) and np.isnan(v[3]), v)
    check("attach keeps row order and count", out["_d"].tolist() == df["_d"].tolist())
    analog.SCORES = real
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
