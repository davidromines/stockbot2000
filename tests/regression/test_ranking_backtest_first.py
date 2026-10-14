"""ranking.evidence_mode=backtest_first: who may hold a slot, and what scores them (owner, 2026-10-14)."""
import runtime  # noqa: F401
import ranking

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

v = ranking.backtest_first_verdict
check("default mode is the original blend", ranking.settings({})["evidence_mode"] == "blend")
check("a Lab-search fund (no backtest) cannot hold a slot", v(True, None, None, True, "x")[0] is False)
check("a strategy with no backtest cannot", v(False, None, {"worst_case": 0.01}, True, "x")[0] is False)
check("no survivorship result -> worst case unknown -> not eligible", v(False, 0.01, None, True, "x")[0] is False)
ok, why = v(False, 0.01, {"worst_case": -0.0009}, True, "x")
check("negative worst case is out, with the number in the reason", ok is False and "-0.090%" in why)
check("zero worst case is out", v(False, 0.01, {"worst_case": 0.0}, True, "x")[0] is False)
check("positive backtest and positive worst case passes, reason kept", v(False, 0.01, {"worst_case": 0.004}, True, "backtest +1%") == (True, "backtest +1%"))
check("a strategy the gate already rejected keeps its own reason", v(False, 0.01, {"worst_case": 0.004}, False, "loses on unseen data") == (False, "loses on unseen data"))
# the score ignores paper results entirely in this mode
s = ranking.settings({"ranking": {"evidence_mode": "backtest_first"}})
blend = ranking.score(0.01, -0.05, 20, s)
check("blend mode lets paper results move the score (the thing this mode removes)", blend < 0.01 - 0.02)
check("backtest-first score is the prior alone", ranking.score(0.01, None, 0, s) == 0.01)
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
