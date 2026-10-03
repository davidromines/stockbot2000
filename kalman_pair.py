"""Stage AA: Kalman-filter ETF pair mean reversion (Chan 2013, Example 3.3).

Pure functions over price frames plus loaders. Two declared modes:

  "spread"    long y, short slope units of x. Research benchmark only; this
              account cannot short, so it is never tradeable here.
  "long_leg"  buy only the leg the spread calls cheap. Tradeable.

Signals are computed on a close and fill at the NEXT session's open, matching
the project's fill convention.

The backtest loses after costs, but the strategy is paper-tracked anyway: every
strategy accrues a forward record from the day it exists, judged or not, so a
backtest that looks bad today can still be re-examined against real forward
evidence later.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import json
import sqlite3
import sys
from datetime import date

import numpy as np
import pandas as pd

# Declared before any result is computed, so the pair list cannot be tuned to
# the outcome after the fact.
WARMUP = "2004-01-01"   # filter history starts here; trades count only inside the window
PAIRS = [("EWA", "EWC"), ("GLD", "GDX"), ("XLE", "XOP"),
         ("EWU", "EWG"), ("XLF", "KBE"), ("SPY", "RSP")]

# The one pair this fund tracks. Kept as a module constant so the label, the
# strategy JSON and the signal call cannot drift apart.
FUND_LABEL = "kalman_ewa_ewc"
FUND_FAMILY = "kalman_pair"
FUND_PAIR = ("EWA", "EWC")
FUND_CAPITAL = 100.0

DEFAULT_PARAMS = {"mode": "long_leg", "delta": 0.0001, "ve": 0.001,
                  "entry_z": 1.0}


def kalman(x, y, delta=0.0001, ve=0.001):
    """Chan eq. 3.5-3.13. x is augmented with a ones column; beta is
    (slope, intercept). Returns slope, intercept, e and q per day, all
    computed from the beta BEFORE that day's update (the prediction)."""
    x = pd.Series(x).astype(float)
    y = pd.Series(y).astype(float)
    if len(x) != len(y):
        raise ValueError("x and y must be aligned")
    if x.isna().any() or y.isna().any():
        raise ValueError("x and y must not contain NaN")

    vw = delta / (1.0 - delta) * np.eye(2)
    beta = np.zeros(2)
    p = np.zeros((2, 2))

    n = len(x)
    slope = np.empty(n)
    intercept = np.empty(n)
    err = np.empty(n)
    q = np.empty(n)

    for i in range(n):
        xt = np.array([x.iloc[i], 1.0])
        r = p + vw
        yhat = float(xt @ beta)
        qq = float(xt @ r @ xt) + ve
        e = float(y.iloc[i]) - yhat
        # Record the forecast, not the posterior: the signal must be
        # actionable at the close, before the day's information is absorbed.
        slope[i] = beta[0]
        intercept[i] = beta[1]
        err[i] = e
        q[i] = qq
        k = (r @ xt) / qq
        beta = beta + k * e
        p = r - np.outer(k, xt @ r)

    return pd.DataFrame({"slope": slope, "intercept": intercept,
                         "e": err, "q": q}, index=x.index)


def positions(kf, entry_z=1.0):
    """State machine in {-1, 0, +1}. +1 means long y / short slope x."""
    e = kf["e"].to_numpy()
    sd = np.sqrt(kf["q"].to_numpy())
    out = np.zeros(len(e), dtype=int)
    state = 0
    for i in range(len(e)):
        if state == 0:
            if e[i] < -entry_z * sd[i]:
                state = 1
            elif e[i] > entry_z * sd[i]:
                state = -1
        elif state == 1:
            if e[i] >= 0.0:
                state = 0
        else:
            if e[i] <= 0.0:
                state = 0
        out[i] = state
    return pd.Series(out, index=kf.index, dtype=int)


