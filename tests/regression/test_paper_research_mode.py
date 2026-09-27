"""
Paper research mode: new funds get $20 x paper.positions; recapitalize() changes only funds
with no mark, position or trade; a fund with a record keeps its capital; without the setting
everything is as before. In-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import paper_trading as pt

FAILED = []
CFG = {"risk": {"position_size_usd": 20.0, "max_open_positions": 5}, "paper": {"positions": 20}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    c.execute("INSERT INTO prices VALUES ('SPY','2026-09-24',1)")
    pt.init(c)
    check("research positions from config", pt.research_positions(CFG) == 20)
    check("no setting: the live cap", pt.research_positions({"risk": {"max_open_positions": 5}}) == 5)
    new = pt.start(c, CFG, "new")
    check("a new fund gets $400", c.execute("SELECT capital_usd FROM paper_runs WHERE run_id=?", (new,)).fetchone()[0] == 400)
    old_cfg = {"risk": CFG["risk"]}
    a = pt.start(c, old_cfg, "unstepped")
    b = pt.start(c, old_cfg, "stepped")
    c.execute("INSERT INTO paper_equity (run_id, date, cash_usd, positions_usd, equity_usd, open_positions) "
              "VALUES (?, '2026-09-24', 100, 0, 100, 0)", (b,))
    c.commit()
    n = pt.recapitalize(c, CFG)
    cap = dict(c.execute("SELECT name, capital_usd FROM paper_runs").fetchall())
    check("an unstepped $100 fund is recapitalized", n == 1 and cap["unstepped"] == 400, (n, cap))
    check("a fund with a record keeps its $100", cap["stepped"] == 100, cap)
    check("cash matches the new capital",
          c.execute("SELECT cash_usd FROM paper_runs WHERE run_id=?", (a,)).fetchone()[0] == 400)
    check("recapitalize is idempotent", pt.recapitalize(c, CFG) == 0)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
