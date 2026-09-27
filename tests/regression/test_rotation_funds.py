"""
ETF rotation in the tournament: a variant with a positive backtest and validation reaches
PAPER with one unseen-window result stored; a losing backtest is REJECTED; the paper
engine buys the fund's holdings once a month and marks daily; a slot's candidates are the
fund's holdings and its exit fires when the fund rotates out. rotation.backtest / current
are stubbed; in-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import pandas as pd

import holdout
import league
import paper_trading as pt
import rotation
import rotation_funds as rf
import strategy_objects as so

FAILED = []
CFG = {"risk": {"position_size_usd": 20.0, "max_open_positions": 5}, "paper": {"positions": 20},
       "costs": {"enabled": False}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def bt(mean):
    return {"n_trades": 40, "mean_net": mean, "mean_gross": mean + 0.001, "win_rate": 0.6, "cagr": 0.08,
            "max_drawdown": 0.2, "benchmark_cagr": 0.1, "trades": [], "equity": pd.Series([1.0])}


def main():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, close REAL)")
    c.executemany("INSERT INTO prices VALUES (?,?,?,?)", [("SPY", "2026-09-24", 1, 700), ("XLK", "2026-09-24", 1, 250),
                                                          ("XLE", "2026-09-24", 1, 90), ("SHY", "2026-09-24", 1, 82)])
    so.init(c); league.init(c); pt.init(c); holdout.init(c)
    good, bad = rf.variants()[0], rf.variants()[1]
    close = pd.DataFrame({"SPY": [700.0]}, index=["2026-09-24"])
    rotation.backtest = lambda cl, op, p, a, b, cost_bps=5.0: bt(0.01 if p is good else -0.002)
    import factory_pipeline as fp
    r1 = rf.evaluate(c, CFG, good, close, close, "2026-09-24")
    r2 = rf.evaluate(c, CFG, bad, close, close, "2026-09-24")
    check("a positive backtest + validation reaches PAPER", r1["state"] == "PAPER", r1)
    check("a losing backtest is REJECTED", r2["state"] == "REJECTED", r2)
    check("one unseen-window result stored for the survivor",
          holdout.result(c, r1["key"], 1) is not None and holdout.result(c, r2["key"], 1) is None)
    check("the survivor has a paper fund with the rotation rule", c.execute(
        "SELECT COUNT(*) FROM paper_runs WHERE strategy LIKE '%rotation%'").fetchone()[0] == 1)
    check("re-running registers nothing new", rf.evaluate(c, CFG, good, close, close, "2026-09-24").get("state") == "PAPER")
    check("12 declared variants", len(rf.variants()) == 12)

    rotation.current = lambda conn, params, as_of=None: {"holdings": ["XLK", "XLE"], "ranked": [], "as_of": as_of}
    run = dict(c.execute("SELECT * FROM paper_runs WHERE strategy LIKE '%rotation%'").fetchone())
    pt._rotation_step(c, CFG, run, "2026-09-24", __import__("costs").CostModel(CFG))
    held = {r[0] for r in c.execute("SELECT ticker FROM paper_positions WHERE run_id=?", (run["run_id"],))}
    check("the paper fund buys the fund's holdings", held == {"XLK", "XLE"}, held)
    check("and marks its equity", c.execute("SELECT COUNT(*) FROM paper_equity WHERE run_id=?",
                                             (run["run_id"],)).fetchone()[0] == 1)

    import slot_trader as st
    cands, exits = st._rotation_signals(c, rf.genome(good))
    check("a slot's candidates are the fund's holdings, in order", list(cands["ticker"]) == ["XLK", "XLE"])
    check("the exit fires when the fund rotates out", "XLF" in exits and "XLK" not in exits)
    import stop_plans
    check("the live stop plan is valid (a 3 x ATR price stop)", stop_plans.validate(stop_plans.from_genome(rf.genome(good)))[0])
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
