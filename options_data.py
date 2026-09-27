"""
Options data (Stage R, owner 2026-09-27: "build a paper trading system and back
fill the database with public data sources").

Source: DoltHub post-no-preference/options, a free public mirror of US equity
option end-of-day data, queried over its SQL API (no key, no install):

    option_chain        date, symbol, expiration, strike, Call/Put, bid, ask,
                        implied vol, delta, gamma, theta, vega, rho
    volatility_history  per symbol and date: historical vol and implied vol now,
                        a week ago, a month ago, 52-week highs and lows

Measured 2026-09-27: ~2,000 US stocks and ETFs; from early 2020 on Mondays,
Wednesdays and Fridays, daily in recent years; ~150-200 contracts per symbol and
date around the money in three expiries (~2, 5 and 7 weeks). Updated daily.
The API returns at most 1,000 rows per query, so a date's volatility table is
paged by symbol and chains are fetched per symbol and date, only where a
strategy needs them. Every fetch is logged (option_fetch_log), so a backfill
resumes and never asks twice — an empty answer (no data that day) is logged too.

    ./venv/bin/python options_data.py --vol-backfill [--start 2020-01-01]   # all symbols' IV/HV
    ./venv/bin/python options_data.py --chain AAPL 2024-01-08               # one chain
    ./venv/bin/python options_data.py --daily                                # newest vol date
    ./venv/bin/python options_data.py --status
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("options_data")
API = "https://www.dolthub.com/api/v1alpha1/post-no-preference/options/master"
PAGE = 1000
VOL_COLS = ("hv_current", "hv_week_ago", "hv_month_ago", "hv_year_high", "hv_year_low",
            "iv_current", "iv_week_ago", "iv_month_ago", "iv_year_high", "iv_year_low")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_quotes (
            date TEXT NOT NULL, symbol TEXT NOT NULL, expiration TEXT NOT NULL, strike REAL NOT NULL,
            cp TEXT NOT NULL, bid REAL, ask REAL, iv REAL, delta REAL, gamma REAL, theta REAL, vega REAL,
            source TEXT NOT NULL DEFAULT 'dolt',
            PRIMARY KEY (date, symbol, expiration, strike, cp))""")
    conn.execute("CREATE INDEX IF NOT EXISTS option_quotes_sym ON option_quotes (symbol, date)")
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS option_vol (
            date TEXT NOT NULL, symbol TEXT NOT NULL, {', '.join(c + ' REAL' for c in VOL_COLS)},
            source TEXT NOT NULL DEFAULT 'dolt', PRIMARY KEY (date, symbol))""")
    conn.execute("CREATE INDEX IF NOT EXISTS option_vol_sym ON option_vol (symbol, date)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_fetch_log (
            kind TEXT NOT NULL, symbol TEXT NOT NULL, date TEXT NOT NULL, rows INTEGER NOT NULL,
            at TEXT NOT NULL, PRIMARY KEY (kind, symbol, date))""")
    conn.commit()


def query(sql: str, tries: int = 4) -> list:
    """Rows for one SQL query against the public API. A RowLimit answer returns its
    1,000 rows (callers page); a timeout or HTTP error is retried with backoff."""
    url = API + "?" + urllib.parse.urlencode({"q": sql})
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=120) as r:
                d = json.load(r)
            status = d.get("query_execution_status")
            if status in ("Success", "RowLimit"):
                return d.get("rows") or []
            last = d.get("query_execution_message")
        except Exception as e:                           # noqa: BLE001 — network: retry
            last = f"{type(e).__name__}: {e}"
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"options API failed after {tries} tries: {last}")


def _f(x):
    return None if x in (None, "") else float(x)


def _done(conn, kind, symbol, date) -> bool:
    return conn.execute("SELECT 1 FROM option_fetch_log WHERE kind=? AND symbol=? AND date=?",
                        (kind, symbol, date)).fetchone() is not None


def _log(conn, kind, symbol, date, n) -> None:
    conn.execute("INSERT OR REPLACE INTO option_fetch_log VALUES (?,?,?,?,?)",
                 (kind, symbol, date, n, datetime.now(timezone.utc).isoformat(timespec="seconds")))


