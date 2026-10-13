"""
Addendum F, Phase A4-A5: multiple testing across families and the enrollment event. Read-only.

A4  How many things were looked at, and which count applies to which claim.
    - Family level (the 43 families with >= 20 closed paper trades): per-family one-sided p from a Student t on the
      date-clustered mean (df = independent entry dates - 1), Holm and Benjamini-Hochberg adjusted, a max-T sign-flip
      test that keeps the dependence between families, and the effective number of independent tests (Nyholt) from the
      correlation of per-date family returns. Run on the honest basis (net of costs, next-open fills, restated trades)
      and on the same returns minus SPY over the same holding window, because a long-only family makes money in a
      rising market without any edge.
    - The Lab's 1.05M trials bound the BACKTEST evidence of the survivors. The forward window is a fresh sample for
      strategies fixed before it started, so the count that applies to a forward family-level claim is the number of
      families compared (43 here, 88 defined), not the search count. Picking the best fund inside a family would bring
      the large count back.
A5  The enrollment event. Lab survivors were enrolled 2026-09-27 and the funds were started on 2026-09-24 (LIVE start): trades
    dated before the first completed session at creation are a replay, not forward. Their share, and how each family's
    result changes when they are removed, are reported.

    ./venv/bin/python audit_selection.py [--out reports/audit_selection_<date>.md]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import sqlite3
import sys

import numpy as np
import pandas as pd

import forward_stats as fs
from universe import load_config

HIGHLIGHTED = ["lab_search", "momentum", "kf_seasonality", "st_uptrend_pullback", "bollinger_reversion",
               "kf_mean_reversion", "st_momentum_1d", "turn_of_month"]
MIN_TRADES = 20
MIN_DATES_FOR_TEST = 5
SPY = "SPY"


# --- data ------------------------------------------------------------------------------------
def load(conn) -> pd.DataFrame:
    df = pd.read_sql_query(
        """SELECT p.family, x.run_id, x.ticker, x.entry_date, x.exit_date, x.net_pct, x.gross_pct, x.cost_pct,
                  substr(p.created_at, 1, 10) AS created
           FROM paper_trades_restated x JOIN paper_runs p ON p.run_id = x.run_id
           WHERE x.version = 'v2_next_open' AND p.family IS NOT NULL""", conn)
    return df


def sessions(conn) -> list:
    return [r[0] for r in conn.execute("SELECT date FROM prices WHERE ticker = ? ORDER BY date", (SPY,))]


def add_spy(conn, df: pd.DataFrame, sess: list) -> pd.DataFrame:
    """SPY's return between the same two next-session opens each trade was restated on; excess = net - SPY."""
    op = pd.read_sql_query("SELECT date, open FROM prices WHERE ticker = ? ORDER BY date", conn, params=(SPY,)).set_index("date")["open"]
    pos = {d: i for i, d in enumerate(sess)}
    nxt = lambda d: sess[pos[d] + 1] if d in pos and pos[d] + 1 < len(sess) else None
    e = df["entry_date"].map(nxt)
    x = df["exit_date"].map(nxt)
    df = df.assign(spy_pct=(x.map(op) / e.map(op) - 1) * 100)
    df["excess_pct"] = df["net_pct"] - df["spy_pct"]
    return df


def retro_flag(df: pd.DataFrame, sess: list) -> pd.DataFrame:
    """Retroactive = entered before the last completed session on or before the fund's creation date."""
    arr = np.array(sess)
    first_ok = {}
    for c in df["created"].unique():
        i = np.searchsorted(arr, c, side="right") - 1
        first_ok[c] = arr[i] if i >= 0 else c
    return df.assign(first_session=df["created"].map(first_ok), retro=lambda d: d["entry_date"] < d["first_session"])


# --- per-family tests ----------------------------------------------------------------------
def family_row(g: pd.DataFrame, col: str) -> dict:
    x = g[col].dropna()
    g = g.loc[x.index]
    if len(x) < 3:
        return {"n": len(x), "dates": 0, "mean": float("nan"), "t": float("nan"), "df": 0, "p": float("nan")}
    cd, ct = fs.cluster_stats(x, g["entry_date"]), fs.cluster_stats(x, g["ticker"])
    cands = [v for v in (cd["t"], ct["t"]) if v == v]
    t = min(cands) if cands else float("nan")
    dates = int(cd["clusters"])
    return {"n": int(len(x)), "dates": dates, "mean": float(x.mean()), "t": t, "df": dates - 1,
            "p": fs.t_pvalue_one_sided(t, dates - 1)}


def family_table(df: pd.DataFrame, col: str) -> pd.DataFrame:
    rows = []
    for fam, g in df.groupby("family"):
        if len(g) >= MIN_TRADES:
            rows.append({"family": fam, **family_row(g, col)})
    t = pd.DataFrame(rows).set_index("family")
    ok = t["dates"] >= MIN_DATES_FOR_TEST
    p = t["p"].where(ok)
    t["p_holm"] = fs.holm(p.tolist())
    t["q_bh"] = fs.benjamini_hochberg(p.tolist())
    return t


