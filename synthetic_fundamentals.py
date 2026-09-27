"""
Real fundamentals for the synthetic dead companies (owner, 2026-09-26: "fix the
fundamental screens").

Synthetic dead companies had prices but no financial statements, so every
fundamental screen (Value Book, Profitability, Earnings Yield, ...) could never
buy one: their "with dead companies" backtest was the survivors-only backtest.

But most of these companies FILED. When a dead company's CIK has 10-K/10-Q
filings in our SEC data (sec_filings / sec_facts, 2009+), this computes its
point-in-time fundamentals exactly the way the real panel does:

    facts      value_metrics._facts_for(adsh)             the company's own filing
    prior      the previous filing of the same CIK        (change-based metrics)
    shares     value_metrics._pick(facts, "shares")       from the filing itself
    price      the company's REAL filed price level (10-K Item 5 quarter near the
               filing, item5_anchors) where one exists — 22% of filings — else the
               SYNTHETIC path's close on the filing date (its per-company level error
               is the generator's, stated)
    metrics    value_metrics.compute(cur, prev, mcap, mkt)
    daily      fundamental_features' rule: available LAG_DAYS after `filed`,
               as-of joined backwards, from 2009-01-01 (where the real panel starts)

Companies whose filings are not in our data (pre-2009, no CIK, never filed
XBRL) get no fundamentals — the same as a real company without them, which no
fundamental screen can buy either.

The output is stamped with the synthetic build it was computed from; the
survivorship backtest ignores it if the generator has been rebuilt since.

    ./run_bounded.sh ./venv/bin/python synthetic_fundamentals.py --build
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import os
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

import fundamental_features as ff
import value_metrics as vm

log = logging.getLogger("synthetic_fundamentals")
OUT = Path("data/universe/synthetic_fundamentals.parquet")
STAMP = Path("data/universe/synthetic_fundamentals.json")
START = "2009-01-01"


def _iso(filed: str) -> str:
    return f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}" if len(filed) == 8 else filed[:10]


def market_context_from(px: pd.Series, spy: pd.Series, d: str) -> dict:
    """value_metrics._market_context on a price SERIES (date-indexed, ISO strings): same arithmetic."""
    p = px[(px.index <= d) & (px > 0)].tail(65)
    if len(p) < 25:
        return {}
    a = p.to_numpy(dtype="float64")
    rets = np.diff(np.log(a))
    sigma = float(np.sqrt(252.0 * np.mean(rets ** 2))) if rets.size else None
    s = spy[(spy.index <= d) & (spy > 0)].tail(65)
    excess = None
    if len(s) >= 25:
        b = s.to_numpy(dtype="float64")
        excess = float(np.log(a[-1] / a[0]) - np.log(b[-1] / b[0]))
    return {"sigma": sigma, "excess": excess, "price": float(a[-1])}


ANCHOR_WINDOW_DAYS = 100


def real_price(anchors: list, d: str) -> float | None:
    """The company's own filed price level near `d`: sqrt(high * low) of the newest 10-K Item 5
    quarter ending in the ANCHOR_WINDOW_DAYS before d (item5_anchors), else None."""
    lo = (pd.Timestamp(d) - pd.Timedelta(days=ANCHOR_WINDOW_DAYS)).strftime("%Y-%m-%d")
    near = [(pe, hi, low) for pe, hi, low in anchors if lo <= pe <= d]
    if not near:
        return None
    pe, hi, low = max(near)
    return float(np.sqrt(hi * low))


def company_metrics(conn, cik: int, px: pd.Series, spy: pd.Series, filings: list,
                    anchors: list | None = None) -> pd.DataFrame:
    """
    One row per filing: filed + FUNDAMENTAL_COLS. Market cap uses the company's REAL
    filed price level where a 10-K Item 5 quarter is near the filing, else the
    synthetic close. Synthetic levels are right in aggregate but random per company
    (synthetic/filed IQR 0.23-6.9x), and a valuation ratio is only as right as its
    price; trade returns do not depend on the level, so the path is not changed.
    """
    rows, prev = [], None
    for adsh, filed in filings:
        cur = vm._facts_for(conn, adsh)
        if not cur:
            continue
        d = _iso(str(filed))
        shares = vm._pick(cur, "shares", {0, 1, 4})
        before = px[px.index <= d]
        rp = real_price(anchors or [], d)
        level = rp if rp else (float(before.iloc[-1]) if len(before) else None)
        mcap = level * float(shares) if shares and shares > 0 and level else None
        mkt = market_context_from(px, spy, d) if mcap else None
        if mkt and mcap:
            mkt["rel_size"] = float(np.log(max(mcap, 1.0) / 1e13))
        m = vm.compute(cur, prev, mcap, mkt)
        prev = cur
        rows.append({"filed": str(filed), "price_source": "filed" if rp else "synthetic",
                     **{c: m.get(c) for c in ff.FUNDAMENTAL_COLS}, "market_cap": mcap})
    return pd.DataFrame(rows)


def project(dates: pd.Index, f: pd.DataFrame) -> pd.DataFrame:
    """fundamental_features.build's as-of join for one company: LAG_DAYS after `filed`, backwards only."""
    if f.empty:
        return pd.DataFrame()
    f = f.copy()
    f["avail"] = pd.to_datetime(f["filed"].str.replace("-", ""), format="%Y%m%d", errors="coerce")
    f = f.dropna(subset=["avail"]).sort_values("avail")
    if f.empty:
        return pd.DataFrame()
    f["filed_on"] = f["avail"]
    f["avail"] = f["avail"] + pd.Timedelta(days=ff.LAG_DAYS)
    d = pd.DataFrame({"date": [x for x in dates if x >= START]})
    if d.empty:
        return pd.DataFrame()
    d["dt"] = pd.to_datetime(d["date"])
    m = pd.merge_asof(d.sort_values("dt"), f.sort_values("avail"), left_on="dt", right_on="avail",
                      direction="backward")
    m = m[m["avail"].notna()]
    m["days_since_filing"] = (m["dt"] - m["filed_on"]).dt.days
    return m[["date", "days_since_filing", *ff.FUNDAMENTAL_COLS]]