def chain(conn, symbol: str, date: str) -> list:
    """The option chain for `symbol` on `date` (dicts), from the local store or fetched once."""
    init(conn)
    if not _done(conn, "chain", symbol, date):
        rows = query(f"SELECT * FROM option_chain WHERE date='{date}' AND act_symbol='{symbol}'")
        conn.executemany("INSERT OR REPLACE INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, "
                         "delta, gamma, theta, vega) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                         [(r["date"], r["act_symbol"], r["expiration"], float(r["strike"]), r["call_put"][0].upper(),
                           _f(r["bid"]), _f(r["ask"]), _f(r["vol"]), _f(r["delta"]), _f(r["gamma"]),
                           _f(r["theta"]), _f(r["vega"])) for r in rows])
        _log(conn, "chain", symbol, date, len(rows))
        conn.commit()
    cur = conn.execute("SELECT date, symbol, expiration, strike, cp, bid, ask, iv, delta FROM option_quotes "
                       "WHERE symbol=? AND date=?", (symbol, date))
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def vol_date(conn, date: str) -> int:
    """Every symbol's volatility row for one date, paged by symbol. Returns rows stored."""
    init(conn)
    if _done(conn, "vol", "*", date):
        return 0
    after, n = "", 0
    while True:
        rows = query(f"SELECT * FROM volatility_history WHERE date='{date}' AND act_symbol > '{after}' "
                     f"ORDER BY act_symbol LIMIT {PAGE}")
        conn.executemany(f"INSERT OR REPLACE INTO option_vol (date, symbol, {', '.join(VOL_COLS)}) "
                         f"VALUES (?,?,{','.join('?' * len(VOL_COLS))})",
                         [(r["date"], r["act_symbol"], *[_f(r.get(c)) for c in VOL_COLS]) for r in rows])
        n += len(rows)
        if len(rows) < PAGE:
            break
        after = rows[-1]["act_symbol"]
    _log(conn, "vol", "*", date, n)
    conn.commit()
    return n


def sessions(conn, start: str, end: str | None = None) -> list:
    """Trading sessions from our own SPY history (the Dolt dates are a subset)."""
    q = "SELECT date FROM prices WHERE ticker='SPY' AND date >= ?" + (" AND date <= ?" if end else "") + " ORDER BY date"
    return [r[0] for r in conn.execute(q, (start, end) if end else (start,))]


def vol_backfill(conn, start: str = "2020-01-01", end: str | None = None) -> dict:
    todo = [d for d in sessions(conn, start, end) if not _done(conn, "vol", "*", d)]
    got = empty = 0
    for i, d in enumerate(todo, 1):
        n = vol_date(conn, d)
        got += bool(n)
        empty += not n
        if i % 20 == 0:
            log.info(f"vol backfill: {i}/{len(todo)} dates, {got} with data, latest {d}")
    return {"dates": len(todo), "with_data": got, "empty": empty}


def status(conn) -> dict:
    init(conn)
    v = conn.execute("SELECT COUNT(*), COUNT(DISTINCT date), MIN(date), MAX(date), COUNT(DISTINCT symbol) "
                     "FROM option_vol").fetchone()
    q = conn.execute("SELECT COUNT(*), COUNT(DISTINCT symbol||date) FROM option_quotes").fetchone()
    return {"vol_rows": v[0], "vol_dates": v[1], "vol_from": v[2], "vol_to": v[3], "vol_symbols": v[4],
            "chain_rows": q[0], "chains": q[1]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--vol-backfill", action="store_true")
    ap.add_argument("--start", default="2020-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--chain", nargs=2, metavar=("SYMBOL", "DATE"))
    ap.add_argument("--daily", action="store_true", help="volatility rows for the newest sessions not yet fetched")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=120)
    init(conn)
    if a.vol_backfill:
        print(json.dumps(vol_backfill(conn, a.start, a.end)))
    if a.daily:
        last = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
        recent = sessions(conn, "2000-01-01")[-5:]
        # Re-ask the last five sessions: the mirror publishes a day's rows the next morning.
        for d in recent:
            if d in recent[-5:] and conn.execute("SELECT rows FROM option_fetch_log WHERE kind='vol' AND symbol='*' "
                                                 "AND date=?", (d,)).fetchone() == (0,):
                conn.execute("DELETE FROM option_fetch_log WHERE kind='vol' AND symbol='*' AND date=?", (d,))
        print(json.dumps(vol_backfill(conn, recent[0], last)))
    if a.chain:
        rows = chain(conn, a.chain[0].upper(), a.chain[1])
        print(f"{len(rows)} contracts")
    if a.status:
        print(json.dumps(status(conn), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
