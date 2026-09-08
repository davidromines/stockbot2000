"""
Computes the 20 technical indicators for every ticker in `prices` and writes them
to the `features` table.

The counterpart to `backfill.py`: that fetches raw bars, this derives everything
the model reads. Same guarantees — resumable, idempotent, interruptible.

Resumability here needs no progress table. Which tickers need work is derived by
comparing the latest feature date against the latest price date per ticker, so
the answer is always computed from what is actually in the database rather than
from a bookkeeping table that could drift out of sync with it. Re-run after new
prices land and exactly the tickers that moved get recomputed.

Note that a ticker needs 210 bars before any features exist — the 200-day SMA has
to warm up. Tickers listed within the last ten months are therefore skipped, and
that is correct rather than a gap to fill.

Usage:
    python build_features.py --limit 20     # prove it on 20 tickers
    python build_features.py                # everything outstanding
    python build_features.py --status       # coverage, no computing
    python build_features.py --rebuild      # recompute everything from scratch
"""
import argparse
import logging
import signal
import sys
import time

import storage
from features import compute_features_for_ticker
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("build_features")

MIN_BARS = storage.MIN_BARS_FOR_FEATURES  # 200-day SMA warm-up

_interrupted = False


def _handle_interrupt(signum, frame):
    global _interrupted
    if _interrupted:
        log.warning("Second interrupt — exiting now.")
        sys.exit(130)
    _interrupted = True
    log.warning("Interrupt received. Finishing current ticker, then stopping cleanly...")


def run(config: dict, limit: int | None = None, rebuild: bool = False,
        commit_every: int = 50) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)

    if rebuild:
        n = conn.execute("DELETE FROM features").rowcount
        conn.commit()
        log.warning(f"--rebuild: cleared {n:,} existing feature rows")

    types = config["universe"].get("feature_types")
    todo = storage.tickers_needing_features(conn, types=types)
    outstanding = len(todo)
    if limit:
        todo = todo[:limit]

    log.info(f"Feature types: {', '.join(types) if types else 'all'}")
    log.info(f"{outstanding} tickers need features | computing {len(todo)} this run")
    if not todo:
        log.info("Nothing to do.")
        conn.close()
        return

    started = time.time()
    done = skipped = rows_written = 0

    for i, ticker in enumerate(todo, start=1):
        if _interrupted:
            log.warning(f"Stopping after {i - 1} tickers as requested.")
            break

        prices = storage.load_prices(conn, ticker)
        if len(prices) < MIN_BARS:
            skipped += 1
            continue

        feats = compute_features_for_ticker(prices)
        if feats.empty:
            skipped += 1
            continue

        rows_written += storage.upsert_features(conn, feats)
        done += 1

        if i % commit_every == 0:
            conn.commit()
            elapsed = time.time() - started
            rate = i / elapsed if elapsed else 0
            remaining = (len(todo) - i) / rate if rate else 0
            log.info(f"{i}/{len(todo)} tickers | {rows_written:,} feature rows | "
                     f"{skipped} skipped | {rate:.1f} tickers/s | ETA {remaining/60:.1f} min")

    conn.commit()
    log.info("-" * 60)
    log.info(f"Computed {done} tickers, skipped {skipped} (under {MIN_BARS} bars), "
             f"{rows_written:,} rows in {(time.time()-started)/60:.1f} min")
    log.info(f"features table: {storage.feature_stats(conn)}")
    if _interrupted:
        log.warning("Run was interrupted — re-run to continue from here.")
    conn.close()


def show_status(config: dict) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)
    types = config["universe"].get("feature_types")
    p, f = storage.price_stats(conn), storage.feature_stats(conn)
    outstanding = len(storage.tickers_needing_features(conn, types=types))
    ineligible = storage.feature_ineligible_count(conn, types=types)
    print(f"prices     : {p['rows']:,} rows | {p['tickers']:,} tickers | "
          f"{p['first_date']} -> {p['last_date']}")
    print(f"features   : {f['rows']:,} rows | {f['tickers']:,} tickers | "
          f"{f['first_date']} -> {f['last_date']}")
    print(f"outstanding: {outstanding:,} tickers")
    print(f"ineligible : {ineligible:,} tickers under {MIN_BARS} bars "
          f"(too recently listed for a 200-day SMA — expected, not missing)")
    if outstanding == 0:
        print("\nFeature coverage is complete.")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="Only process this many tickers.")
    parser.add_argument("--rebuild", action="store_true", help="Delete all features and recompute.")
    parser.add_argument("--status", action="store_true", help="Show coverage and exit.")
    args = parser.parse_args()

    config = load_config()
    if args.status:
        show_status(config)
        return

    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    run(config, limit=args.limit, rebuild=args.rebuild)


if __name__ == "__main__":
    main()
