"""
Stage O: genome rules may read `cal_*` columns (trading_calendar.py), computed
from the exchange calendar per row date — the same value live and in backtest.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import genome as gn

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    dates = pd.to_datetime(["2024-01-12", "2024-01-16", "2024-01-31", "2024-01-31", "2024-02-01"])
    df = pd.DataFrame({"ticker": ["A", "A", "A", "B", "A"], "date": dates, "close": [1.0] * 5})
    rev = gn.evaluate({"col": "cal_tdom_rev"}, df).tolist()
    check("cal_tdom_rev from the calendar (last session of Jan = 1)", rev == [13.0, 12.0, 1.0, 1.0, 20.0], rev)
    pre = gn.evaluate({"col": "cal_pre_holiday"}, df).tolist()
    check("cal_pre_holiday: Friday before MLK day", pre == [1.0, 0.0, 0.0, 0.0, 0.0], pre)
    rule = {"op": "lt", "args": [{"col": "cal_tdom_rev"}, {"const": 1.5}]}
    fire = gn._as_bool(gn.evaluate(rule, df)).tolist()
    check("a turn-of-month rule fires on the month's last session only", fire == [False, False, True, True, False], fire)
    check("an unknown cal_ column is NaN, not an error",
          gn.evaluate({"col": "cal_nope"}, df).isna().all())
    check("a non-calendar missing column is still NaN", gn.evaluate({"col": "nope"}, df).isna().all())
    one = df.iloc[[2]]                                  # a live-style single latest bar
    check("the value does not depend on other rows (live == backtest)",
          gn.evaluate({"col": "cal_tdom_rev"}, one).tolist() == [1.0])
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
