"""
Alpha Research and Validation bench (Stage AD4, Addendum H Phases B-C). Read-only on market data; writes only its own
registry tables (`alpha_signals`, `alpha_trials`) and a report. Changes no live rule.

**Unit of research = one signal, not a strategy.** The first set is twelve published signals in seven families, each with
its published direction, computed point in time from our data:

    momentum     mom_12_1, mom_9_1            price 1 month ago / 12 (9) months ago - 1            (+)
    value        fcf_to_price, earnings_yield, book_to_market                                    (+)
    quality      gross_profitability                                                             (+)
    earnings     sue, sue_fresh (SUE only while <= 20 sessions old)                             (+)
    reversal     rev_1w = -(5-session return)                                                    (+)
    low risk     low_vol_60 = -(60-session sd of daily log returns)                              (+)
    investment   neg_asset_growth = -asset_growth, neg_accruals = -accruals                      (+)

**Windows (pre-stated):** discovery 2010-2019, validation 2020-2022. The 2023+ research holdout is NOT touched.
**Target:** excess return over SPY from the next open to the open h sessions later, h = 5, 20, 60; formation every 5
sessions; universe = common stock >= $5 and >= $1M/day.

**Per signal x horizon x window:**
- IC: per-date Spearman correlation of the signal with the excess return; mean and a Newey-West t (lag = overlap).
- Implementation (Experiment B): equal-weight long-only basket of the top 20 names, net of the modelled round trip
  (spread tier + slippage), excess over SPY; Newey-West t.
- Volatility screen (AD4.5 test 1): the same basket after removing the top volatility decile; paired difference.
- Incremental value: ridge model on all twelve signals fitted on discovery, scored on validation, against the same
  model without the signal (ablation): change in mean validation IC, paired Newey-West t.
- Dependence map: correlation of the per-date IC series and the mean cross-sectional rank correlation between signals.

**Multiple testing:** every (signal, horizon, window, variant) evaluated is appended to `alpha_trials`; validation
p-values are Holm-adjusted across all validation tests run in the same pass.

**Status rule (pre-registered as experiment `alpha_bench_v1`):** VALIDATED = validation basket net excess > 0 with
Holm-adjusted one-sided p <= 0.05 AND validation mean IC > 0 AND incremental change in IC > 0. REPLICATED = discovery
IC in the published direction with NW t >= 2 (not validated). Otherwise NOT_SUPPORTED. VALIDATED makes a signal a
candidate for prospective SHADOW; it never touches live capital (AD6 decides that).

**Timing dial (AD4.5 test 2, pre-registered `classifier_timing_dial_v1`, one look):** does the cross-sectional mean
of the walk-forward XGBoost probability (oos_predictions) predict SPY's next-20-session return? Pass = pooled NW t >= 2
and the same sign in >= 70% of folds.

    ./run_bounded.sh ./venv/bin/python alpha_bench.py --register      # pre-register both experiments (once)
    ./run_bounded.sh ./venv/bin/python alpha_bench.py --run --write    # bench + timing dial -> reports/alpha_bench_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import math
import sqlite3
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import costs as costs_mod
import forward_stats as fs
from universe import load_config

ROOT = Path(__file__).resolve().parent
EXPERIMENT = "alpha_bench_v1"
TIMING = "classifier_timing_dial_v1"
DISCOVERY = ("2010-01-01", "2019-12-31")
VALIDATION = ("2020-01-01", "2022-12-31")
HORIZONS = (5, 20, 60)
STEP = 5
TOP_K = 20
SLIPPAGE_RT = 0.001                          # 0.05% per side, the cost model's slippage
MIN_NAMES = 100
FUND_COLS = ("fcf_to_price", "earnings_yield", "book_to_market", "gross_profitability", "asset_growth", "accruals")

SIGNALS = [
    # id, family, definition, published source
    ("mom_12_1", "momentum", "close[t-21] / close[t-252] - 1", "Jegadeesh & Titman (1993); JKP ret_12_1"),
    ("mom_9_1", "momentum", "close[t-21] / close[t-189] - 1", "JKP ret_9_1"),
    ("fcf_to_price", "value", "daily_fundamentals.fcf_to_price ((OCF - capex) / market cap), point in time", "JKP fcf_me"),
    ("earnings_yield", "value", "daily_fundamentals.earnings_yield, point in time", "JKP ni_me"),
    ("book_to_market", "value", "daily_fundamentals.book_to_market, point in time", "Fama & French (1992); JKP be_me"),
    ("gross_profitability", "quality", "daily_fundamentals.gross_profitability, point in time", "Novy-Marx (2013); JKP gp_at"),
    ("sue", "earnings", "daily_sue.sue (standardised unexpected earnings, period-matched)", "Bernard & Thomas (1989); JKP niq_su"),
    ("sue_fresh", "earnings", "daily_sue.sue where sue_age <= 20 sessions, else missing", "PEAD; drift concentrated after the report"),
    ("rev_1w", "reversal", "-(close[t] / close[t-5] - 1)", "Jegadeesh (1990); Lehmann (1990)"),
    ("low_vol_60", "low_risk", "-(sd of daily log returns over t-59..t)", "Ang, Hodrick, Xing & Zhang (2006); Frazzini & Pedersen (2014)"),
    ("neg_asset_growth", "investment", "-daily_fundamentals.asset_growth", "Cooper, Gulen & Schill (2008); JKP at_gr1"),
    ("neg_accruals", "investment", "-daily_fundamentals.accruals", "Sloan (1996); JKP oaccruals_at"),
]


# --- registry ---------------------------------------------------------------------------------------------------
def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS alpha_signals (
        signal_id TEXT PRIMARY KEY, family TEXT NOT NULL, definition TEXT NOT NULL, definition_hash TEXT NOT NULL,
        direction INTEGER NOT NULL, source TEXT, horizons TEXT, required_data TEXT, status TEXT NOT NULL,
        status_at TEXT, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS alpha_trials (
        id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL, experiment TEXT NOT NULL, signal_id TEXT NOT NULL,
        kind TEXT NOT NULL, horizon INTEGER, window TEXT, variant TEXT, metrics TEXT NOT NULL)""")
    conn.commit()


