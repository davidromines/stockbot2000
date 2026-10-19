"""
Prediction service (Stage AD5, Addendum H Phase D) — research and SHADOW only. No live path imports this module.

Per horizon h in {5, 20, 60} sessions it fits a model of the excess return over SPY (next open to next open, the
alpha bench's target) on the twelve registered signals (alpha_bench.SIGNALS), and keeps the model only if it beats a
simpler one on data it has not seen:

    ladder   0. historical mean (zero excess)  ->  1. ridge on the signals' per-date ranks  ->  2. the existing
             walk-forward XGBoost score, scored on the SAME rows (its probability ranks stocks too)
    fit      discovery 2010-2019; compare on validation 2020-2022; 2023+ untouched
    keep     the simplest rung whose validation IC is not beaten by a more complex one by > 0.005

Each kept model is frozen (`prediction_models`: version = hash of coefficients + window) and used to write dated
forecasts BEFORE outcomes exist (`prediction_log`): expected excess return, P(excess > 0) and the 10th percentile from
the model's own validation residuals, net of the modelled round-trip cost, and an ABSTAIN flag when the expected net
excess is below `abstain_below` or its interval spans zero. Calibration of those forecasts is checked as outcomes
arrive (`--calibration`).

    ./run_bounded.sh ./venv/bin/python predict_service.py --fit --write     # ladder report + freeze the models
    ./venv/bin/python predict_service.py --score                           # today's forecasts into prediction_log
    ./venv/bin/python predict_service.py --calibration                     # forecasts whose horizon has passed
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import alpha_bench as ab
import costs as costs_mod
from universe import load_config

ROOT = Path(__file__).resolve().parent
IDS = [s[0] for s in ab.SIGNALS]
QUANTILES = tuple(np.round(np.linspace(0.05, 0.95, 19), 2))
P_UP_MIN = 0.55                  # abstain unless the model gives at least this chance of beating SPY
ABSTAIN_BELOW = 0.004            # expected net excess per holding period below this: abstain (a switching cost)
MARGIN = 0.005                   # a more complex rung must beat a simpler one's validation IC by this


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS prediction_models (
        version TEXT PRIMARY KEY, horizon INTEGER NOT NULL, rung TEXT NOT NULL, coefs TEXT, resid_q TEXT,
        window TEXT NOT NULL, metrics TEXT NOT NULL, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS prediction_log (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, date TEXT NOT NULL, ticker TEXT NOT NULL,
        horizon INTEGER NOT NULL, model_version TEXT NOT NULL, expected_excess REAL, expected_net REAL, p_up REAL,
        q10 REAL, abstain INTEGER NOT NULL, UNIQUE (date, ticker, horizon, model_version))""")
    conn.commit()


def _ic(pred, y) -> float:
    return ab.spearman(np.asarray(pred, dtype=float), np.asarray(y, dtype=float))


def oos_scores(conn, dates: list) -> dict:
    """{date: Series(ticker -> XGBoost walk-forward score)} for the sample dates (empty where absent)."""
    if not dates:
        return {}
    q = ",".join("?" * len(dates))
    try:
        d = pd.read_sql(f"SELECT ticker, date, score FROM oos_predictions WHERE date IN ({q})", conn, params=dates)
    except Exception:                                          # noqa: BLE001
        return {}
    return {k: g.set_index("ticker")["score"] for k, g in d.groupby("date")}


def ladder(conn, data: dict | None = None) -> dict:
    """Fit and compare the rungs per horizon. Returns {h: {...metrics, coefs, resid_q, keep}}."""
    if data is None:
        data = ab.load(conn, ab.DISCOVERY[0], ab.VALIDATION[1])
    out = {}
    for h in ab.HORIZONS:
        rows = {}
        for w, (a, b) in (("discovery", ab.DISCOVERY), ("validation", ab.VALIDATION)):
            idx = ab.sample_dates(data["dates"], a, b, max(ab.HORIZONS))
            att = ab.attach(conn, [data["dates"][i] for i in idx])
            rows[w] = [(data["dates"][i], cs) for i in idx if (cs := ab.cross_section(data, att, i, h)) is not None]
        if not rows["discovery"] or not rows["validation"]:
            out[h] = {"error": "no data"}
            continue
        X = np.vstack([ab.zmatrix(cs, IDS) for _, cs in rows["discovery"]])
        y = np.concatenate([cs["excess"].to_numpy() for _, cs in rows["discovery"]])
        coef = ab.ridge(X, y)
        resid, ic_r, ic_x, ic_x_dates = [], [], [], 0
        xs = oos_scores(conn, [d for d, _ in rows["validation"]])
        for d, cs in rows["validation"]:
            p = ab.zmatrix(cs, IDS) @ coef
            ic_r.append(_ic(p, cs["excess"]))
            resid.append(cs["excess"].to_numpy() - p)
            if d in xs:
                s = cs.join(xs[d].rename("xgb"), how="inner")
                if len(s) >= ab.MIN_NAMES:
                    ic_x.append(_ic(s["xgb"], s["excess"]))
                    ic_x_dates += 1
        lag = max(1, int(np.ceil(h / ab.STEP)))
        r_all = np.concatenate(resid)
        m_r, m_x = float(np.nanmean(ic_r)), (float(np.nanmean(ic_x)) if ic_x else float("nan"))
        keep = "ridge" if m_r > MARGIN else "mean"            # the mean rung's IC is 0 by construction
        if ic_x and m_x > (m_r if keep == "ridge" else 0) + MARGIN:
            keep = "xgboost (not frozen here: walk-forward model)"
        out[h] = {"ic_ridge": m_r, "ic_ridge_t": ab.nw_t(ic_r, lag), "ic_xgb": m_x, "ic_xgb_t": ab.nw_t(ic_x, lag),
                  "xgb_dates": ic_x_dates, "keep": keep, "coefs": dict(zip(IDS, map(float, coef))),
                  "resid_q": {f"{q:.2f}": float(np.nanquantile(r_all, q)) for q in QUANTILES},
                  "resid": r_all[np.isfinite(r_all)][::50]}
    return out


