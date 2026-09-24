"""
Regression tests for intraday.py (Addendum A I7, Addendum B B8).

Pinned: features are computed from the bars alone (VWAP, distance from open
and from VWAP); a genome over those features fires on the last bar; scan()
records SHADOW signals only and has no path to the execution engine.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import intraday
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def bars(closes):
    idx = pd.date_range("2026-09-24 09:30", periods=len(closes), freq="1min", tz="America/New_York")
    return pd.DataFrame({"Open": closes, "High": [c + 0.1 for c in closes], "Low": [c - 0.1 for c in closes],
                         "Close": closes, "Volume": [1000] * len(closes)}, index=idx)


def main():
    f = intraday.features(bars([100.0] * 10 + [102.0]), "AAA")
    check("feature columns present", all(c in f.columns for c in intraday.FEATURES))
    check("pct_from_open on the last bar", abs(f["pct_from_open"].iloc[-1] - 2.0) < 1e-9, f.iloc[-1].to_dict())
    check("price above VWAP after a jump", f["pct_from_vwap"].iloc[-1] > 0)
    g = {"entry": {"op": "gt", "args": [{"col": "pct_from_vwap"}, {"const": 1.0}]},
         "exit": {"op": "lt", "args": [{"col": "pct_from_vwap"}, {"const": -1.0}]},
         "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 1}}
    v = intraday.evaluate(g, f)
    check("entry fires on the last bar", v["entry"] and not v["exit"], v)
    check("empty bars fire nothing", intraday.evaluate(g, intraday.features(pd.DataFrame(), "X")) ==
          {"entry": False, "exit": False})

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    so.register(c, {"strategy_key": "fx_intra_test", "name": "intra", "family": "intraday_vwap",
                    "league": "tactical", "genome": g, "parameters": {"k": 1}, "source": "factory_template",
                    "intraday": True, "universe": ["AAA", "BBB"]})
    check("intraday strategy discovered", len(intraday.intraday_strategies(c)) == 1)
    out = intraday.scan(c, bars_fn=lambda s: bars([100.0] * 10 + [102.0]))
    rows = [tuple(r) for r in c.execute("SELECT DISTINCT mode FROM intraday_signals").fetchall()]
    check("scan records signals for both symbols", len(out) == 2, out)
    check("every intraday signal is SHADOW (B8)", rows == [("SHADOW",)], rows)
    src = open(os.path.join(ROOT, "intraday.py")).read()
    check("no path to the execution engine", "import execution" not in src and "ExecutionEngine" not in src
          and "import broker" not in src)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
