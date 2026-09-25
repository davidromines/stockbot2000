"""
Regression tests for the LIVE path (robinhood_live.py and slot_trader LIVE mode),
against a FAKE Robinhood — no network, no account, no orders.

Pinned: an approved buy goes review -> place (dollar amount, market, regular
hours, stable ref_id) -> confirmed fill; a failed review is REJECTED and never
placed; a transport failure after submission leaves the order UNKNOWN (never
resubmitted); sells are sized in shares rounded DOWN; responses are read in
the shapes Robinhood actually returns (payloads under "data"); LIVE
reconciliation tolerates shares the system did not buy but not fewer than the
slots hold; a pending order from an earlier run is resolved into the slot log;
LIVE is refused while execution_mode is not LIVE.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
from unittest import mock

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import broker as bk
import execution as ex
import quotes as qt
import robinhood_live as rl
import robinhood_mcp as rh
import signals as sg
import slot_trader as st

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


class FakeRH:
    """Answers tool calls the way the real server shapes them (probed 2026-09-24)."""

    def __init__(self, positions=None, fail_review=False, fail_place=None, fill=True):
        self.calls, self.positions = [], positions or {}
        self.fail_review, self.fail_place, self.fill = fail_review, fail_place, fill

    def __call__(self, tool, args):
        self.calls.append((tool, dict(args)))
        if tool == "get_portfolio":
            return {"data": {"total_value": "87.72", "buying_power": {"buying_power": "68.45"}}}
        if tool == "get_accounts":
            return {"data": {"accounts": [{"account_number": "403446024", "unsettled_funds": "0.00",
                                           "agentic_allowed": True, "type": "limited_margin"}]}}
        if tool == "get_equity_positions":
            return {"data": {"positions": [{"symbol": s, "quantity": str(q), "shares_available_for_sells": str(q),
                                            "average_buy_price": "50.0"} for s, q in self.positions.items()]}}
        if tool == "get_equity_quotes":
            s = args["symbols"][0]
            return {"data": {"results": [{"quote": {"symbol": s, "last_trade_price": "50.00",
                                                    "venue_last_trade_time": "2099-01-01T00:00:00Z"}}]}}
        if tool == "review_equity_order":
            if self.fail_review:
                raise rh.RobinhoodError("insufficient buying power")
            return {"data": {"alerts": []}}
        if tool == "place_equity_order":
            if self.fail_place:
                raise self.fail_place
            return {"data": {"id": "rh-1", "state": "queued"}}
        if tool == "get_equity_orders":
            st_ = "filled" if self.fill else "queued"
            return {"data": {"orders": [{"id": "rh-1", "state": st_, "cumulative_quantity": "0.4",
                                         "average_price": "50.00"}]}}
        if tool == "cancel_equity_order":
            return {"data": {}}
        raise AssertionError(f"unexpected tool {tool}")


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    c.execute("INSERT INTO features VALUES ('AAA', '2026-09-23', 2.0, 5e7)")
    c.execute("INSERT INTO fundamentals VALUES ('AAA', '2026-01-01', 5e9)")
    st.init(c)
    return c


def order(side="BUY", notional=20.0, qty=None, cid="cid-1"):
    o = bk.Order(signal_id=cid, symbol="AAA", side=side, notional=notional if side == "BUY" else None,
                 quantity=qty)
    o.to(bk.VALIDATING); o.to(bk.APPROVED)
    return o


def main():
    with mock.patch.object(qt, "market_open", lambda *a: True), mock.patch("time.sleep", lambda s: None):
        c = db()
        fake = FakeRH()
        b = rl.LiveBroker(c, "403446024", call=fake, poll_seconds=5)
        o = b.place_order(order())
        tools = [t for t, _ in fake.calls]
        check("buy: review before place", tools.index("review_equity_order") < tools.index("place_equity_order"),
              tools)
        pa = next(a for t, a in fake.calls if t == "place_equity_order")
        check("buy: $20 market, regular hours", pa["dollar_amount"] == "20.00" and pa["type"] == "market"
              and pa["market_hours"] == "regular_hours" and "quantity" not in pa, pa)
        check("buy: stable ref_id from the decision", pa["ref_id"] == rl.ref_id("cid-1"), pa["ref_id"])
        check("buy: confirmed fill read back", o.state == bk.FILLED and o.filled_quantity == 0.4
              and o.avg_fill_price == 50.0 and o.broker_order_id == "rh-1", (o.state, o.filled_quantity))

        fake = FakeRH(fail_review=True)
        o = rl.LiveBroker(c, "403446024", call=fake).place_order(order(cid="cid-2"))
        check("failed review -> REJECTED, never placed", o.state == bk.REJECTED
              and "place_equity_order" not in [t for t, _ in fake.calls], o.state)

        fake = FakeRH(fail_place=TimeoutError("read timed out"))
        o = rl.LiveBroker(c, "403446024", call=fake).place_order(order(cid="cid-3"))
        check("transport failure after submit -> UNKNOWN (never resubmitted)", o.state == bk.UNKNOWN
              and [t for t, _ in fake.calls].count("place_equity_order") == 1, o.state)

        fake = FakeRH()
        rl.LiveBroker(c, "403446024", call=fake).place_order(order(side="SELL", qty=0.40184899, cid="cid-4"))
        pa = next(a for t, a in fake.calls if t == "place_equity_order")
        check("sell: shares rounded DOWN to 6 dp", pa["quantity"] == "0.401848" and "dollar_amount" not in pa, pa)

        b = rl.LiveBroker(c, "403446024", call=FakeRH(positions={"AAA": 0.4}))
        acct = b.get_account()
        check("account read from the real shapes", acct["equity"] == 87.72 and acct["cash"] == 68.45
              and acct["unsettled_funds"] == 0.0, acct)
        check("positions read from under data", b.get_positions().get("AAA", {}).get("quantity") == 0.4)

        # LIVE reconciliation: more shares than the slots bought is fine, fewer is not.
        c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, "
                  "price, reason, signal_id) VALUES ('2026-09-24T14:00:00', 'LIVE', 1, 'k', 1, 'AAA', 'OPEN', "
                  "0.2, 50, 't', 's')")
        c.commit()
        ok, _ = st.reconcile(c, rl.LiveBroker(c, "403446024", call=FakeRH(positions={"AAA": 0.4, "ACT": 1})),
                             "LIVE")
        check("LIVE reconcile tolerates shares the system did not buy", ok)
        ok, diffs = st.reconcile(c, rl.LiveBroker(c, "403446024", call=FakeRH(positions={"AAA": 0.1})), "LIVE")
        check("LIVE reconcile fails when the account holds fewer than the slots", not ok, diffs)

        # A pending order from an earlier run resolves into the slot log.
        c.execute("DELETE FROM slot_trades")
        sig = sg.Signal(symbol="AAA", action="BUY", strategy="slot2:fx_k", reason="r", notional_value=20.0,
                        session="2026-09-24")
        sg.record(c, sig)
        c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
                  "reason) VALUES ('2026-09-24T13:00:00', 2, 'ASSIGN', 'fx_k', 1, 20, 'LIVE', 't')")
        c.execute("INSERT INTO orders (client_order_id, signal_id, created_at, session, symbol, side, notional, "
                  "state, broker_order_id, mode) VALUES (?, ?, 't', '2026-09-24', 'AAA', 'BUY', 20, 'SUBMITTED', "
                  "'rh-1', 'LIVE')", (ex.client_id(sig.signal_id, "LIVE"), sig.signal_id))
        c.commit()
        import slots
        slots.genome_for = lambda conn, k, v: {"entry": {}, "exit": {}, "risk": {"stop_atr_multiple": 2.0,
                                                                                   "max_hold_days": 20}}
        import notify
        notify.notify = lambda *a, **k: []
        done = st.resolve_pending(c, {}, rl.LiveBroker(c, "403446024", call=FakeRH()), "LIVE")
        pos = st.open_positions(c, "LIVE")
        check("pending order resolved into the slot log", len(done) == 1 and pos.get(2, {}).get("quantity") == 0.4,
              (done, pos))

    # Pinned: the production config/risk.yaml may really say LIVE.
    with mock.patch.object(st.risk_engine, "load_limits",
                           lambda *a, **k: {"execution_mode": "SIMULATION",
                                            "robinhood": {"account_number": "403446024"}}):
        try:
            st._build(c, {}, "LIVE", None)
            check("LIVE refused while execution_mode is not LIVE", False)
        except st.LiveNotWired:
            check("LIVE refused while execution_mode is not LIVE", True)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