def load(conn, a, b, start, end):
    """Closes and opens for a and b on SPY's trading days, dropping any date
    where either close is missing."""
    q = ("SELECT ticker, date, close, open FROM prices "
         "WHERE ticker IN (?, ?, 'SPY') AND date >= ? AND date <= ?")
    df = pd.read_sql_query(q, conn, params=(a, b, start, end))
    if df.empty:
        empty = pd.DataFrame(columns=[a, b])
        return empty, empty.copy()
    close = df.pivot(index="date", columns="ticker", values="close")
    open_ = df.pivot(index="date", columns="ticker", values="open")
    if "SPY" not in close.columns:
        empty = pd.DataFrame(columns=[a, b])
        return empty, empty.copy()
    # SPY defines the session calendar; a date SPY did not trade is not a
    # session, even if a stale row exists for one of the legs.
    keep = close["SPY"].notna()
    close = close.loc[keep]
    open_ = open_.reindex(close.index)
    close = close[[a, b]].dropna()
    open_ = open_.reindex(close.index)[[a, b]]
    close.index.name = "date"
    open_.index.name = "date"
    return close, open_


def _spread_ret(side, slope0, px_a, py_a, px_b, py_b):
    """Gross return of one unit-notional spread position, long y short x."""
    rx = px_b / px_a - 1.0
    ry = py_b / py_a - 1.0
    # Size the short leg so both legs carry equal notional at entry; the
    # hedge ratio is slope * (price_x / price_y) shares of x per share of y.
    w = slope0 * px_a / py_a
    gross = (ry - w * rx) / (1.0 + w)
    return side * gross


def backtest(close, open_, a, b, params, start, end, cost_bps=5.0):
    mode = params["mode"]
    if mode not in ("spread", "long_leg"):
        raise ValueError("mode must be 'spread' or 'long_leg'")
    delta = float(params["delta"])
    ve = float(params["ve"])
    entry_z = float(params["entry_z"])

    # The filter sees the whole history including warm-up; only signal days
    # inside [start, end] may open a trade.
    kf = kalman(close[a], close[b], delta=delta, ve=ve)
    pos = positions(kf, entry_z=entry_z)

    dates = list(close.index)
    in_window = [d for d in dates if start <= d <= end]
    if not in_window:
        return {"trades": [], "n_trades": 0, "mean_net": 0.0,
                "mean_gross": 0.0, "win_rate": 0.0, "avg_hold": 0.0,
                "equity": pd.Series(dtype=float), "cagr": 0.0,
                "max_drawdown": 0.0}

    cost = cost_bps / 10000.0
    trades = []
    open_side = 0
    entry_i = None
    entry_slope = 0.0

    for i, d in enumerate(dates):
        if d < start or d > end:
            continue
        want = int(pos.iloc[i])
        if open_side == 0 and want != 0:
            # A change decided today fills at tomorrow's open.
            if i + 1 >= len(dates):
                continue
            open_side = want
            entry_i = i + 1
            entry_slope = float(kf["slope"].iloc[i])
        elif open_side != 0 and want != open_side:
            if i + 1 >= len(dates):
                continue
            trades.append(_close_trade(close, open_, a, b, mode, open_side,
                                       entry_i, i + 1, entry_slope, cost))
            open_side = 0
            entry_i = None
            if want != 0:
                open_side = want
                entry_i = i + 1
                entry_slope = float(kf["slope"].iloc[i])

    if open_side != 0:
        trades.append(_close_trade(close, open_, a, b, mode, open_side,
                                   entry_i, len(dates) - 1, entry_slope, cost))

    rets = [t["ret_net"] for t in trades]
    gross = [t["ret_gross"] for t in trades]
    equity = (1.0 + pd.Series(rets, dtype=float)).cumprod()
    if len(equity):
        equity.index = [t["exit_date"] for t in trades]

    n = len(trades)
    mean_net = float(np.mean(rets)) if n else 0.0
    mean_gross = float(np.mean(gross)) if n else 0.0
    win_rate = float(np.mean([r > 0 for r in rets])) if n else 0.0
    pos_of = {d: i for i, d in enumerate(dates)}
    holds = [pos_of[t["exit_date"]] - pos_of[t["entry_date"]] for t in trades]
    avg_hold = float(np.mean(holds)) if n else 0.0

    cagr = 0.0
    if n:
        span = (pd.Timestamp(trades[-1]["exit_date"])
                - pd.Timestamp(trades[0]["entry_date"])).days
        total = float(equity.iloc[-1])
        if span > 0 and total > 0:
            cagr = total ** (365.25 / span) - 1.0

    max_dd = 0.0
    if n:
        peak = equity.cummax()
        dd = (equity / peak - 1.0).min()
        max_dd = float(-dd)

    return {"trades": trades, "n_trades": n, "mean_net": mean_net,
            "mean_gross": mean_gross, "win_rate": win_rate,
            "avg_hold": avg_hold, "equity": equity, "cagr": cagr,
            "max_drawdown": max_dd}


