"""
FINSABER validation dataset: importer and provider.

FINSABER is an S&P 500 daily price series, 2000-2024, that includes delisted
companies. That inclusion is the whole point: the primary database's
survivorship bias is its largest known defect (22.6% of the knowable 2008
universe is priceable here), and a dataset that kept the companies that died is
the only way to measure how much of an apparent edge is that bias.

It is a SECONDARY VALIDATION dataset. It lives in its own SQLite file and is
never written into the primary database, never replaces the `prices` table, and
is never joined to it. The two have different adjustment conventions and
different universes; a join would produce a series that is neither.

The download is not this module's job. `import_csv` reads a path it is given.
"""
import runtime  # noqa: F401  — must precede numpy/pandas. Both modules
                #   have a __main__ block, so they are entry points too.
import argparse
import hashlib
import logging
import os
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

import data_providers as dp

log = logging.getLogger("finsaber")

DEFAULT_DB = "data/finsaber.db"

# Canonical column names, and the aliases seen in the wild for the adjusted
# close. Matched case-insensitively after stripping whitespace and underscores,
# because the published files differ on all three.
REQUIRED_COLUMNS = ["date", "symbol", "open", "high", "low", "close",
                    "adjusted_close", "volume"]
COLUMN_ALIASES = {
    "adjclose": "adjusted_close",
    "adj_close": "adjusted_close",
    "adj close": "adjusted_close",
    "adjustedclose": "adjusted_close",
    "adjusted_close": "adjusted_close",
}

# Rows are rejected, not repaired. A non-positive close or an inverted high/low
# is a physically impossible bar, and the primary database rejects the same
# shapes at write time (see storage.is_valid_ohlcv). Accepting them here would
# make the validation set easier to trade than the real one, which is exactly
# the direction that flatters a strategy.
def _valid(frame: pd.DataFrame) -> pd.Series:
    return (
        frame["close"].notna() & (frame["close"] > 0)
        & frame["open"].notna() & (frame["open"] > 0)
        & frame["high"].notna() & (frame["high"] > 0)
        & frame["low"].notna() & (frame["low"] > 0)
        & (frame["high"] >= frame["low"])
    )


def connect(db_path: str = DEFAULT_DB) -> sqlite3.Connection:
    conn = sqlite3.connect(db_path, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    return conn


def init(conn: sqlite3.Connection) -> None:
    """Create both tables if absent. Safe to call on every run."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS finsaber_prices (
            symbol    TEXT NOT NULL,
            date      TEXT NOT NULL,
            open      REAL,
            high      REAL,
            low       REAL,
            close     REAL,
            adj_close REAL,
            volume    REAL,
            PRIMARY KEY (symbol, date)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS finsaber_import (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            source_path   TEXT,
            sha256        TEXT,
            rows_read     INTEGER,
            rows_written  INTEGER,
            rows_rejected INTEGER,
            first_date    TEXT,
            last_date     TEXT,
            symbols       INTEGER,
            imported_at   TEXT
        )
    """)
    conn.commit()


def _normalise_columns(columns) -> dict:
    """
    Map the file's header onto canonical names, or fail naming what is missing.

    Failing loudly matters more than it looks. A file whose adjusted column is
    named `adj close` would otherwise import with `adjusted_close` absent, and
    every `adjusted_bars` call would return NaN closes that look like missing
    data rather than a misread header.
    """
    mapping = {}
    for c in columns:
        key = str(c).strip().lower()
        key = COLUMN_ALIASES.get(key, key)
        mapping[c] = key
    present = set(mapping.values())
    missing = [c for c in REQUIRED_COLUMNS if c not in present]
    if missing:
        raise ValueError(
            f"FINSABER CSV is missing required column(s): {missing}. "
            f"Found: {sorted(present)}")
    return mapping


