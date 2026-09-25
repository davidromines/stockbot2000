"""Thin, defensive client for Robinhood crypto orders, quotes and positions.

Stage K5 part 1. Every call goes through an injected ``call(tool, args)`` so
tests never touch the network and nothing is placed on import.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import time
from datetime import datetime, timezone
from decimal import Decimal, ROUND_DOWN

import broker as bk
import robinhood_live as rl

# broker.py may predate the UNKNOWN state; fall back to the literal so a missing
# attribute can never silently become an exception mid-order.
UNKNOWN = getattr(bk, "UNKNOWN", "UNKNOWN")

# Crypto order states are a different vocabulary from equity states. Anything
# not listed maps to UNKNOWN rather than being optimistically treated as live.
_STATE_MAP = {
    "queued": bk.SUBMITTED,
    "confirmed": bk.SUBMITTED,
    "unconfirmed": bk.SUBMITTED,
    "pending": bk.SUBMITTED,
    "partially_filled": bk.PARTIALLY_FILLED,
    "filled": bk.FILLED,
    "canceled": bk.CANCELLED,
    "cancelled": bk.CANCELLED,
    "voided": bk.CANCELLED,
    "rejected": bk.REJECTED,
    "failed": bk.REJECTED,
}

_TERMINAL = (bk.FILLED, bk.CANCELLED, bk.REJECTED)


def _map_state(raw):
    if not isinstance(raw, str):
        return UNKNOWN
    return _STATE_MAP.get(raw.strip().lower(), UNKNOWN)


def _parse_ts(value):
    """Parse an ISO timestamp to an aware UTC datetime, or None."""
    if not isinstance(value, str) or not value.strip():
        return None
    text = value.strip()
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    if dt.tzinfo is None:
        # A naive timestamp has no defined instant; refusing it is the
        # conservative reading, since guessing a zone could make a stale quote
        # look fresh.
        return None
    return dt.astimezone(timezone.utc)


def _pair(raw):
    """'BTC', 'BTCUSD', 'btc-usd' -> 'BTC-USD'; None stays None."""
    if not raw:
        return None
    t = str(raw).upper().replace("-", "")
    if t.endswith("USD") and len(t) > 3:
        t = t[:-3]
    return f"{t}-USD"


class CryptoLive:
    def __init__(self, account, call=None, sleep=time.sleep, now=None,
                 poll_seconds=20.0, poll_every=2.0, max_quote_age=120.0):
        if not account:
            raise ValueError("account (rhs_account_number) is required")
        self.account = str(account)
        if call is None:
            import robinhood_mcp
            call = robinhood_mcp.call
        self._call = call
        self._sleep = sleep
        self._now = now or (lambda: datetime.now(timezone.utc))
        self.poll_seconds = float(poll_seconds)
        self.poll_every = float(poll_every)
        self.max_quote_age = float(max_quote_age)
        self._increments = None

    # -- quotes -----------------------------------------------------------
    def quote(self, symbol):
        want = str(symbol).replace("-", "").upper()
        resp = self._call("get_crypto_quotes",
                          {"symbols": [want], "rhs_account_number": self.account})
        rows = rl.rows(resp, "results", "data")
        row = None
        for r in rows or []:
            if isinstance(r, dict) and str(rl.find(r, "symbol") or "").upper() == want:
                row = r
                break
        if row is None:
            return None
        bid = rl.num(rl.find(row, "bid_price", "bid"))
        ask = rl.num(rl.find(row, "ask_price", "ask"))
        mark = rl.num(rl.find(row, "mark_price", "mark"))
        if bid is None or ask is None or bid <= 0 or ask <= 0 or ask < bid:
            return None
        updated = _parse_ts(rl.find(row, "updated_at", "quote_time"))
        if updated is None:
            return None
        age = (self._now() - updated).total_seconds()
        if age > self.max_quote_age:
            return None
        price = mark if (mark is not None and mark > 0) else (bid + ask) / 2.0
        return {
            "symbol": _pair(symbol),
            "bid": bid,
            "ask": ask,
            "mark": mark,
            "price": price,
            "updated_at": updated.isoformat(),
            "age_s": age,
        }

    # -- currency pairs ---------------------------------------------------
    def increments(self):
        if self._increments is None:
            resp = self._call("get_currency_pairs", {"limit": 700})
            out = {}
            for row in rl.rows(resp, "results", "data") or []:
                if not isinstance(row, dict):
                    continue
                sym = rl.find(row, "symbol")
                if not sym:
                    continue
                out[str(sym).upper()] = {
                    "qty_increment": rl.num(rl.find(row, "min_order_quantity_increment")),
                    "min_qty": rl.num(rl.find(row, "min_order_size")),
                    "tradable": str(rl.find(row, "tradability") or "").lower() == "tradable",
                }
            self._increments = out
        return self._increments

    def round_qty(self, symbol, qty):
        pair = self.increments().get(str(symbol).upper())
        if not pair:
            return None
        inc = pair.get("qty_increment")
        if not inc or inc <= 0:
            return None
        try:
            d = Decimal(str(qty))
            step = Decimal(str(inc))
        except Exception:
            return None
        if d <= 0:
            return None
        # Round DOWN: rounding up can exceed the sellable balance and get the
        # order rejected after it has already been sent.
        rounded = (d / step).to_integral_value(rounding=ROUND_DOWN) * step
        if rounded <= 0:
            return None
        min_qty = pair.get("min_qty")
        if min_qty is not None and rounded < Decimal(str(min_qty)):
            return None
        return format(rounded.normalize(), "f")

    # -- positions --------------------------------------------------------
    def positions(self):
        out = {}
        cursor, seen = None, set()
        while True:
            args = {"rhs_account_number": self.account}
            if cursor:
                args["cursor"] = cursor
            resp = self._call("get_crypto_positions", args)
            for row in rl.rows(resp, "results", "data") or []:
                if not isinstance(row, dict):
                    continue
                code = rl.find(row, "code")
                if not code:
                    continue
                qty = rl.num(rl.find(row, "quantity_transferable"))
                if qty is None or qty <= 0:
                    continue
                out["%s-USD" % str(code).upper()] = qty
            cursor = rl.find(resp, "next", "cursor")
            if not cursor or cursor in seen:
                break
            seen.add(cursor)
        return out

    # -- orders -----------------------------------------------------------
    def _place(self, args):
        args = dict(args)
        args["rhs_account_number"] = self.account
        return self._call("place_crypto_order", args)

    def _order_id(self, resp):
        oid = rl.find(resp, "id", "order_id")
        return str(oid) if oid else None

    def buy(self, symbol, usd, client_order_id):
        resp = self._place({
            "symbol": str(symbol).upper(),
            "side": "buy",
            "type": "market",
            "dollar_amount": "%.2f" % float(usd),
            "time_in_force": "gtc",
            "ref_id": rl.ref_id(client_order_id),
        })
        return self._poll(self._order_id(resp))

    def sell(self, symbol, qty, client_order_id):
        rounded = self.round_qty(symbol, qty)
        if rounded is None:
            return {"state": bk.REJECTED, "reason": "quantity below minimum increment"}
        resp = self._place({
            "symbol": str(symbol).upper(),
            "side": "sell",
            "type": "market",
            "quantity": rounded,
            "time_in_force": "gtc",
            "ref_id": rl.ref_id(client_order_id),
        })
        return self._poll(self._order_id(resp))

    def place_stop(self, symbol, qty, stop_price, client_order_id):
        rounded = self.round_qty(symbol, qty)
        if rounded is None:
            return {"state": bk.REJECTED, "reason": "quantity below minimum increment"}
        price = float(stop_price)
        # Sub-dollar crypto needs significant digits, not cents; "%.2f" would
        # round a $0.0000123 stop to zero.
        stop = "%.2f" % price if price >= 1 else "%.6g" % price
        resp = self._place({
            "symbol": str(symbol).upper(),
            "side": "sell",
            "type": "stop_loss",
            "quantity": rounded,
            "stop_price": stop,
            "time_in_force": "gtc",
            "ref_id": rl.ref_id(client_order_id),
        })
        # Stops are not polled: the resting order is not expected to fill now.
        return {"state": _map_state(rl.find(resp, "state")),
                "order_id": self._order_id(resp)}

    def cancel(self, order_id):
        try:
            self._call("cancel_crypto_order",
                       {"rhs_account_number": self.account, "order_id": order_id})
            return True
        except Exception:
            return False

    def _poll(self, order_id):
        if not order_id:
            # No id means we cannot know what happened; never report FILLED.
            return {"state": UNKNOWN, "order_id": None,
                    "filled_qty": None, "avg_price": None}
        deadline = self._now().timestamp() + self.poll_seconds
        # Bounded by count as well as clock, so a clock that does not advance
        # (or a sleep that returns at once) cannot spin forever.
        tries = int(self.poll_seconds / max(self.poll_every, 1e-9)) + 1
        state = UNKNOWN
        filled = None
        avg = None
        while True:
            resp = self._call("get_crypto_orders",
                              {"rhs_account_number": self.account,
                               "order_id": order_id})
            rows = rl.rows(resp, "results", "data") or []
            row = None
            for r in rows:
                if isinstance(r, dict) and str(rl.find(r, "id", "order_id") or "") == str(order_id):
                    row = r
                    break
            if row is None and rows and isinstance(rows[0], dict):
                row = rows[0]
            if row is not None:
                state = _map_state(rl.find(row, "state"))
                filled = rl.num(rl.find(row, "cumulative_quantity", "filled_quantity"))
                avg = rl.num(rl.find(row, "average_price", "avg_price"))
            if state in _TERMINAL:
                break
            tries -= 1
            if tries <= 0 or self._now().timestamp() >= deadline:
                break
            self._sleep(self.poll_every)
        return {"state": state, "order_id": order_id,
                "filled_qty": filled, "avg_price": avg}

    def open_orders(self, symbol=None):
        resp = self._call("get_crypto_orders",
                          {"rhs_account_number": self.account, "state_group": "open"})
        want = _pair(symbol) if symbol else None
        out = []
        for row in rl.rows(resp, "results", "data") or []:
            if not isinstance(row, dict):
                continue
            # Orders carry currency_code ("BTC"), not a pair symbol (the tool's guide).
            sym = _pair(rl.find(row, "symbol") or rl.find(row, "currency_code"))
            if want and sym != want:
                continue
            out.append({
                "order_id": rl.find(row, "id", "order_id"),
                "symbol": sym,
                "side": rl.find(row, "side"),
                "type": rl.find(row, "type"),
                "state": _map_state(rl.find(row, "state")),
            })
        return out
