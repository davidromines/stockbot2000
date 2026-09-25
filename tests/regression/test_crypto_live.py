"""Regression tests for crypto_live.CryptoLive. No network, no real orders."""
import runtime  # noqa: F401

import os
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import broker as bk
import crypto_live
import robinhood_live as rl

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


NOW = datetime(2026, 9, 25, 12, 0, 0, tzinfo=timezone.utc)


class Fake:
    """Records every (tool, args) and returns canned responses."""

    def __init__(self, responses):
        self.responses = responses
        self.calls = []

    def __call__(self, tool, args):
        self.calls.append((tool, dict(args)))
        resp = self.responses.get(tool)
        if callable(resp):
            return resp(args, self.calls)
        if resp is None:
            raise AssertionError("unexpected tool %s" % tool)
        return resp

    def args_for(self, tool):
        return [a for t, a in self.calls if t == tool]


def client(responses, **kw):
    kw.setdefault("now", lambda: NOW)
    kw.setdefault("sleep", lambda s: None)
    return crypto_live.CryptoLive("123456", call=Fake(responses), **kw)


def quote_resp(updated):
    return {"data": {"results": [{
        "symbol": "BTCUSD", "bid_price": "83401.74", "ask_price": "84983.68",
        "mark_price": "84192.71", "updated_at": updated}]}}


def test_quote():
    fresh = (NOW - timedelta(seconds=5)).isoformat()
    c = client({"get_crypto_quotes": quote_resp(fresh)})
    q = c.quote("BTC-USD")
    check("quote maps BTCUSD to BTC-USD", q and q["symbol"] == "BTC-USD", repr(q))
    check("quote price is mark", q and abs(q["price"] - 84192.71) < 1e-6, repr(q))
    check("quote age is measured", q and abs(q["age_s"] - 5.0) < 1e-6, repr(q))

    stale = (NOW - timedelta(seconds=600)).isoformat()
    c2 = client({"get_crypto_quotes": quote_resp(stale)})
    check("stale quote returns None", c2.quote("BTC-USD") is None)

    c3 = client({"get_crypto_quotes": {"data": {"results": []}}})
    check("absent symbol returns None", c3.quote("BTC-USD") is None)


def test_increments_and_round_qty():
    pairs = {"results": [{
        "symbol": "BTC-USD", "min_order_size": "0.000001",
        "min_order_quantity_increment": "0.00000001", "tradability": "tradable"}]}
    c = client({"get_currency_pairs": pairs})
    check("round_qty rounds down",
          c.round_qty("BTC-USD", "0.123456789") == "0.12345678",
          repr(c.round_qty("BTC-USD", "0.123456789")))
    check("round_qty below min_qty returns None",
          c.round_qty("BTC-USD", "0.0000001") is None)
    check("round_qty unknown pair returns None",
          c.round_qty("ETH-USD", "1.0") is None)
    check("increments cached after first call",
          len([t for t, _ in c._call.calls if t == "get_currency_pairs"]) == 1)


def test_buy_polls_to_filled():
    def orders(args, calls):
        n = len([t for t, _ in calls if t == "get_crypto_orders"])
        state = "queued" if n == 1 else "filled"
        return {"data": {"results": [{
            "id": "ord-1", "state": state, "cumulative_quantity": "0.0002",
            "average_price": "84000.00", "side": "buy", "type": "market"}]}}

    c = client({"place_crypto_order": {"id": "ord-1", "state": "queued"},
                "get_crypto_orders": orders})
    res = c.buy("BTC-USD", 20, "coid-1")
    args = c._call.args_for("place_crypto_order")[0]
    check("buy sends dollar_amount 20.00", args.get("dollar_amount") == "20.00", repr(args))
    check("buy sends type market", args.get("type") == "market", repr(args))
    check("buy sends ref_id of client id",
          args.get("ref_id") == rl.ref_id("coid-1"), repr(args))
    check("buy returns FILLED", res["state"] == bk.FILLED, repr(res))
    check("buy returns filled_qty and avg_price",
          res["filled_qty"] == 0.0002 and res["avg_price"] == 84000.0, repr(res))


def test_buy_without_order_id():
    c = client({"place_crypto_order": {"state": "queued"}})
    res = c.buy("BTC-USD", 20, "coid-2")
    check("placement without order id returns UNKNOWN",
          res["state"] == crypto_live.UNKNOWN, repr(res))
    check("placement without order id does not poll",
          not c._call.args_for("get_crypto_orders"))


