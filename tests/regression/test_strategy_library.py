"""
REGRESSION: a citation is provenance, not a result — and a refuted ENCODING is
not a refuted publication.

Phase 8 says in capitals that all external strategies are HYPOTHESES and that a
published strategy must never be assumed to work in this universe. Two ways that
discipline fails quietly:

1. **Provenance fields go missing.** An entry without `known_biases` and
   `limitations` is a recommendation wearing a citation, and this project's
   whole record is of caveats discovered after a number was believed.

2. **A failed encoding gets recorded against its author.** Five of the twenty
   seeds say outright that they are not the published rule — "an adaptation, not
   the strategy", "an approximation of the published rule, not the rule". Their
   encoding was refuted here; Jegadeesh & Titman were not. "REFUTED" against a
   famous name is the version someone would remember, and it would be wrong.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_strategy_library.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import strategy_library as sl

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
sl.init(conn)

GOOD = {"entry_id": "t:1", "name": "T", "family": "value",
        "original_hypothesis": "h", "known_biases": "b", "limitations": "l",
        "validation_status": sl.HYPOTHESIS}

sl.upsert(conn, GOOD)
check("a complete entry is accepted", len(sl.listing(conn)) == 1)

for missing in ("known_biases", "limitations", "original_hypothesis"):
    bad = {k: v for k, v in GOOD.items() if k != missing}
    bad["entry_id"] = "t:bad"
    try:
        sl.upsert(conn, bad)
        check(f"an entry missing {missing} is REFUSED", False,
              "provenance fields are not optional")
    except SystemExit:
        check(f"an entry missing {missing} is REFUSED", True)

try:
    sl.upsert(conn, {**GOOD, "entry_id": "t:2", "validation_status": "GREAT"})
    check("an unknown validation status is refused", False)
except SystemExit:
    check("an unknown validation status is refused", True)

try:
    sl.upsert(conn, {**GOOD, "entry_id": "t:3", "family": "vibes"})
    check("an unknown family is refused", False)
except SystemExit:
    check("an unknown family is refused", True)

# --- faithfulness governs what a failure may conclude -----------------------
check("the non-faithful seeds are enumerated", len(sl.NOT_FAITHFUL) == 5,
      str(sorted(sl.NOT_FAITHFUL)))
for nm in ("cross_sectional_momentum", "dual_momentum", "donchian_breakout"):
    check(f"{nm} is marked as not faithful to its publication",
          nm in sl.NOT_FAITHFUL)
    kind, why = sl.NOT_FAITHFUL[nm]
    check(f"{nm} records WHY it deviates", bool(why.strip()))
    check(f"{nm}'s deviation kind is valid", kind in sl.FAITHFULNESS)

# The real import, against the live database, is where the two statuses divide.
from universe import load_config
import storage
cfg = load_config()
live = storage.connect(cfg["database"]["market_data_path"])
sl.init(live)
rows = {r["entry_id"]: r for r in sl.listing(live)}
if rows:
    faithful_fail = [r for r in rows.values()
                     if r["entry_id"].startswith("seed:")
                     and r["faithfulness"] == sl.FAITHFUL
                     and r["validation_status"] == sl.REFUTED]
    unfaithful = [r for r in rows.values()
                  if r["entry_id"].startswith("seed:")
                  and r["faithfulness"] != sl.FAITHFUL]
    check("a faithful encoding that failed is REFUTED", len(faithful_fail) > 0,
          "these are genuine refutations and should say so")
    check("a NON-faithful encoding that failed is never REFUTED",
          all(r["validation_status"] != sl.REFUTED for r in unfaithful),
          str([(r["name"], r["validation_status"]) for r in unfaithful]))
    check("its reason says the encoding failed, not the publication",
          all("OUR ENCODING" in (r["status_reason"] or "") for r in unfaithful),
          "attributing a result to an author whose rule was never run")
    check("nothing in the library is SUPPORTED",
          not any(r["validation_status"] == sl.SUPPORTED for r in rows.values()),
          "nothing here has cleared a forward test")
    fam = [r for r in rows.values() if r["entry_id"].startswith("family:")]
    check("the pre-registered families are all untested hypotheses",
          len(fam) >= 7 and all(r["validation_status"] == sl.HYPOTHESIS
                                for r in fam), str(len(fam)))
    check("each family says it is not yet implemented",
          all(r["implementation"] == "NOT YET IMPLEMENTED" for r in fam))
    check("every library entry carries biases AND limitations",
          all((r["known_biases"] or "").strip() and (r["limitations"] or "").strip()
              for r in rows.values()))
live.close()

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
