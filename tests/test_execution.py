"""
End to end: signal -> risk -> order -> fill -> position, plus the failure paths.

The failure paths are the reason this file exists. A happy-path test proves the
system can trade; these prove it cannot trade TWICE, cannot trade while halted,
and does not resubmit an order whose fate it does not know. Those are the three
ways an execution engine loses real money that a strategy never would.

Run:  PYTHONPATH=. venv/bin/python tests/test_execution.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile
from pathlib import Path

import broker as bk
import execution as ex
import killswitch as ks
from risk_engine import RiskEngine, load_limits
from signals import Signal

ks.KILL_FILE = Path(tempfile.mktemp(suffix=".KILL"))
LIMITS = load_limits()
QUOTES = {"AAPL": {"symbol": "AAPL", "price": 50.0,
                   "dollar_volume_20": 20_000_000.0, "market_cap": 5e9},
          "TNON": {"symbol": "TNON", "price": 5.54,
                   "dollar_volume_20": 102_000_000.0, "market_cap": 3.5e6}}

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


def fresh(cash=100.0, fill_ratio=1.0):
    conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
    conn.row_factory = sqlite3.Row
    b = bk.SimulatedBroker(cash=cash, quotes=QUOTES, fill_ratio=fill_ratio)
    e = ex.ExecutionEngine(conn, b, RiskEngine(LIMITS), mode="SIMULATION",
                           session="2026-09-22")
    return conn, b, e


def sig(**kw):
    base = dict(symbol="AAPL", action="BUY", strategy="test", reason="unit test",
                notional_value=20.0, confidence=0.9, session="2026-09-22")
    base.update(kw)
    return Signal(**base)


# --- 1. the happy path ------------------------------------------------------
conn, b, e = fresh()
r = e.execute(sig(), reconciled=True)
check("order fills", r["status"] == "filled", str(r.get("reasons")))
check("position created", "AAPL" in b.get_positions())
check("cash reduced", b.cash < 100.0, f"cash {b.cash}")
check("fill recorded in db",
      conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1)
check("order recorded in db",
      conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1)
check("risk approval recorded",
      conn.execute("SELECT COUNT(*) FROM risk_events WHERE decision='APPROVED'"
                   ).fetchone()[0] == 1)

# --- 2. IDEMPOTENCY — the one that must not fail ---------------------------
r2 = e.execute(sig(), reconciled=True)
check("identical signal suppressed as duplicate", r2["status"] == "duplicate", str(r2))
check("still exactly one order",
      conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1)
check("still exactly one fill",
      conn.execute("SELECT COUNT(*) FROM fills").fetchone()[0] == 1)
qty_after = b.get_positions()["AAPL"]["quantity"]
r3 = e.execute(sig(), reconciled=True)
check("third submission changes no position",
      abs(b.get_positions()["AAPL"]["quantity"] - qty_after) < 1e-9)

# --- 3. kill switch stops execution ----------------------------------------
conn, b, e = fresh()
ks.engage(conn, "test halt")
r = e.execute(sig(), reconciled=True)
check("halted while KILL_SWITCH present", r["status"] == "halted", str(r))
check("no order written while halted",
      conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 0)
ks.release(conn, "test")

# --- 4. reconciliation never run must halt ---------------------------------
conn, b, e = fresh()
r = e.execute(sig(), reconciled=None)
check("unreconciled session halts", r["status"] == "halted", str(r))

# --- 5. risk rejection ------------------------------------------------------
conn, b, e = fresh()
r = e.execute(sig(symbol="TNON", notional_value=20.0), reconciled=True)
check("nano-cap rejected before reaching the broker", r["status"] == "rejected",
      str(r.get("reasons")))
check("rejection recorded with reasons",
      conn.execute("SELECT COUNT(*) FROM risk_events WHERE decision='REJECTED'"
                   ).fetchone()[0] == 1)

# --- 6. sizing comes from the risk engine, not the signal ------------------
conn, b, e = fresh()
r = e.execute(sig(notional_value=10_000.0), reconciled=True)
check("oversized signal is capped, not obeyed",
      r["status"] == "filled" and r["order"].notional <= LIMITS["max_trade_dollars"],
      f"notional {r['order'].notional if r.get('order') else '?'}")

# --- 7. SHADOW builds an order and places nothing --------------------------
conn = sqlite3.connect(tempfile.mktemp(suffix=".db")); conn.row_factory = sqlite3.Row
b = bk.SimulatedBroker(cash=100.0, quotes=QUOTES)
e = ex.ExecutionEngine(conn, b, RiskEngine(LIMITS), mode="SHADOW", session="2026-09-22")
r = e.execute(sig(), reconciled=True)
check("shadow mode returns an order", r["status"] == "shadow", str(r))
check("shadow mode places NOTHING", b.get_positions() == {}, str(b.get_positions()))
check("shadow order still recorded for later scoring",
      conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0] == 1)

# --- 8. partial fill --------------------------------------------------------
conn, b, e = fresh(fill_ratio=0.5)
r = e.execute(sig(), reconciled=True)
check("partial fill reported as PARTIALLY_FILLED",
      r["status"] == "partially_filled", str(r))

# --- 9. broker failure does not leave a phantom order ----------------------
class Exploding(bk.SimulatedBroker):
    def place_order(self, order):
        raise ConnectionError("broker unreachable")

conn = sqlite3.connect(tempfile.mktemp(suffix=".db")); conn.row_factory = sqlite3.Row
b = Exploding(cash=100.0, quotes=QUOTES)
e = ex.ExecutionEngine(conn, b, RiskEngine(LIMITS), session="2026-09-22")
r = e.execute(sig(), reconciled=True)
check("broker exception -> FAILED, not an exception", r["status"] == "failed", str(r))
check("failure recorded",
      conn.execute("SELECT state FROM orders").fetchone()["state"] == "FAILED")
check("error counter incremented", e.errors == 1)

# --- 10. UNKNOWN is resolved by asking, never by resubmitting --------------
class Unknowning(bk.SimulatedBroker):
    def __init__(self, *a, **kw):
        super().__init__(*a, **kw); self.submits = 0
    def place_order(self, order):
        self.submits += 1
        order.broker_order_id = "rh-123"
        order.to(bk.SUBMITTING); order.to(bk.UNKNOWN)
        return order
    def get_order(self, order_id):
        return {"state": bk.FILLED, "filled_quantity": 0.4,
                "avg_fill_price": 50.0, "broker_order_id": "rh-123"}

conn = sqlite3.connect(tempfile.mktemp(suffix=".db")); conn.row_factory = sqlite3.Row
b = Unknowning(cash=100.0, quotes=QUOTES)
e = ex.ExecutionEngine(conn, b, RiskEngine(LIMITS), session="2026-09-22")
r = e.execute(sig(), reconciled=True)
check("UNKNOWN resolved to the broker's real state", r["status"] == "filled", str(r))
check("UNKNOWN did NOT cause a resubmit", b.submits == 1, f"submitted {b.submits} times")

# --- 11. illegal state transitions are refused -----------------------------
o = bk.Order(signal_id="x", symbol="AAPL", side="BUY", notional=20.0)
o.to(bk.VALIDATING); o.to(bk.APPROVED); o.to(bk.SUBMITTING); o.to(bk.SUBMITTED)
o.to(bk.FILLED)
try:
    o.to(bk.SUBMITTED)
    check("a FILLED order cannot be resubmitted", False)
except bk.TransitionError:
    check("a FILLED order cannot be resubmitted", True)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
