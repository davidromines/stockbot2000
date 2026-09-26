"""
Regression tests for value_metrics.compute's fcf_to_price metric.

fcf_to_price is free cash flow to price: (operating cash flow - capex) / market
cap. The failure this pins down is a sign error — capex is reported as a
positive outflow in XBRL, so adding it instead of subtracting turns the most
capital-hungry companies into the best cash generators, and the resulting
screen looks plausible while ranking the universe backwards.

Run: PYTHONPATH=. venv/bin/python tests/regression/test_fcf_to_price.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from value_metrics import compute  # noqa: E402

FAILED = 0
TOL = 1e-12


def check(name, cond, detail=""):
    global FAILED
    if cond:
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name}" + (f"  ({detail})" if detail else ""))


def close(a, b):
    return a is not None and b is not None and abs(a - b) < TOL


OCF = "NetCashProvidedByUsedInOperatingActivities"
CAPEX = "PaymentsToAcquirePropertyPlantAndEquipment"
CAPEX_ALT = "PaymentsToAcquireProductiveAssets"


def facts(ocf=None, capex=None, capex_tag=CAPEX):
    """Build a {tag: {qtrs: value}} map from the two inputs under test."""
    cur = {}
    if ocf is not None:
        cur[OCF] = ocf
    if capex is not None:
        cur[capex_tag] = capex
    return cur


# 1. Annual filing: (100 - 30) / 1000 = 0.07; legacy fcf_yield = 100 / 1000.
m = compute(facts({4: 100}, {4: 30}), None, market_cap=1000)
check("annual: fcf_to_price subtracts capex", close(m["fcf_to_price"], 0.07),
      f"got {m['fcf_to_price']!r}")
check("annual: fcf_yield unchanged (ocf only)", close(m["fcf_yield"], 0.10),
      f"got {m['fcf_yield']!r}")

# 2. Quarterly filing: annualised to (100 - 20) / 1000 = 0.08. A quarter left
# un-annualised would give 0.02, so this also pins the ann() helper.
m = compute(facts({1: 25}, {1: 5}), None, market_cap=1000)
check("quarterly: both flows annualised x4", close(m["fcf_to_price"], 0.08),
      f"got {m['fcf_to_price']!r}")

# 3. Capex tagged negative is still an outflow: abs() before subtracting.
m = compute(facts({4: 100}, {4: -30}), None, market_cap=1000)
check("negative capex still subtracted", close(m["fcf_to_price"], 0.07),
      f"got {m['fcf_to_price']!r}")

# 4. Absence is not zero. Missing capex must not be treated as zero capex, which
# would silently report operating cash flow as free cash flow.
m = compute(facts({4: 100}, None), None, market_cap=1000)
check("missing capex: fcf_to_price None", m["fcf_to_price"] is None,
      f"got {m['fcf_to_price']!r}")
check("missing capex: fcf_yield still computed", close(m["fcf_yield"], 0.10),
      f"got {m['fcf_yield']!r}")
m = compute(facts(None, {4: 30}), None, market_cap=1000)
check("missing ocf: both None",
      m["fcf_to_price"] is None and m["fcf_yield"] is None,
      f"got {m['fcf_to_price']!r} / {m['fcf_yield']!r}")

# 5. No market cap means no valuation metric at all.
for mc in (None, 0):
    m = compute(facts({4: 100}, {4: 30}), None, market_cap=mc)
    check(f"market_cap {mc!r}: fcf_to_price None", m["fcf_to_price"] is None,
          f"got {m['fcf_to_price']!r}")

# 6. The fallback capex tag resolves identically.
m = compute(facts({4: 100}, {4: 30}, capex_tag=CAPEX_ALT), None, market_cap=1000)
check("alternative capex tag", close(m["fcf_to_price"], 0.07),
      f"got {m['fcf_to_price']!r}")

# 7. Negative free cash flow is a real signal and must not be clipped to zero.
m = compute(facts({4: 10}, {4: 50}), None, market_cap=1000)
check("negative FCF not clipped", close(m["fcf_to_price"], -0.04),
      f"got {m['fcf_to_price']!r}")

print(f"\n  {'ALL PASS' if not FAILED else f'{FAILED} FAILED'}")
sys.exit(1 if FAILED else 0)
