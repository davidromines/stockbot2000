"""
Crypto OHLCV into its own table. Phase 12, items 38 and 39.

WHY A SEPARATE TABLE
---------------------
`prices` has one consumer assumption baked into every query that reads it: US
market sessions. `backfill.last_market_session()` asks a liquid ETF for the
newest completed session, `freshness.py` fails a run when that session is
behind, `simulator.py` fills at the next session's open, and the null surface
is computed over session-indexed holding periods.

Crypto trades continuously. Putting a 24/7 instrument into `prices` would not
raise an error anywhere — it would silently make "the last completed session"
ambiguous, give every equity a spurious weekend neighbour in the freshness
check, and change what "45 days" means in the benchmark. So crypto lives in
`crypto_prices`, and `symbols.security_type` is 'crypto' so the equity screens
keep excluding it through the `tradeable_types` filter they already apply.

THE SESSION CONVENTION, DECIDED EXPLICITLY
--------------------------------------------
Item 39 blocks the rest of the phase, because the fill convention is where this
project took its largest single correction: the classifier went from +$1.63 to
-$58.77 gross once signals stopped filling at the close that produced them.

Crypto has no close and no next open, so the equity rule cannot be inherited
unmodified. The decision recorded here:

    A BAR IS A SESSION. A signal computed from a bar's close fills at the NEXT
    BAR'S OPEN, at whatever interval the data was fetched.

That preserves the property that matters — you cannot trade on a price until
after the bar that produced it has closed — without pretending a 00:00 UTC
boundary means something to a market that does not stop. `BAR_SECONDS` is
stored with the data so a consumer can never guess the interval wrong: a
strategy backtested on 1h bars and run on 1d bars is two different strategies.

SOURCE
------
Coinbase Exchange public candles. Binance was the first choice — it is what the
SETS repository uses — but it answers **HTTP 451, Unavailable For Legal
Reasons**, from this host, which is a jurisdiction block rather than a
transient failure and is not worth routing around. Coinbase is US-accessible,
needs no key and no account.

Its candle format differs from Binance's in three ways that each cause a silent
error if assumed rather than checked: the row is
`[time, low, high, open, close, volume]` — low and high come BEFORE open and
close — rows arrive NEWEST FIRST, and a request returns at most 300 candles
regardless of what is asked for.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("crypto")

BASE = "https://api.exchange.coinbase.com/products"
DEFAULT_PAIRS = ("BTC-USD", "ETH-USD", "SOL-USD", "XRP-USD", "ADA-USD",
                 "AVAX-USD", "LINK-USD", "DOT-USD", "LTC-USD", "MATIC-USD")
INTERVAL_SECONDS = {"1h": 3600, "6h": 21600, "1d": 86400}
MAX_CANDLES = 300      # Coinbase's hard cap per request, whatever is asked


PRODUCTS = "https://api.exchange.coinbase.com/products"


def record_status(conn, symbols=None) -> dict:
    """
    Record each pair's listing status from the exchange, at load time.

    **This is the survivorship record the equity side had to reconstruct.**
    For US equities this project replays 114 Internet Archive snapshots to
    guess which tickers existed on a date, and still only prices 22.6% of the
    knowable 2008 universe — because yfinance serves no delisted ticker and
    the record had to be rebuilt backwards from whatever survived.

    Coinbase answers the question directly: MATIC-USD reports
    `status: delisted, trading_disabled: true`. Capturing that on every load
    means the crypto side starts with a point-in-time listing record instead of
    spending months rebuilding one, and a backtest can know a pair stopped
    trading rather than inferring it from the data simply stopping.

    `last_seen` advances on every run, so a pair that vanishes from the
    products list leaves a dated final observation behind.
    """
    init(conn)
    try:
        req = urllib.request.Request(
            PRODUCTS, headers={"User-Agent": "stockbot2000/1.0"})
        with urllib.request.urlopen(req, timeout=30) as r:
            products = {p["id"]: p for p in json.loads(r.read().decode())}
    except Exception as e:      # noqa: BLE001
        log.warning(f"product list unavailable: {type(e).__name__}: {e}")
        return {"checked": 0, "delisted": 0}

    today = datetime.now(timezone.utc).date().isoformat()
    wanted = symbols or [r[0] for r in conn.execute(
        "SELECT DISTINCT symbol FROM crypto_prices")]
    delisted = 0
    for sym in wanted:
        p = products.get(sym)
        if p is None:
            # Absent from the product list entirely: it is gone, and the last
            # date we saw it is the most honest thing we can record.
            status, disabled = "absent", 1
        else:
            status = p.get("status") or "unknown"
            disabled = 1 if p.get("trading_disabled") else 0
        delisted += 1 if (status != "online" or disabled) else 0
        conn.execute("""INSERT INTO crypto_listings
            (symbol, status, trading_disabled, first_seen, last_seen)
            VALUES (?,?,?,?,?)
            ON CONFLICT(symbol) DO UPDATE SET
              status=excluded.status,
              trading_disabled=excluded.trading_disabled,
              last_seen=excluded.last_seen""",
            (sym, status, disabled, today, today))
    conn.commit()
    return {"checked": len(wanted), "delisted": delisted}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_prices (
            symbol       TEXT NOT NULL,
            open_time    INTEGER NOT NULL,   -- epoch seconds, bar OPEN
            interval     TEXT NOT NULL,
            bar_seconds  INTEGER NOT NULL,
            open REAL, high REAL, low REAL, close REAL,
            volume REAL, quote_volume REAL, trades INTEGER,
            source       TEXT DEFAULT 'coinbase',
            PRIMARY KEY (symbol, interval, open_time)
        ) WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_listings (
            symbol           TEXT PRIMARY KEY,
            status           TEXT NOT NULL,
            trading_disabled INTEGER NOT NULL,
            first_seen       TEXT NOT NULL,
            last_seen        TEXT NOT NULL
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_cp_sym "
                 "ON crypto_prices(symbol, open_time)")
    conn.commit()


def _fetch(symbol: str, interval: str, start_s: int | None,
            end_s: int | None = None) -> list:
    """
    One page of candles, oldest first.

    Coinbase returns newest-first and caps at 300 rows, so the caller walks
    FORWARD by requesting an explicit [start, end] window rather than paging
    from a cursor. Reversing here means every caller downstream sees the same
    oldest-first order the equity loader produces.
    """
    bar_s = INTERVAL_SECONDS[interval]
    q = {"granularity": bar_s}
    if start_s is not None:
        q["start"] = datetime.fromtimestamp(start_s, timezone.utc).isoformat()
        q["end"] = datetime.fromtimestamp(
            end_s if end_s is not None else start_s + bar_s * MAX_CANDLES,
            timezone.utc).isoformat()
    req = urllib.request.Request(
        f"{BASE}/{symbol}/candles?{urllib.parse.urlencode(q)}",
        headers={"User-Agent": "stockbot2000/1.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        rows = json.loads(r.read().decode())
    return sorted(rows, key=lambda k: k[0])


def _ohlc(k):
    """
    (open, high, low, close) from a Coinbase candle.

    The row is [time, low, high, open, close, volume]. Reading it in Binance's
    order — open, high, low, close at 1..4 — would swap low with open and high
    with close, producing bars that pass a naive range check while being wrong,
    on every single row.
    """
    return float(k[3]), float(k[2]), float(k[1]), float(k[4])


def _valid(k) -> bool:
    """
    Reject impossible bars at write time, as storage.is_valid_ohlcv does for
    equities. The equity loader learned this the expensive way: yfinance
    returns negative prices for some adjusted series, and a guard at the write
    is the only place that catches it before it reaches a backtest.
    """
    try:
        o, h, l, c = _ohlc(k)
    except (TypeError, ValueError, IndexError):
        return False
    if min(o, h, l, c) <= 0:
        return False
    return l <= min(o, c) and h >= max(o, c) and h >= l


def load(conn, symbols=DEFAULT_PAIRS, interval: str = "1h",
         max_bars: int = 20000, rate: float = 0.35) -> dict:
    """
    Resumable: each symbol continues from the newest bar already stored.
    Re-running is a no-op once current, which the project requires of every
    stage.
    """
    init(conn)
    if interval not in INTERVAL_SECONDS:
        raise SystemExit(f"unsupported interval {interval!r}; "
                         f"have {sorted(INTERVAL_SECONDS)}")
    bar_s = INTERVAL_SECONDS[interval]
    now_s = int(time.time())
    written = rejected = 0

    for sym in symbols:
        have = conn.execute(
            "SELECT MAX(open_time) FROM crypto_prices WHERE symbol=? AND interval=?",
            (sym, interval)).fetchone()[0]
        start_ms = ((have + bar_s) * 1000) if have else None
        got = 0
        # Walk forward in explicit windows. Coinbase has no cursor and caps
        # each response at 300 rows, so the loop owns the clock.
        cur = (have + bar_s) if have else int(time.time()) - bar_s * max_bars
        while got < max_bars and cur < int(time.time()):
            end = min(cur + bar_s * MAX_CANDLES, int(time.time()))
            try:
                ks = _fetch(sym, interval, cur, end)
            except Exception as e:      # noqa: BLE001
                log.warning(f"{sym}: {type(e).__name__}: {e}")
                break
            rows = []
            for k in ks:
                ot = int(k[0])
                # The newest candle is the bar IN PROGRESS. Storing it would
                # put a partial close in the table, the same defect the equity
                # loader avoids by excluding today's bar.
                if ot + bar_s > now_s:
                    continue
                if not _valid(k):
                    rejected += 1
                    continue
                o, h, l, c = _ohlc(k)
                rows.append((sym, ot, interval, bar_s, o, h, l, c,
                             float(k[5]), 0.0, 0, "coinbase"))
            if rows:
                conn.executemany(
                    "INSERT OR REPLACE INTO crypto_prices (symbol, open_time, "
                    "interval, bar_seconds, open, high, low, close, volume, "
                    "quote_volume, trades, source) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                    rows)
                conn.commit()
                written += len(rows)
                got += len(rows)
            cur = end
            time.sleep(rate)
        log.info(f"  {sym}: {got:,} new bars")

    # Register in `symbols` so security_type filters keep crypto out of the
    # equity screens by default rather than by anyone remembering to exclude it.
    for sym in symbols:
        conn.execute(
            "INSERT OR IGNORE INTO symbols (ticker, security_type) VALUES (?,?)",
            (sym, "crypto"))
    conn.commit()
    st = record_status(conn, list(symbols))
    return {"written": written, "rejected": rejected, "symbols": len(symbols),
            "interval": interval, "delisted": st["delisted"]}


def coverage(conn, interval: str = "1h") -> list:
    init(conn)
    return [dict(r) for r in conn.execute("""
        SELECT symbol, COUNT(*) bars, MIN(open_time) first, MAX(open_time) last
        FROM crypto_prices WHERE interval=? GROUP BY symbol ORDER BY symbol""",
        (interval,))]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--interval", default="1h")
    ap.add_argument("--max-bars", type=int, default=20000)
    ap.add_argument("--symbols", nargs="*")
    ap.add_argument("--status", action="store_true",
                    help="refresh listing status from the exchange")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.load:
        r = load(conn, a.symbols or DEFAULT_PAIRS, a.interval, a.max_bars)
        print(f"\n  wrote {r['written']:,} bars across {r['symbols']} symbols "
              f"at {r['interval']}"
              + (f", rejected {r['rejected']} impossible bars" if r["rejected"] else ""))

    if a.status:
        st = record_status(conn)
        print(f"\n  recorded listing status for {st['checked']} pairs "
              f"({st['delisted']} not trading)")

    listings = {r["symbol"]: r for r in conn.execute(
        "SELECT * FROM crypto_listings")}
    rows = coverage(conn, a.interval)
    print(f"\n  CRYPTO COVERAGE — {a.interval}")
    print("  " + "-" * 70)
    for r in rows:
        f = datetime.fromtimestamp(r["first"], timezone.utc).date()
        l = datetime.fromtimestamp(r["last"], timezone.utc).date()
        li = listings.get(r["symbol"])
        flag = ""
        if li and (li["status"] != "online" or li["trading_disabled"]):
            flag = f"   {li['status'].upper()}"
        print(f"  {r['symbol']:<12}{r['bars']:>8,} bars   {f} .. {l}{flag}")
    if not rows:
        print("  nothing loaded yet — run with --load")
    gone = [s for s, li in listings.items()
            if li["status"] != "online" or li["trading_disabled"]]
    if gone:
        print(f"\n  {len(gone)} pair(s) no longer trading: {', '.join(sorted(gone))}")
        print("  Their history is kept. A backtest that silently drops them")
        print("  measures only the pairs that survived — which is the bias the")
        print("  equity side spends 114 Internet Archive snapshots fighting.")
    print("\n  A bar is a session: a signal from a bar's close fills at the")
    print("  NEXT bar's open. bar_seconds travels with every row, because a")
    print("  strategy backtested on 1h and run on 1d is two strategies.\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