def freeze(conn, res: dict) -> list:
    """Freeze each kept ridge model; a model is never overwritten (its version is its content hash)."""
    init(conn)
    out = []
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for h, m in res.items():
        if m.get("keep") != "ridge":
            continue
        body = json.dumps({"h": h, "coefs": m["coefs"], "window": [ab.DISCOVERY, ab.VALIDATION]}, sort_keys=True)
        v = f"ridge-h{h}-" + hashlib.sha256(body.encode()).hexdigest()[:10]
        conn.execute("INSERT OR IGNORE INTO prediction_models VALUES (?,?,?,?,?,?,?,?)",
                     (v, h, "ridge", json.dumps(m["coefs"]), json.dumps(m["resid_q"]),
                      json.dumps([ab.DISCOVERY, ab.VALIDATION]),
                      json.dumps({k: m[k] for k in ("ic_ridge", "ic_ridge_t", "ic_xgb", "ic_xgb_t", "xgb_dates")}, default=float),
                      now))
        out.append(v)
    conn.commit()
    return out


def forecast(cs: pd.DataFrame, coefs: dict, resid: np.ndarray) -> pd.DataFrame:
    """Expected excess, P(>0) and the 10th percentile for each name, from the frozen coefficients and the model's own
    validation residuals; expected net = expected excess - modelled round trip; abstain where weak or uncertain."""
    z = ab.zmatrix(cs, IDS)
    mu = z @ np.array([coefs[i] for i in IDS])
    rt = cs["dollar_volume_20"].map(lambda v: float(costs_mod.estimate_spread_pct(float(v))) if v == v else 0.003) \
        + ab.SLIPPAGE_RT
    r = np.sort(resid)
    p_up = np.array([1 - np.searchsorted(r, -m) / len(r) for m in mu]) if len(r) else np.full(len(mu), np.nan)
    q10 = mu + (np.quantile(r, 0.1) if len(r) else np.nan)
    net = mu - rt.to_numpy()
    abstain = (net < ABSTAIN_BELOW) | ~(p_up >= P_UP_MIN)
    return pd.DataFrame({"ticker": cs.index, "expected_excess": mu, "expected_net": net, "p_up": p_up, "q10": q10,
                         "abstain": abstain.astype(int)})


def latest_cross_section(conn, data: dict) -> tuple:
    """The newest date's signals (no outcome needed): (date, DataFrame)."""
    i = len(data["dates"]) - 1
    d = data["dates"][i]
    att = ab.attach(conn, [d]).get(d)
    if att is None:
        return d, None
    C = data["close"]
    df = pd.DataFrame({"close": C.iloc[i]}).join(att, how="left")
    df["mom_12_1"] = C.iloc[i - 21] / C.iloc[i - 252] - 1
    df["mom_9_1"] = C.iloc[i - 21] / C.iloc[i - 189] - 1
    df["rev_1w"] = -(C.iloc[i] / C.iloc[i - 5] - 1)
    lr = np.log(C.iloc[i - 60:i + 1]).diff().iloc[1:]
    df["low_vol_60"] = -lr.std()
    df["neg_asset_growth"] = -df["asset_growth"]
    df["neg_accruals"] = -df["accruals"]
    df["sue_fresh"] = df["sue"].where(df["sue_age"] <= 20)
    df = df[(df["close"] >= 5) & (df["dollar_volume_20"] >= 1e6)]
    return d, df


