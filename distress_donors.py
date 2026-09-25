"""
Stage M3 — a library of REAL distress paths, for synthetic failures to copy.

Generator v4 built failed companies from the lower tail of real *buyout* final
years, because the real dead sample is almost all buyouts: a bankrupt
company's price history disappears from free data. But the DECLINE into
distress does not need a dead company — it happened, on real dates, to every
stock in our own database that collapsed, whether it later died or recovered.
Research: docs/STAGE_M_RESEARCH.md (CHS 2008: distressed stocks run ~94%
annual volatility, skew ~+2.5, deeply negative excess returns).

AN EPISODE
----------
A common stock (no data-quality flag) that
  - at trigger date T closed below $2 AND below 15% of its 52-week high, and
  - closed at or above $5 at some point in the 3 years before T.
A = the last session before T with a close >= $5: the last day a strategy with
the $5 floor could still have bought it. The donor segment runs from 252
sessions before A to T; for companies that then died it continues to their
last bar.

WHAT IS KEPT
------------
Returns, never price levels. Prices here are split-adjusted, and distressed
companies reverse-split, so an adjusted $5 may not have been a real $5 — the
episode SELECTION carries that noise (stated), the stored path does not.
Per episode: daily residuals vs SPY (beta from the segment), raw returns,
beta, sessions from A to T, the fall A->T, volatility and skew of the last 60
sessions before T, the flat-day share, era, exchange, and whether the company
later died.

    ./run_bounded.sh ./venv/bin/python distress_donors.py --build
    ./venv/bin/python distress_donors.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

log = logging.getLogger("distress_donors")
OUT = Path("data/universe/distress_donors.parquet")
TRIGGER_PRICE, TRIGGER_FRAC, TRADEABLE, LOOKBACK_YEARS, PRE = 2.0, 0.15, 5.0, 3, 252


def episodes(conn) -> pd.DataFrame:
    q = """SELECT f.ticker, MIN(f.date) trigger FROM features f JOIN prices p ON p.ticker=f.ticker AND p.date=f.date
           JOIN symbols s ON s.ticker=f.ticker
           WHERE s.security_type='common_stock' AND (s.data_quality IS NULL OR s.data_quality='')
             AND f.pct_of_52w_high < ? AND p.close < ? GROUP BY f.ticker"""
    return pd.read_sql_query(q, conn, params=(TRIGGER_FRAC, TRIGGER_PRICE))


def build(conn) -> pd.DataFrame:
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"].pct_change()
    ep = episodes(conn)
    dead = {t for (t,) in conn.execute("SELECT symbol FROM delistings")}
    last_all = dict(conn.execute("SELECT ticker, MAX(date) FROM prices GROUP BY ticker").fetchall())
    newest = max(last_all.values())
    exch = dict(conn.execute("SELECT ticker, exchange FROM symbols").fetchall())
    rows = []
    for e in ep.itertuples(index=False):
        px = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker=? ORDER BY date", conn,
                               params=(e.ticker,)).set_index("date")["close"]
        if px.empty or e.trigger not in px.index:
            continue
        ti = px.index.get_loc(e.trigger)
        lo = max(0, ti - 252 * LOOKBACK_YEARS)
        window = px.iloc[lo:ti]
        above = window[window >= TRADEABLE]
        if above.empty:
            continue                                  # never tradeable at the $5 floor before the collapse
        a_date = above.index[-1]
        ai = px.index.get_loc(a_date)
        died = e.ticker in dead or last_all[e.ticker] < newest[:8] + "01"
        end = len(px) - 1 if died else ti
        seg = px.iloc[max(0, ai - PRE): end + 1]
        r = seg.pct_change().dropna()
        j = pd.concat([r.rename("r"), spy.rename("m")], axis=1, join="inner").dropna()
        if len(j) < 60:
            continue
        m, y = j["m"].to_numpy(), j["r"].to_numpy()
        beta = float(np.cov(y, m)[0, 1] / np.var(m)) if np.var(m) > 0 else 1.0
        beta = float(np.clip(beta, -1.0, 4.0))
        resid = np.clip(y - beta * m, -0.9, 3.0)
        pre = px.iloc[max(0, ti - 60): ti + 1].pct_change().dropna().to_numpy()
        rows.append({
            "ticker": e.ticker, "trigger": e.trigger, "last_tradeable": a_date,
            "year": int(e.trigger[:4]), "exchange": exch.get(e.ticker), "died": bool(died),
            "sessions_decline": int(ti - ai), "fall_a_to_t": float(px.iloc[ti] / px.iloc[ai] - 1),
            "price_a": float(px.iloc[ai]),               # the real last close at the tradeable level
            "vol_pre60": float(np.std(pre) * np.sqrt(252)) if len(pre) > 5 else None,
            "skew_pre60": float(pd.Series(pre).skew()) if len(pre) > 5 else None,
            "flat_share": float((np.abs(y) < 1e-6).mean()), "beta": beta,
            "a_offset": int(min(PRE, ai)),             # index of A inside the stored series
            "t_offset": int(min(PRE, ai) + (ti - ai)),  # index of T inside the stored series
            "dates": json.dumps(list(j.index)), "resid": json.dumps([round(float(x), 6) for x in resid]),
            "ret": json.dumps([round(float(x), 6) for x in y]),
        })
    df = pd.DataFrame(rows)
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    return df


def report(df: pd.DataFrame) -> str:
    L = ["", f"  DISTRESS DONORS — {len(df):,} real episodes ({int(df['died'].sum())} later died, "
             f"{int((~df['died']).sum())} survived)",
         f"  sessions from last $5 close to distress: median {df['sessions_decline'].median():.0f}, "
         f"p25 {df['sessions_decline'].quantile(.25):.0f}, p75 {df['sessions_decline'].quantile(.75):.0f}",
         f"  fall from last $5 close to distress: median {df['fall_a_to_t'].median():+.0%}",
         f"  last-60-session volatility (annualised): median {df['vol_pre60'].median():.0%}   "
         f"skew: median {df['skew_pre60'].median():+.2f}   (CHS 2008 top-1% distress: ~94%, +2.5)",
         f"  beta: median {df['beta'].median():.2f}   flat days: median {df['flat_share'].median():.1%}",
         "", "  by era:"]
    for (lo, hi) in ((1990, 1999), (2000, 2003), (2004, 2007), (2008, 2009), (2010, 2019), (2020, 2026)):
        s = df[(df["year"] >= lo) & (df["year"] <= hi)]
        L.append(f"    {lo}-{hi}: {len(s):>4}")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Real distress paths for synthetic failures (Stage M3).")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True, timeout=60)
    df = build(conn) if a.build else pd.read_parquet(OUT)
    print(report(df))
    return 0


if __name__ == "__main__":
    sys.exit(main())
