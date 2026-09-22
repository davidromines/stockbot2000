"""
The signal: the only thing the execution engine will accept. Phase 3.

WHY A SCHEMA AND NOT A DICT
---------------------------
Everything upstream of here — five conviction screens, an evolved genome, an
XGBoost classifier, five ETF switchers — produces a different shape. The
execution engine must not know or care which. A single validated object is the
seam: upstream may be rewritten freely, and downstream only ever sees this.

**Free-form text never reaches execution.** A natural-language instruction is
converted into a validated Signal first, or it is rejected. The engine takes
structured input only, so there is no path where a sentence becomes an order.

WHY signal_id IS THE IDEMPOTENCY KEY
------------------------------------
It is derived from the content that defines the trade — strategy, symbol,
action, and the session it was generated for — not from a timestamp or a random
value. So the same decision, generated twice by a re-run or a retry after a
crash, produces the SAME id and the execution engine can recognise it as one
order rather than two. A random id would make every retry a new trade, which is
the exact failure this project must not have with real money.

Deliberately NOT here: prices to trade at, order types, routing. A signal says
what the strategy concluded. How that becomes an order is the execution engine's
business, and mixing the two is how a strategy ends up silently deciding
execution policy.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import hashlib
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("signals")

ACTIONS = ("BUY", "SELL", "HOLD", "CLOSE")
ASSET_TYPES = ("equity", "option", "crypto")


class SignalError(ValueError):
    """Raised when a signal is malformed. Never swallowed — a bad signal is a bug."""


@dataclass
class Signal:
    symbol: str
    action: str
    strategy: str
    reason: str
    asset_type: str = "equity"
    quantity: float | None = None
    notional_value: float | None = None
    confidence: float = 0.0
    expected_edge: float = 0.0
    session: str = ""                 # the trading date this was generated FOR
    timestamp: str = field(default_factory=lambda:
                           datetime.now(timezone.utc).isoformat())
    expiration: str | None = None
    signal_id: str = ""

    def __post_init__(self):
        self.symbol = str(self.symbol).upper().strip()
        self.action = str(self.action).upper().strip()
        if not self.signal_id:
            self.signal_id = self.derive_id()

    def derive_id(self) -> str:
        """
        Content-addressed id. The same decision always hashes to the same value.

        `session` is in the hash and `timestamp` is not, deliberately: two runs
        of the same morning's book must collide, while the same strategy firing
        on a different day must not.
        """
        basis = f"{self.strategy}|{self.symbol}|{self.action}|{self.asset_type}|{self.session}"
        return hashlib.sha256(basis.encode()).hexdigest()[:24]

    def validate(self) -> None:
        if not self.symbol or len(self.symbol) > 12:
            raise SignalError(f"bad symbol: {self.symbol!r}")
        if self.action not in ACTIONS:
            raise SignalError(f"action must be one of {ACTIONS}, got {self.action!r}")
        if self.asset_type not in ASSET_TYPES:
            raise SignalError(f"asset_type must be one of {ASSET_TYPES}")
        if not self.strategy:
            raise SignalError("strategy is required — an unattributable order "
                              "cannot be reviewed or switched off later")
        if not self.reason:
            raise SignalError("reason is required — see strategy")
        if not 0.0 <= self.confidence <= 1.0:
            raise SignalError(f"confidence out of range: {self.confidence}")
        if self.action in ("BUY", "SELL"):
            has_qty = self.quantity is not None and self.quantity > 0
            has_notional = self.notional_value is not None and self.notional_value > 0
            if not (has_qty or has_notional):
                raise SignalError(f"{self.action} needs a positive quantity or "
                                  f"notional_value")
            # Both is ambiguous, not generous: the engine would have to guess
            # which one the strategy meant, and a wrong guess is a wrong size.
            if has_qty and has_notional:
                raise SignalError("specify quantity OR notional_value, not both")

    def is_actionable(self) -> bool:
        """HOLD is a real answer and must be recorded, but it places no order."""
        return self.action in ("BUY", "SELL", "CLOSE")

    def to_dict(self) -> dict:
        return asdict(self)

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)


def from_dict(d: dict) -> Signal:
    known = {f for f in Signal.__dataclass_fields__}
    unknown = set(d) - known
    if unknown:
        # Silently dropping a field is how a typo'd "quantitiy" becomes a
        # zero-sized order that nobody can explain afterwards.
        raise SignalError(f"unknown signal fields: {sorted(unknown)}")
    s = Signal(**{k: v for k, v in d.items() if k in known})
    s.validate()
    return s


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS signals (
            signal_id      TEXT PRIMARY KEY,
            created_at     TEXT NOT NULL,
            session        TEXT NOT NULL,
            symbol         TEXT NOT NULL,
            asset_type     TEXT NOT NULL,
            action         TEXT NOT NULL,
            quantity       REAL,
            notional_value REAL,
            confidence     REAL NOT NULL DEFAULT 0,
            expected_edge  REAL NOT NULL DEFAULT 0,
            strategy       TEXT NOT NULL,
            reason         TEXT NOT NULL,
            expiration     TEXT,
            payload        TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_signals_session ON signals(session)")
    conn.commit()


def record(conn, sig: Signal) -> bool:
    """
    Persist a signal. Returns False if this exact signal was already stored.

    INSERT OR IGNORE rather than REPLACE: a signal is an immutable record of a
    decision. Overwriting one would rewrite history, and the audit trail is the
    point of storing it at all.
    """
    sig.validate()
    init(conn)
    cur = conn.execute("""
        INSERT OR IGNORE INTO signals (signal_id, created_at, session, symbol,
            asset_type, action, quantity, notional_value, confidence,
            expected_edge, strategy, reason, expiration, payload)
        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (sig.signal_id, sig.timestamp, sig.session, sig.symbol, sig.asset_type,
         sig.action, sig.quantity, sig.notional_value, sig.confidence,
         sig.expected_edge, sig.strategy, sig.reason, sig.expiration,
         sig.to_json()))
    conn.commit()
    return cur.rowcount > 0
