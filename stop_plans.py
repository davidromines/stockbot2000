"""
Mandatory stop plans. Addendum A §15-17, Addendum B §B13.

Every live strategy must carry a risk plan before it may hold a slot, and the
plan is evaluated by risk management, not by the strategy: a strategy that says
HOLD while its stop is breached is sold (§17).

A plan is a list of rules. Supported rule types (§15):

    {"type": "fixed_pct",    "pct": 8.0}               stop 8% below entry
    {"type": "atr",          "atr_multiple": 2.5}      entry - 2.5 x ATR at entry
    {"type": "volatility",   "sigma_multiple": 2.0}    entry x (1 - 2 x daily sigma x sqrt(hold))
    {"type": "trailing_pct", "pct": 10.0}              10% below the high since entry
    {"type": "trailing_atr", "atr_multiple": 3.0}      high since entry - 3 x ATR
    {"type": "time",         "max_hold_days": 20}      exit after N sessions
    {"type": "take_profit",  "pct": 15.0}              exit once price >= entry x 1.15
    {"type": "strategy"}                                the strategy's own exit rule

Emergency exits are not a per-plan rule: they come from the kill switches and
apply to every position regardless of plan.

**A plan is valid only if it contains at least one PRICE stop** (fixed, ATR,
volatility or trailing). A time exit alone does not bound a loss: a position
can gap to zero inside twenty sessions. That is the rule that makes a stop
"mandatory" rather than decorative.

When several price stops apply, the HIGHEST stop price wins — the tightest
protection is the one in force. Risk is never loosened by adding a rule.

**A take-profit is an exit, not a stop.** It bounds no loss, so it never makes a
plan valid on its own. It comes from the genome's `risk.take_profit_pct` — the
same gene the backtest (`simulator.py`) and the paper engine
(`paper_trading.py`) apply. Until 2026-09-24 `from_genome` dropped it, so a
live slot traded a different strategy from the one that was tested and ranked.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import math

PRICE_STOPS = ("fixed_pct", "atr", "volatility", "trailing_pct", "trailing_atr")
ALL_TYPES = PRICE_STOPS + ("time", "take_profit", "strategy")

# Parameter each rule type needs, and its sane bounds. A 0.1% stop is noise
# that exits on the first tick; a 90% stop is no stop. Out-of-range values are
# rejected, never clamped — a clamped plan is not the plan that was tested.
_PARAMS = {
    "fixed_pct": ("pct", 0.5, 50.0),
    "atr": ("atr_multiple", 0.25, 10.0),
    "volatility": ("sigma_multiple", 0.25, 10.0),
    "trailing_pct": ("pct", 0.5, 50.0),
    "trailing_atr": ("atr_multiple", 0.25, 10.0),
    "time": ("max_hold_days", 1, 750),
    "take_profit": ("pct", 0.5, 500.0),
}


def from_genome(g: dict | None) -> list:
    """The plan implied by a strategy genome's `risk` block. [] when it has none."""
    risk = (g or {}).get("risk") or {}
    plan = []
    if risk.get("stop_atr_multiple"):
        plan.append({"type": "atr", "atr_multiple": float(risk["stop_atr_multiple"])})
    if risk.get("stop_pct"):
        plan.append({"type": "fixed_pct", "pct": float(risk["stop_pct"])})
    if risk.get("trailing_pct"):
        plan.append({"type": "trailing_pct", "pct": float(risk["trailing_pct"])})
    if risk.get("trailing_atr_multiple"):
        plan.append({"type": "trailing_atr", "atr_multiple": float(risk["trailing_atr_multiple"])})
    if risk.get("max_hold_days"):
        plan.append({"type": "time", "max_hold_days": int(risk["max_hold_days"])})
    if risk.get("take_profit_pct"):
        plan.append({"type": "take_profit", "pct": float(risk["take_profit_pct"])})
    if (g or {}).get("exit"):
        plan.append({"type": "strategy"})
    return plan