def _close_trade(close, open_, a, b, mode, side, entry_i, exit_i, slope0, cost):
    ea, eb = close.index[entry_i], close.index[exit_i]
    px_a, px_b = float(open_[a].iloc[entry_i]), float(open_[a].iloc[exit_i])
    py_a, py_b = float(open_[b].iloc[entry_i]), float(open_[b].iloc[exit_i])

    if mode == "spread":
        gross = _spread_ret(side, slope0, px_a, py_a, px_b, py_b)
        # Both legs are charged on entry and on exit.
        net = gross - 4.0 * cost
        rec_side = "long_spread" if side > 0 else "short_spread"
    else:
        # Never short: +1 spread buys y, -1 spread buys x.
        if side > 0:
            gross = py_b / py_a - 1.0
            rec_side = "long_" + b
        else:
            gross = px_b / px_a - 1.0
            rec_side = "long_" + a
        net = gross - 2.0 * cost

    return {"entry_date": ea, "exit_date": eb, "side": rec_side,
            "ret_gross": float(gross), "ret_net": float(net)}


def signal(conn, a, b, params=None):
    """Today's long-only entry signal for the pair, or None.

    Reads the same filter the backtest reads, over the same history, so the
    forward record and the backtest are the same rule. Returns the leg the
    spread calls cheap: e below -entry_z*sd means y (b) is cheap, e above
    +entry_z*sd means x (a) is cheap.
    """
    p = dict(DEFAULT_PARAMS)
    if params:
        p.update(params)
    entry_z = float(p["entry_z"])

    close, _ = load(conn, a, b, WARMUP, date.today().isoformat())
    if close.empty or len(close) < 2:
        return None
    kf = kalman(close[a], close[b], delta=float(p["delta"]),
                ve=float(p["ve"]))
    e = float(kf["e"].iloc[-1])
    sd = float(np.sqrt(kf["q"].iloc[-1]))
    if sd <= 0.0:
        return None
    if e < -entry_z * sd:
        return {"ticker": b, "side": 1, "entry_z": entry_z}
    if e > entry_z * sd:
        return {"ticker": a, "side": 1, "entry_z": entry_z}
    return None


