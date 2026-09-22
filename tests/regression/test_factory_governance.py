"""
REGRESSION: generation is refused unless every governance gate is satisfied.

Four ungoverned searches ran before the freeze and every one located its result
in the scoreboard rather than in the market. The binding constraint was never
the amount of search, so item 23 re-enables generation only behind gates that
make it impossible to run without a record of what was being looked for.

The property that matters most: **this module cannot lift its own restriction.**
Flipping search.mode to ACTIVE is a human edit to config.yaml. A governor that
can unfreeze itself is not a governor.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_factory_governance.py
"""
import runtime  # noqa: F401
import inspect
import json
import sqlite3
import tempfile

import experiment_registry as reg
import factory

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
reg.init(conn)

ACTIVE = {"search": {"mode": "ACTIVE"}, "lab": {"seed_mode": "NONE"}}
FROZEN = {"search": {"mode": "FROZEN"}, "lab": {"seed_mode": "NONE"}}

SPEC = {"primary_metric": "excess", "universe": ["common_stock"],
        "entry_rule": "evolved", "exit_rule": "evolved"}
reg.create(conn, "exp-ok", "A testable claim.", "tester", SPEC)
reg.register(conn, "exp-ok")
reg.create(conn, "exp-draft", "A draft claim.", "tester", SPEC)

# --- each gate independently ------------------------------------------------
a = factory.authorize(conn, ACTIVE, None, 1000)
check("no experiment blocks the run", not a["permitted"])
check("the block explains what a registered experiment is for",
      any("before any result exists" in b for b in a["blockers"]))

a = factory.authorize(conn, ACTIVE, "exp-ok", None)
check("no declared budget blocks the run", not a["permitted"])
check("the budget block explains the permanent cost",
      any("rises permanently" in b for b in a["blockers"]))

a = factory.authorize(conn, ACTIVE, "exp-draft", 1000)
check("a DRAFT experiment is not good enough", not a["permitted"])
check("the block says why a draft is insufficient",
      any("edited after seeing a result" in b for b in a["blockers"]))

seeded = {"search": {"mode": "ACTIVE"}, "lab": {"seed_mode": "ALL"}}
a = factory.authorize(conn, seeded, "exp-ok", 1000)
check("seed_mode other than NONE blocks the run", not a["permitted"])
check("the seed block cites the measured contamination",
      any("12.8%" in b for b in a["blockers"]))

# --- all gates satisfied ----------------------------------------------------
a = factory.authorize(conn, ACTIVE, "exp-ok", 1000)
check("a fully governed run IS permitted", a["permitted"], str(a["blockers"]))
check("the authorisation prices the budget against the ledger",
      any("noise bar" in n for n in a["notes"]))
check("ancestry is recorded and not switchable",
      any("not switchable" in n for n in a["notes"]))

# --- the freeze -------------------------------------------------------------
a = factory.authorize(conn, FROZEN, "exp-ok", 1000)
check("a FROZEN search refuses an otherwise-valid run", not a["permitted"])
check("the freeze block says it was a decision, not an outage",
      any("not an outage" in b for b in a["blockers"]))

reg.create(conn, "exp-thaw", "A claim worth the freeze.", "tester",
           {**SPEC, "freeze_justification":
            "forward observation cannot answer this and the budget is small"})
reg.register(conn, "exp-thaw")
a = factory.authorize(conn, FROZEN, "exp-thaw", 1000)
check("an experiment that JUSTIFIES the freeze may proceed", a["permitted"],
      str(a["blockers"]))
check("the justification is echoed back",
      any("freeze acknowledged" in n for n in a["notes"]))

# --- blockers accumulate ----------------------------------------------------
a = factory.authorize(conn, {"search": {"mode": "FROZEN"},
                             "lab": {"seed_mode": "ALL"}}, None, None)
check("every unmet requirement is reported, not just the first",
      len(a["blockers"]) >= 4, f"{len(a['blockers'])}")

# --- the governor cannot ungovern itself ------------------------------------
src = inspect.getsource(factory)
check("the module never writes config", "open(" not in src and "yaml.dump" not in src)
check("the module never sets search.mode",
      "mode'] =" not in src and 'mode"] =' not in src,
      "a governor that can lift its own restriction is not a governor")
check("the module cannot register an experiment for itself",
      "reg.create(" not in src and "reg.register(" not in src,
      "it would otherwise satisfy its own first gate")
check("the module does not run a search itself",
      "evolve" not in src.lower().replace("evolutionary", ""),
      "authorisation is separate from execution")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
