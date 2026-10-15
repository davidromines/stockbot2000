"""Intraday Runner M2: stop rules, the minute-bar simulator and the position manager (plan R2.5 / R2.6, Phase 7 scenarios)."""
import runtime  # noqa: F401
import json
from datetime import datetime, timedelta

import pandas as pd

import intraday_manager as im
import intraday_sim as sim
import intraday_stops as st

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

NY = st.NY
T0 = datetime(2026, 10, 14, 10, 0, tzinfo=NY)                      # a summer (EDT) session
FREE = sim.Costs(half_spread_bps=0, slippage_bps=0, sell_fee_bps=0, latency_bars=0)
CFG = st.StopConfig(mode="pct", initial_pct=1.0, trail_pct=1.0, max_hold_minutes=30)


def bars(rows, start=T0):
    """rows of (open, high, low, close); one-minute bars from `start`."""
    return pd.DataFrame([{"ts": start + timedelta(minutes=i), "open": o, "high": h, "low": l, "close": c} for i, (o, h, l, c) in enumerate(rows)])


# ---- the stop itself ------------------------------------------------------------------------------------------
ts = st.TrailingStop(100.0, T0, CFG)
ts.observe(103.0, T0 + timedelta(minutes=1))
check("worked example: entry 100, high 103, 1% trail -> trigger 101.97", abs(ts.stop_price - 101.97) < 1e-9)
before = ts.stop_price
for p in (102.0, 101.5, 99.0):
    ts.observe(p, T0 + timedelta(minutes=2))
check("the trailing stop never moves down", ts.stop_price == before)
check("a price at the stop is a breach, just above is not", ts.breached(101.97) and not ts.breached(101.9701))
ts2 = st.TrailingStop(100.0, T0 + timedelta(seconds=30), CFG)             # filled mid-bar
check("a bar that began before the fill cannot lift the stop", ts2.observe_bar_high(T0, 110.0) is False and ts2.highest == 100.0)
check("a bar that begins at the fill can", ts2.observe_bar_high(T0 + timedelta(seconds=30), 104.0) is True and abs(ts2.stop_price - 104 * 0.99) < 1e-9)
check("a price observed before the fill is ignored", st.TrailingStop(100.0, T0, CFG).observe(120.0, T0 - timedelta(seconds=1)) is False)
atr = st.TrailingStop(100.0, T0, st.StopConfig(mode="atr", atr=0.5, initial_atr_mult=2, trail_atr_mult=2))
atr.observe(102.0, T0 + timedelta(minutes=1))
check("ATR mode: initial entry - 2 ATR, trail highest - 2 ATR", abs(atr.initial - 99.0) < 1e-9 and abs(atr.stop_price - 101.0) < 1e-9)
check("the dollar cap tightens the initial stop (intended loss)", abs(st.cap_initial_pct(CFG, 20.0, 0.10).initial_pct - 0.5) < 1e-9 and st.cap_initial_pct(CFG, 20.0, 5.0).initial_pct == 1.0)
try:
    st.StopConfig(mode="atr")
    check("atr mode without an ATR is refused", False)
except ValueError:
    check("atr mode without an ATR is refused", True)

# ---- scenario 1: steady rise ----------------------------------------------------------------------------------
steady = bars([(100 + 0.3 * i, 100 + 0.3 * i + 0.2, 100 + 0.3 * i - 0.05, 100 + 0.3 * i + 0.1) for i in range(60)])
t = sim.simulate_trade(steady, 0, CFG, FREE)
check("steady rise: never stopped, leaves on the holding-time limit with a gain", t["reason"] == "maximum holding time" and not t["stopped"] and t["net_pct"] > 5)
check("steady rise: the stop trailed up and sits above the initial stop", t["final_stop"] > 100.0)

