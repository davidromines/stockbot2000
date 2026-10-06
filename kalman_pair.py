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


def _fresh_targets(pos, dates, started_on):
    """What the fund may act on: only runs of the signal that began on or after
    started_on. A run already in progress when the fund opened is state it never
    decided to enter, so it is masked, and so is the filter's warm-up.

    Returns (targets, starts). targets[i] is the side to hold after session i's
    decision (0 when the run predates the fund); starts[i] is True where a run
    the fund may enter began at i.
    """
    targets = np.zeros(len(pos), dtype=int)
    starts = np.zeros(len(pos), dtype=bool)
    live, prev = False, 0
    for i in range(len(pos)):
        cur = int(pos[i])
        begins = cur != 0 and cur != prev
        if cur == 0:
            live = False
        elif begins:
            live = dates[i] >= started_on
        starts[i] = begins and live
        targets[i] = cur if live else 0
        prev = cur
    return targets, starts


def _dollar_volume(conn, ticker, day):
    """20-day dollar volume for the cost tier; 0 (the widest tier) when unknown."""
    try:
        row = conn.execute("SELECT dollar_volume_20 FROM features WHERE ticker=? AND date<=? "
                           "ORDER BY date DESC LIMIT 1", (ticker, day)).fetchone()
    except sqlite3.OperationalError:
        return 0.0
    return float(row[0]) if row and row[0] is not None else 0.0


def step_fund(conn, cfg):
    """Advance the fund by its newest session. Returns a one-line summary, or
    None when there was nothing to step.

    Booked the way paper_trading books a fund, so accounting.py reconciles it:
    one equity mark per session actually stepped (skipped sessions are never
    backfilled), entries cost nothing, an exit's cost comes out of its proceeds.

    The signal decided at the previous close fills at this session's open. The
    fund enters a run only if it began at that previous close and on or after
    started_on: a run in progress when the fund opened is not inherited, and a
    missed entry is not made late. Exits are always honoured. One position of
    position_size_usd at a time. A missing open changes nothing and is retried.
    """
    import costs as costs_mod

    open_fund(conn)
    a, b = FUND_PAIR
    run = conn.execute("SELECT run_id, cash_usd, started_on, last_step_on, status "
                       "FROM paper_runs WHERE name=?", (FUND_LABEL,)).fetchone()
    if run is None or run[4] != "open":
        return None
    run_id, cash, started_on, last_step_on, _ = run

    close, open_ = load(conn, a, b, WARMUP, "9999-12-31")
    if len(close) < 3:
        return None
    dates = [str(d) for d in close.index]
    today = dates[-1]
    if last_step_on is not None and last_step_on >= today:
        return None

    kf = kalman(close[a], close[b], delta=DEFAULT_PARAMS["delta"], ve=DEFAULT_PARAMS["ve"])
    pos = positions(kf, entry_z=DEFAULT_PARAMS["entry_z"])
    targets, starts = _fresh_targets(pos.to_numpy(), dates, started_on)
    want = {1: b, -1: a}.get(int(targets[-2]))

    held = [tuple(r) for r in conn.execute(
        "SELECT ticker, entry_date, entry_price, shares, days_held "
        "FROM paper_positions WHERE run_id=?", (run_id,))]
    leaving = [h for h in held if h[0] != want]
    staying = [h for h in held if h[0] == want]
    entering = want if (want and starts[-2] and not staying) else None

    fills = {}
    for tk in [h[0] for h in leaving] + ([entering] if entering else []):
        px = open_.at[today, tk]
        if not (px == px and px > 0):
            return None
        fills[tk] = float(px)

    cost_model = costs_mod.CostModel(cfg)
    size = float((cfg.get("risk") or {}).get("position_size_usd") or FUND_CAPITAL / 5.0)
    notes = []
    try:
        for tk, entry_date, entry_px, shares, _days in leaving:
            px = fills[tk]
            gross = shares * (px - entry_px)
            cost = float(cost_model.round_trip(shares * entry_px, _dollar_volume(conn, tk, today),
                                               shares))
            conn.execute(
                "INSERT OR REPLACE INTO paper_trades (run_id, ticker, entry_date, exit_date, "
                "entry_price, exit_price, shares, gross_pnl_usd, costs_usd, net_pnl_usd, "
                "pnl_pct, exit_reason) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                (run_id, tk, entry_date, today, entry_px, px, shares, gross, cost, gross - cost,
                 (px / entry_px - 1.0) * 100.0,
                 "e crossed zero" if want is None else "signal changed"))
            conn.execute("DELETE FROM paper_positions WHERE run_id=? AND ticker=?", (run_id, tk))
            cash += shares * px - cost
            notes.append("EXIT %s %+.2f net" % (tk, gross - cost))
        if entering:
            if cash + 1e-9 >= size:
                px = fills[entering]
                conn.execute(
                    "INSERT INTO paper_positions (run_id, ticker, entry_date, entry_price, "
                    "shares, stop_price, days_held) VALUES (?,?,?,?,?,?,0)",
                    (run_id, entering, today, px, size / px, None))
                cash -= size
                notes.append("ENTER %s @ %.2f" % (entering, px))
            else:
                notes.append("no cash to enter %s" % entering)

        index = {d: i for i, d in enumerate(dates)}
        marks, n_open = 0.0, 0
        for tk, entry_date, _px, shares, days in conn.execute(
                "SELECT ticker, entry_date, entry_price, shares, days_held "
                "FROM paper_positions WHERE run_id=?", (run_id,)).fetchall():
            days = len(dates) - 1 - index[entry_date] if entry_date in index else days + 1
            conn.execute("UPDATE paper_positions SET days_held=? WHERE run_id=? AND ticker=?",
                         (days, run_id, tk))
            marks += shares * float(close.at[today, tk])
            n_open += 1
            if tk != entering:
                notes.append("hold %s" % tk)
        equity = cash + marks
        conn.execute("INSERT OR REPLACE INTO paper_equity (run_id, date, cash_usd, positions_usd, "
                     "equity_usd, open_positions) VALUES (?,?,?,?,?,?)",
                     (run_id, today, cash, marks, equity, n_open))
        conn.execute("UPDATE paper_runs SET cash_usd=?, last_step_on=? WHERE run_id=?",
                     (cash, today, run_id))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return "kalman fund %s: %s | equity $%.2f" % (today, ", ".join(notes) or "flat", equity)


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

    import storage

    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    try:
        if args.open:
            open_fund(conn)
            return 0
        if args.step:
            print(step_fund(conn, cfg) or "kalman fund: nothing to step")
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
