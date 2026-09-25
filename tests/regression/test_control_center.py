"""
Regression test: the Control Center (Addendum D, N1) and the trader heartbeat.

Pinned:
  - slot_trader._heartbeat records a trader_runs row, and never raises — even
    on a connection that cannot write (a heartbeat must not stop a trade)
  - live_positions pairs OPEN/CLOSE per slot from the LIVE log only: realized
    gross on the closed trade, unrealized at the latest monitor mark, estimated
    costs charged on both, a SIMULATION trade never counted
  - replacements() applies the plan's own rules: a challenger with enough
    advantage is still BLOCKED while the holder has held fewer than
    min_hold_sessions, or when its family is full
  - control_center never writes: its connection is read-only

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import control_center as cc
import slot_trader as st

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def fixture(path):
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    st.init(c)
    c.execute("CREATE TABLE IF NOT EXISTS features (ticker TEXT, date TEXT, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE IF NOT EXISTS prices (ticker TEXT, date TEXT, close REAL)")
    c.executemany("INSERT INTO features VALUES (?,?,?)", [("AAA", "2026-09-23", 2e8), ("BBB", "2026-09-23", 2e8)])
    c.executemany("INSERT INTO prices VALUES ('SPY', ?, 1)", [("2026-09-2%d" % i,) for i in range(1, 5)])
    ins = ("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, "
           "atr, stop_plan, reason, signal_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)")
    plan = '[{"type": "atr", "atr_multiple": 3}, {"type": "take_profit", "pct": 0.1}]'
    c.execute(ins, ("2026-09-24T14:00:00", "LIVE", 1, "k1", 1, "AAA", "OPEN", 1.0, 100.0, 2.0, plan, "entry", "s1"))
    c.execute(ins, ("2026-09-24T15:00:00", "LIVE", 1, "k1", 1, "AAA", "CLOSE", 1.0, 110.0, 2.0, plan, "take-profit", "s2"))
    c.execute(ins, ("2026-09-24T15:10:00", "LIVE", 2, "k2", 1, "BBB", "OPEN", 2.0, 50.0, 1.0, plan, "entry", "s3"))
    c.execute(ins, ("2026-09-24T15:10:00", "SIMULATION", 3, "k3", 1, "AAA", "OPEN", 5.0, 100.0, 1.0, plan, "e", "s4"))
    c.execute("INSERT INTO slot_marks (at, mode, slot_id, symbol, price, high, stop, verdict) VALUES "
              "('2026-09-24T16:00:00','LIVE',2,'BBB',52.0,52.0,47.0,'within plan')")
    c.commit()
    return c


def main():
    print("\n  test_control_center")
    with tempfile.TemporaryDirectory() as d:
        path = os.path.join(d, "t.db")
        c = fixture(path)

        st._heartbeat(c, "LIVE", "ok", pass_="monitor", actions=0, positions=1, reconciled=1, cash=19.26)
        r = c.execute("SELECT mode, outcome, cash, reconciled FROM trader_runs").fetchall()
        check("heartbeat recorded", [tuple(x) for x in r] == [("LIVE", "ok", 19.26, 1)], [tuple(x) for x in r])
        ro = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            st._heartbeat(ro, "LIVE", "ok")
            check("heartbeat on a read-only connection does not raise", True)
        except Exception as e:                               # noqa: BLE001
            check("heartbeat on a read-only connection does not raise", False, repr(e))

        ro.row_factory = sqlite3.Row
        pos, closed = cc.live_positions(ro)
        check("one closed LIVE trade, SIMULATION ignored", len(closed) == 1 and set(pos) == {2}, (closed, pos))
        check("realized gross = (110-100) x 1", abs(closed[0]["gross"] - 10.0) < 1e-9, closed[0]["gross"])
        check("realized costs charged (5 bps tier, both sides)",
              abs(closed[0]["cost"] - 0.0005 / 2 * 210) < 1e-9, closed[0]["cost"])
        p = pos[2]
        check("unrealized gross at the latest mark = (52-50) x 2", abs(p["unrealized_gross"] - 4.0) < 1e-9, p)
        check("take-profit price from the stop plan", abs(p["take_profit_price"] - 55.0) < 1e-9, p["take_profit_price"])
        check("stop from the monitor mark", p["stop"] == 47.0, p["stop"])
        try:
            ro.execute("CREATE TABLE x (a)")
            check("control center connection is read-only", False)
        except sqlite3.OperationalError:
            check("control center connection is read-only", True)

        settings = {"min_advantage_score": 0.002, "min_hold_sessions": 3, "max_replacements_per_day": 2,
                    "max_per_family": 4}
        plan = {"settings": settings, "release": [], "assign": [],
                "held": {1: {"strategy_key": "held", "version": 1, "since": "2099-01-01T00:00:00"}}}
        board = [{"rank": 1, "name": "cand", "family": "f2", "slot": None, "eligible": True, "score": 0.02,
                  "trades": 5},
                 {"rank": 2, "name": "held", "family": "f1", "slot": 1, "eligible": True, "score": 0.001,
                  "trades": 9}]
        rp = cc.replacements(ro, plan, board)
        row = rp["challengers"][0]
        check("enough advantage but a new holder -> BLOCKED by min hold",
              row["status"] == "BLOCKED" and any("sessions" in b for b in row["blocked_by"]), row)
        plan["held"][1]["since"] = "2000-01-01T00:00:00"
        rp = cc.replacements(ro, plan, board)
        check("held long enough, different family -> ELIGIBLE", rp["challengers"][0]["status"] == "ELIGIBLE",
              rp["challengers"][0])
        board[0]["family"] = "f1"
        settings["max_per_family"] = 0
        rp = cc.replacements(ro, plan, board)
        check("family full -> BLOCKED", any("family" in b for b in rp["challengers"][0]["blocked_by"]),
              rp["challengers"][0])
        ro.close()
        c.close()

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        sys.exit(1)
    print("  all passed")


if __name__ == "__main__":
    main()
