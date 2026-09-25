"""
Stage M5 — realism graded PER EXIT TYPE, against the right real sample.

The existing gate (universe_validate.py) compares synthetic final years with
the real dead sample — 158 companies, almost all BUYOUTS, because a bankrupt
company's prices vanish from free data. So it grades everything against
buyouts: v4 passed by copying buyouts, and a realistic failure would be
penalised for not looking like one. Here each type meets its own real
counterpart (docs/STAGE_M_RESEARCH.md §5):

    buyout / other   vs the real dead sample (as before), last 252 sessions
                     before delisting
    failure          vs REAL distress episodes HELD OUT of generation: the
                     validation build uses half the donors (parity 1), the test
                     uses the other half (parity 0) — so passing cannot come
                     from copying the paths it is scored on. Both sides are
                     aligned on the same event: 120 sessions ending the day the
                     stock first closes below $2 and below 15% of its 52-week
                     high.
    spac             vs real SPAC common shares in the primary database
                     (blank-check names), their full traded history

Each: cross-validated AUC of a classifier telling real from synthetic on the
same path features as the existing gate. Gate < 0.60, as before.

Plus the literature moments (Shumway, CHS) for failures.

    ./run_bounded.sh ./venv/bin/python validate_v5.py --run
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

import universe_validate as uv

log = logging.getLogger("validate_v5")
VAL_BUILD = Path("data/universe/synthetic_v5_holdout.parquet")
OUT = Path("data/universe/validation_v5.json")
WIN = 120
MAX_AUC = uv.MAX_AUC


def _auc(R: list, S: list, seed: int = 7) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    R, S = pd.DataFrame(R), pd.DataFrame(S)
    if len(R) < 20 or len(S) < 20:
        return {"auc": None, "passes": None, "n_real": len(R), "n_synthetic": len(S), "note": "sample too small"}
    X = pd.concat([R, S], ignore_index=True)[uv.FEATS].fillna(0.0).clip(-50, 50)
    y = np.r_[np.ones(len(R)), np.zeros(len(S))]
    clf = GradientBoostingClassifier(random_state=seed, n_estimators=150, max_depth=3)
    auc = float(np.mean(cross_val_score(clf, X, y, cv=5, scoring="roc_auc")))
    clf.fit(X, y)
    imp = dict(sorted(zip(uv.FEATS, clf.feature_importances_.round(3)), key=lambda kv: -kv[1]))
    med = {f: [round(float(R[f].median()), 4), round(float(S[f].median()), 4)] for f in uv.FEATS}
    return {"auc": round(auc, 3), "passes": auc < MAX_AUC, "n_real": len(R), "n_synthetic": len(S),
            "top_features": dict(list(imp.items())[:4]), "median_real_vs_synth": med}


def one_per_template(syn: pd.DataFrame, seed: int = 7) -> pd.DataFrame:
    """At most one synthetic company per real template. Many synthetic companies copy the same
    real path; left in, cross-validation puts exact twins on both sides of a fold and the
    classifier recognises the twin, not the fake (SPACs: AUC 0.93 from ~77 templates)."""
    firsts = syn.drop_duplicates("company_id")[["company_id", "template"]].dropna()
    keep = firsts.sample(frac=1.0, random_state=seed).drop_duplicates("template")["company_id"]
    return syn[syn["company_id"].isin(set(keep))]


def _distress_window(close: pd.Series) -> pd.Series | None:
    """The WIN sessions ending the first day the path is below $2 and below 15% of its 52-week high."""
    c = close.dropna().reset_index(drop=True) if not isinstance(close.index, pd.Index) else close.dropna()
    hi = c.rolling(252, min_periods=20).max()
    hit = np.where((c.to_numpy() < 2) & (c.to_numpy() < 0.15 * hi.to_numpy()))[0]
    if not len(hit) or hit[0] < WIN:
        return None
    return c.iloc[hit[0] - WIN + 1: hit[0] + 1]


def failures(conn, spy_r, syn: pd.DataFrame) -> dict:
    dd = pd.read_parquet("data/universe/distress_donors.parquet")
    test = dd.iloc[0::2]                               # parity 0 — never used by the validation build
    R = []
    for r in test.itertuples():
        px = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker=? AND date<=? ORDER BY date", conn,
                               params=(r.ticker, r.trigger)).set_index("date")["close"]
        w = px.tail(WIN)
        f = uv.path_features(w, spy_r) if len(w) >= WIN else None
        if f:
            R.append(f)
    S = []
    for cid, g in one_per_template(syn[syn["cohort_id"].str.contains("performance")]).groupby("company_id"):
        w = _distress_window(g[~g["is_delisting_bar"]].set_index("date")["close"])
        f = uv.path_features(w, spy_r) if w is not None else None
        if f:
            S.append(f)
    return _auc(R, S)


def buyouts(conn, spy_r, syn: pd.DataFrame) -> dict:
    import os
    import universe_cohorts as uc
    sample = pd.read_parquet("data/universe/cohort_sample_v1.parquet")
    fconn = sqlite3.connect("file:data/finsaber.db?mode=ro", uri=True) if os.path.exists("data/finsaber.db") else None
    R = []
    for r in sample.itertuples(index=False):
        f = uv.path_features(uc._series(conn, fconn, r.ticker, r.source == "primary", None, 252).iloc[:-1], spy_r)
        if f:
            R.append(f)
    S = []
    ids = syn.loc[syn["is_delisting_bar"] & syn["synthetic_reason"].str.contains("merger|acqui"), "company_id"].unique()
    rng = np.random.default_rng(7)
    for cid in rng.choice(ids, size=min(1500, len(ids)), replace=False):
        g = syn[syn["company_id"] == cid]
        f = uv.path_features(g[~g["is_delisting_bar"]].set_index("date")["close"].tail(252), spy_r)
        if f:
            S.append(f)
    return _auc(R, S)


def spacs(conn, spy_r, syn: pd.DataFrame) -> dict:
    import universe_synthetic_v5 as v5
    # parity 0 only — the validation build copied the parity-1 SPACs
    tick = [t for i, (t,) in enumerate(conn.execute(v5.SPAC_SQL).fetchall()) if i % 2 == 0]
    R = []
    for t in tick:
        px = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker=? ORDER BY date", conn,
                               params=(t,)).set_index("date")["close"].tail(252)
        f = uv.path_features(px, spy_r)
        if f:
            R.append(f)
    S = []
    for cid, g in one_per_template(syn[syn["cohort_id"].str.contains("spac", na=False)]).groupby("company_id"):
        f = uv.path_features(g[~g["is_delisting_bar"]].set_index("date")["close"].tail(252), spy_r)
        if f:
            S.append(f)
    return _auc(R, S)


def moments(syn: pd.DataFrame) -> dict:
    f = syn[syn["cohort_id"].str.contains("performance", na=False)]
    d = f[f["is_delisting_bar"]].drop_duplicates("company_id")
    return {"delisting_return_mean": round(float(d["delisting_return"].mean()), 3),
            "delisting_return_sd": round(float(d["delisting_return"].std()), 3),
            "worthless_share": round(float((d["delisting_return"] <= -0.999).mean()), 3),
            "literature": "Shumway 1997 NYSE/AMEX mean -29.9% sd 48.9% ~11% worthless; Nasdaq -55% effective"}


def run(conn, cfg) -> dict:
    import universe_synthetic_v5 as v5
    if not VAL_BUILD.exists():
        log.info("validation build (parity-1 donors) ...")
        v5.build(conn, cfg, out=VAL_BUILD, donor_parity=1)
    spy_r = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                              ).set_index("date")["close"].pct_change()
    syn = pd.read_parquet(VAL_BUILD, columns=["company_id", "date", "close", "is_delisting_bar", "cohort_id",
                                              "synthetic_reason", "delisting_return", "template"])
    syn["cohort_id"] = syn["cohort_id"].astype(str)
    syn["synthetic_reason"] = syn["synthetic_reason"].astype(str)
    out = {"failures_vs_heldout_real_distress": failures(conn, spy_r, syn),
           "buyouts_vs_real_dead_sample": buyouts(conn, spy_r, syn),
           "spacs_vs_real_spacs": spacs(conn, spy_r, syn),
           "failure_delisting_moments": moments(syn), "max_auc": MAX_AUC}
    OUT.write_text(json.dumps(out, indent=1, default=str))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Per-exit-type realism test for generator v5 (Stage M5).")
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True, timeout=60)
    out = run(conn, cfg) if a.run else json.loads(OUT.read_text())
    for k in ("failures_vs_heldout_real_distress", "buyouts_vs_real_dead_sample", "spacs_vs_real_spacs"):
        v = out[k]
        print(f"  {k:<36} AUC {v.get('auc')}  {'PASS' if v.get('passes') else 'FAIL' if v.get('passes') is False else '—'}"
              f"  (real {v['n_real']}, synthetic {v['n_synthetic']})  top {list((v.get('top_features') or {}).keys())[:3]}")
    print(f"  failure delisting returns: {out['failure_delisting_moments']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
