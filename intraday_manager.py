"""
Intraday Momentum Runner (Addendum G), M2: the live position manager as a state machine.

It owns ONE thing: given a quote, what should happen to an open intraday position, and how a failed exit is handled.
It talks to the world only through a `broker` object with two methods and an `alert` callback, so the real wiring
(ExecutionEngine / LiveBroker, Telegram) is a thin adapter and every failure path is testable with a fake:

    broker.submit_sell(symbol, qty, ref_id) -> {"status": "FILLED"|"PARTIAL"|"REJECTED"|"PENDING",
                                               "filled_qty": float, "avg_price": float|None, "reason": str}
    broker.order_status(ref_id)             -> the same shape, or None when the broker has no such order

Rules (plan R2.6):
  * trailing/initial stop, maximum hold and the New-York-time flatten decide WHEN to exit (intraday_stops);
  * monitoring health: no usable quote for `halt_after_s` -> new entries halt (flag + alert); for `exit_after_s` -> exit at market;
  * a failed exit is never treated as a success. Before any retry the previous order is reconciled with the broker;
    a second sell is only sent when the first is known to be terminal (rejected / cancelled / unknown to the broker);
    a partial fill reduces the quantity still to sell; after `max_attempts` sells the position is ESCALATED and the owner alerted;
  * every sell reference is deterministic (symbol, fill time, attempt number), so a retry after a restart cannot create
    a duplicate order;
  * the state serialises to JSON; `restore` + `rebuild` recover it after a restart with the position still open.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta

import intraday_stops as st

OPEN, EXITING, CLOSED, ESCALATED = "OPEN", "EXITING", "CLOSED", "ESCALATED"
EPS = 1e-9


@dataclass
class Position:
    symbol: str
    qty: float
    entry_price: float
    fill_time: str                       # ISO, tz-aware
    status: str = OPEN
    highest: float = 0.0
    stop: float = 0.0
    exit_reason: str | None = None
    exit_ref: str | None = None
    attempts: int = 0
    exited_qty: float = 0.0
    proceeds: float = 0.0
    seen: dict = field(default_factory=dict)      # filled quantity already booked, per order reference
    last_good_quote: str | None = None            # ISO of the newest usable quote
    entries_halted: bool = False
    log: list = field(default_factory=list)

    @property
    def remaining(self) -> float:
        return max(0.0, self.qty - self.exited_qty)


class Manager:
    def __init__(self, broker, cfg: st.StopConfig, alert=None, halt_after_s: int = 30, exit_after_s: int = 90,
                 max_attempts: int = 3, max_quote_age_s: int = 20):
        self.broker, self.cfg, self.alert = broker, cfg, alert or (lambda msg: None)
        self.halt_after_s, self.exit_after_s = halt_after_s, exit_after_s
        self.max_attempts, self.max_quote_age_s = max_attempts, max_quote_age_s

    # --- construction / persistence ----------------------------------------------------------------------------
    def open(self, symbol: str, qty: float, entry_price: float, fill_time: datetime) -> Position:
        ts = st.TrailingStop(entry_price, fill_time, self.cfg)
        return Position(symbol, qty, entry_price, fill_time.isoformat(), highest=ts.highest, stop=ts.stop_price,
                        last_good_quote=fill_time.isoformat())

    @staticmethod
    def snapshot(pos: Position) -> dict:
        return asdict(pos)

    @staticmethod
    def restore(d: dict) -> Position:
        return Position(**d)

    def rebuild(self, pos: Position, bars) -> Position:
        """After a restart: re-derive highest and stop from the stored bars since the fill ((bar_start, high) pairs).
        The stop is a monotone function of the eligible highs, so this equals the state before the restart."""
        ts = st.rebuild(pos.entry_price, datetime.fromisoformat(pos.fill_time), self.cfg, bars)
        pos.highest, pos.stop = max(pos.highest, ts.highest), max(pos.stop, ts.stop_price)
        return pos

    # --- the decision -----------------------------------------------------------------------------------------
    def tick(self, pos: Position, price: float | None, quote_ts: datetime | None, now: datetime) -> Position:
        if pos.status in (CLOSED, ESCALATED):
            return pos
        if pos.status == EXITING:                                     # reconcile the working order first
            return self._exit(pos, pos.exit_reason or "exit")
        good = price is not None and quote_ts is not None and (now - quote_ts).total_seconds() <= self.max_quote_age_s
        if not good:
            silent = (now - datetime.fromisoformat(pos.last_good_quote)).total_seconds()
            if silent >= self.exit_after_s:
                return self._exit(pos, "monitoring lost")
            if silent >= self.halt_after_s and not pos.entries_halted:
                pos.entries_halted = True
                self.alert(f"{pos.symbol}: no usable quote for {silent:.0f}s - new intraday entries halted")
            return pos
        pos.last_good_quote, pos.entries_halted = quote_ts.isoformat(), False
        fill = datetime.fromisoformat(pos.fill_time)
        ts = st.TrailingStop(pos.entry_price, fill, self.cfg)
        ts.highest, ts._stop = pos.highest, pos.stop                  # restore the monotone state, then observe
        ts.observe(price, quote_ts)
        pos.highest, pos.stop = ts.highest, ts.stop_price
        if now >= st.flatten_at(now.astimezone(st.NY).date(), self.cfg):
            return self._exit(pos, "end-of-session flatten")
        if self.cfg.max_hold_minutes and now - fill >= timedelta(minutes=self.cfg.max_hold_minutes):
            return self._exit(pos, "maximum holding time")
        if ts.breached(price):
            return self._exit(pos, ts.reason())
        return pos

    # --- the exit, with reconciliation -----------------------------------------------------------------------
    def _book(self, pos: Position, r: dict) -> None:
        q = float(r.get("filled_qty") or 0.0)
        new = max(0.0, q - pos.seen.get(pos.exit_ref, 0.0))
        if new > 0:
            pos.exited_qty += new
            pos.proceeds += new * float(r.get("avg_price") or 0.0)
            pos.seen[pos.exit_ref] = q

    def _exit(self, pos: Position, reason: str) -> Position:
        pos.exit_reason = pos.exit_reason or reason
        if pos.exit_ref:                                              # an order exists: reconcile before anything else
            r = self.broker.order_status(pos.exit_ref) or {"status": "NOT_FOUND", "filled_qty": 0.0}
            self._book(pos, r)
            if pos.remaining <= EPS:
                pos.status = CLOSED
                pos.log.append(f"closed: {pos.exit_reason}")
                return pos
            if r["status"] in ("PENDING", "PARTIAL"):                 # still working at the broker: wait, never double-sell
                pos.status = EXITING
                return pos
            # terminal (rejected, cancelled, unknown) with quantity left: the remainder is resent below
        if pos.attempts >= self.max_attempts:
            if pos.status != ESCALATED:
                pos.status = ESCALATED
                self.alert(f"{pos.symbol}: exit failed after {pos.attempts} attempts ({pos.exit_reason}); "
                           f"{pos.remaining:.6f} still held - needs manual attention")
            return pos
        pos.attempts += 1
        pos.exit_ref = f"x-{pos.symbol}-{pos.fill_time}-{pos.attempts}"
        r = self.broker.submit_sell(pos.symbol, pos.remaining, pos.exit_ref)
        self._book(pos, r)
        pos.status = CLOSED if pos.remaining <= EPS else EXITING
        if r.get("status") == "REJECTED":
            pos.log.append(f"rejected ({pos.attempts}): {r.get('reason')}")
        return pos
