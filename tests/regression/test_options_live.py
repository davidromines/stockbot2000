"""
options_live.py (R7): real option orders mirror PROVEN paper option trades, and nothing is
placed unless every gate holds. A fake Robinhood; in-memory database; no network.

Gates checked: allow_options off, no options level, kill switch, market closed, not proven;
then entries (whole contracts within per_trade_usd, review before place, ref_id fixed),
exits when the paper trade closes, reconcile mismatch halts, an UNKNOWN order blocks entries.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import datetime as dt
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import killswitch
import options_live as ol
import quotes
import risk_engine

FAILED = []
NOW = dt.datetime(2026, 10, 5, 15, 0, tzinfo=dt.timezone.utc)
ACCT = "403446024"


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


class FakeRH:
    def __init__(self, level="option_level_2"):
        self.level, self.calls, self.positions = level, [], {}

    def __call__(self, name, args):
        self.calls.append((name, args))
        if name == "get_accounts":
            return {"accounts": [{"account_number": ACCT, "option_level": self.level}]}
        if name == "get_option_instruments":
            return {"instruments": [{"id": f"oid-{args['type']}-{args['strike_price']}"}]}
        if name == "get_option_quotes":
            return {"quotes": [{"bid_price": "1.18", "ask_price": "1.22"}]}
        if name == "review_option_order":
            return {"ok": True}
        if name == "place_option_order":
            return {"id": f"bo-{len(self.calls)}", "state": "filled"}
        if name == "get_option_orders":
            return {"orders": [{"state": "filled", "processed_quantity": "4", "average_price": "1.22"}]}
        if name == "get_option_positions":
            return {"positions": [{"option_id": k, "quantity": str(v)} for k, v in self.positions.items()]}
        return {}


def db(paper_trades=25, net=50.0):
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE option_trades (id INTEGER PRIMARY KEY, mode TEXT, strategy TEXT, symbol TEXT, legs TEXT, "
              "opened TEXT, closed TEXT, cost REAL, value REAL, ret REAL, usd REAL, reason TEXT, signal TEXT)")
    for i in range(paper_trades):
        c.execute("INSERT INTO option_trades (mode, strategy, symbol, legs, opened, closed, ret, usd) VALUES "
                  "('PAPER','opt_x','OLD','[]','2026-09-01','2026-09-10',0.1,?)", (net / paper_trades,))
    legs = [{"exp": "2026-11-20", "strike": 100.0, "cp": "C", "ask": 1.2}]
    c.execute("INSERT INTO option_trades (mode, strategy, symbol, legs, opened) VALUES "
              "('PAPER','opt_x','AAA',?,'2026-10-05')", (json.dumps(legs),))
    c.commit()
    return c


def main():
    cfg = {"options": {"live": {"per_trade_usd": 500}}}  # 4 contracts x $122 at the fake ask below
    armed = {"allow_options": True}
    risk_engine.load_limits = lambda *a, **k: armed
    killswitch.global_engaged = lambda: None
    quotes.market_open = lambda *a, **k: True
    killswitch.record_event = lambda *a, **k: None
    import notify
    notify.notify = lambda *a, **k: None

    armed["allow_options"] = False
    r = ol.run(db(), cfg, FakeRH(), ACCT, NOW)
    check("allow_options off: nothing placed", "allow_options" in (r["halt"] or "") and r["entries"] == 0, r)
    armed["allow_options"] = True
    r = ol.run(db(), cfg, FakeRH(level=""), ACCT, NOW)
    check("no options level: nothing placed", "options access" in (r["halt"] or ""), r)
    killswitch.global_engaged = lambda: "test"
    r = ol.run(db(), cfg, FakeRH(), ACCT, NOW)
    check("kill switch: nothing placed", "kill switch" in (r["halt"] or ""), r)
    killswitch.global_engaged = lambda: None
    quotes.market_open = lambda *a, **k: False
    check("market closed: nothing placed", "market closed" in (ol.run(db(), cfg, FakeRH(), ACCT, NOW)["halt"] or ""))
    quotes.market_open = lambda *a, **k: True
    r = ol.run(db(paper_trades=5), cfg, FakeRH(), ACCT, NOW)
    check("not proven on paper (5 trades): no entry", r["entries"] == 0 and r["skipped"], r)
    r = ol.run(db(net=-10.0), cfg, FakeRH(), ACCT, NOW)
    check("losing paper record: no entry", r["entries"] == 0, r)

    c, rh = db(), FakeRH()
    r = ol.run(c, cfg, rh, ACCT, NOW)
    check("proven: the paper trade is mirrored", r["entries"] == 1, r)
    o = c.execute("SELECT quantity, limit_price, ref_id, side, purpose FROM option_live_orders").fetchone()
    check("whole contracts within $500 at the live ask (4 x $122)", o[0] == 4 and abs(o[1] - 1.22) < 1e-9, o)
    names = [n for n, _ in rh.calls]
    check("review before place", names.index("review_option_order") < names.index("place_option_order"))
    placed = [a for n, a in rh.calls if n == "place_option_order"][0]
    check("the order carries the ledger's fixed ref_id", placed["ref_id"] == o[2] and o[2] != "pending")
    check("a second run does not buy the same trade again", ol.run(c, cfg, rh, ACCT, NOW)["entries"] == 0)

    rh.positions = {"oid-call-100.0000": 4}
    c.execute("UPDATE option_live_orders SET filled_qty=4, avg_price=1.22, state='FILLED'")
    c.execute("UPDATE option_trades SET closed='2026-10-12' WHERE symbol='AAA'")
    c.commit()
    r = ol.run(c, cfg, rh, ACCT, NOW + dt.timedelta(days=7))
    sell = c.execute("SELECT side, quantity, limit_price FROM option_live_orders WHERE side='sell'").fetchone()
    check("paper trade closed: contracts sold at the bid", r["exits"] == 1 and sell[1] == 4 and abs(sell[2] - 1.18) < 1e-9,
          (r, sell))

    c2, rh2 = db(), FakeRH()
    rh2.positions = {"someone-else": 1}
    r = ol.run(c2, cfg, rh2, ACCT, NOW)
    check("broker positions differ from the ledger: halt", "ledger vs broker" in (r["halt"] or "") and r["entries"] == 0, r)

    c3 = db()
    ol.init(c3)
    c3.execute("INSERT INTO option_live_orders (trade_id, strategy, symbol, exp, strike, cp, purpose, side, quantity, "
               "ref_id, state, created_at, updated_at) VALUES (9,'opt_x','ZZZ','2026-11-20',1,'C','open','buy',1,'r',"
               "'UNKNOWN','t','t')")
    c3.commit()
    r = ol.run(c3, cfg, FakeRH(), ACCT, NOW)
    check("an order with an unknown outcome blocks new entries", r["entries"] == 0 and "unknown" in (r["halt"] or ""), r)
    check("tick: buys round up, sells down, nickels from $3", ol.tick(1.221, True) == 1.23 and
          ol.tick(3.07, False) == 3.05)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