def date_matrix(df: pd.DataFrame, col: str, fams: list) -> pd.DataFrame:
    return (df[df["family"].isin(fams)].pivot_table(index="entry_date", columns="family", values=col, aggfunc="mean"))


def effective_tests(dm: pd.DataFrame, min_common: int = 6) -> dict:
    cols = list(dm.columns)
    m = len(cols)
    C = np.eye(m)
    vals = []
    for i in range(m):
        for j in range(i + 1, m):
            both = dm.iloc[:, [i, j]].dropna()
            if len(both) >= min_common and both.iloc[:, 0].std() > 0 and both.iloc[:, 1].std() > 0:
                r = float(both.corr().iloc[0, 1])
                C[i, j] = C[j, i] = r
                vals.append(r)
    return {"families": m, "median_pairwise_corr": float(np.median(vals)) if vals else float("nan"),
            "n_pairs": len(vals), "meff": fs.nyholt_meff(C)}


# --- report ---------------------------------------------------------------------------------
def f(x, spec="{:+.2f}"):
    return "n/a" if x is None or x != x else spec.format(x)


def build(conn) -> dict:
    sess = sessions(conn)
    df = retro_flag(add_spy(conn, load(conn), sess), sess)
    out = {"rows": int(len(df)), "families": int(df["family"].nunique())}
    pro = df[~df["retro"]]
    out["retro_rows"] = int(df["retro"].sum())
    out["tables"] = {}
    for label, d in (("all restated trades", df), ("prospective trades only (retroactive replay removed)", pro)):
        out["tables"][label] = {"abs": family_table(d, "net_pct"), "exc": family_table(d, "excess_pct")}
    fams = [k for k, g in pro.groupby("family") if len(g) >= MIN_TRADES]
    out["maxT"] = {}
    out["meff"] = {}
    for col in ("net_pct", "excess_pct"):
        dm = date_matrix(pro, col, fams)
        out["maxT"][col] = fs.maxt_signflip(dm)
        out["meff"][col] = effective_tests(dm)
    out["noise"] = {n: (fs.luck_threshold(n), ) for n in (43, 88, 1405)}
    # A5: retro vs prospective per highlighted family, and the lab_search day-by-day table
    a5 = []
    for fam in HIGHLIGHTED:
        g = df[df["family"] == fam]
        if g.empty:
            continue
        r, p = g[g["retro"]], g[~g["retro"]]
        a5.append({"family": fam, "n": len(g), "retro_n": len(r), "retro_share": len(r) / len(g),
                   "retro_mean": r["net_pct"].mean() if len(r) else float("nan"),
                   "pro_n": len(p), "pro_mean": p["net_pct"].mean() if len(p) else float("nan"),
                   "pro_dates": p["entry_date"].nunique(), "created": ", ".join(sorted(g["created"].unique())[:3]),
                   "pro_exc_mean": p["excess_pct"].mean() if len(p) else float("nan")})
    out["a5"] = pd.DataFrame(a5)
    ls = df[df["family"] == "lab_search"].groupby("entry_date").agg(n=("net_pct", "size"), net=("net_pct", "mean"),
                                                                     spy=("spy_pct", "mean"), retro=("retro", "max"))
    out["lab_by_date"] = ls
    out["spy_window"] = (sess[0], sess[-1])
    return out


