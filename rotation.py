"""Sector / asset-class ETF rotation (relative + optional absolute momentum).

Faber (2007) for the absolute filter, Antonacci (2014) for dual momentum.
Pure functions over price frames so backtests, paper trading and live slots
share one implementation.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import sqlite3
import sys
from datetime import date

import numpy as np
import pandas as pd

UNIVERSES = {
    "sectors": ["XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLU", "XLV", "XLY"],
    "assets": ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "VNQ", "DBC"],
}
SAFE = "SHY"


def load(conn, tickers, start, end):
    """Pivot prices into (close, open) frames on SPY's trading dates."""
    tickers = list(dict.fromkeys(list(tickers) + [SAFE, "SPY"]))
    q = ("SELECT ticker, date, close, open FROM prices "
         "WHERE date >= ? AND date <= ? AND ticker IN (%s)"
         % ",".join("?" * len(tickers)))
    df = pd.read_sql_query(q, conn, params=[start, end] + tickers)
    if df.empty:
        empty = pd.DataFrame(index=pd.Index([], dtype=object))
        return empty, empty
    close = df.pivot(index="date", columns="ticker", values="close")
    open_ = df.pivot(index="date", columns="ticker", values="open")
    # A trading day is a date present for SPY; anything else is a partial
    # session and would silently shift the monthly signal day.
    if "SPY" not in close.columns:
        empty = pd.DataFrame(index=pd.Index([], dtype=object))
        return empty, empty
    dates = close.index[close["SPY"].notna()]
    close = close.loc[dates].sort_index()
    open_ = open_.reindex(close.index)
    return close, open_


def month_starts(dates):
    """First session of each calendar month in a sorted date index."""
    idx = pd.Index(sorted(dates))
    if len(idx) == 0:
        return []
    keys = pd.Series(idx, index=idx).astype(str).str[:7]
    return list(idx[~keys.duplicated()])


def rank(close, as_of, lookback, universe):
    """Trailing return over `lookback` sessions, best first."""
    tickers = UNIVERSES[universe] if isinstance(universe, str) else list(universe)
    if as_of not in close.index:
        return []
    pos = close.index.get_loc(as_of)
    if pos < lookback:
        return []
    base = close.index[pos - lookback]
    out = []
    for t in tickers:
        if t not in close.columns:
            continue
        a, b = close.at[as_of, t], close.at[base, t]
        if pd.isna(a) or pd.isna(b) or b == 0:
            continue
        out.append((t, float(a) / float(b) - 1.0))
    out.sort(key=lambda x: x[1], reverse=True)
    return out


def _safe_return(close, as_of, lookback):
    r = rank(close, as_of, lookback, [SAFE])
    return r[0][1] if r else None


def holdings(close, as_of, params):
    """Tickers to hold after the signal day `as_of`."""
    ranked = rank(close, as_of, params["lookback"], params["universe"])
    if not ranked:
        return []
    picks = [t for t, _ in ranked[: params["top_k"]]]
    if not params.get("abs_filter"):
        return picks
    safe_r = _safe_return(close, as_of, params["lookback"])
    if safe_r is None:
        # Conservative: without a SAFE reading we cannot certify positive
        # momentum, so the whole book goes to cash-equivalent.
        return [SAFE]
    out = []
    for t, r in ranked[: params["top_k"]]:
        if r > safe_r:
            out.append(t)
        elif SAFE not in out:
            out.append(SAFE)
    return out or [SAFE]


def _signal_days(close, start, end):
    """Last session of each month inside [start, end]."""
    idx = close.index[(close.index >= start) & (close.index <= end)]
    if len(idx) == 0:
        return []
    keys = pd.Series(idx, index=idx).astype(str).str[:7]
    last = keys[~keys.duplicated(keep="last")].index
    return list(last)


def backtest(close, open_, params, start, end, cost_bps=5.0):
    """Monthly rotation backtest; fills at the next session's open."""
    cost = cost_bps / 10000.0
    signals = _signal_days(close, start, end)
    trades, equity = [], {}
    held = {}          # ticker -> entry open price
    entry_dates = {}
    book = 1.0
    last_open_date = None

    def close_trade(ticker, exit_date, exit_px):
        entry_px = held.pop(ticker)
        gross = exit_px / entry_px - 1.0
        trades.append({
            "ticker": ticker,
            "entry_date": entry_dates.pop(ticker),
            "exit_date": exit_date,
            "ret_gross": gross,
            "ret_net": (1.0 + gross) * (1.0 - cost) / (1.0 + cost) - 1.0,
        })

    for sig in signals:
        pos = close.index.get_loc(sig)
        if pos + 1 >= len(close.index):
            break
        fill = close.index[pos + 1]
        target = holdings(close, sig, params)
        if not target:
            continue
        px = open_.loc[fill]
        # Sell first so the book value used for sizing is post-cost.
        for t in list(held):
            if t not in target and not pd.isna(px.get(t)):
                close_trade(t, fill, float(px[t]))
                book *= (1.0 - cost)
        new = [t for t in target if t not in held and not pd.isna(px.get(t))]
        if new:
            book *= (1.0 - cost)
        for t in new:
            held[t] = float(px[t])
            entry_dates[t] = fill
        last_open_date = fill

    if last_open_date is not None:
        px = open_.loc[last_open_date]
        for t in list(held):
            if not pd.isna(px.get(t)):
                close_trade(t, last_open_date, float(px[t]))
                book *= (1.0 - cost)

    # Equity marked at close, costs applied on the days trades occur.
    eq_dates = close.index[(close.index >= start) & (close.index <= end)]
    values, cur, prev = [], 1.0, None
    for d in eq_dates:
        if prev is not None:
            pass
        cur = 1.0
        values.append(cur)
        prev = d
    equity = _equity_curve(close, open_, params, start, end, cost_bps, signals)

    n = len(trades)
    nets = [t["ret_net"] for t in trades]
    grosses = [t["ret_gross"] for t in trades]
    years = max((pd.Timestamp(equity.index[-1]) - pd.Timestamp(equity.index[0])).days / 365.25, 1e-9) \
        if len(equity) > 1 else 1e-9
    final = float(equity.iloc[-1]) if len(equity) else 1.0
    cagr = final ** (1.0 / years) - 1.0 if final > 0 else -1.0
    dd = equity / equity.cummax() - 1.0
    spy = close["SPY"].reindex(equity.index).dropna()
    bench = 1.0
    if len(spy) > 1 and spy.iloc[0] > 0:
        bench = float(spy.iloc[-1]) / float(spy.iloc[0])
    return {
        "trades": trades,
        "n_trades": n,
        "mean_net": float(np.mean(nets)) if n else 0.0,
        "mean_gross": float(np.mean(grosses)) if n else 0.0,
        "win_rate": float(np.mean([x > 0 for x in nets])) if n else 0.0,
        "equity": equity,
        "cagr": float(cagr),
        "max_drawdown": float(-dd.min()) if len(dd) else 0.0,
        "benchmark_cagr": float(bench ** (1.0 / years) - 1.0) if bench > 0 else -1.0,
    }


