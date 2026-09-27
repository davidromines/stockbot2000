"""
options_lab.py: contract choice (at the money, target expiry, liquid quotes only),
fills (buy at ask, sell at bid), settlement at intrinsic value on expiration, and
the backtest/paper walk. Synthetic chains in memory; the fetch log is pre-filled
so nothing reaches the network.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import options_data as od
import options_lab as ol

FAILED = []
CFG = {"options": {"stake_usd": 100.0}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def quote(c, date, exp, strike, cp, bid, ask, delta):
    c.execute("INSERT INTO option_quotes (date, symbol, expiration, strike, cp, bid, ask, iv, delta) "
              "VALUES (?,?,?,?,?,?,?,0.3,?)", (date, "AAA", exp, strike, cp, bid, ask, delta))
    c.execute("INSERT OR IGNORE INTO option_fetch_log VALUES ('chain','AAA',?,1,'t')", (date,))


def main():
    c = sqlite3.connect(":memory:")
    ol.init(c)
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    s = ol.settings(CFG)
    d0, exp = "2024-01-08", "2024-02-09"
    for k, dc in ((95.0, 0.7), (100.0, 0.52), (105.0, 0.3)):
        quote(c, d0, exp, k, "C", 2.0, 2.2, dc)
        quote(c, d0, exp, k, "P", 1.8, 2.0, dc - 1)
    quote(c, d0, "2024-01-12", 100.0, "C", 1.0, 1.1, 0.5)          # too near: outside the DTE window
    legs = ol.pick(c, "AAA", d0, "C", (21, 60, 35), s)
    check("call: the at-the-money strike in the target expiry", legs and legs[0]["strike"] == 100.0
          and legs[0]["exp"] == exp and legs[0]["ask"] == 2.2, legs)
    st = ol.pick(c, "AAA", d0, "S", (21, 60, 35), s)
    check("straddle: call + put at one strike", st and {l["cp"] for l in st} == {"C", "P"}
          and len({l["strike"] for l in st}) == 1, st)
    c.execute("UPDATE option_quotes SET bid=0.1 WHERE strike=100 AND cp='C' AND expiration=?", (exp,))
    check("a wide market is refused", ol.pick(c, "AAA", d0, "C", (21, 60, 35), s) is None)
    c.execute("UPDATE option_quotes SET bid=2.0 WHERE strike=100 AND cp='C' AND expiration=?", (exp,))

    d1 = "2024-01-22"
    quote(c, d1, exp, 100.0, "C", 3.0, 3.3, 0.6)
    v = ol.value(c, "AAA", legs, d1)
    check("sold at the bid", v == 3.0, v)
    check("no quote that day -> None (try a later date)", ol.value(c, "AAA", legs, "2024-01-24") is None)
    c.execute("INSERT INTO prices VALUES ('AAA', ?, 107.5)", (exp,))
    v = ol.value(c, "AAA", legs, "2024-02-12")
    check("at expiration: intrinsic value from the stock's close", abs(v - 7.5) < 1e-9, v)

    ol.STRATEGIES["t_call"] = {"rule": "stock_signal", "legs": "C", "dte": (21, 60, 35), "hold": 5, "per_day": 1}
    n = ol.run(c, CFG, "t_call", [d0, d1], "BACKTEST", {d0: [("AAA", "test signal")]})
    t = c.execute("SELECT cost, value, ret, usd, reason FROM option_trades WHERE strategy='t_call'").fetchone()
    check("walk: opened on the signal, closed at the holding limit at the bid", n == 1 and t[0] == 2.2
          and t[1] == 3.0 and t[4] == "holding limit", t)
    check("return on premium and dollars on the stake", abs(t[2] - (3.0 / 2.2 - 1)) < 1e-12
          and abs(t[3] - 100 * t[2]) < 1e-9, t)
    r = ol.summarize(c, "t_call")
    check("summary", r["trades"] == 1 and r["win_rate"] == 1.0, r)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
