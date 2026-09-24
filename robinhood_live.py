"""
The LIVE broker: the real Robinhood Agentic account behind the existing
BrokerInterface (Addendum A I8; Addendum B §B13-B14).

Everything that decides WHETHER to trade stays where it was — slots.py picks
the strategies, the risk engine sizes and approves, the kill switches halt, the
execution engine deduplicates and records. This module only turns an approved
Order into Robinhood calls and reads the account back:

    place_order   review_equity_order (pre-trade checks) -> place_equity_order
                  -> poll get_equity_orders until filled or 20 s
                  BUY  : market, regular hours, dollar_amount = the risk engine's notional
                  SELL : market, regular hours, quantity = the slot's shares (6 dp, rounded DOWN)
                  ref_id = UUIDv5(client_order_id): a retried decision is the SAME
                  Robinhood order (the server deduplicates on ref_id)
    get_account   equity and buying power from get_portfolio; daily P&L and
                  drawdown from this module's own equity snapshots (live_equity)
    get_positions get_equity_positions, valued at real-time quotes
    get_quote     get_equity_quotes (real time), plus liquidity from the database
                  and market cap from the filings, else Robinhood's own
                  fundamentals (market_caps.py), because the risk engine
                  rejects a quote without them

Response shapes are read defensively (field names searched, not assumed); a
response this module cannot read raises, and the engine treats that as a
failure — never as a fill. A transport failure after submission leaves the
order UNKNOWN; it is resolved by asking Robinhood, never by resubmitting.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging
import time
import uuid
from datetime import datetime, timezone
from decimal import ROUND_DOWN, Decimal

import broker as bk
import quotes as qt
import robinhood_mcp as rh

log = logging.getLogger("robinhood_live")

STATE = {"new": bk.SUBMITTED, "queued": bk.SUBMITTED, "confirmed": bk.SUBMITTED,
         "unconfirmed": bk.SUBMITTED, "pending": bk.SUBMITTED,
         "partially_filled": bk.PARTIALLY_FILLED, "filled": bk.FILLED,
         "cancelled": bk.CANCELLED, "canceled": bk.CANCELLED, "voided": bk.CANCELLED,
         "rejected": bk.REJECTED, "failed": bk.REJECTED}


def find(obj, *keys):
    """First value under any of `keys`, searching nested dicts and lists."""
    if isinstance(obj, dict):
        for k in keys:
            if k in obj and obj[k] not in (None, ""):
                return obj[k]
        for v in obj.values():
            r = find(v, *keys)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = find(v, *keys)
            if r is not None:
                return r
    return None


def rows(obj, *keys) -> list:
    """The list of records under the first of `keys` (or obj itself if it is a list)."""
    if isinstance(obj, list):
        return obj
    if not isinstance(obj, dict):
        return []
    for k in keys:
        if isinstance(obj.get(k), list):
            return obj[k]
    # Robinhood wraps payloads, e.g. {"data": {"positions": [...]}}: search nested dicts.
    for v in obj.values():
        if isinstance(v, dict):
            r = rows(v, *keys)
            if r:
                return r
    return []


def num(v) -> float | None:
    # Robinhood nests some figures one level deeper, e.g.
    # "buying_power": {"buying_power": "68.4500", ...} (probe, 2026-09-24).
    if isinstance(v, dict):
        for k in ("buying_power", "amount", "value"):
            if k in v:
                return num(v[k])
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def ref_id(client_order_id: str) -> str:
    return str(uuid.uuid5(uuid.NAMESPACE_URL, f"stockbot2000:{client_order_id}"))


def dp6_down(q: float) -> str:
    return str(Decimal(str(q)).quantize(Decimal("0.000001"), rounding=ROUND_DOWN))


def _init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS live_equity (
        at TEXT NOT NULL, session TEXT NOT NULL, equity REAL NOT NULL, buying_power REAL)""")
    conn.commit()


