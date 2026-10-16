"""The Intraday Runner through the REAL ExecutionEngine / RiskEngine / simulated ledger broker (no fake engine).

Added 2026-10-15 after the first live day: the Runner scanned all session but every entry died in
ExecutionEngine._counts with "tuple indices must be integers or slices, not str", because the service's connection did
not use sqlite3.Row. The earlier cycle test used a fake engine and could not see it. This one cannot be fooled that way.
"""
import runtime  # noqa: F401
import sqlite3
from datetime import datetime, timedelta, timezone

import pandas as pd

import intraday_runner as ir
import quotes as qt
import slot_trader as stx
import slots
import minute_bars as mb

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)


def bars(n=40):
    import numpy as np
    START = datetime(2026, 10, 14, 9, 30, tzinfo=ir.NY)
    closes = [100.0] * 25 + list(np.linspace(100.0, 101.0, n - 25))
    vols = [1000.0] * 25 + [3000.0] * (n - 25)
    rows, prev = [], closes[0]
    for i, (c, v) in enumerate(zip(closes, vols)):
        rows.append({"ts": START + timedelta(minutes=i), "open": prev, "high": max(prev, c) * 1.00075, "low": min(prev, c) * 0.99925, "close": c, "volume": v})
        prev = c
    return pd.DataFrame(rows)


def spy(n=40):
    import numpy as np
    START = datetime(2026, 10, 14, 9, 30, tzinfo=ir.NY)
    cl = list(np.linspace(400.0, 400.2, n))
    return pd.DataFrame([{"ts": START + timedelta(minutes=i), "open": cl[i], "high": cl[i] * 1.0002, "low": cl[i] * 0.9998, "close": cl[i], "volume": 1e6} for i in range(n)])


c = sqlite3.connect(":memory:")                                   # deliberately a PLAIN connection (no row_factory)
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL, source TEXT)")
c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
for d in ("2026-09-22", "2026-09-23"):
    c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
c.execute("INSERT INTO features VALUES ('AAA', '2026-09-23', 2.0, 2e8)")
c.execute("INSERT INTO fundamentals VALUES ('AAA', '2026-01-01', 5e9)")
slots.init(c); stx.init(c); mb.init(c); ir.init(c)
CFG = {"intraday": {"stage": "LIVE", "slots": [3, 5], "position_dollars": 20.0}}
ir.assign(c, CFG)

px = {"AAA": 101.0}
T = [datetime(2026, 10, 14, 14, 10, 20, tzinfo=timezone.utc)]
provider = qt.FixedQuotes(px, conn=c)
sim_conn_factory = c
c.row_factory = None
broker, engine = stx._build(c, {}, "SIMULATION", provider)
runner = ir.Runner(c, CFG, engine, lambda s: (px[s], T[0]), lambda tk, now: {"AAA": bars(), "SPY": spy()}, stage_ok_fn=lambda: True,
                   universe_fn=lambda: ["AAA"], meta_fn=lambda ts: {"AAA": {"daily_atr_pct": 0.025, "dollar_volume_20": 2e8}}, mode="SIMULATION")
check("the Runner forces sqlite3.Row on its connection", c.row_factory is sqlite3.Row)
out = runner.tick(T[0])
check("through the real engine: the leader is bought (no TypeError)", out.get("entered") == ["AAA"] and len(runner.positions) == 1)
check("the order is in the orders table as FILLED and the slot ledger has the OPEN", c.execute(
    "SELECT state FROM orders WHERE symbol='AAA' AND side='BUY'").fetchone()[0] == "FILLED"
      and c.execute("SELECT action, mode FROM slot_trades WHERE slot_id=3").fetchall()[0][0] == "OPEN")
check("the simulated account really holds the shares (reconciles with the ledger)", stx.reconcile(c, broker, "SIMULATION")[0])
T[0] += timedelta(seconds=70)
px["AAA"] = 103.0
runner.tick(T[0])
check("a higher price lifts the trailing stop", list(runner.positions.values())[0].highest == 103.0)
T[0] += timedelta(seconds=15)
px["AAA"] = 101.5                                                  # below 103 x 0.99 = 101.97
runner.tick(T[0])
check("the stop exits through the real engine: SELL filled, CLOSE in the ledger, nothing left open", not runner.positions
      and c.execute("SELECT action FROM slot_trades WHERE slot_id=3 ORDER BY id").fetchall()[-1][0] == "CLOSE"
      and c.execute("SELECT COUNT(*) FROM orders WHERE symbol='AAA' AND side='SELL' AND state='FILLED'").fetchone()[0] == 1)
check("the account is flat again and reconciles", stx.reconcile(c, broker, "SIMULATION")[0])
T[0] += timedelta(seconds=70)
out = runner.tick(T[0])
check("the same symbol is not bought again that session", not out.get("entered") and not runner.positions)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
