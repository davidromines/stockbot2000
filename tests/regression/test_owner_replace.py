"""
slots.owner_replace: the owner's explicit swap of one slot's holder records RELEASE then
ASSIGN with the owner named; it refuses an ineligible strategy, one already in another slot,
and one correlated above max_correlation with another holder. In-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import slots

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def refused(fn):
    try:
        fn()
    except ValueError as e:
        return str(e)
    return None


conn = sqlite3.connect(":memory:")
conn.row_factory = sqlite3.Row
slots.init(conn)
cfg = {}
for sl, key in ((4, "hold4"), (5, "macd")):
    conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) "
                 "VALUES ('2026-09-24T14:40:01+00:00', ?, 'ASSIGN', ?, 1, 20.0, 'SIMULATION', 'x')", (sl, key))
conn.commit()
rows = [{"strategy_key": "fcf", "version": 1, "eligible": True, "reasons": [], "score": 0.0177, "family": "fcf_to_price"},
        {"strategy_key": "bad", "version": 1, "eligible": False, "reasons": ["backtest loses money"], "score": -0.01},
        {"strategy_key": "hold4", "version": 1, "eligible": True, "reasons": [], "score": 0.017},
        {"strategy_key": "twin", "version": 1, "eligible": True, "reasons": [], "score": 0.016}]

check("ineligible strategy refused",
      "not eligible" in (refused(lambda: slots.owner_replace(conn, cfg, 5, "bad", 1, "t", "LIVE", rows)) or ""))
check("strategy already in another slot refused",
      "already holds slot 4" in (refused(lambda: slots.owner_replace(conn, cfg, 5, "hold4", 1, "t", "LIVE", rows)) or ""))
conn.execute("CREATE TABLE strategy_correlation (key_a TEXT, ver_a INT, key_b TEXT, ver_b INT, corr REAL)")
conn.execute("INSERT INTO strategy_correlation VALUES ('twin',1,'hold4',1,0.9)")
check("strategy correlated with another holder refused",
      "correlation" in (refused(lambda: slots.owner_replace(conn, cfg, 5, "twin", 1, "t", "LIVE", rows)) or ""))

r = slots.owner_replace(conn, cfg, 5, "fcf", 1, "MACD Pullback predicted to lose", "LIVE", rows)
held = slots.current(conn, cfg)
check("slot 5 now holds the new strategy", held[5]["strategy_key"] == "fcf", held[5])
check("slot 4 untouched", held[4]["strategy_key"] == "hold4")
last = conn.execute("SELECT action, reason, strategy_key FROM slot_assignments ORDER BY id DESC LIMIT 2").fetchall()
check("RELEASE then ASSIGN, owner named in both",
      [x["action"] for x in last] == ["ASSIGN", "RELEASE"] and all("owner" in x["reason"] for x in last)
      and last[1]["strategy_key"] == "macd", [dict(x) for x in last])
check("returns the released holder", r["released"]["strategy_key"] == "macd")

sys.exit(1 if FAILED else 0)