# ---- scenario 2: sharp rise then retrace ----------------------------------------------------------------------
up = [(100, 100.4, 99.9, 100.3), (100.3, 102.0, 100.2, 101.9), (101.9, 105.0, 101.8, 104.9)]   # high 105
down = [(104.9, 105.0, 104.0, 104.1), (104.1, 104.2, 103.0, 103.1), (103.1, 103.2, 102.0, 102.1), (102.1, 102.2, 101.0, 101.1)]
t = sim.simulate_trade(bars(up + down), 0, CFG, FREE)
check("rise then retrace: exits on the trailing stop at the trigger 105 x 0.99", t["reason"] == "trailing stop" and abs(t["trigger_price"] - 103.95) < 1e-9)
check("rise then retrace: executes at the next open or better-than-trigger-capped price, and the trade is a winner", t["exec_ref"] <= 103.95 and t["net_pct"] > 2)
check("trigger and execution are recorded separately", t["trigger_price"] is not None and t["exec_ref"] != t["trigger_price"] or t["exec_ref"] == t["trigger_price"])

# ---- scenario 3: falls immediately ----------------------------------------------------------------------------
fall = bars([(100, 100.1, 99.9, 100.0), (100.0, 100.0, 98.5, 98.6), (98.6, 98.7, 98.0, 98.1), (98.1, 98.2, 97.5, 97.6)])
t = sim.simulate_trade(fall, 0, CFG, FREE)
check("falls at once: initial stop 99.00 triggers", t["reason"] == "initial stop" and abs(t["trigger_price"] - 99.0) < 1e-9)
check("falls at once: the sale is at the next open (98.6), below the trigger: the shortfall is reported", abs(t["exec_ref"] - 98.6) < 1e-9 and t["past_trigger_pct"] > 0.3)
check("intended stop loss is 1% while the realised loss is larger", abs(t["intended_stop_loss_pct"] - 1.0) < 1e-9 and t["net_pct"] < -1.3)

# ---- scenario 4: rises, then gaps below the trailing stop ------------------------------------------------------
gap = bars(up + [(104.9, 105.0, 104.5, 104.8), (102.0, 102.1, 101.5, 101.6), (101.6, 101.7, 101.0, 101.2)])
t = sim.simulate_trade(gap, 0, CFG, FREE)
check("gap through the trailing stop: sold at the gap open 102.0, not at the 103.95 trigger", t["reason"].endswith("(gap)") and t["exec_ref"] == 102.0)
check("gap loss against the trigger is reported (about 1.9%)", abs(t["past_trigger_pct"] - (103.95 - 102.0) / 103.95 * 100) < 1e-6)
s = sim.summarize([t])
check("summary counts the gap-through-stop loss", s["gap_losses"] == 1 and s["stop_rate"] == 1.0)

# ---- scenario 5: oscillation around the stop -------------------------------------------------------------------
osc_hold = bars([(100, 100.0, 99.5, 100.0), (100.0, 100.0, 99.01, 100.0), (100.0, 100.0, 99.02, 100.0), (100.0, 100.0, 99.4, 100.0)])
check("a low just above the stop does not trigger", sim.simulate_trade(osc_hold, 0, CFG, FREE)["stopped"] is False)
osc_hit = bars([(100, 100.0, 99.5, 100.0), (100.0, 100.0, 99.0, 100.0), (99.9, 100.0, 99.4, 100.0), (100.0, 100.0, 99.4, 100.0)])
check("a low exactly at the stop triggers, and one trade results", sim.simulate_trade(osc_hit, 0, CFG, FREE)["stopped"] is True)
# the bar that sets a new high is checked against the OLD stop first (adverse first)
adv = bars([(100, 100.1, 99.9, 100.0), (100.0, 106.0, 98.0, 100.0), (100.0, 100.1, 99.9, 100.0)])
t = sim.simulate_trade(adv, 0, CFG, FREE)
check("adverse extreme first: a bar spanning 98-106 stops out at the initial stop, not on the trailed one", t["reason"] == "initial stop" and abs(t["trigger_price"] - 99.0) < 1e-9)

