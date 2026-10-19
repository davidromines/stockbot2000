"""
External benchmark (Stage AD8.1): does our pipeline reproduce published factor portfolios?

Rebuilds two Jensen-Kelly-Pedersen (JKP) factors from OUR prices and point-in-time fundamentals, monthly, and compares
them with the JKP return series already in `published_returns` (US, CRSP-based, dead companies included):

    ret_12_1   price 1 month ago / price 12 months ago - 1             (momentum, Jegadeesh-Titman formation)
    be_me      book-to-market as known at the month end (daily_fundamentals, point in time)

Each month end: terciles of the signal among our eligible stocks, equal-weighted next-month returns of the top (pf3) and
bottom (pf1) terciles, and the spread pf3 - pf1. The comparison that matters is the SPREAD: raw tercile returns
correlate highly with any portfolio of stocks through the market alone, so a high pf3 correlation proves little; a high
spread correlation means our signal ranks stocks the way the published one does.

Known deviations from JKP (stated, not fixed): our universe is the stocks we hold prices for (survivors over-represented,
dead companies mostly missing), common stock >= $5 with >= $1M/day at formation instead of JKP's CRSP universe and NYSE
breakpoints; equal weights only; month-end closes on adjusted prices. Pass mark (pre-stated, Stage AD8): spread
correlation >= 0.9 = faithful; 0.6-0.9 = partial (investigate); < 0.6 = our implementation differs materially. LEAN or
any other engine is considered only if a gap cannot be explained (owner H8, 2026-10-19).

    ./run_bounded.sh ./venv/bin/python external_benchmark.py [--start 2010-01 --end 2024-12] [--write]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd

from universe import load_config

ROOT = Path(__file__).resolve().parent
SIGNALS = ("ret_12_1", "be_me")


def month_ends(conn, start: str, end: str) -> list:
    d = pd.read_sql("SELECT date FROM prices WHERE ticker='SPY' AND date >= ? AND date <= ? ORDER BY date", conn,
                    params=(start, end))["date"]
    s = pd.Series(pd.to_datetime(d.values), index=d.values)
    return list(s.groupby([s.dt.year, s.dt.month]).apply(lambda x: x.index[-1]))


def load_month_end_panel(conn, dates: list) -> pd.DataFrame:
    """ticker, date, close, dollar_volume_20 at each month end, common stock only."""
    q = ",".join("?" * len(dates))
    px = pd.read_sql(f"SELECT p.ticker, p.date, p.close FROM prices p JOIN symbols s ON s.ticker=p.ticker "
                     f"WHERE s.security_type='common_stock' AND (s.data_quality IS NULL OR s.data_quality='') "
                     f"AND p.date IN ({q})", conn, params=dates)
    dv = pd.read_sql(f"SELECT ticker, date, dollar_volume_20 FROM features WHERE date IN ({q})", conn, params=dates)
    return px.merge(dv, on=["ticker", "date"], how="left")


def attach_bm(conn, panel: pd.DataFrame, dates: list) -> pd.DataFrame:
    q = ",".join("?" * len(dates))
    bm = pd.read_sql(f"SELECT ticker, date, book_to_market FROM daily_fundamentals WHERE date IN ({q})", conn, params=dates)
    return panel.merge(bm, on=["ticker", "date"], how="left")


def signals(panel: pd.DataFrame) -> pd.DataFrame:
    """Adds ret_12_1, be_me and the next-month return. Months are the panel's own month-end dates, in order."""
    p = panel.sort_values(["ticker", "date"]).copy()
    g = p.groupby("ticker")["close"]
    p["lag1"], p["lag12"], p["next"] = g.shift(1), g.shift(12), g.shift(-1)
    p["ret_12_1"] = p["lag1"] / p["lag12"] - 1
    p["be_me"] = p.get("book_to_market")
    p["fwd"] = p["next"] / p["close"] - 1
    return p


def terciles(p: pd.DataFrame, signal: str, min_price: float = 5.0, min_dv: float = 1e6) -> pd.DataFrame:
    """Per month: equal-weighted next-month return of the bottom (pf1) and top (pf3) terciles, and the spread."""
    e = p[(p["close"] >= min_price) & (p["dollar_volume_20"] >= min_dv) & p[signal].notna() & p["fwd"].notna()]
    e = e[np.isfinite(e[signal]) & (e["fwd"].abs() < 5)]       # a >500% month is a data defect, not a return
    rows = []
    for d, g in e.groupby("date"):
        if len(g) < 60:
            continue
        lo, hi = g[signal].quantile([1 / 3, 2 / 3])
        pf1, pf3 = g[g[signal] <= lo]["fwd"].mean(), g[g[signal] >= hi]["fwd"].mean()
        rows.append({"formed": d, "pf1": pf1, "pf3": pf3, "spread": pf3 - pf1, "n": len(g)})
    out = pd.DataFrame(rows)
    if len(out):
        out["month"] = pd.to_datetime(out["formed"]).dt.to_period("M") + 1     # the month the return is earned in
    return out


