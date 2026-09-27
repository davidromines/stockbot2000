"""
The intraday signal engine. Addendum A §3, §18; Addendum B §B8; build step I7.

Evaluates intraday strategies against today's live 1-minute bars during market
hours — the same genome grammar as every other strategy, over a different
feature set built from the bars themselves:

    price          last close of the bar
    vwap           session volume-weighted average price so far
    pct_from_open  % change from the session's first bar
    pct_from_vwap  % distance from VWAP
    ret_15m        % change over the last 15 bars
    range_pct      session high-low range as % of the open
    minutes_open   minutes since the session opened

**Every intraday signal is SHADOW (B8).** Free sources keep about 60 days of
1-minute history, which cannot validate a strategy, and live polling does not
create research history. An intraday strategy therefore records what it WOULD
have done, in `intraday_signals`, and never reaches a slot or the broker, until
a historical intraday provider exists (quotes.IntradayHistory) and the strategy
has been validated on it. That is enforced here, not left to the caller:
`scan()` has no path to the execution engine.

A strategy is intraday when its strategy_meta row has `intraday` true.

    python intraday.py --scan        evaluate every intraday strategy now
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

import genome as gn
import quotes as qt

log = logging.getLogger("intraday")
FEATURES = ("price", "vwap", "pct_from_open", "pct_from_vwap", "ret_15m", "range_pct", "minutes_open")
STAKE = 20.0               # one slot's dollars per SHADOW position
NO_ENTRY_AFTER = 360       # minutes after the open (15:30 ET): no new positions
FLAT_AFTER = 380           # 15:50 ET: every open position closes
MIN_SCAN_GAP_S = 290       # slot_trader runs SIMULATION :00, SHADOW :02, LIVE :04 every 5 min: only the first scans


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intraday_signals (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            at           TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            version      INTEGER NOT NULL,
            symbol       TEXT NOT NULL,
            action       TEXT NOT NULL,
            price        REAL,
            bar_time     TEXT,
            features     TEXT,
            mode         TEXT NOT NULL DEFAULT 'SHADOW'
        )""")
    # Stage Q2 (owner, 2026-09-27): the SHADOW trade book — what each intraday
    # strategy WOULD have made, one $STAKE position per strategy and symbol,
    # always flat by the end of the session.
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intraday_open (
            strategy_key TEXT NOT NULL, version INTEGER NOT NULL, symbol TEXT NOT NULL,
            session TEXT NOT NULL, opened_at TEXT NOT NULL, entry_price REAL NOT NULL,
            last_price REAL, last_at TEXT,
            PRIMARY KEY (strategy_key, version, symbol))""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intraday_trades (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_key TEXT NOT NULL, version INTEGER NOT NULL, symbol TEXT NOT NULL,
            session TEXT NOT NULL, opened_at TEXT NOT NULL, entry_price REAL NOT NULL,
            closed_at TEXT NOT NULL, exit_price REAL NOT NULL, reason TEXT NOT NULL,
            ret_pct REAL NOT NULL, usd REAL NOT NULL, mode TEXT NOT NULL DEFAULT 'SHADOW')""")
    conn.execute("CREATE TABLE IF NOT EXISTS intraday_scans (at TEXT PRIMARY KEY)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS intraday_defs (
            strategy_key TEXT PRIMARY KEY, name TEXT, genome TEXT NOT NULL,
            universe TEXT NOT NULL, rationale TEXT, created_at TEXT)""")
    conn.commit()


def features(bars: pd.DataFrame, ticker: str) -> pd.DataFrame:
    """Per-bar intraday features from one session's 1-minute OHLCV (yfinance column names)."""
    if bars is None or bars.empty:
        return pd.DataFrame(columns=["ticker", "date", *FEATURES])
    b = bars.copy()
    typical = (b["High"] + b["Low"] + b["Close"]) / 3
    vol = b["Volume"].clip(lower=0)
    cumv = vol.cumsum().replace(0, float("nan"))
    out = pd.DataFrame({
        "ticker": ticker,
        "date": [str(t) for t in b.index],
        "price": b["Close"].to_numpy(),
        "vwap": ((typical * vol).cumsum() / cumv).to_numpy(),
    })
    first_open = float(b["Open"].iloc[0])
    out["pct_from_open"] = (out["price"] / first_open - 1) * 100
    out["pct_from_vwap"] = (out["price"] / out["vwap"] - 1) * 100
    out["ret_15m"] = out["price"].pct_change(15).to_numpy() * 100
    out["range_pct"] = ((b["High"].cummax() - b["Low"].cummin()) / first_open * 100).to_numpy()
    out["minutes_open"] = range(len(out))
    return out


def evaluate(genome: dict, frame: pd.DataFrame) -> dict:
    """{'entry': bool, 'exit': bool} for the LAST bar of `frame`."""
    if frame.empty:
        return {"entry": False, "exit": False}
    e = gn._as_bool(gn.evaluate(genome["entry"], frame)).to_numpy()
    x = gn._as_bool(gn.evaluate(genome["exit"], frame)).to_numpy() if genome.get("exit") else [False]
    return {"entry": bool(e[-1]), "exit": bool(x[-1])}


def intraday_strategies(conn) -> list:
    """(key, version, genome, universe) for strategies flagged intraday."""
    import strategy_objects as so
    so.init(conn)
    out = []
    for key, ver, universe in conn.execute(
            "SELECT strategy_key, version, universe FROM strategy_meta WHERE intraday IN ('true','1','True')"):
        g = so.genome(conn, key, ver)
        if g:
            try:
                uni = json.loads(universe) if universe else []
            except (TypeError, ValueError):
                uni = []
            out.append((key, ver, g, uni if isinstance(uni, list) else []))
    try:
        for key, g, uni in conn.execute("SELECT strategy_key, genome, universe FROM intraday_defs"):
            out.append((key, 1, json.loads(g), json.loads(uni)))
    except sqlite3.Error:
        pass
    return out