def _hash(s: str) -> str:
    return hashlib.sha256(s.encode()).hexdigest()[:16]


def seed_registry(conn) -> int:
    """Insert the first signal set (DISCOVERED). An existing id is never redefined: a changed definition is refused."""
    init(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    n = 0
    for sid, fam, defn, src in SIGNALS:
        r = conn.execute("SELECT definition_hash FROM alpha_signals WHERE signal_id=?", (sid,)).fetchone()
        if r:
            if r[0] != _hash(defn):
                raise RuntimeError(f"{sid}: definition changed; a changed signal needs a new signal_id")
            continue
        req = "fundamentals (point in time)" if sid in FUND_COLS or sid.startswith("neg_") else (
            "earnings surprise" if sid.startswith("sue") else "daily prices")
        conn.execute("INSERT INTO alpha_signals VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                     (sid, fam, defn, _hash(defn), 1, src, json.dumps(list(HORIZONS)), req, "DISCOVERED", now, now))
        n += 1
    conn.commit()
    return n


def trial(conn, experiment, sid, kind, h, window, variant, metrics) -> None:
    conn.execute("INSERT INTO alpha_trials (at, experiment, signal_id, kind, horizon, window, variant, metrics) "
                 "VALUES (?,?,?,?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(timespec="seconds"), experiment, sid,
                                              kind, h, window, variant, json.dumps(metrics, default=float)))


def trial_count(conn) -> int:
    init(conn)
    return int(conn.execute("SELECT COUNT(*) FROM alpha_trials").fetchone()[0])


def specs() -> dict:
    return {
        EXPERIMENT: {
            "primary_metric": "validation-window (2020-2022) excess return over SPY of an equal-weight long-only top-20 basket, "
                              "next open to next open, net of modelled spread tier + 0.1% slippage, Newey-West t; Holm across "
                              "every validation test in the pass",
            "universe": "common stock, close >= $5, dollar_volume_20 >= $1M at formation; formation every 5 sessions",
            "entry_rule": "the twelve signal definitions in alpha_bench.SIGNALS, published directions, no tuning",
            "exit_rule": "fixed horizon h in {5, 20, 60} sessions",
            "holding_period": "5, 20, 60 sessions",
            "cost_assumptions": "costs.estimate_spread_pct by dollar volume + 0.1% round-trip slippage",
            "evaluation_period": "discovery 2010-2019 (reported, decides REPLICATED only); validation 2020-2022 decides",
            "data_version": "prices / daily_fundamentals / daily_sue as stored on the run date",
            "stopping_rule": "one pass per signal definition; a changed definition is a new signal_id",
            "sample_size": "every formation date in each window with >= 100 eligible names",
            "holdout_policy": "2023+ is not read",
            "pass_rule": "VALIDATED = basket net excess > 0, Holm-adjusted one-sided p <= 0.05, validation IC > 0, incremental IC > 0",
        },
        TIMING: {
            "primary_metric": "correlation between the per-date mean oos_predictions score and SPY's next-20-session return "
                              "(next open to open), Newey-West t with lag 20",
            "universe": "every date in oos_predictions (walk-forward, 31 folds)",
            "entry_rule": "none (a measurement)", "exit_rule": "none", "holding_period": "20 sessions",
            "cost_assumptions": "none (a predictive test, not a strategy)",
            "evaluation_period": "all walk-forward test dates, one look",
            "data_version": "oos_predictions as stored", "stopping_rule": "one look; no re-run with a different horizon",
            "sample_size": "every date", "holdout_policy": "the walk-forward test folds only",
            "pass_rule": "pooled NW t >= 2 and the same sign in >= 70% of folds",
        },
    }


def register(conn) -> list:
    import experiment_registry as er
    out = []
    hyp = {EXPERIMENT: "At least one of twelve published signals, implemented long-only on our data, earns positive net excess "
                       "return over SPY in 2020-2022 beyond what multiple testing explains. Fails if none passes the rule.",
           TIMING: "The walk-forward classifier's average probability across stocks predicts the market's next-20-session "
                   "return. Fails if the pooled NW t is below 2 or the sign is unstable across folds."}
    for k, sp in specs().items():
        try:
            out.append(er.get(conn, k))
        except er.RegistryError:
            er.create(conn, k, hyp[k], "Claude (Stage AD4, owner-approved plan 2026-10-19)", sp)
            out.append(er.register(conn, k))
    return out


# --- statistics ----------------------------------------------------------------------------------------------
def nw_t(x, lag: int) -> float:
    """Newey-West t of the mean of a series with overlapping observations."""
    x = np.asarray([v for v in x if v == v], dtype=float)
    n = len(x)
    if n < 10:
        return float("nan")
    e = x - x.mean()
    s = float(e @ e) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - L / (lag + 1)) * float(e[L:] @ e[:-L]) / n
    se = math.sqrt(s / n) if s > 0 else float("nan")
    return float(x.mean() / se) if se == se and se else float("nan")