class RobinhoodQuotes(qt.QuoteProvider):
    """Real-time quotes from the Robinhood MCP, refused when stale or outside the session."""

    def __init__(self, conn, call=None, max_age_seconds: int = 300):
        self.conn, self.max_age = conn, max_age_seconds
        self.call = call or rh.call
        self._cache = {}

    def get(self, symbol):
        if symbol in self._cache:
            return self._cache[symbol]
        q = None
        try:
            r = self.call("get_equity_quotes", {"symbols": [symbol]})
            # Shape (probe 2026-09-24): {"data": {"results": [{"quote": {"symbol": ...,
            # "last_trade_price": ..., "venue_last_trade_time": ...}}]}}
            recs = rows(find(r, "results", "quotes") or r, "results", "quotes")
            rec = next((x for x in recs if str(find(x, "symbol") or "").upper() == symbol.upper()), None)
            if rec is None:
                raise rh.RobinhoodError(f"no quote for {symbol} in response")
            px = num(find(rec, "last_trade_price", "last_price"))
            ts = find(rec, "venue_last_trade_time", "updated_at", "last_trade_time")
            if px and px > 0 and qt.market_open():
                if ts:
                    age = (datetime.now(timezone.utc) - datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
                           ).total_seconds()
                    if age > self.max_age:
                        log.warning(f"{symbol}: quote {age:.0f}s old — stale, refused")
                        px = None
                if px:
                    q = {"symbol": symbol, "price": px, "as_of": ts, "source": "robinhood",
                         **qt._db_fields(self.conn, symbol, "robinhood", call=self.call)}
        except rh.NeedsLogin:
            raise
        except Exception as e:                               # noqa: BLE001
            log.error(f"{symbol}: robinhood quote failed: {type(e).__name__}: {e}")
        self._cache[symbol] = q
        return q


