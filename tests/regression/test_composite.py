"""Regression test for composite.py. Synthetic data, in-memory sqlite only."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import composite as C  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


def panel(n_tickers=80, n_sessions=400, seed=7):
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2015-01-01", periods=n_sessions).strftime("%Y-%m-%d")
    tickers = ["T%03d" % i for i in range(n_tickers)]
    # Persistent characteristics (as real ones are): a per-ticker level plus small
    # daily noise, so today's value says something about the next 20 sessions.
    bm = rng.normal(size=(n_tickers, 1)) + 0.1 * rng.normal(size=(n_tickers, n_sessions))
    sv = rng.normal(size=(n_tickers, 1)) + 0.1 * rng.normal(size=(n_tickers, n_sessions))
    # close follows a random walk whose next-20-session return is driven by the
    # book_to_market rank positively and short_volume_ratio_20 negatively.
    bm_rank = pd.DataFrame(bm).rank(pct=True).to_numpy() - 0.5
    sv_rank = pd.DataFrame(sv).rank(pct=True).to_numpy() - 0.5
    drift = 0.05 * bm_rank - 0.05 * sv_rank
    noise = rng.normal(scale=0.02, size=(n_tickers, n_sessions))
    logret = (drift + noise) / C.HORIZON
    close = 100.0 * np.exp(np.cumsum(logret, axis=1))
    rows = []
    for i, t in enumerate(tickers):
        for j, d in enumerate(dates):
            rows.append((t, d, close[i, j], bm[i, j], sv[i, j]))
    df = pd.DataFrame(rows, columns=["ticker", "date", "close", "book_to_market",
                                     "short_volume_ratio_20"])
    for name in C.SIGNALS:
        if name not in df.columns:
            df[name] = rng.normal(size=len(df))
    df["ticker"] = df["ticker"].astype("category")
    return df


def main():
    df = panel()
    df = C.add_momentum(df)
    df = C.add_forward(df)
    check("add_momentum produces mom_9_1", "mom_9_1" in df.columns)
    check("add_forward produces fwd_ret", "fwd_ret" in df.columns)
    check("fwd_ret NaN at the end", df.groupby("ticker", observed=True)["fwd_ret"].apply(
        lambda s: s.tail(C.HORIZON).isna().all()).all())

    ranks = C.cross_ranks(df)
    vals = ranks.to_numpy(dtype=float)
    fin = vals[np.isfinite(vals)]
    check("ranks within (-0.5, 0.5]", fin.min() > -0.5 and fin.max() <= 0.5,
          "min=%s max=%s" % (fin.min(), fin.max()))
    df2 = df.copy()
    df2.loc[df2.index[:50], "sue"] = np.nan
    r2 = C.cross_ranks(df2)
    check("NaN preserved in ranks", r2["sue"].isna().sum() >= 50)
    check("missing signal column -> all NaN",
          C.cross_ranks(df.drop(columns=["sue"]))["sue"].isna().all())

    ic = C.daily_ic(df, ranks)
    check("IC of book_to_market positive", ic["book_to_market"].mean() > 0.1,
          "mean=%.4f" % ic["book_to_market"].mean())
    check("IC of short_volume_ratio_20 positive after sign",
          ic["short_volume_ratio_20"].mean() > 0.0,
          "mean=%.4f" % ic["short_volume_ratio_20"].mean())

    w = C.weights(ic)
    check("first rows NaN (too few IC rows)", w.iloc[:C.HORIZON + 1].isna().all().all())
    wf = w.to_numpy(dtype=float)
    rows = wf[np.isfinite(wf).all(axis=1)]
    check("weights non-negative", (rows >= 0).all())
    check("weights sum to 1", np.allclose(rows.sum(axis=1), 1.0, atol=1e-6))

    t = len(ic) - 1
    ic3 = ic.copy()
    ic3.iloc[t - C.HORIZON - 1] = 0.9
    check("the newest closed IC row (t-H-1) is used", not np.allclose(
        w.iloc[t].to_numpy(dtype=float), C.weights(ic3).iloc[t].to_numpy(dtype=float), equal_nan=True))
    ic2 = ic.copy()
    ic2.iloc[t - C.HORIZON:] = 0.0   # positions > t-H-1 are not yet known at t
    w2 = C.weights(ic2)
    check("weights ignore IC not yet closed at t (last horizon rows)",
          np.allclose(w.iloc[t].to_numpy(dtype=float),
                      w2.iloc[t].to_numpy(dtype=float), equal_nan=True))

    sc = C.composite_scores(df, ranks, w)
    check("composite_scores columns", list(sc.columns) == ["ticker", "date", "composite", "n_signals"])
    thin = ranks.copy()
    for c in list(C.SIGNALS)[2:]:
        thin[c] = np.nan
    sc2 = C.composite_scores(df, thin, w)
    check("NaN composite when fewer than MIN_SIGNALS",
          sc2["composite"].isna().all() and (sc2["n_signals"] < C.MIN_SIGNALS).all())

    late = sc[sc["date"] >= sorted(sc["date"].unique())[len(sc["date"].unique()) // 2]].copy()
    late = late.merge(df[["ticker", "date", "fwd_ret"]], on=["ticker", "date"], how="left")
    late = late.dropna(subset=["composite", "fwd_ret"])
    own = late.groupby("date").apply(
        lambda g: g["composite"].rank().corr(g["fwd_ret"].rank()), include_groups=False)
    check("composite IC on later half > 0", own.mean() > 0.0, "mean=%.4f" % own.mean())

    conn = sqlite3.connect(":memory:")
    C.init(conn)
    conn.execute("INSERT INTO daily_composite VALUES ('AAA','2020-01-02',0.25,5)")
    conn.commit()
    frame = pd.DataFrame({"_t": ["AAA", "BBB"], "_d": ["2020-01-02", "2020-01-02"]})
    out = C.attach(conn, frame)
    check("attach round-trip", np.isclose(out["composite"].iloc[0], 0.25) and
          np.isnan(out["composite"].iloc[1]))
    check("attach dtype float32", out["composite"].dtype == np.float32)
    empty = sqlite3.connect(":memory:")
    out2 = C.attach(empty, frame)
    check("attach without table -> all NaN", out2["composite"].isna().all())

    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
