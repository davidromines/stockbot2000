"""
Stage P4 — per-trade stop from a column (risk.stop_pct_col): the simulator stops at
entry x (1 + column value at the signal bar) when that is tighter than the ATR stop;
a stray positive value never puts a stop above entry; the ranking keeps such a
strategy out of the live slots (the live stop plan does not carry it yet).
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import costs
import simulator
import strategy_factory as sf

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


# Entry on bar 2 (close 102), filled at bar 3's open 103. Bar 4 closes 97: 5.8% below
# entry — inside a 2x5 ATR stop (93) but below a -5% analog stop (97.85).
close = [100, 101, 102, 103, 97, 97, 97, 97, 97, 97, 97, 97]


def run(q10):
    df = pd.DataFrame({"ticker": ["X"] * 12, "date": pd.date_range("2020-01-01", periods=12, freq="D"),
                       "close": np.array(close, "float64"), "open": np.array(close, "float64"),
                       "atr_14": [5.0] * 12, "dollar_volume_20": [5e7] * 12, "analog_q10": [q10] * 12})
    panel = simulator.Panel(df, max_hold=6, exit_prices=df[["ticker", "date", "close", "open"]])
    g = {"entry": {"op": "and", "args": [{"op": "gt", "args": [{"col": "close"}, {"const": 101.5}]},
                                         {"op": "lt", "args": [{"col": "close"}, {"const": 102.5}]}]},
         "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]},
         "risk": {"max_hold_days": 6, "stop_atr_multiple": 2.0, "stop_pct_col": "analog_q10"}}
    return simulator.simulate(g, panel, costs.CostModel({"costs": {"enabled": False}}), position_size_usd=100.0)


def main():
    r = run(-0.05)
    check("a -5% analog stop fires where the ATR stop would not", r["exit_reason"][0] == "stop_loss", r["exit_reason"])
    r2 = run(-0.20)
    check("a looser analog stop leaves the tighter ATR stop in charge (no exit at -5.8%)",
          r2["exit_reason"][0] != "stop_loss", r2["exit_reason"])
    r3 = run(0.30)
    check("a positive value is clipped: no stop above entry, so no instant stop-out",
          r3["exit_reason"][0] != "stop_loss" or r3["exit_price"][0] < 103, (r3["exit_reason"], r3["exit_price"]))
    r4 = run(np.nan)
    check("a missing value falls back to the ATR stop alone", r4["exit_reason"][0] != "stop_loss")
    fam = sf.F.get("analog_stop")
    check("analog_stop family carries stop_pct_col = analog_q10",
          fam is not None and fam["build"]({"q": 0.9, "hold": 20, "stop": 3.0})["risk"]["stop_pct_col"] == "analog_q10")
    import ranking
    src = open(ranking.__file__).read()
    check("the ranking keeps per-trade column stops out of the live slots", "stop_pct_col" in src and
          "not supported by the live stop plan" in src)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
