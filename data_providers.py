"""
Provider interface for price data.

Strategies and the backtester read bars through this interface so the same code
can run against the primary market database or a secondary validation dataset
without knowing which. The two datasets are not interchangeable and must never
be merged: `data/market_data.db` is the primary, survivorship-biased series the
system trades on, and `data/finsaber.db` is a validation set that includes
delisted names. Writing one into the other would silently change what every
backtest means.

`IntradayProvider` is a reserved slot. No historical intraday source is
configured, and `has_historical_intraday()` says so rather than letting a caller
discover it by exception.
"""
import runtime  # noqa: F401  — must precede numpy/pandas. Both modules
                #   have a __main__ block, so they are entry points too.
import logging
import sqlite3

import pandas as pd

log = logging.getLogger("data_providers")

# The exact shape every provider must return. Callers index these by name, so a
# provider that renames or reorders them breaks the backtester in a way that
# looks like a data problem.
BAR_COLUMNS = ["ticker", "date", "open", "high", "low", "close", "volume"]


class DataProvider:
    """
    Read-only daily bars, a point-in-time universe, and a coverage summary.

    Deliberately no write methods. A provider that could write would make it
    possible to "fix" a dataset from inside a backtest, which is how a
    validation set stops being independent.
    """

    def name(self) -> str:
        raise NotImplementedError

    def daily_bars(self, tickers: list | None, start: str, end: str) -> pd.DataFrame:
        """
        Bars for `tickers` (None = every ticker) between `start` and `end`
        inclusive, as 'YYYY-MM-DD' strings.

        Returns exactly BAR_COLUMNS. Dates are strings, not timestamps: the
        primary database stores them as TEXT and every join in the system is a
        string comparison, so returning Timestamps here would make the two
        providers disagree on equality.
        """
        raise NotImplementedError

    def universe(self, on_date: str) -> list[str]:
        """Tickers with a bar on `on_date` — the tradeable set as of that session."""
        raise NotImplementedError

    def coverage(self) -> dict:
        """Keys: name, first_date, last_date, securities, bars."""
        raise NotImplementedError


class StockbotProvider(DataProvider):
    """
    The primary market database.

    Takes an already-open connection rather than a path so the caller controls
    the connection's lifetime and pragmas; opening a second connection to a
    database mid-backfill would contend with the writer.
    """

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def name(self) -> str:
        return "stockbot"

    def daily_bars(self, tickers: list | None, start: str, end: str) -> pd.DataFrame:
        where = ["date BETWEEN ? AND ?"]
        params: list = [start, end]
        if tickers is not None:
            tickers = list(tickers)
            if not tickers:
                return _empty_bars()
            # Chunked to stay under SQLite's bound-variable limit; a full-universe
            # call would otherwise fail at ~1000 tickers.
            frames = []
            for i in range(0, len(tickers), 900):
                block = tickers[i:i + 900]
                ph = ",".join("?" * len(block))
                frames.append(pd.read_sql_query(
                    f"SELECT ticker, date, open, high, low, close, volume FROM prices "
                    f"WHERE {' AND '.join(where)} AND ticker IN ({ph}) "
                    f"ORDER BY ticker, date",
                    self.conn, params=params + block))
            return _shape(pd.concat(frames, ignore_index=True) if frames else _empty_bars())

        return _shape(pd.read_sql_query(
            f"SELECT ticker, date, open, high, low, close, volume FROM prices "
            f"WHERE {' AND '.join(where)} ORDER BY ticker, date",
            self.conn, params=params))

    def universe(self, on_date: str) -> list[str]:
        rows = self.conn.execute(
            "SELECT DISTINCT ticker FROM prices WHERE date = ? ORDER BY ticker",
            (on_date,)).fetchall()
        return [r[0] for r in rows]

    def coverage(self) -> dict:
        row = self.conn.execute("""
            SELECT COUNT(*) AS bars, COUNT(DISTINCT ticker) AS securities,
                   MIN(date) AS first_date, MAX(date) AS last_date
            FROM prices
        """).fetchone()
        return {"name": self.name(), "first_date": row["first_date"],
                "last_date": row["last_date"], "securities": row["securities"],
                "bars": row["bars"]}


class IntradayProvider(DataProvider):
    """
    Reserved for a historical intraday source (Phase 13 §B8). None is configured.

    Every method raises rather than returning empty. An empty frame is
    indistinguishable from "no bars in this window", and a strategy silently
    backtested on zero bars reports a flat equity curve that looks like a
    result. Failing loudly is the only safe behaviour for a provider that does
    not exist yet.
    """

    _MSG = ("no historical intraday source is configured; IntradayProvider is a "
            "reserved slot (Phase 13 §B8) and cannot serve bars")

    def name(self) -> str:
        return "intraday"

    def daily_bars(self, tickers: list | None, start: str, end: str) -> pd.DataFrame:
        raise NotImplementedError(self._MSG)

    def intraday_bars(self, tickers: list | None, start: str, end: str,
                      interval: str) -> pd.DataFrame:
        raise NotImplementedError(self._MSG)

    def universe(self, on_date: str) -> list[str]:
        raise NotImplementedError(self._MSG)

    def coverage(self) -> dict:
        raise NotImplementedError(self._MSG)


def has_historical_intraday() -> bool:
    """False until a real intraday source is wired up. Callers must branch on this."""
    return False


# --------------------------------------------------------------------------
# Registry
# --------------------------------------------------------------------------

PROVIDERS: dict = {}


def register(name: str, factory) -> None:
    """
    Register a provider factory under `name`.

    A factory, not an instance: providers hold connections, and a module-level
    instance would pin one open for the process lifetime and make the registry
    unimportable without a database present.
    """
    if name in PROVIDERS and PROVIDERS[name] is not factory:
        log.warning(f"Overriding provider {name!r}")
    PROVIDERS[name] = factory


def get(name: str, **kw) -> DataProvider:
    if name not in PROVIDERS:
        raise KeyError(f"Unknown data provider {name!r}; known: {sorted(PROVIDERS)}")
    return PROVIDERS[name](**kw)


def _empty_bars() -> pd.DataFrame:
    return pd.DataFrame(columns=BAR_COLUMNS)


def _shape(df: pd.DataFrame) -> pd.DataFrame:
    """
    Force a frame into the contract: exact columns, exact order, string dates.

    Applied on the way out of every provider so a caller never has to know which
    one it is talking to. `volume` is left as-is rather than cast to int — the
    primary table stores it as INTEGER but a provider may legitimately have
    fractional volume, and truncating it here would be a silent data change.
    """
    if df.empty:
        return _empty_bars()
    df = df.copy()
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d")
    return df[BAR_COLUMNS].reset_index(drop=True)


# Registered here rather than in storage.py so that importing the provider
# interface is enough to make the primary database available. finsaber.py
# registers itself on import, which is why it is not imported from this module —
# that would make the primary path depend on the validation dataset existing.
register("stockbot", StockbotProvider)