def test_sell_below_min():
    pairs = {"results": [{
        "symbol": "BTC-USD", "min_order_size": "0.000001",
        "min_order_quantity_increment": "0.00000001", "tradability": "tradable"}]}
    c = client({"get_currency_pairs": pairs})
    res = c.sell("BTC-USD", "0.0000001", "coid-3")
    check("sell below min_qty is REJECTED", res["state"] == bk.REJECTED, repr(res))
    check("sell below min_qty places nothing",
          not c._call.args_for("place_crypto_order"))


def test_place_stop():
    pairs = {"results": [{
        "symbol": "BTC-USD", "min_order_size": "0.000001",
        "min_order_quantity_increment": "0.00000001", "tradability": "tradable"}]}
    c = client({"get_currency_pairs": pairs,
                "place_crypto_order": {"id": "ord-9", "state": "queued"}})
    res = c.place_stop("BTC-USD", "0.0002", 80000.0, "coid-4")
    args = c._call.args_for("place_crypto_order")[0]
    check("place_stop sends type stop_loss", args.get("type") == "stop_loss", repr(args))
    check("place_stop sends gtc", args.get("time_in_force") == "gtc", repr(args))
    check("place_stop does not poll",
          not c._call.args_for("get_crypto_orders"))
    check("place_stop maps queued to SUBMITTED", res["state"] == bk.SUBMITTED, repr(res))


def test_positions_pages():
    def positions(args, calls):
        if args.get("cursor") == "page2":
            return {"data": {"results": [
                {"currency": {"code": "ETH"}, "quantity": "1.5",
                 "quantity_transferable": "1.5"}], "next": None}}
        return {"data": {"results": [
            {"currency": {"code": "BTC"}, "quantity": "0.0002",
             "quantity_transferable": "0.0002"},
            {"currency": {"code": "DOGE"}, "quantity": "0",
             "quantity_transferable": "0"}], "next": "page2"}}

    c = client({"get_crypto_positions": positions})
    pos = c.positions()
    check("positions follows next cursor",
          pos == {"BTC-USD": 0.0002, "ETH-USD": 1.5}, repr(pos))
    check("positions skips zero quantity", "DOGE-USD" not in pos, repr(pos))


def test_open_orders_filter():
    resp = {"data": {"results": [
        {"id": "o1", "symbol": "BTCUSD", "side": "buy", "type": "market",
         "state": "queued"},
        {"id": "o2", "symbol": "ETHUSD", "side": "sell", "type": "stop_loss",
         "state": "confirmed"}]}}
    c = client({"get_crypto_orders": resp})
    all_orders = c.open_orders()
    check("open_orders returns all when unfiltered", len(all_orders) == 2, repr(all_orders))
    btc = c.open_orders("BTC-USD")
    check("open_orders filters by symbol",
          len(btc) == 1 and btc[0]["order_id"] == "o1", repr(btc))
    check("open_orders maps state", btc[0]["state"] == bk.SUBMITTED, repr(btc))


def test_poll_is_bounded():
    # A clock that never advances and an order that never fills must still end.
    c = client({"place_crypto_order": {"id": "o9", "state": "queued"},
                "get_crypto_orders": {"data": {"results": [{"id": "o9", "state": "queued"}]}}})
    r = c.buy("BTC-USD", 20, "cid-9")
    check("poll ends on a frozen clock with the order still SUBMITTED", r["state"] == bk.SUBMITTED, repr(r))


def test_cancel():
    c = client({"cancel_crypto_order": {}})
    check("cancel returns True on success", c.cancel("ord-1") is True)

    def boom(tool, args):
        raise RuntimeError("nope")

    c2 = crypto_live.CryptoLive("123456", call=boom, now=lambda: NOW,
                                sleep=lambda s: None)
    check("cancel returns False on error", c2.cancel("ord-1") is False)


def test_empty_account():
    try:
        crypto_live.CryptoLive("", call=lambda t, a: {})
        check("empty account raises ValueError", False)
    except ValueError:
        check("empty account raises ValueError", True)


def main():
    test_quote()
    test_increments_and_round_qty()
    test_buy_polls_to_filled()
    test_buy_without_order_id()
    test_sell_below_min()
    test_place_stop()
    test_positions_pages()
    test_open_orders_filter()
    test_poll_is_bounded()
    test_cancel()
    test_empty_account()
    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
