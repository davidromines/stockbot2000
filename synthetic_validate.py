"""
Can the synthetic data be told apart from the real thing? The gate before trust.

This search has found five separate loopholes in its own scoreboard: a price
filter, a monoculture, dead branches, lopsided branches, and a crash-buying
artifact. It is extremely good at discovering the signature of whatever produced
its data. Handing it synthetic prices without this test would be handing it a
sixth: if every synthetic failure has a detectable fingerprint, the search will
learn to *recognise* our simulation rather than to avoid bankruptcy, and it will
score beautifully for doing so.

The test is deliberately stronger than the search is. A gradient-boosted
classifier is given the same 20 indicators a genome can see, and asked to
separate synthetic rows from real ones:

    AUC ~0.50   indistinguishable — the search has nothing to grip
    AUC  0.60+  a signature exists and the search will find it
    AUC  0.70+  the synthetic data is a tell, not a simulation

If a purpose-built classifier with the whole feature set cannot separate them,
an expression tree of a few nodes will not either. Failing this test is not a
reason to tune the threshold; it is a reason to fix the generator.

Usage:
    python synthetic_validate.py --member 0
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import features as feat_mod
import storage
import synthetic_delistings as sd
from train_model import FEATURE_COLS
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("synvalidate")


def run(cfg: dict, member: int = 0, window: tuple[str, str] = ("2010-01-01", "2015-12-31"),
        sample: int = 120000, compare: str = "all") -> dict:
    import xgboost as xgb
    from sklearn.metrics import roc_auc_score

    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)

    log.info("Realising synthetic bars")
    syn = sd.realise(conn, member, window[0], window[1])
    if syn.empty:
        raise SystemExit("No synthetic bars in that window.")

    log.info("Computing indicators on the synthetic series")
    syn = syn.sort_values(["ticker", "date"])
    # Same indicator code the real panel uses, per ticker — anything else would
    # compare two different calculations rather than two different datasets, and
    # the classifier would detect the calculation.
    parts = []
    for _, g in syn.groupby("ticker", observed=True):
        if len(g) < 210:
            continue
        try:
            parts.append(feat_mod.compute_features_for_ticker(g.reset_index(drop=True)))
        except Exception:
            continue
    sfeat = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if sfeat.empty:
        raise SystemExit("No synthetic tickers had enough history for indicators.")
    log.info(f"  {len(sfeat):,} synthetic feature rows from {len(parts):,} tickers")

    # Which real population to compare against decides what the number means.
    #
    #   --vs all       synthetic dying companies against the surviving market.
    #                  A high AUC here is EXPECTED and not by itself damning: a
    #                  company actually heading for delisting also separates from
    #                  survivors, because it really is different.
    #   --vs delisted  synthetic dying companies against the 131 REAL delisted
    #                  paths we hold. This is the realism test. If a classifier
    #                  cannot tell simulated deaths from observed ones, the
    #                  simulation is doing its job.
    #
    # The second is the one that licenses use; the first only says the rows are
    # not interchangeable with healthy ones, which they should not be.
    if compare == "delisted":
        log.info("Loading REAL delisted companies for comparison")
        syms = [r[0] for r in conn.execute(
            "SELECT symbol FROM delistings WHERE asset_type='Stock' AND have_prices=1")]
        real = storage.load_training_frame(
            conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
            start_date="1995-01-01", end_date="2026-12-31", include_liquidity=True)
        real = real[real["ticker"].astype(str).isin(set(syms))]
        log.info(f"  {len(real):,} rows from {real['ticker'].nunique()} real delisted names")
    else:
        log.info("Loading a matched sample of real rows")
        real = storage.load_training_frame(
            conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
            start_date=window[0], end_date=window[1],
            min_price=cfg["risk"].get("min_price"),
            min_dollar_volume=cfg["risk"].get("min_dollar_volume"),
            include_liquidity=True)

    # Compare like with like. The real panel carries the tradeability floors the
    # scanner uses (min_price, min_dollar_volume); the synthetic set must too, or
    # the classifier simply learns "penny stock" and reports a perfect score for
    # detecting a filter rather than a simulation. This also mirrors real use: a
    # dying company drops below $5 and leaves the tradeable universe, exactly as
    # it would have done in life.
    mp = cfg["risk"].get("min_price") or 0
    mv = cfg["risk"].get("min_dollar_volume") or 0
    if "close" in sfeat and mp:
        sfeat = sfeat[sfeat["close"] >= mp]
    if "dollar_volume_20" in sfeat and mv:
        sfeat = sfeat[sfeat["dollar_volume_20"] >= mv]
    log.info(f"  {len(sfeat):,} synthetic rows survive the tradeability floors")
    if sfeat.empty:
        raise SystemExit("No synthetic rows clear the tradeability floors.")

    cols = [c for c in FEATURE_COLS if c in sfeat.columns and c in real.columns]
    a = sfeat[cols].dropna()
    b = real[cols].dropna()
    n = min(len(a), len(b), sample // 2)
    if n < 5000:
        raise SystemExit(f"Too few comparable rows ({n}).")
    rng = np.random.default_rng(0)
    a = a.iloc[rng.choice(len(a), n, replace=False)]
    b = b.iloc[rng.choice(len(b), n, replace=False)]

    X = pd.concat([a, b], ignore_index=True).to_numpy(dtype="float32")
    y = np.r_[np.ones(n), np.zeros(n)]
    idx = rng.permutation(len(y))
    X, y = X[idx], y[idx]
    cut = int(len(y) * 0.7)

    m = xgb.XGBClassifier(n_estimators=220, max_depth=5, learning_rate=0.1,
                          subsample=0.8, colsample_bytree=0.8,
                          eval_metric="auc", n_jobs=int(cfg["compute"]["max_threads"]))
    m.fit(X[:cut], y[:cut])
    auc = float(roc_auc_score(y[cut:], m.predict_proba(X[cut:])[:, 1]))

    imp = sorted(zip(cols, m.feature_importances_), key=lambda t: -t[1])[:6]
    against = "REAL DELISTED COMPANIES" if compare == "delisted" else "THE SURVIVING MARKET"
    print(f"\n  SYNTHETIC vs {against} — {window[0]} to {window[1]}")
    print(f"  {n:,} synthetic rows against {n:,} real rows, {len(cols)} indicators\n")
    print(f"    classifier AUC : {auc:.3f}")
    verdict = ("INDISTINGUISHABLE — safe to use" if auc < 0.60 else
               "SIGNATURE PRESENT — the search will find it" if auc < 0.70 else
               "STRONG TELL — fix the generator before using this")
    print(f"    verdict        : {verdict}\n")
    print("    most discriminating indicators (what gives it away):")
    for c, v in imp:
        print(f"      {c:<22}{v:>7.3f}")
    print("\n  A purpose-built classifier with every feature is a far stronger adversary")
    print("  than an expression tree of a few nodes. If it cannot separate them, the")
    print("  search cannot either.")
    conn.close()
    return {"auc": auc, "n": n}


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--member", type=int, default=0)
    ap.add_argument("--start", default="2010-01-01")
    ap.add_argument("--end", default="2015-12-31")
    ap.add_argument("--vs", default="all", choices=("all", "delisted"),
                    help="'delisted' is the realism test; 'all' only shows that "
                         "dying rows differ from healthy ones, which they should.")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    run(cfg, a.member, (a.start, a.end), compare=a.vs)


if __name__ == "__main__":
    main()
