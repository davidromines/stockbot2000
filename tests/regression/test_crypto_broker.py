"""Regression: CryptoBroker routes crypto orders through the broker interface.

No network: the crypto client is a fake and the equity transport is a fake
callable. The database is in-memory with a handful of daily bars.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import broker as bk
import crypto_broker as cb
import crypto_data

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILED.append(name)
        print(f"  FAIL  {name}  {detail}")


class FakeClient:
    def __init__(self, quote=None, buy=None, sell=None, positions=None,
                 stop=None, cancel=True, orders=None, raise_on=None):
        self._quote, self._buy, self._sell = quote, buy, sell
        self._positions, self._stop, self._cancel = positions or {}, stop, cancel
        self._orders, self._raise = orders or [], raise_on
        self.calls = []

    def quote(self, symbol):
        self.calls.append(("quote", symbol))
        return self._quote

    def positions(self):
        return self._positions

    def buy(self, symbol, usd, client_order_id):
        self.calls.append(("buy", symbol, usd, client_order_id))
        if self._raise:
            raise self._raise
        return self._buy

    def sell(self, symbol, qty, client_order_id):
        self.calls.append(("sell", symbol, qty, client_order_id))
        if self._raise:
            raise self._raise
        return self._sell

    def place_stop(self, symbol, qty, stop_price, client_order_id):
        self.calls.append(("stop", symbol, qty, stop_price, client_order_id))
        return self._stop

    def cancel(self, order_id):
        self.calls.append(("cancel", order_id))
        return self._cancel

    def open_orders(self, symbol=None):
        return self._orders

    def _call(self, tool, args):
        return {"data": {"results": [{"id": args.get("order_id"), "state": "filled",
                                      "cumulative_quantity": "0.5",
                                      "average_price": "101.25"}]}}


def make_broker(client, bars=25):
    conn = sqlite3.connect(":memory:")
    crypto_data.init(conn)
    for i in range(bars):
        conn.execute("INSERT INTO crypto_prices (symbol, open_time, interval, bar_seconds,"
                     " close, volume) VALUES ('BTC-USD', ?, '1d', 86400, 100.0, 10.0)", (i * 86400,))
    conn.commit()
    def call(tool, args=None):
        # The broker's own transport; only get_crypto_orders is expected here.
        if tool == "get_crypto_orders" and args and args.get("rhs_account_number") == "ACCT":
            return client._call(tool, args)
        return {}
    return cb.CryptoBroker(conn, "ACCT", call=call, client=client), conn


def order(side="BUY", asset_type="crypto", **kw):
    o = bk.Order(signal_id=f"s-{side}-{asset_type}", symbol="BTC-USD", side=side,
                 asset_type=asset_type, **kw)
    o.to(bk.VALIDATING)
    o.to(bk.APPROVED)
    return o


QUOTE = {"symbol": "BTC-USD", "bid": 99.0, "ask": 101.0, "mark": 100.0, "price": 100.0,
         "updated_at": "2026-09-25T18:00:00+00:00", "age_s": 1.0}

# 1. an equity order is refused before the client is touched
client = FakeClient(quote=QUOTE, buy={"state": bk.FILLED, "order_id": "x",
                                      "filled_qty": 1.0, "avg_price": 100.0})
broker, conn = make_broker(client)
o = order(asset_type="equity", notional=20.0)
broker.place_order(o)
check("equity order REJECTED", o.state == bk.REJECTED, o.state)
check("equity order never reached the client", not client.calls, client.calls)

# 2. a BUY fills, carrying the client's id, quantity and price
client = FakeClient(quote=QUOTE, buy={"state": bk.FILLED, "order_id": "rh-1",
                                      "filled_qty": 0.2, "avg_price": 100.5})
broker, conn = make_broker(client)
o = order(notional=20.0)
broker.place_order(o)
check("buy ends FILLED", o.state == bk.FILLED, o.state)
check("buy carries broker_order_id", o.broker_order_id == "rh-1", o.broker_order_id)
check("buy carries filled_quantity", o.filled_quantity == 0.2, o.filled_quantity)
check("buy carries avg_fill_price", o.avg_fill_price == 100.5, o.avg_fill_price)
check("buy passed the notional through", ("buy", "BTC-USD", 20.0, o.client_order_id) in client.calls,
      client.calls)

# 3. a client REJECTED result ends REJECTED with its reason
client = FakeClient(quote=QUOTE, buy={"state": bk.REJECTED, "reason": "below minimum"})
broker, conn = make_broker(client)
o = order(notional=20.0)
broker.place_order(o)
check("client rejection ends REJECTED", o.state == bk.REJECTED, o.state)
check("client rejection keeps the reason", "below minimum" in o.note, o.note)

# 4. a client UNKNOWN result ends UNKNOWN, not SUBMITTED
client = FakeClient(quote=QUOTE, buy={"state": bk.UNKNOWN, "order_id": None,
                                      "filled_qty": None, "avg_price": None})
broker, conn = make_broker(client)
o = order(notional=20.0)
broker.place_order(o)
check("client UNKNOWN ends UNKNOWN", o.state == bk.UNKNOWN, o.state)

# 5. a transport failure after sending is UNKNOWN, never FILLED
client = FakeClient(quote=QUOTE, raise_on=RuntimeError("socket closed"))
broker, conn = make_broker(client)
o = order(notional=20.0)
broker.place_order(o)
check("transport failure ends UNKNOWN", o.state == bk.UNKNOWN, o.state)
check("transport failure is not a fill", o.filled_quantity == 0.0, o.filled_quantity)

# 5b. a Robinhood error from the client may come after the order was sent (it polls): UNKNOWN
client = FakeClient(quote=QUOTE, raise_on=cb.rl.rh.RobinhoodError("poll failed"))
broker, conn = make_broker(client)
o = order(notional=20.0)
broker.place_order(o)
check("Robinhood error after sending ends UNKNOWN, not REJECTED", o.state == bk.UNKNOWN, o.state)

# 6. a SELL needs a quantity and delegates
client = FakeClient(quote=QUOTE, sell={"state": bk.FILLED, "order_id": "rh-2",
                                       "filled_qty": 0.1, "avg_price": 99.0})
broker, conn = make_broker(client)
o = order(side="SELL", quantity=0.1)
broker.place_order(o)
check("sell ends FILLED", o.state == bk.FILLED, o.state)
check("sell passed the quantity through", ("sell", "BTC-USD", 0.1, o.client_order_id) in client.calls,
      client.calls)

# 7. the quote carries liquidity from the bars, and is None when the client has none
client = FakeClient(quote=QUOTE)
broker, conn = make_broker(client)
q = broker.get_quote("BTC-USD")
check("quote carries dollar_volume_20", q and q["dollar_volume_20"] == 1000.0, q)
check("quote is tagged robinhood_crypto", q and q["source"] == "robinhood_crypto", q)
broker, conn = make_broker(FakeClient(quote=None))
check("no client quote means no quote", broker.get_quote("BTC-USD") is None)

# 8. too few bars means unknown liquidity, not a guessed one
broker, conn = make_broker(FakeClient(quote=QUOTE), bars=3)
check("thin history has no liquidity", broker.get_quote("BTC-USD")["dollar_volume_20"] is None)

# 9. positions are valued at the quote price
broker, conn = make_broker(FakeClient(quote=QUOTE, positions={"BTC-USD": 0.5}))
pos = broker.get_positions()
check("position valued at the quote", pos["BTC-USD"]["value"] == 50.0, pos)
check("position entry is not invented", pos["BTC-USD"]["entry"] == 0.0, pos)

# 10. stops delegate, and open_stops filters to stop_loss
client = FakeClient(quote=QUOTE, stop={"state": bk.SUBMITTED, "order_id": "st-1"},
                    orders=[{"order_id": "st-1", "symbol": "BTC-USD", "side": "sell",
                             "type": "stop_loss", "state": bk.SUBMITTED},
                            {"order_id": "l-1", "symbol": "BTC-USD", "side": "buy",
                             "type": "limit", "state": bk.SUBMITTED}])
broker, conn = make_broker(client)
res = broker.place_stop("BTC-USD", 0.1, 90.0, "co-1")
check("place_stop delegates", res == {"state": bk.SUBMITTED, "order_id": "st-1"}, res)
check("open_stops keeps only stops", [s["order_id"] for s in broker.open_stops()] == ["st-1"],
      broker.open_stops())

# 11. get_order maps the raw record
broker, conn = make_broker(FakeClient(quote=QUOTE))
rec = broker.get_order("rh-9")
check("get_order maps state", rec and rec["state"] == bk.FILLED, rec)
check("get_order maps the fill", rec and rec["filled_quantity"] == 0.5 and rec["avg_fill_price"] == 101.25, rec)

# 12. cancel delegates
client = FakeClient(quote=QUOTE, cancel=True)
broker, conn = make_broker(client)
check("cancel delegates", broker.cancel_order("rh-9") is True)
check("cancel reached the client", ("cancel", "rh-9") in client.calls, client.calls)

if FAILED:
    print(f"\n{len(FAILED)} FAILED: {', '.join(FAILED)}")
    sys.exit(1)
print("\nALL PASS")
