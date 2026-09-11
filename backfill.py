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
    python backfill.py --retry-failed --period 1y   # rescue instruments too new for max
    python backfill.py --status            # progress, no fetching

For the full run, use nohup — see README.
"""
import runtime  # noqa: F401  — must precede numpy/pandas/xgboost
import argparse
import logging
import random
import signal
import sys
import time

import yfinance as yf
from yfinance.exceptions import YFRateLimitError

import storage
from data_pull import chunked, reshape_to_long
from universe import get_all_us_symbols, load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backfill")

_interrupted = False


class RateLimited(Exception):
    """Yahoo is throttling us and backing off further is not helping."""


class Throttle:
    """
    Adaptive pacing for Yahoo, which publishes no rate limit and no Retry-After.

    Two behaviours that matter:

    - The delay between batches ratchets *up* on every throttling signal and
      decays back down only after sustained success. Yahoo's limit appears to be
      a moving target, so the safe delay is discovered rather than configured.
    - Every sleep carries jitter. Fixed sleeps synchronise retries into bursts,
      which is the pattern most likely to be read as abuse.
    """

    def __init__(self, base_sec: float, jitter_frac: float, growth: float,
                 max_sec: float, recover_after: int = 10):
        self.base = base_sec
        self.current = base_sec
        self.jitter_frac = jitter_frac
        self.growth = growth
        self.max_sec = max_sec
        self.recover_after = recover_after
        self.strikes = 0
        self._clean_batches = 0

    def _jittered(self, seconds: float) -> float:
        spread = seconds * self.jitter_frac
        return max(0.0, seconds + random.uniform(-spread, spread))

    def wait(self) -> None:
        if self.current > 0:
            time.sleep(self._jittered(self.current))

    def penalize(self) -> None:
        """Called on any throttling signal: slow down and remember it."""
        self.strikes += 1
        self._clean_batches = 0
        previous = self.current
        self.current = min(self.current * self.growth if self.current else 1.0, self.max_sec)
        log.warning(f"Throttling signal #{self.strikes}: batch delay {previous:.1f}s -> {self.current:.1f}s")

    def reward(self) -> None:
        """Called after a clean batch: ease back toward the configured pace."""
        self._clean_batches += 1
        if self._clean_batches >= self.recover_after and self.current > self.base:
            self.current = max(self.base, self.current / self.growth)
            self._clean_batches = 0
            log.info(f"Sustained clean batches; easing batch delay to {self.current:.1f}s")

    def backoff(self, attempt: int, first_pause: float) -> None:
        """Escalating pause after a rate-limited request."""
        pause = min(first_pause * (self.growth ** (attempt - 1)), self.max_sec)
        pause = self._jittered(pause)
        log.warning(f"Rate limited — pausing {pause:.0f}s before retry {attempt}")
        time.sleep(pause)


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


def fetch_batch(tickers: list[str], period: str, interval: str, attempts: int,
                backoff: int, throttle: Throttle, rate_limit_pause: float,
                max_strikes: int, threads: bool = True):
    """
    Download one batch with retries. Returns a raw yfinance frame, or None if the
    batch genuinely has no data.

    Raises `RateLimited` when Yahoo is throttling and backing off is not helping.
    That is deliberately not the same outcome as "no data": under throttling the
    right move is to stop the run and resume later, not to mark 50 real tickers
    as permanently failed. Getting that distinction wrong would silently hollow
    out the universe — the tickers would be recorded as having no history when in
    fact we were never allowed to ask.
    """
    for attempt in range(1, attempts + 1):
        try:
            raw = yf.download(
                tickers=tickers, period=period, interval=interval,
                group_by="ticker", auto_adjust=True, threads=threads, progress=False,
            )
            if raw is not None and not raw.empty:
                throttle.reward()
                return raw
            # An empty frame is ambiguous: it means either "these tickers have no
            # data" or "we are being throttled and Yahoo returned nothing". Treat
            # a repeated empty as the latter, since the alternative is failing
            # real tickers.
            log.warning(f"Batch returned empty (attempt {attempt}/{attempts})")
        except YFRateLimitError:
            throttle.penalize()
            if throttle.strikes >= max_strikes:
                raise RateLimited(f"rate limited {throttle.strikes} times")
            if attempt < attempts:
                throttle.backoff(attempt, rate_limit_pause)
            continue
        except Exception as e:
            log.warning(f"Batch failed (attempt {attempt}/{attempts}): {e}")

        if attempt < attempts:
            time.sleep(backoff * attempt * random.uniform(0.8, 1.4))

    return None


def run_backfill(config: dict, limit: int | None = None, retry_failed: bool = False,
                 batch_size: int | None = None, period_override: str | None = None) -> None:
    bcfg = config.get("backfill", {})
    period = period_override or bcfg.get("period", "max")
    interval = bcfg.get("interval", "1d")
    batch_size = batch_size or bcfg.get("batch_size", 50)
    pause = bcfg.get("sleep_between_batches_sec", 1.0)
    attempts = bcfg.get("retry_attempts", 3)
    backoff = bcfg.get("retry_backoff_sec", 5)
    max_ticker_attempts = bcfg.get("max_ticker_attempts", 3)
    threads = bcfg.get("threads", True)
    rate_limit_pause = bcfg.get("rate_limit_backoff_sec", 60)
    max_strikes = bcfg.get("rate_limit_max_strikes", 5)
    empty_streak_limit = bcfg.get("empty_batches_before_stopping", 3)

    throttle = Throttle(
        base_sec=pause,
        jitter_frac=bcfg.get("jitter_frac", 0.3),
        growth=bcfg.get("throttle_growth", 2.0),
        max_sec=bcfg.get("rate_limit_backoff_max_sec", 900),
    )

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
             f"{outstanding} outstanding | fetching {len(todo)} this run | period={period}")
    if not todo:
        log.info("Nothing to do.")
        conn.close()
        return

    started = time.time()
    ok = failed = rows_written = 0
    empty_streak = 0
    rate_limited = False

    for i, batch in enumerate(chunked(todo, batch_size), start=1):
        if _interrupted:
            log.warning("Stopping before batch %d as requested.", i)
            break

        try:
            raw = fetch_batch(batch, period, interval, attempts, backoff, throttle,
                              rate_limit_pause, max_strikes, threads)
        except RateLimited as e:
            log.error(f"Sustained rate limiting ({e}). Stopping so progress is kept — "
                      f"re-run later and it will continue from here.")
            rate_limited = True
            break

        if raw is None:
            empty_streak += 1
            # Several empty batches in a row is far more likely to be throttling
            # than a genuine run of dataless tickers. Back off and stop rather
            # than burning attempts and marking real tickers failed.
            if empty_streak >= empty_streak_limit:
                throttle.penalize()
                log.error(f"{empty_streak} consecutive empty batches — treating as throttling. "
                          f"Stopping without marking these tickers failed; re-run later.")
                rate_limited = True
                break
            for t in batch:
                storage.mark_failed(conn, t, "batch download returned nothing")
            failed += len(batch)
            conn.commit()
            throttle.wait()
            continue

        empty_streak = 0

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

        throttle.wait()

    log.info("-" * 60)
    log.info(f"Fetched {ok} tickers, {failed} failed, {rows_written:,} rows written "
             f"in {(time.time()-started)/60:.1f} min")
    log.info(f"prices table: {storage.price_stats(conn)}")
    log.info(f"ingest state: {storage.ingest_summary(conn)}")
    if _interrupted:
        log.warning("Run was interrupted — re-run to continue from here.")
    if rate_limited:
        log.warning("Run stopped on rate limiting — progress is saved. Wait a while, "
                    "then re-run to continue. Consider raising "
                    "backfill.sleep_between_batches_sec if it recurs.")
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
    parser.add_argument("--period", help="Override the configured period, e.g. 5y, 1y, 5d. "
                                         "Used to rescue instruments too new for period=max.")
    parser.add_argument("--status", action="store_true", help="Show progress and exit.")
    args = parser.parse_args()

    config = load_config()
    runtime.be_nice()

    if args.status:
        show_status(config)
        return

    signal.signal(signal.SIGINT, _handle_interrupt)
    signal.signal(signal.SIGTERM, _handle_interrupt)
    run_backfill(config, limit=args.limit, retry_failed=args.retry_failed,
                 batch_size=args.batch_size, period_override=args.period)


if __name__ == "__main__":
    main()
