"""
The intraday strategy set (Stage Q2, owner 2026-09-27: test short-term trading).

Six same-day strategies on 1-minute bars, recorded in SHADOW by intraday.scan():
each would-be trade opens and closes inside one session and lands in
intraday_trades with the money it would have made on a $20 position. They live
in intraday_defs, not the league: B8 keeps intraday strategies away from slots
and the broker until an intraday history can validate them, and the account's
pattern-day-trader limit (3 same-day round trips in 5 sessions) would cap them
anyway. Features (all from today's bars): pct_from_open, pct_from_vwap,
ret_15m, range_pct, minutes_open — percentages, minutes since 09:30 ET.

    ./venv/bin/python intraday_set.py --register
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timezone

import intraday

# The most traded US names and index ETFs: tight markets, reliable 1-minute bars.
UNIVERSE = ["SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "AMZN", "META", "GOOGL", "TSLA",
            "AMD", "AVGO", "NFLX", "JPM", "XOM", "COST", "LLY", "UNH", "BAC", "PLTR"]


def c(x):
    return {"col": x}


def k(v):
    return {"const": float(v)}


def gt(a, b):
    return {"op": "gt", "args": [a, b]}


def lt(a, b):
    return {"op": "lt", "args": [a, b]}


def and_(*xs):
    out = xs[0]
    for x in xs[1:]:
        out = {"op": "and", "args": [out, x]}
    return out


NEVER = lt(c("price"), k(0))       # held to the end-of-session close


def G(entry, exit_=None):
    return {"entry": entry, "exit": exit_ or NEVER, "risk": {"max_hold_days": 0}}


STRATEGIES = {
    "intraday:vwap_reversion": (
        "VWAP reversion: a stock 0.8% below its session VWAP after the first half hour snaps back to VWAP.",
        G(and_(lt(c("pct_from_vwap"), k(-0.8)), gt(c("minutes_open"), k(30))), gt(c("pct_from_vwap"), k(0)))),
    "intraday:vwap_trend": (
        "VWAP trend: up 0.8% on the day and above VWAP in the first two hours; ride it until it loses VWAP.",
        G(and_(gt(c("pct_from_vwap"), k(0.5)), gt(c("pct_from_open"), k(0.8)),
               gt(c("minutes_open"), k(30)), lt(c("minutes_open"), k(120))), lt(c("pct_from_vwap"), k(0)))),
    "intraday:opening_breakout": (
        "Opening-range breakout: more than 1% above the open between 30 and 90 minutes in; out if it gives most back.",
        G(and_(gt(c("pct_from_open"), k(1.0)), gt(c("minutes_open"), k(29)), lt(c("minutes_open"), k(90))),
          lt(c("pct_from_open"), k(0.3)))),
    "intraday:dip_15m": (
        "15-minute dip: a 1% drop in fifteen minutes is bought for the bounce.",
        G(and_(lt(c("ret_15m"), k(-1.0)), gt(c("minutes_open"), k(30))), gt(c("ret_15m"), k(0.3)))),
    "intraday:late_day_momentum": (
        "Last-half-hour momentum: up 0.5% on the day at 15:00 ET, held into the close (Gao et al. 2018).",
        G(and_(gt(c("pct_from_open"), k(0.5)), gt(c("minutes_open"), k(329)), lt(c("minutes_open"), k(345))))),
    "intraday:first_hour_fade": (
        "First-hour fade: down 1% on the day after the first hour is bought until it regains VWAP.",
        G(and_(lt(c("pct_from_open"), k(-1.0)), gt(c("minutes_open"), k(59)), lt(c("minutes_open"), k(75))),
          gt(c("pct_from_vwap"), k(0)))),
}


def register(conn) -> int:
    intraday.init(conn)
    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    for key, (why, g) in STRATEGIES.items():
        conn.execute("INSERT OR REPLACE INTO intraday_defs VALUES (?,?,?,?,?, COALESCE((SELECT created_at "
                     "FROM intraday_defs WHERE strategy_key=?), ?))",
                     (key, key.split(":", 1)[1].replace("_", " "), json.dumps(g, sort_keys=True),
                      json.dumps(UNIVERSE), why, key, now))
    conn.commit()
    return len(STRATEGIES)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--register", action="store_true")
    a = ap.parse_args(argv)
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    if a.register:
        print(f"{register(conn)} intraday strategies registered on {len(UNIVERSE)} symbols")
    return 0


if __name__ == "__main__":
    sys.exit(main())
