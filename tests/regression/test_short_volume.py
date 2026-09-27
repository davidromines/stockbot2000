"""short_volume.py: both FINRA file layouts parse; the 20-session ratio is
sum(short)/sum(total) through each date; missing data stays NaN. In memory."""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import short_volume as sv

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    new = "Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market\n20260925|AAA|40|0|100|B,Q\n12\n"
    old = "Date|Symbol|ShortVolume|TotalVolume|Market\n20100104|AAA|30|60|Q\n"
    check("consolidated layout: total is the 5th column", sv.parse(new) == {"AAA": (40.0, 100.0)}, sv.parse(new))
    check("facility layout: total is the 4th column; trailer skipped", sv.parse(old) == {"AAA": (30.0, 60.0)})
    c = sqlite3.connect(":memory:")
    sv.init(c)
    dates = pd.bdate_range("2026-08-03", periods=25).strftime("%Y-%m-%d").tolist()
    c.executemany("INSERT INTO short_volume VALUES ('AAA', ?, ?, 100)", [(d, 50.0 if i < 20 else 10.0) for i, d in enumerate(dates)])
    df = pd.DataFrame({"_t": ["AAA", "AAA", "BBB"], "_d": [dates[9], dates[-1], dates[-1]]})
    out = sv.attach(c, df, dates[0], dates[-1], ["AAA", "BBB"])
    r = out.set_index(["_t", "_d"])["short_volume_ratio_20"]
    check("ratio over the last 20 sessions", abs(r[("AAA", dates[-1])] - (15 * 50 + 5 * 10) / 2000) < 1e-6, r.to_dict())
    check("10 sessions is enough (min periods)", abs(r[("AAA", dates[9])] - 0.5) < 1e-6)
    check("no data -> NaN, never zero", pd.isna(r[("BBB", dates[-1])]))
    check("row count unchanged", len(out) == 3)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
