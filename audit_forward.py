"""
Addendum F, Phase A1-A3: audit forward-positive families from the raw trade records.

Read-only. Recomputes each family's result from `paper_trades` (not from funnel.py's
output), checks what the percentage means, flags trades that span a corporate action,
removes duplicated observations, and recomputes uncertainty with methods that do not
assume the trades are independent. It decides nothing and changes nothing: the
classification printed is a mechanical provisional label for a human to review.

    ./venv/bin/python audit_forward.py                      # lab_search, momentum
    ./venv/bin/python audit_forward.py --reported           # the seven reported + turn_of_month
    ./venv/bin/python audit_forward.py --families a,b --out reports/x.md

What it found about the paper engine (verified against `paper_trading.py` and the data): a position is
entered at the CLOSE of the session that produced the signal and exits are booked at the close that
triggers them (entry price equals that day's close on ~99% of rows); `pnl_pct` is the GROSS price move,
not net of the modelled costs. The simulator and backtest use next-open fills since 2026-09-15; the paper
engine does not. The "honest fills" basis below re-prices each trade at the next session's open, from the
adjusted price series, minus the modelled round-trip cost.

Method notes
  iid t          mean / (sd / sqrt n): what funnel.py reports (sample sd here, population sd there)
  deduped        one observation per (ticker, entry_date): the mean over every fund that took it
  cluster t      standard error clustered by entry date (and by ticker), CR1 form; the smaller of
                 the two t-statistics is the one used for the label
  bootstrap      resample entry dates with replacement (fixed seed): 95% interval for the mean
  n_eff          n / design effect, design effect = (cluster SE / iid SE)^2
  luck threshold the level the maximum of N independent noise t-statistics exceeds 5% of the
                 time; N is uncertain (families 88 ... unique Lab structures 127,652)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import math
import sqlite3
import sys
from statistics import NormalDist

import numpy as np
import pandas as pd

from universe import load_config

REPORTED = ["lab_search", "momentum", "kf_seasonality", "st_uptrend_pullback", "bollinger_reversion",
            "kf_mean_reversion", "st_momentum_1d"]
EXTRA = ["turn_of_month"]
N_LUCK = {"88 families": 88, "1,405 specs": 1405, "127,652 Lab structures": 127652}
CA_THRESHOLD = 0.015         # |recorded close / adjusted close on that date - 1| above this = adjusted since the trade
MIN_DATE_CLUSTERS = 20       # fewer independent entry dates than this cannot support a label above 'unresolved'
BOOT = 4000
SEED = 20261013


# --- loading -------------------------------------------------------------------------
def load_trades(conn, family: str) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT t.run_id, t.ticker, t.entry_date, t.exit_date, t.entry_price, t.exit_price, t.shares,
                  t.gross_pnl_usd AS gross, t.costs_usd AS costs, t.net_pnl_usd AS net, t.pnl_pct,
                  t.exit_reason, r.created_at, r.capital_usd
           FROM paper_trades t JOIN paper_runs r ON r.run_id = t.run_id
           WHERE r.family = ? AND t.pnl_pct IS NOT NULL""", conn, params=(family,))
    return df


def attach_prices(conn, df: pd.DataFrame) -> pd.DataFrame:
    """Adjusted close on the entry / exit dates and the adjusted OPEN of the session after each."""
    out = df.copy()
    for c in ("close_entry", "close_exit", "open_next_entry", "open_next_exit"):
        out[c] = np.nan
    if out.empty:
        return out
    lo = min(out["entry_date"].min(), out["exit_date"].min())
    for tk, idx in out.groupby("ticker").groups.items():
        p = pd.read_sql_query("SELECT date, open, close FROM prices WHERE ticker = ? AND date >= ? ORDER BY date",
                              conn, params=(tk, lo))
        if p.empty:
            continue
        pos = {d: i for i, d in enumerate(p["date"])}
        for i in idx:
            ie, ix = pos.get(out.at[i, "entry_date"]), pos.get(out.at[i, "exit_date"])
            if ie is not None:
                out.at[i, "close_entry"] = p["close"].iat[ie]
                if ie + 1 < len(p):
                    out.at[i, "open_next_entry"] = p["open"].iat[ie + 1]
            if ix is not None:
                out.at[i, "close_exit"] = p["close"].iat[ix]
                if ix + 1 < len(p):
                    out.at[i, "open_next_exit"] = p["open"].iat[ix + 1]
    return out


