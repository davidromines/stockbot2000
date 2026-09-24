"""
Regression tests for universe_layer_a.norm_name and the provenance rules.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import universe_layer_a as ua

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    check("suffix and punctuation stripped", ua.norm_name("Altaba Inc.") == "ALTABA", ua.norm_name("Altaba Inc."))
    check("same company, two spellings", ua.norm_name("AAR CORP") == ua.norm_name("AAR Corporation"))
    check("ampersand normalised", ua.norm_name("Johnson & Johnson") == ua.norm_name("JOHNSON AND JOHNSON"))
    check("None is empty, never a match key", ua.norm_name(None) == "")
    check("month bounds", ua._month_start("1996-03") == "1996-03-01" and ua._month_end("1996-02") == "1996-02-29")
    src = open(os.path.join(ROOT, "universe_layer_a.py")).read()
    check("reasons come only from 8-K items", "REASON_ITEMS" in src and "1.03" in src and "2.01" in src)
    check("never writes the primary database", "mode=ro" in src and "to_sql" not in src)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
