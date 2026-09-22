"""
REGRESSION: the trial counter must count everything, and never go down.

Two failures it guards against. Under-counting: the counter previously saw only
evaluations, so continuous re-ranking — which is selection, and therefore
testing — was invisible to the correction. And resetting: deleting records does
not delete the selection pressure that produced them, it only destroys the
denominator every deflated-Sharpe claim depends on.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_multiple_testing.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import multiple_testing as mt

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# The noise bar: this is the number that makes a leaderboard interpretable.
check("noise bar grows with trial count",
      mt.noise_max_sharpe(1_000_000) > mt.noise_max_sharpe(1_000) > mt.noise_max_sharpe(10))
check("the bar at ~1M trials is about 5.3 SE",
      5.0 < mt.noise_max_sharpe(1_037_905) < 5.5,
      f"{mt.noise_max_sharpe(1_037_905):.2f}")
check("a single trial has no multiple-testing penalty",
      mt.noise_max_sharpe(1) == 0.0)

# Effective trials sit between the raw and distinct counts, never outside them.
e = mt.effective(1_000_000, 100_000)
check("effective trials lie between unique and total",
      100_000 <= e <= 1_000_000, str(e))
check("effective equals total when every structure is unique",
      mt.effective(500, 500) == 500)
check("effective is never zero for a non-empty count", mt.effective(10, 0) == 10)

# Counting must include SELECTION, not just evaluation.
import inspect
src = inspect.getsource(mt.count)
check("promotion decisions are counted as trials",
      "FROM promotions" in src,
      "picking the top N repeatedly is a search; the firewall flagged that the "
      "counter could not see it")
check("backtest runs are counted as trials", "kind='backtest'" in src)

# Monotonicity: the counter may never fall.
conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
mt.init(conn)
for at, n in (("2026-09-01T00:00:00", 100), ("2026-09-02T00:00:00", 250),
              ("2026-09-03T00:00:00", 900)):
    conn.execute("INSERT INTO trial_ledger (at,evaluations,promotions,backtests,"
                 "sweeps,total_trials) VALUES (?,?,?,?,?,?)", (at, n, 0, 0, 0, n))
conn.commit()
check("a rising counter reports no problem", mt.check_monotonic(conn) == [])

conn.execute("INSERT INTO trial_ledger (at,evaluations,promotions,backtests,"
             "sweeps,total_trials) VALUES ('2026-09-04T00:00:00',0,0,0,0,10)")
conn.commit()
probs = mt.check_monotonic(conn)
check("a FALLING counter is reported as a problem", len(probs) == 1, str(probs))
check("the problem names the cause",
      probs and ("removed" in probs[0] or "rebuilt" in probs[0]), str(probs))

check("context_line exists so a figure is never printed without its context",
      callable(mt.context_line))

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
