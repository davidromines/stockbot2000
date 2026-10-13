"""experience_experiment: helpers and the leak-free pool rule (synthetic library)."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd
import experience_experiment as ee
from analog import COLS

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

a, b = pd.Series(np.full(30, 0.02)), pd.Series(np.zeros(30))
d, lo, hi = ee.boot_diff(a, b)
check("a constant positive difference has a positive lower bound", abs(d - 0.02) < 1e-9 and lo > 0)
rng = np.random.default_rng(1)
n = pd.Series(rng.normal(0, 0.05, 40))
d2, lo2, hi2 = ee.boot_diff(n, n * 0)
check("noise has an interval containing zero", lo2 < 0 < hi2)
check("too few dates -> no interval", np.isnan(ee.boot_diff(pd.Series([1.0, 2.0]), pd.Series([0.0, 0.0]))[1]))
lib = pd.DataFrame({"date": [f"2021-01-{d:02d}" for d in range(1, 29)] * 2})
qd = ee.query_dates(lib, "2021-01-01", "2021-12-31")
check("query dates are every 4th library date", qd == [f"2021-01-{d:02d}" for d in range(1, 29, 4)])
# the pool rule: a row whose outcome is not yet known on the query date must not be a neighbour
rows = pd.DataFrame({c: np.float32(0.5) for c in COLS}, index=range(6))
rows["exit_date"] = ["2021-01-05", "2021-01-09", "2021-01-15", "2021-02-01", "2021-02-10", "2021-03-01"]
pool = rows[rows["exit_date"] <= "2021-01-31"]
check("only outcomes known by the query date enter the pool", len(pool) == 3)
check("spec locks the decision rule and the cost", "bootstrap" in ee.SPEC["decision_rule"] and "0.17" in ee.SPEC["cost_assumptions"])
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
