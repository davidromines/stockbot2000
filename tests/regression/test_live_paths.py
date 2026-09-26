"""
Regression tests for five live-trading paths that are coded but were untested
(Addendum D N2): stale quote, quote outside market hours, partial fill recorded
at the filled quantity, rejected buy writes no OPEN, and a failed stop sell
keeps the position.

These paths decide whether real money moves, so each is pinned to the exact
behaviour the modules document. No network and no real database: the Robinhood
transport is a fake callable and the store is an in-memory SQLite database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import broker as bk
import robinhood_live as rl
import slot_trader as st

FAILED = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if detail and not cond else ""))
    if not cond:
        FAILED.append(name)


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def quote_response(symbol, price, age_seconds):
    ts = (datetime.now(timezone.utc) - timedelta(seconds=age_seconds)).isoformat()
    return {"data": {"results": [{"quote": {"symbol": symbol, "last_trade_price": str(price),
                                            "venue_last_trade_time": ts}}]}}


def with_quote_env(fn):
    """Run fn with market_open and _db_fields patched; always restore them."""
    orig_open, orig_fields = rl.qt.market_open, rl.qt._db_fields
    try:
        rl.qt._db_fields = lambda *a, **kw: {"dollar_volume_20": 5e7, "market_cap": 5e9}
        return fn()
    finally:
        rl.qt.market_open, rl.qt._db_fields = orig_open, orig_fields


def test_quotes():
    def stale():
        rl.qt.market_open = lambda *a, **kw: True
        q = rl.RobinhoodQuotes(conn(), call=lambda n, a: quote_response("AAA", 50.0, 600)).get("AAA")
        check("stale quote (10 min old) refused", q is None, str(q))

    def fresh():
        rl.qt.market_open = lambda *a, **kw: True
        q = rl.RobinhoodQuotes(conn(), call=lambda n, a: quote_response("AAA", 50.0, 30)).get("AAA")
        check("fresh quote (30 s old) accepted", q is not None and q["price"] == 50.0, str(q))

    def closed():
        rl.qt.market_open = lambda *a, **kw: False
        q = rl.RobinhoodQuotes(conn(), call=lambda n, a: quote_response("AAA", 50.0, 5)).get("AAA")
        check("quote outside market hours refused", q is None, str(q))

    with_quote_env(stale)
    with_quote_env(fresh)
    with_quote_env(closed)


def order(signal_id, symbol, side, notional=None, quantity=None, filled=0.0, price=None):
    o = bk.Order(signal_id=signal_id, symbol=symbol, side=side, notional=notional, quantity=quantity)
    o.filled_quantity, o.avg_fill_price = filled, price
    return o


def test_record_trade():
    c = conn()
    st.init(c)
    holder = {"strategy_key": "rising200", "version": 1}

    partial = {"status": "partially_filled", "signal_id": "s1",
               "order": order("s1", "AAA", "BUY", notional=20, filled=0.25, price=40.0)}
    wrote = st._record_trade(c, "SIMULATION", 1, holder, "AAA", "OPEN", partial, "entry")
    rows = c.execute("SELECT quantity, price FROM slot_trades").fetchall()
    check("partial fill writes one OPEN row", wrote and len(rows) == 1, str([tuple(r) for r in rows]))
    check("partial fill recorded at the filled quantity",
          len(rows) == 1 and abs(rows[0]["quantity"] - 0.25) < 1e-9 and abs(rows[0]["price"] - 40.0) < 1e-9,
          str([tuple(r) for r in rows]))
    pos = st.open_positions(c, "SIMULATION")
    check("open_positions shows the partial quantity",
          pos.get(1, {}).get("quantity") == 0.25, str(pos))

    rejected = {"status": "rejected", "signal_id": "s2",
                "order": order("s2", "BBB", "BUY", notional=20, filled=0.0, price=None)}
    wrote = st._record_trade(c, "SIMULATION", 2, holder, "BBB", "OPEN", rejected, "entry")
    n = c.execute("SELECT COUNT(*) FROM slot_trades").fetchone()[0]
    check("rejected buy writes no OPEN row", wrote is False and n == 1, f"wrote={wrote} rows={n}")
    check("rejected buy leaves open_positions unchanged",
          set(st.open_positions(c, "SIMULATION")) == {1}, str(st.open_positions(c, "SIMULATION")))


class FakeEngine:
    session = "2026-09-25"

    def __init__(self, status, filled, price):
        self.status, self.filled, self.price = status, filled, price

    def execute(self, sig, reconciled=None):
        o = order(sig.signal_id, sig.symbol, "SELL", quantity=sig.quantity,
                  filled=self.filled, price=self.price)
        return {"status": self.status, "signal_id": sig.signal_id, "order": o, "reasons": []}


def test_failed_stop_sell():
    c = conn()
    st.init(c)
    holder = {"strategy_key": "rising200", "version": 1}
    opened = {"status": "filled", "signal_id": "s1",
              "order": order("s1", "AAA", "BUY", notional=20, filled=0.5, price=40.0)}
    st._record_trade(c, "SIMULATION", 1, holder, "AAA", "OPEN", opened, "entry")
    pos = st.open_positions(c, "SIMULATION")[1]

    results = []
    st._exit(c, FakeEngine("failed", 0.0, None), "SIMULATION", 1, pos, "stop breached", True, results)
    still = st.open_positions(c, "SIMULATION")
    check("failed stop sell keeps the position open",
          still.get(1, {}).get("quantity") == 0.5, str(still))
    check("failed stop sell appends a failed result",
          len(results) == 1 and results[0]["status"] == "failed", str(results))

    st._exit(c, FakeEngine("filled", 0.5, 39.0), "SIMULATION", 1, pos, "stop breached", True, results)
    check("filled stop sell closes the position",
          st.open_positions(c, "SIMULATION") == {}, str(st.open_positions(c, "SIMULATION")))
    check("filled stop sell appends a filled result",
          len(results) == 2 and results[1]["status"] == "filled", str(results))


def main():
    test_quotes()
    test_record_trade()
    test_failed_stop_sell()
    if FAILED:
        print(f"\n{len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
