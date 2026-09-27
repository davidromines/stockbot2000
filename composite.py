"""Stage S multi-signal composite.

Eight weak signals are combined into one score per stock per day. Weights come
from each signal's recent out-of-sample information coefficient, with a
covariance correction (Kakushadze & Yu 2016) so that signals which repeat each
other do not double-count. Everything is point in time: an IC at date d is only
knowable once the forward return that produced it has closed, so weights at
position t may only use IC rows at positions <= t - horizon - 1.
"""
import runtime  # noqa: F401  (thread limits are read at numpy import time)

import argparse
import logging
import sqlite3
from datetime import date as _date, timedelta

import numpy as np
import pandas as pd

log = logging.getLogger("composite")

SIGNALS = {
    "book_to_market": 1,
    "earnings_yield": 1,
    "fcf_to_price": 1,
    "gross_profitability": 1,
    "mom_9_1": 1,
    "sue": 1,
    "analog_p_up": 1,
    "short_volume_ratio_20": -1,
}
HORIZON = 20
LOOKBACK = 252
MIN_SIGNALS = 3
# A composite needs signals carrying at least this share of the day's weight. A count
# of signals is the wrong test: when only three signals have positive weight and
# one of them is earnings surprise (present ~63 days after a filing), almost no
# stock has all three and the composite goes blank (found on the first build).
MIN_WEIGHT_SHARE = 0.5
RIDGE = 0.5

# An IC needs enough cross-sectional observations to mean anything; below this
# the correlation is noise and is stored as NaN rather than a small number.
MIN_IC_ROWS = 30
# Fewer than this many usable IC rows and the covariance estimate is not
# invertible in any meaningful sense, so the whole weight row is NaN.
MIN_WEIGHT_ROWS = 60

WARMUP_DAYS = 330
FORWARD_PAD_DAYS = 45


def add_momentum(df):
    """mom_9_1: 9-month return skipping the most recent month."""
    df = df.sort_values(["ticker", "date"])
    g = df.groupby("ticker", observed=True)["close"]
    df["mom_9_1"] = g.shift(21) / g.shift(210) - 1.0
    return df


def add_forward(df, horizon=HORIZON):
    df = df.sort_values(["ticker", "date"])
    g = df.groupby("ticker", observed=True)["close"]
    df["fwd_ret"] = g.shift(-horizon) / df["close"] - 1.0
    return df


def cross_ranks(df):
    """Per-date percentile rank of sign*value, centred on zero.

    Ranks lie in (-0.5, 0.5]. Missing values stay missing: a signal that is
    unknown for a stock must not be ranked as if it were average.
    """
    out = pd.DataFrame(index=df.index)
    for name, sign in SIGNALS.items():
        if name not in df.columns:
            out[name] = np.nan
            continue
        v = pd.to_numeric(df[name], errors="coerce") * sign
        out[name] = v.groupby(df["date"], observed=True).rank(pct=True) - 0.5
    return out


def daily_ic(df, ranks):
    """Spearman IC per date between each signal rank and the forward return."""
    order = np.argsort(df["date"].to_numpy(), kind="stable")
    d = df["date"].to_numpy()[order]
    fwd = pd.to_numeric(df["fwd_ret"], errors="coerce").to_numpy(dtype=float)[order]
    cols = list(SIGNALS)
    rk = np.column_stack([ranks[c].to_numpy(dtype=float)[order] for c in cols])
    dates, starts = np.unique(d, return_index=True)
    ends = np.append(starts[1:], len(d))
    data = np.full((len(dates), len(cols)), np.nan)
    for i, (a, b) in enumerate(zip(starts, ends)):
        f = fwd[a:b]
        for j in range(len(cols)):
            r = rk[a:b, j]
            ok = np.isfinite(f) & np.isfinite(r)
            if ok.sum() < MIN_IC_ROWS:
                continue
            rr = pd.Series(r[ok]).rank().to_numpy()
            ff = pd.Series(f[ok]).rank().to_numpy()
            if rr.std() == 0 or ff.std() == 0:
                continue
            data[i, j] = float(np.corrcoef(rr, ff)[0, 1])
    return pd.DataFrame(data, index=pd.Index(dates, name="date"), columns=cols)


