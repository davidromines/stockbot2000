"""
A template whose key has a newer recycled version must not be re-minted as a
duplicate of its own original (strategy_objects.defined_before). In-memory only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import league
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def obj(hold):
    return {"strategy_key": "fx_t", "name": "T", "family": "fam", "league": "tactical",
            "genome": {"entry": {"col": "close"}, "exit": {"col": "close"},
                       "risk": {"stop_atr_multiple": 2.0, "max_hold_days": hold}},
            "parameters": {"hold": hold}, "data_requirements": ["features"]}


def main():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    so.init(c)
    check("a new template is not defined before", so.defined_before(c, obj(2)) is None)
    so.register(c, obj(2))
    check("after registering: defined as v1", so.defined_before(c, obj(2)) == 1)
    so.register(c, obj(4))                          # the recycled variant: v2
    check("the original still counts as defined after a newer version", so.defined_before(c, obj(2)) == 1)
    n = len(league.versions(c, "fx_t"))
    check("only two versions exist", n == 2, n)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