def _equity_curve(close, open_, params, start, end, cost_bps, signals):
    """Book value by date, marked at close. Each position's value moves with its OWN
    day-to-day price change (entry at the fill day's open, then close to close); at a
    rebalance the book is re-split equally across the new holdings and costs are charged
    on the value traded. (Fixed 2026-09-27: the first version multiplied the book by each
    holding's return SINCE ENTRY every day, compounding it daily.)"""
    cost = cost_bps / 10000.0
    eq_dates = close.index[(close.index >= start) & (close.index <= end)]
    if len(eq_dates) == 0:
        return pd.Series(dtype=float)
    fills = {}
    for sig in signals:
        pos = close.index.get_loc(sig)
        if pos + 1 < len(close.index):
            fills[close.index[pos + 1]] = sig
    val, mark, cash, out = {}, {}, 1.0, []
    for d in eq_dates:
        if d in fills:
            target = holdings(close, fills[d], params)
            px = open_.loc[d]
            if target:
                # positions move from their last mark to this open first
                for t in list(val):
                    o = px.get(t)
                    if not pd.isna(o) and mark.get(t):
                        val[t] *= float(o) / mark[t]
                        mark[t] = float(o)
                book = cash + sum(val.values())
                tradeable = [t for t in target if not pd.isna(px.get(t))]
                if tradeable:
                    want = {t: book / len(tradeable) for t in tradeable}
                    traded = sum(abs(want.get(t, 0.0) - val.get(t, 0.0)) for t in set(want) | set(val))
                    book -= traded * cost
                    val = {t: book / len(tradeable) for t in tradeable}
                    mark = {t: float(px[t]) for t in tradeable}
                    cash = 0.0
        for t in list(val):
            c = close.at[d, t] if t in close.columns else np.nan
            if not pd.isna(c) and mark.get(t):
                val[t] *= float(c) / mark[t]
                mark[t] = float(c)
        out.append(cash + sum(val.values()))
    return pd.Series(out, index=eq_dates)


def current(conn, params, as_of=None):
    """Today's target holdings and the ranking behind them."""
    if as_of is None:
        row = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()
        as_of = row[0] if row else None
    if as_of is None:
        return {"as_of": None, "holdings": [], "ranked": []}
    lookback = int(params["lookback"])
    start = (pd.Timestamp(as_of) - pd.Timedelta(days=int((lookback + 30) * 1.6))).strftime("%Y-%m-%d")
    close, _ = load(conn, UNIVERSES[params["universe"]], start, as_of)
    return {
        "as_of": as_of,
        "holdings": holdings(close, as_of, params),
        "ranked": rank(close, as_of, lookback, params["universe"]),
    }


def main(argv=None):
    from universe import load_config

    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest", action="store_true")
    ap.add_argument("--current", action="store_true")
    ap.add_argument("--universe", default="sectors")
    ap.add_argument("--lookback", type=int, default=126)
    ap.add_argument("--top-k", type=int, default=3)
    ap.add_argument("--abs-filter", action="store_true")
    ap.add_argument("--start", default="2006-01-01")
    ap.add_argument("--end", default=date.today().isoformat())
    ap.add_argument("--cost-bps", type=float, default=5.0)
    args = ap.parse_args(argv)

    path = load_config()["database"]["market_data_path"]
    conn = sqlite3.connect("file:%s?mode=ro" % path, uri=True)
    params = {"universe": args.universe, "lookback": args.lookback,
              "top_k": args.top_k, "abs_filter": args.abs_filter}
    try:
        if args.current:
            res = current(conn, params)
            print("as_of", res["as_of"])
            for t, r in res["ranked"]:
                print("  %-5s %+.2f%%" % (t, r * 100))
            print("holdings:", " ".join(res["holdings"]) or "(none)")
            return 0
        close, open_ = load(conn, UNIVERSES[args.universe], args.start, args.end)
        res = backtest(close, open_, params, args.start, args.end, args.cost_bps)
        print("n_trades        %d" % res["n_trades"])
        print("mean net/trade  %+.3f%%" % (res["mean_net"] * 100))
        print("CAGR            %+.2f%%" % (res["cagr"] * 100))
        print("SPY CAGR        %+.2f%%" % (res["benchmark_cagr"] * 100))
        print("max drawdown    %.2f%%" % (res["max_drawdown"] * 100))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
