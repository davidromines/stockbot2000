"""
Regression test: the exit_rules sweep (exit_sweep.py) and the simulator's
trailing stop it depends on.

Pinned:
  - trailing_atr_multiple exits when a close falls k x ATR below the highest
    close since entry, fills at the NEXT open, and is labelled trailing_stop
  - no trailing gene -> the simulator result is unchanged (existing results
    stay comparable)
  - take_profit_pct exits at the target, next open
  - the grid: as_is first, then every take-profit x trail combination; None
    REMOVES a gene rather than setting it to null
  - the pre-registered adoption rule: beat as_is over the window AND in a
    majority of blocks — winning the total on one block is not enough
  - registration freezes the slot strategies into the spec, once

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import costs
import exit_sweep as xs
import experiment_registry as er
import simulator

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


# Signal on bar 1 (close 100.5), fill at bar 2 open 101. Rises to a 120 close
# on bar 5, falls back; ATR 4.
CLOSE = [100, 100.5, 104, 110, 116, 120, 113, 108, 100, 95, 94, 93]
OPEN_ = [100, 100.5, 101, 105, 111, 117, 119, 112, 107, 99, 94, 93]


def run(risk):
    df = pd.DataFrame({"ticker": ["X"] * 12, "date": pd.date_range("2020-01-01", periods=12, freq="D"),
                       "close": np.array(CLOSE, dtype="float64"), "open": np.array(OPEN_, dtype="float64"),
                       "atr_14": [4.0] * 12, "dollar_volume_20": [5e7] * 12})
    panel = simulator.Panel(df, max_hold=9, exit_prices=df[["ticker", "date", "close", "open"]])
    g = {"entry": {"op": "and", "args": [{"op": "gt", "args": [{"col": "close"}, {"const": 100.2}]},
                                         {"op": "lt", "args": [{"col": "close"}, {"const": 100.8}]}]},
         "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]},
         "risk": {"max_hold_days": 9, "stop_atr_multiple": 2.0, **risk}}
    return simulator.simulate(g, panel, costs.CostModel({"costs": {"enabled": False}}), position_size_usd=100.0)


def main():
    base = run({})
    check("no profit exit: holds to max_hold", base["exit_reason"][0] == "max_hold", base["exit_reason"])
    check("fill at next open (101)", abs(base["entry_price"][0] - 101.0) < 1e-9, base["entry_price"])

    t = run({"trailing_atr_multiple": 2.0})
    # peak 120 (bar 5) -> level 112; bar 7 closes 108 <= 112 -> fill bar 8 open 107
    check("trailing stop exits after the peak, next open",
          t["exit_reason"][0] == "trailing_stop" and abs(t["exit_price"][0] - 107.0) < 1e-9,
          (t["exit_reason"], t["exit_price"]))
    check("and books the gain the plain rule gave back", t["net_pnl_usd"] > base["net_pnl_usd"],
          (t["net_pnl_usd"], base["net_pnl_usd"]))
    check("trailed count reported", t["n_trailed"] == 1, t["n_trailed"])

    p = run({"take_profit_pct": 10.0})
    # target 111.1; bar 4 closes 116 -> fill bar 5 open 117
    check("take-profit exits at the target, next open",
          p["exit_reason"][0] == "take_profit" and abs(p["exit_price"][0] - 117.0) < 1e-9,
          (p["exit_reason"], p["exit_price"]))

    c = xs.cells()
    check("grid: as_is first, then 4 x 3 combinations", c[0][0] == xs.AS_IS and len(c) == 13, [x[0] for x in c])
    g0 = {"entry": {}, "risk": {"stop_atr_multiple": 2.0, "take_profit_pct": 15.0}}
    g1 = xs.apply(g0, {"take_profit_pct": None, "trailing_atr_multiple": 3.0})
    check("None removes the gene; values set; original untouched",
          "take_profit_pct" not in g1["risk"] and g1["risk"]["trailing_atr_multiple"] == 3.0
          and g0["risk"]["take_profit_pct"] == 15.0, (g0, g1))

    def rows(block_nets):
        out = []
        for cell, nets in block_nets.items():
            for i, n in enumerate(nets):
                out.append({"block": f"b{i}", "strategy": "S", "cell": cell, "trades": 10, "gross": n * 10,
                            "costs": 0.0, "net": n * 10, "excess": 0.0, "win": 0.5, "n_tp": 0,
                            "n_trail": 0, "n_stop": 0})
        return out
    v = xs.verdicts(xs.combine(rows({xs.AS_IS: [0.1, 0.1, 0.1], "A": [0.2, 0.2, 0.0], "B": [0.9, 0.0, 0.0]})))
    check("wins the window and 2 of 3 blocks -> adoptable", v[("S", "A")]["adoptable"], v[("S", "A")])
    check("wins the window on ONE block -> not adoptable", not v[("S", "B")]["adoptable"]
          and v[("S", "B")]["beats_window"], v[("S", "B")])

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    xs.slot_strategies = lambda c, cfg: {"fx_a@v1": {"entry": {"op": "gt"}, "risk": {"max_hold_days": 20}}}
    s1 = xs.ensure_registered(conn, {}, ("2006-01-01", "2019-12-31"))
    xs.slot_strategies = lambda c, cfg: {"fx_other@v9": {"entry": {"op": "lt"}}}
    s2 = xs.ensure_registered(conn, {}, ("2006-01-01", "2019-12-31"))
    e = er.get(conn, xs.EXPERIMENT)
    check("registered once, RUNNING, strategies frozen in the spec",
          e["status"] == er.RUNNING and list(s1["entry_rule"]) == ["fx_a@v1"] and s2 == s1, (e["status"], s2))

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
