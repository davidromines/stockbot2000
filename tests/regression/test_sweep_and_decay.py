"""
Regression test for stop_sweep.py and signal_decay.py (Phase 6 §13, §20;
§30 checklist items "stop sweep works" and "signal decay analysis works").

Pinned, stop sweep: blocks cover the registered window exactly; resumability
reads back what was written; combining blocks sums trades and net and weights
the win rate by trades; the registered claim (tight beats wide, per trade)
can come out either way.

Pinned, signal decay: returns are measured from the NEXT open; a score that
really sorts forward returns is found at every horizon; the verdict is
sign-aware (a top decile that UNDERperforms is "inverted", not "decaying");
a random score is "nonexistent".

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import signal_decay as sd
import stop_sweep as ss

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def sweep_tests():
    b = ss._blocks(("2006-01-01", "2019-12-31"), 4)
    check("blocks cover the window exactly", b[0][0] == "2006-01-01" and b[-1][1] == "2019-12-31"
          and all(pd.Timestamp(b[i][1]) + pd.Timedelta(days=1) == pd.Timestamp(b[i + 1][0]) for i in range(len(b) - 1)), b)
    p = Path(tempfile.mkdtemp()) / "sweep.jsonl"
    p.write_text("\n".join(json.dumps({"block": "2006", "entry": "rising_200", "hold": 10, "stop": s})
                           for s in (1.0, 2.0)) + "\n")
    check("resume skips what is on disk", ss._done(p) == {("2006", "rising_200", 10, 1.0), ("2006", "rising_200", 10, 2.0)})
    rows = [{"block": "a", "entry": "e", "hold": 10, "stop": 2.0, "trades": 10, "net": -5.0, "excess": -1.0,
             "win": 0.2, "gap_loss": 0.0, "stopped": 1},
            {"block": "b", "entry": "e", "hold": 10, "stop": 2.0, "trades": 30, "net": 1.0, "excess": 0.5,
             "win": 0.6, "gap_loss": 0.0, "stopped": 2},
            {"block": "a", "entry": "e", "hold": 10, "stop": 6.0, "trades": 0, "net": 0, "excess": 0, "win": 0,
             "gap_loss": 0, "stopped": 0}]
    c = ss.combine(rows)
    check("combine sums blocks and drops empty cells", len(c) == 1 and c[0]["trades"] == 40 and c[0]["net"] == -4.0
          and c[0]["blocks"] == 2, c)
    check("win rate weighted by trades", abs(c[0]["win"] - (0.2 * 10 + 0.6 * 30) / 40) < 1e-12, c[0]["win"])
    cells = [{"stop": 2.0, "net_per_trade": 0.1}, {"stop": 6.0, "net_per_trade": -0.2}]
    check("claim can hold", ss.tight_vs_wide(cells)["verdict"] == "HOLDS")
    cells = [{"stop": 2.0, "net_per_trade": -0.3}, {"stop": 6.0, "net_per_trade": -0.2}]
    check("claim can fail (the 2026-09-24 result)", ss.tight_vs_wide(cells)["verdict"] == "does NOT hold")
    check("no wide cells: no verdict", ss.tight_vs_wide([{"stop": 2.0, "net_per_trade": 1}]) is None)


def decay_db(sign: float, noise: bool = False):
    """40 tickers over 120 sessions; each ticker drifts; score = its drift (or noise)."""
    rng = np.random.default_rng(3)
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE oos_predictions (ticker TEXT, date TEXT, fold TEXT, score REAL, label INTEGER)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL)")
    days = pd.bdate_range("2020-01-01", periods=120).strftime("%Y-%m-%d")
    for k in range(40):
        drift = (k - 20) / 2000
        px = 100 * np.cumprod(1 + drift + rng.normal(0, 0.002, len(days)))
        for i, d in enumerate(days):
            c.execute("INSERT INTO prices VALUES (?,?,?)", (f"T{k}", d, float(px[i])))
            if i < 90:
                s = rng.uniform() if noise else 0.5 + sign * drift * 10
                c.execute("INSERT INTO oos_predictions VALUES (?,?,'f',?,0)", (f"T{k}", d, float(s)))
    return c


def decay_tests():
    r = sd.measure(decay_db(+1), sample=None)
    check("a score that sorts returns: positive at every horizon", r["verdict"].startswith("persistent"), r["verdict"])
    h1 = r["horizons"][1]
    check("spread measured from the next open (top > bottom)", h1["top_mean"] > h1["bottom_mean"], h1)
    r = sd.measure(decay_db(-1), sample=None)
    check("an inverted score is reported as inverted, not decaying", r["verdict"].startswith("inverted"), r["verdict"])
    r = sd.measure(decay_db(+1, noise=True), sample=None)
    check("a random score is nonexistent", r["verdict"].startswith("nonexistent"), r["verdict"])


def main():
    sweep_tests()
    decay_tests()
    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
