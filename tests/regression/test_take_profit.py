"""
Regression test: the live slot trades the take-profit the strategy was tested
with (2026-09-24).

The backtest (simulator.py) and the paper engine (paper_trading.py) both sell
when price reaches entry x (1 + take_profit_pct). stop_plans.from_genome
dropped the gene, so a live slot held through every target the tested
strategy would have sold at.

Pinned:
  - from_genome carries take_profit_pct as a take_profit rule; validate()
    accepts it, bounds it, and never counts it as a price stop
  - check(): stop first, then take-profit, then time, then strategy exit
  - a live slot sells at the target through the real ExecutionEngine
  - a position recorded BEFORE the fix (stored plan without the rule) gets
    the target from its own strategy version's genome
  - a genome with no take_profit_pct is unchanged: no profit exit

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import paper_trading as pt
import quotes as qt
import slot_trader as st
import slots
import stop_plans as sp

FAILED = []
TP = {"entry": {"op": "gt"}, "exit": {"op": "lt"},
      "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20, "take_profit_pct": 10.0}}
NO_TP = {"entry": {"op": "gt"}, "exit": {"op": "lt"},
         "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20, "take_profit_pct": None}}


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def fixture():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    for d in ("2026-09-22", "2026-09-23"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
    c.execute("INSERT INTO features VALUES ('AAA', '2026-09-23', 2.0, 5e7)")
    c.execute("INSERT INTO fundamentals VALUES ('AAA', '2026-01-01', 5e9)")
    st.init(c)
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, "
              "mode, reason) VALUES ('2026-09-23T00:00:00', 1, 'ASSIGN', 'fx_test', 1, 20.0, 'SIMULATION', 't')")
    c.commit()
    return c


def main():
    plan = sp.from_genome(TP)
    check("from_genome carries take_profit_pct", {"type": "take_profit", "pct": 10.0} in plan, plan)
    check("plan with it validates", sp.validate(plan)[0], sp.validate(plan))
    check("take-profit alone is not a valid plan (bounds no loss)",
          not sp.validate([{"type": "take_profit", "pct": 10.0}])[0])
    check("out-of-range target rejected, not clamped",
          not sp.validate([{"type": "atr", "atr_multiple": 2}, {"type": "take_profit", "pct": 0.1}])[0])
    check("no gene -> no rule", not [r for r in sp.from_genome(NO_TP) if r["type"] == "take_profit"])

    pos = {"entry_price": 50.0, "atr": 2.0}
    v = sp.check(plan, pos, 55.01, 1)          # 50 x 1.10 is 55.000000000000007 in floats, as in paper_trading
    check("at the target: exit, kind take_profit", v["exit"] and v["kind"] == "take_profit", v)
    check("below the target: hold", not sp.check(plan, pos, 54.9, 1)["exit"])
    check("stop outranks target", sp.check(plan, pos, 45.0, 1)["kind"] == "stop")
    check("target outranks time exit", sp.check(plan, pos, 56.0, 25)["kind"] == "take_profit")

    # Live path: buy, then the target.
    slots.genome_for = lambda conn, k, v: TP
    pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": ["AAA"]}), set())
    c = fixture()
    st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0}, conn=c))
    p = st.open_positions(c, "SIMULATION")
    check("entry stores the take-profit in its plan",
          any(r["type"] == "take_profit" for r in p[1]["stop_plan"]), p.get(1))
    r = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 54.0}, conn=c))
    check("+8%: holds", not [x for x in r if x["action"] == "CLOSE"], r)
    r = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 55.5}, conn=c))
    closes = [x for x in r if x["action"] == "CLOSE"]
    check("+11%: sells for the profit", closes and closes[0]["status"] == "filled"
          and closes[0]["reason"].startswith("take profit"), r)

    # A position recorded before the fix: stored plan has no take-profit.
    c = fixture()
    st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0}, conn=c))
    old = [r for r in sp.from_genome(TP) if r["type"] != "take_profit"]
    c.execute("UPDATE slot_trades SET stop_plan=? WHERE action='OPEN'", (json.dumps(old),))
    c.commit()
    check("fixture: stored plan lacks the target",
          not any(r["type"] == "take_profit" for r in st.open_positions(c, "SIMULATION")[1]["stop_plan"]))
    r = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 56.0}, conn=c))
    check("older position still sells at its strategy's target",
          [x for x in r if x["action"] == "CLOSE" and x["reason"].startswith("take profit")], r)

    # No gene: no profit exit.
    slots.genome_for = lambda conn, k, v: NO_TP
    c = fixture()
    st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0}, conn=c))
    r = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 80.0}, conn=c))
    check("strategy without a target: +60% still holds", not [x for x in r if x["action"] == "CLOSE"], r)

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
