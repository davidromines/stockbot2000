"""ledger_check (Stage AD1.3): the slot ledger against the broker's realised P&L by day and its account value, with a fake
broker. A matching account passes; a missing trade, a hand-placed position or a value gap is reported."""
import runtime  # noqa: F401
import sqlite3

import ledger_check as lc
import slot_trader

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
slot_trader.init(c)
c.execute("CREATE TABLE live_equity (at TEXT, session TEXT, equity REAL, buying_power REAL)")
c.execute("INSERT INTO live_equity VALUES ('2026-09-24T15:30:00','2026-09-24',100.0,100.0)")
for at, sym, act, q, px in (("2026-10-01T14:00:00", "AAA", "OPEN", 1.0, 20.0), ("2026-10-02T14:00:00", "AAA", "CLOSE", 1.0, 22.0),
                            ("2026-10-02T14:05:00", "BBB", "OPEN", 2.0, 10.0)):
    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, reason, signal_id) "
              "VALUES (?,'LIVE',1,'fx',1,?,?,?,?,'t',?)", (at, sym, act, q, px, at + sym))
c.commit()
cfg = {"costs": {}}


def fake(realized, total, equity, held):
    def call(tool, args):
        if tool == "get_realized_pnl":
            return {"data": {"data_points": [{"start_time": k + "T04:00:00Z", "realized_gain": str(v), "number_of_trades": 1}
                                             for k, v in realized.items()]}}
        if tool == "get_portfolio":
            return {"data": {"total_value": str(total), "equity_value": str(equity)}}
        return {"data": {"positions": [{"symbol": s, "quantity": str(q)} for s, q in held.items()]}}
    return call


# ledger: +2.00 realised, BBB open basis $20; broker: BBB worth $21 -> expected 100 + 2 + 1 = 103
r = lc.check(c, cfg, lc.broker_figures("x", fake({"2026-10-02": 2.0}, 103.0, 21.0, {"BBB": 2.0})))
check("a matching account passes, gap within the tolerance", r["ok"] and abs(r["gap"]) <= lc.TOLERANCE, r)
check("expected = start + realised + broker value of the open slot positions - their basis",
      abs(r["expected"] - (100 + r["realised_net"] + 1.0)) < 1e-9, r)
r2 = lc.check(c, cfg, lc.broker_figures("x", fake({"2026-10-02": 2.0, "2026-10-03": -1.5}, 101.5, 21.0, {"BBB": 2.0})))
check("a realised day missing from the ledger is listed", not r2["ok"] and r2["day_diffs"][0][0] == "2026-10-03", r2["day_diffs"])
r3 = lc.check(c, cfg, lc.broker_figures("x", fake({"2026-10-02": 2.0}, 113.0, 31.0, {"BBB": 2.0, "ZZZ": 1.0})))
check("a position the slots did not buy is named and fails the check", not r3["ok"] and r3["outside_slots"] == ["ZZZ"], r3)
r4 = lc.check(c, cfg, lc.broker_figures("x", fake({"2026-10-02": 2.0}, 104.0, 21.0, {"BBB": 2.0})))
check("a value gap above the tolerance fails", not r4["ok"] and r4["gap"] > lc.TOLERANCE, r4)
r5 = lc.check(c, cfg, lc.broker_figures("x", fake({"2026-09-24": -0.74, "2026-10-02": 2.0}, 103.0, 21.0, {"BBB": 2.0})))
check("the pre-LIVE day (owner's manual sale) is outside the comparison", r5["ok"], r5["day_diffs"])
check("the report renders", "Ledger check" in lc.render(r))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
