"""
Owns the market-data database (`data/market_data.db`).

This is the only module that writes SQL against it. Everything else goes through
these helpers, so schema changes have exactly one place to happen.

Deliberately separate from `position_tracking.py` / `positions.db`, which is the
trade ledger — "what the system actually did". This database is market history:
large, regenerable, and rebuilt by re-running the backfill. Losing it costs time;
losing the ledger loses the record of real trades.

Tables:
  prices        OHLCV bars, PK (ticker, date), upserted so reruns update rather
                than duplicate.
  features      Derived indicators, same key. Schema is created here but stays
                empty until the pipeline is repointed off Parquet.
  symbols       Ticker registry with first_seen / last_seen, so that from now on
                we can tell when a symbol leaves the listings.
  ingest_state  Per-ticker backfill progress. This is what makes the long
                backfill resumable.
"""
import logging
import sqlite3
from datetime import date

import pandas as pd

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("storage")

PRICE_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume", "source"]


def connect(db_path: str) -> sqlite3.Connection:
    """
    Open the market-data database with settings tuned for a long bulk load.

    WAL keeps the database readable while a multi-hour backfill is writing.
    synchronous=NORMAL trades a little crash durability for a large speed gain,
    which is the right trade here: the data is re-fetchable, and the backfill is
    resumable anyway.
    """
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA cache_size=-64000")  # ~64 MB page cache
    return conn


def init_db(conn: sqlite3.Connection) -> None:
    """Create every table if absent. Safe to call on every run."""
    # WITHOUT ROWID: the primary key IS the access pattern (one ticker's bars in
    # date order), so the usual hidden rowid table would be a wasted second copy
    # of ~31M rows. STRICT rejects type-confused writes at insert time.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS prices (
            ticker  TEXT    NOT NULL,
            date    TEXT    NOT NULL,
            open    REAL,
            high    REAL,
            low     REAL,
            close   REAL,
            volume  INTEGER,
            source  TEXT    NOT NULL DEFAULT 'yfinance',
            PRIMARY KEY (ticker, date)
        ) STRICT, WITHOUT ROWID
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS symbols (
            ticker      TEXT PRIMARY KEY,
            name        TEXT,
            exchange    TEXT,
            first_seen  TEXT NOT NULL,
            last_seen   TEXT NOT NULL,
            is_active   INTEGER NOT NULL DEFAULT 1
        ) STRICT
    """)

    conn.execute("""
        CREATE TABLE IF NOT EXISTS ingest_state (
            ticker      TEXT PRIMARY KEY,
            first_date  TEXT,
            last_date   TEXT,
            row_count   INTEGER NOT NULL DEFAULT 0,
            status      TEXT    NOT NULL DEFAULT 'pending',
            attempts    INTEGER NOT NULL DEFAULT 0,
            last_error  TEXT,
            updated_at  TEXT    NOT NULL
        ) STRICT
    """)

    # Progress queries scan by status; without this they table-scan 6k rows on
    # every batch.
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ingest_status ON ingest_state(status)")

    _init_features_table(conn)
    conn.commit()


def _init_features_table(conn: sqlite3.Connection) -> None:
    """
    Create the features table from the canonical column list.

    FEATURE_COLS lives in train_model.py, which owns it. Imported lazily so that
    `storage` stays importable without pulling in xgboost and scikit-learn.
    """
    from train_model import FEATURE_COLS

    cols = ",\n            ".join(f"{c} REAL" for c in FEATURE_COLS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS features (
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,
            {cols},
            PRIMARY KEY (ticker, date)
        ) STRICT, WITHOUT ROWID
    """)


# --------------------------------------------------------------------------
# Prices
# --------------------------------------------------------------------------

_UPSERT_PRICES = """
    INSERT INTO prices (ticker, date, open, high, low, close, volume, source)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    ON CONFLICT(ticker, date) DO UPDATE SET
        open=excluded.open, high=excluded.high, low=excluded.low,
        close=excluded.close, volume=excluded.volume, source=excluded.source
"""


def upsert_prices(conn: sqlite3.Connection, df: pd.DataFrame, source: str = "yfinance") -> int:
    """
    Upsert a long-format OHLCV frame (one row per ticker/date).

    Returns rows written. Re-running with the same data updates in place and
    leaves the row count unchanged — the idempotency the project requires of
    every pipeline stage.
    """
    if df.empty:
        return 0

    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")

    rows = []
    for r in frame.itertuples(index=False):
        volume = getattr(r, "volume", None)
        rows.append((
            str(r.ticker),
            str(r.date),
            _as_float(r.open), _as_float(r.high), _as_float(r.low), _as_float(r.close),
            None if pd.isna(volume) else int(volume),
            source,
        ))

    conn.executemany(_UPSERT_PRICES, rows)
    return len(rows)


def _as_float(v):
    return None if pd.isna(v) else float(v)


def price_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute("""
        SELECT COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers,
               MIN(date) AS first_date, MAX(date) AS last_date
        FROM prices
    """).fetchone()
    return dict(row)