def p_one_sided(t: float, n: int) -> float:
    return fs.t_pvalue_one_sided(t, max(1, n - 1)) if t == t else 1.0


def _rank(a: np.ndarray) -> np.ndarray:
    return pd.Series(a).rank(pct=True).to_numpy()


def spearman(a: np.ndarray, b: np.ndarray) -> float:
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < MIN_NAMES:
        return float("nan")
    return float(np.corrcoef(_rank(a[m]), _rank(b[m]))[0, 1])


# --- data ------------------------------------------------------------------------------------------------------
def load(conn, start: str, end: str) -> dict:
    """Wide close/open matrices (dates x tickers) for common stock, SPY, and the sample dates' attached columns."""
    lo = (pd.Timestamp(start) - pd.Timedelta(days=400)).strftime("%Y-%m-%d")
    hi = (pd.Timestamp(end) + pd.Timedelta(days=120)).strftime("%Y-%m-%d")
    spy = pd.read_sql("SELECT date, open, close FROM prices WHERE ticker='SPY' AND date >= ? AND date <= ? ORDER BY date",
                      conn, params=(lo, hi)).set_index("date")
    dates = list(spy.index)
    tick = [r[0] for r in conn.execute("SELECT ticker FROM symbols WHERE security_type='common_stock' AND "
                                       "(data_quality IS NULL OR data_quality='') ORDER BY ticker")]
    di, ti = {d: i for i, d in enumerate(dates)}, {t: j for j, t in enumerate(tick)}
    # Streamed straight into float32 matrices: a DataFrame of ~20M rows with string columns needs several GB.
    C = np.full((len(dates), len(tick)), np.nan, dtype="float32")
    O = np.full((len(dates), len(tick)), np.nan, dtype="float32")
    cur = conn.execute("SELECT ticker, date, open, close FROM prices WHERE date >= ? AND date <= ?", (lo, hi))
    while True:
        rows = cur.fetchmany(500_000)
        if not rows:
            break
        for t, d, o, c_ in rows:
            j, i = ti.get(t), di.get(d)
            if j is not None and i is not None:
                O[i, j] = o if o is not None else np.nan
                C[i, j] = c_ if c_ is not None else np.nan
    keep = ~np.isnan(C).all(axis=0)
    cols = [t for t, k in zip(tick, keep) if k]
    close = pd.DataFrame(C[:, keep], index=dates, columns=cols)
    opn = pd.DataFrame(O[:, keep], index=dates, columns=cols)
    del C, O
    return {"dates": dates, "close": close, "open": opn, "spy": spy}