def _sha256(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


_UPSERT = """
    INSERT OR REPLACE INTO finsaber_prices
        (symbol, date, open, high, low, close, adj_close, volume)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
"""


def import_csv(conn: sqlite3.Connection, path: str, chunksize: int = 200_000) -> dict:
    """
    Import one FINSABER CSV, in chunks.

    Never reads the whole file: it is ~253 MB and the pandas object overhead on
    a full read is several times that (see storage._read_downcast for the
    measured ratio). Chunking also makes the import interruptible without
    losing the work already committed.

    Idempotent by construction — `INSERT OR REPLACE` on (symbol, date) means a
    second run of the same file leaves the row count unchanged. The
    `finsaber_import` table gains a row per run, which is the record of what was
    imported and when, not a duplicate of the data.
    """
    if not os.path.exists(path):
        raise FileNotFoundError(f"FINSABER CSV not found: {path}")

    init(conn)
    digest = _sha256(path)

    rows_read = rows_written = rows_rejected = 0
    first_date = last_date = None
    symbols: set = set()

    reader = pd.read_csv(path, chunksize=chunksize, dtype=str,
                         keep_default_na=False, na_values=[""])
    for chunk in reader:
        chunk = chunk.rename(columns=_normalise_columns(chunk.columns))
        rows_read += len(chunk)

        # Dates are normalised before validation so a malformed date is rejected
        # with the rest rather than crashing the run mid-file.
        chunk["date"] = pd.to_datetime(chunk["date"], errors="coerce")
        for c in ("open", "high", "low", "close", "adjusted_close", "volume"):
            chunk[c] = pd.to_numeric(chunk[c], errors="coerce")

        ok = _valid(chunk) & chunk["date"].notna()
        rejected = int((~ok).sum())
        if rejected:
            rows_rejected += rejected
            log.warning(f"Rejected {rejected} impossible rows in {os.path.basename(path)}")
        chunk = chunk.loc[ok]
        if chunk.empty:
            continue

        chunk["date"] = chunk["date"].dt.strftime("%Y-%m-%d")
        chunk["symbol"] = chunk["symbol"].astype(str).str.strip()

        lo, hi = chunk["date"].min(), chunk["date"].max()
        first_date = lo if first_date is None or lo < first_date else first_date
        last_date = hi if last_date is None or hi > last_date else last_date
        symbols.update(chunk["symbol"].unique())

        rows = [
            (r.symbol, r.date, _f(r.open), _f(r.high), _f(r.low), _f(r.close),
             _f(r.adjusted_close), _f(r.volume))
            for r in chunk.itertuples(index=False)
        ]
        conn.executemany(_UPSERT, rows)
        conn.commit()
        rows_written += len(rows)

    conn.execute("""
        INSERT INTO finsaber_import (source_path, sha256, rows_read, rows_written,
                                     rows_rejected, first_date, last_date, symbols,
                                     imported_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (os.path.abspath(path), digest, rows_read, rows_written, rows_rejected,
          first_date, last_date, len(symbols), _now()))
    conn.commit()

    stats = {"source_path": os.path.abspath(path), "sha256": digest,
             "rows_read": rows_read, "rows_written": rows_written,
             "rows_rejected": rows_rejected, "first_date": first_date,
             "last_date": last_date, "symbols": len(symbols)}
    log.info(f"Imported {rows_written:,} rows ({rows_rejected:,} rejected) "
             f"from {os.path.basename(path)}")
    return stats


def _f(v):
    return None if v is None or pd.isna(v) else float(v)


def _now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")


def coverage(conn: sqlite3.Connection) -> dict:
    row = conn.execute("""
        SELECT COUNT(*) AS bars, COUNT(DISTINCT symbol) AS securities,
               MIN(date) AS first_date, MAX(date) AS last_date
        FROM finsaber_prices
    """).fetchone()
    return {"name": "finsaber", "first_date": row["first_date"],
            "last_date": row["last_date"], "securities": row["securities"],
            "bars": row["bars"]}


def imports(conn: sqlite3.Connection) -> list[dict]:
    return [dict(r) for r in conn.execute(
        "SELECT * FROM finsaber_import ORDER BY id").fetchall()]


class FinsaberProvider(dp.DataProvider):
    """
    Read-only access to the FINSABER database.

    `daily_bars` returns `close`, NOT `adj_close`. The primary database's
    `prices.close` is split/dividend-adjusted by yfinance, and FINSABER's
    `adjusted_close` is adjusted on a different basis; comparing a strategy's
    returns across the two datasets requires the same convention on both sides,
    and the primary side is fixed. `adjusted_bars` exposes the other column for
    callers that specifically want FINSABER's own adjustment.
    """

    def __init__(self, db_path: str = DEFAULT_DB):
        self.db_path = db_path
        self.conn = connect(db_path)

    def name(self) -> str:
        return "finsaber"

    def _bars(self, tickers: list | None, start: str, end: str, price_col: str) -> pd.DataFrame:
        where = ["date BETWEEN ? AND ?"]
        params: list = [start, end]
        if tickers is not None:
            tickers = list(tickers)
            if not tickers:
                return dp._empty_bars()
            frames = []
            for i in range(0, len(tickers), 900):
                block = tickers[i:i + 900]
                ph = ",".join("?" * len(block))
                frames.append(pd.read_sql_query(
                    f"SELECT symbol AS ticker, date, open, high, low, "
                    f"{price_col} AS close, volume FROM finsaber_prices "
                    f"WHERE {' AND '.join(where)} AND symbol IN ({ph}) "
                    f"ORDER BY symbol, date",
                    self.conn, params=params + block))
            return dp._shape(pd.concat(frames, ignore_index=True) if frames else dp._empty_bars())

        return dp._shape(pd.read_sql_query(
            f"SELECT symbol AS ticker, date, open, high, low, "
            f"{price_col} AS close, volume FROM finsaber_prices "
            f"WHERE {' AND '.join(where)} ORDER BY symbol, date",
            self.conn, params=params))

    def daily_bars(self, tickers: list | None, start: str, end: str) -> pd.DataFrame:
        return self._bars(tickers, start, end, "close")

    def adjusted_bars(self, tickers: list | None, start: str, end: str) -> pd.DataFrame:
        return self._bars(tickers, start, end, "adj_close")

    def universe(self, on_date: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT symbol FROM finsaber_prices WHERE date = ? ORDER BY symbol",
            (on_date,)).fetchall()
        return [r[0] for r in rows]

    def coverage(self) -> dict:
        return coverage(self.conn)


# Registered on import, as the task requires. The factory takes no arguments so
# `dp.get("finsaber")` uses DEFAULT_DB; pass db_path explicitly for any other file.
dp.register("finsaber", FinsaberProvider)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="FINSABER validation dataset importer")
    ap.add_argument("--import", dest="import_path", metavar="PATH",
                    help="CSV file to import")
    ap.add_argument("--db", default=DEFAULT_DB, help=f"SQLite file (default {DEFAULT_DB})")
    ap.add_argument("--status", action="store_true", help="print coverage and exit")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO)

    if args.import_path:
        if not os.path.exists(args.import_path):
            print(f"error: no such file: {args.import_path}", file=sys.stderr)
            return 2
        conn = connect(args.db)
        stats = import_csv(conn, args.import_path)
        for k, v in stats.items():
            print(f"{k}: {v}")
        conn.close()
        return 0

    if args.status:
        if not os.path.exists(args.db):
            print(f"error: no such database: {args.db}", file=sys.stderr)
            return 2
        conn = connect(args.db)
        cov = coverage(conn)
        for k, v in cov.items():
            print(f"{k}: {v}")
        for row in imports(conn):
            print(f"import {row['id']}: {row['source_path']} "
                  f"({row['rows_written']:,} rows, {row['imported_at']})")
        conn.close()
        return 0

    ap.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
