"""
Rebuilds a point-in-time record of what was listed, from the Internet Archive.

The NASDAQ Trader symbol directory is a live view of what is listed *today*, and
nobody publishes yesterday's. That is the mechanical reason this project has a
survivorship problem: every universe we can build is a universe of survivors.

The Wayback Machine, however, archived that file roughly 120 times between 2008
and 2026. Each snapshot is a genuine point-in-time listing of the US market on
the day it was taken. Replaying them gives what a current directory cannot: the
tickers that existed then and do not exist now.

**This does not fix the bias.** It supplies no prices, so those dead tickers still
cannot be traded in a backtest. What it does is turn an unmeasured bias into a
measured coverage gap — "our 2012 universe contains N% of what actually traded,
and here are the 1,400 names we are missing". That number is what makes the
decision about paid point-in-time data an informed one instead of a guess.

Free, no API key, no purchase.

Usage:
    python reconstruct_universe.py --fetch      # download + parse snapshots (resumable)
    python reconstruct_universe.py --report     # coverage gap by year
    python reconstruct_universe.py --missing 2012   # names listed then, absent now
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import random
import time
from pathlib import Path

import requests

import storage
from universe import classify_security_type, load_config, normalize_symbol

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("reconstruct")

CDX = ("https://web.archive.org/cdx/search/cdx?url=nasdaqtrader.com/dynamic/SymDir/"
       "{file}.txt&output=json&fl=timestamp,statuscode&filter=statuscode:200&collapse=digest")
WAYBACK = "https://web.archive.org/web/{ts}id_/https://www.nasdaqtrader.com/dynamic/SymDir/{file}.txt"

FILES = ("nasdaqlisted", "otherlisted")


def snapshot_list(file: str, timeout: int = 60) -> list[str]:
    """Timestamps of archived captures whose content differs from the previous one."""
    resp = requests.get(CDX.format(file=file), timeout=timeout)
    resp.raise_for_status()
    rows = resp.json()
    return [r[0] for r in rows[1:]] if len(rows) > 1 else []


class ArchiveBlocked(Exception):
    """The Wayback Machine has stopped answering — back off and resume later."""


def fetch_snapshot(file: str, ts: str, cache_dir: Path, timeout: int = 60) -> str | None:
    """
    Fetch one archived capture, caching it on disk.

    Cached because the Wayback Machine is slow and rate-limited, and because these
    files are the primary evidence: once a capture is on disk it never needs
    fetching again, and the reconstruction becomes reproducible offline.
    """
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / f"{file}_{ts}.txt"
    if path.exists():
        return path.read_text(encoding="utf-8", errors="replace")
    try:
        resp = requests.get(WAYBACK.format(ts=ts, file=file), timeout=timeout)
        if resp.status_code != 200 or "Symbol" not in resp.text[:400]:
            log.warning(f"{file} {ts}: unusable response ({resp.status_code})")
            return None
        path.write_text(resp.text, encoding="utf-8")
        return resp.text
    except requests.exceptions.ConnectionError:
        # Distinguished from a bad capture on purpose. archive.org refuses
        # connections outright once it decides you have asked too often, and
        # every subsequent request fails the same way. Treating that as "this
        # snapshot is unusable" would march through the whole list marking
        # nothing and leave no sign of why.
        raise ArchiveBlocked(f"{file} {ts}")
    except Exception as e:
        log.warning(f"{file} {ts}: {e}")
        return None


def parse_snapshot(text: str, file: str) -> list[dict]:
    """
    Parse one archived directory into tagged listings.

    Reuses the same classifier and symbol normaliser as the live universe, so a
    2009 capture is tagged by exactly the same rules as today's file. Without that
    the coverage comparison would measure differences in parsing rather than
    differences in the market.
    """
    lines = [ln for ln in text.splitlines() if ln and not ln.startswith("File Creation Time")]
    if len(lines) < 2:
        return []
    header = lines[0].split("|")
    sym_col = "Symbol" if "Symbol" in header else "ACT Symbol"
    if sym_col not in header:
        return []

    out = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) != len(header):
            continue
        row = dict(zip(header, parts))
        if row.get("Test Issue") == "Y":
            continue
        ticker = normalize_symbol(row.get(sym_col, ""))
        if not ticker:
            continue
        name = (row.get("Security Name") or "").strip()
        out.append({
            "ticker": ticker,
            "name": name or None,
            "security_type": classify_security_type(name, row.get("ETF", "N"), ticker),
            "exchange": "NASDAQ" if file == "nasdaqlisted" else row.get("Exchange"),
        })
    return out


def fetch_all(config: dict, pause: float = 3.0) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)
    cache = Path(config["universe"].get("archive_cache_dir", "data/archive_snapshots"))

    done = storage.archived_snapshots(conn)
    log.info(f"{len(done)} snapshots already stored")
    blocked = stored = 0
    max_blocked = 4

    for file in FILES:
        try:
            stamps = snapshot_list(file)
        except Exception as e:
            log.error(f"Could not list snapshots for {file}: {e}")
            log.error("If this is a connection refusal, archive.org is rate limiting; "
                      "progress is saved and a later re-run will continue.")
            continue
        log.info(f"{file}: {len(stamps)} archived captures")

        for i, ts in enumerate(stamps, start=1):
            key = f"{file}:{ts}"
            if key in done:
                continue
            try:
                text = fetch_snapshot(file, ts, cache)
            except ArchiveBlocked:
                blocked += 1
                if blocked >= max_blocked:
                    log.error(
                        f"archive.org is refusing connections after {stored} new snapshots. "
                        f"Rate limited — progress is saved, re-run later to continue.")
                    conn.close()
                    return
                wait = min(60 * (2 ** (blocked - 1)), 900)
                log.warning(f"Connection refused ({blocked}/{max_blocked}); waiting {wait}s")
                time.sleep(wait)
                continue
            if text is None:
                continue
            blocked = 0
            rows = parse_snapshot(text, file)
            if not rows:
                log.warning(f"{file} {ts}: parsed zero listings")
                continue
            day = f"{ts[0:4]}-{ts[4:6]}-{ts[6:8]}"
            n = storage.record_historical_listings(conn, day, key, rows)
            stored += 1
            log.info(f"{file} {ts[:8]}: {n:,} listings ({i}/{len(stamps)})")
            time.sleep(pause * random.uniform(0.7, 1.4))

    conn.close()


def report(config: dict) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)

    rows = storage.coverage_by_snapshot(conn)
    if not rows:
        print("No archived snapshots stored yet — run --fetch first.")
        conn.close()
        return

    print(f"{'snapshot':<12}{'listed then':>12}{'have prices':>13}{'missing':>10}{'coverage':>10}")
    print("-" * 57)
    for r in rows:
        print(f"{r['snapshot_date']:<12}{r['listed']:>12,}{r['covered']:>13,}"
              f"{r['listed'] - r['covered']:>10,}{r['covered'] / r['listed']:>9.1%}")

    total = storage.total_ever_listed(conn)
    print()
    print(f"Distinct common stocks ever seen across all snapshots : {total['ever']:,}")
    print(f"  of which we hold price history                      : {total['covered']:,}")
    print(f"  vanished — listed at some point, absent today       : {total['ever'] - total['covered']:,}")
    conn.close()


def missing(config: dict, year: str, limit: int = 25) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    rows = storage.missing_tickers(conn, year, limit)
    if not rows:
        print(f"No snapshots stored for {year}.")
    else:
        print(f"Listed in {year}, no price history today (showing {len(rows)}):")
        for r in rows:
            print(f"  {r['ticker']:<8} {r['snapshot_date']}  {(r['name'] or '')[:58]}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--fetch", action="store_true", help="Download and store archived snapshots.")
    parser.add_argument("--report", action="store_true", help="Coverage gap per snapshot.")
    parser.add_argument("--missing", metavar="YEAR", help="List names listed that year but gone now.")
    args = parser.parse_args()

    config = load_config()
    runtime.be_nice()
    if args.fetch:
        fetch_all(config)
    if args.report:
        report(config)
    if args.missing:
        missing(config, args.missing)
    if not (args.fetch or args.report or args.missing):
        parser.print_help()


if __name__ == "__main__":
    main()