def published(conn, signal: str) -> pd.DataFrame:
    q = pd.read_sql("SELECT leg, date, ret FROM published_returns WHERE source='jkp' AND signal=? AND weighting='ew' "
                    "AND leg IN ('pf1','pf3')", conn, params=(signal,))
    w = q.pivot_table(index="date", columns="leg", values="ret").reset_index()
    w["month"] = pd.to_datetime(w["date"]).dt.to_period("M")
    w["spread"] = w["pf3"] - w["pf1"]
    return w[["month", "pf1", "pf3", "spread"]]


def compare(ours: pd.DataFrame, theirs: pd.DataFrame) -> dict:
    m = ours.merge(theirs, on="month", suffixes=("_ours", "_jkp"))
    if len(m) < 12:
        return {"months": len(m)}
    c = lambda a, b: float(np.corrcoef(m[a], m[b])[0, 1])          # noqa: E731
    sp = c("spread_ours", "spread_jkp")
    return {"months": len(m), "corr_pf3": c("pf3_ours", "pf3_jkp"), "corr_pf1": c("pf1_ours", "pf1_jkp"),
            "corr_spread": sp, "mean_spread_ours": float(m["spread_ours"].mean()),
            "mean_spread_jkp": float(m["spread_jkp"].mean()), "mean_pf3_ours": float(m["pf3_ours"].mean()),
            "mean_pf3_jkp": float(m["pf3_jkp"].mean()),
            "verdict": "faithful" if sp >= 0.9 else "partial: investigate" if sp >= 0.6 else "differs materially",
            "first": str(m["month"].min()), "last": str(m["month"].max())}


def run(conn, start: str, end: str) -> dict:
    dates = month_ends(conn, f"{int(start[:4]) - 1}{start[4:]}-01", f"{end}-31")   # a year earlier for the 12-1 lag
    panel = attach_bm(conn, load_month_end_panel(conn, dates), dates)
    p = signals(panel)
    res = {}
    for s in SIGNALS:
        ours = terciles(p, s)
        ours = ours[(ours["month"] >= pd.Period(start, "M")) & (ours["month"] <= pd.Period(end, "M"))]
        res[s] = {**compare(ours, published(conn, s)), "avg_names": float(ours["n"].mean()) if len(ours) else 0}
    return res


def render(res: dict, start: str, end: str) -> str:
    L = [f"# External benchmark vs JKP — {date.today().isoformat()}", "",
         f"Our tercile portfolios (equal-weighted, next-month returns) against JKP's published US series, {start} to {end}. "
         "The spread (top minus bottom tercile) is the test; raw tercile correlations mostly measure the market.", "",
         "| signal | months | names / month | corr top tercile | corr bottom | **corr spread** | mean spread ours | mean spread JKP | verdict |",
         "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for s, r in res.items():
        if "corr_spread" not in r:
            L.append(f"| {s} | {r.get('months', 0)} | | | | | | | too few months |")
            continue
        L.append(f"| {s} | {r['months']} | {r['avg_names']:.0f} | {r['corr_pf3']:.2f} | {r['corr_pf1']:.2f} | "
                 f"**{r['corr_spread']:.2f}** | {r['mean_spread_ours']:+.2%} | {r['mean_spread_jkp']:+.2%} | {r['verdict']} |")
    L += ["", "Deviations from JKP: our universe (survivors over-represented), >= $5 and >= $1M/day at formation, all-stock "
          "breakpoints, equal weights, adjusted month-end closes. Pass marks stated before running: >= 0.9 faithful, "
          "0.6-0.9 investigate, < 0.6 differs materially. Read-only."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--start", default="2010-01")
    ap.add_argument("--end", default="2024-12")
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    res = run(conn, a.start, a.end)
    text = render(res, a.start, a.end)
    print(text)
    if a.write:
        p = ROOT / "reports" / f"external_benchmark_{date.today().isoformat()}.md"
        p.write_text(text)
        print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
