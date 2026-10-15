"""Intraday Runner: scanner, gates, slot isolation, exit exemption in the risk engine, and a full fake-broker cycle."""
import runtime  # noqa: F401
import json
import sqlite3
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import numpy as np
import pandas as pd

import intraday_manager as im
import intraday_momentum as mom
import intraday_runner as ir
import intraday_stops as st
import risk_engine
import signals as sg
import slots

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

NY = st.NY
UTC = timezone.utc
START = datetime(2026, 10, 14, 9, 30, tzinfo=NY)


def mkbars(closes, vols, rng_pct=0.0015, start=START, o0=None):
    rows, prev = [], o0 if o0 is not None else closes[0]
    for i, (c, v) in enumerate(zip(closes, vols)):
        o = prev
        rows.append({"ts": start + timedelta(minutes=i), "open": o, "high": max(o, c) * (1 + rng_pct / 2), "low": min(o, c) * (1 - rng_pct / 2),
                     "close": c, "volume": v})
        prev = c
    return pd.DataFrame(rows)


def strong(n=40):
    closes = [100.0] * 25 + list(np.linspace(100.0, 101.0, n - 25))
    vols = [1000.0] * 25 + [3000.0] * (n - 25)
    return mkbars(closes, vols)


def spy_bars(n=40, drift=0.0005):
    return mkbars(list(np.linspace(400.0, 400.0 * (1 + drift), n)), [1e6] * n, rng_pct=0.0004)


META = {"AAA": {"daily_atr_pct": 0.025, "dollar_volume_20": 2e8}}
NOW = START + timedelta(minutes=40, seconds=20)

# ---- the scanner ------------------------------------------------------------------------------------------------
f = mom.features(strong(), spy_bars(), 0.025, 2e8, NOW)
check("a clear leader qualifies", mom.reject_reasons(f) == [])
check("features are the documented quantities", f["ret15"] > 0.009 and f["vol_accel"] > 1.5 and f["breakout"] > 0 and f["dist_vwap"] > 0)
weak_mkt = mom.features(strong(), spy_bars(drift=-0.02), 0.025, 2e8, NOW)
check("a weak market blocks it", "weak market" in mom.reject_reasons(weak_mkt))
check("stale data blocks it", "stale data" in mom.reject_reasons(mom.features(strong(), spy_bars(), 0.025, 2e8, NOW + timedelta(minutes=10))))
check("an extended move (in daily ranges) is refused", "extended" in mom.reject_reasons(mom.features(strong(), spy_bars(), 0.004, 2e8, NOW)))
flat = mkbars([100.0] * 40, [1000.0] * 40)
check("a flat stock is refused", mom.reject_reasons(mom.features(flat, spy_bars(), 0.025, 2e8, NOW)) != [])
quiet = mkbars([100.0] * 25 + list(np.linspace(100, 101, 15)), [1000.0] * 40)
check("no volume acceleration is refused", "no volume acceleration" in mom.reject_reasons(mom.features(quiet, spy_bars(), 0.025, 2e8, NOW)))
check("too few bars", mom.features(strong().iloc[:20], spy_bars(), 0.025, 2e8, NOW) is None and mom.reject_reasons(None) == ["too few bars"])
costly = mom.features(strong(), spy_bars(), 0.025, 1e5, NOW)
check("illiquid names (wide estimated spread) are refused", any("cost" in r for r in mom.reject_reasons(costly)))
# no look-ahead: the features at bar 40 do not change when later bars exist
full = strong(60)
full.loc[40:, "close"] = 50.0
a, b = mom.features(full.iloc[:40], spy_bars(), 0.025, 2e8, NOW), mom.features(strong(60).iloc[:40], spy_bars(), 0.025, 2e8, NOW)
check("features at t ignore every later bar", {k: v for k, v in a.items()} == {k: v for k, v in b.items()})
res = mom.scan({"AAA": strong(), "FLAT": flat}, spy_bars(), {**META, "FLAT": META["AAA"]}, now=NOW)
check("scan returns the qualifier and a reject histogram, flagged uncalibrated", [c["ticker"] for c in res["candidates"]] == ["AAA"]
      and res["rejected"] and res["calibrated"] is False)

