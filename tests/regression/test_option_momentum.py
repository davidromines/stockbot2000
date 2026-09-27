"""
R6 option momentum (options_lab.sig_opt_momentum): ranks by the mean past straddle
return over months t-12..t-2 (the latest month skipped), needs MOM_MIN_MONTHS of
history, fires once a month. Formation is stubbed; no database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import options_lab as ol

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    firsts = [f"2025-{m:02d}-02" for m in range(1, 13)] + ["2026-01-02"]
    seen = []
    ret = {"AAA": 0.10, "BBB": -0.05, "CCC": 0.30}

    def fake_ret(conn, sym, d0, d1, s):
        seen.append((sym, d0, d1))
        if sym == "DDD":                         # too little history
            return 0.9 if d0 >= "2025-10" else None
        if sym == "CCC" and d0 == "2025-12-02":
            return 5.0                           # the skipped latest month must not count
        return ret[sym]

    ol._month_firsts = lambda conn, upto: [d for d in firsts if d <= upto]
    ol.liquid = lambda conn, date, n: ["AAA", "BBB", "CCC", "DDD"]
    ol.straddle_return = fake_ret
    p = {**ol.STRATEGIES["opt_momentum_straddle"], "top": 2}
    state = {}
    out = ol.sig_opt_momentum(None, "2026-01-02", p, {}, state)
    syms = [x[0] for x in out]
    check("top two by mean formation return", syms == ["CCC", "AAA"], out)
    check("the most recent month (t-1) is not used", not any(d0 == "2025-12-02" for _, d0, _ in seen), seen[-3:])
    check("a stock with too few months is not ranked", "DDD" not in syms)
    check("second call in the same month signals nothing", ol.sig_opt_momentum(None, "2026-01-05", p, {}, state) == [])
    check("registered with the engine's rule table", ol.STRATEGIES["opt_momentum_straddle"]["rule"] == "opt_momentum")
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