def score(conn) -> int:
    """Write today's forecasts for every frozen model (shadow). Returns rows written."""
    init(conn)
    models = conn.execute("SELECT version, horizon, coefs, resid_q FROM prediction_models").fetchall()
    if not models:
        return 0
    end = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    start = (pd.Timestamp(end) - pd.Timedelta(days=420)).strftime("%Y-%m-%d")
    data = ab.load(conn, start, end)
    d, cs = latest_cross_section(conn, data)
    if cs is None or not len(cs):
        return 0
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for v, h, coefs, rq in models:
        q = json.loads(rq)                                          # the validation residuals' quantiles
        qs = sorted((float(k), float(x)) for k, x in q.items())
        resid = np.interp(np.linspace(0.05, 0.95, 91), [a for a, _ in qs], [b for _, b in qs])
        f = forecast(cs, json.loads(coefs), resid)
        conn.executemany("INSERT OR IGNORE INTO prediction_log (at, date, ticker, horizon, model_version, expected_excess, "
                         "expected_net, p_up, q10, abstain) VALUES (?,?,?,?,?,?,?,?,?,?)",
                         [(now, d, r.ticker, int(h), v, float(r.expected_excess), float(r.expected_net), float(r.p_up),
                           float(r.q10), int(r.abstain)) for r in f.itertuples()])
        n += len(f)
    conn.commit()
    return n


def render(res: dict, frozen: list) -> str:
    L = [f"# Prediction ladder — {date.today().isoformat()} (Stage AD5)", "",
         f"Target: excess over SPY, next open to next open. Fit {ab.DISCOVERY[0][:4]}-{ab.DISCOVERY[1][:4]}, compared on "
         f"{ab.VALIDATION[0][:4]}-{ab.VALIDATION[1][:4]}; 2023+ untouched. A more complex rung is kept only if it beats the "
         f"simpler one's validation IC by more than {MARGIN}.", "",
         "| h | ridge IC (t) | XGBoost IC on the same rows (t, dates) | kept |", "|---:|---:|---:|---|"]
    for h, m in res.items():
        if "error" in m:
            L.append(f"| {h} | | | {m['error']} |")
            continue
        xi = "n/a" if m["ic_xgb"] != m["ic_xgb"] else f"{m['ic_xgb']:+.4f}"
        xt = "n/a" if m["ic_xgb_t"] != m["ic_xgb_t"] else f"{m['ic_xgb_t']:+.1f}"
        L.append(f"| {h} | {m['ic_ridge']:+.4f} ({m['ic_ridge_t']:+.1f}) | {xi} ({xt}, {m['xgb_dates']}) | {m['keep']} |")
    L += ["", "Frozen models: " + (", ".join(frozen) or "none (no rung beat the historical mean by the margin)"), "",
          "Ridge coefficients (h = 20), on per-date ranks centred at zero:"]
    c20 = (res.get(20) or {}).get("coefs") or {}
    for k, v in sorted(c20.items(), key=lambda x: -abs(x[1])):
        L.append(f"- {k}: {v:+.5f}")
    L += ["", "Forecasts are written daily to `prediction_log` (shadow); nothing trades on them. Calibration is checked "
          "with `--calibration` once horizons pass."]
    return "\n".join(L) + "\n"


def calibration(conn) -> pd.DataFrame:
    """Forecasts whose horizon has passed, by decile of expected excess: mean expected vs realised excess."""
    init(conn)
    p = pd.read_sql("SELECT date, ticker, horizon, expected_excess, p_up FROM prediction_log", conn)
    if p.empty:
        return p
    spy = pd.read_sql("SELECT date, open FROM prices WHERE ticker='SPY' ORDER BY date", conn).set_index("date")["open"]
    pos = {d: i for i, d in enumerate(spy.index)}
    rows = []
    for (d, h), g in p.groupby(["date", "horizon"]):
        i = pos.get(d)
        if i is None or i + 1 + h >= len(spy):
            continue
        d0, d1 = spy.index[i + 1], spy.index[i + 1 + h]
        px = pd.read_sql("SELECT ticker, date, open FROM prices WHERE date IN (?, ?)", conn, params=(d0, d1))
        w = px.pivot(index="ticker", columns="date", values="open")
        if d0 not in w or d1 not in w:
            continue
        ex = (w[d1] / w[d0] - 1) - (spy.iloc[i + 1 + h] / spy.iloc[i + 1] - 1)
        g = g.set_index("ticker").join(ex.rename("realised"), how="inner")
        g["h"] = h
        rows.append(g)
    if not rows:
        return pd.DataFrame()
    a = pd.concat(rows)
    a["decile"] = a.groupby("h")["expected_excess"].transform(
        lambda x: pd.qcut(x.rank(method="first"), min(10, len(x)), labels=False))
    return a.groupby(["h", "decile"]).agg(expected=("expected_excess", "mean"), realised=("realised", "mean"),
                                          p_up=("p_up", "mean"), hit=("realised", lambda x: (x > 0).mean()), n=("realised", "size"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fit", action="store_true")
    ap.add_argument("--score", action="store_true")
    ap.add_argument("--calibration", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    if a.fit:
        res = ladder(conn)
        frozen = freeze(conn, res)
        text = render(res, frozen)
        print(text)
        if a.write:
            p = ROOT / "reports" / f"prediction_ladder_{date.today().isoformat()}.md"
            p.write_text(text)
            print(f"written {p}")
    if a.score:
        print(f"forecasts written: {score(conn)}")
    if a.calibration:
        print(calibration(conn).to_string())
    return 0


if __name__ == "__main__":
    sys.exit(main())
