"""
One list of attached panel columns: every loader that decides whether a rule needs
the attached panel (factory_pipeline, survivorship_backtest) uses storage.needs_panel.
Found 2026-09-27: survivorship_backtest checked fundamentals + SUE only, so alpha,
short-volume and analog strategies were backtested without their column (0 trades).
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import factory_pipeline as fp
import storage
import strategy_factory as sf

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def g(c):
    return sf.G(sf.gt(sf.rank(sf.col(c)), sf.k(0.9)))


def main():
    for c in ("alpha_252", "short_volume_ratio_20", "analog_p_up", "composite", "book_to_market", "sue",
              "opp_buyers_90"):
        check(f"needs_panel sees {c}", storage.needs_panel(g(c)))
    check("a price-only rule does not need the panel", not storage.needs_panel(g("rsi_14")))
    check("factory_pipeline uses the same rule", fp._needs_fund({}, g("composite")) and not fp._needs_fund({}, g("rsi_14")))
    src = open(os.path.join(os.path.dirname(storage.__file__), "survivorship_backtest.py")).read()
    check("survivorship_backtest uses storage.needs_panel", "storage.needs_panel(g)" in src)
    fam = sf.F.get("multi_signal")
    check("multi_signal family registered", fam is not None)
    if fam:
        g0 = fam["build"]({"q": 0.9, "hold": 20, "stop": 3.0})
        check("multi_signal ranks the composite column", storage.needs_panel(g0) and '"composite"' in str(g0).replace("'", '"'))
    fam = sf.F.get("insider_buying")
    check("insider_buying family registered and reads opp_buyers_90",
          fam is not None and storage.needs_panel(fam["build"]({"buyers": 1, "hold": 20, "stop": 3.0})))
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