def weights(ic, horizon=HORIZON, lookback=LOOKBACK, ridge=RIDGE):
    """Covariance-corrected weights from trailing, already-closed IC rows."""
    cols = list(ic.columns)
    out = np.full(ic.shape, np.nan)
    vals = ic.to_numpy(dtype=float)
    for t in range(len(ic)):
        # An IC at position p is only known once its forward return has closed,
        # i.e. at position p + horizon + 1. So at t we may use p <= t-horizon-1.
        hi = t - horizon - 1
        if hi < 0:
            continue
        lo = max(0, hi - lookback + 1)
        block = vals[lo:hi + 1]
        if np.isfinite(block).any(axis=1).sum() < MIN_WEIGHT_ROWS:
            continue
        mu = np.nanmean(block, axis=0)
        S = pd.DataFrame(block).cov(min_periods=20).to_numpy(dtype=float)
        S = np.where(np.isfinite(S), S, 0.0)
        diag = np.diag(S).copy()
        bad = ~np.isfinite(diag)
        diag[bad] = 1e-4
        np.fill_diagonal(S, diag)
        ok = np.isfinite(mu)
        if not ok.any():
            continue
        idx = np.where(ok)[0]
        A = S[np.ix_(idx, idx)]
        A = A + ridge * np.diag(np.diag(A)) + 1e-8 * np.eye(len(idx))
        try:
            w = np.linalg.solve(A, mu[idx])
        except np.linalg.LinAlgError:
            continue
        w = np.where(np.isfinite(w), w, 0.0)
        w = np.clip(w, 0.0, None)
        tot = w.sum()
        if tot <= 0:
            continue
        row = np.full(len(cols), np.nan)
        row[idx] = w / tot
        out[t] = row
    return pd.DataFrame(out, index=ic.index, columns=cols)


def composite_scores(df, ranks, w):
    """Weighted average of available ranks, renormalised over used signals."""
    cols = list(SIGNALS)
    wv = w.reindex(index=pd.Index(df["date"].to_numpy()), columns=cols).to_numpy(dtype=float)
    rv = np.column_stack([ranks[c].to_numpy(dtype=float) for c in cols])
    use = np.isfinite(rv) & np.isfinite(wv) & (wv > 0)
    nsig = use.sum(axis=1)
    wsum = np.where(use, wv, 0.0).sum(axis=1)
    num = np.where(use, wv * np.nan_to_num(rv), 0.0).sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        comp = np.where(wsum >= MIN_WEIGHT_SHARE, num / wsum, np.nan)
    return pd.DataFrame({"ticker": df["ticker"].to_numpy(), "date": df["date"].to_numpy(),
                         "composite": comp, "n_signals": nsig.astype(int)})


