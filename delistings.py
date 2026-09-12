"""
The delisting registry. Which companies died, and when — measured, not estimated.

This project's central weakness has always been stated as an average: backtests
run about 10.4 points a year optimistic. That number came from comparing our
returns against a CRSP-based benchmark, and it is an average over a universe, not
a fact about any particular strategy. It could not say *which* companies were
missing, or when, so it could not be applied where it actually mattered.

This module replaces the estimate with a list. Alpha Vantage publishes every
delisted US listing with its IPO and delisting dates, and one request returns the
whole set. Measured 2026-09-12:

    9,464 delisted listings, of which 7,480 are common stock
      418 we hold prices for                            (5.6%)
    7,062 we hold nothing for                          (94.4%)

**7,062 companies that a backtest on this database can never buy**, each with the
exact date it stopped trading. That independently corroborates the Internet
Archive reconstruction, which put the gap at 9,029 — two unrelated methods
landing in the same place.

**The coverage limit, stated plainly:** the registry is thin before 2009 — 4
delistings in 2008, 2 in 2007. So it does *not* cover the financial crisis, which
sits inside this project's 2006-2019 search window and is precisely where the
missing failures would be most damaging. For that era `edgar_registry.py` is the
better instrument, since a company that stopped filing 10-Ks in 2009 is visible
there from 1993 onward.

Prices for the dead are still absent and no free source supplies them. What
changes is that the hole is now enumerated: a strategy can be asked how many of
its entries fall in names that were about to disappear, instead of being charged
a flat haircut that fits no strategy in particular.

Usage:
    python delistings.py --fetch        # pull the registry (needs the API key file)
    python delistings.py --report       # what died, what we hold, what we cannot see
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import csv
import io
import logging
from pathlib import Path

import requests

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("delistings")

KEY_FILE = Path.home() / ".alphavantage_key"
URL = "https://www.alphavantage.co/query"


def _key() -> str:
    """
    Read the API key from a 0600 file, never from the repo or a command line.

    A key pasted into a shell command lands in the shell history and in any
    transcript of the session; a key committed to config.yaml lands on GitHub.
    Neither is recoverable once done, so the key lives in one file outside the
    repository and is never logged.
    """
    if not KEY_FILE.exists():
        raise SystemExit(
            f"No API key at {KEY_FILE}.\n"
            "Get a free one at https://www.alphavantage.co/support/#api-key then:\n"
            f'  echo "YOURKEY" > {KEY_FILE} && chmod 600 {KEY_FILE}')
    k = KEY_FILE.read_text().strip()
    if not k or k == "YOUR_KEY_HERE":
        raise SystemExit(f"{KEY_FILE} holds a placeholder, not a key.")
    return k


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS delistings (
            symbol          TEXT NOT NULL,
            name            TEXT,
            exchange        TEXT,
            asset_type      TEXT,
            ipo_date        TEXT,
            delisting_date  TEXT NOT NULL,
            have_prices     INTEGER NOT NULL DEFAULT 0,
            source          TEXT NOT NULL,
            fetched_at      TEXT NOT NULL,
            PRIMARY KEY (symbol, delisting_date)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_delist_date ON delistings(delisting_date)")
    conn.commit()


def fetch(conn) -> int:
    """Pull the whole delisted registry. One request returns all of it."""
    init(conn)
    r = requests.get(URL, params={"function": "LISTING_STATUS", "state": "delisted",
                                  "apikey": _key()}, timeout=120)
    r.raise_for_status()
    body = r.text
    if not body.lstrip().lower().startswith("symbol"):
        # Alpha Vantage reports quota and key errors as a JSON body with HTTP 200.
        raise SystemExit(f"Unexpected response (quota or bad key?): {body[:200]}")

    have = {t[0].upper() for t in conn.execute("SELECT DISTINCT ticker FROM prices")}
    rows, now = [], storage._now()
    for d in csv.DictReader(io.StringIO(body)):
        sym = (d.get("symbol") or "").upper()
        dld = d.get("delistingDate") or ""
        if not sym or not dld or dld == "null":
            continue
        rows.append((sym, d.get("name"), d.get("exchange"), d.get("assetType"),
                     (d.get("ipoDate") or None), dld,
                     1 if sym in have else 0, "alphavantage", now))
    conn.executemany("""INSERT OR REPLACE INTO delistings
        (symbol,name,exchange,asset_type,ipo_date,delisting_date,have_prices,source,fetched_at)
        VALUES (?,?,?,?,?,?,?,?,?)""", rows)
    conn.commit()
    log.info(f"Recorded {len(rows):,} delistings")
    return len(rows)


def mark_symbols(conn) -> None:
    """
    Stamp our own symbol table with delisting dates where they are known.

    Only touches the 418 delisted names we actually hold prices for. The other
    7,062 cannot be marked because they were never in the table — which is the
    entire problem, and why the count below matters more than the update count.
    """
    n = conn.execute("""
        UPDATE symbols SET is_active = 0
        WHERE ticker IN (SELECT symbol FROM delistings WHERE asset_type='Stock')
    """).rowcount
    conn.commit()
    log.info(f"Marked {n:,} held symbols inactive from the registry")


def report(conn) -> None:
    init(conn)
    tot = conn.execute("SELECT COUNT(*) FROM delistings").fetchone()[0]
    if not tot:
        raise SystemExit("Registry empty — run --fetch first.")
    stock = conn.execute("SELECT COUNT(*) FROM delistings WHERE asset_type='Stock'").fetchone()[0]
    held = conn.execute("SELECT COUNT(*) FROM delistings WHERE asset_type='Stock' "
                        "AND have_prices=1").fetchone()[0]

    print(f"\n  THE DELISTING REGISTRY — companies that stopped trading")
    print(f"  {'delisted listings':<34}{tot:>8,}")
    print(f"  {'of which common stock':<34}{stock:>8,}")
    print(f"  {'we hold prices for':<34}{held:>8,}   {held/stock:>6.1%}")
    print(f"  {'we hold NOTHING for':<34}{stock-held:>8,}   {(stock-held)/stock:>6.1%}")

    print(f"\n  {'delisted in':<14}{'companies':>11}{'we have':>9}{'blind to':>10}")
    print("  " + "-" * 46)
    for row in conn.execute("""
        SELECT substr(delisting_date,1,4) y, COUNT(*) n, SUM(have_prices) h
        FROM delistings WHERE asset_type='Stock' AND delisting_date >= '2006'
        GROUP BY y ORDER BY y"""):
        print(f"  {row[0]:<14}{row[1]:>11,}{row[2] or 0:>9,}{row[1]-(row[2] or 0):>10,}")

    print("\n  Coverage is thin before 2009 — the registry carries 4 delistings for 2008.")
    print("  The financial crisis sits inside the 2006-2019 search window and is exactly")
    print("  where the missing failures would hurt most, so for that era use")
    print("  edgar_registry.py, which reaches back to 1993.")
    print("\n  Prices for these companies remain unavailable from any free source. What")
    print("  this buys is an enumerated hole rather than an averaged one.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)
    if a.fetch:
        fetch(conn)
    if a.mark:
        mark_symbols(conn)
    if a.report or not (a.fetch or a.mark):
        report(conn)
    conn.close()


if __name__ == "__main__":
    main()