def render(o: dict, counter: dict, as_of: str) -> str:
    L = [f"# Phase A4-A5: multiple testing and the enrollment event", "",
         f"Computed {as_of} UTC, read-only, from `paper_trades_restated` (next-open fills, net of modelled costs) joined to "
         f"`paper_runs` and SPY. {o['rows']:,} restated trades, {o['families']} families; {o['retro_rows']:,} trades "
         f"({100 * o['retro_rows'] / o['rows']:.1f}%) are a retroactive replay (see A5).", "",
         "## A4. What was looked at, and which count applies", "",
         "| quantity | value | applies to |", "|---|---:|---|",
         f"| Lab search trials (append-only counter) | {counter['total_trials']:,} | backtest evidence of the Lab survivors |",
         f"| unique Lab structures | {counter['unique_structures']:,} | same, structural dedupe |",
         f"| effective Lab trials (project estimate, between the two) | {counter['effective_trials']:,} | same |",
         "| factory / knowledge specs | 1,405 | backtest evidence of factory families |",
         "| families defined | 88 | the pool the funnel draws its forward families from |",
         f"| families with >= {MIN_TRADES} closed forward trades | {len(o['tables']['all restated trades']['abs'])} | the family-level forward comparison |",
         "", "The forward window is a fresh sample for strategies fixed before it began, so a forward family-level claim "
         "is corrected for the number of families compared, not for the Lab's trial count. (An earlier note in this "
         "project said `lab_search`'s relevant luck level was the Lab's 4.4-4.9; that applies only if a best fund inside "
         "the family were picked after the fact.) Noise-only 95% t for the best of N independent tests: "
         + ", ".join(f"N={n}: {v[0]:.2f}" for n, v in o["noise"].items()) + ".", ""]
    for col, name in (("net_pct", "absolute honest net return"), ("excess_pct", "honest net return minus SPY over the same window")):
        mt, me = o["maxT"][col], o["meff"][col]
        L += [f"### Effective number of independent family tests ({name}, prospective trades)", "",
              f"{me['families']} families, median pairwise correlation of per-date returns {f(me['median_pairwise_corr'], '{:+.2f}')} "
              f"over {me['n_pairs']} pairs, Nyholt effective tests **{me['meff']:.1f}**. (Correlations rest on 5-19 shared dates: indicative.)", ""]
    for tab_name, tabs in o["tables"].items():
        for col, key, name in (("net_pct", "abs", "absolute honest net"), ("excess_pct", "exc", "excess over SPY")):
            t = tabs[key].copy()
            mt = o["maxT"][col] if tab_name.startswith("prospective") else None
            L += [f"### {name}; {tab_name}", "",
                  "| family | trades | independent dates | mean % | cluster t | df | p (one-sided) | Holm | BH q |" +
                  (" max-T adj p |" if mt is not None else ""),
                  "|---|---:|---:|---:|---:|---:|---:|---:|---:|" + ("---:|" if mt is not None else "")]
            order = [x for x in HIGHLIGHTED if x in t.index] + [x for x in t.sort_values("p").index if x not in HIGHLIGHTED][:6]
            for fam in order:
                r = t.loc[fam]
                extra = f" {f(mt.loc[fam, 'p_maxT'], '{:.3f}')} |" if mt is not None and fam in mt.index else (" |" if mt is not None else "")
                L.append(f"| {fam} | {int(r['n']):,} | {int(r['dates'])} | {f(r['mean'])} | {f(r['t'], '{:+.1f}')} | {int(r['df'])} | "
                         f"{f(r['p'], '{:.3f}')} | {f(r['p_holm'], '{:.3f}')} | {f(r['q_bh'], '{:.3f}')} |" + extra)
            L.append("")
    L += ["## A5. The enrollment event", "",
          "Lab survivors were enrolled on 2026-09-27 with their start date set to 2026-09-24 (the LIVE start). The paper engine "
          "entered the 09-24 signals at the 09-24 close when the funds were created, three days after the fact. Those entries "
          "use only data through 09-24 (no feature look-ahead), and the survivor list was fixed by the 2020-2022 validation "
          "gate, not by anything after 09-24; but the trades are a replay and the funds were created knowing the outcome window. "
          "Trades dated before the first completed session on or before the fund's creation date are flagged retroactive.", "",
          "| family | funds created | trades | retroactive | retro share | retro mean % | prospective trades | prospective dates | prospective mean % | prospective mean minus SPY % |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in o["a5"].iterrows():
        L.append(f"| {r['family']} | {r['created']} | {int(r['n']):,} | {int(r['retro_n']):,} | {100 * r['retro_share']:.1f}% | {f(r['retro_mean'])} | "
                 f"{int(r['pro_n']):,} | {int(r['pro_dates'])} | {f(r['pro_mean'])} | {f(r['pro_exc_mean'])} |")
    L += ["", "### lab_search by entry date (honest net %, SPY over the same windows)", "",
          "| entry date | trades | mean net % | mean SPY % | retroactive |", "|---|---:|---:|---:|---|"]
    for d, r in o["lab_by_date"].iterrows():
        L.append(f"| {d} | {int(r['n']):,} | {f(r['net'])} | {f(r['spy'])} | {'yes' if r['retro'] else ''} |")
    L += ["", "## What could be wrong with this analysis", "",
          "- 5-19 independent entry dates in one market regime: t-distribution p-values with 4-18 degrees of freedom are fragile, "
          "and a family-level correlation from the same few dates is a rough guide only.",
          "- The max-T sign-flip null assumes per-date family means are symmetric about zero; an absolute-return null is rejected "
          "by market drift alone, which is why the excess-over-SPY version is shown. SPY is a crude benchmark for a stock-picking "
          "family (beta and sector are not removed).",
          "- 'Retroactive' uses the last completed session at creation; a fund created before the open could be argued either way "
          "by one session.",
          "- The restated table excludes trades that exit on the newest stored bar (mostly stop-outs), which flatters every family "
          "until those trades can be restated.",
          "- Choosing which families to test (families with >= 20 trades) is itself a data-dependent choice."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=None)
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    import multiple_testing as mt
    counter = dict(mt.count(conn))
    conn.row_factory = None
    o = build(conn)
    now = dt.datetime.now(dt.timezone.utc)
    md = render(o, counter, now.strftime("%Y-%m-%d %H:%M"))
    out = a.out or f"reports/audit_selection_{now.strftime('%Y-%m-%d')}.md"
    with open(out, "w") as fh:
        fh.write(md)
    print(md)
    print(f"wrote {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
