"""
Does the model's information survive past its training horizon? Phase 6 section 20.

The classifier was trained to predict one specific horizon. That choice was made
early and never tested, and the spec is direct about it: *do not assume the
original target horizon is optimal.*

This measures the out-of-sample score against forward returns at 1, 2, 5, 10 and
20 days, and reports which of four answers the data supports:

    short-lived    decays fast — information exists but is gone within days
    medium-term    holds to roughly the trained horizon and fades after
    persistent     roughly flat across horizons
    nonexistent    no horizon separates the top decile from the bottom

THE TRAP THIS DELIBERATELY AVOIDS
-----------------------------------
The spec adds: *do not optimize the horizon on the same holdout.* Finding the
best horizon here and then trading it would be selecting on the same data the
measurement came from — the multiple-testing problem in miniature, on a sample
of five. So this module reports the SHAPE across all five horizons and does not
recommend one. If a horizon looks better, that is a hypothesis for a
pre-registered forward test, not a parameter to adopt.

WHAT IS MEASURED
----------------
Top-decile forward return minus bottom-decile forward return, per horizon, on
the 7.6M walk-forward out-of-sample predictions. Decile spread rather than AUC
because AUC answers "does it rank" and this asks "does the ranking pay" — and
the project already knows those are different quantities: 31 of 31 folds rank
above chance while the same model is gross negative under honest fills.

Returns are measured from the NEXT open, matching the fill convention
everywhere else. Measuring from the signal close would inflate every horizon
equally and make the decay curve look flatter than it is.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("decay")

HORIZONS = (1, 2, 5, 10, 20)


def _load_predictions(conn, sample: int | None) -> pd.DataFrame:
    """
    Whole dates, spread evenly across the full prediction window.

    The first version took `ORDER BY date LIMIT n`, which is not a sample: it
    was the first nine months of 2011, reported as "sampled from 7.6M". A
    decay curve from one year says nothing about the other fourteen. Sampling
    whole dates keeps each day's cross-section intact and covers every regime.
    """
    if not sample:
        return pd.read_sql_query(
            "SELECT ticker, date, score FROM oos_predictions", conn)
    dates = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM oos_predictions ORDER BY date")]
    total = conn.execute("SELECT COUNT(*) FROM oos_predictions").fetchone()[0]
    if not dates or total <= sample:
        return pd.read_sql_query(
            "SELECT ticker, date, score FROM oos_predictions", conn)
    step = max(1, round(total / sample))
    keep = dates[::step]
    frames = []
    for i in range(0, len(keep), 500):
        chunk = keep[i:i + 500]
        ph = ",".join("?" * len(chunk))
        frames.append(pd.read_sql_query(
            f"SELECT ticker, date, score FROM oos_predictions WHERE date IN ({ph})",
            conn, params=chunk))
    return pd.concat(frames, ignore_index=True)


def measure(conn, horizons=HORIZONS, sample: int | None = 400_000,
            trained: int | None = None) -> dict:
    """
    Decile spread by horizon.

    Sampled by default: 7.6M predictions joined against forward prices at five
    horizons is a large join, and the decile spread is stable long before the
    full set is consumed. The sample size is reported so nobody reads a
    sampled number as an exhaustive one.
    """
    preds = _load_predictions(conn, sample)
    if preds.empty:
        return {"rows": 0, "horizons": {}, "verdict": "no predictions recorded"}

    tickers = preds["ticker"].unique().tolist()
    lo, hi = preds["date"].min(), preds["date"].max()
    log.info(f"{len(preds):,} predictions, {len(tickers):,} tickers, {lo}..{hi}, "
             f"{preds['date'].nunique():,} dates")

    # Opens, not closes. A signal from a close is actionable at the next open,
    # and measuring from the close would credit the model with a move it could
    # never have captured — at every horizon equally, which is worse here than
    # elsewhere because it flattens the decay curve this module exists to see.
    # Loaded per ticker chunk: fifteen years of opens for every ticker at once
    # does not fit beside the rest of this VM's work.
    parts = []
    for i in range(0, len(tickers), 500):
        chunk = tickers[i:i + 500]
        ph = ",".join("?" * len(chunk))
        px = pd.read_sql_query(
            f"SELECT ticker, date, open FROM prices WHERE ticker IN ({ph}) "
            f"AND date >= ? AND open > 0 ORDER BY ticker, date",
            conn, params=(*chunk, lo))
        g = px.groupby("ticker")["open"]
        # entry = next open (offset 1), exit = open h sessions later
        entry = g.shift(-1)
        for h in horizons:
            px[f"r{h}"] = (g.shift(-(1 + h)) - entry) / entry
        parts.append(preds[preds["ticker"].isin(chunk)].merge(
            px.drop(columns="open"), on=["ticker", "date"], how="inner"))
    fwd_all = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()

    out = {}
    for h in horizons:
        m = fwd_all[["date", "score", f"r{h}"]].rename(columns={f"r{h}": "ret"}) \
            .dropna(subset=["ret"])
        if len(m) < 1000:
            out[h] = {"n": len(m), "spread": None,
                      "note": "too few matched rows to measure"}
            continue
        m["decile"] = pd.qcut(m["score"], 10, labels=False, duplicates="drop")
        top = m[m["decile"] == m["decile"].max()]["ret"]
        bot = m[m["decile"] == m["decile"].min()]["ret"]
        spread = float(top.mean() - bot.mean())
        # Standard error of the difference, so a spread can be read against
        # the noise in it rather than as a point.
        se = float(np.sqrt(top.var(ddof=1) / len(top) + bot.var(ddof=1) / len(bot)))
        # The row-level t treats 2,000 stocks on one day as 2,000 independent
        # draws; they share that day's market and are not. Deciles within each
        # date, one spread per date, and a t across dates is the honest one.
        m["dq"] = m.groupby("date")["score"].transform(
            lambda x: pd.qcut(x.rank(method="first"), 10, labels=False)
            if len(x) >= 20 else np.nan)
        per = m.dropna(subset=["dq"]).groupby("date").apply(
            lambda g: g.loc[g["dq"] == 9, "ret"].mean() - g.loc[g["dq"] == 0, "ret"].mean())
        per = per.dropna()
        t_dates = (float(per.mean() / per.std(ddof=1) * np.sqrt(len(per)))
                   if len(per) > 2 and per.std(ddof=1) > 0 else 0.0)
        out[h] = {"n": int(len(m)), "top_mean": float(top.mean()),
                  "n_dates": int(len(per)), "spread_dates": float(per.mean()) if len(per) else None,
                  "t_dates": t_dates,
                  "bottom_mean": float(bot.mean()), "spread": spread,
                  "se": se, "t": (spread / se) if se > 0 else 0.0,
                  "n_top": int(len(top)), "n_bottom": int(len(bot))}

    return {"rows": len(preds), "sampled": bool(sample), "sample_size": sample,
            "dates": int(preds["date"].nunique()), "window": [lo, hi],
            "horizons": out, "verdict": _verdict(out, trained)}


def _verdict(h: dict, trained: int | None = None) -> str:
    """
    Which answer the shape supports. Sign-aware, on the date-clustered t.

    The first version tested `abs(t)` and then described the result as decay,
    so a top decile that significantly UNDERperformed at two days was reported
    as "decaying after 2 days". A negative spread is not a weak positive one.
    """
    usable = {k: v for k, v in h.items() if v.get("spread") is not None}
    if not usable:
        return "nonexistent — no horizon could be measured"
    t = lambda v: v.get("t_dates", v["t"])  # noqa: E731
    # t=2 is a low bar and is used as a floor rather than a finding.
    pos = sorted(k for k, v in usable.items() if t(v) >= 2.0)
    neg = sorted(k for k, v in usable.items() if t(v) <= -2.0)
    note = ""
    if trained and trained in usable and abs(t(usable[trained])) < 2.0:
        note = f"; nothing at the {trained}-day horizon the model was trained on"
    if not pos and not neg:
        return ("nonexistent — no horizon separates the top decile from the "
                "bottom by more than its own noise" + note)
    if pos and neg:
        return (f"sign-changing — the top decile UNDERperforms at "
                f"{', '.join(f'{k}d' for k in neg)} and outperforms at "
                f"{', '.join(f'{k}d' for k in pos)}" + note)
    if neg:
        return (f"inverted — the top decile underperforms at "
                f"{', '.join(f'{k}d' for k in neg)}" + note)
    if len(pos) == len(usable):
        return "persistent — positive at every horizon measured" + note
    if pos[-1] <= 2:
        return "short-lived — positive only within two sessions" + note
    return (f"medium-term — positive at {', '.join(f'{k}d' for k in pos)}"
            + note)


def render(r: dict) -> str:
    if not r.get("horizons"):
        return f"\n  {r.get('verdict', 'nothing measured')}\n"
    L = ["", "  SIGNAL DECAY BY HORIZON",
         f"  {r['rows']:,} out-of-sample predictions"
         + (f" on {r.get('dates', 0):,} evenly spaced dates" if r.get("sampled") else ""),
         f"  {r['window'][0]} .. {r['window'][1]}",
         "  top-decile minus bottom-decile forward return, from the NEXT open",
         "  " + "-" * 70,
         f"  {'horizon':>8}{'matched':>12}{'top':>10}{'bottom':>10}"
         f"{'spread':>10}{'t':>8}{'t(dates)':>9}"]
    for h, v in sorted(r["horizons"].items()):
        if v.get("spread") is None:
            L.append(f"  {h:>6}d{v['n']:>12,}{'—':>10}{'—':>10}{'—':>10}{'—':>8}")
            continue
        L.append(f"  {h:>6}d{v['n']:>12,}{v['top_mean']:>9.3%}"
                 f"{v['bottom_mean']:>10.3%}{v['spread']:>10.3%}{v['t']:>8.1f}"
                 f"{v.get('t_dates', 0):>9.1f}")
    L += ["  " + "-" * 70,
          "  t = pooled rows (overstated: stocks on one date are not independent)",
          "  t(dates) = one within-date decile spread per date — the one the verdict uses",
          "", f"  VERDICT: {r['verdict']}", "",
          "  No horizon is recommended. Picking the best one here and trading",
          "  it would select on the same data the measurement came from, which",
          "  is the multiple-testing problem on a sample of five. A horizon",
          "  that looks better is a hypothesis for a pre-registered forward",
          "  test, not a parameter to adopt.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=400_000,
                    help="0 for the full 7.6M set")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    trained = int((cfg.get("labeling") or {}).get("horizon_days") or 0) or None
    r = measure(conn, sample=a.sample or None, trained=trained)
    print(render(r))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
