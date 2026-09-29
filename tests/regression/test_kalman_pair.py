"""Regression tests for kalman_pair.py (TASK-057)."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import kalman_pair as kp  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s  %s" % (name, detail))
        FAILED.append(name)


def synth(n=600, seed=7):
    rs = np.random.RandomState(seed)
    idx = pd.bdate_range("2006-07-03", periods=n).strftime("%Y-%m-%d")
    x = 100.0 * np.exp(np.cumsum(rs.normal(0, 0.01, n)))
    noise = np.zeros(n)
    for i in range(1, n):
        noise[i] = 0.8 * noise[i - 1] + rs.normal(0, 0.5)
    y = 1.5 * x + 10.0 + noise
    return pd.Series(x, index=idx), pd.Series(y, index=idx)


def make_db(x, y):
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, "
                 "high REAL, low REAL, close REAL, volume REAL)")
    rows = []
    for i, d in enumerate(x.index):
        rows.append(("EWA", d, x.iloc[i], x.iloc[i], x.iloc[i], x.iloc[i], 1e6))
        rows.append(("EWC", d, y.iloc[i], y.iloc[i], y.iloc[i], y.iloc[i], 1e6))
        rows.append(("SPY", d, 100.0, 100.0, 100.0, 100.0, 1e6))
    # A date SPY did not trade (both legs present), plus a date where EWC is missing.
    rows.append(("EWA", "2006-07-01", 1.0, 1.0, 1.0, 1.0, 1e6))
    rows.append(("EWC", "2006-07-01", 1.0, 1.0, 1.0, 1.0, 1e6))
    rows.append(("EWA", "2006-06-30", 1.0, 1.0, 1.0, 1.0, 1e6))
    rows.append(("SPY", "2006-06-30", 1.0, 1.0, 1.0, 1.0, 1e6))
    conn.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()
    return conn


def main():
    x, y = synth()
    kf = kp.kalman(x, y)

    check("kalman columns", list(kf.columns) == ["slope", "intercept", "e", "q"])
    check("kalman index preserved", list(kf.index) == list(x.index))
    check("slope converges near 1.5",
          abs(kf["slope"].iloc[-100:].mean() - 1.5) < 0.2,
          "mean=%.4f" % kf["slope"].iloc[-100:].mean())
    check("e mean near zero", abs(kf["e"].iloc[-100:].mean()) < 0.5,
          "mean=%.4f" % kf["e"].iloc[-100:].mean())
    check("q positive", bool((kf["q"] > 0).all()))

    pos = kp.positions(kf, entry_z=1.0)
    check("positions in {-1,0,+1}", set(pos.unique()).issubset({-1, 0, 1}))
    check("positions same length", len(pos) == len(kf))

    e = kf["e"].to_numpy()
    sd = np.sqrt(kf["q"].to_numpy())
    prev = pos.shift(1).fillna(0).to_numpy()
    ok_entry = True
    for i in range(len(pos)):
        if prev[i] == 0 and pos.iloc[i] == 1 and not (e[i] < -1.0 * sd[i]):
            ok_entry = False
        if prev[i] == 0 and pos.iloc[i] == -1 and not (e[i] > 1.0 * sd[i]):
            ok_entry = False
    check("entries only on z breach", ok_entry)

    conn = make_db(x, y)
    close, open_ = kp.load(conn, "EWA", "EWC", "2006-01-01", "2012-12-31")
    check("load keeps both legs", list(close.columns) == ["EWA", "EWC"])
    check("load drops SPY-missing date", "2006-07-01" not in close.index)
    check("load drops missing-leg date", "2006-06-30" not in close.index)
    check("load restricted to SPY dates", len(close) == len(x))

    params = {"mode": "spread", "delta": 0.0001, "ve": 0.001, "entry_z": 1.0}
    res = kp.backtest(close, open_, "EWA", "EWC", params,
                      close.index[0], close.index[-1], cost_bps=5.0)
    check("spread backtest has trades", res["n_trades"] > 0)
    check("mean_net < mean_gross", res["mean_net"] < res["mean_gross"])
    # Exact spread arithmetic: y cheap vs x (long spread) then y recovers, x flat.
    up = kp._spread_ret(+1, 1.5, 20.0, 30.0, 20.0, 31.0)
    check("long spread gains when y recovers relative to x", up > 0, up)
    check("short spread loses on the same move", kp._spread_ret(-1, 1.5, 20.0, 30.0, 20.0, 31.0) < 0)
    check("spread return is sized on both legs' notional",
          abs(up - (1.0 / 30.0) / (1.0 + 1.5 * 20.0 / 30.0)) < 1e-12, up)
    check("max_drawdown in [0,1]",
          0.0 <= res["max_drawdown"] <= 1.0,
          "dd=%.4f" % res["max_drawdown"])

    # Fills must land on the session after the signal day.
    dates = list(close.index)
    ok_fill = True
    for t in res["trades"]:
        if t["entry_date"] not in dates or t["exit_date"] not in dates:
            ok_fill = False
        if dates.index(t["exit_date"]) <= dates.index(t["entry_date"]):
            ok_fill = False
    check("fills on session after signal", ok_fill)

    lp = {"mode": "long_leg", "delta": 0.0001, "ve": 0.001, "entry_z": 1.0}
    res2 = kp.backtest(close, open_, "EWA", "EWC", lp,
                       close.index[0], close.index[-1], cost_bps=5.0)
    check("long_leg never shorts",
          all(not t["side"].startswith("short") for t in res2["trades"]))
    check("long_leg has trades", res2["n_trades"] > 0)
    check("long_leg mean_net < mean_gross",
          res2["mean_net"] < res2["mean_gross"])

    check("PAIRS declared", len(kp.PAIRS) == 6 and ("EWA", "EWC") in kp.PAIRS)

    conn.close()
    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