def build(conn, synth: str | None = None) -> dict:
    import universe_loader as ul
    synth = synth or ul.SYNTH
    ev = pd.read_parquet("data/universe/dead_evidence.parquet", columns=["company_id", "cik"]).dropna()
    ev["cik"] = ev["cik"].astype(int)
    syn = pd.read_parquet(synth, columns=["company_id", "date", "close", "is_delisting_bar"])
    syn = syn[~syn["is_delisting_bar"]]
    syn["date"] = pd.Index(syn["date"]).astype(str).str[:10]
    syn = syn.merge(ev, on="company_id")
    spy = pd.read_sql_query("SELECT date, close FROM prices WHERE ticker='SPY' ORDER BY date", conn
                            ).set_index("date")["close"]
    fil = pd.read_sql_query("SELECT cik, adsh, filed FROM sec_filings WHERE form IN "
                            "('10-K','10-Q','10-K/A','10-Q/A','10-KT') ORDER BY cik, filed", conn)
    fil["cik"] = fil["cik"].astype(int)
    by_cik = {c: list(zip(g["adsh"], g["filed"])) for c, g in fil.groupby("cik")}
    anch = {}
    if conn.execute("SELECT 1 FROM sqlite_master WHERE name='item5_anchors'").fetchone():
        for cik, pe, hi, lo in conn.execute("SELECT cik, period_end, high, low FROM item5_anchors "
                                            "ORDER BY cik, period_end, filed DESC"):
            lst = anch.setdefault(int(cik), [])
            if not lst or lst[-1][0] != pe:
                lst.append((pe, float(hi), float(lo)))
    n_real = 0
    # Earnings surprise from each dead company's own filings (the same rule as the live
    # companies' daily_sue): earnings-surprise strategies can then buy dead companies, so
    # their survivorship test is measurable instead of "survivors only".
    import sue_features as sfe
    sue_all = sfe.compute_sue(sfe.quarterly_eps_by_cik(conn, sorted(syn["cik"].unique())))
    sue_by = {int(c): g for c, g in sue_all.groupby("ticker")} if not sue_all.empty else {}
    n_sue = 0
    parts, n_co, n_fil = [], 0, 0
    for cid, g in syn.groupby("company_id", sort=False):
        cik = int(g["cik"].iloc[0])
        filings = by_cik.get(cik)
        if not filings:
            continue
        g = g.sort_values("date")
        px = g.set_index("date")["close"]
        lo, hi = px.index[0].replace("-", ""), px.index[-1].replace("-", "")
        filings = [(a, f) for a, f in filings if lo <= str(f) <= hi]   # filed while the path exists
        if not filings:
            continue
        f = company_metrics(conn, cik, px, spy, filings, anch.get(cik))
        n_real += int((f.get("price_source") == "filed").sum()) if len(f) else 0
        daily = project(px.index, f)
        if daily.empty:
            continue
        su = sfe.project_dates(sue_by.get(cik), daily["date"])
        daily["sue"], daily["sue_age"] = su["sue"].to_numpy(), su["sue_age"].to_numpy()
        n_sue += int(su["sue"].notna().sum())
        daily.insert(0, "company_id", cid)
        parts.append(daily)
        n_co += 1
        n_fil += len(f)
        if n_co % 250 == 0:
            log.info(f"{n_co:,} companies, {n_fil:,} filings")
    out = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    out.to_parquet(OUT, index=False)
    stamp = {"generator": f"{os.path.basename(synth)}:{os.path.getsize(synth)}", "companies": n_co,
             "filings": n_fil, "filings_priced_at_filed_level": n_real, "daily_rows": int(len(out)),
             "daily_rows_with_sue": n_sue,
             "synthetic_companies": int(syn["company_id"].nunique())}
    STAMP.write_text(json.dumps(stamp, indent=1))
    return stamp


def load(generator: str | None, start: str | None = None, end: str | None = None,
         columns: list | None = None) -> pd.DataFrame | None:
    """
    The build for `generator`, or None when absent or stale. `start`/`end` (ISO) and
    `columns` restrict what is read: the full file is 4.5M rows, and loading it whole
    beside a real fundamental panel took the survivorship run past its 6 GB cap
    (OOM, 2026-09-26).
    """
    if not (OUT.exists() and STAMP.exists()):
        return None
    if json.loads(STAMP.read_text()).get("generator") != generator:
        log.warning("synthetic fundamentals are from another synthetic build — ignored; rebuild them")
        return None
    filters = []
    if start:
        filters.append(("date", ">=", start))
    if end:
        filters.append(("date", "<=", end))
    have = None
    if columns is not None:
        import pyarrow.parquet as pq
        have = set(pq.read_schema(OUT).names)
    cols = None if columns is None else ["company_id", "date", *[c for c in columns if c in have]]
    df = pd.read_parquet(OUT, columns=cols, filters=filters or None)
    for c in (columns or []):
        if c not in df.columns:
            df[c] = float("nan")     # a column added after this build: unknown, never zero
    for c in df.columns:
        if c not in ("company_id", "date"):
            df[c] = df[c].astype("float32")
    return df


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(f"file:{load_config()['database']['market_data_path']}?mode=ro", uri=True, timeout=60)
    if a.build:
        print(json.dumps(build(conn), indent=1))
    elif STAMP.exists():
        print(STAMP.read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