# --- pure statistics (tested) -----------------------------------------------------------
def iid_stats(x) -> dict:
    x = np.asarray(x, dtype=float)
    n = len(x)
    if n < 3:
        return {"n": n, "mean": float(x.mean()) if n else float("nan"), "sd": float("nan"), "t": float("nan")}
    sd = float(x.std(ddof=1))
    se = sd / math.sqrt(n)
    return {"n": n, "mean": float(x.mean()), "sd": sd, "se": se, "t": float(x.mean() / se) if se else float("nan")}


def cluster_stats(x, groups) -> dict:
    """CR1 cluster-robust standard error of a mean; t with G-1 degrees of freedom noted."""
    x = np.asarray(x, dtype=float)
    g = pd.Series(groups).reset_index(drop=True)
    n = len(x)
    G = g.nunique()
    m = x.mean()
    s = pd.Series(x - m).groupby(g).sum()
    var = (G / (G - 1)) * float((s ** 2).sum()) / (n ** 2) if G > 1 else float("nan")
    se = math.sqrt(var) if var == var and var > 0 else float("nan")
    return {"clusters": int(G), "se": se, "t": float(m / se) if se == se and se else float("nan")}


def dedupe(df: pd.DataFrame, keys=("ticker", "entry_date")) -> pd.DataFrame:
    """One observation per key: mean return over every fund that took it, plus how many did."""
    return df.groupby(list(keys), as_index=False).agg(pnl_pct=("pnl_pct", "mean"), funds=("run_id", "nunique"),
                                                       rows=("pnl_pct", "size"))


def bootstrap_by_cluster(x, groups, reps=BOOT, seed=SEED) -> dict:
    """Resample whole clusters (entry dates) with replacement; interval for the mean and P(mean <= 0)."""
    x = np.asarray(x, dtype=float)
    g = pd.Series(groups).reset_index(drop=True)
    sums = pd.Series(x).groupby(g).sum().to_numpy()
    cnts = pd.Series(x).groupby(g).size().to_numpy()
    rng = np.random.default_rng(seed)
    idx = rng.integers(0, len(sums), size=(reps, len(sums)))
    means = sums[idx].sum(axis=1) / cnts[idx].sum(axis=1)
    return {"lo": float(np.percentile(means, 2.5)), "hi": float(np.percentile(means, 97.5)),
            "p_le_zero": float((means <= 0).mean())}


def luck_threshold(n_tests: int, level: float = 0.95) -> float:
    """t that the maximum of n_tests independent standard-normal statistics exceeds with prob 1 - level."""
    return NormalDist().inv_cdf(level ** (1.0 / n_tests))


def classify(t_cluster: float, ci_lo: float, date_clusters: int) -> str:
    """Mechanical, provisional. Never returns an 'eligible' or 'supported' label: that needs a human."""
    if not (t_cluster == t_cluster):
        return "Unresolved (cannot compute)"
    if date_clusters < MIN_DATE_CLUSTERS:
        return f"Unresolved: only {date_clusters} independent entry dates (need {MIN_DATE_CLUSTERS}+)"
    if t_cluster < 2.0 or ci_lo <= 0:
        return "Unresolved: not significant after the dependence correction"
    if t_cluster < luck_threshold(88):
        return "Unresolved: significant, but inside the range luck produces among 88 families"
    return "Promising but unproven: survives dependence and the 88-family luck bar"


def corporate_action_flag(df: pd.DataFrame, thr: float = CA_THRESHOLD) -> pd.Series:
    """The engine records the close it saw; the prices table is back-adjusted later. A gap means an adjustment."""
    re = (df["entry_price"] / df["close_entry"] - 1).abs()
    rx = (df["exit_price"] / df["close_exit"] - 1).abs()
    return ((re > thr) | (rx > thr)).fillna(False)


