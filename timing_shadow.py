"""
Market-timing dial, SHADOW (Stage AD4 follow-up, owner "go" 2026-10-20). Places nothing; changes no exposure.

The pre-registered one-look test `classifier_timing_dial_v1` PASSED on the walk-forward predictions (2011-2026): the
cross-sectional mean of the XGBoost probability predicted SPY's next-20-session return (corr +0.36, NW t +6.5, same sign
in 94% of folds). That was retrained-per-fold models on history. This module asks the question that decides whether it
is usable: does the LIVE model (models/xgb_uptrend.json, frozen by hash) keep doing it on dates that had not happened
when this was written?

Daily (`--log`, daily.sh [9k5]): the mean probability over today's tradeable universe (same loader and filters as the
paper engine's model fund), its z-score against the live model's own trailing distribution (`--baseline` scores the
previous BASELINE sessions once, for scaling only — in-sample, never evaluated), and the exposure it would suggest:
`full` when z >= 0, `half` when z < 0. Appended to `timing_shadow`.

Pre-registered rule (`market_timing_dial_shadow_v1`): after >= 120 logged sessions whose 20-session outcome exists,
the correlation between z and SPY's next-20-session return (next open to open) must be > 0 with a Newey-West t (lag
20) >= 2; secondary (reported, not deciding): the half/full exposure rule's return against always-full. Until then,
INTERIM. If it passes, the next step is a paper exposure overlay, then the owner's decision — never automatic.

    ./venv/bin/python timing_shadow.py --register     # once
    ./venv/bin/python timing_shadow.py --baseline     # once: the scaling history
    ./venv/bin/python timing_shadow.py --log          # daily
    ./venv/bin/python timing_shadow.py --evaluate     # progress (INTERIM until the sample)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import sqlite3
import sys
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from universe import load_config

EXPERIMENT = "market_timing_dial_shadow_v1"
BASELINE = 120
START = "2026-10-19"     # first feature date that counts: scored after registration (10-20), outcomes all in the future
NEED = 120
H = 20


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS timing_shadow (
        date TEXT PRIMARY KEY, at TEXT NOT NULL, model_hash TEXT NOT NULL, n INTEGER, mean_score REAL, z REAL,
        exposure TEXT, kind TEXT NOT NULL)""")
    conn.commit()


def model_hash(cfg) -> str:
    return hashlib.sha256(open(cfg["model"]["path"], "rb").read()).hexdigest()[:12]


def _model(cfg):
    import xgboost as xgb
    m = xgb.XGBClassifier()
    m.load_model(cfg["model"]["path"])
    want = getattr(m, "feature_names_in_", None)
    if want is None:
        want = m.get_booster().feature_names
    return m, list(want)


def score_frame(df: pd.DataFrame, model, want: list) -> float:
    return float(np.mean(model.predict_proba(df[want])[:, 1])) if len(df) else float("nan")


def today(conn, cfg) -> dict:
    """The live model's mean probability over today's tradeable universe."""
    import storage
    from train_model import FEATURE_COLS
    latest = storage.load_latest_features(conn, FEATURE_COLS, types=cfg["universe"]["tradeable_types"],
                                          max_staleness_days=cfg["scoresheet"].get("max_staleness_days", 5),
                                          min_price=cfg["risk"].get("min_price"),
                                          min_dollar_volume=cfg["risk"].get("min_dollar_volume"))
    if latest.empty:
        return {}
    model, want = _model(cfg)
    day = str(latest["date"].max())[:10]
    latest = latest[latest["date"].astype(str).str[:10] == day]
    return {"date": day, "n": int(len(latest)), "mean_score": score_frame(latest, model, want)}


def baseline(conn, cfg, sessions: int = BASELINE) -> int:
    """Score the previous `sessions` dates once (scaling only; in-sample for the live model, never evaluated)."""
    init(conn)
    from train_model import FEATURE_COLS
    model, want = _model(cfg)
    dates = [r[0] for r in conn.execute("SELECT date FROM prices WHERE ticker='SPY' ORDER BY date DESC LIMIT ?",
                                        (sessions + 1,))][1:]
    cols = ", ".join(f"f.{c}" for c in want)
    mp, mdv = float(cfg["risk"].get("min_price") or 0), float(cfg["risk"].get("min_dollar_volume") or 0)
    types = cfg["universe"]["tradeable_types"]
    tq = ",".join("?" * len(types))
    n = 0
    hsh = model_hash(cfg)
    for d in dates:
        if conn.execute("SELECT 1 FROM timing_shadow WHERE date=?", (d,)).fetchone():
            continue
        df = pd.read_sql(f"SELECT {cols} FROM features f JOIN prices p ON p.ticker=f.ticker AND p.date=f.date "
                         f"JOIN symbols s ON s.ticker=f.ticker WHERE f.date=? AND s.security_type IN ({tq}) "
                         f"AND (s.data_quality IS NULL OR s.data_quality='') "
                         f"AND p.close >= ? AND f.dollar_volume_20 >= ?", conn, params=(d, *types, mp, mdv)).dropna()
        if len(df) < 100:
            continue
        conn.execute("INSERT OR IGNORE INTO timing_shadow VALUES (?,?,?,?,?,?,?,?)",
                     (d, datetime.now(timezone.utc).isoformat(timespec="seconds"), hsh, len(df),
                      score_frame(df, model, want), None, None, "baseline"))
        n += 1
    conn.commit()
    return n