def sample_dates(dates: list, start: str, end: str, max_h: int) -> list:
    idx = [i for i, d in enumerate(dates) if start <= d <= end and i >= 252 and i + 1 + max_h < len(dates)]
    return idx[::STEP]


def attach(conn, dates_s: list) -> dict:
    """{date: DataFrame(ticker, dollar_volume_20, fundamentals..., sue, sue_age)} for the sample dates."""
    q = ",".join("?" * len(dates_s))
    dv = pd.read_sql(f"SELECT ticker, date, dollar_volume_20 FROM features WHERE date IN ({q})", conn, params=dates_s)
    fu = pd.read_sql(f"SELECT ticker, date, {', '.join(FUND_COLS)} FROM daily_fundamentals WHERE date IN ({q})", conn,
                     params=dates_s)
    su = pd.read_sql(f"SELECT ticker, date, sue, sue_age FROM daily_sue WHERE date IN ({q})", conn, params=dates_s)
    m = dv.merge(fu, on=["ticker", "date"], how="left").merge(su, on=["ticker", "date"], how="left")
    return {d: g.set_index("ticker") for d, g in m.groupby("date")}


def cross_section(data: dict, att: dict, i: int, h: int) -> pd.DataFrame | None:
    """Signals and the h-session excess return for formation index i (close of day i; entry next open)."""
    C, O, spy, dates = data["close"], data["open"], data["spy"], data["dates"]
    d = dates[i]
    a = att.get(d)
    if a is None:
        return None
    c0 = C.iloc[i]
    df = pd.DataFrame({"close": c0})
    df = df.join(a, how="left")
    df["mom_12_1"] = C.iloc[i - 21] / C.iloc[i - 252] - 1
    df["mom_9_1"] = C.iloc[i - 21] / C.iloc[i - 189] - 1
    df["rev_1w"] = -(c0 / C.iloc[i - 5] - 1)
    lr = np.log(C.iloc[i - 60:i + 1]).diff().iloc[1:]
    df["low_vol_60"] = -lr.std()
    df["vol60"] = lr.std()
    df["neg_asset_growth"] = -df["asset_growth"]
    df["neg_accruals"] = -df["accruals"]
    df["sue_fresh"] = df["sue"].where(df["sue_age"] <= 20)
    e0, e1 = O.iloc[i + 1], O.iloc[i + 1 + h]
    s0, s1 = float(spy["open"].iloc[i + 1]), float(spy["open"].iloc[i + 1 + h])
    df["excess"] = (e1 / e0 - 1) - (s1 / s0 - 1)
    elig = (df["close"] >= 5) & (df["dollar_volume_20"] >= 1e6) & df["excess"].notna() & np.isfinite(df["excess"]) \
        & (df["excess"].abs() < 3)
    out = df[elig]
    return out if len(out) >= MIN_NAMES else None