# ---- gates ------------------------------------------------------------------------------------------------------
S = ir.settings({"intraday": {"stage": "LIVE"}})
ny = datetime(2026, 10, 14, 11, 0, tzinfo=NY)
check("all clear -> allowed", ir.entry_gate(S, ny, 0, 0, 0.0, 0, True, None, None)[0])
check("not LIVE -> refused", not ir.entry_gate(S, ny, 0, 0, 0.0, 0, False, None, None)[0])
check("kill switch -> refused", "kill" in ir.entry_gate(S, ny, 0, 0, 0.0, 0, True, "x", None)[1])
check("outside the window (09:40 and 14:31) -> refused", not ir.entry_gate(S, ny.replace(hour=9, minute=40), 0, 0, 0.0, 0, True, None, None)[0]
      and not ir.entry_gate(S, ny.replace(hour=14, minute=31), 0, 0, 0.0, 0, True, None, None)[0])
check("3 entries a session is the cap", not ir.entry_gate(S, ny, 3, 0, 0.0, 0, True, None, None)[0])
check("2 simultaneous is the cap", not ir.entry_gate(S, ny, 1, 2, 0.0, 0, True, None, None)[0])
check("a -$2.00 day (realised + unrealised) stops entries", not ir.entry_gate(S, ny, 1, 0, -2.0, 0, True, None, None)[0]
      and ir.entry_gate(S, ny, 1, 0, -1.99, 0, True, None, None)[0])
check("3 consecutive order failures stop entries", not ir.entry_gate(S, ny, 0, 0, 0.0, 3, True, None, None)[0])
check("a runner halt stops entries", not ir.entry_gate(S, ny, 0, 0, 0.0, 0, True, None, "an exit could not be completed")[0])
rows = [{"action": "OPEN", "slot_id": 3, "symbol": "AAA", "price": 100.0, "quantity": 0.2},
        {"action": "CLOSE", "slot_id": 3, "symbol": "AAA", "price": 99.0, "quantity": 0.2},
        {"action": "OPEN", "slot_id": 5, "symbol": "BBB", "price": 50.0, "quantity": 0.4}]
pnl, entries, syms = ir.realised_today(rows)
check("realised P&L, entries and symbols traded today", abs(pnl + 0.2) < 1e-9 and entries == 2 and syms == {"AAA", "BBB"})
cap = st.cap_initial_pct(st.StopConfig(), 20.0, 0.5)
check("the $0.50 loss limit caps the initial stop at 2.5% of a $20 position (not binding at 1%)", cap.initial_pct == 1.0)

# ---- slot isolation ---------------------------------------------------------------------------------------------
db = sqlite3.connect(":memory:")
slots.init(db)
for sl, key in ((1, "fx_a"), (2, "fx_b"), (3, "fx_c"), (4, "fx_d"), (5, "fx_e")):
    db.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) VALUES "
               "('2026-10-14T09:00:00+00:00',?,?,?,?,?,?,?)", (sl, "ASSIGN", key, 1, 20.0, "LIVE", "x"))
db.commit()
CFG = {"intraday": {"stage": "LIVE", "slots": [3, 5], "position_dollars": 20.0}}
done = ir.assign(db, CFG)
cur = slots.current(db, CFG)
check("assign hands slots 3 and 5 to the Runner and releases their old holders", done == [3, 5]
      and cur[3]["strategy_key"] == ir.KEY and cur[5]["strategy_key"] == ir.KEY and cur[1]["strategy_key"] == "fx_a")
check("old holders have RELEASE rows with the reason", db.execute("SELECT COUNT(*) FROM slot_assignments WHERE action='RELEASE' AND slot_id IN (3,5)").fetchone()[0] == 2)
check("assign is idempotent", ir.assign(db, CFG) == [] and db.execute("SELECT COUNT(*) FROM slot_assignments").fetchone()[0] == 5 + 4)
check("reserved set follows the stage", slots.intraday_reserved(CFG) == {3, 5} and slots.intraday_reserved({"intraday": {"stage": "OFF", "slots": [3]}}) == set())
slots.assess = lambda conn, cfg: []                                   # no ranked strategies: every medium-term holder is released
p = slots.plan(db, CFG)
touched = {x[0] for x in p["release"]} | {x[0] for x in p["assign"]} | set(p["cash_slots"]) | set(p["keep"])
check("the medium-term plan never touches the reserved slots", not ({3, 5} & touched) and {1, 2, 4} <= touched)
p_off = slots.plan(db, {"intraday": {"stage": "OFF", "slots": [3, 5]}})
check("with the stage OFF the plan sees them again", {3, 5} & ({x[0] for x in p_off["release"]}))

