"""Reports read basket slots (Stage AD2.1 item 1): every member is paired by slot and symbol in live_pnl, eod_report,
the Control Center and the Telegram bot; a one-stock slot reads exactly as before."""
import runtime  # noqa: F401
import json
import sqlite3

import control_center as cc
import eod_report as er
import live_pnl
import slot_trader
import telegram_bot as tb

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
slot_trader.init(c)
c.execute("CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL)")
plan = json.dumps([{"type": "atr", "atr_multiple": 3.0}, {"type": "time", "max_hold_days": 21}])
rows = [("2026-10-20T13:35:00", 1, "fx_b", "AAA", "OPEN", 0.1, 50.0), ("2026-10-20T13:35:01", 1, "fx_b", "BBB", "OPEN", 0.25, 20.0),
        ("2026-10-20T13:35:02", 1, "fx_b", "CCC", "OPEN", 0.5, 10.0), ("2026-10-20T13:35:03", 2, "fx_s", "DDD", "OPEN", 0.4, 50.0),
        ("2026-10-21T15:00:00", 1, "fx_b", "BBB", "CLOSE", 0.25, 18.0)]
for at, sl, k, sym, act, q, px in rows:
    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, atr, stop_plan, reason, signal_id) "
              "VALUES (?,?,?,?,1,?,?,?,?,1.0,?,'t',?)", (at, "LIVE", sl, k, sym, act, q, px, plan, at + sym))
for sl, sym, px in ((1, "AAA", 55.0), (1, "CCC", 9.0), (2, "DDD", 51.0)):
    c.execute("INSERT INTO slot_marks (at, mode, slot_id, symbol, price, high, stop, verdict) VALUES "
              "('2026-10-21T19:00:00','LIVE',?,?,?,?,1,'hold')", (sl, sym, px, px))
c.commit()
lp = live_pnl.compute(c, {"costs": {}}, "LIVE")
check("live_pnl: the closed member is paired with its own OPEN (BBB 20 -> 18)",
      len(lp["closed"]) == 1 and lp["closed"][0]["symbol"] == "BBB" and abs(lp["closed"][0]["gross"] - (-0.5)) < 1e-9, lp["closed"])
check("live_pnl: every open member counts (AAA, CCC in slot 1; DDD in slot 2)", sorted(o["symbol"] for o in lp["open"]) == ["AAA", "CCC", "DDD"])
check("eod_report: all open positions are listed", [p["symbol"] for p in er._section_positions(c, "LIVE")] == ["AAA", "CCC", "DDD"])
check("eod_report: realised P&L pairs a close with its own name", abs(er._realized_gross(c, "2026-10-21", "LIVE")[0] + 0.5) < 1e-9)
sl = {r["slot"]: r for r in er._section_slots(c, "LIVE", [])}
check("eod_report: a basket slot shows its names and the combined marked result",
      sl[1]["symbol"] == "AAA+CCC" and abs(sl[1]["current_usd"] - (0.1 * 5 + 0.5 * -1)) < 0.005, sl[1])
check("eod_report: a one-stock slot reads as before", sl[2]["symbol"] == "DDD" and abs(sl[2]["current_usd"] - 0.4) < 0.005, sl[2])
pos, closed = cc.live_positions(c)
check("control center: a basket slot is one combined card listing its members",
      pos[1]["symbol"] == "2 names: AAA, CCC" and len(pos[1]["members"]) == 2 and abs(pos[1]["cost_basis"] - 10.0) < 1e-9, pos[1])
check("control center: a one-stock slot is unchanged and now carries its time limit",
      pos[2]["symbol"] == "DDD" and pos[2]["max_hold_days"] == 21, pos[2])
check("control center: the closed member is a closed trade", [t["symbol"] for t in closed] == ["BBB"])
cfg = {"slots": {"basket": {"k": 4, "modes": ["LIVE"]}}}
import universe
universe.load_config = lambda *a, **k: cfg
out = tb._positions(c)
check("telegram /positions lists every basket member when LIVE trades baskets", len(out) == 3 and any("CCC" in x for x in out), out)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
