"""
regime_filter.py: RISK_OFF when SPY is below its 200-day average; ON blocks new entries,
SHADOW only records, OFF does nothing; UNKNOWN never blocks; an unknown mode fails safe
to SHADOW. In-memory database with a synthetic SPY series.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import regime_filter as rf

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def db(falling: bool):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    d = pd.bdate_range("2025-01-01", periods=320).strftime("%Y-%m-%d")
    px = np.r_[np.linspace(100, 150, 260), np.linspace(150, 100 if falling else 170, 60)]
    c.executemany("INSERT INTO prices VALUES ('SPY',?,?)", list(zip(d, px)))
    c.commit()
    return c


def main():
    on, off = db(False), db(True)
    check("rising SPY above its 200-day average is RISK_ON", rf.state(on)["state"] == "RISK_ON", rf.state(on))
    check("SPY fallen below it is RISK_OFF", rf.state(off)["state"] == "RISK_OFF", rf.state(off))
    r = rf.check(off, {"regime_filter": {"mode": "ON"}}, [1, 2])
    check("ON + RISK_OFF blocks new entries, with the reason", r["block"] and "200-day" in r["reason"], r)
    r = rf.check(off, {"regime_filter": {"mode": "SHADOW"}}, [1])
    check("SHADOW records but never blocks", not r["block"] and r["would_block"], r)
    check("the shadow decision is logged",
          off.execute("SELECT COUNT(*) FROM regime_filter_log WHERE would_block=1").fetchone()[0] >= 1)
    check("OFF does nothing", not rf.check(off, {"regime_filter": {"mode": "OFF"}})["block"])
    check("ON in a rising market blocks nothing", not rf.check(on, {"regime_filter": {"mode": "ON"}})["block"])
    check("an unknown mode fails safe to SHADOW", rf.settings({"regime_filter": {"mode": "yes"}})["mode"] == "SHADOW")
    empty = sqlite3.connect(":memory:")
    empty.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    empty.execute("INSERT INTO prices VALUES ('SPY','2026-01-02',100)")
    check("too little history is UNKNOWN and never blocks",
          rf.state(empty)["state"] == "UNKNOWN" and not rf.check(empty, {"regime_filter": {"mode": "ON"}})["block"])
    src = open(os.path.join(os.path.dirname(rf.__file__), "slot_trader.py")).read()
    check("the slot trader consults it before entries", "regime_filter.check(" in src)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
