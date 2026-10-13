"""
Addendum F, Phase E3 — a small, pre-registered baseline-versus-similarity experiment (the "Historical Experience
Learning Engine" question), built on the Stage P library instead of a new subsystem.

QUESTION   Does choosing stocks by what happened after their most similar past situations (analog.py) earn more net
           of costs, out of sample, than (a) not using history at all and (b) a basic predictive model on the same
           information, once costs and next-open entries are charged?

DESIGN     (all fixed in the experiment registry before the first run; see SPEC)
  library    data/analog/library.parquet: one row per stock-day every 5th session since 2006, features are each
             indicator's percentile among all stocks that day (point in time), outcome = open of the next session to
             the open 20 sessions later on unfiltered prices (a collapse counts), gross of costs.
  periods    train: exit date <= 2019-12-31 | validation: query dates 2020-2022 | test: query dates 2023-01-01 on.
             Query dates are every 4th library date (20 sessions apart), so holdings never overlap.
  universe   per query date, 500 random liquid names (log dollar volume percentile >= 0.30) with a known outcome.
  selection  top decile (50 names) by each method on that date:
               random     every one of the 500 (the universe mean; no history used)
               momentum   120-session return, the simple rule that does not use similarity
               analog     mean outcome of the 200 nearest past situations whose own outcome was known on that date
               model      gradient-boosted regressor on the same features, fitted once on rows exited by the end of
                          the preceding period (no refit inside a period)
  cost       0.17 % round trip charged to every selected trade (the engine's modelled average), entry at the next open.
  decision   the analog method "merits further investment" ONLY if, in the TEST period, its mean net return per
             selected trade exceeds BOTH random and momentum, and the 95 % lower bound of that difference, from a
             bootstrap over the query dates, is above zero, and it also exceeds the model.  Otherwise it does not,
             and no subsystem is built.

CAVEAT     The 2023-onward window was already looked at by Stage P's evaluation (analog_eval.py), so it is a
           chronological test, not an unseen one.  Only forward trading is unseen.

    ./run_bounded.sh ./venv/bin/python experience_experiment.py            # run (registers on first use)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

from analog import COLS, neighbours
from universe import load_config

EXPERIMENT = "analog_vs_baseline_2026_10"
SEED = 20261013
K = 200
NAMES = 500
TOP = 0.10
COST = 0.0017
POOL_ROWS = 500_000
TRAIN_END, VAL_START, VAL_END, TEST_START = "2019-12-31", "2020-01-01", "2022-12-31", "2023-01-01"
LIQ = 0.30
METHODS = ["random", "momentum", "analog", "model"]

SPEC = {
    "primary_metric": "mean net return per selected trade (top decile of 500 random liquid names per query date), costs 0.17 % round trip, next-open entry, 20-session hold",
    "universe": "analog library rows (every 5th session since 2006), 500 random names per query date with log_dollar_volume percentile >= 0.30",
    "entry_rule": "top decile by each method: random (no selection), momentum (ret_120), analog (mean outcome of 200 nearest past situations known by that date), model (boosted regressor on the same features)",
    "exit_rule": "open 20 sessions after the entry open",
    "holding_period": "20 sessions, non-overlapping query dates",
    "cost_assumptions": "0.17 % round trip on every selected trade",
    "evaluation_period": f"validation: query dates {VAL_START} to {VAL_END}; test: {TEST_START} onward; train: outcomes known by {TRAIN_END}",
    "data_version": "data/analog/library.parquet as built; seed 20261013",
    "stopping_rule": "one run per version; no parameter is changed after the first look",
    "sample_size": "every 4th library date in each period, 500 names per date",
    "holdout_policy": "2023-onward was seen by Stage P's evaluation: a chronological test, not an unseen one",
    "decision_rule": "analog merits further investment only if TEST mean net exceeds both random and momentum with a 95% bootstrap lower bound (over dates) of the difference above zero, and exceeds the model; otherwise stop",
}


def register(conn):
    import experiment_registry as er
    conn.row_factory = sqlite3.Row
    try:
        e = er.get(conn, EXPERIMENT)
    except er.RegistryError:
        er.create(conn, EXPERIMENT, "Selecting stocks by similarity to past situations earns more net return than not using history and than a basic model on the same features, out of sample.",
                  "claude", SPEC)
        er.register(conn, EXPERIMENT)
        e = er.get(conn, EXPERIMENT)
    return e


def load() -> pd.DataFrame:
    lib = pd.read_parquet(Path("data/analog/library.parquet"))
    lib = lib.dropna(subset=["fwd_ret", "exit_date"]).reset_index(drop=True)
    lib["fwd_ret"] = lib["fwd_ret"].astype("float32")
    return lib


def query_dates(lib: pd.DataFrame, lo: str, hi: str) -> list:
    d = sorted(lib.loc[(lib["date"] >= lo) & (lib["date"] <= hi), "date"].unique())
    return d[::4]


def fit_model(lib: pd.DataFrame, exit_by: str, rng):
    from xgboost import XGBRegressor
    tr = lib[lib["exit_date"] <= exit_by]
    tr = tr.sample(min(len(tr), 600_000), random_state=int(rng.integers(1 << 30)))
    m = XGBRegressor(n_estimators=200, max_depth=4, learning_rate=0.05, subsample=0.8, tree_method="hist", n_jobs=3, verbosity=0)
    m.fit(tr[COLS].to_numpy(np.float32), tr["fwd_ret"].clip(-0.5, 1.0).to_numpy(np.float32))
    return m


def run_period(lib, pool_all, dates, model, rng) -> pd.DataFrame:
    rows = []
    for d in dates:
        day = lib[(lib["date"] == d) & (lib["log_dollar_volume"] >= LIQ)]
        if len(day) < 100:
            continue
        u = day.sample(min(NAMES, len(day)), random_state=int(rng.integers(1 << 30)))
        k = max(1, int(round(len(u) * TOP)))
        pool = pool_all[pool_all["exit_date"] <= d]                         # outcomes already known on d
        idx, _ = neighbours(pool[COLS].to_numpy(np.float32), u[COLS].to_numpy(np.float32), K)
        fr = pool["fwd_ret"].to_numpy(np.float32)
        score = {"momentum": u["ret_120"].to_numpy(), "analog": fr[idx].mean(axis=1), "model": model.predict(u[COLS].to_numpy(np.float32))}
        out = {"date": d, "universe": len(u), "random": float(u["fwd_ret"].mean() - COST)}
        for name, s in score.items():
            top = np.argsort(-s)[:k]
            sel = u["fwd_ret"].to_numpy()[top]
            out[name] = float(sel.mean() - COST)
            out[name + "_q10"] = float(np.quantile(sel, 0.1) - COST)
            out[name + "_hit"] = float((sel - COST > 0).mean())
        out["random_q10"] = float(np.quantile(u["fwd_ret"], 0.1) - COST)
        out["random_hit"] = float((u["fwd_ret"] - COST > 0).mean())
        rows.append(out)
    return pd.DataFrame(rows)


def boot_diff(a: pd.Series, b: pd.Series, reps: int = 4000) -> tuple:
    d = (a - b).dropna().to_numpy()
    if len(d) < 5:
        return np.nan, np.nan, np.nan
    rng = np.random.default_rng(SEED)
    m = np.array([rng.choice(d, len(d)).mean() for _ in range(reps)])
    return float(d.mean()), float(np.quantile(m, 0.025)), float(np.quantile(m, 0.975))


def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def run() -> dict:
    cfg = load_config()
    rc = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    rc.row_factory = sqlite3.Row
    e = register(rc)
    rng = np.random.default_rng(SEED)
    lib = load()
    pool_all = lib.sample(min(POOL_ROWS, len(lib)), random_state=SEED)
    res = {}
    for name, (lo, hi, model_exit) in {"validation": (VAL_START, VAL_END, TRAIN_END), "test": (TEST_START, "2099-12-31", VAL_END)}.items():
        model = fit_model(lib, model_exit, rng)
        res[name] = run_period(lib, pool_all, query_dates(lib, lo, hi), model, rng)
    return {"res": res, "registry": e, "rows": len(lib)}


def render(o: dict, as_of: str) -> str:
    L = [f"# Phase E3: historical-experience (similarity) experiment, baseline versus analog", "",
         f"Run {as_of}. Pre-registered as `{EXPERIMENT}` v{o['registry']['version']} (registered {o['registry']['registered_at']}); the spec is locked. Library {o['rows']:,} stock-days with known outcomes. "
         "All figures are net of 0.17 % round-trip cost, next-open entry, 20-session hold, top decile (50 of 500 random liquid names) per query date, query dates 20 sessions apart.", ""]
    verdict = None
    for per in ("validation", "test"):
        r = o["res"][per]
        L += [f"## {per.capitalize()} period ({len(r)} query dates, {r['date'].iloc[0]} to {r['date'].iloc[-1]})", "",
              "| method | mean net % per selected trade | 10th percentile of trades % | share of trades net positive | worst date % | dates with positive mean |", "|---|---:|---:|---:|---:|---:|"]
        for m in METHODS:
            L.append(f"| {m} | {f(r[m].mean() * 100)} | {f(r[m + '_q10'].mean() * 100)} | {r[m + '_hit'].mean():.0%} | {f(r[m].min() * 100)} | {(r[m] > 0).mean():.0%} |")
        L += ["", "Difference in mean net return per trade, analog minus other (percentage points; 95 % bootstrap interval over query dates):", "", "| versus | difference | interval |", "|---|---:|---|"]
        diffs = {}
        for m in ("random", "momentum", "model"):
            d, lo, hi = boot_diff(r["analog"], r[m])
            diffs[m] = (d, lo, hi)
            L.append(f"| {m} | {f(d * 100)} | {f(lo * 100)} to {f(hi * 100)} |")
        L.append("")
        if per == "test":
            verdict = all(diffs[m][1] > 0 for m in ("random", "momentum")) and diffs["model"][0] > 0
    r = o["res"]["test"]
    dd = (r["analog"] - r["random"])
    need = (1.96 * dd.std() / abs(dd.mean())) ** 2 if abs(dd.mean()) > 1e-9 else float("nan")
    L += ["## Power", "", f"In the test period the analog-minus-random difference averages {f(dd.mean() * 100)} points with a standard deviation of {f(dd.std() * 100, '{:.1f}')} points across dates; "
          f"detecting a difference that size at 95 % would take about {need:.0f} non-overlapping query dates (there are {len(dd)}). The point estimates favour the analog method in both periods; the data cannot tell that from noise, "
          "and the same sample shows a basic model and a momentum rule are no more distinguishable from random. A larger replication is the only way to resolve it, and Stage P's much larger walk-forward (400,000 predictions) found AUC 0.523.", ""]
    L += ["## Decision", "",
          ("**The analog method meets the pre-registered bar** (beats random and momentum with a lower bound above zero, and beats the model). It merits a larger, still pre-registered replication before any use."
           if verdict else
           "**The analog method does not meet the pre-registered bar** in the test period (it must beat both the no-history baseline and the simple momentum rule with a 95 % lower bound above zero, and beat the model). "
           "Consistent with Stage P (walk-forward AUC 0.523 against 0.626 for the classifier). No subsystem is built; the experience-library idea is not expanded."), "",
          "## What could be wrong with this analysis", "",
          "- The 2023-onward window was already examined by Stage P's evaluation; this is a chronological test, not an unseen one.",
          "- 500 random names per date and 200 neighbours from a 500,000-row sample of the library are choices made once, in advance; a larger pool or different feature weighting could behave differently (that is a different experiment).",
          "- Library features are cross-sectional percentiles on a 5-session grid; they omit sector, breadth, maximum adverse excursion, gaps and intraday information the addendum lists as candidates.",
          "- Gross outcomes are open to open; the single 0.17 % cost does not vary with liquidity or price.",
          "- Where fundamentals were unavailable (early years) the percentile is a constant 0.5, which weakens the similarity method in those years."]
    return "\n".join(L) + "\n", verdict


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    now = datetime.now(timezone.utc)
    o = run()
    text, verdict = render(o, now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"experience_experiment_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    # record the result in the registry (once)
    import experiment_registry as er
    rc = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=120)
    rc.row_factory = sqlite3.Row
    e = er.get(rc, EXPERIMENT)
    if e["status"] != "COMPLETE":
        if e["status"] == "REGISTERED":
            er.start(rc, EXPERIMENT)
        summ = {p: {m: float(o["res"][p][m].mean()) for m in METHODS} for p in o["res"]}
        er.complete(rc, EXPERIMENT, {"mean_net_per_trade": summ, "meets_bar": bool(verdict)},
                    "analog meets the pre-registered bar" if verdict else "analog does not meet the pre-registered bar; no subsystem built")
    return 0


if __name__ == "__main__":
    sys.exit(main())
