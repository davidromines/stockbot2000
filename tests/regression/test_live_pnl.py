"""
live_pnl.py: the real account's slot trades only — pairing, gross / costs / net,
open marks, and a mode filter. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import live_pnl

FAILED = []
CFG = {"costs": {"sec_fee_per_million_usd": 27.80, "finra_taf_per_share_usd": 0.000166, "finra_taf_cap_usd": 8.30}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INT, strategy_key TEXT,"
              " version INT, symbol TEXT, action TEXT, quantity REAL, price REAL)")
    c.execute("CREATE TABLE slot_marks (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INT, symbol TEXT, price REAL)")
    c.execute("CREATE TABLE paper_runs (run_id TEXT, name TEXT, label TEXT)")
    c.execute("INSERT INTO paper_runs VALUES ('abc', 'n', 'Value Book')")
    ins = "INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price) VALUES (?,?,?,?,?,?,?,?,?)"
    c.executemany(ins, [
        ("2026-09-24T15:00:00+00:00", "LIVE", 1, "paper:abc", 1, "AAA", "OPEN", 0.2, 100.0),
        ("2026-09-25T15:00:00+00:00", "LIVE", 1, "paper:abc", 1, "AAA", "CLOSE", 0.2, 110.0),
        ("2026-09-24T15:00:00+00:00", "LIVE", 2, "x", 1, "BBB", "OPEN", 1.0, 20.0),
        ("2026-09-25T15:00:00+00:00", "LIVE", 2, "x", 1, "BBB", "CLOSE", 1.0, 18.0),
        ("2026-09-25T16:00:00+00:00", "LIVE", 2, "x", 1, "CCC", "OPEN", 0.5, 40.0),
        ("2026-09-24T15:00:00+00:00", "SIMULATION", 3, "x", 1, "ZZZ", "OPEN", 1.0, 20.0),
        ("2026-09-25T15:00:00+00:00", "SIMULATION", 3, "x", 1, "ZZZ", "CLOSE", 1.0, 99.0),
    ])
    c.execute("INSERT INTO slot_marks (at, mode, slot_id, symbol, price) VALUES ('2026-09-25T19:00:00+00:00','LIVE',2,'CCC',44.0)")
    r = live_pnl.compute(c, CFG, "LIVE")
    check("two closed LIVE trades; SIMULATION excluded", r["closed_n"] == 2, r["closed_n"])
    g = r["closed_total"]["gross"]
    check("gross = sum of (exit - entry) x qty", abs(g - (2.0 - 2.0)) < 1e-9, g)
    fee = live_pnl.sell_fees(22.0, 0.2, CFG) + live_pnl.sell_fees(18.0, 1.0, CFG)
    check("costs = SEC + TAF on each sell", abs(r["closed_total"]["costs"] - fee) < 1e-12, r["closed_total"]["costs"])
    check("net = gross - costs", abs(r["closed_total"]["net"] - (g - fee)) < 1e-12)
    check("strategy label from paper_runs", r["closed"][0]["strategy"] == "Value Book", r["closed"][0]["strategy"])
    check("one winner", r["wins"] == 1, r["wins"])
    check("open position marked at the latest LIVE mark", len(r["open"]) == 1 and abs(r["open_gross"] - 2.0) < 1e-9, r["open"])
    check("render names the scope", "slot trades only" in live_pnl.render(r)[0])
    empty = live_pnl.compute(c, CFG, "SHADOW")
    check("no trades -> a plain line", live_pnl.render(empty) == ["no SHADOW slot trades yet"])
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
