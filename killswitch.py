"""
Six ways to stop trading, and one rule: when uncertain, do not trade. Phase 5.

WHY SIX AND NOT ONE
-------------------
They fail in different ways and at different times. A file on disk works when
the database is unreachable. A daily-loss check works when nobody is watching.
An error-rate trip works when the broker is up but answering wrongly. A single
switch would have a single failure mode; these overlap on purpose.

FAIL CLOSED IS THE WHOLE DESIGN
--------------------------------
Every check here returns "halt" when it cannot determine the answer. An
unreadable state file halts. A portfolio that could not be fetched halts. A
reconciliation that did not run halts. The alternative — treating "I don't know"
as "carry on" — is how a system keeps trading through exactly the conditions the
switches exist to catch.

THE FILE SWITCH IS THE ONE THAT MATTERS
----------------------------------------
`data/KILL_SWITCH` stops everything, immediately, with no code running and no
database needed. `touch data/KILL_SWITCH` from any shell. It is checked first,
before anything that could itself fail, so a broken system can still be stopped
by a human with a keyboard.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("killswitch")

KILL_FILE = Path("data/KILL_SWITCH")
STATE_TABLE = "system_events"


@dataclass
class Verdict:
    trading_allowed: bool
    reasons: list

    def halt(self, why: str) -> "Verdict":
        self.trading_allowed = False
        self.reasons.append(why)
        return self


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS system_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            at         TEXT NOT NULL,
            kind       TEXT NOT NULL,
            detail     TEXT NOT NULL,
            severity   TEXT NOT NULL DEFAULT 'info'
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS risk_events (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            at         TEXT NOT NULL,
            signal_id  TEXT,
            symbol     TEXT,
            decision   TEXT NOT NULL,
            reasons    TEXT NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_sysev_kind ON system_events(kind)")
    conn.commit()


def record_event(conn, kind: str, detail: str, severity: str = "info") -> None:
    init(conn)
    conn.execute("INSERT INTO system_events (at, kind, detail, severity) VALUES (?,?,?,?)",
                 (datetime.now(timezone.utc).isoformat(), kind, detail, severity))
    conn.commit()


def engage(conn=None, why: str = "manual") -> None:
    """Trip the file switch. Deliberately trivial: it must work when nothing else does."""
    KILL_FILE.parent.mkdir(parents=True, exist_ok=True)
    KILL_FILE.write_text(f"{datetime.now(timezone.utc).isoformat()}\n{why}\n")
    log.warning(f"KILL SWITCH ENGAGED: {why}")
    if conn is not None:
        record_event(conn, "kill_switch_engaged", why, "critical")


def release(conn=None, who: str = "manual") -> bool:
    """
    Clear the file switch. Never automatic.

    Nothing in this system releases a kill switch on its own. A switch that
    resets itself is a delay, not a stop, and the conditions that trip these are
    exactly the ones where an automatic retry does the most damage.
    """
    if not KILL_FILE.exists():
        return False
    KILL_FILE.unlink()
    log.warning(f"kill switch released by {who}")
    if conn is not None:
        record_event(conn, "kill_switch_released", who, "warning")
    return True


def check(conn, portfolio: dict | None, limits: dict,
          recent_errors: int = 0, reconciled: bool | None = None) -> Verdict:
    """
    Every switch, in order of how reliably each can be evaluated.

    The file switch is first because it needs nothing. The database switch is
    next. The state-dependent ones come last, because they are the ones that can
    themselves fail — and when they do, they halt.
    """
    v = Verdict(trading_allowed=True, reasons=[])

    # 1. the file switch — works with no database and no network
    if KILL_FILE.exists():
        try:
            detail = KILL_FILE.read_text().strip().splitlines()[-1]
        except Exception:
            detail = "unreadable"
        return v.halt(f"KILL_SWITCH file present ({detail})")

    # 2. the environment switch — how a scheduler or operator disables a run
    if os.environ.get("TRADING_ENABLED", "true").strip().lower() in ("false", "0", "no"):
        v.halt("TRADING_ENABLED is false")

    # 3. portfolio-dependent switches. Unreadable state halts rather than passes.
    if portfolio is None:
        return v.halt("portfolio state unavailable — cannot evaluate loss limits")

    eq = float(portfolio.get("equity") or 0)
    dl = float(portfolio.get("daily_pnl") or 0)
    cap_usd = float(limits.get("max_daily_loss_dollars", 0) or 0)
    if cap_usd and dl <= -abs(cap_usd):
        v.halt(f"daily loss ${dl:,.2f} breaches ${cap_usd:,.2f}")
    cap_pct = float(limits.get("max_daily_loss_percent", 0) or 0)
    if cap_pct and eq > 0 and (dl / eq * 100) <= -abs(cap_pct):
        v.halt(f"daily loss {dl / eq * 100:.1f}% breaches {cap_pct:.1f}%")

    dd = float(portfolio.get("drawdown_percent") or 0)
    cap_dd = float(limits.get("max_drawdown_percent", 0) or 0)
    if cap_dd and dd >= abs(cap_dd):
        v.halt(f"drawdown {dd:.1f}% breaches {cap_dd:.1f}%")

    # 4. error rate — the broker is reachable but answering wrongly
    if recent_errors >= int(limits.get("max_consecutive_errors", 3)):
        v.halt(f"{recent_errors} consecutive execution errors")

    # 5. reconciliation. None means it never ran, which is NOT the same as
    #    passing — and is treated as a halt for exactly that reason.
    if reconciled is None:
        v.halt("positions not reconciled this session")
    elif reconciled is False:
        v.halt("internal state disagrees with the broker")

    return v


def global_engaged() -> str | None:
    """Why trading is globally stopped by an operator switch, or None."""
    if KILL_FILE.exists():
        try:
            return KILL_FILE.read_text().strip().splitlines()[-1]
        except Exception:
            return "unreadable"
    if os.environ.get("TRADING_ENABLED", "true").strip().lower() in ("false", "0", "no"):
        return "TRADING_ENABLED is false"
    return None


def emergency_policy(limits: dict) -> str:
    """'flatten' (close every slot position) or 'hold' (stop new orders only)."""
    p = str(limits.get("emergency_policy", "flatten")).lower()
    return p if p in ("flatten", "hold") else "flatten"


# --- per-strategy switches (Addendum A §25, B13) ------------------------------
# A strategy can be stopped without stopping the account. State is an
# append-only log, never a flag column: the latest ENGAGE/RELEASE row for a key
# decides, so who stopped a strategy, when and why is never overwritten. Like
# the global switch, nothing here releases a strategy on its own.

def _init_strategy(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS strategy_kills (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            at           TEXT NOT NULL,
            strategy_key TEXT NOT NULL,
            action       TEXT NOT NULL CHECK (action IN ('ENGAGE','RELEASE')),
            reason       TEXT NOT NULL,
            actor        TEXT NOT NULL
        )""")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_skill_key ON strategy_kills(strategy_key)")


