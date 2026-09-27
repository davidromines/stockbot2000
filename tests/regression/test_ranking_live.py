"""
ranking.live_per_trade (Addendum D criterion 12): a strategy's closed LIVE slot trades are
read from slot_trades (OPEN then CLOSE per slot), attributed to the strategy that opened
them, and an open position is not counted. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ranking

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, slot_id INT, action TEXT, quantity REAL, "
              "price REAL, strategy_key TEXT, version INT, mode TEXT)")
    rows = [(1, "OPEN", 1, 100.0, "a", 1, "LIVE"), (2, "OPEN", 1, 50.0, "b", 1, "LIVE"),
            (1, "CLOSE", 1, 110.0, "a", 1, "LIVE"), (2, "CLOSE", 1, 45.0, "b", 1, "LIVE"),
            (1, "OPEN", 1, 200.0, "a", 1, "LIVE"), (3, "OPEN", 1, 10.0, "a", 1, "SIMULATION"),
            (3, "CLOSE", 1, 20.0, "a", 1, "SIMULATION")]
    c.executemany("INSERT INTO slot_trades (slot_id, action, quantity, price, strategy_key, version, mode) "
                  "VALUES (?,?,?,?,?,?,?)", rows)
    r, n = ranking.live_per_trade(c, "a", 1)
    check("one closed LIVE trade for a, +10%", n == 1 and abs(r - 0.10) < 1e-9, (r, n))
    r, n = ranking.live_per_trade(c, "b", 1)
    check("b's trade attributed to b, -10%", n == 1 and abs(r + 0.10) < 1e-9, (r, n))
    check("another version has none", ranking.live_per_trade(c, "a", 2) == (None, 0))
    check("no table -> none", ranking.live_per_trade(sqlite3.connect(":memory:"), "a", 1) == (None, 0))
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