# --- one family ---------------------------------------------------------------------------
def _stats_block(b: pd.DataFrame, col: str) -> dict:
    x = b[col]
    iid = iid_stats(x)
    dd = dedupe(b.assign(pnl_pct=x))
    cd = cluster_stats(x, b["entry_date"])
    ct = cluster_stats(x, b["ticker"])
    boot = bootstrap_by_cluster(x, b["entry_date"])
    deff = (cd["se"] / iid["se"]) ** 2 if iid.get("se") and cd["se"] == cd["se"] else float("nan")
    return {"iid": iid, "deduped_by_ticker_entry": iid_stats(dd["pnl_pct"]), "cluster_date": cd, "cluster_ticker": ct,
            "bootstrap_date": boot, "design_effect": deff,
            "n_eff": iid["n"] / deff if deff == deff and deff else float("nan")}


def audit_family(conn, family: str) -> dict:
    raw = load_trades(conn, family)
    if raw.empty:
        return {"family": family, "n": 0}
    d = attach_prices(conn, raw)
    d["notional"] = d["entry_price"] * d["shares"]
    d["cost_pct"] = d["costs"] / d["notional"] * 100
    d["gross_calc"] = (d["exit_price"] / d["entry_price"] - 1) * 100
    d["net_calc"] = d["net"] / d["notional"] * 100
    d["flag_ca"] = corporate_action_flag(d)
    d["r_gross_sameclose"] = d["pnl_pct"]
    d["r_net_sameclose"] = d["pnl_pct"] - d["cost_pct"]
    d["r_net_honest"] = (d["open_next_exit"] / d["open_next_entry"] - 1) * 100 - d["cost_pct"]
    honest = d.dropna(subset=["r_net_honest"]).copy()
    out = {"family": family, "n": int(len(d)), "funds": int(d["run_id"].nunique()),
           "opportunities": int(d.drop_duplicates(["ticker", "entry_date"]).shape[0]),
           "tickers": int(d["ticker"].nunique()), "entry_dates": int(d["entry_date"].nunique()),
           "first_entry": d["entry_date"].min(), "last_exit": d["exit_date"].max()}
    out["dup_factor"] = out["n"] / out["opportunities"]
    out["pnl_pct_matches_net"] = float(((d["pnl_pct"] - d["net_calc"]).abs() < 0.02).mean())
    out["pnl_pct_matches_gross"] = float(((d["pnl_pct"] - d["gross_calc"]).abs() < 0.02).mean())
    out["costs_pct_mean"] = float(d["cost_pct"].mean())
    out["notional_min_med_max"] = [float(d["notional"].min()), float(d["notional"].median()), float(d["notional"].max())]
    out["entry_equals_close"] = float(((d["entry_price"] / d["close_entry"] - 1).abs() < 0.002).mean())
    out["exit_equals_close"] = float(((d["exit_price"] / d["close_exit"] - 1).abs() < 0.002).mean())
    out["ca_flagged"] = int(d["flag_ca"].sum())
    out["ca_flagged_tickers"] = sorted(d.loc[d["flag_ca"], "ticker"].unique().tolist())[:12]
    out["honest_rows"] = int(len(honest))
    out["bases"] = {
        "A. as reported: GROSS, same-close fills, all rows": _stats_block(d, "r_gross_sameclose"),
        "B. net of modelled costs, same-close fills, all rows": _stats_block(d, "r_net_sameclose"),
        "C. net, same-close fills, rows that have a next-open price": _stats_block(honest, "r_net_sameclose") if len(honest) > 5 else None,
        "D. net, NEXT-OPEN fills on adjusted prices, same rows as C": _stats_block(honest, "r_net_honest") if len(honest) > 5 else None,
    }
    dd = out["bases"]["D. net, NEXT-OPEN fills on adjusted prices, same rows as C"]
    if dd:
        cl = [x for x in (dd["cluster_date"]["t"], dd["cluster_ticker"]["t"]) if x == x]
        out["t_cluster_min"] = min(cl) if cl else float("nan")
        out["classification"] = classify(out["t_cluster_min"], dd["bootstrap_date"]["lo"], dd["cluster_date"]["clusters"])
    else:
        out["t_cluster_min"] = float("nan")
        out["classification"] = "Unresolved (no rows with a next-open price)"
    dates = sorted(d["entry_date"].unique())
    half = dates[len(dates) // 2] if dates else None
    out["halves"] = {"split_date": half,
                     "first": iid_stats(d.loc[d["entry_date"] < half, "r_net_sameclose"]),
                     "second": iid_stats(d.loc[d["entry_date"] >= half, "r_net_sameclose"])}
    d["cohort"] = np.where(d["created_at"].str[:10] <= "2026-09-26", "funds created on or before 09-26", "funds created after 09-26")
    out["cohorts"] = {k: iid_stats(v["r_net_sameclose"]) for k, v in d.groupby("cohort")}
    out["exit_reasons"] = d["exit_reason"].value_counts().head(5).to_dict()
    return out


# --- report --------------------------------------------------------------------------------
def fnum(x, f="{:+.2f}"):
    return "n/a" if x is None or x != x else f.format(x)


def render(results: list, funnel_rows: dict, as_of: str) -> str:
    L = ["# Forward-family audit (Addendum F, Phase A1-A3)", "",
         f"Computed {as_of} UTC from `paper_trades` / `paper_runs` / `prices`, read-only. "
         "Provisional labels are mechanical; the verdict (A6) is a human decision.", "",
         "**Two findings about the paper engine come first** (verified in `paper_trading.py` and in the rows below): "
         "(1) entries are priced at the CLOSE of the signal session and exits at the close that triggers them, not at the next open "
         "(the simulator and backtest were fixed to next-open on 2026-09-15; the paper engine was not); (2) `pnl_pct`, which the funnel "
         "and the dossier call net, is the GROSS price move: modelled costs are stored but not deducted from it.", "",
         "## Summary (basis D unless stated)", "",
         "| family | trades | funds | unique entries | dup factor | funnel t (iid, gross, same-close) | t after costs + next-open fills (iid) | cluster t D: date / ticker | independent entry dates | n_eff | mean D | 95% boot CI D | provisional label |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|"]
    K = ("A. as reported: GROSS, same-close fills, all rows", "B. net of modelled costs, same-close fills, all rows",
         "C. net, same-close fills, rows that have a next-open price", "D. net, NEXT-OPEN fills on adjusted prices, same rows as C")
    for r in results:
        if r["n"] == 0:
            L.append(f"| {r['family']} | 0 | | | | | | | | | | | no trades |")
            continue
        dd = r["bases"][K[3]]
        f = funnel_rows.get(r["family"])
        if not dd:
            L.append(f"| {r['family']} | {r['n']:,} | | | | | | | | | | | {r['classification']} |")
            continue
        L.append(f"| {r['family']} | {r['n']:,} | {r['funds']} | {r['opportunities']:,} | {r['dup_factor']:.2f} | "
                 f"{fnum(f['t_stat'], '{:+.1f}') if f else 'n/a'} | {fnum(dd['iid']['t'], '{:+.1f}')} | "
                 f"{fnum(dd['cluster_date']['t'], '{:+.1f}')} / {fnum(dd['cluster_ticker']['t'], '{:+.1f}')} | "
                 f"{dd['cluster_date']['clusters']} | {dd['n_eff']:.0f} | {fnum(dd['iid']['mean'])}% | "
                 f"[{fnum(dd['bootstrap_date']['lo'])}%, {fnum(dd['bootstrap_date']['hi'])}%] | {r['classification']} |")
    L += ["", "Noise-only luck thresholds for the largest of N independent t-statistics (95%): " +
          ", ".join(f"N={v:,} ({k}): {luck_threshold(v):.2f}" for k, v in N_LUCK.items()) + ".",
          f"A label above 'unresolved' also needs at least {MIN_DATE_CLUSTERS} independent entry dates.", ""]
    for r in results:
        if r["n"] == 0:
            continue
        L += [f"## {r['family']}", "",
              f"- Rows {r['n']:,} from {r['funds']} funds; {r['opportunities']:,} distinct (ticker, entry date) opportunities "
              f"(each taken by {r['dup_factor']:.2f} funds on average); {r['tickers']} tickers; {r['entry_dates']} entry dates "
              f"({r['first_entry']} to last exit {r['last_exit']}).",
              f"- What `pnl_pct` is: equals the gross price move on {100 * r['pnl_pct_matches_gross']:.1f}% of rows and net P&L / notional on "
              f"{100 * r['pnl_pct_matches_net']:.1f}%. Mean modelled cost {r['costs_pct_mean']:.3f}% of notional per round trip. "
              f"Notional min / median / max ${r['notional_min_med_max'][0]:.2f} / ${r['notional_min_med_max'][1]:.2f} / ${r['notional_min_med_max'][2]:.2f}.",
              f"- Entry price equals that day's close on {100 * r['entry_equals_close']:.1f}% of rows; exit price equals that day's close on "
              f"{100 * r['exit_equals_close']:.1f}%.",
              f"- Corporate-action check (recorded entry or exit price more than {100 * CA_THRESHOLD:.1f}% from the adjusted close on that date): "
              f"**{r['ca_flagged']} rows**" + (f", tickers {', '.join(r['ca_flagged_tickers'])}." if r['ca_flagged'] else "."),
              f"- {r['honest_rows']:,} of {r['n']:,} rows have a next-session open for both legs (trades exiting on the last stored bar do not).", ""]
        L += ["| basis | n | mean % | sd % | iid t | deduped (ticker, entry): mean / t / n | cluster t: date (G) | cluster t: ticker (G) | design effect | n_eff | bootstrap 95% | P(mean<=0) |",
              "|---|---:|---:|---:|---:|---|---|---|---:|---:|---|---:|"]
        for label, s_ in r["bases"].items():
            if not s_:
                continue
            i, dd_, cd, ct, bt = s_["iid"], s_["deduped_by_ticker_entry"], s_["cluster_date"], s_["cluster_ticker"], s_["bootstrap_date"]
            L.append(f"| {label} | {i['n']:,} | {fnum(i['mean'])} | {fnum(i['sd'], '{:.2f}')} | {fnum(i['t'], '{:+.1f}')} | "
                     f"{fnum(dd_['mean'])} / {fnum(dd_['t'], '{:+.1f}')} / {dd_['n']:,} | {fnum(cd['t'], '{:+.1f}')} ({cd['clusters']}) | "
                     f"{fnum(ct['t'], '{:+.1f}')} ({ct['clusters']}) | {fnum(s_['design_effect'], '{:.1f}')} | {fnum(s_['n_eff'], '{:.0f}')} | "
                     f"[{fnum(bt['lo'])}, {fnum(bt['hi'])}] | {bt['p_le_zero']:.3f} |")
        h = r["halves"]
        L += ["", f"- Stability (net, same-close): entries before {h['split_date']}: mean {fnum(h['first']['mean'])}% (n {h['first']['n']:,}); "
              f"on or after: {fnum(h['second']['mean'])}% (n {h['second']['n']:,}).",
              "- Fund cohorts (net, same-close): " + "; ".join(f"{k}: mean {fnum(v['mean'])}% (n {v['n']:,})" for k, v in r["cohorts"].items()) + ".",
              f"- Exit reasons: {r['exit_reasons']}.", f"- **Provisional label:** {r['classification']}", ""]
    L += ["## What could be wrong with this audit", "",
          "- The window is about 16 sessions of one market; any family's mean can move with the next week of trades, and the entry dates "
          "are too few to treat as independent draws of the market.",
          "- Basis D uses the adjusted price series for both legs, which also corrects spin-offs and splits; a dividend adjustment "
          "is small but not zero. Next-open prices are the best available proxy for a real fill, not a fill.",
          "- Clustering by entry date or ticker handles a shared market move and repeated tickers, not every dependence "
          "(overlapping holds, correlated strategies on different tickers).",
          "- The modelled round-trip cost (about 0.15-0.18% of notional) is the engine's own number, not measured fills.",
          "- Luck thresholds assume independent tests and a known N; both are uncertain.",
          "- The funnel's t is the same formula as the iid column here; differences between them are a different data snapshot."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--families", help="comma-separated; default lab_search,momentum")
    ap.add_argument("--reported", action="store_true", help="the seven reported families plus turn_of_month")
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    fams = REPORTED + EXTRA if a.reported else (a.families.split(",") if a.families else ["lab_search", "momentum"])
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    import funnel
    funnel_rows = {f["family"]: f for f in funnel.forward_families(conn)}
    conn.row_factory = None
    res = [audit_family(conn, f) for f in fams]
    now = dt.datetime.now(dt.timezone.utc)
    md = render(res, funnel_rows, now.strftime("%Y-%m-%d %H:%M"))
    out = a.out or f"reports/audit_forward_{now.strftime('%Y-%m-%d')}.md"
    with open(out, "w") as fh:
        fh.write(md)
    with open(out.replace(".md", ".json"), "w") as fh:
        json.dump(res, fh, indent=1, default=str)
    print(md)
    print(f"wrote {out} and {out.replace('.md', '.json')}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
