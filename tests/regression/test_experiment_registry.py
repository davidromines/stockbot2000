"""
REGRESSION: pre-registration must actually prevent researcher degrees of freedom.

A registry that permits silent edits is a diary, and a diary is not evidence.
These tests assert the refusals, because the refusals are the entire mechanism —
everything else is record-keeping.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_experiment_registry.py
"""
import runtime  # noqa: F401
import json
import sqlite3
import tempfile

import experiment_registry as reg

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
reg.init(conn)

SPEC = {"primary_metric": "excess_pnl_usd", "universe": "common_stock",
        "entry_rule": "rsi_14 < 30", "exit_rule": "max_hold",
        "holding_period": 20, "cost_assumptions": "costs.py default",
        "evaluation_period": ["2020-01-01", "2022-12-31"],
        "data_version": "truth_v1", "stopping_rule": "fixed sample",
        "sample_size": 20000, "holdout_policy": "sealed untouched"}

e = reg.create(conn, "EXP-001", "Tight stops outperform wide stops", "claude", SPEC)
check("an experiment can be created", e["status"] == reg.DRAFT)
check("a spec hash is recorded", len(e["spec_hash"]) == 64)

# A hypothesis is mandatory: a test you cannot fail is not a test.
try:
    reg.create(conn, "EXP-BAD", "   ", "claude", SPEC)
    check("an empty hypothesis is refused", False)
except reg.RegistryError:
    check("an empty hypothesis is refused", True)

# DRAFT is editable.
reg.update(conn, "EXP-001", {"holding_period": 25})
check("a DRAFT may be edited",
      json.loads(reg.get(conn, "EXP-001")["spec"])["holding_period"] == 25)

reg.register(conn, "EXP-001")
check("registration locks the experiment",
      reg.get(conn, "EXP-001")["status"] == reg.REGISTERED)

# THE central assertion.
try:
    reg.update(conn, "EXP-001", {"primary_metric": "sharpe"})
    check("a LOCKED field cannot be changed after registration", False,
          "this is the whole mechanism")
except reg.RegistryError:
    check("a LOCKED field cannot be changed after registration", True)

try:
    reg.update(conn, "EXP-001", {"entry_rule": "rsi_14 < 40"})
    check("the entry rule cannot be swapped after registration", False)
except reg.RegistryError:
    check("the entry rule cannot be swapped after registration", True)

# Non-locked fields may still be annotated.
reg.update(conn, "EXP-001", {"notes": "ran on the 22nd"})
check("non-locked fields may still be updated",
      "notes" in json.loads(reg.get(conn, "EXP-001")["spec"]))

# Changing your mind is allowed, but it is recorded.
v2 = reg.new_version(conn, "EXP-001", "Tight stops outperform, measured on Sharpe",
                     "claude", {**SPEC, "primary_metric": "sharpe"},
                     reason="excess_pnl was the wrong metric for this question")
check("a new VERSION may change a locked field", v2["version"] == 2)
check("the new version records what it supersedes", v2["supersedes"] == 1)
check("the ORIGINAL version still exists",
      reg.get(conn, "EXP-001", version=1)["status"] == reg.REGISTERED,
      "an experiment that vanished because it did not work is the file-drawer "
      "problem")

# Lifecycle.
reg.register(conn, "EXP-001")
reg.start(conn, "EXP-001")
check("a registered experiment can start", reg.get(conn, "EXP-001")["status"] == reg.RUNNING)
reg.complete(conn, "EXP-001", {"excess": 123.0}, "no effect detected")
done = reg.get(conn, "EXP-001")
check("results may be attached on completion", done["status"] == reg.COMPLETE)
check("the conclusion is stored", "no effect" in (done["conclusion"] or ""))

try:
    reg.start(conn, "EXP-001")
    check("a COMPLETE experiment is terminal", False)
except reg.RegistryError:
    check("a COMPLETE experiment is terminal", True)

# A rejected experiment is kept, not deleted.
e3 = reg.create(conn, "EXP-002", "Crash buying works", "claude", SPEC)
reg.reject(conn, "EXP-002", "superseded by forward evidence")
check("a REJECTED experiment is retained with its reason",
      reg.get(conn, "EXP-002")["status"] == reg.REJECTED)
# Three rows: EXP-001 v1, EXP-001 v2, EXP-002. EXP-BAD was refused at creation
# for having no hypothesis and correctly does not exist.
rows = reg.listing(conn)
check("the registry lists every experiment including rejected ones",
      len(rows) == 3, f"{len(rows)}: {[(r['experiment_id'], r['version']) for r in rows]}")
check("the refused experiment was never created",
      not any(r["experiment_id"] == "EXP-BAD" for r in rows))

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