def ticker_price_range(conn: sqlite3.Connection, ticker: str) -> dict | None:
    row = conn.execute("""
        SELECT COUNT(*) AS rows, MIN(date) AS first_date, MAX(date) AS last_date
        FROM prices WHERE ticker = ?
    """, (ticker,)).fetchone()
    return dict(row) if row and row["rows"] else None


# --------------------------------------------------------------------------
# Symbol registry
# --------------------------------------------------------------------------

def record_symbols(conn: sqlite3.Connection, symbols: list[dict], seen_on: str | None = None) -> int:
    """
    Record today's listing snapshot.

    first_seen is preserved across runs; last_seen advances. A ticker that stops
    appearing keeps its old last_seen, which is how we will later identify
    delistings — see the survivorship-bias note in CLAUDE.md. This does not
    recover history that yfinance never served, but it stops the gap widening
    from today forward.
    """
    seen_on = seen_on or date.today().isoformat()
    rows = [
        (s["ticker"], s.get("name"), s.get("exchange"), seen_on, seen_on)
        for s in symbols
    ]
    conn.executemany("""
        INSERT INTO symbols (ticker, name, exchange, first_seen, last_seen, is_active)
        VALUES (?, ?, ?, ?, ?, 1)
        ON CONFLICT(ticker) DO UPDATE SET
            name=excluded.name, exchange=excluded.exchange,
            last_seen=excluded.last_seen, is_active=1
    """, rows)

    # Anything not in today's snapshot is no longer listed.
    conn.execute("UPDATE symbols SET is_active=0 WHERE last_seen < ?", (seen_on,))
    conn.commit()
    return len(rows)


# --------------------------------------------------------------------------
# Ingest state (resumability)
# --------------------------------------------------------------------------

def seed_ingest_state(conn: sqlite3.Connection, tickers: list[str]) -> int:
    """Register tickers as pending without disturbing rows already completed."""
    now = _now()
    conn.executemany(
        "INSERT OR IGNORE INTO ingest_state (ticker, status, updated_at) VALUES (?, 'pending', ?)",
        [(t, now) for t in tickers],
    )
    conn.commit()
    return conn.execute("SELECT COUNT(*) FROM ingest_state WHERE status='pending'").fetchone()[0]


def pending_tickers(conn: sqlite3.Connection, tickers: list[str], max_attempts: int = 3) -> list[str]:
    """
    Which of `tickers` still need fetching.

    Excludes anything already done, and anything that has failed too many times —
    a handful of symbols in the directory simply have no Yahoo data, and retrying
    them forever would stall the run.
    """
    placeholders = ",".join("?" * len(tickers))
    rows = conn.execute(f"""
        SELECT ticker FROM ingest_state
        WHERE ticker IN ({placeholders})
          AND status != 'done'
          AND attempts < ?
    """, (*tickers, max_attempts)).fetchall()
    known = {r["ticker"] for r in rows}

    seeded = {r["ticker"] for r in conn.execute(
        f"SELECT ticker FROM ingest_state WHERE ticker IN ({placeholders})", tickers
    ).fetchall()}
    unseeded = [t for t in tickers if t not in seeded]

    return [t for t in tickers if t in known or t in unseeded]


def mark_done(conn: sqlite3.Connection, ticker: str, first_date: str, last_date: str, row_count: int) -> None:
    conn.execute("""
        INSERT INTO ingest_state (ticker, first_date, last_date, row_count, status, attempts, last_error, updated_at)
        VALUES (?, ?, ?, ?, 'done', COALESCE((SELECT attempts FROM ingest_state WHERE ticker=?), 0), NULL, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            first_date=excluded.first_date, last_date=excluded.last_date,
            row_count=excluded.row_count, status='done', last_error=NULL,
            updated_at=excluded.updated_at
    """, (ticker, first_date, last_date, row_count, ticker, _now()))


def mark_failed(conn: sqlite3.Connection, ticker: str, error: str) -> None:
    conn.execute("""
        INSERT INTO ingest_state (ticker, status, attempts, last_error, updated_at)
        VALUES (?, 'failed', 1, ?, ?)
        ON CONFLICT(ticker) DO UPDATE SET
            status='failed', attempts=ingest_state.attempts + 1,
            last_error=excluded.last_error, updated_at=excluded.updated_at
    """, (ticker, error[:500], _now()))


def ingest_summary(conn: sqlite3.Connection) -> dict:
    rows = conn.execute("SELECT status, COUNT(*) AS n FROM ingest_state GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def _now() -> str:
    return pd.Timestamp.utcnow().strftime("%Y-%m-%d %H:%M:%S")


if __name__ == "__main__":
    from universe import load_config

    cfg = load_config()
    path = cfg["database"]["market_data_path"]
    conn = connect(path)
    init_db(conn)
    log.info(f"Initialized market data DB at {path}")
    log.info(f"prices: {price_stats(conn)}")
    log.info(f"ingest: {ingest_summary(conn) or 'empty'}")
    conn.close()
