"""
REGRESSION: the defects that let the search fool itself.

  seed contamination        survivors inheriting a hand-written constant
  structural duplicate rules  one idea occupying a whole shortlist
  dead branches             bloat as mutation armour
  price-floor benchmark contamination  a null that pays for buying cheap

The seed case is the newest and the most embarrassing: 231 of 455 survivors
carried the literal constant 40 from seeds.py, and the "convergence" was
reported as the project's best finding before being retracted an hour later.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_search_hygiene.py
"""
import runtime  # noqa: F401
import inspect
import re

import numpy as np

import genome as gn

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- 1. SEED CONTAMINATION IS DETECTABLE -----------------------------------
# The mechanism that caught it: survivors agreeing on an EXACT constant. An
# interquartile range of zero across many "independent" discoveries is descent.
import seeds
seed_src = inspect.getsource(seeds)
seed_constants = set(re.findall(r"col\(\"rsi_14\"\),\s*(\d+)", seed_src))
check("seed constants are extractable from seeds.py",
      len(seed_constants) > 0, f"found {seed_constants}")
check("the specific constant that contaminated the search is present",
      "40" in seed_constants,
      "if this disappears the detector below is testing nothing")


def iqr_zero(values):
    """The signature of descent: every 'independent' result identical."""
    a = np.array(values, dtype="float64")
    return float(np.percentile(a, 75) - np.percentile(a, 25)) == 0.0


check("identical constants across survivors are flagged (IQR == 0)",
      iqr_zero([40.0] * 200))
check("genuinely learned thresholds are NOT flagged",
      not iqr_zero([33.7, 32.9, 34.2, 36.9, 33.9]))

# --- 2. STRUCTURAL DEDUPLICATION -------------------------------------------
# Comparing rule TEXT let one idea fill 199 of 200 shortlist slots, because the
# same structure with a different constant looked like a different strategy.
a = {"op": "lt", "args": [{"col": "sma_200"}, {"const": 7.05}]}
b = {"op": "lt", "args": [{"col": "sma_200"}, {"const": 8.59}]}
c = {"op": "gt", "args": [{"col": "rsi_14"}, {"const": 7.05}]}
check("same structure, different constant -> SAME shape",
      gn.shape(a) == gn.shape(b),
      "these are one idea and must not occupy two shortlist slots")
check("different structure -> different shape", gn.shape(a) != gn.shape(c))

# --- 3. DEAD BRANCHES -------------------------------------------------------
# 60 "distinct" rules turned out to be one rule with 60 branches that could
# never fire — bloat that survives mutation because it changes nothing.
# The shape value_range actually expects: per-column quantiles, matching what
# the constant sampler uses. Asserted below so this test fails loudly if that
# contract changes rather than silently testing nothing.
stats = {"rsi_14": {"quantiles": [0.0, 25.0, 50.0, 75.0, 100.0]},
         "close": {"quantiles": [1.0, 10.0, 50.0, 200.0, 1000.0]}}
check("value_range reads per-column quantiles as expected",
      gn.value_range({"col": "rsi_14"}, stats) == (0.0, 100.0),
      f"got {gn.value_range({'col': 'rsi_14'}, stats)}")
impossible = {"op": "gt", "args": [{"col": "rsi_14"}, {"const": 500.0}]}
possible = {"op": "gt", "args": [{"col": "rsi_14"}, {"const": 70.0}]}
check("a comparison whose answer is fixed before data arrives is degenerate",
      gn.is_degenerate(impossible, stats),
      "rsi_14 cannot exceed 500; this branch is dead")
check("a live comparison is NOT called degenerate",
      not gn.is_degenerate(possible, stats))

# --- 4. THE NULL MUST VARY BY PRICE AND HORIZON ----------------------------
# A market-wide null paid anything that bought cheap stocks. 66 survivors were
# voided over this.
import benchmark as bench
sig = inspect.signature(bench.null_surface)
check("the null is a SURFACE, not a scalar",
      "anchors" in sig.parameters,
      "a flat null is what produced the sma_200 < $8 price filter")
src = inspect.getsource(bench)
check("the null is computed on the unfiltered series",
      "_forward_unfiltered" in src)
check("the null fills the same way the simulator does (open-to-open)",
      "next_open" in src,
      "a null on a different fill convention rigs every comparison")

# --- 5. COSTS ARE CHARGED INSIDE THE SEARCH --------------------------------
import simulator
sim_src = inspect.getsource(simulator.simulate)
check("the simulator charges costs, not the caller afterwards",
      "cost_model.round_trip" in sim_src,
      "scored on gross returns the search finds strategies that cannot pay "
      "their own spread")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
