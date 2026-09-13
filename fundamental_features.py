"""
Project fundamentals onto the daily panel, point-in-time. Phase 3.

Fundamentals arrive quarterly; strategies trade daily. Bridging the two is where
look-ahead bias is easiest to introduce and hardest to see, so the rules here are
deliberately strict.

**A filing is knowable from its filing date, not its period end.** A June quarter
is published weeks after June 30. Keying on the period would let a backtest read
a balance sheet before it existed — the same class of error that has produced six
false results in this project. Everything below is forward-filled from `filed`
plus a buffer, and never backwards.

**Two traps this module exists to avoid, both found before building it:**

1. `storage._feature_where` requires `IS NOT NULL` on every column in
   FEATURE_COLS. Adding fundamentals there would silently collapse the panel
   from 5.19M rows to only post-2009 filers with complete statements, and
   quietly change what every strategy is measured against. So fundamentals are
   **not** FEATURE_COLS; they are a separate, optional, null-tolerant join.

2. `genome._as_bool` maps NaN to False. That makes `piotroski_f > 7` never fire
   where data is absent — which is safe — but makes `not(piotroski_f > 7)` fire
   on *every* row without fundamentals, which is a free selector for the
   pre-2009 era and for ETFs. This search has found five loopholes of exactly
   that shape already. `has_fundamentals` is therefore carried alongside, so the
   asymmetry is visible and testable rather than hidden, and searches using
   fundamentals are confined to a window where the data exists.

Usage:
    python fundamental_features.py --build          # project onto trading days
    python fundamental_features.py --coverage
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("fund_feat")

# Filings are public on their filing date, but the market has to see and price
# them. Two trading days is a conservative buffer: it costs a little signal and
# removes any argument about same-day availability.
LAG_DAYS = 2

# Curated, not everything. Thirty-six columns would triple the genome's search
# space for the sake of ratios that are either near-duplicates or too sparsely
# covered to be usable. Each of these earns its place on evidence and coverage.
FUNDAMENTAL_COLS = [
    "piotroski_f",          # 89% coverage. The best-evidenced value screen there is.
    "book_to_market",       # 70%. Fama-French (1993), the original value factor.
    "gross_profitability",  # 51%. Novy-Marx (2013), "the other side of value".
    "chs_distress",         # 52%. Campbell-Hilscher-Szilagyi; predicts delisting.
    "asset_growth",         # 96%. Cooper et al (2008), strongest balance-sheet growth.
    "accruals",             # Sloan (1996). Earnings not backed by cash.
    "roa",                  # 90%. Plain profitability.
    "earnings_yield",       # E/P.
    "net_share_issuance",   # 89%. Daniel & Titman dilution.
    "debt_to_equity",
    "cash_to_assets",
    "altman_z",             # 83%. Famous; kept for comparison with CHS.
]


def init(conn) -> None:
    cols = ",\n            ".join(f"{c} REAL" for c in FUNDAMENTAL_COLS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS daily_fundamentals (
            ticker           TEXT NOT NULL,
            date             TEXT NOT NULL,
            has_fundamentals INTEGER NOT NULL,
            days_since_filing INTEGER,
            {cols},
            PRIMARY KEY (ticker, date)
        ) STRICT, WITHOUT ROWID
    """)
    have = {r[1] for r in conn.execute("PRAGMA table_info(daily_fundamentals)")}
    for c in FUNDAMENTAL_COLS:
        if c not in have:
            conn.execute(f"ALTER TABLE daily_fundamentals ADD COLUMN {c} REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_dfund_date ON daily_fundamentals(date)")
    conn.commit()