def zscore(conn, day: str, value: float) -> float | None:
    hist = [r[0] for r in conn.execute("SELECT mean_score FROM timing_shadow WHERE date < ? ORDER BY date DESC LIMIT ?",
                                       (day, BASELINE))]
    if len(hist) < 20:
        return None
    sd = float(np.std(hist, ddof=1))
    return (value - float(np.mean(hist))) / sd if sd > 0 else None


def log(conn, cfg) -> dict:
    init(conn)
    t = today(conn, cfg)
    if not t:
        return {}
    z = zscore(conn, t["date"], t["mean_score"])
    exp = None if z is None else ("full" if z >= 0 else "half")
    kind = "prospective" if t["date"] >= START else "baseline"      # a date before START never counts
    conn.execute("INSERT OR IGNORE INTO timing_shadow VALUES (?,?,?,?,?,?,?,?)",
                 (t["date"], datetime.now(timezone.utc).isoformat(timespec="seconds"), model_hash(cfg), t["n"],
                  t["mean_score"], z, exp, kind))
    conn.commit()
    return {**t, "z": z, "exposure": exp}


def nw_t(x, lag: int) -> float:
    import alpha_bench
    return alpha_bench.nw_t(x, lag)


def evaluate(conn) -> dict:
    init(conn)
    d = pd.read_sql("SELECT date, z, exposure FROM timing_shadow WHERE kind='prospective' AND z IS NOT NULL ORDER BY date",
                    conn)
    spy = pd.read_sql("SELECT date, open FROM prices WHERE ticker='SPY' ORDER BY date", conn).set_index("date")["open"]
    pos = {x: i for i, x in enumerate(spy.index)}
    v = spy.to_numpy()
    fwd = []
    for x in d["date"]:
        i = pos.get(x)
        fwd.append(v[i + 1 + H] / v[i + 1] - 1 if i is not None and i + 1 + H < len(v) else np.nan)
    d["fwd"] = fwd
    done = d.dropna(subset=["fwd"])
    out = {"logged": int(len(d)), "with_outcome": int(len(done)), "need": NEED}
    if len(done) >= 10:
        out["corr"] = float(np.corrcoef(done["z"], done["fwd"])[0, 1])
        out["nw_t"] = nw_t((done["z"] * (done["fwd"] - done["fwd"].mean())).to_numpy(), H)
        w = np.where(done["exposure"] == "full", 1.0, 0.5)
        out["rule_vs_full"] = float(np.mean(w * done["fwd"]) - np.mean(done["fwd"]))
    ready = out["with_outcome"] >= NEED
    out["call"] = ("INTERIM" if not ready else
                   "PASS: candidate for a paper exposure overlay" if out.get("corr", 0) > 0 and out.get("nw_t", 0) >= 2
                   else "FAIL")
    return out


def spec() -> dict:
    return {
        "primary_metric": "correlation of the daily z-score of the live model's mean probability with SPY's next-20-session "
                          "return (next open to open); Newey-West t, lag 20",
        "universe": "the paper engine's model-fund universe: tradeable types, min price, min dollar volume (config.yaml)",
        "entry_rule": "z >= 0 -> full exposure, z < 0 -> half (shadow; nothing trades)",
        "exit_rule": "none", "holding_period": "20 sessions",
        "cost_assumptions": "none: a predictive test",
        "evaluation_period": f"feature dates from {START} (scored after registration) until {NEED} have a 20-session outcome",
        "data_version": "models/xgb_uptrend.json frozen by hash at registration; features as stored",
        "stopping_rule": "one evaluation at the fixed sample; a retrained model starts a new experiment",
        "sample_size": f"{NEED} sessions with outcomes", "holdout_policy": "prospective dates only; the baseline is scaling",
        "pass_rule": "corr > 0 and NW t >= 2",
    }


def register(conn, cfg) -> dict:
    import experiment_registry as er
    try:
        return er.get(conn, EXPERIMENT)
    except er.RegistryError:
        er.create(conn, EXPERIMENT,
                  "The live classifier's average probability across the tradeable universe predicts SPY's next-20-session "
                  "return on dates after registration. Fails if the correlation is <= 0 or NW t < 2 at the fixed sample.",
                  "Claude (owner 'go', 2026-10-20)", {**spec(), "model_hash": model_hash(cfg)})
        return er.register(conn, EXPERIMENT)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for f in ("register", "baseline", "log", "evaluate"):
        ap.add_argument(f"--{f}", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    if a.register:
        e = register(conn, cfg)
        print(f"{EXPERIMENT} v{e['version']} {e['status']}")
    conn.row_factory = None
    if a.baseline:
        print(f"baseline sessions scored: {baseline(conn, cfg)}")
    if a.log:
        print(log(conn, cfg))
    if a.evaluate or not (a.register or a.baseline or a.log):
        print(evaluate(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
