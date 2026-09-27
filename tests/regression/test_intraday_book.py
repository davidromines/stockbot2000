"""
The intraday SHADOW trade book (Stage Q2): opens on an entry, closes on the exit
rule, is flat by 15:50 ET, never carries overnight, scans once per 5 minutes,
and records dollars on a $20 position. In-memory database; bars are synthetic.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import intraday
import intraday_set

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def bars(closes):
    idx = pd.date_range("2026-09-28 09:30", periods=len(closes), freq="1min", tz="America/New_York")
    return pd.DataFrame({"Open": closes, "High": closes, "Low": closes, "Close": closes,
                         "Volume": [1000] * len(closes)}, index=idx)


G = {"entry": {"op": "lt", "args": [{"col": "pct_from_open"}, {"const": -1.0}]},
     "exit": {"op": "gt", "args": [{"col": "pct_from_open"}, {"const": 0.0}]}, "risk": {}}
NOW = datetime(2026, 9, 28, 15, 0, tzinfo=timezone.utc)


def main():
    c = sqlite3.connect(":memory:")
    intraday.init(c)
    c.execute("INSERT INTO intraday_defs VALUES ('intraday:t', 't', ?, '[\"AAA\"]', 'test', 'now')",
              (__import__("json").dumps(G),))
    down = [100.0] * 40 + [98.0]                    # 40 minutes in, -2%: entry
    intraday.scan(c, bars_fn=lambda s: bars(down), now=NOW)
    o = c.execute("SELECT entry_price FROM intraday_open").fetchall()
    check("entry opens one position at the scan price", o == [(98.0,)], o)
    intraday.scan(c, bars_fn=lambda s: bars(down + [98.5]), now=NOW)
    check("still open while the exit rule is false", c.execute("SELECT COUNT(*) FROM intraday_open").fetchone()[0] == 1)
    intraday.scan(c, bars_fn=lambda s: bars(down + [100.5]), now=NOW)
    t = c.execute("SELECT entry_price, exit_price, reason, usd FROM intraday_trades").fetchall()
    check("exit rule closes it; dollars on $20", len(t) == 1 and t[0][2] == "exit rule"
          and abs(t[0][3] - 20 * (100.5 / 98 - 1)) < 1e-9, t)
    late = [100.0] * 370 + [98.0]                   # entry signal after 15:30 ET: refused
    intraday.scan(c, bars_fn=lambda s: bars(late), now=NOW)
    check("no new entries after 15:30 ET", c.execute("SELECT COUNT(*) FROM intraday_open").fetchone()[0] == 0)
    intraday.scan(c, bars_fn=lambda s: bars(down), now=NOW)
    flat = [100.0] * 40 + [98.0] * 345               # 385 minutes in: past 15:50 ET
    intraday.scan(c, bars_fn=lambda s: bars(flat), now=NOW)
    r = c.execute("SELECT reason FROM intraday_trades ORDER BY id DESC LIMIT 1").fetchone()[0]
    check("flat by 15:50 ET", r == "end of session", r)
    intraday.scan(c, bars_fn=lambda s: bars(down), now=NOW)
    nxt = datetime(2026, 9, 29, 15, 0, tzinfo=timezone.utc)
    intraday.scan(c, bars_fn=lambda s: bars([100.0] * 10), now=nxt)
    r = c.execute("SELECT reason FROM intraday_trades ORDER BY id DESC LIMIT 1").fetchone()[0]
    check("a position from an earlier session is closed, never carried", "session ended" in r, r)
    rep = intraday.report(c)
    check("report per strategy", rep and rep[0]["strategy"] == "intraday:t" and rep[0]["trades"] == 3, rep)
    n = intraday_set.register(c)
    check("the six-strategy set registers", n == 6 and len(intraday.intraday_strategies(c)) == 7)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
