"""
Quote providers for the trading engine. Addendum A §16, §18; Addendum B §B8.

B8 distinguishes three kinds of market data, and so does this module:

  historical research data   prices / features in market_data.db (not here)
  LIVE market data           `LiveQuotes` — the latest 1-minute bar during
                             market hours, for stops, signals and fills
  historical INTRADAY data   `IntradayHistory` — an interface only. Live polling
                             does not create intraday research history, and
                             nothing here pretends it does (B8). A provider can
                             be plugged in later without touching the engine.

Every quote carries `as_of` (UTC ISO). `LiveQuotes.get` returns None when the
newest bar is older than `max_age_seconds` during market hours — a stale quote
is refused rather than traded on (B13, stale-data protection). Outside market
hours no live quote exists, and the engine must not pretend otherwise: it gets
None and the caller decides (the slot trader simply does not trade).

Quotes also carry `dollar_volume_20` and `market_cap` from the database,
because the risk engine rejects a quote without them (see risk_engine).

Free source: yfinance 1-minute bars (delayed a little; stated, not hidden).
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging
from datetime import datetime, time, timezone
from zoneinfo import ZoneInfo

log = logging.getLogger("quotes")
NY = ZoneInfo("America/New_York")
OPEN, CLOSE = time(9, 30), time(16, 0)


def market_open(now: datetime | None = None) -> bool:
    """Regular session on a weekday. Holidays are caught by the staleness check."""
    t = (now or datetime.now(timezone.utc)).astimezone(NY)
    return t.weekday() < 5 and OPEN <= t.time() < CLOSE


def _db_fields(conn, symbol: str, cap_source: str | None = None, call=None) -> dict:
    """
    Liquidity and market cap for a quote. The cap is the filing cap, else a
    recent sourced one (market_caps.py); with `cap_source` a miss is fetched
    once from that source. Still unknown after that -> None, and the risk
    engine rejects it.
    """
    import market_caps
    dv = conn.execute("SELECT dollar_volume_20 FROM features WHERE ticker=? AND dollar_volume_20 "
                      "IS NOT NULL ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
    cap, src = (market_caps.ensure(conn, symbol, cap_source, call=call) if cap_source
                else market_caps.lookup(conn, symbol))
    return {"dollar_volume_20": float(dv[0]) if dv and dv[0] else None,
            "market_cap": cap, "market_cap_source": src}


class QuoteProvider:
    def get(self, symbol: str) -> dict | None:
        raise NotImplementedError


class DatabaseQuotes(QuoteProvider):
    """Last stored close. For tests and after-hours reporting — never for a fill."""

    def __init__(self, conn):
        self.conn = conn

    def get(self, symbol):
        r = self.conn.execute("SELECT date, close FROM prices WHERE ticker=? AND close>0 "
                              "ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
        if not r:
            return None
        return {"symbol": symbol, "price": float(r[1]), "as_of": f"{r[0]}T20:00:00+00:00",
                "source": "database_close", **_db_fields(self.conn, symbol)}


class FixedQuotes(QuoteProvider):
    """Injected prices for tests and replays."""

    def __init__(self, prices: dict, conn=None, as_of: str | None = None):
        self.prices, self.conn = prices, conn
        self.as_of = as_of or datetime.now(timezone.utc).isoformat()

    def get(self, symbol):
        if symbol not in self.prices:
            return None
        extra = _db_fields(self.conn, symbol) if self.conn is not None else \
            {"dollar_volume_20": 1e9, "market_cap": 1e11}
        return {"symbol": symbol, "price": float(self.prices[symbol]), "as_of": self.as_of,
                "source": "fixed", **extra}


class LiveQuotes(QuoteProvider):
    """Latest 1-minute bar during market hours; None when stale or closed."""

    def __init__(self, conn, max_age_seconds: int = 900):
        self.conn, self.max_age = conn, max_age_seconds
        self._cache = {}

    def get(self, symbol):
        if symbol in self._cache:
            return self._cache[symbol]
        q = None
        try:
            import yfinance as yf
            h = yf.Ticker(symbol).history(period="1d", interval="1m", prepost=False)
            if len(h):
                ts = h.index[-1].to_pydatetime().astimezone(timezone.utc)
                age = (datetime.now(timezone.utc) - ts).total_seconds()
                if not market_open():
                    log.info(f"{symbol}: market closed, no live quote")
                elif age > self.max_age:
                    log.warning(f"{symbol}: newest bar {age:.0f}s old > {self.max_age}s — stale, refused")
                else:
                    q = {"symbol": symbol, "price": float(h["Close"].iloc[-1]),
                         "high": float(h["High"].max()), "as_of": ts.isoformat(),
                         "source": "yfinance_1m", **_db_fields(self.conn, symbol, "yfinance")}
        except Exception as e:                              # noqa: BLE001
            log.error(f"{symbol}: live quote failed: {type(e).__name__}: {e}")
        self._cache[symbol] = q
        return q


class IntradayHistory:
    """
    Historical intraday bars for research (B8). Not provided: free sources keep
    about 60 days of 1-minute history, which cannot validate a strategy. Any
    intraday strategy therefore stays in paper/shadow until a real provider is
    plugged in here.
    """

    def bars(self, symbol: str, start: str, end: str, interval: str = "1m"):
        raise NotImplementedError("no historical intraday provider configured (B8)")
