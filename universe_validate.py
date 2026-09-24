"""
Addendum C (revision 2), Stage 5 — is the synthetic data good enough to use,
and how much does a strategy depend on it?

1. DISCRIMINABILITY (the gate). A classifier is trained to tell a REAL dead
   company's final year from a SYNTHETIC one, on path features only: volatility,
   skew, kurtosis, autocorrelation of returns and of absolute returns, maximum
   drawdown, final-60 return, beta, the share of flat days and of big moves.
   Cross-validated AUC near 0.5 means indistinguishable. The previous generator
   scored 0.978. Until a generator scores below `max_auc` (0.60), synthetic
   rows are for retests and stress bounds only — never discovery or promotion
   (Addendum C question 5). The verdict is written to the report and checked by
   `usable_for_gates()`.
2. DISTRIBUTIONS. Synthetic vs real, per feature: medians and the KS statistic.
3. PROVENANCE. Every synthetic row is tagged; no synthetic row has volume; real
   rows are untouched (the loader's real rows equal the prices table).
4. SENSITIVITY. One price-only strategy (12-1 momentum, monthly, top decile,
   equal weight) re-run in all five loader modes. Price-only on purpose:
   synthetic rows have no volume, so a strategy with a liquidity floor could
   never see them, and inventing volume to let it would be fiction.

    python universe_validate.py --run     writes data/universe/validation_v1.json
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

import universe_cohorts as uc
import universe_loader as ul

log = logging.getLogger("universe_validate")
OUT = "data/universe/validation_v2.json"
MAX_AUC = 0.60
FEATS = ["vol", "skew", "kurt", "ac1", "ac1_abs", "max_dd", "final_60", "beta", "flat_share", "big_share"]


def path_features(close: pd.Series, spy_r: pd.Series) -> dict | None:
    s = close.dropna()
    if len(s) < 120:
        return None
    r = s.pct_change().dropna()
    r = r[np.isfinite(r)]
    if len(r) < 100 or r.std() == 0:
        return None
    j = pd.concat([r, spy_r], axis=1, join="inner").dropna()
    beta = float(np.cov(j.iloc[:, 0], j.iloc[:, 1])[0, 1] / np.var(j.iloc[:, 1])) if len(j) > 60 else np.nan
    eq = s / s.iloc[0]
    return {"vol": float(r.std() * np.sqrt(252)), "skew": float(r.skew()), "kurt": float(r.kurt()),
            "ac1": float(r.autocorr(1)), "ac1_abs": float(r.abs().autocorr(1)),
            "max_dd": float((eq / eq.cummax() - 1).min()),
            "final_60": float(s.iloc[-1] / s.iloc[-61] - 1), "beta": beta,
            "flat_share": float((r.abs() < 1e-6).mean()), "big_share": float((r.abs() > 0.1).mean())}


def discriminability(conn, n_synth: int = 1500, seed: int = 7, reasons: tuple | None = None) -> dict:
    from sklearn.ensemble import GradientBoostingClassifier
    from sklearn.model_selection import cross_val_score
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"].pct_change()
    sample = pd.read_parquet("data/universe/cohort_sample_v1.parquet")
    fconn = sqlite3.connect("file:data/finsaber.db?mode=ro", uri=True) if os.path.exists("data/finsaber.db") else None
    real = []
    for r in sample.itertuples(index=False):
        ser = uc._series(conn, fconn, r.ticker, r.source == "primary", None, 252)
        f = path_features(ser.iloc[:-1], spy)          # exclude the final (delisting) bar, as for synthetic
        if f:
            real.append(f)
    syn = pd.read_parquet(ul.SYNTH, columns=["company_id", "date", "close", "is_delisting_bar", "synthetic_reason"])
    if reasons:
        syn = syn[syn["synthetic_reason"].isin(reasons)]
    dead_ids = syn.loc[syn["is_delisting_bar"], "company_id"].unique()
    rng = np.random.default_rng(seed)
    pick = set(rng.choice(dead_ids, size=min(n_synth, len(dead_ids)), replace=False))
    synth = []
    for cid, g in syn[syn["company_id"].isin(pick)].groupby("company_id"):
        g = g[~g["is_delisting_bar"]].set_index("date")["close"].tail(252)
        f = path_features(g, spy)
        if f:
            synth.append(f)
    R, S = pd.DataFrame(real), pd.DataFrame(synth)
    X = pd.concat([R, S], ignore_index=True)[FEATS].fillna(0.0).clip(-50, 50)
    y = np.r_[np.ones(len(R)), np.zeros(len(S))]
    clf = GradientBoostingClassifier(random_state=seed, n_estimators=150, max_depth=3)
    auc = float(np.mean(cross_val_score(clf, X, y, cv=5, scoring="roc_auc")))
    clf.fit(X, y)
    imp = dict(sorted(zip(FEATS, clf.feature_importances_.round(3)), key=lambda kv: -kv[1]))
    from scipy.stats import ks_2samp
    dist = {f: {"real_median": float(R[f].median()), "synthetic_median": float(S[f].median()),
                "ks": float(ks_2samp(R[f].dropna(), S[f].dropna()).statistic)} for f in FEATS}
    return {"auc": round(auc, 3), "max_auc": MAX_AUC, "passes": auc < MAX_AUC, "n_real": len(R),
            "n_synthetic": len(S), "feature_importance": imp, "distributions": dist,
            "previous_generator_auc": 0.978}


def provenance(conn) -> dict:
    syn = pd.read_parquet(ul.SYNTH, columns=["is_synthetic", "data_source", "cohort_id", "generation_method",
                                              "synthetic_reason", "synthetic_seed", "volume"])
    tags_ok = bool(syn["is_synthetic"].all() and syn["data_source"].notna().all() and syn["cohort_id"].notna().all()
                   and syn["generation_method"].notna().all() and syn["synthetic_reason"].notna().all()
                   and syn["synthetic_seed"].notna().all())
    real = ul.load_backtest_data(conn, "2016-06-01", "2016-06-30", "as_is")
    real = real[~real["is_synthetic"]].sort_values(["ticker", "date"]).head(5000)
    direct = pd.read_sql_query("SELECT ticker, date, close FROM prices WHERE date BETWEEN '2016-06-01' AND "
                               "'2016-06-30'", conn)
    m = real.merge(direct, on=["ticker", "date"], suffixes=("", "_db"))
    return {"every_synthetic_row_tagged": tags_ok, "synthetic_rows_without_volume": bool(syn["volume"].isna().all()),
            "real_rows_untouched": bool(len(m) and np.allclose(m["close"], m["close_db"])),
            "synthetic_rows": int(len(syn))}


def momentum_by_mode(conn, start="2009-01-01", end="2024-12-31") -> dict:
    """12-1 momentum, monthly, top decile, equal weight — price-only, in every mode."""
    out = {}
    for mode in ul.MODES:
        months = []
        for y in range(int(start[:4]) - 1, int(end[:4]) + 1):
            df = ul.load_backtest_data(conn, f"{y}-01-01", f"{y}-12-31", mode)
            df = df[df["close"].notna()]
            df["m"] = df["date"].str[:7]
            last = df.sort_values("date").groupby(["ticker", "m"]).tail(1)[["ticker", "m", "close"]]
            months.append(last)
        px = pd.concat(months).pivot_table(index="m", columns="ticker", values="close", aggfunc="last").sort_index()
        mom = px.shift(1) / px.shift(12) - 1
        ret = px.shift(-1) / px - 1
        # A ticker that disappears next month exits at its last close: use the
        # last available price rather than dropping the loss.
        nxt = px.ffill(limit=1).shift(-1) / px - 1
        ret = ret.fillna(nxt)
        rows = []
        for m in px.index:
            if m < start[:7] or m >= end[:7]:
                continue
            sc = mom.loc[m].dropna()
            sc = sc[px.loc[m, sc.index] > 1.0]
            if len(sc) < 50:
                continue
            top = sc[sc >= sc.quantile(0.9)].index
            # The delisting bar already carries the mode's delisting return (0
            # in `zero`), so a genuinely missing price is filled flat, the same
            # way in every mode.
            rows.append(float(ret.loc[m, top].fillna(0.0).mean()))
        r = np.array(rows)
        out[mode] = {"months": int(len(r)), "cagr": round(float(np.prod(1 + r) ** (12 / len(r)) - 1), 4) if len(r) else None,
                     "mean_monthly": round(float(r.mean()), 4) if len(r) else None}
    return out


def run(conn) -> dict:
    rep = {"built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "discriminability": discriminability(conn), "provenance": provenance(conn),
           # The real sample is mostly clean exits (Stage 2 caveat), so the
           # like-for-like comparison is against synthetic MERGER paths.
           "discriminability_merger_only": {k: v for k, v in discriminability(
               conn, reasons=("merger", "drawn:merger")).items() if k in ("auc", "passes", "n_real", "n_synthetic",
                                                                          "feature_importance")},
           "sensitivity_12_1_momentum": momentum_by_mode(conn)}
    rep["verdict"] = ("synthetic rows MAY be used beyond retests" if rep["discriminability"]["passes"]
                      else "synthetic rows are for retests and stress bounds ONLY (fails the discriminability gate)")
    json.dump(rep, open(OUT, "w"), indent=1, default=str)
    return rep


def usable_for_gates() -> bool:
    """True only if the latest validation passed the discriminability test."""
    try:
        return bool(json.load(open(OUT))["discriminability"]["passes"])
    except (OSError, ValueError, KeyError):
        return False


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Addendum C Stage 5: validation and sensitivity.")
    ap.add_argument("--run", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    if args.run:
        conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
        run(conn)
    rep = json.load(open(OUT))
    d = rep["discriminability"]
    print(f"DISCRIMINABILITY  AUC {d['auc']} (gate < {d['max_auc']}; previous generator {d['previous_generator_auc']})"
          f"  real {d['n_real']}  synthetic {d['n_synthetic']}")
    print("  top features:", list(d["feature_importance"].items())[:4])
    for f, v in d["distributions"].items():
        print(f"  {f:<11} real {v['real_median']:+.4f}  synthetic {v['synthetic_median']:+.4f}  KS {v['ks']:.3f}")
    dm = rep.get("discriminability_merger_only") or {}
    print(f"  merger-only (like for like): AUC {dm.get('auc')}  top {list((dm.get('feature_importance') or {}).items())[:3]}")
    print("PROVENANCE", rep["provenance"])
    print("SENSITIVITY 12-1 momentum, 2009-2024")
    for m, v in rep["sensitivity_12_1_momentum"].items():
        print(f"  {m:<10} CAGR {v['cagr']}  months {v['months']}")
    print("VERDICT:", rep["verdict"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