def basket(cs: pd.DataFrame, sid: str, k: int = TOP_K, screen_vol: bool = False) -> float:
    s = cs[cs[sid].notna()]
    if screen_vol and len(s):
        s = s[s["vol60"] < s["vol60"].quantile(0.9)]
    if len(s) < k:
        return float("nan")
    top = s.nlargest(k, sid)
    rt = top["dollar_volume_20"].map(lambda v: float(costs_mod.estimate_spread_pct(float(v)))) + SLIPPAGE_RT
    return float((top["excess"] - rt).mean())


def zmatrix(cs: pd.DataFrame, ids: list) -> np.ndarray:
    """Per-date ranks mapped to [-0.5, 0.5], missing = 0 (neutral)."""
    return np.column_stack([(cs[s].rank(pct=True) - 0.5).fillna(0).to_numpy() for s in ids])


def ridge(X: np.ndarray, y: np.ndarray, lam: float = 10.0) -> np.ndarray:
    k = X.shape[1]
    return np.linalg.solve(X.T @ X + lam * len(y) / 1000 * np.eye(k), X.T @ y)


# --- the bench --------------------------------------------------------------------------------------------------
def bench(conn, data: dict | None = None, write_trials: bool = True) -> dict:
    ids = [s[0] for s in SIGNALS]
    if data is None:
        data = load(conn, DISCOVERY[0], VALIDATION[1])
    res = {"signals": {}, "dependence": None, "windows": {"discovery": DISCOVERY, "validation": VALIDATION}}
    per_h = {}
    for h in HORIZONS:
        lag = max(1, math.ceil(h / STEP))
        rows = {"discovery": [], "validation": []}
        for wname, (a, b) in (("discovery", DISCOVERY), ("validation", VALIDATION)):
            idx = sample_dates(data["dates"], a, b, max(HORIZONS))
            att = attach(conn, [data["dates"][i] for i in idx])
            for i in idx:
                cs = cross_section(data, att, i, h)
                if cs is not None:
                    rows[wname].append((data["dates"][i], cs))
        per_h[h] = rows
        # incremental: ridge on discovery, scored on validation, full vs ablated
        Xd = np.vstack([zmatrix(cs, ids) for _, cs in rows["discovery"]]) if rows["discovery"] else np.zeros((0, len(ids)))
        yd = np.concatenate([cs["excess"].to_numpy() for _, cs in rows["discovery"]]) if rows["discovery"] else np.zeros(0)
        full = ridge(Xd, yd) if len(yd) else np.zeros(len(ids))
        abl = {j: ridge(np.delete(Xd, j, axis=1), yd) if len(yd) else np.zeros(len(ids) - 1) for j in range(len(ids))}
        ic_full = [spearman(zmatrix(cs, ids) @ full, cs["excess"].to_numpy()) for _, cs in rows["validation"]]
        for j, sid in enumerate(ids):
            m = {}
            for wname in ("discovery", "validation"):
                ic = [spearman(cs[sid].to_numpy(dtype=float), cs["excess"].to_numpy()) for _, cs in rows[wname]]
                bk = [basket(cs, sid) for _, cs in rows[wname]]
                bv = [basket(cs, sid, screen_vol=True) for _, cs in rows[wname]]
                diff = [x - y for x, y in zip(bv, bk) if x == x and y == y]
                n_ok = sum(1 for v in bk if v == v)
                m[wname] = {"dates": len(rows[wname]), "ic": float(np.nanmean(ic)) if ic else float("nan"),
                            "ic_t": nw_t(ic, lag), "basket": float(np.nanmean(bk)) if n_ok else float("nan"),
                            "basket_t": nw_t(bk, lag), "basket_n": n_ok,
                            "vol_screen_gain": float(np.mean(diff)) if diff else float("nan"),
                            "vol_screen_t": nw_t(diff, lag), "ic_series": ic}
            ic_abl = [spearman(np.delete(zmatrix(cs, ids), j, axis=1) @ abl[j], cs["excess"].to_numpy())
                      for _, cs in rows["validation"]]
            dlt = [x - y for x, y in zip(ic_full, ic_abl) if x == x and y == y]
            m["incremental_ic"] = float(np.mean(dlt)) if dlt else float("nan")
            m["incremental_t"] = nw_t(dlt, lag)
            res["signals"].setdefault(sid, {})[h] = m
        if h == 20 and rows["discovery"]:
            ics = pd.DataFrame({sid: res["signals"][sid][20]["discovery"]["ic_series"] for sid in ids})
            sample = rows["discovery"][::4]
            xc = np.nanmean([pd.DataFrame({s: cs[s] for s in ids}).rank().corr().to_numpy() for _, cs in sample], axis=0)
            res["dependence"] = {"ic_corr": ics.corr(), "value_corr": pd.DataFrame(xc, index=ids, columns=ids)}
    # Holm across every validation basket test in this pass, then the status rule
    tests = [(sid, h) for sid in ids for h in HORIZONS]
    pv = [p_one_sided(res["signals"][s][h]["validation"]["basket_t"], res["signals"][s][h]["validation"]["basket_n"])
          for s, h in tests]
    adj = fs.holm(pv)
    for (sid, h), p, a in zip(tests, pv, adj):
        m = res["signals"][sid][h]
        m["p"], m["p_holm"] = p, a
        v, dd = m["validation"], m["discovery"]
        m["status"] = ("VALIDATED" if (v["basket"] > 0 and a <= 0.05 and v["ic"] > 0 and m["incremental_ic"] > 0) else
                       "REPLICATED" if (dd["ic"] > 0 and (dd["ic_t"] or 0) >= 2) else "NOT_SUPPORTED")
    if write_trials:
        init(conn)
        for sid in ids:
            for h in HORIZONS:
                m = res["signals"][sid][h]
                for wname in ("discovery", "validation"):
                    w = {k: v for k, v in m[wname].items() if k != "ic_series"}
                    trial(conn, EXPERIMENT, sid, "ic+basket", h, wname, "faithful/long-only top-20", w)
                    trial(conn, EXPERIMENT, sid, "vol_screen", h, wname, "top-20 minus top-decile volatility",
                          {"gain": w["vol_screen_gain"], "t": w["vol_screen_t"]})
                trial(conn, EXPERIMENT, sid, "incremental", h, "validation", "ridge ablation",
                      {"d_ic": m["incremental_ic"], "t": m["incremental_t"], "status": m["status"]})
            best = max((res["signals"][sid][h]["status"] for h in HORIZONS),
                       key=["NOT_SUPPORTED", "REPLICATED", "VALIDATED"].index)
            conn.execute("UPDATE alpha_signals SET status=?, status_at=? WHERE signal_id=?",
                         (best, datetime.now(timezone.utc).isoformat(timespec="seconds"), sid))
        conn.commit()
    return res


