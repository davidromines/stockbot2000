"""intraday_replay (Stage AD7): population replay, the random-time control, market intraday momentum, the pre-registered
prospective rule. Synthetic bars only; no network, no production database."""
import runtime  # noqa: F401
import json
import sqlite3
from datetime import datetime, timedelta

import numpy as np
import pandas as pd

import intraday_replay as rp
import intraday_stops as st

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

NY = rp.NY


def day_bars(day, p0, drift_per_min, n=390, vol=1000.0):
    t0 = datetime.fromisoformat(day).replace(hour=9, minute=30, tzinfo=NY)
    c = p0 * np.exp(np.arange(n) * drift_per_min)
    o = np.r_[p0, c[:-1]]
    return pd.DataFrame({"ts": [t0 + timedelta(minutes=i) for i in range(n)], "open": o, "high": np.maximum(o, c) * 1.0002,
                         "low": np.minimum(o, c) * 0.9998, "close": c, "volume": vol})


days = {d: {"SPY": day_bars(d, 700, 0.0), "AAA": day_bars(d, 100, 0.0002), "BBB": day_bars(d, 50, -0.0002)}
        for d in ("2026-10-13", "2026-10-14")}
calls = []


def fake_scan(cut, spy, now):
    calls.append(now)
    return {"candidates": [{"ticker": "AAA", "cost": 0.0009}, {"ticker": "BBB", "cost": 0.0009}], "rejected": {}}


stop = st.StopConfig(mode="pct", initial_pct=1.0, trail_pct=1.0, max_hold_minutes=60, flatten_hhmm="15:45")
S = {"entry_start": "09:50", "entry_end": "14:30"}
d = rp.replay(days, fake_scan, lambda k: stop, S, 5.0)
check("each name's first signal per session only", len(d) == 4 and d.groupby("day").ticker.nunique().eq(2).all(), d)
check("the scan runs every 5 minutes through the entry window", len(calls) == 2 * ((14 * 60 + 30 - (9 * 60 + 50)) // 5 + 1))
a = d[d.ticker == "AAA"].iloc[0]
check("first signal at the window's start", a.time == "09:50")
check("a rising name earns a positive gross return, a falling one negative",
      a.gross > 0 and d[d.ticker == "BBB"].iloc[0].gross < 0)
check("net is gross less costs", a.net < a.gross)
check("fixed horizons are measured from the bar after next", abs(a.r30 - (np.exp(0.0002 * 30) - 1)) < 1e-9, a.r30)
check("SPY over the same minutes is the market control (flat here)", abs(a.spy30) < 1e-12 and abs(a.x30 - a.r30) < 1e-12)
check("a random-time control is recorded for every signal", d.control_net.notna().all())
sm = rp.summarize(d)
check("summary: signals, sessions, t by day, vs control", sm["signals"] == 4 and sm["sessions"] == 2 and "t_vs_control" in sm, sm)
half = {"2026-10-15": {"SPY": day_bars("2026-10-15", 700, 0, n=210)}}
check("a half day (or no SPY) is skipped", rp.replay(half, fake_scan, lambda k: stop, S).empty)

# --- market intraday momentum: up first half-hour -> buy the bull leg at 15:30
rows = []
for k, (day, first, last) in enumerate((("2026-10-12", 0.0, 0.0), ("2026-10-13", +0.01, +0.002), ("2026-10-14", -0.01, -0.003))):
    prev_close = 100.0
    for t, o, c in (("SPY", prev_close, prev_close * (1 + first)), ("SH", 30.0, 30.0 * (1 - first))):
        rows.append({"ticker": t, "ts": f"{day} 09:30", "open": o, "high": c, "low": o, "close": c})
        lo = 1 + (last if t == "SPY" else -last)
        rows.append({"ticker": t, "ts": f"{day} 15:30", "open": 100.0 if t == "SPY" else 30.0, "high": 1, "low": 1,
                     "close": (100.0 if t == "SPY" else 30.0) * lo})
bars = pd.DataFrame(rows)
# the previous close used for day k is day k-1's 15:30 close; make day 2's first return explicit
t = rp.mim_table(bars, "09:30", "15:30", [("SPY", "SH", 1)], {"SPY": 0.0001, "SH": 0.0003})
check("one row per index day after the first", len(t) == 2, t)
up = t[t.day == "2026-10-13"].iloc[0]
dn = t[t.day == "2026-10-14"].iloc[0]
check("an up first period buys the bull ETF, a down one the inverse ETF (long, never short)",
      up.leg == "SPY" and dn.leg == "SH", t)
check("the timed trade is net of that leg's cost", abs(up.timed_net - (0.002 - 0.0001)) < 1e-9 and abs(dn.timed_net - (0.003 - 0.0003)) < 1e-9, t)
ms = rp.mim_summary(t)
check("the summary reports correlation, hit rate and the always-long control", {"corr", "hit", "long_mean"} <= set(ms.columns))

# --- pre-registration and the prospective evaluation
c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
e = rp.register(c)
check("the decision rule is registered and locked", e["status"] == "REGISTERED" and "300" in e["spec"])
check("registering again is a no-op", rp.register(c)["version"] == e["version"])
c.execute("CREATE TABLE intraday_runner_signals (id INTEGER PRIMARY KEY, at TEXT, session TEXT, ticker TEXT, score REAL, "
          "features TEXT, action TEXT, note TEXT, calibrated INT)")
c.execute("CREATE TABLE minute_bars (ticker TEXT, ts TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
b = day_bars("2026-10-20", 100, 0.0002)
c.executemany("INSERT INTO minute_bars VALUES ('AAA',?,?,?,?,?,?)",
              [(x.ts.strftime("%Y-%m-%d %H:%M"), x.open, x.high, x.low, x.close, x.volume) for x in b.itertuples()])
c.execute("INSERT INTO intraday_runner_signals (at, session, ticker, features, action) VALUES "
          "('2026-10-20T14:10:20+00:00','2026-10-20','AAA',?, 'QUALIFIED')", (json.dumps({"cost": 0.0009}),))
c.execute("INSERT INTO intraday_runner_signals (at, session, ticker, features, action) VALUES "
          "('2026-10-16T14:10:20+00:00','2026-10-16','AAA','{}', 'QUALIFIED')")
cfg = {"intraday": {"stage": "LIVE", "slots": [3]}, "intraday_twin": {"stage": "LIVE", "slots": [5]}}
p = rp.prospective(c, cfg)
check("only signals from the registered start are evaluated", len(p) == 1 and p.iloc[0].day == "2026-10-20", p)
check("a stock signal is exited by the stock Runner's stop rules", p.iloc[0].runner == "stock" and p.iloc[0].net > 0)
v = rp.verdict(p)
check("before the fixed sample the call is INTERIM", v["stock"]["call"] == "INTERIM", v)
rng = np.random.default_rng(1)
big = pd.DataFrame({"day": [f"d{i % 30}" for i in range(300)], "runner": "stock", "net": 0.002 + rng.normal(0, 0.004, 300)})
check("at the fixed sample a positive, significant mean passes to paper", rp.verdict(big)["stock"]["call"] == "PASS: to paper",
      rp.verdict(big))
big["net"] = -0.001
check("...and a mean <= 0 retires v0", rp.verdict(big)["stock"]["call"] == "RETIRE v0")
check("the report renders all three parts", "Market intraday momentum" in rp.render({"stock": d, "twin": d.iloc[:0],
                                                                                  "sessions": 2, "tickers": 3},
                                                                                 {"30m": t}, v))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
