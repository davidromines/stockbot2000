"""SUE per quarterly filing: year-ago match by period date, sd of prior deltas only."""
import runtime  # noqa: F401  (thread limits before numpy/pandas)

import argparse
import sys
from datetime import date, timedelta

import numpy as np
import pandas as pd

import fundamental_features as ff
from storage import connect
from universe import load_config

MAX_AGE_DAYS = 63
MIN_PRIOR = 4
MAX_PRIOR = 8
YEAR_AGO_LO = 350
YEAR_AGO_HI = 380
BATCH = 500
QUARTERLY_FORMS = ("10-Q", "10-K", "10-Q/A", "10-K/A")


def _d(s):
    """YYYYMMDD (SEC) or YYYY-MM-DD (prices) -> date. The two formats must never be compared
    as strings: '-' sorts before every digit, so an ISO date always looks earlier."""
    s = str(s).replace("-", "")[:8]
    return date(int(s[0:4]), int(s[4:6]), int(s[6:8]))


def quarterly_eps(conn, tickers=None):
    sql = """
        SELECT f.ticker, f.period, f.filed, f.adsh, x.ddate, x.value
          FROM sec_filings f
          JOIN sec_facts x ON x.adsh = f.adsh
         WHERE x.tag = 'EarningsPerShareBasic' AND x.qtrs = 1
           AND f.form IN ({})
    """.format(",".join("?" * len(QUARTERLY_FORMS)))
    params = list(QUARTERLY_FORMS)
    if tickers is not None:
        tickers = list(tickers)
        if not tickers:
            return pd.DataFrame(columns=["ticker", "period", "filed", "eps"])
        sql += " AND f.ticker IN ({})".format(",".join("?" * len(tickers)))
        params += tickers
    df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        return pd.DataFrame(columns=["ticker", "period", "filed", "eps"])
    # Several qtrs=1 rows per filing: the latest ddate describes the period.
    df = df.sort_values(["ticker", "period", "filed", "ddate"])
    df = df.drop_duplicates(["ticker", "period", "filed", "adsh"], keep="last")
    # Amendments: latest filing per (ticker, period) wins.
    df = df.sort_values(["ticker", "period", "filed"])
    df = df.drop_duplicates(["ticker", "period"], keep="last")
    out = df[["ticker", "period", "filed", "value"]].rename(columns={"value": "eps"})
    return out.reset_index(drop=True)


def compute_sue(eps_df):
    cols = ["ticker", "period", "filed", "eps", "delta", "sue"]
    if eps_df is None or eps_df.empty:
        return pd.DataFrame(columns=cols)
    df = eps_df.copy()
    df["_p"] = df["period"].map(_d)
    df = df.sort_values(["ticker", "_p"]).reset_index(drop=True)

    deltas = []
    for _, g in df.groupby("ticker", sort=False):
        periods = list(g["_p"])
        eps = list(g["eps"])
        for i, p in enumerate(periods):
            lo, hi = p - timedelta(days=YEAR_AGO_HI), p - timedelta(days=YEAR_AGO_LO)
            cands = [j for j, q in enumerate(periods) if lo <= q <= hi]
            if not cands:
                deltas.append(np.nan)
                continue
            j = min(cands, key=lambda k: abs((periods[k] - (p - timedelta(days=365))).days))
            deltas.append(eps[i] - eps[j])
    df["delta"] = deltas

    sues = []
    for _, g in df.groupby("ticker", sort=False):
        d = list(g["delta"])
        for i in range(len(d)):
            prior = [v for v in d[:i] if v == v][-MAX_PRIOR:]
            if len(prior) < MIN_PRIOR:
                sues.append(np.nan)
                continue
            sd = float(np.std(prior, ddof=1))
            sues.append(np.nan if sd == 0 or d[i] != d[i] else d[i] / sd)
    df["sue"] = sues

    df = df[df["sue"].notna()]
    return df[cols].reset_index(drop=True)


def init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS daily_sue (
            ticker   TEXT NOT NULL,
            date     TEXT NOT NULL,
            sue      REAL,
            sue_age  INTEGER,
            PRIMARY KEY (ticker, date)
        )
        """
    )
    conn.commit()


def project(conn, sue_df, start="2009-01-01"):
    if sue_df is None or sue_df.empty:
        return 0
    total = 0
    for ticker, g in sue_df.groupby("ticker", sort=False):
        prices = pd.read_sql_query(
            "SELECT date FROM prices WHERE ticker = ? AND date >= ? ORDER BY date",
            conn, params=[ticker, start],
        )
        if prices.empty:
            continue
        dates = list(prices["date"])
        rows = []
        days = [(dt, _d(dt)) for dt in dates]
        # Oldest quarter first, so a newer surprise overwrites an older one on shared dates.
        for _, r in g.assign(_f=g["filed"].map(_d)).sort_values("_f").iterrows():
            filed = _d(r["filed"])
            avail = filed + timedelta(days=ff.LAG_DAYS)
            for dt, day in days:
                if day < avail:
                    continue
                age = (day - filed).days
                if age > MAX_AGE_DAYS:
                    break  # dates sorted; nothing later can be fresh either
                rows.append((ticker, dt, float(r["sue"]), int(age)))
        if rows:
            conn.executemany(
                "INSERT OR REPLACE INTO daily_sue (ticker, date, sue, sue_age) "
                "VALUES (?, ?, ?, ?)",
                rows,
            )
            total += len(rows)
    conn.commit()
    return total


def build(conn, tickers=None):
    init(conn)
    if tickers is None:
        tickers = [r[0] for r in conn.execute(
            "SELECT DISTINCT ticker FROM sec_filings ORDER BY ticker")]
    tickers = list(tickers)
    n_sue = n_daily = 0
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        eps = quarterly_eps(conn, batch)
        sue = compute_sue(eps)
        n_sue += len(sue)
        n_daily += project(conn, sue)
        conn.commit()
    return {"tickers": len(tickers), "surprises": n_sue, "daily_rows": n_daily}


def coverage(conn):
    n, t = conn.execute("SELECT COUNT(*), COUNT(DISTINCT ticker) FROM daily_sue").fetchone()
    have = conn.execute(
        "SELECT COUNT(*) FROM prices p WHERE p.date >= '20160101' AND p.date <= '20191231' "
        "AND EXISTS (SELECT 1 FROM daily_sue s WHERE s.ticker = p.ticker AND s.date = p.date)"
    ).fetchone()[0]
    allp = conn.execute(
        "SELECT COUNT(*) FROM prices WHERE date >= '20160101' AND date <= '20191231'"
    ).fetchone()[0]
    share = (have / allp) if allp else 0.0
    return {"rows": n, "tickers": t, "share_2016_2019": share}


def main(argv=None):
    ap = argparse.ArgumentParser()
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    args = ap.parse_args(argv)
    conn = connect(load_config()["database"]["market_data_path"])
    try:
        if args.build:
            print(build(conn))
        if args.coverage:
            print(coverage(conn))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