def timing_dial(conn) -> dict:
    """Pre-registered one-look test of the classifier as a market-timing signal."""
    m = pd.read_sql("SELECT date, fold, AVG(score) AS s FROM oos_predictions GROUP BY date, fold ORDER BY date", conn)
    spy = pd.read_sql("SELECT date, open FROM prices WHERE ticker='SPY' ORDER BY date", conn).set_index("date")["open"]
    pos = {d: i for i, d in enumerate(spy.index)}
    vals = spy.to_numpy()
    fwd = []
    for d in m["date"]:
        i = pos.get(d)
        fwd.append(vals[i + 21] / vals[i + 1] - 1 if i is not None and i + 21 < len(vals) else np.nan)
    m["fwd"] = fwd
    m = m.dropna()
    # standardise the score within each fold (each fold's model has its own level), then pool
    m["z"] = m.groupby("fold")["s"].transform(lambda x: (x - x.mean()) / (x.std() or 1))
    pooled = float(np.corrcoef(m["z"], m["fwd"])[0, 1])
    prod = (m["z"] * (m["fwd"] - m["fwd"].mean())).to_numpy()
    t = nw_t(prod, 20)
    by_fold = m.groupby("fold").apply(lambda g: float(np.corrcoef(g["s"], g["fwd"])[0, 1]) if len(g) > 20 else np.nan).dropna()
    same = float((np.sign(by_fold) == np.sign(pooled)).mean()) if len(by_fold) else float("nan")
    return {"dates": int(len(m)), "folds": int(len(by_fold)), "corr": pooled, "nw_t": t, "same_sign_share": same,
            "pass": bool(t == t and t >= 2 and same >= 0.7)}


# --- report -------------------------------------------------------------------------------------------------------
def _f(v, s="{:+.3f}"):
    return "n/a" if v is None or v != v else s.format(v)


