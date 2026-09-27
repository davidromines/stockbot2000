"""Walk-forward evaluation of the analog forecaster (analog.py, Stage P2).

The question this answers is narrow and falsifiable: does the share of past
analogs that rose predict whether a stock rises, year by year, and does it beat
the XGBoost classifier on the same stock-days? Everything here is measured on
library rows whose own outcome is already known, so the "prediction" for a row
is made only from rows that had exited before that row's date.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/sklearn)

import argparse
import json
import os
import sqlite3
import sys

import numpy as np
import pandas as pd
from sklearn.metrics import roc_auc_score

from analog import forecast
from universe import load_config

OUT_PATH = os.path.join("data", "analog", "eval.json")


def monthly_dates(lib, start="2010-01-01"):
    """First library date of each calendar month from `start` onward."""
    dates = pd.Series(sorted(set(lib["date"].astype(str))))
    dates = dates[dates >= start]
    if dates.empty:
        return []
    keys = dates.str[:7]
    return list(dates.groupby(keys).first())


def _auc(scores, labels):
    """AUC, or None when only one class is present (undefined, not zero)."""
    labels = np.asarray(labels)
    if len(labels) == 0 or len(np.unique(labels)) < 2:
        return None
    return float(roc_auc_score(labels, np.asarray(scores)))


def _summarise(rows):
    if not rows:
        return {"n": 0, "auc": None, "top_decile_ret": None, "all_ret": None,
                "spread": None, "hit_top": None}
    p_up = np.array([r["p_up"] for r in rows], dtype=float)
    fwd = np.array([r["fwd_ret"] for r in rows], dtype=float)
    # Top decile is defined per query date, not pooled: pooling would let a
    # single high-p_up date dominate the selection and inflate the spread.
    top = np.zeros(len(rows), dtype=bool)
    for date in set(r["date"] for r in rows):
        idx = np.array([i for i, r in enumerate(rows) if r["date"] == date])
        if len(idx) == 0:
            continue
        cut = np.quantile(p_up[idx], 0.90)
        sel = idx[p_up[idx] >= cut]
        # Ties at the cut can exceed 10%; keep them rather than break arbitrarily.
        top[sel] = True
    top_ret = float(fwd[top].mean()) if top.any() else None
    all_ret = float(fwd.mean())
    return {
        "n": len(rows),
        "auc": _auc(p_up, (fwd > 0).astype(int)),
        "top_decile_ret": top_ret,
        "all_ret": all_ret,
        "spread": (top_ret - all_ret) if top_ret is not None else None,
        "hit_top": float((fwd[top] > 0).mean()) if top.any() else None,
    }


def evaluate(lib, query_dates, k=200, lib_sample=None, seed=7):
    """Walk-forward: score each query date using only rows known by then."""
    pool = lib
    if lib_sample is not None and lib_sample < len(lib):
        pool = lib.sample(n=lib_sample, random_state=seed).reset_index(drop=True)
    rows = []
    for date in query_dates:
        queries = lib[(lib["date"].astype(str) == str(date)) & lib["fwd_ret"].notna()]
        if queries.empty:
            continue
        fc = forecast(pool, queries, date, k)
        if fc is None or len(fc) == 0:
            continue
        merged = fc.merge(
            queries[["ticker", "date", "fwd_ret"]], on=["ticker", "date"], how="inner"
        )
        for rec in merged.to_dict("records"):
            if not np.isfinite(rec["fwd_ret"]) or not np.isfinite(rec["p_up"]):
                continue
            rows.append({"ticker": rec["ticker"], "date": str(rec["date"]),
                         "p_up": float(rec["p_up"]), "mean": float(rec["mean"]),
                         "fwd_ret": float(rec["fwd_ret"])})
    by_year = {}
    for year in sorted(set(r["date"][:4] for r in rows)):
        by_year[year] = _summarise([r for r in rows if r["date"][:4] == year])
    return {"overall": _summarise(rows), "by_year": by_year, "rows": rows}


def compare_xgb(conn, rows):
    """AUC of analog p_up vs XGBoost score on the stock-days both cover."""
    if not rows:
        return {}
    try:
        xgb = pd.read_sql_query("SELECT ticker, date, score, label FROM oos_predictions", conn)
    except Exception:
        return {}
    if xgb.empty:
        return {}
    df = pd.DataFrame(rows)[["ticker", "date", "p_up", "fwd_ret"]]
    xgb["date"] = xgb["date"].astype(str)
    df["date"] = df["date"].astype(str)
    m = df.merge(xgb, on=["ticker", "date"], how="inner")
    if m.empty:
        return {}
    return {
        "n_matched": int(len(m)),
        "auc_analog": _auc(m["p_up"], m["label"]),
        "auc_xgb": _auc(m["score"], m["label"]),
    }


def _fmt(v, pct=False):
    if v is None:
        return "  n/a"
    return f"{v * 100:+.2f}%" if pct else f"{v:.3f}"


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--k", type=int, default=200)
    ap.add_argument("--sample", type=int, default=400000)
    args = ap.parse_args(argv)

    from analog import load_library
    lib = load_library()
    dates = monthly_dates(lib, start=args.start)
    res = evaluate(lib, dates, k=args.k, lib_sample=args.sample)

    print(f"{'year':<6}{'n':>8}{'auc':>9}{'spread':>11}{'hit_top':>10}")
    for year, s in sorted(res["by_year"].items()):
        print(f"{year:<6}{s['n']:>8}{_fmt(s['auc']):>9}{_fmt(s['spread'], True):>11}"
              f"{_fmt(s['hit_top']):>10}")
    o = res["overall"]
    print(f"{'ALL':<6}{o['n']:>8}{_fmt(o['auc']):>9}{_fmt(o['spread'], True):>11}"
          f"{_fmt(o['hit_top']):>10}")

    cfg = load_config()
    path = cfg["database"]["market_data_path"]
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    try:
        cmp = compare_xgb(conn, res["rows"])
    finally:
        conn.close()
    if cmp:
        print(f"XGBoost: n={cmp['n_matched']} auc_analog={_fmt(cmp['auc_analog'])} "
              f"auc_xgb={_fmt(cmp['auc_xgb'])}")
    else:
        print("XGBoost: no matched rows")

    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w") as fh:
        json.dump({"overall": o, "by_year": res["by_year"], "xgb": cmp}, fh, indent=2)
    return 0


if __name__ == "__main__":
    sys.exit(main())
