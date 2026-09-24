"""
Regression test: the Value Fund can hold a slot (owner's option C, 2026-09-24).

Pinned:
  - value_fund.ranked_holdings() orders current holdings by score_at_entry
    (highest first, unscored last, ties by ticker); no table -> []
  - a value holder gets a VALID stop plan (ATR price stop from
    slots.value_risk plus "sell when the fund sells it")
  - slot_trader buys the fund's top holding, or the next when another slot
    already holds the top one
  - when the fund drops the stock, the slot sells its own shares
  - ranking sizes a value trade at the fund's capital / holdings, not $20

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import quotes as qt
import ranking
import slot_trader as st
import slots
import stop_plans
import value_fund

FAILED = []
CFG = {"costs": {}}
FUND = value_fund.FUND
KEY = f"value:{FUND}"


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def hold(c, ticker, score):
    c.execute("INSERT INTO value_fund_positions (name,ticker,opened_on,entry_price,shares,thesis,score_at_entry) "
              "VALUES (?,?,'2026-07-01',10,1,'t',?)", (FUND, ticker, score))


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    for d in ("2026-09-22", "2026-09-23"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
    for t in ("AAA", "BBB", "CCC"):
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', 2.0, 5e9)", (t,))
        c.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', 5e10)", (t,))
    value_fund.init(c)
    st.init(c)
    return c


def assign(c, slot, key):
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
              "reason) VALUES ('2026-09-23T00:00:00', ?, 'ASSIGN', ?, 1, 20.0, 'SIMULATION', 't')", (slot, key))


def main():
    c = sqlite3.connect(":memory:")
    check("no value tables -> no holdings", value_fund.ranked_holdings(c, FUND) == [])

    c = db()
    hold(c, "CCC", None)
    hold(c, "BBB", 0.9)
    hold(c, "AAA", 0.4)
    check("holdings ranked by score at entry, unscored last",
          value_fund.ranked_holdings(c, FUND) == ["BBB", "AAA", "CCC"], value_fund.ranked_holdings(c, FUND))

    g = slots.genome_for(None, KEY, 1)
    plan = stop_plans.from_genome(g)
    ok, why = stop_plans.validate(plan)
    check("value slot has a valid stop plan (price stop + fund exit)", ok and g.get("value") == FUND and
          {r["type"] for r in plan} == {"atr", "strategy"}, (plan, why))

    # Two value slots: the first takes the top name, the second the next one.
    assign(c, 1, KEY)
    assign(c, 2, KEY)
    c.commit()
    px = {"AAA": 40.0, "BBB": 50.0, "CCC": 25.0}
    r = st.trade(c, CFG, "SIMULATION", qt.FixedQuotes(px, conn=c))
    pos = st.open_positions(c, "SIMULATION")
    syms = {s: p["symbol"] for s, p in pos.items()}
    check("slot buys the fund's top holding", syms.get(1) == "BBB"
          and abs(pos[1]["quantity"] * 50.0 - 20.0) < 1e-6, (r, syms))
    check("a second slot takes the next holding, not a duplicate", syms.get(2) == "AAA", syms)
    check("with the ATR stop recorded", pos[1]["stop_plan"] and pos[1]["atr"] == 2.0, pos.get(1))

    r = st.trade(c, CFG, "SIMULATION", qt.FixedQuotes(px, conn=c))
    check("fund unchanged: holds, trades nothing", not [x for x in r if x["action"] in ("BUY", "CLOSE")], r)

    # The fund sells BBB at a review.
    c.execute("DELETE FROM value_fund_positions WHERE ticker='BBB'")
    c.commit()
    r = st.trade(c, CFG, "SIMULATION", qt.FixedQuotes({**px, "BBB": 52.0}, conn=c))
    closes = [x for x in r if x["action"] == "CLOSE"]
    check("fund sells the stock: the slot sells it", closes and closes[0]["symbol"] == "BBB"
          and closes[0]["reason"] == "strategy exit signal" and closes[0]["status"] == "filled", r)
    sold = c.execute("SELECT quantity FROM slot_trades WHERE action='CLOSE' AND symbol='BBB'").fetchone()
    check("the sale is the slot's own shares", sold and abs(sold[0] - 20.0 / 50.0) < 1e-9, sold)
    pos = st.open_positions(c, "SIMULATION")
    check("the other value slot keeps its stock", pos.get(2, {}).get("symbol") == "AAA", pos)
    check("the freed slot re-buys the next holding not already held", pos.get(1, {}).get("symbol") == "CCC",
          {s: p["symbol"] for s, p in pos.items()})

    # Ranking: a value trade is sized at capital / holdings.
    fw, n = ranking.forward_per_trade({"net_usd": 4.0, "capital_usd": 100.0, "fund_kind": "value",
                                       "closed_trades": 0, "open_positions": 10, "position_usd": 10.0})
    check("value forward return per trade uses the fund's own position size",
          n == 10 and abs(fw - 0.04) < 1e-12, (fw, n))

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
