"""synthetic_volume.py: deterministic per company, on the fitted scale, falls with price within a company."""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import synthetic_volume as sv

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    p = {"c0": 6.0, "c1": 0.0, "sd_u": 0.0, "u": [0.0], "b": 1.0, "phi": 0.5, "innov": 0.01}
    close = np.r_[np.full(100, 20.0), np.full(100, 2.0)]
    a, b = sv.volume(close, p, 7), sv.volume(close, p, 7)
    check("deterministic for a seed", np.array_equal(a, b))
    dv = close * a
    check("dollar volume on the fitted scale (10^6 at the mean log price)",
          abs(np.median(np.log10(dv)) - 6.0) < 0.6, np.median(np.log10(dv)))
    check("dollar volume falls when the price collapses (b > 0)", np.median(dv[100:]) < np.median(dv[:100]) / 5)
    check("volumes are positive", (a > 0).all())
    check("performance cohorts are failures, others are not",
          sv.kind_of("v5:performance|NASDAQ") == "failure" and sv.kind_of("v5:merger|NYSE") == "other")
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
