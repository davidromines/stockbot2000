"""
Addendum C (revision 2), Stage 2 — cohort statistics for companies that died.

For every dead company we hold REAL prices for (primary database or FINSABER),
measure its final year: return, volatility, drawdown from the one-year high,
final-60-session return, beta to SPY and years listed. Group into cohorts and
save the per-cohort distributions as a versioned, hashed artifact that Stage 3
samples from.

COHORTS
-------
Key: reason class x sector division x cap bucket. Reason comes from Layer A
(8-K items only — mostly unknown); sector from SIC via industry.py; cap bucket
from the first market cap on record, else "unknown". A cohort with fewer than
`min_cohort` members is pooled up a documented hierarchy:

    (reason, division, cap)  ->  (reason, division)  ->  (reason)  ->  (all)

and every Stage 3 draw records which level it was sampled at.

THE TRAP THIS FILE MUST NOT FALL INTO
-------------------------------------
The dead companies we hold prices for are the ones that survived the
survivorship filter: a clean acquisition keeps its price history, a bankruptcy
mostly does not (CLAUDE.md: never calibrate the failure case on that sample).
So this artifact records the sample's composition beside every statistic, and
the report states the share of known acquisitions against known failures.
Stage 3 does not take these numbers as the truth about failing companies; it
takes them as the best free evidence, tagged as such.

    python universe_cohorts.py --build     writes data/universe/cohorts_v1.json
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

log = logging.getLogger("universe_cohorts")
OUT = "data/universe/cohorts_v1.json"
DEFAULTS = {"min_cohort": 20, "final_window": 252, "cap_edges": [3e8, 2e9, 1e10]}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **((cfg.get("universe_reconstruction") or {}).get("cohorts") or {})}


def cap_bucket(cap, edges) -> str:
    if cap is None or not np.isfinite(cap) or cap <= 0:
        return "unknown"
    names = ["micro", "small", "mid", "large"]
    for e, n in zip(edges, names):
        if cap < e:
            return n
    return names[len(edges)]


def division(sic) -> str:
    try:
        import industry
        return industry.division_of(int(sic))[0] if sic is not None and not pd.isna(sic) else "unknown"
    except Exception:                                        # noqa: BLE001
        return "unknown"


def _series(conn, fconn, ticker: str, primary: bool, last: str | None, n: int) -> pd.Series:
    if primary:
        df = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker=? AND close>0 ORDER BY date",
                               conn, params=(ticker,))
    else:
        df = pd.read_sql_query("SELECT date, adj_close AS close FROM finsaber_prices WHERE symbol=? AND "
                               "adj_close>0 ORDER BY date", fconn, params=(ticker,))
    s = df.set_index("date")["close"]
    if last:
        s = s[s.index <= last]
    return s.tail(n + 1)


def measure(s: pd.Series, spy: pd.Series) -> dict | None:
    if len(s) < 60:
        return None
    r = s.pct_change().dropna()
    j = pd.concat([r, spy.pct_change()], axis=1, join="inner").dropna()
    beta = float(np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / np.var(j.iloc[:, 1])) if len(j) > 30 else None
    return {"final_year_return": float(s.iloc[-1] / s.iloc[0] - 1),
            "ann_vol": float(r.std() * np.sqrt(252)),
            "drawdown_from_high": float(s.iloc[-1] / s.max() - 1),
            "final_60_return": float(s.iloc[-1] / s.iloc[-61] - 1) if len(s) > 61 else None,
            "beta": beta, "bars": int(len(s))}


def _dist(v) -> dict | None:
    v = np.asarray([x for x in v if x is not None and np.isfinite(x)], dtype=float)
    if not len(v):
        return None
    return {"n": int(len(v)), "mean": float(v.mean()), "std": float(v.std()),
            **{f"p{q}": float(np.percentile(v, q)) for q in (5, 25, 50, 75, 95)}}


def build(conn, cfg: dict, layer_a: pd.DataFrame, finsaber_db: str = "data/finsaber.db") -> dict:
    s = settings(cfg)
    dead = layer_a[layer_a["in_scope"] & layer_a["status"].isin(["delisted", "ended"])
                   & (layer_a["has_primary_prices"] | layer_a["has_finsaber_prices"])].copy()
    fconn = sqlite3.connect(f"file:{finsaber_db}?mode=ro", uri=True) if os.path.exists(finsaber_db) else None
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"]
    # First market cap on record per ticker (bare-column rule: the MIN row).
    caps = {t: c for t, c, _ in conn.execute("SELECT ticker, market_cap, MIN(filed) FROM fundamentals "
                                             "WHERE market_cap>0 GROUP BY ticker").fetchall()}
    rows = []
    for r in dead.itertuples(index=False):
        last = r.delisted_on if isinstance(r.delisted_on, str) else None
        ser = _series(conn, fconn, r.ticker, bool(r.has_primary_prices), last, s["final_window"])
        m = measure(ser, spy)
        if m is None:
            continue
        years = None
        if isinstance(r.first_seen, str) and isinstance(r.last_seen, str):
            years = (pd.Timestamp(r.last_seen) - pd.Timestamp(r.first_seen)).days / 365.25
        rows.append({"company_id": r.company_id, "ticker": r.ticker,
                     "reason": r.delisting_reason if isinstance(r.delisting_reason, str) else "unknown",
                     "division": division(r.sic), "cap": cap_bucket(caps.get(r.ticker), s["cap_edges"]),
                     "years_listed": years, "source": "primary" if r.has_primary_prices else "finsaber", **m})
    if fconn:
        fconn.close()
    sample = pd.DataFrame(rows)
    metrics = ("final_year_return", "ann_vol", "drawdown_from_high", "final_60_return", "beta", "years_listed")

    def stats(g):
        return {"n": int(len(g)), **{m: _dist(g[m].tolist()) for m in metrics}}

    cohorts = {"all": stats(sample)}
    for level, keys in (("reason", ["reason"]), ("reason_division", ["reason", "division"]),
                        ("reason_division_cap", ["reason", "division", "cap"])):
        for k, g in sample.groupby(keys):
            k = k if isinstance(k, tuple) else (k,)
            if len(g) >= s["min_cohort"]:
                cohorts[f"{level}:" + "|".join(map(str, k))] = stats(g)
    comp = sample["reason"].value_counts().to_dict()
    art = {"version": 1, "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "settings": s, "sample_size": int(len(sample)),
           "sample_composition": {"by_reason": comp, "by_source": sample["source"].value_counts().to_dict(),
                                  "by_cap": sample["cap"].value_counts().to_dict()},
           "caveat": ("calibrated on dead companies whose prices SURVIVED; clean exits are over-represented "
                      "and failures under-represented — never read as the truth about failing companies"),
           "pooling": ["reason_division_cap", "reason_division", "reason", "all"],
           "cohorts": cohorts}
    blob = json.dumps(art, sort_keys=True, default=str).encode()
    art["sha256"] = hashlib.sha256(blob).hexdigest()
    return art, sample


def lookup(art: dict, reason: str, div: str, cap: str) -> tuple:
    """(cohort stats, level used) — the most specific cohort that exists."""
    c = art["cohorts"]
    for level, key in (("reason_division_cap", f"{reason}|{div}|{cap}"), ("reason_division", f"{reason}|{div}"),
                       ("reason", reason)):
        if f"{level}:{key}" in c:
            return c[f"{level}:{key}"], level
    return c["all"], "all"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Addendum C Stage 2: cohort statistics.")
    ap.add_argument("--build", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    if args.build:
        la = pd.read_parquet("data/universe/layer_a.parquet")
        conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
        art, sample = build(conn, cfg, la)
        with open(OUT, "w") as f:
            json.dump(art, f, indent=1, default=str)
        sample.to_parquet("data/universe/cohort_sample_v1.parquet", index=False)
    art = json.load(open(OUT))
    print(f"sample {art['sample_size']}  composition {art['sample_composition']}")
    print(f"cohorts: {len(art['cohorts'])}  sha256 {art['sha256'][:16]}")
    a = art["cohorts"]["all"]
    for m in ("final_year_return", "ann_vol", "drawdown_from_high", "final_60_return", "beta", "years_listed"):
        d = a[m]
        if d:
            print(f"  {m:<20} n={d['n']:<4} p5 {d['p5']:+.3f}  p50 {d['p50']:+.3f}  p95 {d['p95']:+.3f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
