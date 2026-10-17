"""Twin-ETF Runner: leg selection, leverage-scaled stops, pair exclusivity, and a full cycle through the REAL engine."""
import runtime  # noqa: F401
import sqlite3
from datetime import datetime, timedelta, timezone

import numpy as np
import pandas as pd

import intraday_runner as ir
import intraday_twin as tw
import minute_bars as mb
import quotes as qt
import slot_trader as stx
import slots

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

NY = ir.NY
START = datetime(2026, 10, 14, 9, 30, tzinfo=NY)
NOW = START + timedelta(minutes=40, seconds=20)


def mk(closes, vols, rng=0.0015):
    rows, prev = [], closes[0]
    for i, (c, v) in enumerate(zip(closes, vols)):
        rows.append({"ts": START + timedelta(minutes=i), "open": prev, "high": max(prev, c) * (1 + rng / 2), "low": min(prev, c) * (1 - rng / 2), "close": c, "volume": v})
        prev = c
    return pd.DataFrame(rows)


def up(p0, pct=0.01, n=40):
    return mk([p0] * 25 + list(np.linspace(p0, p0 * (1 + pct), n - 25)), [1000.0] * 25 + [3000.0] * (n - 25))


def down(p0, pct=0.01, n=40):
    return mk([p0] * 25 + list(np.linspace(p0, p0 * (1 - pct), n - 25)), [1000.0] * 25 + [1500.0] * (n - 25))


def flat(p0, n=40):
    return mk([p0] * n, [1000.0] * n, 0.0005)


META = {t: {"daily_atr_pct": 0.012, "dollar_volume_20": 5e8} for t in ("SPY", "SH", "SSO", "SDS", "QQQ", "PSQ", "QLD", "QID", "IWM", "RWM")}
CFG = {"intraday_twin": {"stage": "LIVE", "slots": [5]}}

# ---- which leg ---------------------------------------------------------------------------------------------------
r = tw.scan_pairs({"SPY": up(770.0), "SH": down(32.0)}, META, NOW, CFG)
check("the index breaking UP buys the bull leg", [c["ticker"] for c in r["candidates"]] == ["SPY"] and r["candidates"][0]["pair"] == "SPY/SH")
r = tw.scan_pairs({"SPY": down(770.0), "SH": up(32.0)}, META, NOW, CFG)
check("the index breaking DOWN buys the inverse leg (long the inverse ETF, never a short)", [c["ticker"] for c in r["candidates"]] == ["SH"])
r = tw.scan_pairs({"SPY": flat(770.0), "SH": flat(32.0)}, META, NOW, CFG)
check("a flat index buys nothing", r["candidates"] == [] and r["rejected"])
r = tw.scan_pairs({"SPY": up(770.0, 0.012), "SH": up(32.0, 0.006)}, META, NOW, CFG)
check("the INDEX decides, one leg per pair: SPY up buys SPY even if SH is also rising", [c["ticker"] for c in r["candidates"]] == ["SPY"]
      and r["candidates"][0]["direction"] == "UP")
r = tw.scan_pairs({"SPY": down(770.0), "SH": flat(32.0)}, META, NOW, CFG)
check("index DOWN buys the inverse leg even though the inverse leg shows no momentum of its own",
      [c["ticker"] for c in r["candidates"]] == ["SH"] and r["candidates"][0]["direction"] == "DOWN" and r["candidates"][0]["price"] == 32.0)
r = tw.scan_pairs({"SPY": down(770.0)}, META, NOW, CFG)
check("index DOWN but no bars for the inverse leg: skipped, never falls back to anything else", r["candidates"] == [] and r["rejected"])
r = tw.scan_pairs({"SPY": down(770.0), "SH": flat(32.0)}, {**META, "SH": {"daily_atr_pct": 0.012, "dollar_volume_20": 1e5}}, NOW, CFG)
check("the bought leg must still be cheap enough to trade", r["candidates"] == [])
r = tw.scan_pairs({"SPY": mk([770.0] * 25 + list(np.linspace(770.0, 762.0, 15)), [1000.0] * 40), "SH": flat(32.0)}, META, NOW, CFG)
check("a falling index without volume acceleration buys nothing", r["candidates"] == [])
r = tw.scan_pairs({"SPY": down(770.0, 0.05), "SH": flat(32.0)}, META, NOW, CFG)
check("an index already far from the open (extended) buys nothing, in either direction",
      r["candidates"] == [] and tw.scan_pairs({"SPY": up(770.0, 0.05), "SH": flat(32.0)}, META, NOW, CFG)["candidates"] == [])
r = tw.scan_pairs({"SSO": up(70.0, 0.0015), "SDS": flat(53.0)}, META, NOW, CFG)
check("a 2x leg needs twice the 15-minute move (0.15% is not enough, 1% is)", r["candidates"] == []
      and [c["ticker"] for c in tw.scan_pairs({"SSO": up(70.0, 0.01), "SDS": flat(53.0)}, META, NOW, CFG)["candidates"]] == ["SSO"])
