"""
Resumable historical backfill: pulls OHLCV history for the full universe into
`data/market_data.db`.

Run it, kill it, run it again — it picks up where it stopped. That is the whole
design goal, not a nicety. A full run is ~6,200 tickers x 20 years against a free
Yahoo endpoint with no SLA, over SSH sessions that have dropped mid-run before.
Anything that has to start from zero after an interruption will never finish.

How resumability works: `ingest_state` holds one row per ticker. A ticker is only
marked 'done' after its rows are committed, and state is committed once per batch,
so a hard kill loses at most one batch of work — never the database's consistency.

Usage:
    python backfill.py --limit 20          # prove the loop on 20 tickers
    python backfill.py                     # full universe
    python backfill.py --retry-failed      # another pass at failures
    python backfill.py --status            # progress, no fetching

For the full run, use nohup — see README.
"""
import argparse
import logging
import signal
import sys
import time

import yfinance as yf

import storage
from data_pull import chunked, reshape_to_long
from universe import get_all_us_symbols, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")

_interrupted = False


def _handle_interrupt(signum, frame):
    """
    Ask the loop to stop after the current batch rather than dying mid-write.

    Second Ctrl-C exits immediately, for when the first is not enough.
    """
    global _interrupted
    if _interrupted:
        log.warning("Second interrupt — exiting now.")
        sys.exit(130)
    _interrupted = True
    log.warning("Interrupt received. Finishing current batch, then stopping cleanly...")


def fetch_batch(tickers: list[str], period: str, interval: str,
                attempts: int, backoff: int):
    """Download one batch with retries. Returns a raw yfinance frame, or None."""
    for attempt in range(1, attempts + 1):
        try:
            raw = yf.download(
                tickers=tickers, period=period, interval=interval,
                group_by="ticker", auto_adjust=True, threads=True, progress=False,
            )
            if raw is not None and not raw.empty:
                return raw
            log.warning(f"Batch returned empty (attempt {attempt}/{attempts})")
        except Exception as e:
            log.warning(f"Batch failed (attempt {attempt}/{attempts}): {e}")
        if attempt < attempts:
            time.sleep(backoff * attempt)
    return None


def run_backfill(config: dict, limit: int | None = None, retry_failed: bool = False,
                 batch_size: int | None = None) -> None:
    bcfg = config.get("backfill", {})
    period = bcfg.get("period", "20y")
    interval = bcfg.get("interval", "1d")
    batch_size = batch_size or bcfg.get("batch_size", 50)
    pause = bcfg.get("sleep_between_batches_sec", 1.0)
    attempts = bcfg.get("retry_attempts", 3)
    backoff = bcfg.get("retry_backoff_sec", 5)
    max_ticker_attempts = bcfg.get("max_ticker_attempts", 3)

    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)

    symbols = get_all_us_symbols(config)
    storage.record_symbols(conn, symbols)
    all_tickers = [s["ticker"] for s in symbols]

    storage.seed_ingest_state(conn, all_tickers)

    if retry_failed:
        conn.execute("UPDATE ingest_state SET status='pending', attempts=0 WHERE status='failed'")
        conn.commit()
        log.info("Reset failed tickers to pending.")

    todo = storage.pending_tickers(conn, all_tickers, max_attempts=max_ticker_attempts)
    # Count before --limit truncates, or the summary reports skipped tickers as
    # finished ones.
    outstanding = len(todo)
    done_already = len(all_tickers) - outstanding
    if limit:
        todo = todo[:limit]

    log.info(f"Universe {len(all_tickers)} tickers | {done_already} done | "
             f"{outstanding} outstanding | fetching {len(todo)} this run")
    if not todo:
        log.info("Nothing to do.")
        conn.close()
        return

    started = time.time()
    ok = failed = rows_written = 0

    for i, batch in enumerate(chunked(todo, batch_size), start=1):
        if _interrupted:
            log.warning("Stopping before batch %d as requested.", i)
            break

        raw = fetch_batch(batch, period, interval, attempts, backoff)
        if raw is None:
            for t in batch:
                storage.mark_failed(conn, t, "batch download returned nothing")
            failed += len(batch)
            conn.commit()
            continue

        long_df = reshape_to_long(raw, batch)

        if long_df.empty:
            for t in batch:
                storage.mark_failed(conn, t, "no rows after reshape")
            failed += len(batch)
        else:
            long_df = long_df.dropna(subset=["close"])
            present = set(long_df["ticker"].unique())

            for ticker in batch:
                if ticker not in present:
                    # Symbol is in the listing directory but Yahoo serves nothing
                    # for it. Common for very recent listings.
                    storage.mark_failed(conn, ticker, "no data returned for ticker")
                    failed += 1
                    continue

                sub = long_df[long_df["ticker"] == ticker]
                n = storage.upsert_prices(conn, sub)
                storage.mark_done(conn, ticker, str(sub["date"].min())[:10],
                                  str(sub["date"].max())[:10], n)
                rows_written += n
                ok += 1

        # One commit per batch: the resumability boundary.
        conn.commit()

        elapsed = time.time() - started
        processed = ok + failed
        rate = processed / elapsed if elapsed else 0
        remaining = (len(todo) - processed) / rate if rate else 0
        log.info(
            f"batch {i} | {processed}/{len(todo)} tickers | {rows_written:,} rows | "
            f"{failed} failed | {rate:.1f} tickers/s | ETA {remaining/60:.1f} min"
        )

        if pause:
            time.sleep(pause)

    log.info("-" * 60)
    log.info(f"Fetched {ok} tickers, {failed} failed, {rows_written:,} rows written "
             f"in {(time.time()-started)/60:.1f} min")
    log.info(f"prices table: {storage.price_stats(conn)}")
    log.info(f"ingest state: {storage.ingest_summary(conn)}")
    if _interrupted:
        log.warning("Run was interrupted — re-run to continue from here.")
    conn.close()


def show_status(config: dict) -> None:
    conn = storage.connect(config["database"]["market_data_path"])
    storage.init_db(conn)
    stats = storage.price_stats(conn)
    summary = storage.ingest_summary(conn)
    print(f"prices : {stats['rows']:,} rows | {stats['tickers']:,} tickers | "
          f"{stats['first_date']} -> {stats['last_date']}")
    print(f"ingest : {summary or 'nothing seeded yet'}")
    failures = conn.execute("""
        SELECT ticker, attempts, last_error FROM ingest_state
        WHERE status='failed' ORDER BY ticker LIMIT 10
    """).fetchall()
    if failures:
        print(f"\nfirst {len(failures)} failures:")
        for r in failures:
            print(f"  {r['ticker']:8s} attempts={r['attempts']}  {r['last_error']}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--limit", type=int, help="Only fetch this many tickers (for testing).")
    parser.add_argument("--batch-size", type=int, help="Override config batch size.")
    parser.add_argument("--retry-failed", action="store_true", help="Reset failed tickers and retry.")
    parser.add_argument("--status", action="store_true", help="Show progress and exit.")
    args = parser.parse_args()

    config = load_config()

    if args.status:
        show_status(config)
        return

    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    run_backfill(config, limit=args.limit, retry_failed=args.retry_failed,
                 batch_size=args.batch_size)


if __name__ == "__main__":
    main()