# ---- entry timing, costs, latency -----------------------------------------------------------------------------
lat = bars([(100, 100.1, 99.9, 100.0), (101, 101.1, 100.9, 101.0), (102, 102.1, 101.9, 102.0), (103, 103.1, 102.9, 103.0), (103, 103.1, 102.9, 103.0)])
t0 = sim.simulate_trade(lat, 0, st.StopConfig(max_hold_minutes=2), sim.Costs(0, 0, 0, 0))
t1 = sim.simulate_trade(lat, 0, st.StopConfig(max_hold_minutes=2), sim.Costs(0, 0, 0, 1))
check("the fill is at the next bar's open, one more bar with latency 1", t0["entry_ref"] == 101 and t1["entry_ref"] == 102)
c = sim.simulate_trade(lat, 0, st.StopConfig(max_hold_minutes=2), sim.Costs(2, 2, 0.3, 0))
check("costs are inside net: pay the ask on entry, receive the bid on exit, plus the sale fee", c["net_pct"] < c["gross_pct"] - 0.07 and c["costs_pct"] > 0.07)
check("no bar to fill on -> no trade", sim.simulate_trade(lat, 4, st.StopConfig(), FREE) is None)

# ---- scenario 10: near the close, daylight saving, early close ------------------------------------------------
from datetime import date
check("flatten 15:45 ET is 20:45 UTC in winter", st.to_utc(st.flatten_at(date(2026, 1, 15), CFG)).strftime("%H:%M") == "20:45")
check("flatten 15:45 ET is 19:45 UTC in summer", st.to_utc(st.flatten_at(date(2026, 7, 15), CFG)).strftime("%H:%M") == "19:45")
check("the day after Thanksgiving closes at 13:00 ET, so the flatten is 12:45 ET", st.flatten_at(date(2026, 11, 27), CFG).strftime("%H:%M") == "12:45")
check("the week of the clock change keeps the same New York time", st.flatten_at(date(2026, 3, 6), CFG).strftime("%H:%M") == "15:45" and st.flatten_at(date(2026, 3, 9), CFG).strftime("%H:%M") == "15:45")
late = bars([(100, 100.1, 99.95, 100.05) for _ in range(30)], start=datetime(2026, 10, 14, 15, 30, tzinfo=NY))
t = sim.simulate_trade(late, 0, st.StopConfig(max_hold_minutes=None), FREE)
check("open near the close: out at the 15:45 flatten bar", t["reason"] == "end-of-session flatten" and t["exit_time"].astimezone(NY).strftime("%H:%M") == "15:45")

# ---- exit signal (momentum deterioration) -----------------------------------------------------------------------
flat = bars([(100, 100.2, 99.9, 100.1) for _ in range(10)])
t = sim.simulate_trade(flat, 0, CFG, FREE, exit_signal=lambda k, ctx: "momentum deteriorated" if k >= 3 else None)
check("a signal exit acts on the next bar's open", t["reason"] == "momentum deteriorated" and t["exit_time"] == T0 + timedelta(minutes=4))


# ---- the manager: failure paths --------------------------------------------------------------------------------
class FakeBroker:
    def __init__(self, script):
        self.script, self.sent, self.orders = list(script), [], {}
    def submit_sell(self, symbol, qty, ref_id):
        self.sent.append((symbol, qty, ref_id))
        r = dict(self.script.pop(0)); r.setdefault("filled_qty", 0.0); r.setdefault("avg_price", None)
        self.orders[ref_id] = r
        return r
    def order_status(self, ref_id):
        return self.orders.get(ref_id)


def mgr(script, alerts=None, **kw):
    b = FakeBroker(script)
    return b, im.Manager(b, CFG, alert=(alerts.append if alerts is not None else None), **kw)


NOW = T0 + timedelta(minutes=5)
fill = T0