def open_fund(conn):
    """Register the fund if it is not already registered. Idempotent.

    INSERT OR IGNORE rather than a check-then-insert: the name is UNIQUE, so
    a concurrent or repeated call cannot create a second fund, and re-running
    the daily capture never resets a fund that has already accrued a record.
    """
    import uuid
    from datetime import datetime
    today = (conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
             or datetime.utcnow().strftime("%Y-%m-%d"))
    run_id = "kf_" + FUND_LABEL[:8]
    conn.execute(
        "INSERT OR IGNORE INTO paper_runs "
        "(run_id, name, strategy, capital_usd, cash_usd, started_on, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)",
        (run_id, FUND_LABEL,
         json.dumps({"pair": "%s/%s" % FUND_PAIR, "mode": "long_leg",
                     "family": FUND_FAMILY}),
         FUND_CAPITAL, FUND_CAPITAL, today,
         datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S") + "Z"))
    conn.commit()


def step_fund(conn, cfg):
    """Ensure the fund is registered then step it.

    open_fund ensures the fund row exists; paper_trading.step_genome steps
    the fund using its JSON strategy. If step_genome is unavailable (schema
    difference) the call is a no-op: the [5/10] paper step in daily.sh
    steps all open funds anyway, so this is belt-and-suspenders.
    """
    open_fund(conn)
    try:
        import paper_trading
        paper_trading.step_genome(conn, cfg, FUND_LABEL)
    except (AttributeError, TypeError, KeyError):
        pass  # step handled by the [5/10] paper step; registration is enough


def _print_result(label, res):
    print("%-28s n=%4d gross=%+8.4f net=%+8.4f win=%5.1f%% hold=%6.1f "
          "cagr=%+8.2f%% maxdd=%6.2f%%"
          % (label, res["n_trades"], res["mean_gross"], res["mean_net"],
             100.0 * res["win_rate"], res["avg_hold"],
             100.0 * res["cagr"], 100.0 * res["max_drawdown"]))


def main(argv=None):
    from universe import load_config

    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--pair", default="EWA,EWC")
    ap.add_argument("--mode", default="long_leg")
    ap.add_argument("--start", default="2006-07-01")
    ap.add_argument("--end", default="2012-12-31")
    ap.add_argument("--delta", type=float, default=0.0001)
    ap.add_argument("--ve", type=float, default=0.001)
    ap.add_argument("--entry-z", type=float, default=1.0)
    ap.add_argument("--cost-bps", type=float, default=5.0)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--step", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config()
    path = cfg["database"]["market_data_path"]
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    try:
        if args.all:
            today = date.today().isoformat()
            windows = [("2006-07-01", "2012-12-31"), ("2013-01-01", today)]
            for a, b in PAIRS:
                for mode in ("spread", "long_leg"):
                    for ws, we in windows:
                        # The filter needs history to learn the hedge ratio: load from
                        # WARMUP, count only trades signalled inside [ws, we].
                        close, open_ = load(conn, a, b, WARMUP, we)
                        if close.empty:
                            continue
                        params = {"mode": mode, "delta": args.delta,
                                  "ve": args.ve, "entry_z": args.entry_z}
                        res = backtest(close, open_, a, b, params, ws, we,
                                       cost_bps=args.cost_bps)
                        _print_result("%s/%s %s..%s" % (a, b, mode, ws), res)
            return 0

        a, b = [s.strip() for s in args.pair.split(",")]
        close, open_ = load(conn, a, b, WARMUP, args.end)
        if close.empty:
            print("no data for %s/%s" % (a, b))
            return 1
        params = {"mode": args.mode, "delta": args.delta, "ve": args.ve,
                  "entry_z": args.entry_z}
        res = backtest(close, open_, a, b, params, args.start, args.end,
                       cost_bps=args.cost_bps)
        _print_result("%s/%s %s" % (a, b, args.mode), res)
        return 0
    finally:
        conn.close()


def _main_fund(argv=None):
    """--open / --step. These write, so they need a read-write connection;
    the backtest path above opens read-only and must stay that way."""
    from universe import load_config

    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--step", action="store_true")
    args = ap.parse_args(argv)

    cfg = load_config()
    path = cfg["database"]["market_data_path"]
    conn = sqlite3.connect(path)
    try:
        if args.open:
            open_fund(conn)
            return 0
        if args.step:
            step_fund(conn, cfg)
            return 0
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    # --open/--step write to the database and need a read-write connection;
    # every other flag is a read-only backtest. Dispatch before main() opens
    # the read-only handle.
    if any(f in sys.argv[1:] for f in ("--open", "--step")):
        sys.exit(_main_fund())
    sys.exit(main())
