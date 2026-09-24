"""
The execution engine: the only path from signal to broker. Phases 6, 7, 9, 10.

THE SEQUENCE, AND WHY IT IS THIS ORDER
---------------------------------------
  1. kill switches      cheapest and most authoritative; nothing else matters
                        if trading is halted
  2. duplicate check    before any work, so a retry costs nothing and cannot
                        half-execute
  3. quote              needed to size, and its absence is a rejection
  4. risk validation    the only sizing authority
  5. build the order    from the risk engine's size, never the signal's request
  6. submit             through the broker interface
  7. reconcile          ask the broker what actually happened
  8. record             every step, whatever the outcome

Each step can reject. A rejection is recorded with its reasons and the engine
returns — it never falls through to the next step "just in case".

IDEMPOTENCY IS THE LOAD-BEARING PROPERTY
-----------------------------------------
`client_order_id` is the signal id, which is content-addressed over the
decision. Submitting the same decision twice collides on the orders table's
primary key and returns the original order. This is checked in three places —
the engine, the database and the simulated broker — because a duplicate order
with real money is the failure that cannot be undone by a later fix.

UNKNOWN IS NOT A FAILURE TO RETRY
----------------------------------
If submission returns UNKNOWN, the engine does NOT resubmit. It queries the
broker for the order and resolves the real state. Blind retry on UNKNOWN is how
one intended trade becomes two, and the whole point of an explicit state machine
is to make that impossible to do by accident.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import logging
from datetime import datetime, timezone

import broker as bk
import killswitch as ks
import signals as sg

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("exec")


def init(conn) -> None:
    sg.init(conn)
    ks.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders (
            client_order_id TEXT PRIMARY KEY,
            signal_id       TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            session         TEXT NOT NULL,
            symbol          TEXT NOT NULL,
            side            TEXT NOT NULL,
            asset_type      TEXT NOT NULL DEFAULT 'equity',
            notional        REAL,
            quantity        REAL,
            state           TEXT NOT NULL,
            broker_order_id TEXT,
            filled_quantity REAL NOT NULL DEFAULT 0,
            avg_fill_price  REAL,
            mode            TEXT NOT NULL,
            note            TEXT
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS fills (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            client_order_id TEXT NOT NULL,
            at              TEXT NOT NULL,
            quantity        REAL NOT NULL,
            price           REAL NOT NULL,
            state           TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_orders_session ON orders(session)")
    conn.commit()


def _log_json(event: str, **kw) -> None:
    """Structured line per event. Never carries credentials — none pass through here."""
    log.info(json.dumps({"event": event,
                         "at": datetime.now(timezone.utc).isoformat(), **kw},
                        default=str))


def _record_risk(conn, sig, decision: str, reasons: list) -> None:
    conn.execute("INSERT INTO risk_events (at, signal_id, symbol, decision, reasons) "
                 "VALUES (?,?,?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), sig.signal_id, sig.symbol,
                  decision, json.dumps(reasons)))
    conn.commit()


def _save_order(conn, o: bk.Order, session: str, mode: str) -> None:
    conn.execute("""
        INSERT INTO orders (client_order_id, signal_id, created_at, session, symbol,
            side, asset_type, notional, quantity, state, broker_order_id,
            filled_quantity, avg_fill_price, mode, note)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
        ON CONFLICT(client_order_id) DO UPDATE SET
            state=excluded.state, broker_order_id=excluded.broker_order_id,
            filled_quantity=excluded.filled_quantity,
            avg_fill_price=excluded.avg_fill_price, note=excluded.note""",
        (o.client_order_id, o.signal_id, o.created_at, session, o.symbol, o.side,
         o.asset_type, o.notional, o.quantity, o.state, o.broker_order_id,
         o.filled_quantity, o.avg_fill_price, mode, o.note))
    if o.filled_quantity and o.avg_fill_price:
        conn.execute("INSERT INTO fills (client_order_id, at, quantity, price, state) "
                     "VALUES (?,?,?,?,?)",
                     (o.client_order_id, datetime.now(timezone.utc).isoformat(),
                      o.filled_quantity, o.avg_fill_price, o.state))
    conn.commit()


def already_submitted(conn, signal_id: str) -> dict | None:
    r = conn.execute("SELECT * FROM orders WHERE client_order_id=?", (signal_id,)).fetchone()
    return dict(r) if r else None


def is_emergency_exit(sig) -> bool:
    """An exit issued under the emergency policy (Addendum A §25)."""
    return sig.action == "CLOSE" and str(sig.strategy).endswith(":EMERGENCY")


class ExecutionEngine:
    def __init__(self, conn, broker: bk.BrokerInterface, risk_engine,
                 mode: str = "SIMULATION", session: str = ""):
        if mode not in ("SIMULATION", "SHADOW", "LIVE"):
            raise ValueError(f"unknown mode {mode!r}")
        self.conn = conn
        self.broker = broker
        self.risk = risk_engine
        self.mode = mode
        self.session = session or datetime.now(timezone.utc).date().isoformat()
        self.errors = 0
        init(conn)

    # -- portfolio snapshot handed to risk and the kill switches -------------

    def snapshot(self) -> dict | None:
        try:
            acct = self.broker.get_account()
            pos = self.broker.get_positions()
            snap = {"equity": float(acct.get("equity") or 0),
                    "buying_power": float(self.broker.get_buying_power() or 0),
                    "daily_pnl": float(acct.get("daily_pnl") or 0),
                    "drawdown_percent": float(acct.get("drawdown_percent") or 0),
                    "positions": pos}
            # Settled cash / day-trade count for the account-rule guard (I12),
            # from this engine's own orders in this mode.
            import account_rules
            return account_rules.annotate(self.conn, snap, self.risk.L, self.session[:10], self.mode)
        except Exception as e:      # noqa: BLE001 — unreadable state must halt, not raise
            log.error(f"portfolio snapshot failed: {type(e).__name__}: {e}")
            return None

    def _counts(self, symbol: str) -> dict:
        row = self.conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE session=? AND state NOT IN "
            "('REJECTED','FAILED')", (self.session,)).fetchone()
        per = self.conn.execute(
            "SELECT COUNT(*) AS n FROM orders WHERE session=? AND symbol=? AND "
            "state NOT IN ('REJECTED','FAILED')", (self.session, symbol)).fetchone()
        return {"orders_today": row["n"], "orders_for_symbol": per["n"]}

    def _emergency_exit(self, sig, portfolio: dict, halt_reasons: list) -> dict:
        """
        Close a position while trading is halted (§25: "exit positions according
        to emergency policy"). The one thing a halt does not block: a switch
        that also prevents getting OUT traps the account in the condition it
        tripped on. Sized from what is held, never more; no entry is possible
        on this path.
        """
        held = (portfolio.get("positions") or {}).get(sig.symbol)
        qty = float((held or {}).get("quantity") or sig.quantity or 0)
        if qty <= 0:
            _record_risk(self.conn, sig, "REJECTED", ["emergency exit: nothing held"])
            return {"status": "rejected", "signal_id": sig.signal_id, "reasons": ["nothing held"]}
        prior = already_submitted(self.conn, sig.signal_id)
        if prior:
            return {"status": "duplicate", "signal_id": sig.signal_id, "order": prior,
                    "reasons": ["this decision already produced an order"]}
        _record_risk(self.conn, sig, "EMERGENCY_EXIT", halt_reasons)
        order = bk.Order(signal_id=sig.signal_id, symbol=sig.symbol, side="SELL",
                         asset_type=sig.asset_type, notional=None, quantity=qty)
        order.to(bk.VALIDATING); order.to(bk.APPROVED)
        _save_order(self.conn, order, self.session, self.mode)
        if self.mode == "SHADOW":
            return {"status": "shadow", "signal_id": sig.signal_id, "order": order}
        try:
            order = self.broker.place_order(order)
        except Exception as e:      # noqa: BLE001
            order.state, order.note = bk.FAILED, f"{type(e).__name__}: {e}"
        _save_order(self.conn, order, self.session, self.mode)
        _log_json("EMERGENCY_EXIT", signal_id=sig.signal_id, symbol=sig.symbol,
                  state=order.state, reasons=halt_reasons)
        return {"status": order.state.lower(), "signal_id": sig.signal_id, "order": order}

    # -- the one public entry point -----------------------------------------

    def execute(self, sig: sg.Signal, reconciled: bool | None = None) -> dict:
        sig.session = sig.session or self.session
        sg.record(self.conn, sig)
        _log_json("SIGNAL_RECEIVED", signal_id=sig.signal_id, symbol=sig.symbol,
                  action=sig.action, strategy=sig.strategy, mode=self.mode)

        if not sig.is_actionable():
            return {"status": "no_action", "signal_id": sig.signal_id,
                    "reasons": [f"{sig.action} places no order"]}

        # 1. kill switches, before any work
        portfolio = self.snapshot()
        verdict = ks.check(self.conn, portfolio, self.risk.L,
                           recent_errors=self.errors, reconciled=reconciled)
        if not verdict.trading_allowed and is_emergency_exit(sig) and portfolio is not None:
            return self._emergency_exit(sig, portfolio, verdict.reasons)
        if not verdict.trading_allowed:
            _record_risk(self.conn, sig, "HALTED", verdict.reasons)
            _log_json("TRADING_HALTED", signal_id=sig.signal_id, reasons=verdict.reasons)
            return {"status": "halted", "signal_id": sig.signal_id,
                    "reasons": verdict.reasons}

        # 2. duplicate check, before anything can half-execute
        prior = already_submitted(self.conn, sig.signal_id)
        if prior:
            _log_json("DUPLICATE_SUPPRESSED", signal_id=sig.signal_id,
                      existing_state=prior["state"])
            return {"status": "duplicate", "signal_id": sig.signal_id,
                    "order": prior, "reasons": ["this decision already produced an order"]}

        # 3. quote
        quote = None
        try:
            quote = self.broker.get_quote(sig.symbol)
        except Exception as e:      # noqa: BLE001
            log.error(f"quote failed for {sig.symbol}: {type(e).__name__}")

        # 4. risk
        rr = self.risk.validate(sig, portfolio, quote, self._counts(sig.symbol))
        if not rr.approved:
            _record_risk(self.conn, sig, "REJECTED", rr.reasons)
            _log_json("ORDER_REJECTED", signal_id=sig.signal_id, symbol=sig.symbol,
                      reasons=rr.reasons)
            return {"status": "rejected", "signal_id": sig.signal_id,
                    "reasons": rr.reasons}
        _record_risk(self.conn, sig, "APPROVED", [])

        # 5. build from the RISK ENGINE's size, never the signal's request
        side = "BUY" if sig.action == "BUY" else "SELL"
        order = bk.Order(signal_id=sig.signal_id, symbol=sig.symbol, side=side,
                         asset_type=sig.asset_type,
                         notional=rr.sized_notional,
                         quantity=rr.sized_quantity if side == "SELL" else None)
        order.to(bk.VALIDATING); order.to(bk.APPROVED)
        _save_order(self.conn, order, self.session, self.mode)

        # SHADOW stops here: real data, real risk, no order.
        if self.mode == "SHADOW":
            _log_json("SHADOW_ORDER", signal_id=sig.signal_id, symbol=sig.symbol,
                      side=side, notional=order.notional)
            return {"status": "shadow", "signal_id": sig.signal_id, "order": order}

        # 6. submit
        try:
            order = self.broker.place_order(order)
            self.errors = 0
        except Exception as e:      # noqa: BLE001
            self.errors += 1
            order.state = bk.FAILED
            order.note = f"{type(e).__name__}: {e}"
            _save_order(self.conn, order, self.session, self.mode)
            _log_json("ORDER_FAILED", signal_id=sig.signal_id, error=order.note)
            return {"status": "failed", "signal_id": sig.signal_id,
                    "reasons": [order.note]}

        # 7. UNKNOWN is resolved by asking, never by resubmitting
        if order.state == bk.UNKNOWN:
            resolved = None
            try:
                resolved = self.broker.get_order(order.broker_order_id
                                                 or order.client_order_id)
            except Exception:       # noqa: BLE001
                pass
            if resolved and resolved.get("state"):
                order.state = resolved["state"]
                order.filled_quantity = float(resolved.get("filled_quantity") or 0)
                order.avg_fill_price = resolved.get("avg_fill_price")
                _log_json("UNKNOWN_RESOLVED", signal_id=sig.signal_id,
                          state=order.state)
            else:
                _log_json("UNKNOWN_UNRESOLVED", signal_id=sig.signal_id,
                          note="left UNKNOWN deliberately; NOT resubmitted")

        _save_order(self.conn, order, self.session, self.mode)
        _log_json("ORDER_" + order.state, signal_id=sig.signal_id, symbol=sig.symbol,
                  side=side, notional=order.notional,
                  filled=order.filled_quantity, price=order.avg_fill_price,
                  broker_order_id=order.broker_order_id, mode=self.mode)
        return {"status": order.state.lower(), "signal_id": sig.signal_id,
                "order": order}
