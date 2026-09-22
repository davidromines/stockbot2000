"""
REGRESSION: the sealed window may be evaluated once per strategy, ever.

Every peek costs statistical validity and there is no way to un-peek. The rule
is therefore enforced mechanically rather than by discipline, and refused
attempts are logged as well as permitted ones — a pattern of refusals on one
strategy is itself evidence about how a decision was reached.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_sealed_holdout.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import evaluate_holdout as hold

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
hold.init(conn)

ok, reason = hold.may_evaluate(conn, "strat-A")
check("an unevaluated strategy may be evaluated", ok, reason)

calls = {"n": 0}


def fake_runner(tconn):
    calls["n"] += 1
    return {"excess": 42.0}


# Patch the truth-set open so the test does not need a real snapshot.
class _Dummy:
    def close(self):
        pass


hold.truth_set.open_version = lambda v: _Dummy()

r = hold.evaluate(conn, "strat-A", "sealed_v1", runner=fake_runner)
check("the first evaluation runs", r["excess"] == 42.0 and calls["n"] == 1)

ok, reason = hold.may_evaluate(conn, "strat-A")
check("a second evaluation is REFUSED", not ok, reason)
check("the refusal explains why un-peeking is impossible",
      "un-peek" in reason or "cannot" in reason.lower(), reason)

try:
    hold.evaluate(conn, "strat-A", "sealed_v1", runner=fake_runner)
    check("evaluate() raises on a second attempt", False,
          "the seal must be mechanical, not advisory")
except hold.SealError:
    check("evaluate() raises on a second attempt", True)

check("the runner was NOT invoked a second time", calls["n"] == 1,
      f"ran {calls['n']} times — a refused attempt must not still evaluate")

rows = hold.report(conn)
check("both the permitted and the REFUSED attempts are logged", len(rows) == 2,
      f"{len(rows)} — a hidden refusal defeats the purpose")
check("a bare may_evaluate() check logs nothing",
      len([r for r in rows if r["reason"] == "first evaluation"]) == 0,
      "asking whether a strategy MAY be evaluated reveals no result, so it is "
      "not a look and must not consume the one evaluation")
check("exactly one attempt is marked permitted",
      sum(1 for r in rows if r["permitted"]) == 1)

# --- an evaluation may only be spent on a SEALED snapshot -------------------
try:
    hold.evaluate(conn, "strat-C", "v1", runner=fake_runner)
    check("evaluating against a NON-sealed snapshot is refused", False,
          "one typo would spend the single look on data the search has already "
          "seen thousands of times")
except hold.SealError as e:
    check("evaluating against a NON-sealed snapshot is refused", True)
    check("the refusal names it as not sealed", "not a sealed snapshot" in str(e))

check("a caller error does NOT consume strat-C's evaluation",
      hold.may_evaluate(conn, "strat-C")[0],
      "a rejected version is a typo, not a look")
check("a caller error is not logged against the strategy",
      hold.attempts(conn, "strat-C") == 0)

# A different strategy is unaffected.
ok, _ = hold.may_evaluate(conn, "strat-B")
check("a different strategy still has its one evaluation", ok)

# There must be no delete path.
import inspect
src = inspect.getsource(hold)
check("the module offers no way to delete a holdout record",
      "DELETE FROM" not in src.upper() and "DROP TABLE" not in src.upper(),
      "removing a disappointing evaluation is the file-drawer problem applied "
      "to the one window that cannot be re-used")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
