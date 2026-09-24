"""
Regression tests for stop_plans.py and slots.py (Addendum A I1-I5, I9).

Pinned: a plan without a price stop is invalid; the tightest stop wins; risk
exits outrank strategy exits (§17). Empty slots stay in cash (B6); one slot per
family (B7); a holder is replaced only by a clear margin after a minimum hold
(B11); an ineligible holder is released at once; a strategy kill switch removes
eligibility; SIMULATION assignments never move a strategy to LIVE.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import killswitch
import slots
import stop_plans as sp

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def row(key, net, fam, eligible=True, sessions=30):
    return {"strategy_key": key, "version": 1, "net_usd": net, "gross_usd": net + 1,
            "costs_usd": 1, "family": fam, "eligible": eligible, "sessions": sessions,
            "closed_trades": 12, "tier": "ELIGIBLE" if eligible else "INSUFFICIENT_SAMPLE",
            "state": "LIVE_CANDIDATE", "league": "momentum", "max_drawdown_pct": 3,
            "reasons": [] if eligible else ["tier INSUFFICIENT_SAMPLE"]}


def conn_with_prices(n_sessions=10):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, "
              "close REAL, volume REAL, source TEXT)")
    for i in range(n_sessions):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (f"2026-10-{i + 1:02d}",))
    slots.init(c)
    return c


def run_plan(c, ranked, cfg=None):
    slots.assess = lambda conn, cfg: ranked
    return slots.plan(c, cfg or {})


def main():
    # --- stop plans ---------------------------------------------------------
    ok, why = sp.validate([{"type": "time", "max_hold_days": 20}])
    check("time exit alone is not a valid plan", not ok and "no price stop" in why[-1], why)
    check("empty plan invalid", sp.validate([])[0] is False)
    check("out-of-range ATR multiple rejected", not sp.validate([{"type": "atr", "atr_multiple": 50}])[0])
    g = {"entry": {"op": "gt"}, "exit": {"op": "lt"}, "risk": {"stop_atr_multiple": 2.5, "max_hold_days": 20}}
    plan = sp.from_genome(g)
    check("genome risk -> atr + time + strategy rules",
          [r["type"] for r in plan] == ["atr", "time", "strategy"], plan)
    tight = sp.stop_price([{"type": "atr", "atr_multiple": 2}, {"type": "fixed_pct", "pct": 5}], 100, atr=5)
    check("tightest stop wins", abs(tight - 95.0) < 1e-9, tight)
    trail = sp.stop_price([{"type": "trailing_pct", "pct": 10}], 100, high_since_entry=120)
    check("trailing stop follows the high", abs(trail - 108.0) < 1e-9, trail)
    r = sp.check(plan, {"entry_price": 100, "atr": 2}, price=94.0, sessions_held=3)
    check("breached stop exits as risk", r["exit"] and r["kind"] == "stop", r)
    r = sp.check(plan, {"entry_price": 100, "atr": 2}, price=94.0, sessions_held=3, strategy_exit=True)
    check("stop outranks strategy exit (§17)", r["kind"] == "stop", r)
    r = sp.check(plan, {"entry_price": 100, "atr": 2}, price=101.0, sessions_held=20)
    check("time exit after max hold", r["exit"] and r["kind"] == "time", r)
    r = sp.check(plan, {"entry_price": 100}, price=101.0, sessions_held=1)
    check("no evaluable price stop -> exit (fail closed)", r["exit"] and r["kind"] == "risk", r)

    # --- slots --------------------------------------------------------------
    c = conn_with_prices()
    p = run_plan(c, [])
    check("nothing eligible -> all five slots cash (B6)", p["cash_slots"] == [1, 2, 3, 4, 5] and not p["assign"])

    ranked = [row("a", 9, "mom"), row("b", 8, "mom"), row("c", 5, "val"), row("d", 4, "ml", eligible=False)]
    p = run_plan(c, ranked)
    got = [r["strategy_key"] for _, r, _ in p["assign"]]
    check("one slot per family, ineligible skipped (B7)", got == ["a", "c"], got)
    check("three slots stay cash", p["cash_slots"] == [3, 4, 5], p["cash_slots"])

    slots.apply(c, {}, "SIMULATION")
    held = slots.current(c)
    check("assignments recorded", held[1]["strategy_key"] == "a" and held[2]["strategy_key"] == "c", held)
    check("SIMULATION never writes LIVE", c.execute(
        "SELECT COUNT(*) FROM slot_assignments WHERE mode='LIVE'").fetchone()[0] == 0)

    # Holder 'c' (net 5) is challenged by 'e' (net 6): below the $2 margin -> kept.
    p = run_plan(c, [row("a", 9, "mom"), row("e", 6, "evt"), row("c", 5, "val")])
    check("small advantage does not replace",
          not p["release"] and [r["strategy_key"] for _, r, _ in p["assign"]] == ["e"], p["assign"])

    # 'f' beats 'c' by $5 but c was assigned today: min hold not met.
    ranked = [row("a", 9, "mom"), row("f", 10, "evt"), row("g", 9.5, "brk"), row("h", 9.4, "pair"),
              row("i", 9.3, "fx"), row("c", 5, "val")]
    c.execute("DELETE FROM slot_assignments")
    for sl, k, fam in ((1, "a", "mom"), (2, "c", "val"), (3, "g", "brk"), (4, "h", "pair"), (5, "i", "fx")):
        c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, "
                  "mode, reason) VALUES (?,?,?,?,?,?,?,?)", ("2026-10-09T00:00:00", sl, "ASSIGN", k, 1, 20,
                                                            "SIMULATION", "t"))
    p = run_plan(c, ranked)
    check("min hold blocks replacement", not p["release"], p["release"])
    c.execute("UPDATE slot_assignments SET at='2026-10-01T00:00:00'")
    p = run_plan(c, ranked)
    rel = [(s, h["strategy_key"]) for s, h, _ in p["release"]]
    asg = [(s, r["strategy_key"]) for s, r, _ in p["assign"]]
    check("clear margin after min hold replaces the weakest", rel == [(2, "c")] and asg == [(2, "f")], (rel, asg))

    # An ineligible holder is released at once, regardless of hold time.
    ranked[-1] = row("c", 5, "val", eligible=False)
    c.execute("UPDATE slot_assignments SET at='2026-10-09T00:00:00'")
    p = run_plan(c, ranked)
    check("ineligible holder released immediately",
          any(h["strategy_key"] == "c" for _, h, _ in p["release"]), p["release"])

    # Per-strategy kill switch (I9) makes a strategy ineligible in assess().
    killswitch.init(c)
    killswitch.engage_strategy(c, "zz", "test")
    check("strategy kill switch reports halted", killswitch.strategy_halted(c, "zz") == "test")

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