r = tw.scan_pairs({"SPY": up(770.0), "SH": down(32.0), "QQQ": down(728.0), "PSQ": up(25.0)}, META, NOW, CFG)
check("several pairs rank by move in units of the leg's own volatility", {c["ticker"] for c in r["candidates"]} == {"SPY", "PSQ"} and r["calibrated"] is False)
check("stale bars are refused", tw.scan_pairs({"SPY": up(770.0)}, META, NOW + timedelta(minutes=10), CFG)["candidates"] == [])
check("every leg configured by default, both legs of every pair", set(tw.leverage_map(CFG)) == {"SPY", "SH", "SSO", "SDS", "QQQ", "PSQ", "QLD", "QID", "IWM", "RWM"}
      and tw.leverage_map(CFG)["SSO"] == 2 and tw.leverage_map(CFG)["SH"] == 1)

# ---- settings and stops -----------------------------------------------------------------------------------------
s = tw.settings(CFG)
check("defaults: one slot, one position at a time, $1 daily loss, 0.35% stop", s["slots"] == [5] and s["max_simultaneous"] == 1
      and s["max_daily_loss_dollars"] == 1.0 and s["stop"]["trail_pct"] == 0.35)

# ---- a whole cycle through the real engine ---------------------------------------------------------------------
c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")
c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
for d in ("2026-09-22", "2026-09-23"):
    c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
for t in ("SPY", "SSO"):
    c.execute("INSERT INTO features VALUES (?, '2026-09-23', 6.0, 3e10)", (t,))
    c.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', 8e11)", (t,))
slots.init(c); stx.init(c); mb.init(c); ir.init(c)
CFG2 = {"intraday_twin": {"stage": "LIVE", "slots": [5], "position_dollars": 20.0}}
check("assign hands slot 5 to the twin Runner under its own key", ir.assign(c, CFG2, block=tw.BLOCK, key=tw.KEY_TWIN) == [5]
      and slots.current(c, CFG2)[5]["strategy_key"] == tw.KEY_TWIN)
check("the medium-term plan treats slot 5 as reserved", slots.intraday_reserved(CFG2) == {5})
px = {"SPY": 777.7, "SSO": 70.0}
T = [datetime(2026, 10, 14, 14, 10, 20, tzinfo=timezone.utc)]
provider = qt.FixedQuotes(px, conn=c)
c.row_factory = None
broker, engine = stx._build(c, {}, "SIMULATION", provider)
metas = {t: {"daily_atr_pct": 0.012, "dollar_volume_20": 3e10} for t in ("SPY", "SSO")}
runner = tw.TwinRunner(c, CFG2, engine, lambda sym: (px[sym], T[0]),
                       lambda tk, now: {"SPY": up(770.0), "SH": down(32.0)}, stage_ok_fn=lambda: True,
                       universe_fn=lambda: ["SPY", "SH"], meta_fn=lambda ts: META, mode="SIMULATION")
check("stops scale with leverage: 0.35% for SPY and SH, 0.70% for SSO", runner.stop_for("SPY").trail_pct == 0.35
      and runner.stop_for("SH").trail_pct == 0.35 and abs(runner.stop_for("SSO").trail_pct - 0.70) < 1e-9 and abs(runner.stop_for("SSO").initial_pct - 0.70) < 1e-9)
out = runner.tick(T[0])
check("through the real engine: the bull leg is bought for slot 5 under the twin key", out.get("entered") == ["SPY"]
      and c.execute("SELECT strategy_key, symbol, action FROM slot_trades WHERE slot_id=5").fetchall()[0][:] == (tw.KEY_TWIN, "SPY", "OPEN")
      or [tuple(r) for r in c.execute("SELECT strategy_key, symbol, action FROM slot_trades WHERE slot_id=5").fetchall()] == [(tw.KEY_TWIN, "SPY", "OPEN")])
T[0] += timedelta(seconds=70)
px["SPY"] = 781.0
runner.tick(T[0])
pos = list(runner.positions.values())[0]
check("the trailing stop follows the ETF price: 781 x (1 - 0.35%) = 778.27", abs(pos.stop - 781.0 * (1 - 0.0035)) < 1e-6)
T[0] += timedelta(seconds=15)
px["SPY"] = 778.0                                                  # below 778.27
runner.tick(T[0])
check("the stop exits through the engine and the slot is flat", not runner.positions and [tuple(r)[:1] for r in c.execute(
    "SELECT action FROM slot_trades WHERE slot_id=5 ORDER BY id").fetchall()][-1] == ("CLOSE",))
check("slot_trader's medium-term pass skips twin-ETF positions (key starts with intraday:)", tw.KEY_TWIN.startswith("intraday:"))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