def engage_strategy(conn, strategy_key: str, why: str, actor: str = "manual") -> None:
    """Stop one strategy: it may hold no slot and place no new entry."""
    if not why:
        raise ValueError("a strategy kill needs a reason")
    _init_strategy(conn)
    conn.execute("INSERT INTO strategy_kills (at, strategy_key, action, reason, actor) "
                 "VALUES (?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), strategy_key,
                                        "ENGAGE", why, actor))
    conn.commit()
    record_event(conn, "strategy_kill_engaged", f"{strategy_key}: {why}", "warning")


def release_strategy(conn, strategy_key: str, who: str = "manual") -> bool:
    """Release a strategy switch. Never called automatically."""
    if strategy_halted(conn, strategy_key) is None:
        return False
    conn.execute("INSERT INTO strategy_kills (at, strategy_key, action, reason, actor) "
                 "VALUES (?,?,?,?,?)", (datetime.now(timezone.utc).isoformat(), strategy_key,
                                        "RELEASE", "released", who))
    conn.commit()
    record_event(conn, "strategy_kill_released", f"{strategy_key} by {who}", "warning")
    return True


def strategy_halted(conn, strategy_key: str) -> str | None:
    """The engage reason if this strategy is stopped, else None."""
    _init_strategy(conn)
    r = conn.execute("SELECT action, reason FROM strategy_kills WHERE strategy_key=? "
                     "ORDER BY id DESC LIMIT 1", (strategy_key,)).fetchone()
    return r[1] if r and r[0] == "ENGAGE" else None


def status_line(v: Verdict) -> str:
    if v.trading_allowed:
        return "TRADING ENABLED — all kill switches clear"
    return "TRADING HALTED — " + "; ".join(v.reasons)