# ---- the risk engine never blocks an exit ----------------------------------------------------------------------
LIM = {**risk_engine.load_limits(), "account_type": "cash", "limited_margin_settled_funds": True, "max_orders_per_day": 5, "max_daily_loss_dollars": 2.0}
E = risk_engine.RiskEngine(LIM)
port = {"equity": 100.0, "buying_power": 100.0, "unsettled_proceeds": 0.0, "daily_pnl": -20.0, "drawdown_percent": 0.0,
        "positions": {"AAPL": {"value": 20.0, "quantity": 0.4}}}
quote = {"price": 50.0, "dollar_volume_20": 2e7, "market_cap": 5e9}
today = {"orders_today": 99, "orders_for_symbol": 9}
sell = sg.Signal(symbol="AAPL", action="SELL", strategy="t", reason="x", quantity=0.4, session="2026-10-14")
buy = sg.Signal(symbol="MSFT", action="BUY", strategy="t", reason="x", notional_value=20.0, confidence=0.8, session="2026-10-14")
check("a SELL is approved over the order cap and the daily-loss limit", E.validate(sell, port, quote, today).approved)
check("a BUY is still refused by both", not E.validate(buy, port, quote, today).approved)

# ---- the exit adapter -------------------------------------------------------------------------------------------
class FakeEngine:
    session = "2026-10-14"
    def __init__(self, script):
        self.script, self.calls = list(script), []
    def execute(self, sig, reconciled=None):
        self.calls.append(sig)
        r = dict(self.script.pop(0)); r.setdefault("signal_id", sig.signal_id)
        return r


def ord_(q, px, state="FILLED"):
    return SimpleNamespace(filled_quantity=q, avg_fill_price=px, state=state)

eng = FakeEngine([{"status": "failed", "reasons": ["broker down"]}, {"status": "filled", "order": ord_(0.2, 98.7)}])
ad = ir.SellAdapter(db, eng, 3, lambda: True)
ref1, ref2 = "x-AAA-2026-10-14T10:30:00-04:00-1", "x-AAA-2026-10-14T10:30:00-04:00-2"
r1 = ad.submit_sell("AAA", 0.2, ref1)
r2 = ad.submit_sell("AAA", 0.2, ref2)
check("a failed engine result is REJECTED, a fill is FILLED with quantity and price", r1["status"] == "REJECTED" and r2["status"] == "FILLED" and r2["avg_price"] == 98.7)
check("each attempt is a distinct decision (strategy suffix), so a retry is not a duplicate", eng.calls[0].signal_id != eng.calls[1].signal_id
      and eng.calls[1].strategy.endswith(":x2") and not eng.calls[0].strategy.endswith(":x1"))
check("ref parsing handles dashes in the symbol", ir.SellAdapter._parse("x-BRK-B-2026-10-14T10:30:00-04:00-3") == ("BRK-B", 3))
db.execute("CREATE TABLE IF NOT EXISTS orders (client_order_id TEXT, state TEXT, filled_quantity REAL, avg_fill_price REAL, mode TEXT, signal_id TEXT)")
check("order_status is None when the broker side has no such order", ad.order_status(ref1) is None)

# ---- a whole cycle with fakes ----------------------------------------------------------------------------------
import minute_bars as mb
import slot_trader as stx
c = sqlite3.connect(":memory:")
c.row_factory = None
slots.init(c); stx.init(c); mb.init(c); ir.init(c)
CFG2 = {"intraday": {"stage": "LIVE", "slots": [3, 5], "position_dollars": 20.0, "scan_every_s": 60}}
ir.assign(c, CFG2)
sent = []
state = {"price": 101.0, "fills": []}


class CycleEngine:
    session = "2026-10-14"
    def execute(self, sig, reconciled=None):
        state["fills"].append((sig.action, sig.symbol, sig.strategy))
        px = state["price"]
        if sig.action == "BUY":
            return {"status": "filled", "signal_id": sig.signal_id, "order": ord_(20.0 / px, px)}
        return {"status": "filled", "signal_id": sig.signal_id, "order": ord_(float(sig.quantity), px)}


def quote_fn(sym):
    return state["price"], T[0]


