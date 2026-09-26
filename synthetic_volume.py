"""
Trading volume for the synthetic dead companies (owner, 2026-09-26: "fix the
liquidity rules").

The generator produces prices only, so the survivorship backtest set every
synthetic company's liquidity to the $1M/day floor and its volume indicators to
unknown: liquidity rules could not be tested against dead companies at all, and
the $1M/day floor let every synthetic company through.

A volume model fitted on the REAL dead companies whose volume we hold:
    failures  the 70 distress donors that died (our prices)
    others    the 158 real dead sample v4 copies (FINSABER / our prices; mostly buyouts)

    log10 $vol_t = m_i + b * (log10 p_t - mean_i log10 p) + e_t,   e AR(1)
    m_i          = c0 + c1 * mean_i log10 p + u_i,   u drawn from the real companies' residuals

m_i is the company's typical dollar volume, set by its price level (bigger,
pricier companies trade more) plus company noise; b is how volume moves with
price within a company (a collapsing stock's dollar volume falls with it); the
AR(1) residual carries day-to-day persistence. Parameters per kind (failure /
other), fitted by --fit into synthetic_volume.json; --fit also reports a
held-out check (fit on half the companies, compare the other half).

Deterministic per company (seeded by company_id), so a backtest rerun sees the
same volume.

    ./venv/bin/python synthetic_volume.py --fit
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("synthetic_volume")
PARAMS = Path("data/universe/synthetic_volume.json")
YEARS = 5


def _real(conn, fconn) -> list:
    """(kind, close array, volume array) for every real dead company we hold volume for."""
    dd = pd.read_parquet("data/universe/distress_donors.parquet")
    if "source" not in dd.columns:
        dd["source"] = "primary"
    items = [("failure", t, "primary") for t in dd[dd["died"] & (dd["source"] == "primary")]["ticker"]]
    bs = pd.read_parquet("data/universe/cohort_sample_v1.parquet")
    items += [("other", t, s) for t, s in zip(bs["ticker"], bs["source"])]
    out = []
    for kind, t, src in items:
        if src == "primary" or fconn is None:
            d = pd.read_sql_query("SELECT close, volume FROM prices WHERE ticker=? ORDER BY date", conn, params=(t,))
        else:
            d = pd.read_sql_query("SELECT close, volume FROM finsaber_prices WHERE symbol=? ORDER BY date", fconn,
                                  params=(t,))
        d = d[(d["close"] > 0) & (d["volume"] > 0)].tail(252 * YEARS)
        if len(d) >= 120:
            out.append((kind, t, d["close"].to_numpy(float), d["volume"].to_numpy(float)))
    return out


def _fit(rows: list) -> dict:
    per = []
    for _, _, c, v in rows:
        lp, ldv = np.log10(c), np.log10(c * v)
        per.append((lp.mean(), ldv.mean(), lp - lp.mean(), ldv - ldv.mean()))
    mlp = np.array([p[0] for p in per])
    mld = np.array([p[1] for p in per])
    c1, c0 = np.polyfit(mlp, mld, 1) if len(per) > 2 else (0.0, float(mld.mean()))
    resid = mld - (c0 + c1 * mlp)
    sd_u = float(np.std(resid))
    x = np.concatenate([p[2] for p in per])
    y = np.concatenate([p[3] for p in per])
    b = float(np.dot(x, y) / np.dot(x, x)) if np.dot(x, x) > 0 else 0.0
    phis, innov = [], []
    for p in per:
        e = p[3] - b * p[2]
        if len(e) > 20 and np.std(e) > 0:
            phi = float(np.clip(np.corrcoef(e[:-1], e[1:])[0, 1], 0, 0.99))
            phis.append(phi)
            innov.append(float(np.std(e[1:] - phi * e[:-1])))
    return {"c0": float(c0), "c1": float(c1), "sd_u": sd_u, "u": [round(float(x), 4) for x in resid], "b": b,
            "phi": float(np.median(phis)), "innov": float(np.median(innov)), "companies": len(per)}


def fit(conn, fconn) -> dict:
    rows = _real(conn, fconn)
    params = {k: _fit([r for r in rows if r[0] == k]) for k in ("failure", "other")}
    # Held out: fit on even-indexed companies, simulate the odd ones on their own prices, compare.
    check = {}
    for k in ("failure", "other"):
        rk = [r for r in rows if r[0] == k]
        pr = _fit(rk[0::2])
        real_med, syn_med, real_ok, syn_ok = [], [], [], []
        for _, t, c, v in rk[1::2]:
            sv = volume(c, pr, seed=_seed(t))
            real_med.append(np.median(np.log10(c * v)))
            syn_med.append(np.median(np.log10(c * sv)))
            real_ok.append(float((c * v >= 1e6).mean()))
            syn_ok.append(float((c * sv >= 1e6).mean()))
        check[k] = {"companies": len(real_med),
                    "median_log10_dollar_volume_real": float(np.median(real_med)),
                    "median_log10_dollar_volume_synthetic": float(np.median(syn_med)),
                    "share_days_above_1M_real": float(np.mean(real_ok)),
                    "share_days_above_1M_synthetic": float(np.mean(syn_ok)),
                    "company_level_corr": float(np.corrcoef(real_med, syn_med)[0, 1]) if len(real_med) > 2 else None}
    out = {"params": params, "held_out_check": check, "years": YEARS}
    PARAMS.write_text(json.dumps(out, indent=1))
    return out


def _seed(company_id: str) -> int:
    return int(hashlib.sha256(f"volume:{company_id}".encode()).hexdigest()[:8], 16)


def volume(close: np.ndarray, p: dict, seed: int) -> np.ndarray:
    """Share volume for one company's closes under parameters `p` (deterministic in seed)."""
    rng = np.random.default_rng(seed)
    c = np.maximum(np.asarray(close, float), 1e-4)
    lp = np.log10(c)
    # The company level is drawn from the REAL companies' own residuals (skewed: a few
    # failures trade heavily, most barely), not a normal — the held-out check put a
    # normal draw 3x too liquid for failures.
    u = p.get("u")
    m = p["c0"] + p["c1"] * lp.mean() + (float(rng.choice(u)) if u else rng.normal(0.0, p["sd_u"]))
    e = np.empty(len(c))
    e[0] = rng.normal(0.0, p["innov"] / np.sqrt(max(1 - p["phi"] ** 2, 1e-6)))
    z = rng.normal(0.0, p["innov"], len(c))
    for i in range(1, len(c)):
        e[i] = p["phi"] * e[i - 1] + z[i]
    ldv = m + p["b"] * (lp - lp.mean()) + e
    return (10.0 ** ldv) / c


_CACHE = {}


def params() -> dict | None:
    if "p" not in _CACHE:
        _CACHE["p"] = json.loads(PARAMS.read_text())["params"] if PARAMS.exists() else None
    return _CACHE["p"]


def kind_of(cohort_id: str) -> str:
    return "failure" if "performance" in str(cohort_id) else "other"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fit", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(f"file:{load_config()['database']['market_data_path']}?mode=ro", uri=True)
    fconn = sqlite3.connect("file:data/finsaber.db?mode=ro", uri=True) if os.path.exists("data/finsaber.db") else None
    if a.fit:
        print(json.dumps(fit(conn, fconn), indent=1))
    elif PARAMS.exists():
        print(PARAMS.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
