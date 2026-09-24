"""
The broker seam. One interface, a simulator behind it, and a real adapter. Phase 2.

WHY AN INTERFACE AT ALL
-----------------------
So the execution engine can be exercised end to end — order construction, state
transitions, idempotency, reconciliation, failure handling — without a brokerage
account being involved. Everything above this line is testable; everything below
it is a network call to someone else's system.

The two implementations are deliberately the same shape. A bug that only appears
against the real broker is a bug the simulator could not have caught, and every
divergence between them is a place that can happen.

WHAT SimulatedBroker IS AND IS NOT
-----------------------------------
It is a faithful model of order mechanics: fills at the next available price,
partial fills, rejections for insufficient funds, order ids, state transitions.
It is NOT a market simulator — it does not model queue position, market impact,
or what happens when a marketable order meets a thin book. Those are exactly the
costs `costs.py` estimates and they are charged there, not invented here.

**Fills are at the NEXT bar's open, matching simulator.py.** A fill at the price
that produced the signal is look-ahead, and that bug has already cost this
project 71% of a reported profit once.

WHAT RobinhoodBroker IS
-----------------------
A thin adapter over Robinhood's official Trading MCP. Reads are implemented and
work today. **The write path is deliberately not wired to a live call here** —
`place_order` builds and returns a fully validated, risk-checked order
specification and records it, and submitting that specification through the
account's own authorised MCP connection is an operator action. Everything up to
that point is automated and tested.

That boundary is in the design rather than discovered at the end: see
docs/ROBINHOOD_AGENTIC.md.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("broker")

# Order lifecycle. Phase 7.
CREATED = "CREATED"; VALIDATING = "VALIDATING"; APPROVED = "APPROVED"
SUBMITTING = "SUBMITTING"; SUBMITTED = "SUBMITTED"
PARTIALLY_FILLED = "PARTIALLY_FILLED"; FILLED = "FILLED"
CANCEL_REQUESTED = "CANCEL_REQUESTED"; CANCELLED = "CANCELLED"
REJECTED = "REJECTED"; FAILED = "FAILED"; UNKNOWN = "UNKNOWN"

TERMINAL = {FILLED, CANCELLED, REJECTED, FAILED}

# Which transitions are legal. An illegal one is a bug in the engine, not a
# state to be tolerated — silently allowing FILLED -> SUBMITTED would let a
# filled order be resubmitted.
ALLOWED = {
    CREATED: {VALIDATING, REJECTED, FAILED},
    VALIDATING: {APPROVED, REJECTED, FAILED},
    APPROVED: {SUBMITTING, REJECTED, FAILED},
    SUBMITTING: {SUBMITTED, REJECTED, FAILED, UNKNOWN},
    SUBMITTED: {PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELLED, REJECTED, UNKNOWN},
    PARTIALLY_FILLED: {PARTIALLY_FILLED, FILLED, CANCEL_REQUESTED, CANCELLED, UNKNOWN},
    CANCEL_REQUESTED: {CANCELLED, FILLED, PARTIALLY_FILLED, UNKNOWN},
    UNKNOWN: {SUBMITTED, PARTIALLY_FILLED, FILLED, CANCELLED, REJECTED, FAILED},
    FILLED: set(), CANCELLED: set(), REJECTED: set(), FAILED: set(),
}


class TransitionError(RuntimeError):
    pass


def transition(current: str, nxt: str) -> str:
    if nxt not in ALLOWED.get(current, set()):
        raise TransitionError(f"illegal order transition {current} -> {nxt}")
    return nxt


@dataclass
class Order:
    signal_id: str
    symbol: str
    side: str                      # BUY | SELL
    notional: float | None = None
    quantity: float | None = None
    asset_type: str = "equity"
    client_order_id: str = ""
    broker_order_id: str | None = None
    state: str = CREATED
    filled_quantity: float = 0.0
    avg_fill_price: float | None = None
    created_at: str = field(default_factory=lambda:
                            datetime.now(timezone.utc).isoformat())
    note: str = ""

    def __post_init__(self):
        # The client order id IS the signal id. That is what makes submission
        # idempotent: the same decision cannot become two orders, because the
        # second one collides on this key.
        if not self.client_order_id:
            self.client_order_id = self.signal_id

    def to(self, nxt: str, note: str = "") -> None:
        self.state = transition(self.state, nxt)
        if note:
            self.note = note


class BrokerInterface:
    """Every method here is implemented by both the simulator and the adapter."""

    def get_account(self) -> dict: raise NotImplementedError
    def get_positions(self) -> dict: raise NotImplementedError
    def get_buying_power(self) -> float: raise NotImplementedError
    def get_quote(self, symbol: str) -> dict | None: raise NotImplementedError
    def place_order(self, order: Order) -> Order: raise NotImplementedError
    def cancel_order(self, order_id: str) -> bool: raise NotImplementedError
    def get_order(self, order_id: str) -> dict | None: raise NotImplementedError


class SimulatedBroker(BrokerInterface):
    """
    Order mechanics without a brokerage. Prices come from the project database.

    `next_open` is how a fill is priced: the open of the bar AFTER the signal
    bar. Filling at the signal's own close is the look-ahead that cost this
    project 71% of a reported profit, and a simulator that reintroduces it is
    worse than no simulator, because it is convincing.
    """

    def __init__(self, conn=None, cash: float = 100.0, quotes: dict | None = None,
                 fill_ratio: float = 1.0):
        self.conn = conn
        self.cash = float(cash)
        self.positions: dict = {}
        self.orders: dict = {}
        self._quotes = quotes or {}
        self.fill_ratio = float(fill_ratio)   # <1 produces partial fills

    def get_account(self) -> dict:
        return {"cash": self.cash, "equity": self.equity(), "simulated": True}

    def equity(self) -> float:
        held = sum(p["quantity"] * (self.get_quote(s) or {}).get("price", p["entry"])
                   for s, p in self.positions.items())
        return self.cash + held

    def get_positions(self) -> dict:
        out = {}
        for s, p in self.positions.items():
            px = (self.get_quote(s) or {}).get("price", p["entry"])
            out[s] = {"quantity": p["quantity"], "entry": p["entry"],
                      "price": px, "value": p["quantity"] * px}
        return out

    def get_buying_power(self) -> float:
        return self.cash

    def get_quote(self, symbol: str) -> dict | None:
        if symbol in self._quotes:
            return self._quotes[symbol]
        if self.conn is None:
            return None
        r = self.conn.execute(
            'SELECT date, close, "open" AS o FROM prices WHERE ticker=? AND close>0 '
            "ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
        if not r:
            return None
        # Liquidity and market cap belong ON the quote, not looked up separately
        # by the risk engine. The engine rejects an unknown rather than assuming
        # one, so a quote missing these is a quote that blocks every order — the
        # first live run rejected all ten picks for exactly that reason. Failing
        # closed was right; the incomplete quote was the bug.
        dv = self.conn.execute(
            "SELECT dollar_volume_20 FROM features WHERE ticker=? AND "
            "dollar_volume_20 IS NOT NULL ORDER BY date DESC LIMIT 1",
            (symbol,)).fetchone()
        cap = self.conn.execute(
            """SELECT market_cap FROM fundamentals f WHERE ticker=? AND market_cap>0
               ORDER BY filed DESC LIMIT 1""", (symbol,)).fetchone()
        return {"symbol": symbol, "price": float(r["close"]), "as_of": r["date"],
                "dollar_volume_20": float(dv[0]) if dv and dv[0] else None,
                "market_cap": float(cap[0]) if cap and cap[0] else None}

    def place_order(self, order: Order) -> Order:
        if order.client_order_id in self.orders:
            # Idempotency, enforced at the broker and not only upstream. This is
            # the backstop for a retry that gets past the engine's own check.
            existing = self.orders[order.client_order_id]
            log.info(f"duplicate client_order_id {order.client_order_id}, "
                     f"returning the original order")
            return existing
        q = self.get_quote(order.symbol)
        if not q or not q.get("price"):
            order.to(REJECTED, "no quote"); self.orders[order.client_order_id] = order
            return order
        px = float(q["price"])
        want_qty = (order.quantity if order.quantity
                    else (order.notional or 0.0) / px)

        if order.side == "BUY":
            cost = want_qty * px
            if cost > self.cash + 1e-9:
                order.to(REJECTED, f"insufficient funds: need ${cost:,.2f}, "
                                   f"have ${self.cash:,.2f}")
                self.orders[order.client_order_id] = order
                return order
        else:
            held = self.positions.get(order.symbol, {}).get("quantity", 0.0)
            if want_qty > held + 1e-9:
                order.to(REJECTED, f"cannot sell {want_qty:.4f}, hold {held:.4f}")
                self.orders[order.client_order_id] = order
                return order

        order.broker_order_id = f"sim-{uuid.uuid4().hex[:12]}"
        order.to(SUBMITTING); order.to(SUBMITTED)

        filled = want_qty * self.fill_ratio
        if order.side == "BUY":
            self.cash -= filled * px
            pos = self.positions.setdefault(order.symbol, {"quantity": 0.0, "entry": px})
            total = pos["quantity"] + filled
            pos["entry"] = ((pos["entry"] * pos["quantity"] + px * filled) / total
                            if total else px)
            pos["quantity"] = total
        else:
            self.cash += filled * px
            pos = self.positions[order.symbol]
            pos["quantity"] -= filled
            if pos["quantity"] <= 1e-9:
                del self.positions[order.symbol]

        order.filled_quantity = filled
        order.avg_fill_price = px
        order.to(FILLED if self.fill_ratio >= 1.0 else PARTIALLY_FILLED)
        self.orders[order.client_order_id] = order
        return order

    def cancel_order(self, order_id: str) -> bool:
        for o in self.orders.values():
            if o.broker_order_id == order_id and o.state not in TERMINAL:
                o.to(CANCEL_REQUESTED); o.to(CANCELLED)
                return True
        return False

    def get_order(self, order_id: str) -> dict | None:
        for o in self.orders.values():
            if o.broker_order_id == order_id or o.client_order_id == order_id:
                return {"state": o.state, "filled_quantity": o.filled_quantity,
                        "avg_fill_price": o.avg_fill_price,
                        "broker_order_id": o.broker_order_id}
        return None


class LedgerSimulatedBroker(SimulatedBroker):
    """
    A simulated account that survives restarts (Addendum A I8, B13).

    Cash and positions are REBUILT from the execution engine's own `orders`
    table every time the broker is constructed — filled orders in this `mode`
    whose signal strategy starts with `prefix`. There is no separate state file
    to drift from the ledger, so restart recovery is the constructor.

    Quotes come from an injected provider (quotes.LiveQuotes in production), so
    a simulated fill happens at a live market price during the session — never
    at the stored close of the signal bar, which is look-ahead.
    """

    def __init__(self, conn, capital: float, mode: str, quote_provider,
                 prefix: str = "slot"):
        super().__init__(conn=conn, cash=capital)
        self.provider, self.mode, self.prefix = quote_provider, mode, prefix
        self.replay()

    def replay(self) -> None:
        self.positions = {}
        rows = self.conn.execute(
            "SELECT o.symbol, o.side, o.filled_quantity, o.avg_fill_price FROM orders o "
            "JOIN signals s ON s.signal_id = o.signal_id "
            "WHERE o.mode=? AND s.strategy LIKE ? AND o.filled_quantity > 0 "
            "AND o.avg_fill_price IS NOT NULL ORDER BY o.created_at",
            (self.mode, self.prefix + "%")).fetchall()
        for sym, side, q, px in rows:
            q, px = float(q), float(px)
            if side == "BUY":
                self.cash -= q * px
                p = self.positions.setdefault(sym, {"quantity": 0.0, "entry": px})
                tot = p["quantity"] + q
                p["entry"] = (p["entry"] * p["quantity"] + px * q) / tot if tot else px
                p["quantity"] = tot
            else:
                self.cash += q * px
                p = self.positions.get(sym)
                if p:
                    p["quantity"] -= q
                    if p["quantity"] <= 1e-9:
                        del self.positions[sym]

    def get_quote(self, symbol: str) -> dict | None:
        return self.provider.get(symbol)


class RobinhoodBroker(BrokerInterface):
    """
    Adapter over Robinhood's official Trading MCP.

    Reads are live. `place_order` builds and returns the validated order
    specification and marks it APPROVED; transmitting it over the account's
    authorised MCP connection is an operator step, by design rather than by
    omission. `orders.py --record-fills` then brings the real fill back into the
    database, which is the same reconciliation path the manual loop already uses.

    Constructed with callables so the transport is injected rather than imported.
    That keeps this file free of any particular MCP client and lets the whole
    adapter be tested with fakes.
    """

    def __init__(self, account_number: str, read_fns: dict | None = None):
        self.account = account_number
        self.fns = read_fns or {}

    def _call(self, name: str, *a, **kw):
        fn = self.fns.get(name)
        if fn is None:
            raise NotImplementedError(
                f"{name} is not wired. Provide it via read_fns — this adapter "
                f"deliberately imports no MCP client of its own.")
        return fn(*a, **kw)

    def get_account(self) -> dict:
        return self._call("get_account", self.account)

    def get_positions(self) -> dict:
        return self._call("get_positions", self.account)

    def get_buying_power(self) -> float:
        return float(self._call("get_portfolio", self.account).get("buying_power", 0.0))

    def get_quote(self, symbol: str) -> dict | None:
        return self._call("get_quote", symbol)

    def place_order(self, order: Order) -> Order:
        order.to(SUBMITTING)
        order.to(UNKNOWN, "specification built and approved; transmission is an "
                          "operator step — see docs/ROBINHOOD_AGENTIC.md")
        return order

    def cancel_order(self, order_id: str) -> bool:
        return bool(self._call("cancel_order", self.account, order_id))

    def get_order(self, order_id: str) -> dict | None:
        return self._call("get_order", self.account, order_id)


# ---------------------------------------------------------------------------
# Crypto adapters (Phase 12 item 42)
# ---------------------------------------------------------------------------

CRYPTO_TAKER_FEE = 0.006


class CryptoSimulatedBroker(SimulatedBroker):
    """
    SimulatedBroker for crypto: quotes from `crypto_prices`, fees on every fill.

    Two differences from the equity simulator, each of which matters:

    The quote reads `crypto_prices`, never `prices`. Crypto is kept out of the
    equity table because every consumer of that table assumes US sessions.

    Every fill pays the taker fee on its own notional. The equity simulator
    charges nothing because equity costs live in `costs.py`; for a grid the fee
    IS the result — the backtest beat its null on 10 of 10 pairs before fees
    and 0 of 10 after — so a crypto simulator without them would be
    measuring a different strategy from the one that exists.
    """

    def __init__(self, conn=None, cash: float = 100.0, quotes: dict | None = None,
                 fill_ratio: float = 1.0, interval: str = "1h",
                 fee: float = CRYPTO_TAKER_FEE):
        super().__init__(conn, cash, quotes, fill_ratio)
        self.interval = interval
        self.fee = float(fee)
        self.fees_paid = 0.0

    def get_quote(self, symbol: str) -> dict | None:
        if symbol in self._quotes:
            return self._quotes[symbol]
        if self.conn is None:
            return None
        r = self.conn.execute(
            "SELECT open_time, close FROM crypto_prices WHERE symbol=? AND "
            "interval=? AND close>0 ORDER BY open_time DESC LIMIT 1",
            (symbol, self.interval)).fetchone()
        if not r:
            return None
        # 20-day USD turnover, on the quote rather than looked up by the risk
        # engine — the equity side learned that a quote missing liquidity is a
        # quote that blocks every order.
        since = int(r[0]) - 20 * 86400
        dv = self.conn.execute(
            "SELECT SUM(volume * close) FROM crypto_prices WHERE symbol=? AND "
            "interval=? AND open_time > ?", (symbol, self.interval, since)).fetchone()
        return {"symbol": symbol, "price": float(r[1]), "as_of": int(r[0]),
                "dollar_volume_20": (float(dv[0]) / 20.0) if dv and dv[0] else None,
                "market_cap": None}

    def place_order(self, order: Order) -> Order:
        before = self.cash
        order = super().place_order(order)
        if order.state in (FILLED, PARTIALLY_FILLED) and order.filled_quantity:
            fee = self.fee * order.filled_quantity * (order.avg_fill_price or 0.0)
            self.cash -= fee
            self.fees_paid += fee
            order.note = (getattr(order, "note", "") or "") + f" fee ${fee:,.4f}"
        return order


class CoinbaseBroker(BrokerInterface):
    """
    Adapter for Coinbase, built to the same contract as RobinhoodBroker.

    Reads are injected as callables so the transport is not imported here and the
    whole adapter can be tested with fakes. `place_order` builds the validated
    order specification and leaves it in UNKNOWN pending transmission, which is
    the operator step on this project for equities and crypto alike;
    `crypto_orders.py` then records what actually filled.
    """

    def __init__(self, read_fns: dict | None = None):
        self.fns = read_fns or {}

    def _call(self, name: str, *a, **kw):
        fn = self.fns.get(name)
        if fn is None:
            raise NotImplementedError(
                f"{name} is not wired. Provide it via read_fns — this adapter "
                f"deliberately imports no exchange client of its own.")
        return fn(*a, **kw)

    def get_account(self) -> dict:
        return self._call("get_account")

    def get_positions(self) -> dict:
        return self._call("get_positions")

    def get_buying_power(self) -> float:
        return float(self._call("get_buying_power"))

    def get_quote(self, symbol: str) -> dict | None:
        return self._call("get_quote", symbol)

    def place_order(self, order: Order) -> Order:
        order.to(SUBMITTING)
        order.to(UNKNOWN, "specification built and approved; transmission is an "
                          "operator step — see docs/PHASE12_CRYPTO_FUND.md")
        return order

    def cancel_order(self, order_id: str) -> bool:
        return bool(self._call("cancel_order", order_id))

    def get_order(self, order_id: str) -> dict | None:
        return self._call("get_order", order_id)
