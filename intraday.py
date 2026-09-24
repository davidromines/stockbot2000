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
    return out


def scan(conn, bars_fn=None) -> list:
    """Evaluate every intraday strategy now. Records SHADOW signals only (B8)."""
    init(conn)
    if bars_fn is None:
        if not qt.market_open():
            return []

        def bars_fn(sym):
            import yfinance as yf
            return yf.Ticker(sym).history(period="1d", interval="1m", prepost=False)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    out = []
    for key, ver, g, universe in intraday_strategies(conn):
        for sym in universe[:25]:
            try:
                f = features(bars_fn(sym), sym)
                v = evaluate(g, f)
            except Exception as e:                        # noqa: BLE001
                log.warning(f"{key} {sym}: {type(e).__name__}: {e}")
                continue
            for action, fired in (("BUY", v["entry"]), ("SELL", v["exit"])):
                if fired:
                    last = f.iloc[-1]
                    conn.execute("INSERT INTO intraday_signals (at, strategy_key, version, symbol, action, "
                                 "price, bar_time, features, mode) VALUES (?,?,?,?,?,?,?,?,'SHADOW')",
                                 (now, key, ver, sym, action, float(last["price"]), str(last["date"]),
                                  json.dumps({k: float(last[k]) for k in FEATURES if pd.notna(last[k])})))
                    out.append((key, sym, action))
    conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Intraday signal engine (SHADOW only, B8).")
    ap.add_argument("--scan", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    n = intraday_strategies(conn)
    print(f"{len(n)} intraday strateg{'y' if len(n) == 1 else 'ies'} registered")
    if args.scan:
        r = scan(conn)
        print(f"{len(r)} SHADOW signal(s)" if qt.market_open() else "market closed — nothing to scan")
    return 0


if __name__ == "__main__":
    sys.exit(main())
