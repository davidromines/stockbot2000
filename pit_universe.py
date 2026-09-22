"""
What an investor could actually have known about on a given date.
Phase 6 section 5.

THE QUESTION THIS ANSWERS
--------------------------
Not "which securities are in today's database" — which is what every backtest in
this project has silently used — but "which securities existed, were listed, and
had not yet delisted, as of this date".

The difference is the entire survivorship problem. A universe built from today's
symbol table contains only companies that survived to today; a point-in-time
universe contains the ones that were there at the time, including the 8,909
delisted names we have no prices for.

TWO KINDS OF ABSENCE, AND THEY MUST NOT BE CONFLATED
-----------------------------------------------------
  NOT LISTED YET    the company had not IPO'd. Correctly absent; including it
                    would be look-ahead.
  LISTED BUT BLIND  the company existed and traded, and we hold no prices. NOT
                    correctly absent — it is a hole, and it is the survivorship
                    bias itself.

The current system cannot tell these apart, so every backtest treats the second
as if it were the first. `coverage()` reports them separately, which is the
first time this project can state per-date how much of the real universe it
could actually see.

WHERE THE POINT-IN-TIME RECORD ACTUALLY LIVES
----------------------------------------------
**Not in `symbols`.** That table's `first_seen` ranges 2026-09-08 to 2026-09-21
— it records when OUR daily snapshots first saw a ticker, not when the company
listed. Reconstructing a 2012 universe from it returns nothing, which is how
this was found: the first version of this module reported zero knowable
securities on every historical date.

The real record is `historical_listings`: 114 replays of the exchange symbol
directory from the Internet Archive, 2008-01-05 to 2026-08-30. Each is a
genuine snapshot of what was listed on that day.

**The snapshots are sparse** — 114 over eighteen years — so a date between them
uses the most recent prior snapshot, and `snapshot_lag_days` is reported with
every answer. A universe taken from a snapshot four months old is a weaker claim
than one taken from a snapshot four days old, and the caller is told which it has
rather than left to assume.

DATE SEMANTICS
--------------
A security is available on date D when a snapshot at or before D listed it, and
it had not delisted before D. Delisting on D itself counts as available: a stock
that delists on the 21st traded on the 21st. Off-by-one here is a look-ahead of
exactly one day, in the direction that flatters results.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
from functools import lru_cache

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pit")


def init(conn) -> None:
    """Indexes the point-in-time queries need. Idempotent."""
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sym_firstseen ON symbols(first_seen)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_del_symbol ON delistings(symbol)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_del_date ON delistings(delisting_date)")
    conn.commit()


def nearest_snapshot(conn, as_of: str) -> tuple:
    """
    The most recent directory snapshot at or before `as_of`, and its lag in days.

    Returns (None, None) when no snapshot precedes the date — which is an honest
    "cannot answer" rather than a silent empty universe.
    """
    r = conn.execute("SELECT MAX(snapshot_date) FROM historical_listings "
                     "WHERE snapshot_date <= ?", (as_of,)).fetchone()
    snap = r[0] if r else None
    if not snap:
        return None, None
    from datetime import date
    lag = (date.fromisoformat(as_of) - date.fromisoformat(snap)).days
    return snap, lag


def get_available_securities(conn, as_of: str, types: list | None = None,
                             with_prices_only: bool = False) -> list:
    """
    Securities knowable on `as_of`, from the directory snapshot in force then.

    `with_prices_only` is the honest lever. Left False you get the real
    universe — including names we cannot price, which is what a survivorship
    measurement needs. Set True you get the tradeable subset, which is what a
    backtest can actually use. The difference between the two IS the bias, and
    making callers choose explicitly stops them getting it by accident.
    """
    types = types or ["common_stock"]
    snap, lag = nearest_snapshot(conn, as_of)
    if not snap:
        return []
    ph = ",".join("?" * len(types))
    sql = f"""
        SELECT h.ticker, h.security_type, h.exchange, d.delisting_date
        FROM historical_listings h
        LEFT JOIN delistings d ON d.symbol = h.ticker
        WHERE h.snapshot_date = ?
          AND (h.security_type IN ({ph}) OR h.security_type IS NULL)
          -- Delisting ON the date still counts as available: a stock that
          -- delisted on the 21st traded on the 21st.
          AND (d.delisting_date IS NULL OR d.delisting_date >= ?)
    """
    params = [snap, *types, as_of]
    if with_prices_only:
        sql += (" AND EXISTS (SELECT 1 FROM prices p WHERE p.ticker = h.ticker "
                "AND p.date = ?)")
        params.append(as_of)
    out = [dict(r) for r in conn.execute(sql, params)]
    for o in out:
        o["snapshot_date"] = snap
        o["snapshot_lag_days"] = lag
    return out


def coverage(conn, as_of: str, types: list | None = None) -> dict:
    """
    How much of the real universe we could see on a date.

    The number that matters is `blind`: securities that were listed and trading
    and which we hold no price for. That is not a gap in the market, it is a gap
    in us, and it is the survivorship bias stated per-date instead of as an
    annual average.
    """
    snap, lag = nearest_snapshot(conn, as_of)
    known = get_available_securities(conn, as_of, types)
    tickers = [k["ticker"] for k in known]
    if not tickers:
        return {"as_of": as_of, "knowable": 0, "priced": 0, "blind": 0,
                "coverage_pct": 0.0, "snapshot_date": snap,
                "snapshot_lag_days": lag}
    priced = 0
    CH = 900
    for i in range(0, len(tickers), CH):
        block = tickers[i:i + CH]
        ph = ",".join("?" * len(block))
        priced += conn.execute(
            f"SELECT COUNT(DISTINCT ticker) FROM prices WHERE ticker IN ({ph}) "
            f"AND date = ?", (*block, as_of)).fetchone()[0]
    return {"as_of": as_of, "knowable": len(known), "priced": priced,
            "blind": len(known) - priced,
            "coverage_pct": round(priced / len(known) * 100, 2),
            "snapshot_date": snap, "snapshot_lag_days": lag}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of")
    ap.add_argument("--coverage", nargs="*", metavar="DATE")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.coverage is not None:
        dates = a.coverage or ["2008-06-30", "2012-06-29", "2016-06-30",
                               "2020-06-30", "2024-06-28"]
        print(f"\n  POINT-IN-TIME COVERAGE — common stock")
        print("  " + "-" * 62)
        print(f"  {'date':<12}{'knowable':>9}{'priced':>8}{'blind':>8}"
              f"{'coverage':>10}{'snapshot':>12}{'lag':>6}")
        for d in dates:
            c = coverage(conn, d)
            print(f"  {c['as_of']:<12}{c['knowable']:>9,}{c['priced']:>8,}"
                  f"{c['blind']:>8,}{c['coverage_pct']:>9.1f}%"
                  f"{str(c['snapshot_date'] or '-'):>12}"
                  f"{str(c['snapshot_lag_days'] if c['snapshot_lag_days'] is not None else '-'):>6}d")
        print("\n  'blind' is securities that were listed and trading on that date")
        print("  and which this database holds no price for. That is not a gap in")
        print("  the market — it is the survivorship bias, stated per date.")
        conn.close(); return 0

    d = a.as_of or conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    all_known = get_available_securities(conn, d)
    tradeable = get_available_securities(conn, d, with_prices_only=True)
    print(f"\n  UNIVERSE AS OF {d}")
    print(f"    knowable   {len(all_known):,}")
    print(f"    tradeable  {len(tradeable):,}")
    print(f"    blind      {len(all_known) - len(tradeable):,}")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