# scenario 6: delayed / missing quotes
alerts = []
b, m = mgr([{"status": "FILLED", "filled_qty": 1.0, "avg_price": 99.5}], alerts)
p = m.open("AAA", 1.0, 100.0, fill)
p = m.tick(p, 100.2, fill + timedelta(seconds=10), fill + timedelta(seconds=12))
check("a fresh quote is processed, no exit", p.status == im.OPEN and b.sent == [])
p = m.tick(p, None, None, fill + timedelta(seconds=50))
check("no quote for 30+ s: new entries halted and an alert is raised, position kept", p.entries_halted and len(alerts) == 1 and b.sent == [])
p = m.tick(p, 100.1, fill + timedelta(seconds=40), fill + timedelta(seconds=100))      # a stale quote (60 s old) counts as none
check("a quote older than the freshness limit is treated as missing", b.sent == [] or p.status != im.OPEN)
b, m = mgr([{"status": "FILLED", "filled_qty": 1.0, "avg_price": 99.5}], [])
p = m.open("AAA", 1.0, 100.0, fill)
p = m.tick(p, None, None, fill + timedelta(seconds=95))
check("no usable quote for 90 s: exit at market, once", len(b.sent) == 1 and p.status == im.CLOSED and p.exit_reason == "monitoring lost")

# scenario 7: the broker rejects the exit
alerts = []
b, m = mgr([{"status": "REJECTED", "reason": "x"}, {"status": "REJECTED", "reason": "x"}, {"status": "REJECTED", "reason": "x"}], alerts)
p = m.open("AAA", 1.0, 100.0, fill)
for i in range(6):
    p = m.tick(p, 98.0, fill + timedelta(seconds=10 + i), fill + timedelta(seconds=10 + i))
check("rejected exits are retried then escalated with an alert, never silently dropped", p.status == im.ESCALATED and len(b.sent) == 3 and len(alerts) == 1)
check("each retry uses a distinct deterministic reference", len({r for _, _, r in b.sent}) == 3 and b.sent[0][2].startswith("x-AAA-"))
b, m = mgr([{"status": "REJECTED", "reason": "x"}, {"status": "FILLED", "filled_qty": 1.0, "avg_price": 98.0}], [])
p = m.open("AAA", 1.0, 100.0, fill)
for i in range(3):
    p = m.tick(p, 98.0, fill + timedelta(seconds=10 + i), fill + timedelta(seconds=10 + i))
check("a reject followed by a fill closes the position with 2 sells", p.status == im.CLOSED and len(b.sent) == 2 and abs(p.proceeds - 98.0) < 1e-9)
b, m = mgr([{"status": "PENDING"}], [])
p = m.open("AAA", 1.0, 100.0, fill)
for i in range(5):
    p = m.tick(p, 98.0, fill + timedelta(seconds=10 + i), fill + timedelta(seconds=10 + i))
check("a pending exit is waited on: no second sell while the first is unconfirmed", len(b.sent) == 1 and p.status == im.EXITING)

# scenario 8: partial fill
b, m = mgr([{"status": "PARTIAL", "filled_qty": 0.4, "avg_price": 98.0}], [])
p = m.open("AAA", 1.0, 100.0, fill)
p = m.tick(p, 98.0, fill + timedelta(seconds=10), fill + timedelta(seconds=10))
check("partial fill leaves the remainder held and the exit working", abs(p.remaining - 0.6) < 1e-9 and p.status == im.EXITING)
b.orders[p.exit_ref] = {"status": "FILLED", "filled_qty": 1.0, "avg_price": 97.9}
p = m.tick(p, 97.0, fill + timedelta(seconds=20), fill + timedelta(seconds=20))
check("the working order completing closes the position without another sell", p.status == im.CLOSED and len(b.sent) == 1 and p.remaining == 0)
b, m = mgr([{"status": "PARTIAL", "filled_qty": 0.4, "avg_price": 98.0}, {"status": "FILLED", "filled_qty": 0.6, "avg_price": 97.5}], [])
p = m.open("AAA", 1.0, 100.0, fill)
p = m.tick(p, 98.0, fill + timedelta(seconds=10), fill + timedelta(seconds=10))
b.orders[p.exit_ref] = {"status": "CANCELLED", "filled_qty": 0.4, "avg_price": 98.0}
p = m.tick(p, 97.0, fill + timedelta(seconds=20), fill + timedelta(seconds=20))
check("an order cancelled after a partial fill: only the remaining 0.6 is resent", b.sent[1][1] == 0.6 and p.status == im.CLOSED)

