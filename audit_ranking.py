"""
Addendum F, Phase B3 — audit of the ranking formula (read-only; changes nothing live).

Questions the audit answers, each from the production tables, not from the documentation:

  1. Does production match the documented formula?  score = (k x backtest + n x forward) / (k + n), k = 10,
     then x 20 / max(hold, 5)?   (ranking_history vs ranking.score)
  2. What does it do with small and correlated samples?  (n counts TRADES, not independent entry dates)
  3. Is it calibrated?  Each daily ranking is a prediction; the later honest net returns (paper_trades_restated,
     next-open fills, modelled costs deducted) of the same strategy are the outcome.  Rank correlation and
     reliability bins, per ranking date, never pooled across dates as if independent.
  4. Which information predicts?  stored score vs backtest only vs forward only vs the 10:n blend vs an
     empirical-Bayes forward estimate that shrinks by date-clustered uncertainty (a candidate replacement,
     evaluated here chronologically, NOT adopted).
  5. Did the controlled replacements of 2026-10 pick better strategies than the ones they dropped?

    ./venv/bin/python audit_ranking.py            # prints and writes reports/audit_ranking_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

import forward_stats as fs
from universe import load_config

K_PRIOR = 10
MIN_LATER = 3                 # a strategy needs this many later trades to have an outcome at all
TOP_N = 5
MIN_FUNDS = 30


# --- data --------------------------------------------------------------------------------------
def run_map(conn) -> pd.DataFrame:
    """strategy_key, version -> paper run id (factory funds via the link table, plain `paper:` keys directly)."""
    link = pd.read_sql_query("SELECT strategy_key, version, run_id FROM factory_paper_link", conn)
    return link


def history(conn) -> pd.DataFrame:
    rh = pd.read_sql_query("SELECT * FROM ranking_history", conn)
    link = run_map(conn)
    rh = rh.merge(link, on=["strategy_key", "version"], how="left")
    direct = rh["strategy_key"].where(rh["strategy_key"].str.startswith("paper:")).str[6:]
    rh["run_id"] = rh["run_id"].fillna(direct)
    return rh


def trades(conn) -> pd.DataFrame:
    return pd.read_sql_query("SELECT run_id, ticker, entry_date, net_pct FROM paper_trades_restated "
                             "WHERE version='v2_next_open'", conn)


def entries(conn) -> pd.DataFrame:
    """Every entry the fund ever made that is known now: closed trades plus positions still open. A snapshot's `n`
    counts open positions (marked), so independent dates must too."""
    a = pd.read_sql_query("SELECT run_id, ticker, entry_date FROM paper_trades", conn)
    b = pd.read_sql_query("SELECT run_id, ticker, entry_date FROM paper_positions", conn)
    return pd.concat([a, b], ignore_index=True)


# --- 1. formula --------------------------------------------------------------------------------
def formula_check(conn, rh: pd.DataFrame) -> dict:
    """Recompute the blend from stored components using the PRIOR PRODUCTION ACTUALLY USES (ranking.rank): the
    unseen-window (2023-today) result when one exists, else the survivorship backtest; zero for Lab-search funds
    (scored on paper only). The stored score also carries the 20 / max(hold, 5) factor, so stored / raw must be one
    positive constant per strategy across dates."""
    import ranking
    ho = pd.read_sql_query("SELECT strategy_key, version, per_trade FROM holdout_results", conn)
    ho = ho.sort_values("per_trade").drop_duplicates(["strategy_key", "version"], keep="last")
    d = rh.merge(ho.rename(columns={"per_trade": "ho"}), on=["strategy_key", "version"], how="left")
    keys = d["strategy_key"].unique()
    searched = {k: bool(ranking.from_search(conn, k)) for k in keys}
    d["searched"] = d["strategy_key"].map(searched)
    d["prior"] = np.where(d["searched"], 0.0, d["ho"].fillna(d["backtest"]))
    n = d["forward_trades"].fillna(0).clip(lower=0)
    fw = d["forward"].fillna(0.0)
    d["raw"] = np.where(n > 0, (K_PRIOR * d["prior"] + n * fw) / (K_PRIOR + n), d["prior"])
    d = d[d["prior"].notna() & (d["raw"].abs() > 1e-9)].copy()
    d["ratio"] = d["score"] / d["raw"]
    g = d.groupby(["strategy_key", "version"])["ratio"]
    spread = (g.max() - g.min()) / g.median().abs()
    r = d["ratio"].replace([np.inf, -np.inf], np.nan).dropna()
    return {"rows": int(len(d)), "strategies": int(len(spread)), "ratio_stable_share": float((spread < 0.05).mean()),
            "ratio_median": float(r.median()), "ratio_p10": float(r.quantile(0.1)), "ratio_p90": float(r.quantile(0.9)),
            "share_ratio_gt3": float((r > 3).mean()), "share_ratio_neg": float((r < 0).mean()),
            "share_holdout_prior": float(d["ho"].notna().mean()), "share_search_zero_prior": float(d["searched"].mean())}


# --- 2. small / correlated samples -------------------------------------------------------------
def top_composition(rh: pd.DataFrame, tr: pd.DataFrame, top: int = 50) -> pd.DataFrame:
    rows = []
    for d, g in rh[rh["passes_gate"] == 1].groupby("date"):
        t = g.sort_values("score", ascending=False).head(top)
        dates_cache = {}
        nd = []
        for r in t.itertuples():
            if pd.isna(r.run_id):
                nd.append(np.nan); continue
            if r.run_id not in dates_cache:
                x = tr[(tr["run_id"] == r.run_id) & (tr["entry_date"] < d)]
                dates_cache[r.run_id] = x["entry_date"].nunique()
            nd.append(dates_cache[r.run_id])
        t = t.assign(ndates=nd)
        rows.append({"date": d, "top": len(t), "median_trades": float(t["forward_trades"].median()),
                     "share_trades_lt10": float((t["forward_trades"] < 10).mean()),
                     "median_indep_dates": float(np.nanmedian(nd)) if len(nd) else np.nan,
                     "share_dates_lt5": float((pd.Series(nd) < 5).mean())})
    return pd.DataFrame(rows)


# --- 3./4. calibration and information value ---------------------------------------------------
def eb_estimates(tr: pd.DataFrame, as_of: str) -> pd.Series:
    """Empirical-Bayes forward estimate per run id from trades entered before `as_of`: per-fund mean of per-date
    means, standard error from the dates (not the trades), shrunk toward the pool mean with a method-of-moments
    between-fund variance. A fund with one date has no usable standard error and gets the pool mean."""
    x = tr[tr["entry_date"] < as_of]
    dm = x.groupby(["run_id", "entry_date"])["net_pct"].mean().reset_index()
    # a single +164% trade (KOD, shared by three funds) must not decide a fund's estimate: winsorise date means at the pool's 1st/99th percentile
    lo, hi = dm["net_pct"].quantile([0.01, 0.99]) if len(dm) >= 50 else (-np.inf, np.inf)
    dm["net_pct"] = dm["net_pct"].clip(lo, hi)
    g = dm.groupby("run_id")["net_pct"]
    mean, nd, var = g.mean(), g.count(), g.var(ddof=1)
    pool = float(dm["net_pct"].mean()) if len(dm) else 0.0
    # sampling variance of each fund's mean: var / nd; funds with < 3 dates get the median var, so they shrink hard
    med_var = float(var[nd >= 3].median()) if (nd >= 3).any() else 1.0
    v = var.where(nd >= 3, med_var).fillna(med_var).clip(lower=1e-6)
    se2 = v / nd.clip(lower=1)
    tau2 = max(float(mean[nd >= 3].var(ddof=1) - se2[nd >= 3].mean()), 1e-6) if (nd >= 3).sum() > 5 else 1e-6
    w = tau2 / (tau2 + se2)
    return (pool + w * (mean - pool)) / 100.0


def outcomes(tr: pd.DataFrame, d: str) -> pd.DataFrame:
    x = tr[tr["entry_date"] >= d]
    g = x.groupby("run_id")["net_pct"].agg(["mean", "count"])
    g["dates"] = x.groupby("run_id")["entry_date"].nunique()
    g["mean"] = g["mean"] / 100.0
    return g[g["count"] >= MIN_LATER].rename(columns={"mean": "realised", "count": "later_trades", "dates": "later_dates"})


def evaluate(rh: pd.DataFrame, tr: pd.DataFrame) -> dict:
    per_date, bins_rows, top_rows = [], [], []
    for d in sorted(rh["date"].unique()):
        h = rh[(rh["date"] == d) & rh["run_id"].notna()].drop_duplicates("run_id")
        out = outcomes(tr, d)
        m = h.merge(out, left_on="run_id", right_index=True)
        if len(m) < MIN_FUNDS:
            continue
        n = m["forward_trades"].fillna(0)
        m["blend"] = (K_PRIOR * m["backtest"].fillna(0) + n * m["forward"].fillna(0)) / (K_PRIOR + n)
        m["bt_only"] = m["backtest"]
        m["fw_only"] = m["forward"]
        eb = eb_estimates(tr, d)
        m["eb"] = m["run_id"].map(eb)
        preds = ["score", "blend", "bt_only", "fw_only", "eb"]
        row = {"date": d, "funds": len(m), "later_dates": int(m["later_dates"].median()),
               "realised_mean": float(m["realised"].mean())}
        for p in preds:
            mm = m.dropna(subset=[p])
            row[p + "_rho"] = float(mm[p].rank().corr(mm["realised"].rank())) if len(mm) >= MIN_FUNDS else np.nan
            if len(mm) >= MIN_FUNDS:
                top = mm[mm["passes_gate"] == 1].sort_values(p, ascending=False).head(TOP_N)
                row[p + "_top"] = float(top["realised"].mean()) if len(top) else np.nan
                if p == "score":
                    q = pd.qcut(mm[p].rank(method="first"), 5, labels=False)
                    for b, gq in mm.groupby(q):
                        bins_rows.append({"date": d, "bin": int(b) + 1, "predicted": float(gq[p].mean()), "realised": float(gq["realised"].mean()), "n": len(gq)})
        per_date.append(row)
    return {"per_date": pd.DataFrame(per_date), "bins": pd.DataFrame(bins_rows)}


# --- 5. replacements ---------------------------------------------------------------------------
def replacements(conn, tr: pd.DataFrame) -> pd.DataFrame:
    sa = pd.read_sql_query("SELECT id, at, slot_id, action, strategy_key, version, reason FROM slot_assignments ORDER BY id", conn)
    link = run_map(conn)
    def rid(k, v):
        if k.startswith("paper:"):
            return k[6:]
        x = link[(link["strategy_key"] == k) & (link["version"] == v)]
        return x["run_id"].iloc[0] if len(x) else None
    rows = []
    for (at, slot), g in sa.groupby(["at", "slot_id"]):
        rel, asg = g[g["action"] == "RELEASE"], g[g["action"] == "ASSIGN"]
        if rel.empty or asg.empty or "replaced by" not in rel["reason"].iloc[0]:
            continue
        d = at[:10]
        out_id, in_id = rid(rel["strategy_key"].iloc[0], int(rel["version"].iloc[0])), rid(asg["strategy_key"].iloc[0], int(asg["version"].iloc[0]))
        def later(r):
            if not r:
                return np.nan, 0
            x = tr[(tr["run_id"] == r) & (tr["entry_date"] >= d)]
            return (float(x["net_pct"].mean()), len(x)) if len(x) else (np.nan, 0)
        o, on = later(out_id); i, inn = later(in_id)
        rows.append({"date": d, "slot": int(slot), "claimed": rel["reason"].iloc[0].split(": ", 1)[-1][:40],
                     "out_later": o, "out_n": on, "in_later": i, "in_n": inn})
    return pd.DataFrame(rows)


def outlier_dependence(conn, rh: pd.DataFrame, tr: pd.DataFrame) -> dict:
    """How much does each fund's mean depend on its single best trade, and how many funds share that trade?
    (The same ticker/date trade is recorded once per fund that signalled it.)"""
    t = pd.read_sql_query("SELECT run_id, ticker, entry_date, net_pct FROM paper_trades_restated WHERE version='v2_next_open'", conn)
    g = t.groupby("run_id")["net_pct"]
    n, mean, best = g.size(), g.mean(), g.max()
    wo = (g.sum() - best) / (n - 1).replace(0, np.nan)
    last = rh[rh["date"] == rh["date"].max()]
    top = last[(last["passes_gate"] == 1) & last["run_id"].notna()].sort_values("score", ascending=False).drop_duplicates("run_id").head(50)
    d = pd.DataFrame({"n": n, "mean": mean, "best": best, "without_best": wo}).reindex(top["run_id"]).dropna(subset=["n"])
    # the single largest trade overall and how many funds hold it
    big = t.sort_values("net_pct", ascending=False).head(1).iloc[0]
    sharing = t[(t["ticker"] == big["ticker"]) & (t["entry_date"] == big["entry_date"])]["run_id"].nunique()
    import slots
    from universe import load_config
    holders = []
    for sl, h in slots.current(conn, load_config()).items():
        if not h:
            continue
        link = run_map(conn)
        k = h["strategy_key"]
        rid = k[6:] if k.startswith("paper:") else (link[(link["strategy_key"] == k)]["run_id"].iloc[0] if (link["strategy_key"] == k).any() else None)
        if rid in n.index:
            holders.append({"slot": sl, "n": int(n[rid]), "mean": float(mean[rid]), "best": float(best[rid]),
                            "without_best": float(wo[rid]) if wo[rid] == wo[rid] else float("nan"),
                            "has_big": bool(((t["run_id"] == rid) & (t["ticker"] == big["ticker"]) & (t["entry_date"] == big["entry_date"])).any())})
    return {"top": d, "big": big.to_dict(), "sharing": int(sharing), "holders": pd.DataFrame(holders),
            "share_nonpositive_without_best": float((d["without_best"] <= 0).mean()) if len(d) else float("nan")}


def slot_churn(conn) -> dict:
    sa = pd.read_sql_query("SELECT at, slot_id, action, reason FROM slot_assignments", conn)
    rel = sa[sa["action"] == "RELEASE"]
    return {"releases": int(len(rel)), "by_ranking_swap": int(rel["reason"].str.contains("replaced by paper|replaced by fx").sum()),
            "by_owner": int(rel["reason"].str.contains("owner").sum()),
            "by_ineligible": int(rel["reason"].str.contains("no longer eligible").sum())}


# --- report ------------------------------------------------------------------------------------
def f(x, s="{:+.2f}"):
    return "n/a" if x is None or (isinstance(x, float) and np.isnan(x)) else s.format(x)


def build(conn) -> dict:
    rh, tr = history(conn), trades(conn)
    ev = evaluate(rh, tr)
    return {"formula": formula_check(conn, rh), "comp": top_composition(rh, entries(conn)), "eval": ev,
            "repl": replacements(conn, tr), "churn": slot_churn(conn), "outlier": outlier_dependence(conn, rh, tr),
            "dates": sorted(rh["date"].unique()), "funds_mapped": int(rh["run_id"].notna().sum())}


def render(o: dict, as_of: str) -> str:
    L = [f"# Phase B3: audit of the ranking formula", "",
         f"Computed {as_of}, read-only, from `ranking_history` ({len(o['dates'])} daily snapshots, {o['dates'][0]} to {o['dates'][-1]}) and "
         "`paper_trades_restated` (next-open fills, modelled costs deducted). Nothing here changes a live setting.", "",
         "## 1. Does production match the documented formula?", ""]
    fc = o["formula"]
    L += [f"Recomputed (10 x backtest + n x forward) / (10 + n) from the stored components for {fc['rows']:,} rows / {fc['strategies']:,} strategies. "
          f"The stored score divided by that blend is the hold-length factor 20 / max(hold, 5): stable per strategy across dates for {fc['ratio_stable_share']:.0%} of strategies; "
          f"median factor {fc['ratio_median']:.2f}, 10th to 90th percentile {fc['ratio_p10']:.2f} to {fc['ratio_p90']:.2f}; {fc['share_ratio_gt3']:.0%} of rows are scaled by more than 3x "
          "(short measured holds scale a noisy per-trade figure up by up to 4x, the floor being 5 sessions).",
          f"Production deviates from the documented \"starting at the backtest\": {fc['share_holdout_prior']:.0%} of rows use the 2023-to-today unseen-window result as the prior instead of the 2016-19 backtest "
          f"stored in `ranking_history.backtest`, and {fc['share_search_zero_prior']:.0%} are Lab-search funds whose prior is zero (paper evidence only). The stored `backtest` column is therefore not what scores.", "",
          "## 2. What the formula does with small and correlated samples", "",
          "Of the 50 best-scored gate-passing strategies on each date: median trades counted in `n` (closed plus open positions), share with fewer than 10, and the independent entry dates behind those trades (closed plus open, entered before the date).", "",
          "| date | median trades | share < 10 trades | median indep. dates | share < 5 dates |", "|---|---:|---:|---:|---:|"]
    for r in o["comp"].itertuples():
        L.append(f"| {r.date} | {f(r.median_trades, '{:.0f}')} | {f(r.share_trades_lt10, '{:.0%}')} | {f(r.median_indep_dates, '{:.0f}')} | {f(r.share_dates_lt5, '{:.0%}')} |")
    L += ["", "`n` in the formula is a trade count, so ten trades from two entry dates weigh as much against the backtest prior as ten trades from ten dates.", "",
          "## 3. Calibration and information value (chronological)", "",
          "Each daily snapshot is a prediction; the outcome is the mean honest net return of that strategy's trades entered on or after the snapshot date. "
          "A strategy needs >= 3 later trades to have an outcome. Funds recur across snapshots, so rows are not independent; the dates are only 1 to 11 sessions of outcome.", "",
          "| snapshot | funds | stored score rho | 10:n blend rho | backtest rho | forward rho | EB rho | pool mean realised % | top-5 by score % | top-5 by EB % |",
          "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|"]
    pdv = o["eval"]["per_date"]
    for r in pdv.itertuples():
        L.append(f"| {r.date} | {r.funds} | {f(r.score_rho)} | {f(r.blend_rho)} | {f(r.bt_only_rho)} | {f(r.fw_only_rho)} | {f(r.eb_rho)} | "
                 f"{f(r.realised_mean * 100)} | {f(r.score_top * 100)} | {f(r.eb_top * 100)} |")
    if len(pdv):
        L += ["", "| predictor | mean rank correlation over snapshots | snapshots with rho > 0 | mean realised % of its top 5 |", "|---|---:|---:|---:|"]
        for p, lab in (("score", "stored score"), ("blend", "10:n blend"), ("bt_only", "backtest only"), ("fw_only", "forward only"), ("eb", "empirical Bayes on dates")):
            col, tcol = pdv[p + "_rho"].dropna(), pdv.get(p + "_top")
            L.append(f"| {lab} | {f(col.mean(), '{:+.3f}')} | {int((col > 0).sum())} of {len(col)} | {f(tcol.mean() * 100 if tcol is not None else None)} |")
        L += ["", f"Pool mean realised: {f(pdv['realised_mean'].mean() * 100)} % per trade. The top-5 columns are the realised mean of the five best-scored gate-passing strategies at each snapshot "
              "(each snapshot a different mix; the same fund can appear on several)."]
    b = o["eval"]["bins"]
    if len(b):
        agg = b.groupby("bin").agg(predicted=("predicted", "mean"), realised=("realised", "mean"), snaps=("date", "nunique")).reset_index()
        L += ["", "Reliability, stored score in quintiles (mean over snapshots; predicted is per 20 sessions, realised is per trade):", "",
              "| quintile | predicted % | realised % | snapshots |", "|---:|---:|---:|---:|"]
        for r in agg.itertuples():
            L.append(f"| {r.bin} | {f(r.predicted * 100)} | {f(r.realised * 100)} | {r.snaps} |")
    ou = o["outlier"]
    L += ["", "## 3b. Dependence on a single shared trade", "",
          f"The largest honest trade in the restated record is {ou['big']['ticker']} entered {ou['big']['entry_date']} at {f(ou['big']['net_pct'])} % net, and it is recorded in "
          f"{ou['sharing']} different funds (a fund per rule that signalled it). Among the 50 best-scored gate-passing funds on {o['dates'][-1]}, "
          f"{ou['share_nonpositive_without_best']:.0%} have a mean at or below zero once their single best trade is removed.", "",
          "| slot | trades | honest mean % | best trade % | mean without best % | holds the shared big trade |", "|---:|---:|---:|---:|---:|---|"]
    for r in ou["holders"].itertuples():
        L.append(f"| {r.slot} | {r.n} | {f(r.mean)} | {f(r.best)} | {f(r.without_best)} | {'yes' if r.has_big else 'no'} |")
    L += ["", "## 4. Did the controlled replacements pick better strategies?", ""]
    rp = o["repl"]
    if len(rp):
        L += ["| date | slot | claimed | dropped: later trades | dropped: honest net % | added: later trades | added: honest net % |", "|---|---:|---|---:|---:|---:|---:|"]
        for r in rp.itertuples():
            L.append(f"| {r.date} | {r.slot} | {r.claimed} | {r.out_n} | {f(r.out_later)} | {r.in_n} | {f(r.in_later)} |")
        both = rp.dropna(subset=["out_later", "in_later"])
        if len(both):
            L += ["", f"{len(both)} swaps with outcomes for both sides: added strategy beat the dropped one in {int((both['in_later'] > both['out_later']).sum())}; "
                  f"mean difference {f((both['in_later'] - both['out_later']).mean())} points per trade."]
    ch = o["churn"]
    L += ["", f"Slot releases to date: {ch['releases']} (ranking swaps {ch['by_ranking_swap']}, ineligible {ch['by_ineligible']}, owner {ch['by_owner']}).",
          "", "## What could be wrong with this analysis", "",
          "- 1 to 11 sessions of outcome after each snapshot and one market regime: rank correlations of a few hundredths are noise.",
          "- The outcome is the paper fund's trades; the live slot trades the same rule with a stop plan and ATR sizing, so slot results can differ.",
          "- The restated table leaves out trades exiting on the newest bar (mostly stop-outs), which flatters every predictor equally but not necessarily the same.",
          "- The empirical-Bayes estimator is a candidate replacement evaluated on the same short window it was designed on; it is not adopted and nothing is tuned to it.",
          "- Only funds with a paper run are scored; crypto, pair, option and value funds are outside this calibration."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter).parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    now = datetime.now(timezone.utc)
    text = render(build(conn), now.strftime("%Y-%m-%d %H:%M UTC"))
    out = Path("reports") / f"audit_ranking_{now:%Y-%m-%d}.md"
    out.write_text(text)
    print(text)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
