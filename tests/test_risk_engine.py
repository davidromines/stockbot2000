"""
Every risk limit, exercised against a synthetic portfolio.

These run on invented numbers on purpose. A limit tested against live account
state only proves it did not fire today; these prove it fires when it should and
does not when it should not, which is the property that matters when the thing
it is guarding is real money.

Run:  PYTHONPATH=. venv/bin/python tests/test_risk_engine.py
"""
import runtime  # noqa: F401

from risk_engine import RiskEngine, load_limits
from signals import Signal, SignalError

LIMITS = load_limits()
E = RiskEngine(LIMITS)

GOOD_QUOTE = {"price": 50.0, "dollar_volume_20": 20_000_000.0, "market_cap": 5e9}
PORTFOLIO = {"equity": 100.0, "buying_power": 100.0, "daily_pnl": 0.0,
             "drawdown_percent": 0.0, "positions": {}}


def sig(**kw):
    base = dict(symbol="AAPL", action="BUY", strategy="test", reason="test",
                notional_value=20.0, confidence=0.8, session="2026-09-22")
    base.update(kw)
    return Signal(**base)


fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


# --- the happy path must actually work, or every rejection below is vacuous --
r = E.validate(sig(), PORTFOLIO, GOOD_QUOTE, {})
check("clean signal approved", r.approved, str(r.reasons))
check("clean signal sized", r.sized_notional == 20.0, f"got {r.sized_notional}")

# --- size limits ------------------------------------------------------------
r = E.validate(sig(notional_value=500.0), PORTFOLIO, GOOD_QUOTE, {})
check("oversized order capped to max_trade_dollars",
      r.approved and r.sized_notional <= LIMITS["max_trade_dollars"],
      f"got {r.sized_notional}")

held = {**PORTFOLIO, "positions": {"AAPL": {"value": 25.0}}}
r = E.validate(sig(), held, GOOD_QUOTE, {})
check("position already at cap is rejected", not r.approved, str(r.reasons))

full = {**PORTFOLIO, "positions": {f"S{i}": {"value": 20.0} for i in range(5)}}
r = E.validate(sig(), full, GOOD_QUOTE, {})
check("open-position cap enforced", not r.approved, str(r.reasons))

broke = {**PORTFOLIO, "buying_power": 0.50}
r = E.validate(sig(), broke, GOOD_QUOTE, {})
check("no buying power is rejected", not r.approved, str(r.reasons))

# --- tradeability floors ----------------------------------------------------
r = E.validate(sig(), PORTFOLIO, {**GOOD_QUOTE, "price": 2.0}, {})
check("sub-$5 price rejected", not r.approved)

r = E.validate(sig(), PORTFOLIO, {**GOOD_QUOTE, "dollar_volume_20": 100.0}, {})
check("illiquid name rejected", not r.approved)

r = E.validate(sig(), PORTFOLIO, {**GOOD_QUOTE, "market_cap": 3.5e6}, {})
check("nano-cap rejected (the TNON case)", not r.approved)

r = E.validate(sig(), PORTFOLIO, {**GOOD_QUOTE, "market_cap": None}, {})
check("UNKNOWN market cap rejected, not waved through", not r.approved,
      "this is the check that TNON actually needed")

r = E.validate(sig(), PORTFOLIO, {**GOOD_QUOTE, "dollar_volume_20": None}, {})
check("UNKNOWN liquidity rejected", not r.approved)

r = E.validate(sig(), PORTFOLIO, None, {})
check("missing quote rejected — fails closed", not r.approved)

# --- loss limits ------------------------------------------------------------
r = E.validate(sig(), {**PORTFOLIO, "daily_pnl": -20.0}, GOOD_QUOTE, {})
check("daily loss limit blocks new orders", not r.approved, str(r.reasons))

r = E.validate(sig(), {**PORTFOLIO, "drawdown_percent": 40.0}, GOOD_QUOTE, {})
check("drawdown limit blocks new orders", not r.approved, str(r.reasons))

# --- throttles --------------------------------------------------------------
r = E.validate(sig(), PORTFOLIO, GOOD_QUOTE, {"orders_today": 10})
check("daily order cap enforced", not r.approved, str(r.reasons))

r = E.validate(sig(), PORTFOLIO, GOOD_QUOTE, {"orders_for_symbol": 2})
check("per-symbol order cap enforced", not r.approved, str(r.reasons))

# --- instruments ------------------------------------------------------------
r = E.validate(sig(asset_type="option"), PORTFOLIO, GOOD_QUOTE, {})
check("options blocked", not r.approved)
r = E.validate(sig(asset_type="crypto"), PORTFOLIO, GOOD_QUOTE, {})
check("crypto blocked", not r.approved)

# --- exits are never size-blocked ------------------------------------------
held = {**PORTFOLIO, "positions": {"AAPL": {"value": 25.0}}}
r = E.validate(sig(action="CLOSE", notional_value=None, quantity=1.0), held, None, {})
check("CLOSE approved with no quote — an exit must never be trapped", r.approved,
      str(r.reasons))

r = E.validate(sig(action="CLOSE", notional_value=None, quantity=1.0), PORTFOLIO, None, {})
check("CLOSE with no position rejected", not r.approved)

# --- multiple reasons are all reported --------------------------------------
r = E.validate(sig(asset_type="crypto"), {**PORTFOLIO, "daily_pnl": -50.0},
               {**GOOD_QUOTE, "price": 1.0}, {"orders_today": 99})
check("collects every reason, not just the first", len(r.reasons) >= 3,
      f"got {len(r.reasons)}: {r.reasons}")

# --- signal validation ------------------------------------------------------
try:
    Signal(symbol="AAPL", action="TELEPORT", strategy="t", reason="r").validate()
    check("bad action rejected", False)
except SignalError:
    check("bad action rejected", True)

try:
    Signal(symbol="AAPL", action="BUY", strategy="t", reason="r",
           quantity=1, notional_value=20).validate()
    check("quantity AND notional rejected as ambiguous", False)
except SignalError:
    check("quantity AND notional rejected as ambiguous", True)

try:
    Signal(symbol="AAPL", action="BUY", strategy="", reason="r",
           notional_value=20).validate()
    check("missing strategy rejected", False)
except SignalError:
    check("missing strategy rejected", True)

# --- idempotency key --------------------------------------------------------
a = sig(); b = sig()
check("same decision -> same signal_id", a.signal_id == b.signal_id)
c = sig(session="2026-09-23")
check("different session -> different signal_id", a.signal_id != c.signal_id)
d = sig(symbol="MSFT")
check("different symbol -> different signal_id", a.signal_id != d.signal_id)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