T = [datetime(2026, 10, 14, 14, 10, 20, tzinfo=UTC)]                  # 10:10:20 New York, 20 s after the 40th bar
runner = ir.Runner(c, CFG2, CycleEngine(), quote_fn, lambda tk, now: {"AAA": strong(), "SPY": spy_bars()},
                   notify_fn=lambda t, m: sent.append((t, m)), stage_ok_fn=lambda: True,
                   universe_fn=lambda: ["AAA"], meta_fn=lambda ts: META)
out = runner.tick(T[0])
check("the leader is bought for a free slot", out["entered"] == ["AAA"] and len(runner.positions) == 1)
check("the fill is in the slot ledger as an OPEN under the Runner's key", c.execute(
    "SELECT action, strategy_key, symbol FROM slot_trades WHERE slot_id=3").fetchall() == [("OPEN", ir.KEY, "AAA")])
check("the position is persisted and the signal is logged TRADED", c.execute("SELECT COUNT(*) FROM intraday_state").fetchone()[0] == 1
      and c.execute("SELECT action FROM intraday_runner_signals WHERE ticker='AAA'").fetchone()[0] == "TRADED")
check("bars were stored for the evaluation history", c.execute("SELECT COUNT(*) FROM minute_bars WHERE ticker='AAA'").fetchone()[0] == 40)
T[0] += timedelta(seconds=70)
out = runner.tick(T[0])
check("the same symbol is not bought again the same session, and no second position opens", len(runner.positions) == 1
      and [x for x in state["fills"] if x[0] == "BUY"] == [("BUY", "AAA", f"slot3:{ir.KEY}")])
state["price"] = 101.6
T[0] += timedelta(seconds=15)
runner.tick(T[0])
pos = list(runner.positions.values())[0]
check("a rising price lifts the trailing stop", pos.highest == 101.6 and pos.stop > 101.0 * 0.99)
state["price"] = 100.3                                              # below the trailing stop 101.6 x 0.99 = 100.584
T[0] += timedelta(seconds=15)
runner.tick(T[0])
check("a drop through the trailing stop exits through the engine and closes the ledger row", not runner.positions and
      c.execute("SELECT action, reason FROM slot_trades WHERE slot_id=3 ORDER BY id").fetchall()[-1][0] == "CLOSE"
      and [x[0] for x in state["fills"]] == ["BUY", "SELL"])
check("the exit alert was sent and the state row removed", any("exit" in t.lower() for t, _ in sent) and c.execute("SELECT COUNT(*) FROM intraday_state").fetchone()[0] == 0)
# restart recovery: an OPEN row in the ledger and no state -> the position is rebuilt
c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, reason, signal_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
          ("2026-10-14T14:40:00+00:00", "LIVE", 5, ir.KEY, 1, "BBB", "OPEN", 0.2, 100.0, "x", "sig-restart"))
c.commit()
r2 = ir.Runner(c, CFG2, CycleEngine(), quote_fn, lambda tk, now: {}, stage_ok_fn=lambda: True, universe_fn=lambda: [], meta_fn=lambda ts: {})
check("after a restart the open intraday position is recovered from the ledger", 5 in r2.positions and r2.positions[5].symbol == "BBB")
# SHADOW stage: qualifying signals are logged, nothing is ordered
sc = sqlite3.connect(":memory:")
slots.init(sc); stx.init(sc); mb.init(sc); ir.init(sc)
SH = {"intraday": {"stage": "SHADOW", "slots": [3, 5], "position_dollars": 20.0}}
state["fills"].clear()
shadow = ir.Runner(sc, SH, CycleEngine(), quote_fn, lambda tk, now: {"AAA": strong(), "SPY": spy_bars()}, stage_ok_fn=lambda: False,
                   universe_fn=lambda: ["AAA"], meta_fn=lambda ts: META)
T[0] = datetime(2026, 10, 14, 14, 10, 20, tzinfo=UTC)
shadow.tick(T[0])
check("SHADOW logs the qualifying signal and places no order", state["fills"] == [] and not shadow.positions
      and sc.execute("SELECT action FROM intraday_runner_signals").fetchall() == [("QUALIFIED",)])
oc = sqlite3.connect(":memory:")
slots.init(oc); stx.init(oc); mb.init(oc); ir.init(oc)
off = ir.Runner(oc, {"intraday": {"stage": "OFF"}}, CycleEngine(), quote_fn, lambda tk, now: {"AAA": strong()},
                stage_ok_fn=lambda: False, universe_fn=lambda: ["AAA"], meta_fn=lambda ts: META)
check("stage OFF scans nothing", off.tick(T[0]) == {})

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
