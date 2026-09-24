"""
Is the classifier's AUC worth anything in money? Phase 6 section 19.

The XGBoost model ranks better than chance (AUC ~0.63, 31 of 31 walk-forward
folds) and loses money gross under next-open fills. Those are both true, and
the spec's point is that they answer different questions. This module measures
four of them separately, on the walk-forward OUT-OF-SAMPLE predictions only:

    1. classification skill   does it rank?        AUC
    2. forecast calibration   are its numbers true? Brier, log loss, both against
                                                    the base-rate forecast; a
                                                    reliability table; ECE
    3. economic value         does the ranking pay? forward return by confidence
                                                    bucket, from the NEXT open
    4. trading performance    after costs?          the same buckets net of a
                                                    modeled $20 round trip

Buckets are FIXED probability bands (0-10%, 10-20%, ...), decided here before
any result, never quantiles chosen after looking. Precision by bucket is the hit
rate of the trained label (>= up_threshold_pct within horizon_days) among rows
whose score falls in the band.

What this does NOT do: pick a threshold. A bucket that looks profitable is a
hypothesis for a pre-registered forward test (§12), not a rule to adopt — the
same discipline signal_decay.py applies to horizons.

    python model_calibration.py                 # 400k rows on evenly spaced dates
    python model_calibration.py --sample 0      # all 7.6M (slow, run bounded)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import numpy as np
import pandas as pd

import costs as costs_mod
import storage
from signal_decay import _load_predictions
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("calibration")

EDGES = [i / 10 for i in range(11)]            # fixed bands, set before any result
NOTIONAL = 20.0                                # the account's position size
EPS = 1e-6


def probabilities(score: pd.Series) -> pd.Series:
    """Scores are probabilities; tolerate a 0-100 scale rather than mis-read it."""
    p = score.astype("float64")
    if p.max() > 1.0 + 1e-9:
        p = p / 100.0
    return p.clip(EPS, 1 - EPS)


def skill_and_calibration(p: np.ndarray, y: np.ndarray) -> dict:
    """AUC, Brier, log loss, their base-rate references, ECE and the reliability table."""
    from sklearn.metrics import roc_auc_score
    base = float(y.mean())
    b = np.clip(base, EPS, 1 - EPS)
    brier = float(np.mean((p - y) ** 2))
    brier_ref = float(np.mean((b - y) ** 2))
    ll = float(-np.mean(y * np.log(p) + (1 - y) * np.log(1 - p)))
    ll_ref = float(-np.mean(y * np.log(b) + (1 - y) * np.log(1 - b)))
    band = np.clip(np.digitize(p, EDGES[1:-1]), 0, len(EDGES) - 2)
    table, ece = [], 0.0
    for k in range(len(EDGES) - 1):
        m = band == k
        n = int(m.sum())
        if not n:
            continue
        mp, obs = float(p[m].mean()), float(y[m].mean())
        ece += n / len(p) * abs(mp - obs)
        table.append({"band": f"{EDGES[k]:.0%}-{EDGES[k + 1]:.0%}", "n": n,
                      "mean_predicted": mp, "observed": obs})
    return {"n": int(len(p)), "base_rate": base,
            "auc": float(roc_auc_score(y, p)) if 0 < y.sum() < len(y) else None,
            "brier": brier, "brier_base_rate": brier_ref,
            "brier_skill": (1 - brier / brier_ref) if brier_ref > 0 else None,
            "log_loss": ll, "log_loss_base_rate": ll_ref,
            "ece": float(ece), "reliability": table}


def economic(frame: pd.DataFrame, cost_model) -> dict:
    """Hit rate and forward return, gross and net, per fixed band. Needs p, label, ret, dv."""
    f = frame.dropna(subset=["ret"]).copy()
    f["band"] = np.clip(np.digitize(f["p"], EDGES[1:-1]), 0, len(EDGES) - 2)
    # Cost as a fraction of a $20 position, per row's own liquidity. An
    # unknown liquidity gets the WIDEST spread tier, never zero spread.
    dv = f["dv"].where(f["dv"].notna() & (f["dv"] > 0), 0.0)
    f["cost"] = cost_model.round_trip(pd.Series(NOTIONAL, index=f.index),
                                      dollar_volume=dv.to_numpy()) / NOTIONAL
    f["net"] = f["ret"] - f["cost"]
    rows = []
    for k, g in f.groupby("band"):
        rows.append({"band": f"{EDGES[k]:.0%}-{EDGES[k + 1]:.0%}", "n": int(len(g)),
                     "precision": float(g["label"].mean()),
                     "gross_mean": float(g["ret"].mean()), "cost_mean": float(g["cost"].mean()),
                     "net_mean": float(g["net"].mean()),
                     "net_positive": bool(g["net"].mean() > 0)})
    top = f[f["band"] == f["band"].max()]
    return {"n": int(len(f)), "buckets": rows,
            "all_gross_mean": float(f["ret"].mean()), "all_net_mean": float(f["net"].mean()),
            "top_band": rows[-1]["band"] if rows else None,
            "top_band_net_mean": float(top["net"].mean()) if len(top) else None}


def _forward(conn, preds: pd.DataFrame, horizon: int) -> pd.DataFrame:
    """Next-open to open-`horizon`-sessions-later return, plus 20-day $ volume, per prediction."""
    tickers = preds["ticker"].unique().tolist()
    lo = preds["date"].min()
    parts = []
    for i in range(0, len(tickers), 500):
        chunk = tickers[i:i + 500]
        ph = ",".join("?" * len(chunk))
        px = pd.read_sql_query(f"SELECT ticker, date, open FROM prices WHERE ticker IN ({ph}) "
                               f"AND date >= ? AND open > 0 ORDER BY ticker, date", conn, params=(*chunk, lo))
        g = px.groupby("ticker")["open"]
        entry = g.shift(-1)
        px["ret"] = (g.shift(-(1 + horizon)) - entry) / entry
        dv = pd.read_sql_query(f"SELECT ticker, date, dollar_volume_20 AS dv FROM features "
                               f"WHERE ticker IN ({ph}) AND date >= ?", conn, params=(*chunk, lo))
        sub = preds[preds["ticker"].isin(chunk)]
        parts.append(sub.merge(px.drop(columns="open"), on=["ticker", "date"], how="inner")
                     .merge(dv, on=["ticker", "date"], how="left"))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()


def measure(conn, cfg: dict, sample: int | None = 400_000) -> dict:
    preds = _load_predictions_with_label(conn, sample)
    if preds.empty:
        return {"rows": 0, "verdict": "no out-of-sample predictions recorded"}
    preds["p"] = probabilities(preds["score"])
    horizon = int(cfg["labeling"]["horizon_days"])
    sc = skill_and_calibration(preds["p"].to_numpy(), preds["label"].to_numpy().astype("float64"))
    fwd = _forward(conn, preds, horizon)
    ec = economic(fwd, costs_mod.CostModel(cfg)) if len(fwd) else {"n": 0, "buckets": []}
    return {"rows": int(len(preds)), "dates": int(preds["date"].nunique()), "sampled": bool(sample),
            "window": [preds["date"].min(), preds["date"].max()], "horizon_days": horizon,
            "skill": sc, "economic": ec, "verdict": verdict(sc, ec)}


def _load_predictions_with_label(conn, sample):
    p = _load_predictions(conn, sample)
    if p.empty:
        return p
    lab = []
    dates = sorted(p["date"].unique())
    for i in range(0, len(dates), 500):
        ch = dates[i:i + 500]
        ph = ",".join("?" * len(ch))
        lab.append(pd.read_sql_query(f"SELECT ticker, date, label FROM oos_predictions WHERE date IN ({ph})",
                                     conn, params=ch))
    return p.merge(pd.concat(lab, ignore_index=True), on=["ticker", "date"], how="inner")


def verdict(sc: dict, ec: dict) -> dict:
    """One answer per question. Each is judged on its own evidence, never inferred from another."""
    auc = sc.get("auc")
    ranks = auc is not None and auc > 0.55
    calibrated = sc["ece"] < 0.02 and (sc.get("brier_skill") or 0) > 0
    pays = bool(ec.get("buckets")) and ec["buckets"][-1]["gross_mean"] > ec.get("all_gross_mean", 0)
    net = ec.get("top_band_net_mean")
    return {
        "classification_skill": f"{'YES' if ranks else 'NO'} — AUC {auc:.3f}" if auc is not None else "unmeasured",
        "calibration": (f"{'CALIBRATED' if calibrated else 'MISCALIBRATED'} — ECE {sc['ece']:.3f}, "
                        f"Brier skill {sc.get('brier_skill') or 0:+.3f} vs the base-rate forecast"),
        "economic_value": ("the top band out-earns the average row gross" if pays
                           else "NO — the top band does not out-earn the average row gross"),
        "trading_performance": (f"top band {net:+.3%} per trade net of a modeled ${NOTIONAL:.0f} round trip"
                                if net is not None else "unmeasured"),
    }


def render(r: dict) -> str:
    if not r.get("rows"):
        return f"\n  {r.get('verdict')}\n"
    s, e = r["skill"], r["economic"]
    L = ["", "  MODEL CALIBRATION AND ECONOMIC VALUE (Phase 6 §19)",
         f"  {r['rows']:,} out-of-sample predictions on {r['dates']:,} dates, {r['window'][0]}..{r['window'][1]}"
         + ("  (sampled by whole dates)" if r["sampled"] else ""),
         f"  base rate {s['base_rate']:.2%}   AUC {s['auc']:.3f}" if s.get("auc") is not None else "",
         f"  Brier {s['brier']:.4f} vs base-rate {s['brier_base_rate']:.4f}   "
         f"log loss {s['log_loss']:.4f} vs {s['log_loss_base_rate']:.4f}   ECE {s['ece']:.4f}",
         "", f"  {'band':<9}{'n':>10}{'predicted':>11}{'observed':>10}{'gross':>9}{'cost':>8}{'net':>9}"]
    eb = {b["band"]: b for b in e.get("buckets", [])}
    for t in s["reliability"]:
        b = eb.get(t["band"], {})
        L.append(f"  {t['band']:<9}{t['n']:>10,}{t['mean_predicted']:>11.2%}{t['observed']:>10.2%}"
                 + (f"{b['gross_mean']:>9.3%}{-b['cost_mean']:>8.3%}{b['net_mean']:>9.3%}" if b else ""))
    L += ["", f"  returns: next open -> open {r['horizon_days']} sessions later; cost = modeled $"
              f"{NOTIONAL:.0f} round trip at each row's own liquidity", ""]
    for k, v in r["verdict"].items():
        L.append(f"  {k.replace('_', ' '):<22} {v}")
    L += ["", "  No threshold is recommended: a band that looks good is a hypothesis for",
          "  a pre-registered forward test, not a parameter to adopt.", ""]
    return "\n".join(x for x in L if x is not None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--sample", type=int, default=400_000, help="0 for the full set")
    ap.add_argument("--json", help="also write the result here")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    r = measure(conn, cfg, sample=a.sample or None)
    print(render(r))
    if a.json:
        with open(a.json, "w") as fh:
            json.dump(r, fh, indent=2, default=str)
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
