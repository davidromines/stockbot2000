"""
Crypto behind the same BrokerInterface as equities (Stage K5 part 2).

CryptoBroker is a LiveBroker whose reads and writes go to Robinhood's crypto
endpoints instead of the equity ones. Everything above the broker — the
execution engine, the risk engine, the kill switches — is unchanged, which is
the point: a crypto order is approved, deduplicated and recorded by exactly the
code that handles an equity order.

Two things differ from the equity adapter and both are deliberate:

`dollar_volume_20` is computed from `crypto_prices`, not from `features`. The
risk engine rejects a quote without liquidity, and crypto has no row in the
equity feature table, so a quote that omitted it would block every crypto order.

Cost basis is not read. Robinhood's crypto positions do not expose an average
buy price through the tools this project uses, and inventing one (the current
mark, say) would make every open position look flat. Entry is 0.0 and the
accounting layer, which has the fills, is the place that knows the truth.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging

import broker as bk
import crypto_live as cl
import robinhood_live as rl

log = logging.getLogger("crypto_broker")

# The risk engine rejects a quote whose liquidity is unknown, so a symbol with
# too few daily bars is a symbol that cannot be traded rather than one that is
# traded with a guessed figure.
MIN_BARS_FOR_LIQUIDITY = 5
LIQUIDITY_BARS = 20


class CryptoBroker(rl.LiveBroker):
    def __init__(self, conn, account_number, call=None, client=None, poll_seconds=20.0):
        if client is None:
            if call is None:
                import robinhood_mcp
                call = robinhood_mcp.call
            client = cl.CryptoLive(account_number, call=call, poll_seconds=poll_seconds)
        # LiveBroker's own provider is never used here (get_quote is overridden),
        # but it is constructed with the same call so get_account still reads the
        # portfolio through the equity transport.
        super().__init__(conn, account_number, call=call, provider=None,
                         poll_seconds=poll_seconds)
        self.client = client

    # -- reads -------------------------------------------------------------
    def _liquidity(self, symbol) -> float | None:
        rows = self.conn.execute(
            "SELECT close, volume FROM crypto_prices WHERE symbol=? AND interval='1d' "
            "AND close>0 ORDER BY open_time DESC LIMIT ?",
            (str(symbol).upper(), LIQUIDITY_BARS)).fetchall()
        if len(rows) < MIN_BARS_FOR_LIQUIDITY:
            return None
        vals = [float(c) * float(v) for c, v in rows if v is not None]
        if not vals:
            return None
        return sum(vals) / len(vals)

    def get_quote(self, symbol):
        q = self.client.quote(symbol)
        if not q:
            return None
        out = dict(q)
        out["dollar_volume_20"] = self._liquidity(symbol)
        out["source"] = "robinhood_crypto"
        return out

    def get_positions(self) -> dict:
        out = {}
        for sym, qty in (self.client.positions() or {}).items():
            q = self.get_quote(sym)
            px = float(q["price"]) if q and q.get("price") else 0.0
            out[sym] = {"quantity": float(qty), "entry": 0.0, "price": px,
                        "value": float(qty) * px}
        return out

    # -- orders ------------------------------------------------------------
    def place_order(self, order: bk.Order) -> bk.Order:
        if order.asset_type != "crypto":
            order.to(bk.REJECTED, f"crypto broker refuses asset_type={order.asset_type!r}")
            return order
        if order.side == "BUY":
            if not order.notional or float(order.notional) <= 0:
                order.to(bk.REJECTED, "buy needs a positive notional")
                return order
        elif order.side == "SELL":
            if not order.quantity or float(order.quantity) <= 0:
                order.to(bk.REJECTED, "sell needs a positive quantity")
                return order
        else:
            order.to(bk.REJECTED, f"unknown side {order.side!r}")
            return order

        order.to(bk.SUBMITTING)
        try:
            if order.side == "BUY":
                res = self.client.buy(order.symbol, order.notional, order.client_order_id)
            else:
                res = self.client.sell(order.symbol, order.quantity, order.client_order_id)
        except Exception as e:                               # noqa: BLE001 — sent or not: unknown
            # Unlike the equity path there is no review call before placing, and
            # the client polls after placing: an error here may come from an
            # order that was sent (even filled). It is UNKNOWN — resolved by
            # asking Robinhood (ref_id makes a retry the same order), never
            # assumed rejected.
            order.to(bk.UNKNOWN, f"transport after submit: {type(e).__name__}: {e}")
            return order

        res = res or {}
        state = res.get("state")
        if state == bk.REJECTED:
            order.to(bk.REJECTED, str(res.get("reason") or "rejected by robinhood"))
            return order
        if state == bk.UNKNOWN or state is None:
            # No readable state means we do not know whether it filled. Reporting
            # SUBMITTED here would let the engine treat an unknown as a live order.
            order.to(bk.UNKNOWN, "crypto order state unreadable")
            return order

        order.broker_order_id = str(res.get("order_id") or "") or None
        order.to(bk.SUBMITTED)
        if state != bk.SUBMITTED:
            try:
                order.to(state)
            except bk.TransitionError:
                log.warning(f"{order.client_order_id}: ignoring SUBMITTED -> {state}")
        order.filled_quantity = float(res.get("filled_qty") or 0.0)
        order.avg_fill_price = res.get("avg_price")
        return order

    def place_stop(self, symbol, quantity, stop_price, client_order_id):
        return self.client.place_stop(symbol, quantity, stop_price, client_order_id)

    def cancel_order(self, order_id: str) -> bool:
        return bool(self.client.cancel(order_id))

    def get_order(self, order_id: str) -> dict | None:
        resp = self.call("get_crypto_orders",
                         {"rhs_account_number": self.account, "order_id": order_id})
        recs = rl.rows(resp, "results", "data") or []
        rec = None
        for r in recs:
            if isinstance(r, dict) and str(rl.find(r, "id", "order_id") or "") == str(order_id):
                rec = r
                break
        if rec is None and recs and isinstance(recs[0], dict):
            rec = recs[0]
        if rec is None:
            return None
        return {"state": cl._map_state(rl.find(rec, "state")),
                "filled_quantity": rl.num(rl.find(rec, "cumulative_quantity", "filled_quantity")) or 0.0,
                "avg_fill_price": rl.num(rl.find(rec, "average_price", "avg_price")),
                "broker_order_id": order_id}

    def open_stops(self, symbol=None) -> list:
        return [o for o in (self.client.open_orders(symbol) or [])
                if str(o.get("type") or "").lower() == "stop_loss"]
