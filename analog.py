"""
The analog forecaster (Stage P, owner 2026-09-26/27): for a stock today, find the
past moments that looked most like it and read what happened next.

    describe   each stock-day as a vector: chart shape (the project's 20 indicators
               plus 20/60/120-session returns and volatility) and fundamentals
               (value, profitability, growth, size) — every one turned into its
               percentile among all stocks THAT day, so 2008 and 2024 compare
               fairly and no single scale dominates
    library    a sample of past stock-days (every STEP sessions, 2006 on) with the
               outcome that followed: the return from the next open to the open
               H sessions later, priced from the unfiltered series (a stock that
               collapsed below the tradeable floor still counts)
    match      for a query day, the K nearest library rows whose outcome was already
               known that day (exit date <= query date: no peeking)
    forecast   of those K: how often the stock rose, the typical move, and the
               worst decile — the spread of what happened, not a single number

Point-in-time throughout: features are the same lagged indicators and fundamentals
every strategy uses (storage.attach_fundamentals), and a library row joins the pool
only once its outcome had happened.

    ./run_bounded.sh ./venv/bin/python analog.py --build            # the library
    ./run_bounded.sh ./venv/bin/python analog.py --forecast AAPL      # today, one stock
    ./run_bounded.sh ./venv/bin/python analog.py --scores [--start 2006-06-01]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("analog")
LIB = Path("data/analog/library.parquet")
SCORES = Path("data/analog/scores.parquet")
H = 20            # sessions ahead the outcome is measured
STEP = 5          # library sampling: every 5th session
K = 200           # neighbours per forecast
SHAPE = ["roc_10", "rsi_14", "bb_pct", "vol_ratio", "adx_14", "stoch_k", "cci_20", "pct_of_52w_high",
         "pct_off_52w_low", "drawdown_200", "price_above_sma200", "log_dollar_volume"]
DERIVED = ["ret_20", "ret_60", "ret_120", "atr_pct"]
FUND = ["book_to_market", "earnings_yield", "gross_profitability", "roa", "asset_growth", "market_cap"]
COLS = SHAPE + DERIVED + FUND


def sessions(conn) -> list:
    return [r[0] for r in conn.execute("SELECT date FROM prices WHERE ticker='SPY' ORDER BY date")]


def _frame(conn, cfg, start: str, end: str) -> pd.DataFrame:
    """Indicators + fundamentals + derived shape for every tradeable stock-day in [start, end]
    (loaded from 200 sessions earlier so the derived returns are defined)."""
    import storage
    from train_model import FEATURE_COLS
    lo = (pd.Timestamp(start) - pd.Timedelta(days=300)).strftime("%Y-%m-%d")
    df = storage.load_training_frame(conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
                                     start_date=lo, end_date=end, min_price=cfg["risk"].get("min_price"),
                                     min_dollar_volume=cfg["risk"].get("min_dollar_volume"), include_liquidity=True)
    if df.empty:
        return df
    df = storage.attach_fundamentals(conn, df).sort_values(["ticker", "date"])
    df["date"] = df["date"].astype(str).str[:10]
    g = df.groupby("ticker", sort=False)["close"]
    for n in (20, 60, 120):
        df[f"ret_{n}"] = (df["close"] / g.shift(n) - 1).astype("float32")
    df["atr_pct"] = (df["atr_14"] / df["close"]).astype("float32")
    return df[df["date"] >= start]


def describe(df: pd.DataFrame) -> pd.DataFrame:
    """Percentile of every feature among all stocks on the same date; unknown -> 0.5 (the
    middle, so a missing fundamental neither attracts nor repels a match)."""
    out = df[["ticker", "date"]].copy()
    for c in COLS:
        if c in df:
            out[c] = df.groupby("date")[c].rank(pct=True).fillna(0.5).astype("float32")
        else:
            out[c] = np.float32(0.5)
    return out


def outcomes(conn, rows: pd.DataFrame, cal: list) -> pd.DataFrame:
    """fwd_ret: next open -> the open H sessions later, unfiltered prices; exit_date too."""
    idx = {d: i for i, d in enumerate(cal)}
    rows = rows.copy()
    pos = rows["date"].map(idx)
    rows["entry_date"] = [cal[int(i) + 1] if pd.notna(i) and int(i) + 1 < len(cal) else None for i in pos]
    rows["exit_date"] = [cal[int(i) + 1 + H] if pd.notna(i) and int(i) + 1 + H < len(cal) else None for i in pos]
    need = sorted(set(rows["entry_date"].dropna()) | set(rows["exit_date"].dropna()))
    px = {}
    for i in range(0, len(need), 200):
        chunk = need[i:i + 200]
        q = pd.read_sql_query('SELECT ticker, date, "open" FROM prices WHERE date IN (%s) AND "open" > 0'
                              % ",".join("?" * len(chunk)), conn, params=chunk)
        px.update({(t, d): o for t, d, o in q.itertuples(index=False)})
    ent = np.array([px.get((t, d)) if d else None for t, d in zip(rows["ticker"], rows["entry_date"])], dtype=float)
    ext = np.array([px.get((t, d)) if d else None for t, d in zip(rows["ticker"], rows["exit_date"])], dtype=float)
    rows["fwd_ret"] = (ext / ent - 1).astype("float32")
    return rows


def build(conn, cfg, start: str = "2006-01-01") -> dict:
    """The library: every STEP-th session from `start`, all tradeable stocks, features + outcome."""
    cal = sessions(conn)
    sample = set(d for i, d in enumerate(cal) if d >= start and i % STEP == 0)
    parts = []
    for y in range(int(start[:4]), int(cal[-1][:4]) + 1):
        df = _frame(conn, cfg, f"{y}-01-01", f"{y}-12-31")
        if df.empty:
            continue
        df = df[df["date"].isin(sample)]
        rows = outcomes(conn, describe(df), cal)
        parts.append(rows)
        log.info(f"library {y}: {len(rows):,} stock-days")
    lib = pd.concat(parts, ignore_index=True)
    LIB.parent.mkdir(parents=True, exist_ok=True)
    lib.to_parquet(LIB, index=False)
    return {"rows": int(len(lib)), "with_outcome": int(lib["fwd_ret"].notna().sum()),
            "from": lib["date"].min(), "to": lib["date"].max()}


def load_library() -> pd.DataFrame:
    return pd.read_parquet(LIB)


def neighbours(lib_x: np.ndarray, q: np.ndarray, k: int = K, chunk: int | None = None) -> tuple:
    """(indices, distances) of the k nearest library rows for each query row (Euclidean).
    Each chunk builds a chunk x library distance matrix plus an int64 partition index, so the
    chunk is sized from the library: about 2e7 cells (~250 MB). A fixed 256 against the full
    1.9M-row library needed several GB and was OOM-killed at the 6 GB cap (09-28, 09-29)."""
    if chunk is None:
        chunk = max(1, min(256, int(2e7 // max(1, lib_x.shape[0]))))
    ln = (lib_x * lib_x).sum(1)
    idx_out, dist_out = [], []
    for i in range(0, len(q), chunk):
        qq = q[i:i + chunk]
        d2 = (qq * qq).sum(1)[:, None] + ln[None, :] - 2.0 * qq @ lib_x.T
        kk = min(k, lib_x.shape[0])
        part = np.argpartition(d2, kk - 1, axis=1)[:, :kk]
        dd = np.take_along_axis(d2, part, 1)
        order = np.argsort(dd, axis=1)
        idx_out.append(np.take_along_axis(part, order, 1))
        dist_out.append(np.sqrt(np.maximum(np.take_along_axis(dd, order, 1), 0)))
    return np.vstack(idx_out), np.vstack(dist_out)


def summarize(outs: np.ndarray) -> dict:
    """What happened next across the matches (NaN outcomes ignored)."""
    o = outs[~np.isnan(outs)]
    if len(o) == 0:
        return {"n": 0, "p_up": None, "mean": None, "median": None, "q10": None, "q90": None}
    return {"n": int(len(o)), "p_up": float((o > 0).mean()), "mean": float(o.mean()),
            "median": float(np.median(o)), "q10": float(np.quantile(o, 0.1)), "q90": float(np.quantile(o, 0.9))}


def forecast(lib: pd.DataFrame, queries: pd.DataFrame, as_of: str, k: int = K) -> pd.DataFrame:
    """For each described query row: the outcome distribution of its k nearest past analogs
    whose outcome was known by `as_of` (their exit date <= as_of)."""
    pool = lib[lib["exit_date"].notna() & (lib["exit_date"] <= as_of) & lib["fwd_ret"].notna()]
    if pool.empty or queries.empty:
        return pd.DataFrame()
    lx = pool[COLS].to_numpy(np.float32)
    qx = queries[COLS].to_numpy(np.float32)
    idx, dist = neighbours(lx, qx, k)
    fr = pool["fwd_ret"].to_numpy(np.float32)
    rows = []
    for j in range(len(queries)):
        s = summarize(fr[idx[j]])
        rows.append({"ticker": queries["ticker"].iat[j], "date": queries["date"].iat[j], **s,
                     "avg_distance": float(dist[j].mean())})
    return pd.DataFrame(rows)


def today(conn, cfg) -> pd.DataFrame:
    """Every tradeable stock described on the newest session."""
    last = conn.execute("SELECT MAX(date) FROM features").fetchone()[0]
    df = _frame(conn, cfg, last, last)
    return describe(df[df["date"] == last]) if not df.empty else df


def scores(conn, cfg, start: str = "2006-06-01", lib_sample: int = 400_000, seed: int = 7) -> dict:
    """analog_p_up / analog_mean / analog_q10 for every library row from `start`, each
    scored only against analogs known at its own date; saved for the daily panel.
    A random `lib_sample` of the library keeps it to minutes; stated, fixed seed."""
    lib = load_library()
    rng = np.random.default_rng(seed)
    pool = lib[lib["fwd_ret"].notna()]
    if len(pool) > lib_sample:
        pool = pool.iloc[np.sort(rng.choice(len(pool), lib_sample, replace=False))]
    out = []
    for d, q in lib[lib["date"] >= start].groupby("date", sort=True):
        f = forecast(pool, q, d)
        if not f.empty:
            out.append(f[["ticker", "date", "p_up", "mean", "q10", "n"]])
    s = pd.concat(out, ignore_index=True).rename(columns={"p_up": "analog_p_up", "mean": "analog_mean",
                                                          "q10": "analog_q10", "n": "analog_n"})
    if SCORES.exists():
        # Incremental: rows from `start` on are replaced; earlier history is kept.
        old = pd.read_parquet(SCORES)
        s = pd.concat([old[old["date"] < start], s], ignore_index=True)
    s.to_parquet(SCORES, index=False)
    return {"rows": int(len(s)), "dates": int(s["date"].nunique()), "from": s["date"].min(), "to": s["date"].max()}


def daily(conn, cfg) -> dict:
    """Score every tradeable stock on the newest session and append to the scores file."""
    q = today(conn, cfg)
    if q.empty or not LIB.exists():
        return {"rows": 0}
    d = q["date"].max()
    f = forecast(load_library(), q, d)
    new = f[["ticker", "date", "p_up", "mean", "q10", "n"]].rename(
        columns={"p_up": "analog_p_up", "mean": "analog_mean", "q10": "analog_q10", "n": "analog_n"})
    if SCORES.exists():
        old = pd.read_parquet(SCORES)
        new = pd.concat([old[old["date"] != d], new], ignore_index=True)
    new.to_parquet(SCORES, index=False)
    return {"date": d, "scored": int(len(f))}


SCORE_COLS = ("analog_p_up", "analog_mean", "analog_q10")


def attach(df: pd.DataFrame, lo: str, hi: str, tickers: list) -> pd.DataFrame:
    """analog_p_up / analog_mean / analog_q10 on a (_t, _d) frame: the newest score at or
    before each date, at most 10 days old (scores are weekly in history, daily forward).
    Point in time: each score used only analogs whose outcome was known at its own date."""
    if not SCORES.exists():
        for c in SCORE_COLS:
            df[c] = np.float32(np.nan)
        return df
    start = (pd.Timestamp(lo) - pd.Timedelta(days=12)).strftime("%Y-%m-%d")
    s = pd.read_parquet(SCORES, columns=["ticker", "date", *SCORE_COLS],
                        filters=[("date", ">=", start), ("date", "<=", hi)])
    s = s[s["ticker"].isin(set(tickers))]
    if s.empty:
        for c in SCORE_COLS:
            df[c] = np.float32(np.nan)
        return df
    s = s.rename(columns={"ticker": "_t"})
    s["_k"] = pd.to_datetime(s["date"])
    for c in SCORE_COLS:
        s[c] = s[c].astype("float32")
    out = df.copy()
    out["_k"] = pd.to_datetime(out["_d"])
    out["_i"] = np.arange(len(out))
    m = pd.merge_asof(out.sort_values("_k"), s.sort_values("_k")[["_t", "_k", *SCORE_COLS]], on="_k", by="_t",
                      direction="backward", tolerance=pd.Timedelta(days=10))
    return m.sort_values("_i").drop(columns=["_k", "_i"]).reset_index(drop=True)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--start", default=None)
    ap.add_argument("--forecast", nargs="*", metavar="TICKER")
    ap.add_argument("--scores", action="store_true")
    ap.add_argument("--daily", action="store_true", help="score the newest session (appends)")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    runtime.be_nice()
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True, timeout=120)
    if a.build:
        print(json.dumps(build(conn, cfg, a.start or "2006-01-01"), default=str))
    if a.scores:
        print(json.dumps(scores(conn, cfg, a.start or "2006-06-01"), default=str))
    if a.daily:
        print(json.dumps(daily(conn, cfg), default=str))
    if a.forecast is not None:
        q = today(conn, cfg)
        if a.forecast:
            q = q[q["ticker"].isin([t.upper() for t in a.forecast])]
        f = forecast(load_library(), q, q["date"].max() if len(q) else "")
        f = f.sort_values("p_up", ascending=False)
        for r in f.head(25).itertuples():
            print(f"  {r.ticker:<6} {r.date}  up in {r.p_up:.0%} of {r.n} matches  median {r.median:+.1%}  "
                  f"typical {r.mean:+.1%}  worst 10% {r.q10:+.1%}  best 10% {r.q90:+.1%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