def build(conn, start: str = "2009-01-01", limit: int | None = None) -> None:
    """
    Forward-fill each company's latest known filing across its trading days.

    An as-of join: on any date, a ticker carries the most recent filing whose
    lagged availability date has already passed. `days_since_filing` travels with
    it, because a figure from three days ago and one from eleven months ago are
    not equally informative and a strategy should be able to tell them apart.
    """
    init(conn)
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM fundamentals ORDER BY ticker")]
    if limit:
        tickers = tickers[:limit]
    log.info(f"Projecting fundamentals for {len(tickers):,} tickers from {start}")

    cols_sql = ",".join(FUNDAMENTAL_COLS)
    written = skipped = 0
    buf = []
    for n, t in enumerate(tickers, 1):
        f = pd.read_sql_query(
            f"SELECT filed, {cols_sql} FROM fundamentals WHERE ticker=? ORDER BY filed",
            conn, params=(t,))
        if f.empty:
            skipped += 1; continue
        # filed is YYYYMMDD text in the SEC feed.
        f["avail"] = pd.to_datetime(f["filed"], format="%Y%m%d", errors="coerce")
        f = f.dropna(subset=["avail"]).sort_values("avail")
        if f.empty:
            skipped += 1; continue

        d = pd.read_sql_query(
            "SELECT date FROM prices WHERE ticker=? AND date>=? ORDER BY date",
            conn, params=(t, start))
        if d.empty:
            skipped += 1; continue
        d["dt"] = pd.to_datetime(d["date"])

        # Shift availability forward by the buffer, then as-of join backwards
        # only: merge_asof with direction="backward" cannot see the future.
        # `filed_on` is carried separately so the age column measures what its
        # name says. Measuring from the lagged date instead made the minimum 0
        # when the true minimum age is LAG_DAYS, which would quietly understate
        # staleness for anyone reading the column later.
        f["filed_on"] = f["avail"]
        f["avail"] = f["avail"] + pd.Timedelta(days=LAG_DAYS)
        merged = pd.merge_asof(d.sort_values("dt"), f.sort_values("avail"),
                               left_on="dt", right_on="avail", direction="backward")
        merged["has_fundamentals"] = merged["avail"].notna().astype(int)
        merged["days_since_filing"] = (merged["dt"] - merged["filed_on"]).dt.days

        keep = merged[merged["has_fundamentals"] == 1]
        if keep.empty:
            skipped += 1; continue
        for row in keep.itertuples(index=False):
            vals = [t, row.date, 1, int(row.days_since_filing)]
            vals += [None if (v is None or (isinstance(v, float) and not np.isfinite(v)))
                     else float(v) for v in
                     [getattr(row, c) for c in FUNDAMENTAL_COLS]]
            buf.append(tuple(vals))
        written += len(keep)
        if len(buf) >= 100000:
            _flush(conn, buf); buf = []
        if n % 500 == 0:
            log.info(f"  {n:,}/{len(tickers):,} tickers | {written:,} rows")
    if buf:
        _flush(conn, buf)
    conn.commit()
    log.info(f"Wrote {written:,} daily rows; {skipped:,} tickers had nothing to project")


def _flush(conn, rows) -> None:
    cols = "ticker,date,has_fundamentals,days_since_filing," + ",".join(FUNDAMENTAL_COLS)
    ph = ",".join("?" * (4 + len(FUNDAMENTAL_COLS)))
    conn.executemany(
        f"INSERT OR REPLACE INTO daily_fundamentals ({cols}) VALUES ({ph})", rows)
    conn.commit()


def coverage(conn) -> None:
    init(conn)
    tot = conn.execute("SELECT COUNT(*) FROM daily_fundamentals").fetchone()[0]
    if not tot:
        raise SystemExit("Nothing projected — run --build first.")
    tick = conn.execute("SELECT COUNT(DISTINCT ticker) FROM daily_fundamentals").fetchone()[0]
    rng = conn.execute("SELECT MIN(date), MAX(date) FROM daily_fundamentals").fetchone()
    stale = conn.execute("SELECT AVG(days_since_filing) FROM daily_fundamentals").fetchone()[0]
    print(f"\n  DAILY FUNDAMENTALS — point-in-time, lagged {LAG_DAYS} days past filing\n")
    print(f"  {'daily rows':<28}{tot:>14,}")
    print(f"  {'tickers':<28}{tick:>14,}")
    print(f"  {'date range':<28}{rng[0]} .. {rng[1]}")
    print(f"  {'mean age of the figures':<28}{stale:>13.0f} days")
    print(f"\n  {'column':<26}{'non-null':>13}{'coverage':>11}")
    print("  " + "-" * 52)
    for c in FUNDAMENTAL_COLS:
        n = conn.execute(f"SELECT COUNT({c}) FROM daily_fundamentals").fetchone()[0]
        print(f"  {c:<26}{n:>13,}{n/tot:>10.0%}")
    print("\n  These are NOT in FEATURE_COLS. The feature loader requires every")
    print("  column to be non-null, so adding them there would collapse the panel")
    print("  to post-2009 filers and silently change what every strategy is")
    print("  measured against. They join optionally and tolerate nulls.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--start", default="2009-01-01")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)
    if a.build:
        build(conn, a.start, a.limit)
    if a.coverage or not a.build:
        coverage(conn)
    conn.close()


if __name__ == "__main__":
    main()
