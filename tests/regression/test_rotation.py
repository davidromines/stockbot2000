"""Regression tests for rotation.py (synthetic frames, no market database)."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import rotation  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


def make_frames(n=400):
    dates = pd.bdate_range("2015-01-01", periods=n).strftime("%Y-%m-%d")
    idx = pd.Index(dates)
    close = pd.DataFrame(index=idx)
    close["SPY"] = 100.0 * (1.0004 ** np.arange(n))
    close["SHY"] = 100.0 * (1.00005 ** np.arange(n))
    close["UP"] = 50.0 * (1.002 ** np.arange(n))
    close["DOWN"] = 50.0 * (0.998 ** np.arange(n))
    close["FLAT"] = 50.0 + np.zeros(n)
    open_ = close.shift(1).fillna(close.iloc[0])
    return close, open_


def main():
    close, open_ = make_frames()
    as_of = close.index[-1]
    lb = 126

    r = rotation.rank(close, as_of, lb, ["UP", "DOWN", "FLAT"])
    check("rank orders by trailing return", [t for t, _ in r] == ["UP", "FLAT", "DOWN"], str(r))
    check("rank returns trailing return values", abs(r[0][1] - (close.at[as_of, "UP"] / close.at[close.index[-1 - lb], "UP"] - 1)) < 1e-12)

    holed = close.copy()
    holed.loc[as_of, "FLAT"] = np.nan
    r2 = rotation.rank(holed, as_of, lb, ["UP", "DOWN", "FLAT"])
    check("rank omits ticker with missing data", "FLAT" not in [t for t, _ in r2], str(r2))

    p = {"universe": ["UP", "DOWN", "FLAT"], "lookback": lb, "top_k": 2, "abs_filter": False}
    h = rotation.holdings(close, as_of, p)
    check("holdings takes the top_k", h == ["UP", "FLAT"], str(h))
    check("holdings without abs_filter never holds SAFE", rotation.SAFE not in h, str(h))

    pa = dict(p, abs_filter=True)
    ha = rotation.holdings(close, as_of, pa)
    check("abs_filter replaces a pick trailing SHY with SHY", ha == ["UP", rotation.SAFE], str(ha))

    losers = close.copy()
    losers["UP"] = 50.0 * (0.999 ** np.arange(len(close)))
    losers["FLAT"] = 50.0 * (0.9995 ** np.arange(len(close)))
    hb = rotation.holdings(losers, as_of, pa)
    check("all-losers book becomes [SHY]", hb == [rotation.SAFE], str(hb))

    check("holdings returns [] when nothing rankable", rotation.holdings(close, close.index[10], p) == [])   # 10 sessions < lookback

    ms = rotation.month_starts(close.index)
    months = pd.Series(close.index).str[:7]
    check("month_starts returns one date per month", len(ms) == months.nunique(), "%d vs %d" % (len(ms), months.nunique()))
    check("month_starts are first sessions", all(pd.Series(close.index).str[:7][pd.Series(close.index).tolist().index(d)] !=
                                                 pd.Series(close.index).str[:7][pd.Series(close.index).tolist().index(d) - 1]
                                                 for d in ms[1:]))

    bt = rotation.backtest(close, open_, p, close.index[0], close.index[-1], cost_bps=5.0)
    check("backtest produced trades", bt["n_trades"] > 0, str(bt["n_trades"]))
    eq = bt["equity"]
    daily_up = close["UP"].iloc[-1] / close["UP"].iloc[0]
    check("the equity curve cannot beat holding the best asset the whole time", eq.iloc[-1] <= daily_up * 1.01,
          (eq.iloc[-1], daily_up))
    # the first signal day with enough history to rank (126 sessions), not the first month-end
    sig = [d for d in rotation._signal_days(close, close.index[0], close.index[-1])
           if rotation.holdings(close, d, p)][0]
    first = bt["trades"][0]
    check("trades fill at the next session's open", first["entry_date"] == close.index[close.index.get_loc(sig) + 1], str(first))
    check("mean_net below mean_gross by the cost", bt["mean_net"] < bt["mean_gross"], "%s %s" % (bt["mean_net"], bt["mean_gross"]))
    check("max_drawdown in [0,1]", 0.0 <= bt["max_drawdown"] <= 1.0, str(bt["max_drawdown"]))
    check("equity starts at 1.0", abs(float(bt["equity"].iloc[0]) - 1.0) < 1e-9, str(bt["equity"].iloc[0]))
    up_days = sum(1 for t in bt["trades"] if t["ticker"] == "UP")
    check("uptrend ticker held most of the time", up_days >= bt["n_trades"] * 0.5, "%d/%d" % (up_days, bt["n_trades"]))

    carried = rotation.backtest(close, open_, {"universe": ["UP"], "lookback": lb, "top_k": 1, "abs_filter": False},
                                close.index[0], close.index[-1], cost_bps=5.0)
    check("a carried holding makes no new trade", carried["n_trades"] == 1, str(carried["n_trades"]))

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
    rows = []
    for t in ["SPY", "UP", "SHY"]:
        for i, d in enumerate(close.index):
            rows.append((t, d, float(open_.at[d, t]), 0.0, 0.0, float(close.at[d, t]), 0.0))
    rows.append(("UP", "2015-01-03", 1.0, 1.0, 1.0, 1.0, 1.0))  # a Saturday: a date SPY lacks
    conn.executemany("INSERT INTO prices VALUES (?,?,?,?,?,?,?)", rows)
    c2, o2 = rotation.load(conn, ["UP"], "2015-01-01", "2016-12-31")
    check("load pivots the prices table", list(c2.columns) == ["SHY", "SPY", "UP"], str(list(c2.columns)))
    check("load keeps only SPY's dates", "2015-01-03" not in c2.index, "")
    check("load drops dates SPY lacks", len(c2) == len(close), "%d vs %d" % (len(c2), len(close)))
    check("load returns matching open frame", list(o2.index) == list(c2.index))

    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