def init(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS daily_composite(
            ticker TEXT, date TEXT, composite REAL, n_signals INTEGER,
            PRIMARY KEY(ticker, date));
        CREATE TABLE IF NOT EXISTS composite_ic(
            date TEXT, signal TEXT, ic REAL, PRIMARY KEY(date, signal));
        CREATE TABLE IF NOT EXISTS composite_weights(
            date TEXT, signal TEXT, weight REAL, PRIMARY KEY(date, signal));
        """
    )
    conn.commit()


def _load(conn, cfg, start, end, feature_cols, forward):
    import storage
    df = storage.load_training_frame(
        conn, feature_cols,
        types=cfg["universe"]["tradeable_types"],
        start_date=start, end_date=end,
        min_price=cfg["risk"]["min_price"],
        min_dollar_volume=cfg["risk"]["min_dollar_volume"],
    )
    if df.empty:
        return df
    df = storage.attach_fundamentals(conn, df)
    # The loader returns Timestamps; every table here keys on ISO date strings.
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    df = add_momentum(df)
    if forward:
        df = add_forward(df)
    return df


def _chunks(start, end, years):
    s = _date.fromisoformat(start)
    e = _date.fromisoformat(end)
    while s <= e:
        try:
            nxt = s.replace(year=s.year + years)
        except ValueError:  # 29 Feb
            nxt = s.replace(year=s.year + years, day=28)
        yield s.isoformat(), min(nxt - timedelta(days=1), e).isoformat()
        s = nxt


def _shift(iso, days):
    return (_date.fromisoformat(iso) + timedelta(days=days)).isoformat()


def _max_date(conn, table, col="date"):
    try:
        r = conn.execute(f"SELECT MAX({col}) FROM {table}").fetchone()
    except sqlite3.OperationalError:
        return None
    return r[0] if r else None


def _store_ic(conn, ic, lo, hi):
    rows = []
    for d, row in ic.iterrows():
        if not (lo <= d <= hi):
            continue
        for s, v in row.items():
            if np.isfinite(v):
                rows.append((d, s, float(v)))
    conn.executemany(
        "INSERT OR REPLACE INTO composite_ic(date, signal, ic) VALUES (?,?,?)", rows)
    return len(rows)


def _read_ic(conn):
    """Stored ICs on the full session calendar (SPY's dates) through the newest price.

    The newest `horizon` sessions have no IC yet (their forward return is still
    open) but still need weights, or today's composite would be blank. Laying the
    ICs on the session calendar keeps weights() counting sessions, not IC rows.
    """
    df = pd.read_sql_query("SELECT date, signal, ic FROM composite_ic", conn)
    if df.empty:
        return pd.DataFrame(columns=list(SIGNALS))
    ic = df.pivot(index="date", columns="signal", values="ic").sort_index()
    cal = [r[0] for r in conn.execute(
        "SELECT date FROM prices WHERE ticker='SPY' AND date >= ? ORDER BY date", (ic.index[0],))]
    if cal:
        ic = ic.reindex(sorted(set(cal) | set(ic.index)))
    return ic.reindex(columns=list(SIGNALS))


def _store_weights(conn, w):
    rows = []
    for d, row in w.iterrows():
        for s, v in row.items():
            if np.isfinite(v):
                rows.append((d, s, float(v)))
    conn.executemany(
        "INSERT OR REPLACE INTO composite_weights(date, signal, weight) VALUES (?,?,?)",
        rows)
    return len(rows)


def _read_weights(conn):
    df = pd.read_sql_query("SELECT date, signal, weight FROM composite_weights", conn)
    if df.empty:
        return pd.DataFrame(columns=list(SIGNALS))
    return df.pivot(index="date", columns="signal", values="weight").sort_index()


def _store_composite(conn, sc, lo, hi):
    rows = []
    for t, d, c, n in sc[["ticker", "date", "composite", "n_signals"]].itertuples(index=False):
        if lo <= d <= hi and np.isfinite(c):
            rows.append((str(t), d, float(c), int(n)))
    conn.executemany(
        "INSERT OR REPLACE INTO daily_composite(ticker, date, composite, n_signals) "
        "VALUES (?,?,?,?)", rows)
    return len(rows)


def build(conn, cfg, start="2008-01-01", end=None, chunk_years=1):
    init(conn)
    if end is None:
        end = _max_date(conn, "prices")
        if end is None:
            return {"ic_dates": 0, "weight_dates": 0, "rows": 0}
    ic_dates = 0
    for lo, hi in _chunks(start, end, chunk_years):
        df = _load(conn, cfg, _shift(lo, -WARMUP_DAYS), _shift(hi, FORWARD_PAD_DAYS),
                   ["roc_10"], forward=True)
        if not df.empty:
            ic = daily_ic(df, cross_ranks(df))
            ic_dates += _store_ic(conn, ic, lo, hi)
        conn.commit()
        log.info("pass1 %s..%s ic_dates=%d", lo, hi, ic_dates)
    w = weights(_read_ic(conn))
    weight_dates = _store_weights(conn, w)
    conn.commit()
    rows = 0
    for lo, hi in _chunks(start, end, chunk_years):
        df = _load(conn, cfg, _shift(lo, -WARMUP_DAYS), hi, ["roc_10"], forward=False)
        if not df.empty:
            sc = composite_scores(df, cross_ranks(df), w)
            rows += _store_composite(conn, sc, lo, hi)
        conn.commit()
        log.info("pass2 %s..%s rows=%d", lo, hi, rows)
    return {"ic_dates": ic_dates, "weight_dates": weight_dates, "rows": rows}


def update(conn, cfg):
    init(conn)
    end = _max_date(conn, "prices")
    if end is None:
        return {"ic_dates": 0, "weight_dates": 0, "rows": 0}
    ic_max = _max_date(conn, "composite_ic")
    lo = _shift(ic_max, -60) if ic_max else "2008-01-01"
    ic_dates = 0
    df = _load(conn, cfg, _shift(lo, -WARMUP_DAYS), _shift(end, FORWARD_PAD_DAYS),
               ["roc_10"], forward=True)
    if not df.empty:
        ic_dates = _store_ic(conn, daily_ic(df, cross_ranks(df)), lo, end)
    conn.commit()
    w = weights(_read_ic(conn))
    weight_dates = _store_weights(conn, w)
    conn.commit()
    comp_max = _max_date(conn, "daily_composite")
    lo2 = _shift(comp_max, -5) if comp_max else lo
    rows = 0
    df = _load(conn, cfg, _shift(lo2, -WARMUP_DAYS), end, ["roc_10"], forward=False)
    if not df.empty:
        rows = _store_composite(conn, composite_scores(df, cross_ranks(df), w), lo2, end)
    conn.commit()
    return {"ic_dates": ic_dates, "weight_dates": weight_dates, "rows": rows}


def attach(conn, df):
    """Left-merge stored composites onto a frame keyed by _t (ticker) / _d (date)."""
    df = df.copy()
    df["composite"] = np.float32(np.nan)
    if df.empty:
        return df
    try:
        conn.execute("SELECT 1 FROM daily_composite LIMIT 1")
    except sqlite3.OperationalError:
        return df
    tickers = sorted({str(t) for t in df["_t"].unique()})
    lo, hi = str(df["_d"].min()), str(df["_d"].max())
    parts = []
    for i in range(0, len(tickers), 900):
        batch = tickers[i:i + 900]
        q = ("SELECT ticker, date, composite FROM daily_composite "
             "WHERE date BETWEEN ? AND ? AND ticker IN (%s)"
             % ",".join("?" * len(batch)))
        parts.append(pd.read_sql_query(q, conn, params=[lo, hi] + batch))
    if not parts:
        return df
    stored = pd.concat(parts, ignore_index=True)
    if stored.empty:
        return df
    stored["composite"] = stored["composite"].astype(np.float32)
    key = pd.DataFrame({"_t": df["_t"].astype(str).to_numpy(),
                        "_d": df["_d"].astype(str).to_numpy()})
    merged = key.merge(stored, how="left", left_on=["_t", "_d"],
                       right_on=["ticker", "date"])
    df["composite"] = merged["composite"].to_numpy(dtype=np.float32)
    return df


def _status(conn):
    ic = _read_ic(conn)
    if ic.empty:
        print("no composite_ic rows")
        return
    tail = ic.tail(LOOKBACK)
    print("IC mean over last %d IC dates:" % len(tail))
    for s in SIGNALS:
        if s in tail.columns:
            print("  %-24s %+.4f" % (s, tail[s].mean()))
    w = _read_weights(conn)
    if not w.empty:
        print("newest weights (%s):" % w.index[-1])
        for s, v in w.iloc[-1].items():
            print("  %-24s %s" % (s, "NaN" if not np.isfinite(v) else "%+.4f" % v))


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Stage S multi-signal composite")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--start", default="2008-01-01")
    a = ap.parse_args(argv)
    import universe
    cfg = universe.load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"])
    try:
        if a.build:
            print(build(conn, cfg, start=a.start))
        if a.update:
            print(update(conn, cfg))
        if a.status or not (a.build or a.update):
            _status(conn)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