class LiveBroker(bk.BrokerInterface):
    def __init__(self, conn, account_number: str, call=None, calls=None, provider=None,
                 poll_seconds: float = 20.0):
        if not account_number:
            raise ValueError("robinhood.account_number is not set in config/risk.yaml")
        self.conn, self.account = conn, str(account_number)
        self.call = call or rh.call
        self.calls = calls or rh.calls
        self.provider = provider or RobinhoodQuotes(conn, self.call)
        self.poll = poll_seconds
        _init(conn)

    # -- reads -------------------------------------------------------------
    def _portfolio(self) -> dict:
        p = self.call("get_portfolio", {"account_number": self.account})
        eq = num(find(p, "total_value", "total_equity", "portfolio_value"))
        bp = num(find(p, "buying_power", "cash_available_for_trading", "cash"))
        if eq is None or bp is None:
            raise rh.RobinhoodError(f"portfolio unreadable: {str(p)[:300]}")
        return {"equity": eq, "buying_power": bp}

    def get_account(self) -> dict:
        p = self._portfolio()
        session = datetime.now(qt.NY).date().isoformat()
        prev = self.conn.execute("SELECT equity FROM live_equity WHERE session < ? ORDER BY at DESC LIMIT 1",
                                 (session,)).fetchone()
        peak = self.conn.execute("SELECT MAX(equity) FROM live_equity").fetchone()[0]
        self.conn.execute("INSERT INTO live_equity VALUES (?,?,?,?)",
                          (datetime.now(timezone.utc).isoformat(), session, p["equity"], p["buying_power"]))
        self.conn.commit()
        peak = max(peak or p["equity"], p["equity"])
        # Robinhood's own unsettled figure covers sales made outside this system
        # (e.g. a manual sell in the app); account_rules takes the larger of it
        # and the system's ledger, so no buy is funded by unsettled proceeds.
        unsettled = None
        try:
            accts = self.call("get_accounts", {})
            mine = next((a for a in rows(accts, "accounts") if str(a.get("account_number")) == self.account), {})
            unsettled = num(mine.get("unsettled_funds"))
        except rh.NeedsLogin:
            raise
        except Exception as e:                               # noqa: BLE001
            log.warning(f"unsettled_funds unreadable: {type(e).__name__}")
        return {"equity": p["equity"], "cash": p["buying_power"], "unsettled_funds": unsettled,
                "daily_pnl": p["equity"] - prev[0] if prev else 0.0,
                "drawdown_percent": (peak - p["equity"]) / peak * 100 if peak else 0.0}

    def get_buying_power(self) -> float:
        return self._portfolio()["buying_power"]

    def get_positions(self) -> dict:
        out, cursor = {}, None
        for _ in range(10):
            args = {"account_number": self.account}
            if cursor:
                args["cursor"] = cursor
            r = self.call("get_equity_positions", args)
            for p in rows(r, "positions", "results"):
                sym = str(find(p, "symbol") or "").upper()
                # Sellable shares, per Robinhood's own guidance: shares held for
                # a pending sell are not available to sell again.
                qty = num(find(p, "shares_available_for_sells", "quantity"))
                if not sym or not qty:
                    continue
                entry = num(find(p, "average_buy_price", "average_cost", "avg_cost")) or 0.0
                q = self.provider.get(sym)
                px = q["price"] if q else entry
                out[sym] = {"quantity": qty, "entry": entry, "price": px, "value": qty * px}
            cursor = find(r, "next") if isinstance(r, dict) else None
            if not cursor:
                break
        return out

    def get_quote(self, symbol):
        return self.provider.get(symbol)

    # -- orders --------------------------------------------------------------
    def _args(self, order: bk.Order) -> dict:
        a = {"account_number": self.account, "symbol": order.symbol, "side": order.side.lower(),
             "type": "market", "market_hours": "regular_hours", "time_in_force": "gfd"}
        if order.side == "BUY" and order.notional:
            a["dollar_amount"] = f"{float(order.notional):.2f}"
        elif order.quantity:
            a["quantity"] = dp6_down(float(order.quantity))
        else:
            raise ValueError("order has neither a notional (buy) nor a quantity (sell)")
        return a

    def _apply(self, order: bk.Order, rec) -> None:
        st = STATE.get(str(find(rec, "state", "status") or "").lower())
        if st and st != order.state:
            try:
                order.to(st)
            except bk.TransitionError:
                log.warning(f"{order.client_order_id}: ignoring {order.state} -> {st}")
        order.filled_quantity = num(find(rec, "cumulative_quantity", "filled_quantity")) or order.filled_quantity
        # Raw Robinhood records say average_price; get_order()'s normalised
        # record says avg_fill_price — both must be read, or a fill has no price.
        order.avg_fill_price = num(find(rec, "average_price", "average_fill_price", "avg_fill_price")) \
            or order.avg_fill_price

    def place_order(self, order: bk.Order) -> bk.Order:
        args = self._args(order)
        try:
            self.call("review_equity_order", args)
        except rh.RobinhoodError as e:
            order.to(bk.REJECTED, f"review: {e}")
            return order
        order.to(bk.SUBMITTING)
        try:
            r = self.call("place_equity_order", {**args, "ref_id": ref_id(order.client_order_id)})
        except rh.RobinhoodError as e:
            order.to(bk.REJECTED, f"place: {e}")
            return order
        except Exception as e:                               # noqa: BLE001 — sent or not: unknown
            order.to(bk.UNKNOWN, f"transport after submit: {type(e).__name__}: {e}")
            return order
        order.broker_order_id = str(find(r, "id", "order_id") or "") or None
        order.to(bk.SUBMITTED)
        self._apply(order, r)
        deadline = time.time() + self.poll
        while order.broker_order_id and order.state not in bk.TERMINAL and time.time() < deadline:
            time.sleep(2)
            rec = self.get_order(order.broker_order_id)
            if rec:
                self._apply(order, rec)
        return order

    def get_order(self, order_id: str) -> dict | None:
        r = self.call("get_equity_orders", {"account_number": self.account, "order_id": order_id})
        recs = rows(r, "orders", "results")
        rec = recs[0] if recs else None
        if not rec:
            return None
        st = STATE.get(str(find(rec, "state", "status") or "").lower())
        return {"state": st, "filled_quantity": num(find(rec, "cumulative_quantity", "filled_quantity")) or 0.0,
                "avg_fill_price": num(find(rec, "average_price", "average_fill_price")),
                "broker_order_id": order_id}

    def cancel_order(self, order_id: str) -> bool:
        try:
            self.call("cancel_equity_order", {"account_number": self.account, "order_id": order_id})
            return True
        except rh.RobinhoodError as e:
            log.warning(f"cancel {order_id}: {e}")
            return False
