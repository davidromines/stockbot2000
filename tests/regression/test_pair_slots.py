"""
Regression test: a bull/bear ETF switching fund can hold a slot (roadmap step 3).

Pinned:
  - pair_funds.next_leg() predicts the leg the fund's own replay holds at the
    next bar — the slot trades exactly what the forward record trades
  - min_hold delays a switch in next_leg just as it does in the replay
  - step() still records the same curve after the replay() refactor
  - a pair holder gets a VALID stop plan (price stop from slots.pair_risk plus
    the switch as strategy exit), so slots.assess no longer rejects it
  - slot_trader buys the fund's leg; when the fund switches it sells the old
    leg and buys the new one, sized from the slot's own shares

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pair_funds
import quotes as qt
import slot_trader as st
import slots
import stop_plans

FAILED = []
CFG = {"costs": {}}


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def market(n_up: int, n_down: int):
    """SPY rises for n_up sessions then falls for n_down; SH mirrors it."""
    days = pd.bdate_range("2026-01-02", periods=n_up + n_down).strftime("%Y-%m-%d")
    spy = np.concatenate([100 * 1.01 ** np.arange(n_up), 100 * 1.01 ** (n_up - 1) * 0.98 ** np.arange(1, n_down + 1)])
    return list(days), spy


def db(days, spy, min_hold=1, upto=None):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    for d, p in list(zip(days, spy))[:upto]:
        for t, px in (("SPY", p), ("SH", 10000.0 / p)):
            c.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,1e6,'t')", (t, d, px, px, px, px))
    pair_funds.init(c)
    c.execute("INSERT INTO pair_funds (name,label,bull,bear,signal,method,param,min_hold,capital_usd,"
              "started_on,status) VALUES ('sp500_1x','S&P Switch 1x','SPY','SH','SPY','roc',5,?,100.0,?,'open')",
              (min_hold, days[10]))
    c.commit()
    return c


def main():
    days, spy = market(40, 12)

    c = db(days, spy, upto=35)
    nl = pair_funds.next_leg(c, CFG, "sp500_1x")
    check("rising market: next leg is the bull ETF", nl and nl["leg"] == "SPY" and not nl["switching"], nl)

    # Prediction == what the replay actually holds one bar later, at every step.
    agree = True
    for k in range(20, len(days)):
        pred = pair_funds.next_leg(db(days, spy, upto=k), CFG, "sp500_1x")
        r = dict(db(days, spy, upto=k + 1).execute("SELECT * FROM pair_funds").fetchone())
        res = pair_funds.replay(db(days, spy, upto=k + 1), CFG, r)
        actual = {"ERX": "SPY", "ERY": "SH"}[res["held"]]
        if pred["leg"] != actual:
            agree = False
            print(f"    day {k}: predicted {pred['leg']}, replay holds {actual}")
    check("next_leg matches the replay's next holding on every day", agree)

    c = db(days, spy)
    nl = pair_funds.next_leg(c, CFG, "sp500_1x")
    check("falling market: next leg is the bear ETF", nl["leg"] == "SH", nl)
    c = db(days, spy, min_hold=500, upto=44)
    nl = pair_funds.next_leg(c, CFG, "sp500_1x")
    check("min_hold delays the switch", nl["leg"] == "SPY" and not nl["switching"], nl)
    check("unknown / closed fund -> None", pair_funds.next_leg(c, CFG, "nope") is None)
    c = db(days, spy, upto=35)
    c.execute("DELETE FROM prices WHERE ticker='SH' AND date=?", (days[34],))
    check("a leg missing the newest bar -> None (no stale signal)", pair_funds.next_leg(c, CFG, "sp500_1x") is None)

    c = db(days, spy)
    pair_funds.step(c, CFG)
    e = c.execute("SELECT equity_usd, switches FROM pair_fund_equity").fetchone()
    r = dict(c.execute("SELECT * FROM pair_funds").fetchone())
    check("step() records the replay's curve", e and abs(e[0] - pair_funds.replay(c, CFG, r)["final"]) < 1e-9
          and e[1] >= 1, tuple(e) if e else None)

    # A pair holder's slot rules and stop plan.
    g = slots.genome_for(None, "pair:sp500_1x", 1)
    plan = stop_plans.from_genome(g)
    ok, why = stop_plans.validate(plan)
    check("pair slot has a valid stop plan (price stop + switch exit)", ok and
          {r["type"] for r in plan} == {"atr", "strategy"}, (plan, why))

    # slot_trader: buy the leg, then switch.
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    for d in ("2026-09-22", "2026-09-23"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
    for t, atr in (("SPY", 8.0), ("SH", 0.4)):
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', ?, 5e9)", (t, atr))
        c.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', 8e11)", (t,))
    st.init(c)
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
              "reason) VALUES ('2026-09-23T00:00:00', 3, 'ASSIGN', 'pair:sp500_1x', 1, 20.0, 'SIMULATION', 't')")
    c.commit()
    leg = {"v": {"leg": "SPY", "held": "SPY", "bull": "SPY", "bear": "SH", "switching": False}}
    pair_funds.next_leg = lambda conn, cfg, name: leg["v"]
    quotes = qt.FixedQuotes({"SPY": 700.0, "SH": 32.0}, conn=c)

    r = st.trade(c, CFG, "SIMULATION", quotes)
    pos = st.open_positions(c, "SIMULATION")
    check("pair slot buys the fund's leg", 3 in pos and pos[3]["symbol"] == "SPY"
          and abs(pos[3]["quantity"] * 700.0 - 20.0) < 1e-6, (r, pos))
    check("with the ATR stop recorded", pos[3]["stop_plan"] and pos[3]["atr"] == 8.0, pos.get(3))

    r = st.trade(c, CFG, "SIMULATION", qt.FixedQuotes({"SPY": 700.0, "SH": 32.0}, conn=c))
    check("no switch: holds, buys nothing more", not [x for x in r if x["action"] in ("BUY", "CLOSE")], r)

    leg["v"] = {"leg": "SH", "held": "SPY", "bull": "SPY", "bear": "SH", "switching": True}
    r = st.trade(c, CFG, "SIMULATION", qt.FixedQuotes({"SPY": 690.0, "SH": 32.5}, conn=c))
    closes = [x for x in r if x["action"] == "CLOSE"]
    check("fund switches: the slot sells the old leg", closes and closes[0]["symbol"] == "SPY"
          and closes[0]["reason"] == "strategy exit signal" and closes[0]["status"] == "filled", r)
    pos = st.open_positions(c, "SIMULATION")
    check("and buys the new leg in the same pass", 3 in pos and pos[3]["symbol"] == "SH", (r, pos))
    sold = c.execute("SELECT quantity FROM slot_trades WHERE action='CLOSE' AND symbol='SPY'").fetchone()
    check("the sale is the slot's own shares", sold and abs(sold[0] - 20.0 / 700.0) < 1e-9, sold)

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
