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

# Stored alongside the indicators but deliberately NOT in FEATURE_COLS. These are
# tradeability filters, not model inputs — feeding liquidity to the classifier
# would let it learn "small illiquid names move more", which is exactly the
# artifact the filters exist to remove.
LIQUIDITY_COLS = ["dollar_volume_20"]


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
            ticker        TEXT PRIMARY KEY,
            name          TEXT,
            exchange      TEXT,
            security_type TEXT,
            first_seen    TEXT NOT NULL,
            last_seen     TEXT NOT NULL,
            is_active     INTEGER NOT NULL DEFAULT 1
        ) STRICT
    """)
    # Migration for databases created before security_type existed. Cheaper and
    # far safer than rebuilding a table that took hours of downloads to fill.
    existing = {r[1] for r in conn.execute("PRAGMA table_info(symbols)")}
    if "security_type" not in existing:
        conn.execute("ALTER TABLE symbols ADD COLUMN security_type TEXT")
        log.info("Migrated symbols table: added security_type")
    if "data_quality" not in existing:
        conn.execute("ALTER TABLE symbols ADD COLUMN data_quality TEXT")
        log.info("Migrated symbols table: added data_quality")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_type ON symbols(security_type)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_symbols_quality ON symbols(data_quality)")

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

    conn.execute("""
        CREATE TABLE IF NOT EXISTS historical_listings (
            snapshot_date TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            name          TEXT,
            security_type TEXT,
            exchange      TEXT,
            PRIMARY KEY (snapshot_date, ticker)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS archive_snapshots (
            key           TEXT PRIMARY KEY,
            snapshot_date TEXT NOT NULL,
            listings      INTEGER NOT NULL,
            fetched_at    TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_hist_ticker ON historical_listings(ticker)")

    _init_features_table(conn)
    conn.commit()


def _init_features_table(conn: sqlite3.Connection) -> None:
    """
    Create the features table from the canonical column list.

    FEATURE_COLS lives in train_model.py, which owns it. Imported lazily so that
    `storage` stays importable without pulling in xgboost and scikit-learn.
    """
    from train_model import FEATURE_COLS

    cols = ",\n            ".join(f"{c} REAL" for c in FEATURE_COLS + LIQUIDITY_COLS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS features (
            ticker TEXT NOT NULL,
            date   TEXT NOT NULL,
            {cols},
            PRIMARY KEY (ticker, date)
        ) STRICT, WITHOUT ROWID
    """)
    # Migration for tables created before the liquidity columns existed.
    have = {r[1] for r in conn.execute("PRAGMA table_info(features)")}
    for c in LIQUIDITY_COLS:
        if c not in have:
            conn.execute(f"ALTER TABLE features ADD COLUMN {c} REAL")
            log.info(f"Migrated features table: added {c}")


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


def is_valid_ohlcv(frame: pd.DataFrame) -> pd.Series:
    """
    Boolean mask of rows that are physically possible prices.

    yfinance's `auto_adjust=True` back-adjusts historical prices for splits and
    dividends. Where the cumulative adjustment exceeds the original price the
    result goes *negative*, and negating the values also inverts high/low
    ordering. Observed on 3 of 6,169 tickers (VATE, CBIO, DEC) — rare, but a
    negative price silently poisons every indicator computed from it, and the
    Strategy Lab searches hard enough to find and exploit exactly this kind of
    artifact. Rejected at write time rather than filtered downstream, so the
    database never holds an impossible bar.
    """
    return (
        frame["close"].notna()
        & (frame["close"] > 0)
        & (frame["open"] > 0)
        & (frame["high"] > 0)
        & (frame["low"] > 0)
        & (frame["high"] >= frame["low"])
    )


def upsert_prices(conn: sqlite3.Connection, df: pd.DataFrame, source: str = "yfinance") -> int:
    """
    Upsert a long-format OHLCV frame (one row per ticker/date).

    Returns rows written. Re-running with the same data updates in place and
    leaves the row count unchanged — the idempotency the project requires of
    every pipeline stage. Rows failing `is_valid_ohlcv` are rejected and logged.
    """
    if df.empty:
        return 0

    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")

    valid = is_valid_ohlcv(frame)
    if not valid.all():
        rejected = frame.loc[~valid]
        for ticker, n in rejected["ticker"].value_counts().items():
            log.warning(f"{ticker}: rejected {n} rows with impossible prices (negative or high<low)")
        frame = frame.loc[valid]
        if frame.empty:
            return 0

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


def load_prices(conn: sqlite3.Connection, ticker: str) -> pd.DataFrame:
    """One ticker's full history in date order, shaped for `features.py`."""
    return pd.read_sql_query(
        "SELECT ticker, date, open, high, low, close, volume "
        "FROM prices WHERE ticker = ? ORDER BY date",
        conn, params=(ticker,),
    )


# --------------------------------------------------------------------------
# Features
# --------------------------------------------------------------------------

def upsert_features(conn: sqlite3.Connection, df: pd.DataFrame) -> int:
    """
    Upsert computed indicators, keyed on (ticker, date) like prices.

    Only the canonical FEATURE_COLS are stored. `compute_features_for_ticker`
    also emits intermediates (bb_upper, obv, obv_sma_20, vol_sma_20) that the
    model does not consume; keeping them would mean the table and the model
    disagreeing about what a feature is.
    """
    from train_model import FEATURE_COLS

    if df.empty:
        return 0

    stored = FEATURE_COLS + [c for c in LIQUIDITY_COLS if c in df.columns]
    cols = ["ticker", "date"] + stored
    frame = df.copy()
    frame["date"] = pd.to_datetime(frame["date"]).dt.strftime("%Y-%m-%d")
    frame = frame[cols]

    placeholders = ",".join("?" * len(cols))
    updates = ",".join(f"{c}=excluded.{c}" for c in stored)
    sql = (f"INSERT INTO features ({','.join(cols)}) VALUES ({placeholders}) "
           f"ON CONFLICT(ticker, date) DO UPDATE SET {updates}")

    # NaN is normal here — every rolling indicator is undefined for its warm-up
    # window — but sqlite3 has no NaN, so it must become NULL explicitly.
    frame = frame.astype(object).where(pd.notna(frame), None)
    conn.executemany(sql, list(frame.itertuples(index=False, name=None)))
    return len(frame)


MIN_BARS_FOR_FEATURES = 210  # 200-day SMA warm-up


def tickers_needing_features(conn: sqlite3.Connection, min_bars: int = MIN_BARS_FOR_FEATURES,
                             types: list[str] | None = None) -> list[str]:
    """
    Tickers whose features are missing or stale *and* that have enough history
    to compute any.

    Compares the latest feature date against the latest price date per ticker,
    so this is derived state rather than a progress table that could drift out
    of sync with reality. Re-running after new prices arrive picks up exactly
    the tickers that moved.

    The `min_bars` floor matters for honesty as much as efficiency. Tickers listed
    too recently for a 200-day SMA to warm up will never produce a feature row.
    Counting them as outstanding would leave the status output permanently
    reporting unfinished work on a database that is in fact complete — and would
    re-read all of them on every run forever.

    `types` restricts to security types worth indicating at all. Rolling
    indicators on a warrant or a corporate note are arithmetic without meaning.
    """
    params: list = [min_bars]
    type_clause = ""
    if types:
        type_clause = f"""
          AND p.ticker IN (SELECT ticker FROM symbols
                           WHERE security_type IN ({",".join("?" * len(types))}))"""
        params += list(types)

    # Staleness is a row-count comparison, not a max-date one. compute_features_
    # for_ticker emits one row per price bar, so equal counts mean up to date.
    # Comparing latest dates instead would miss history added at the *start* —
    # which is exactly what switching the pull from 20y to max does, leaving
    # every already-computed ticker looking current while missing years of bars.
    rows = conn.execute(f"""
        SELECT p.ticker
        FROM (SELECT ticker, COUNT(*) AS bars FROM prices GROUP BY ticker) p
        LEFT JOIN (SELECT ticker, COUNT(*) AS feats FROM features GROUP BY ticker) f
          ON p.ticker = f.ticker
        WHERE p.bars >= ?
          {type_clause}
          AND (f.feats IS NULL OR f.feats <> p.bars)
        ORDER BY p.ticker
    """, params).fetchall()
    return [r["ticker"] for r in rows]


def feature_ineligible_count(conn: sqlite3.Connection, min_bars: int = MIN_BARS_FOR_FEATURES,
                             types: list[str] | None = None) -> int:
    """Tickers of the given types that have prices but too little history for features."""
    clause, params = "", []
    if types:
        clause = (f" AND ticker IN (SELECT ticker FROM symbols "
                  f"WHERE security_type IN ({','.join('?' * len(types))}))")
        params = list(types)
    params.append(min_bars)  # bound last: the HAVING placeholder trails the IN list

    return conn.execute(
        f"SELECT COUNT(*) FROM (SELECT ticker FROM prices WHERE 1=1{clause} "
        f"GROUP BY ticker HAVING COUNT(*) < ?)",
        params,
    ).fetchone()[0]


def prune_features_of_excluded_types(conn: sqlite3.Connection, types: list[str]) -> int:
    """
    Delete feature rows for security types no longer in `feature_types`.

    Narrowing the configured types otherwise leaves orphans behind: rows computed
    under a previous, wider setting that nothing will ever refresh again. They are
    worse than absent, because they look like current data while having been
    derived from whatever price history existed when they were written.
    """
    if not types:
        return 0
    placeholders = ",".join("?" * len(types))
    n = conn.execute(f"""
        DELETE FROM features WHERE ticker IN (
            SELECT ticker FROM symbols WHERE security_type NOT IN ({placeholders})
        )
    """, types).rowcount
    if n:
        conn.commit()
        log.info(f"Pruned {n:,} feature rows for security types outside feature_types")
    return n


def feature_stats(conn: sqlite3.Connection) -> dict:
    row = conn.execute("""
        SELECT COUNT(*) AS rows, COUNT(DISTINCT ticker) AS tickers,
               MIN(date) AS first_date, MAX(date) AS last_date
        FROM features
    """).fetchone()
    return dict(row)


CHUNK_ROWS = 500_000


def _read_downcast(conn, sql, params, feature_cols, chunk_rows: int = CHUNK_ROWS) -> pd.DataFrame:
    """
    Read a large result set in chunks, narrowing dtypes as each chunk arrives.

    This is the difference between fitting in memory and being OOM-killed, and
    the reason is not obvious: `pd.read_sql_query` materialises the *entire*
    result set as Python objects before it builds a DataFrame. Every float is a
    24-byte Python object inside a tuple, so downcasting afterwards is far too
    late — the peak has already happened.

    Measured on this database: a 2.6M-row query produced a 0.25 GB frame with a
    4.32 GB peak, a ratio of 17.5x. Extrapolated to the 12M-row training set that
    is roughly 20 GB, against 11.7 GB of RAM. Two runs were killed at 10.4 GB
    resident before this was found.

    Reading in chunks caps the object-overhead peak at one chunk's worth, so peak
    tracks the final frame instead of the row count.
    """
    frames = []
    for chunk in pd.read_sql_query(sql, conn, params=params, chunksize=chunk_rows):
        for c in feature_cols:
            chunk[c] = chunk[c].astype("float32")
        if "close" in chunk:
            chunk["close"] = chunk["close"].astype("float32")
        if "label" in chunk:
            chunk["label"] = chunk["label"].astype("int8")
        if "ticker" in chunk:
            chunk["ticker"] = chunk["ticker"].astype("category")
        if "date" in chunk:
            chunk["date"] = pd.to_datetime(chunk["date"])
        frames.append(chunk)

    if not frames:
        return pd.DataFrame(columns=["ticker", "date", "close", *feature_cols])
    df = pd.concat(frames, ignore_index=True, copy=False)
    del frames
    # Categories are per-chunk until unified; without this the column keeps one
    # category set per chunk and costs more than the plain strings it replaced.
    if "ticker" in df:
        df["ticker"] = df["ticker"].astype("category")
    return df


def _feature_where(feature_cols, types, start_date, end_date,
                   min_price=None, min_dollar_volume=None):
    """Shared WHERE clause and bound parameters for the feature loaders."""
    where = [f"f.{c} IS NOT NULL" for c in feature_cols]
    params: list = []
    if min_price is not None:
        where.append("p.close >= ?"); params.append(float(min_price))
    if min_dollar_volume is not None:
        where.append("f.dollar_volume_20 >= ?"); params.append(float(min_dollar_volume))
    if types:
        where.append(f"f.ticker IN (SELECT ticker FROM symbols "
                     f"WHERE security_type IN ({','.join('?' * len(types))}) "
                     f"AND data_quality IS NULL)")
        params += list(types)
    if start_date:
        where.append("f.date >= ?"); params.append(start_date)
    if end_date:
        where.append("f.date <= ?"); params.append(end_date)
    return " AND ".join(where), params


def feature_dates(conn: sqlite3.Connection, types: list[str] | None = None,
                  start_date: str | None = None, end_date: str | None = None) -> list[str]:
    """
    Distinct dates with usable feature rows, in order.

    Cheap enough to run before loading anything, which is the point: the
    train/test boundary can be chosen from dates alone, so each side is loaded
    separately and the full frame never exists in memory at once.
    """
    clause = []
    params: list = []
    if types:
        clause.append(f"ticker IN (SELECT ticker FROM symbols "
                      f"WHERE security_type IN ({','.join('?' * len(types))}) "
                      f"AND data_quality IS NULL)")
        params += list(types)
    if start_date:
        clause.append("date >= ?"); params.append(start_date)
    if end_date:
        clause.append("date <= ?"); params.append(end_date)
    sql = "SELECT DISTINCT date FROM features"
    if clause:
        sql += " WHERE " + " AND ".join(clause)
    return [r[0] for r in conn.execute(sql + " ORDER BY date", params).fetchall()]


def count_labeled_rows(conn: sqlite3.Connection, feature_cols: list[str],
                       types: list[str] | None = None,
                       start_date: str | None = None,
                       end_date: str | None = None,
                       min_price: float | None = None,
                       min_dollar_volume: float | None = None) -> int:
    """Row count for a prospective load — so memory can be budgeted before committing to it."""
    where, params = _feature_where(feature_cols, types, start_date, end_date,
                                   min_price, min_dollar_volume)
    return conn.execute(
        f"SELECT COUNT(*) FROM features f JOIN prices p "
        f"ON f.ticker = p.ticker AND f.date = p.date WHERE {where}", params
    ).fetchone()[0]


def load_labeled_frame(conn: sqlite3.Connection, feature_cols: list[str],
                       horizon_days: int, up_threshold_pct: float,
                       types: list[str] | None = None,
                       start_date: str | None = None,
                       end_date: str | None = None,
                       sample_per_mille: int | None = None,
                       min_price: float | None = None,
                       min_dollar_volume: float | None = None) -> pd.DataFrame:
    """
    Features, close, and the forward-return label — labelled in SQL, not pandas.

    Doing the label in SQL matters for memory, not elegance. The pandas version
    (`sort_values` then `groupby.shift`) copies the entire frame twice, and at
    15M rows that was the difference between fitting and being OOM-killed with
    10.4 GB resident. A `LEAD()` window does it inside SQLite with no Python-side
    copy at all.

    It also purges the boundary for free: `LEAD` returns NULL for the final
    `horizon_days` rows of each ticker in the loaded range, so those rows drop
    out. Load the train range and the test range separately and no training
    label can reach into the test period.

    Dates come back as `datetime64`, never strings — 15M Python strings cost
    about 1.5 GB on their own.
    """
    horizon = int(horizon_days)          # interpolated, so force it to an int
    where, params = _feature_where(feature_cols, types, start_date, end_date,
                                   min_price, min_dollar_volume)

    # Subsample in SQL, not pandas. Sampling after loading would not help: the
    # peak happens while the full result set is still a pile of Python objects.
    # Applied to `base` so the LEAD window still sees every row — sampling before
    # the window would compute forward returns across gaps and silently corrupt
    # every label.
    sample_clause = ""
    if sample_per_mille is not None and sample_per_mille < 1000:
        sample_clause = f" AND (abs(random()) % 1000) < {int(sample_per_mille)}"
    cols = ", ".join(f"f.{c}" for c in feature_cols)
    sel = ", ".join(feature_cols)

    sql = f"""
        WITH base AS (
            SELECT f.ticker, f.date, p.close, {cols}
            FROM features f JOIN prices p ON f.ticker = p.ticker AND f.date = p.date
            WHERE {where}
        ), lab AS (
            SELECT *, LEAD(close, {horizon}) OVER (
                          PARTITION BY ticker ORDER BY date) AS future_close
            FROM base
        )
        SELECT ticker, date, close, {sel},
               CASE WHEN (future_close / close - 1) * 100 >= ? THEN 1 ELSE 0 END AS label
        FROM lab
        WHERE future_close IS NOT NULL AND close > 0{sample_clause}
    """
    return _read_downcast(conn, sql, params + [up_threshold_pct], feature_cols)


def frame_memory_gb(df: pd.DataFrame) -> float:
    return float(df.memory_usage(deep=True).sum()) / 1e9


def available_memory_gb() -> float:
    """Read MemAvailable from /proc — no psutil dependency needed."""
    try:
        with open("/proc/meminfo") as f:
            for line in f:
                if line.startswith("MemAvailable:"):
                    return int(line.split()[1]) / 1e6
    except OSError:
        pass
    return float("inf")


def load_training_frame(conn: sqlite3.Connection, feature_cols: list[str],
                       types: list[str] | None = None,
                       start_date: str | None = None,
                       end_date: str | None = None,
                       min_price: float | None = None,
                       min_dollar_volume: float | None = None) -> pd.DataFrame:
    """
    Features joined to close price, for model training and backtesting.

    Two memory choices matter at this scale. Indicators come back as `float32`,
    which halves ~15M rows from 2.5 GB to 1.25 GB at no cost to a model that
    trains in single precision anyway. And `ticker` becomes a pandas categorical
    — as plain strings, 15M Python objects would dwarf the numeric data they
    label.

    Rows with any null indicator are excluded here rather than downstream, so the
    caller receives only usable rows.
    """
    cols = ", ".join(f"f.{c}" for c in feature_cols)
    where_sql, params = _feature_where(feature_cols, types, start_date, end_date,
                                       min_price, min_dollar_volume)
    where = [where_sql]

    sql = (f"SELECT f.ticker, f.date, p.close, {cols} "
           f"FROM features f JOIN prices p ON f.ticker = p.ticker AND f.date = p.date "
           f"WHERE {' AND '.join(where)}")

    return _read_downcast(conn, sql, params, feature_cols)


def price_series(conn: sqlite3.Connection, tickers: list[str],
                 start_date: str, end_date: str) -> dict:
    """
    Unfiltered closes for the given tickers, keyed (ticker, date).

    Exits must never use the same filtered view as entries. Tradeability floors
    decide what may be *bought*; a position already open has to be priced and
    closed on schedule even on days the name slips below the floor. Using the
    filtered set for both made held positions invisible on those days, so the
    holding clock stopped and average hold ran to 58 days against a 5-day
    horizon.
    """
    if not tickers:
        return {}
    out = {}
    CH = 900  # stay under SQLite's variable limit
    for i in range(0, len(tickers), CH):
        block = tickers[i:i + CH]
        ph = ",".join("?" * len(block))
        rows = conn.execute(
            f"SELECT ticker, date, close FROM prices "
            f"WHERE ticker IN ({ph}) AND date BETWEEN ? AND ?",
            (*block, start_date, end_date)).fetchall()
        for r in rows:
            out[(r[0], r[1])] = r[2]
    return out


def load_latest_features(conn: sqlite3.Connection, feature_cols: list[str],
                         types: list[str] | None = None,
                         max_staleness_days: int = 5,
                         min_price: float | None = None,
                         min_dollar_volume: float | None = None) -> pd.DataFrame:
    """
    Most recent feature row per ticker — what the daily scorer ranks.

    `max_staleness_days` is not optional hygiene. "Latest row for this ticker"
    and "current" are different things: a halted or delisted name keeps a latest
    row forever, and without this filter the scorer will happily rank a stock
    whose most recent bar is from 2018 and propose buying it. Observed in the
    real table, not hypothetical.

    Staleness is measured against the newest date in the features table rather
    than today's date, so the filter behaves correctly over a weekend, a market
    holiday, or a database that has not been topped up yet.
    """
    cols = ", ".join(f"f.{c}" for c in feature_cols)
    where = [f"f.{c} IS NOT NULL" for c in feature_cols]
    params: list = []
    if min_price is not None:
        where.append("p.close >= ?"); params.append(float(min_price))
    if min_dollar_volume is not None:
        where.append("f.dollar_volume_20 >= ?"); params.append(float(min_dollar_volume))
    if types:
        where.append(f"f.ticker IN (SELECT ticker FROM symbols "
                     f"WHERE security_type IN ({','.join('?' * len(types))}) "
                     f"AND is_active = 1 AND data_quality IS NULL)")
        params += list(types)

    newest = conn.execute("SELECT MAX(date) FROM features").fetchone()[0]
    if newest and max_staleness_days is not None:
        cutoff = (pd.Timestamp(newest) - pd.Timedelta(days=max_staleness_days)).strftime("%Y-%m-%d")
        where.append("f.date >= ?")
        params.append(cutoff)

    sql = (f"SELECT f.ticker, f.date, p.close, {cols} "
           f"FROM features f JOIN prices p ON f.ticker = p.ticker AND f.date = p.date "
           f"JOIN (SELECT ticker, MAX(date) AS d FROM features GROUP BY ticker) m "
           f"  ON f.ticker = m.ticker AND f.date = m.d "
           f"WHERE {' AND '.join(where)}")
    return pd.read_sql_query(sql, conn, params=params)


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
        (s["ticker"], s.get("name"), s.get("exchange"), s.get("security_type"), seen_on, seen_on)
        for s in symbols
    ]
    conn.executemany("""
        INSERT INTO symbols (ticker, name, exchange, security_type, first_seen, last_seen, is_active)
        VALUES (?, ?, ?, ?, ?, ?, 1)
        ON CONFLICT(ticker) DO UPDATE SET
            name=excluded.name, exchange=excluded.exchange,
            security_type=excluded.security_type,
            last_seen=excluded.last_seen, is_active=1
    """, rows)

    # Anything not in today's snapshot is no longer listed.
    conn.execute("UPDATE symbols SET is_active=0 WHERE last_seen < ?", (seen_on,))
    conn.commit()
    return len(rows)


# --------------------------------------------------------------------------
# Ingest state (resumability)
# --------------------------------------------------------------------------

def tickers_by_type(conn: sqlite3.Connection, types: list[str], active_only: bool = True) -> list[str]:
    """Tickers of the given security types, e.g. ['common_stock', 'etf']."""
    placeholders = ",".join("?" * len(types))
    sql = (f"SELECT ticker FROM symbols WHERE security_type IN ({placeholders}) "
           f"AND data_quality IS NULL")
    if active_only:
        sql += " AND is_active = 1"
    return [r["ticker"] for r in conn.execute(sql + " ORDER BY ticker", types).fetchall()]


def type_breakdown(conn: sqlite3.Connection) -> dict:
    """Row and ticker counts per security type — what actually landed."""
    rows = conn.execute("""
        SELECT s.security_type AS t,
               COUNT(DISTINCT s.ticker) AS symbols,
               COUNT(DISTINCT p.ticker) AS with_prices
        FROM symbols s LEFT JOIN prices p ON s.ticker = p.ticker
        GROUP BY s.security_type ORDER BY symbols DESC
    """).fetchall()
    return {r["t"]: {"symbols": r["symbols"], "with_prices": r["with_prices"]} for r in rows}


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


# --------------------------------------------------------------------------
# Point-in-time reconstruction (Internet Archive)
# --------------------------------------------------------------------------

# Highest close ever printed by a US common stock is Berkshire A, near $800k.
# Anything above $1M is definitively an adjustment artifact, not a price.
MAX_PLAUSIBLE_CLOSE = 1_000_000.0
MAX_PLAUSIBLE_RATIO = 1_000_000.0


def flag_price_anomalies(conn: sqlite3.Connection) -> int:
    """
    Mark tickers whose adjusted history is physically impossible.

    yfinance back-adjusts for splits, and serial reverse-splitters compound: TOPS
    carries a maximum adjusted close of $549 *trillion* per share. 425,964 rows
    across 333 tickers sit above $10,000.

    These pass every filter we have. `min_price` is a floor, so an inflated price
    clears it trivially, and `dollar_volume_20` is close x volume, so the same
    tickers look maximally liquid — the guards designed to keep us in tradeable
    names actively prefer them.

    The rule is absolute price plus range, not range alone. Berkshire A really does
    trade near $800k, and Monster Beverage really is up 15,352x — a range-only
    rule at 10,000x would discard both. Validated against NVDA, AAPL, AMZN, MSFT,
    BRK-A/B, TSLA, MNST, GE and F: none are flagged.
    """
    n = conn.execute("""
        UPDATE symbols SET data_quality = 'price_anomaly'
        WHERE ticker IN (
            SELECT ticker FROM (
                SELECT ticker, MAX(close) mx, MIN(close) mn,
                       MAX(close) / MIN(close) ratio
                FROM prices GROUP BY ticker HAVING MIN(close) > 0
            ) WHERE mx > ? OR ratio > ?
        )
    """, (MAX_PLAUSIBLE_CLOSE, MAX_PLAUSIBLE_RATIO)).rowcount
    conn.commit()
    if n:
        log.warning(f"Flagged {n} tickers with impossible adjusted prices")
    return n


def archived_snapshots(conn: sqlite3.Connection) -> set:
    """Snapshot keys already stored — makes the fetch resumable across runs."""
    return {r[0] for r in conn.execute("SELECT key FROM archive_snapshots")}


def record_historical_listings(conn: sqlite3.Connection, snapshot_date: str,
                               key: str, rows: list[dict]) -> int:
    """Store one archived directory capture."""
    conn.executemany("""
        INSERT INTO historical_listings (snapshot_date, ticker, name, security_type, exchange)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(snapshot_date, ticker) DO UPDATE SET
            name=excluded.name, security_type=excluded.security_type,
            exchange=excluded.exchange
    """, [(snapshot_date, r["ticker"], r.get("name"), r.get("security_type"),
           r.get("exchange")) for r in rows])
    conn.execute("""
        INSERT INTO archive_snapshots (key, snapshot_date, listings, fetched_at)
        VALUES (?, ?, ?, ?)
        ON CONFLICT(key) DO UPDATE SET listings=excluded.listings, fetched_at=excluded.fetched_at
    """, (key, snapshot_date, len(rows), _now()))
    conn.commit()
    return len(rows)


def coverage_by_snapshot(conn: sqlite3.Connection, security_type: str = "common_stock") -> list[dict]:
    """
    For each archived capture: how many common stocks were listed, and how many of
    them we hold any price history for.

    The shortfall is the survivorship gap, measured rather than assumed. A ticker
    counts as covered if `prices` holds *any* bar for it — a deliberately generous
    test, so the gap reported is a lower bound on what is really missing.
    """
    rows = conn.execute("""
        SELECT h.snapshot_date,
               COUNT(*) AS listed,
               SUM(CASE WHEN EXISTS (SELECT 1 FROM prices p WHERE p.ticker = h.ticker)
                        THEN 1 ELSE 0 END) AS covered
        FROM historical_listings h
        WHERE h.security_type = ?
        GROUP BY h.snapshot_date
        ORDER BY h.snapshot_date
    """, (security_type,)).fetchall()
    return [dict(r) for r in rows if r["listed"]]


def total_ever_listed(conn: sqlite3.Connection, security_type: str = "common_stock") -> dict:
    row = conn.execute("""
        SELECT COUNT(DISTINCT ticker) AS ever,
               COUNT(DISTINCT CASE WHEN EXISTS
                   (SELECT 1 FROM prices p WHERE p.ticker = h.ticker)
                   THEN ticker END) AS covered
        FROM historical_listings h WHERE security_type = ?
    """, (security_type,)).fetchone()
    return dict(row)


def missing_tickers(conn: sqlite3.Connection, year: str, limit: int = 25) -> list[dict]:
    """Common stocks listed in `year` for which we hold no price history at all."""
    rows = conn.execute("""
        SELECT h.ticker, MIN(h.snapshot_date) AS snapshot_date, h.name
        FROM historical_listings h
        WHERE h.security_type = 'common_stock'
          AND h.snapshot_date LIKE ?
          AND NOT EXISTS (SELECT 1 FROM prices p WHERE p.ticker = h.ticker)
        GROUP BY h.ticker ORDER BY h.ticker LIMIT ?
    """, (f"{year}%", limit)).fetchall()
    return [dict(r) for r in rows]


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