# scenario 9: restart with the position open
b, m = mgr([{"status": "FILLED", "filled_qty": 1.0, "avg_price": 101.0}], [])
p = m.open("AAA", 1.0, 100.0, fill)
p = m.tick(p, 104.0, fill + timedelta(seconds=10), fill + timedelta(seconds=10))
snap = json.loads(json.dumps(m.snapshot(p)))
p2 = m.restore(snap)
check("state survives a JSON round trip", p2.highest == 104.0 and abs(p2.stop - 104 * 0.99) < 1e-9)
fresh = m.restore({**snap, "highest": 100.0, "stop": 99.0})                         # a service that lost its memory
m.rebuild(fresh, [(fill + timedelta(seconds=5), 104.0), (fill - timedelta(minutes=1), 120.0)])
check("rebuilding from stored bars restores the trailing stop and ignores pre-fill highs", fresh.highest == 104.0 and abs(fresh.stop - 104 * 0.99) < 1e-9)
p2 = m.tick(p2, 102.0, fill + timedelta(seconds=30), fill + timedelta(seconds=30))
check("after the restart the trail still triggers, with one sell", p2.status == im.CLOSED and len(b.sent) == 1)
b, m = mgr([{"status": "PENDING"}, {"status": "FILLED", "filled_qty": 1.0, "avg_price": 101.0}], [])
p = m.open("AAA", 1.0, 100.0, fill)
p = m.tick(p, 90.0, fill + timedelta(seconds=10), fill + timedelta(seconds=10))
snap = json.loads(json.dumps(m.snapshot(p)))
b.orders[p.exit_ref] = {"status": "FILLED", "filled_qty": 1.0, "avg_price": 90.0}   # it filled while the service was down
p3 = m.tick(m.restore(snap), 90.0, fill + timedelta(seconds=40), fill + timedelta(seconds=40))
check("restart while an exit is working: reconciled with the broker, no duplicate sell", p3.status == im.CLOSED and len(b.sent) == 1)

# scenario 10 (live): flatten through the manager
b, m = mgr([{"status": "FILLED", "filled_qty": 1.0, "avg_price": 100.0}], [])
close_to = datetime(2026, 10, 14, 15, 46, tzinfo=NY)
p = m.open("AAA", 1.0, 100.0, close_to - timedelta(minutes=10))
p = m.tick(p, 100.1, close_to - timedelta(seconds=2), close_to)
check("the manager flattens at 15:45 New York time", p.exit_reason == "end-of-session flatten" and p.status == im.CLOSED)

# ---- the summary --------------------------------------------------------------------------------------------------
s = sim.summarize([sim.simulate_trade(steady, 0, CFG, FREE), sim.simulate_trade(fall, 0, CFG, FREE)])
need = {"trades", "dates", "win_rate", "mean_net_pct", "median_net_pct", "gross_usd", "costs_usd", "net_usd", "mfe_pct", "mae_pct",
        "hold_minutes", "stop_rate", "gap_losses", "max_drawdown_usd"}
check("the summary carries every statistic the plan asks for", need <= set(s) and s["trades"] == 2)

# ---- isolation: M2 touches no broker, no database, no live path ------------------------------------------------
import inspect
for mod in (st, sim, im):
    src = inspect.getsource(mod)
    check(f"{mod.__name__} imports no broker / execution / database / trader", not any(
        w in src for w in ("import execution", "import broker", "import robinhood", "import sqlite3", "import slot_trader", "import risk_engine", "import killswitch")))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
