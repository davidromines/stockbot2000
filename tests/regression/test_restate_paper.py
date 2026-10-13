"""
restate_paper.py (Addendum F, G1): next-open restatement beside the original paper trades.
In-memory database; the originals must never change, the restatement is idempotent, and a trade whose
exit has no next-session open yet waits instead of being invented.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import restate_paper as rp

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def make_db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE paper_runs (run_id TEXT, family TEXT, created_at TEXT, capital_usd REAL)")
    c.execute("CREATE TABLE paper_trades (run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT, entry_price REAL, "
              "exit_price REAL, shares REAL, gross_pnl_usd REAL, costs_usd REAL, net_pnl_usd REAL, pnl_pct REAL, exit_reason TEXT)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, close REAL)")
    c.execute("INSERT INTO paper_runs VALUES ('r1','fam','2026-09-20',400)")
    dates = [f"2026-09-{d:02d}" for d in range(1, 9)]
    opens, closes = [10, 11, 12, 13, 14, 15, 16, 17], [10.5, 11.5, 12.5, 13.5, 14.5, 15.5, 16.5, 17.5]
    for tk in ("A", "B"):
        for d, o, cl in zip(dates, opens, closes):
            c.execute("INSERT INTO prices VALUES (?,?,?,?)", (tk, d, o, cl))
    def trade(tk, e, x, ie, ix):
        ep, xp = closes[ie], closes[ix]
        sh = 20 / ep
        g = sh * (xp - ep)
        c.execute("INSERT INTO paper_trades VALUES ('r1',?,?,?,?,?,?,?,?,?,?,?)",
                  (tk, e, x, ep, xp, sh, g, 0.04, g - 0.04, (xp / ep - 1) * 100, "exit_rule"))
    trade("A", dates[2], dates[4], 2, 4)        # next opens: dates[3] (13) and dates[5] (15)
    trade("B", dates[6], dates[7], 6, 7)        # exits on the last stored bar: no next open yet
    c.commit()
    return c


def main():
    c = make_db()
    before = c.execute("SELECT * FROM paper_trades ORDER BY ticker").fetchall()
    r = rp.restate(c)
    check("one trade restated, one waits for a next-session open", r["written"] == 1 and r["waiting_for_next_open"] == 1, r)
    row = c.execute("SELECT entry_open_next, exit_open_next, gross_pct, cost_pct, net_pct, net_usd, version FROM paper_trades_restated").fetchone()
    check("entry is the open of the session after the entry date; exit the open after the exit date",
          row[0] == 13 and row[1] == 15, row)
    check("gross is exit/entry - 1 on those opens", abs(row[2] - (15 / 13 - 1) * 100) < 1e-9, row[2])
    check("net = gross - the engine's modelled cost", abs(row[4] - (row[2] - row[3])) < 1e-9 and row[3] > 0, row)
    check("net dollars scale with the $20 notional", abs(row[5] - 20 * row[4] / 100) < 1e-9, row[5])
    check("the version is recorded", row[6] == rp.VERSION)
    r2 = rp.restate(c)
    check("a second run writes nothing new (idempotent)", r2["written"] == 0 and c.execute("SELECT COUNT(*) FROM paper_trades_restated").fetchone()[0] == 1, r2)
    check("the original paper_trades are untouched", c.execute("SELECT * FROM paper_trades ORDER BY ticker").fetchall() == before)
    c.execute("INSERT INTO prices VALUES ('B','2026-09-09',18,18.5)")
    r3 = rp.restate(c)
    check("when the next open appears the waiting trade is picked up", r3["written"] == 1, r3)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
