"""Stage Q3: accumulate 1-minute bars for the same-day trading universe.

Free 1-minute history only reaches back about a week, so this stage is a
collector first and a query layer second: every day it runs is a day of
history that cannot be recovered later. Bars are stored raw (unadjusted),
unlike the daily price tables, because the adjustment factors for a session
are not knowable until after the fact.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

import pandas as pd

NY = "America/New_York"
FIELDS = ("Open", "High", "Low", "Close", "Volume")
OUT_COLUMNS = ["ticker", "ts", "open", "high", "low", "close", "volume"]


def init(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS minute_bars(
            ticker TEXT, ts TEXT,
            open REAL, high REAL, low REAL, close REAL, volume REAL,
            PRIMARY KEY(ticker, ts)
        ) WITHOUT ROWID
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS minute_bars_log(
            run_at TEXT PRIMARY KEY, tickers INTEGER, rows INTEGER,
            first_ts TEXT, last_ts TEXT, note TEXT
        )
        """
    )
    conn.commit()


def _to_ny(index):
    idx = pd.DatetimeIndex(index)
    if idx.tz is None:
        # yfinance always returns tz-aware stamps; a naive index is ambiguous,
        # so treat it as UTC rather than silently assuming New York.
        idx = idx.tz_localize("UTC")
    return idx.tz_convert(NY)


def _flatten(df, ticker=None):
    """Return a frame with plain OHLCV columns plus a ticker column."""
    if isinstance(df.columns, pd.MultiIndex):
        frames = []
        for tk in df.columns.get_level_values(0).unique():
            sub = df[tk]
            sub = sub[[c for c in FIELDS if c in sub.columns]].copy()
            sub["ticker"] = tk
            frames.append(sub)
        if not frames:
            return pd.DataFrame(columns=OUT_COLUMNS)
        return pd.concat(frames)
    if ticker is None:
        raise ValueError("single-level columns require an explicit ticker")
    sub = df[[c for c in FIELDS if c in df.columns]].copy()
    sub["ticker"] = ticker
    return sub


def normalize(df, now=None, ticker=None):
    if df is None or len(df) == 0:
        return pd.DataFrame(columns=OUT_COLUMNS)
    if now is None:
        now = datetime.now(timezone.utc)
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    now = now.astimezone(timezone.utc)

    flat = _flatten(df, ticker=ticker)
    if len(flat) == 0:
        return pd.DataFrame(columns=OUT_COLUMNS)

    flat = flat.copy()
    flat.index = _to_ny(flat.index)
    flat = flat.rename_axis("bar_start").reset_index()

    minutes = flat["bar_start"].dt.hour * 60 + flat["bar_start"].dt.minute
    flat = flat[(minutes >= 9 * 60 + 30) & (minutes < 16 * 60)]

    flat = flat.dropna(subset=["Close"])
    # A bar for the minute still in progress is partial; keeping it would bake
    # a truncated close into history that is never overwritten.
    complete = flat["bar_start"] + pd.Timedelta(minutes=1) <= pd.Timestamp(now)
    flat = flat[complete]

    for col in ("Open", "High", "Low", "Close"):
        flat = flat[flat[col] > 0]
    flat = flat[flat["High"] >= flat["Low"]]

    out = pd.DataFrame(
        {
            "ticker": flat["ticker"].astype(str),
            "ts": flat["bar_start"].dt.strftime("%Y-%m-%d %H:%M"),
            "open": flat["Open"].astype(float),
            "high": flat["High"].astype(float),
            "low": flat["Low"].astype(float),
            "close": flat["Close"].astype(float),
            "volume": flat["Volume"].astype(float) if "Volume" in flat else 0.0,
        }
    )
    return out.sort_values(["ticker", "ts"]).reset_index(drop=True)[OUT_COLUMNS]


def _default_download(tickers):
    import yfinance as yf

    return yf.download(
        tickers,
        period="7d",
        interval="1m",
        progress=False,
        auto_adjust=False,
        group_by="ticker",
        threads=False,
    )


def _log(conn, run_at, tickers, rows, first_ts, last_ts, note):
    conn.execute(
        "INSERT OR REPLACE INTO minute_bars_log"
        "(run_at, tickers, rows, first_ts, last_ts, note) VALUES (?,?,?,?,?,?)",
        (run_at, tickers, rows, first_ts, last_ts, note),
    )
    conn.commit()


