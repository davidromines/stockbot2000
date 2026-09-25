"""Stage K1: measure Robinhood crypto bid/ask spreads and serve a half-spread.

Robinhood charges no crypto commission, so the entire trading cost is the
spread. Backtests must charge the MEASURED half-spread per side rather than a
guessed constant, so this module logs quotes and reports the median.
"""
import runtime  # noqa: F401  (must precede numpy/pandas imports)

import argparse
import json
import sqlite3
import statistics
import sys
from datetime import datetime, timedelta, timezone

import yaml

import crypto_data
import storage

DEFAULTS = {
    "default_half_spread": 0.0095,
    "window_days": 7,
    "min_samples": 12,
}


def _cfg(cfg):
    merged = dict(DEFAULTS)
    if cfg:
        merged.update(cfg)
    return merged


def _now_iso(now=None):
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        return now
    return now.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _to_float(value):
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalise_symbol(raw):
    """Robinhood returns 'BTCUSD'; the rest of the system uses 'BTC-USD'."""
    if not raw:
        return None
    text = str(raw).strip().upper()
    if text.endswith("USD") and not text.endswith("-USD"):
        text = text[:-3] + "-USD"
    return text


def init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS crypto_spreads (
            symbol     TEXT NOT NULL,
            at_utc     TEXT NOT NULL,
            bid        REAL,
            ask        REAL,
            mark       REAL,
            spread_pct REAL NOT NULL,
            routing    TEXT,
            quote_time TEXT,
            source     TEXT DEFAULT 'robinhood',
            PRIMARY KEY (symbol, at_utc)
        )
        """
    )
    conn.commit()


def parse_quotes(resp):
    """Parse a get_crypto_quotes response into validated quote dicts.

    A quote is only usable if both sides are positive numbers and the ask is
    not below the bid; anything else is dropped rather than coerced, because a
    bad spread silently corrupts every backtest that consumes it.
    """
    out = []
    if not isinstance(resp, dict):
        return out
    results = (resp.get("data") or {}).get("results") or []
    for row in results:
        if not isinstance(row, dict):
            continue
        symbol = _normalise_symbol(row.get("symbol"))
        bid = _to_float(row.get("bid_price"))
        ask = _to_float(row.get("ask_price"))
        if not symbol or bid is None or ask is None:
            continue
        if bid <= 0 or ask <= 0 or ask < bid:
            continue
        mid = (ask + bid) / 2.0
        out.append(
            {
                "symbol": symbol,
                "bid": bid,
                "ask": ask,
                "mark": _to_float(row.get("mark_price")),
                "spread_pct": (ask - bid) / mid,
                "routing": row.get("routing"),
                "quote_time": row.get("updated_at"),
            }
        )
    return out


def log_spreads(conn, call, symbols, account, now=None):
    at_utc = _now_iso(now)
    resp = call(
        "get_crypto_quotes",
        {"symbols": list(symbols), "rhs_account_number": account},
    )
    if isinstance(resp, str):
        resp = json.loads(resp)
    init(conn)
    inserted = 0
    for q in parse_quotes(resp):
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO crypto_spreads
                (symbol, at_utc, bid, ask, mark, spread_pct, routing, quote_time, source)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'robinhood')
            """,
            (
                q["symbol"],
                at_utc,
                q["bid"],
                q["ask"],
                q["mark"],
                q["spread_pct"],
                q["routing"],
                q["quote_time"],
            ),
        )
        inserted += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
    conn.commit()
    return inserted


def _window_start(now, window_days):
    if now is None:
        now = datetime.now(timezone.utc)
    elif isinstance(now, str):
        now = datetime.strptime(now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return (now - timedelta(days=window_days)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _spreads(conn, start, symbol=None):
    sql = "SELECT spread_pct FROM crypto_spreads WHERE at_utc >= ?"
    params = [start]
    if symbol is not None:
        sql += " AND symbol = ?"
        params.append(symbol)
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [r[0] for r in rows if r[0] is not None]


def half_spread(conn, symbol, cfg=None, now=None):
    settings = _cfg(cfg)
    start = _window_start(now, settings["window_days"])
    own = _spreads(conn, start, symbol)
    if len(own) >= settings["min_samples"]:
        return statistics.median(own) / 2.0
    # Too few quotes for this pair: a pooled estimate beats a hardcoded guess,
    # but only when the pool itself is large enough to be a measurement.
    pooled = _spreads(conn, start)
    if len(pooled) >= settings["min_samples"]:
        return statistics.median(pooled) / 2.0
    return settings["default_half_spread"]


def report(conn, now=None, cfg=None):
    settings = _cfg(cfg)
    start = _window_start(now, settings["window_days"])
    try:
        rows = conn.execute(
            "SELECT symbol, spread_pct FROM crypto_spreads WHERE at_utc >= ?",
            (start,),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    by_symbol = {}
    for symbol, spread in rows:
        if spread is None:
            continue
        by_symbol.setdefault(symbol, []).append(spread)
    out = []
    for symbol in sorted(by_symbol):
        vals = by_symbol[symbol]
        out.append(
            {
                "symbol": symbol,
                "n": len(vals),
                "median_spread_pct": statistics.median(vals),
                "mean_spread_pct": statistics.fmean(vals),
                "max_spread_pct": max(vals),
            }
        )
    return out


def _default_symbols(conn):
    pairs = list(crypto_data.DEFAULT_PAIRS)
    try:
        rows = conn.execute(
            "SELECT symbol, status, trading_disabled FROM crypto_listings"
        ).fetchall()
    except sqlite3.OperationalError:
        return pairs
    blocked = {
        r[0] for r in rows if r[1] != "online" or (r[2] or 0) == 1
    }
    return [p for p in pairs if p not in blocked]


def main(argv=None):
    parser = argparse.ArgumentParser(description="Robinhood crypto spread logger")
    parser.add_argument("--log", action="store_true", help="fetch and store quotes")
    parser.add_argument("--report", action="store_true", help="print measured spreads")
    args = parser.parse_args(argv)

    from universe import load_config
    cfg = load_config()

    conn = storage.connect(cfg["database"]["market_data_path"])
    try:
        if args.log:
            import robinhood_mcp  # lazy: only the CLI path touches the broker

            account = None
            try:
                with open("config/risk.yaml") as fh:
                    account = (yaml.safe_load(fh) or {}).get("robinhood", {}).get(
                        "account_number"
                    )
            except FileNotFoundError:
                account = None
            if not account:
                account = cfg.get("robinhood", {}).get("account_number")
            symbols = _default_symbols(conn)
            n = log_spreads(conn, robinhood_mcp.call, symbols, account)
            print(f"logged {n} quotes for {len(symbols)} symbols")
        if args.report:
            print(f"{'symbol':<12}{'n':>6}{'median%':>10}{'mean%':>10}{'max%':>10}")
            for row in report(conn, cfg=cfg.get("crypto_costs")):
                print(
                    f"{row['symbol']:<12}{row['n']:>6}"
                    f"{row['median_spread_pct'] * 100:>10.2f}"
                    f"{row['mean_spread_pct'] * 100:>10.2f}"
                    f"{row['max_spread_pct'] * 100:>10.2f}"
                )
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