def render(res: dict, td: dict | None, n_trials: int) -> str:
    L = [f"# Alpha bench — {date.today().isoformat()} (experiment `{EXPERIMENT}`)", "",
         f"Discovery {DISCOVERY[0][:4]}-{DISCOVERY[1][:4]}, validation {VALIDATION[0][:4]}-{VALIDATION[1][:4]}; 2023+ untouched. "
         f"Excess over SPY, next open to next open; basket = equal-weight top {TOP_K}, long-only, net of modelled costs. "
         f"Trials in the registry after this pass: {n_trials}.", "",
         "| signal | h | IC disc (t) | IC valid (t) | basket net disc (t) | basket net valid (t) | Holm p | vol screen gain valid | incremental IC (t) | status |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for sid, by in res["signals"].items():
        for h, m in by.items():
            d, v = m["discovery"], m["validation"]
            L.append(f"| {sid} | {h} | {_f(d['ic'])} ({_f(d['ic_t'], '{:+.1f}')}) | {_f(v['ic'])} ({_f(v['ic_t'], '{:+.1f}')}) | "
                     f"{_f(d['basket'], '{:+.2%}')} ({_f(d['basket_t'], '{:+.1f}')}) | {_f(v['basket'], '{:+.2%}')} "
                     f"({_f(v['basket_t'], '{:+.1f}')}) | {_f(m.get('p_holm'), '{:.3f}')} | {_f(v['vol_screen_gain'], '{:+.2%}')} | "
                     f"{_f(m['incremental_ic'], '{:+.4f}')} ({_f(m['incremental_t'], '{:+.1f}')}) | {m['status']} |")
    L += ["", "IC = per-date Spearman rank correlation with the excess return (Newey-West t). Basket net per holding period. "
          "Vol screen gain = the basket after removing the top volatility decile minus the plain basket (positive = the "
          "screen helps). Incremental IC = validation IC of a ridge model on all twelve signals minus the same model without "
          "this one. Status rule pre-registered: see the module docstring.", ""]
    dep = res.get("dependence")
    if dep is not None:
        L += ["## Dependence (h = 20, discovery): mean cross-sectional rank correlation of signal values", "",
              "| | " + " | ".join(dep["value_corr"].columns) + " |", "|---|" + "---:|" * len(dep["value_corr"].columns)]
        for r, row in dep["value_corr"].iterrows():
            L.append(f"| {r} | " + " | ".join(f"{v:+.2f}" for v in row) + " |")
        L.append("")
    if td:
        L += [f"## Classifier as a timing dial (`{TIMING}`, one look)", "",
              f"{td['dates']:,} dates over {td['folds']} folds: correlation of the average predicted probability with SPY's "
              f"next-20-session return {td['corr']:+.3f}, NW t {_f(td['nw_t'], '{:+.2f}')}, same sign in "
              f"{td['same_sign_share']:.0%} of folds -> **{'PASS' if td['pass'] else 'FAIL'}**.", ""]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    if a.register:
        for e in register(conn):
            print(f"{e['experiment_id']} v{e['version']} {e['status']}")
        print(f"registry: {seed_registry(conn)} signals added")
        return 0
    if a.run:
        import experiment_registry as er
        for k in (EXPERIMENT, TIMING):
            if er.get(conn, k)["status"] not in ("REGISTERED", "RUNNING"):
                print(f"{k} is {er.get(conn, k)['status']}: refusing a second look")
                return 2
        seed_registry(conn)
        conn.row_factory = None
        res = bench(conn)
        td = timing_dial(conn)
        conn.row_factory = sqlite3.Row
        for k, results in ((EXPERIMENT, {s: {h: {kk: vv for kk, vv in m.items() if kk not in ("discovery", "validation")}
                                              for h, m in by.items()} for s, by in res["signals"].items()}),
                           (TIMING, td)):
            er.start(conn, k)
            er.complete(conn, k, json.loads(json.dumps(results, default=float)),
                        "see reports/alpha_bench_<date>.md")
        text = render(res, td, trial_count(conn))
        print(text)
        if a.write:
            p = ROOT / "reports" / f"alpha_bench_{date.today().isoformat()}.md"
            p.write_text(text)
            print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