def collect(conn, tickers=None, download=None, now=None):
    if tickers is None:
        from intraday_set import UNIVERSE

        tickers = list(UNIVERSE)
    tickers = list(tickers)
    if download is None:
        download = _default_download
    if now is None:
        now = datetime.now(timezone.utc)
    run_at = now.astimezone(timezone.utc).isoformat()

    try:
        raw = download(tickers)
        bars = normalize(raw, now=now)
    except Exception as exc:  # a failed fetch must not kill the daily loop
        _log(conn, run_at, len(tickers), 0, None, None, "error: %s" % exc)
        return {"tickers": len(tickers), "rows_new": 0, "first_ts": None, "last_ts": None}

    before = conn.total_changes
    conn.executemany(
        "INSERT OR IGNORE INTO minute_bars"
        "(ticker, ts, open, high, low, close, volume) VALUES (?,?,?,?,?,?,?)",
        list(bars.itertuples(index=False, name=None)),
    )
    conn.commit()
    rows_new = conn.total_changes - before

    first_ts = bars["ts"].min() if len(bars) else None
    last_ts = bars["ts"].max() if len(bars) else None
    _log(conn, run_at, len(tickers), rows_new, first_ts, last_ts, "ok")
    return {
        "tickers": len(tickers),
        "rows_new": rows_new,
        "first_ts": first_ts,
        "last_ts": last_ts,
    }


def coverage(conn):
    rows = conn.execute(
        """
        SELECT ticker, COUNT(DISTINCT substr(ts, 1, 10)) AS sessions,
               MIN(ts), MAX(ts), COUNT(*)
        FROM minute_bars GROUP BY ticker ORDER BY ticker
        """
    ).fetchall()
    return [
        {"ticker": r[0], "sessions": r[1], "first_ts": r[2], "last_ts": r[3], "bars": r[4]}
        for r in rows
    ]


def session(conn, ticker, day):
    rows = conn.execute(
        "SELECT ticker, ts, open, high, low, close, volume FROM minute_bars "
        "WHERE ticker = ? AND substr(ts, 1, 10) = ? ORDER BY ts",
        (ticker, day),
    ).fetchall()
    return pd.DataFrame(rows, columns=OUT_COLUMNS)


def replay(conn, day, tickers=None):
    sql = "SELECT ticker, ts, open, high, low, close, volume FROM minute_bars " \
          "WHERE substr(ts, 1, 10) = ?"
    params = [day]
    if tickers is not None:
        tickers = list(tickers)
        sql += " AND ticker IN (%s)" % ",".join("?" * len(tickers))
        params.extend(tickers)
    sql += " ORDER BY ts, ticker"
    rows = conn.execute(sql, params).fetchall()

    current_ts = None
    bucket = {}
    for ticker, ts, o, h, l, c, v in rows:
        if current_ts is not None and ts != current_ts:
            yield current_ts, bucket
            bucket = {}
        current_ts = ts
        bucket[ticker] = {
            "ticker": ticker, "ts": ts, "open": o, "high": h, "low": l,
            "close": c, "volume": v,
        }
    if current_ts is not None:
        yield current_ts, bucket


def main(argv=None):
    from universe import load_config

    parser = argparse.ArgumentParser(description="Stage Q3 minute bar collection")
    parser.add_argument("--collect", action="store_true")
    parser.add_argument("--coverage", action="store_true")
    parser.add_argument("--replay", nargs=2, metavar=("DAY", "TICKER"))
    args = parser.parse_args(argv)

    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    try:
        init(conn)
        if args.collect:
            print(collect(conn))
        if args.coverage:
            print("%-10s %8s %-16s %-16s %8s" % ("ticker", "sessions", "first_ts", "last_ts", "bars"))
            for row in coverage(conn):
                print("%-10s %8d %-16s %-16s %8d" % (
                    row["ticker"], row["sessions"], row["first_ts"] or "-",
                    row["last_ts"] or "-", row["bars"]))
        if args.replay:
            day, ticker = args.replay
            bars = session(conn, ticker, day)
            for _, row in pd.concat([bars.head(5), bars.tail(5)]).iterrows():
                print(row.to_dict())
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