def validate(plan) -> tuple:
    """(ok, reasons). Fails closed: anything unrecognised makes the plan invalid."""
    reasons = []
    if not isinstance(plan, list) or not plan:
        return False, ["no stop plan"]
    for rule in plan:
        t = (rule or {}).get("type")
        if t not in ALL_TYPES:
            reasons.append(f"unknown rule type {t!r}")
            continue
        if t in _PARAMS:
            key, lo, hi = _PARAMS[t]
            v = rule.get(key)
            try:
                v = float(v)
            except (TypeError, ValueError):
                reasons.append(f"{t}: {key} missing or not a number")
                continue
            if not (lo <= v <= hi) or math.isnan(v):
                reasons.append(f"{t}: {key}={v} outside [{lo}, {hi}]")
    if not any((r or {}).get("type") in PRICE_STOPS for r in plan):
        reasons.append("no price stop: a time or strategy exit alone does not bound a loss")
    return (not reasons), reasons


def stop_price(plan, entry_price: float, atr: float | None = None,
               high_since_entry: float | None = None, sigma: float | None = None,
               hold_days: int | None = None) -> float | None:
    """
    The price below which the position must be exited: the highest of the price
    stops that can be evaluated. A rule whose input is missing (no ATR, no
    sigma) is skipped, and if NO price stop can be evaluated the result is None,
    which callers must treat as "cannot protect this position" (see check()).
    """
    levels = []
    high = max(high_since_entry or entry_price, entry_price)
    for rule in plan or []:
        t = rule.get("type")
        if t == "fixed_pct":
            levels.append(entry_price * (1 - float(rule["pct"]) / 100))
        elif t == "atr" and atr:
            levels.append(entry_price - float(rule["atr_multiple"]) * atr)
        elif t == "volatility" and sigma:
            h = max(1, int(hold_days or 1))
            levels.append(entry_price * (1 - float(rule["sigma_multiple"]) * sigma * math.sqrt(h)))
        elif t == "trailing_pct":
            levels.append(high * (1 - float(rule["pct"]) / 100))
        elif t == "trailing_atr" and atr:
            levels.append(high - float(rule["atr_multiple"]) * atr)
    levels = [lv for lv in levels if lv > 0]
    return max(levels) if levels else None


def check(plan, position: dict, price: float | None, sessions_held: int,
          strategy_exit: bool = False) -> dict:
    """
    Should this position be exited now?

    `position` carries entry_price and optionally atr, high_since_entry, sigma.
    Order of precedence (§17): a missing price is itself an exit condition only
    when no stop can be computed; a breached price stop exits; then the
    take-profit; then the time exit; then the strategy's own exit. Risk
    first, strategy last.
    """
    ok, why = validate(plan)
    entry = float(position["entry_price"])
    sp = stop_price(plan, entry, position.get("atr"),
                    max(position.get("high_since_entry") or entry, price or entry),
                    position.get("sigma"), sessions_held)
    if not ok:
        return {"exit": True, "reason": f"invalid stop plan: {why[0]}", "stop_price": sp,
                "kind": "risk"}
    if sp is None:
        return {"exit": True, "reason": "no evaluable price stop (missing ATR/sigma)",
                "stop_price": None, "kind": "risk"}
    if price is not None and price <= sp:
        return {"exit": True, "reason": f"stop breached: {price:.4f} <= {sp:.4f}",
                "stop_price": sp, "kind": "stop"}
    for rule in plan:
        if rule["type"] == "take_profit" and price is not None \
                and price >= entry * (1 + float(rule["pct"]) / 100):
            return {"exit": True, "reason": f"take profit: {price:.4f} >= entry +{float(rule['pct']):g}%",
                    "stop_price": sp, "kind": "take_profit"}
    for rule in plan:
        if rule["type"] == "time" and sessions_held >= int(rule["max_hold_days"]):
            return {"exit": True, "reason": f"time exit after {sessions_held} sessions",
                    "stop_price": sp, "kind": "time"}
    if strategy_exit and any(r["type"] == "strategy" for r in plan):
        return {"exit": True, "reason": "strategy exit signal", "stop_price": sp,
                "kind": "strategy"}
    return {"exit": False, "reason": "within plan", "stop_price": sp, "kind": None}