def _close(conn, key, ver, sym, row, price, at, reason) -> None:
    ret = (price / row["entry_price"] - 1) * 100
    conn.execute("INSERT INTO intraday_trades (strategy_key, version, symbol, session, opened_at, entry_price, "
                 "closed_at, exit_price, reason, ret_pct, usd) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (key, ver, sym, row["session"], row["opened_at"], row["entry_price"], at, price, reason,
                  ret, STAKE * ret / 100))
    conn.execute("DELETE FROM intraday_open WHERE strategy_key=? AND version=? AND symbol=?", (key, ver, sym))


def _open_rows(conn) -> dict:
    cur = conn.execute("SELECT strategy_key, version, symbol, session, opened_at, entry_price, last_price "
                       "FROM intraday_open")
    cols = [d[0] for d in cur.description]
    return {(r[0], r[1], r[2]): dict(zip(cols, r)) for r in cur.fetchall()}


def scan(conn, bars_fn=None, now: datetime | None = None) -> list:
    """
    Evaluate every intraday strategy now. SHADOW only (B8): records signals and a
    would-be trade book (intraday_open / intraday_trades), never an order.
    One position per strategy and symbol; entries stop at NO_ENTRY_AFTER, and
    everything closes at FLAT_AFTER — an intraday strategy never holds overnight.
    """
    init(conn)
    now = now or datetime.now(timezone.utc)
    if bars_fn is None:
        if not qt.market_open(now):
            return []
        last = conn.execute("SELECT MAX(at) FROM intraday_scans").fetchone()[0]
        if last and (now - datetime.fromisoformat(last)).total_seconds() < MIN_SCAN_GAP_S:
            return []

        def bars_fn(sym):
            import yfinance as yf
            return yf.Ticker(sym).history(period="1d", interval="1m", prepost=False)
    at = now.isoformat(timespec="seconds")
    conn.execute("INSERT OR IGNORE INTO intraday_scans VALUES (?)", (at,))
    session = now.astimezone(qt.NY).strftime("%Y-%m-%d")
    held = _open_rows(conn)
    # A position left from an earlier session (a missed end-of-day scan) closes at
    # its last seen price: an intraday strategy is never carried overnight.
    for (key, ver, sym), row in list(held.items()):
        if row["session"] != session:
            _close(conn, key, ver, sym, row, row["last_price"] or row["entry_price"], at,
                   "session ended before a scan closed it")
            held.pop((key, ver, sym))
    cache = {}
    out = []
    for key, ver, g, universe in intraday_strategies(conn):
        for sym in universe[:25]:
            try:
                if sym not in cache:
                    cache[sym] = features(bars_fn(sym), sym)
                f = cache[sym]
                v = evaluate(g, f)
            except Exception as e:                        # noqa: BLE001
                log.warning(f"{key} {sym}: {type(e).__name__}: {e}")
                continue
            if f.empty:
                continue
            last = f.iloc[-1]
            px, mins = float(last["price"]), int(last["minutes_open"])
            for action, fired in (("BUY", v["entry"]), ("SELL", v["exit"])):
                if fired:
                    conn.execute("INSERT INTO intraday_signals (at, strategy_key, version, symbol, action, "
                                 "price, bar_time, features, mode) VALUES (?,?,?,?,?,?,?,?,'SHADOW')",
                                 (at, key, ver, sym, action, px, str(last["date"]),
                                  json.dumps({k: float(last[k]) for k in FEATURES if pd.notna(last[k])})))
                    out.append((key, sym, action))
            row = held.get((key, ver, sym))
            if row is not None:
                if mins >= FLAT_AFTER:
                    _close(conn, key, ver, sym, row, px, at, "end of session")
                elif v["exit"]:
                    _close(conn, key, ver, sym, row, px, at, "exit rule")
                else:
                    conn.execute("UPDATE intraday_open SET last_price=?, last_at=? WHERE strategy_key=? AND "
                                 "version=? AND symbol=?", (px, at, key, ver, sym))
            elif v["entry"] and mins < NO_ENTRY_AFTER:
                conn.execute("INSERT INTO intraday_open VALUES (?,?,?,?,?,?,?,?)",
                             (key, ver, sym, session, at, px, px, at))
    conn.commit()
    return out


def report(conn) -> list:
    """Per intraday strategy: SHADOW trades, winners, money made per trade and in total ($STAKE each)."""
    init(conn)
    rows = conn.execute("SELECT strategy_key, COUNT(*), SUM(usd > 0), SUM(usd), AVG(ret_pct), "
                        "COUNT(DISTINCT session) FROM intraday_trades GROUP BY strategy_key "
                        "ORDER BY SUM(usd) DESC").fetchall()
    return [{"strategy": r[0], "trades": r[1], "won": r[2], "usd": r[3], "avg_pct": r[4], "sessions": r[5]}
            for r in rows]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Intraday signal engine (SHADOW only, B8).")
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--report", action="store_true", help="SHADOW money made per intraday strategy")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    n = intraday_strategies(conn)
    print(f"{len(n)} intraday strateg{'y' if len(n) == 1 else 'ies'} registered")
    if args.report:
        for r in report(conn):
            print(f"  {r['strategy']:<34} {r['trades']:>4} trades  {r['won']:>4} won  "
                  f"{r['usd']:+8.2f} $  {r['avg_pct']:+.3f}%/trade  {r['sessions']} sessions")
    if args.scan:
        r = scan(conn)
        print(f"{len(r)} SHADOW signal(s)" if qt.market_open() else "market closed — nothing to scan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
