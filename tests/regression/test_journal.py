"""journal.py: ranking snapshots and movement, search, and a strategy timeline
assembled from the append-only tables. In-memory database only."""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import journal

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    c.execute("CREATE TABLE league_strategies (strategy_key TEXT, version INT, name TEXT, family TEXT, created_at TEXT, source_kind TEXT)")
    c.execute("CREATE TABLE league_state (strategy_key TEXT, version INT, at TEXT, from_state TEXT, to_state TEXT, reason TEXT, actor TEXT)")
    c.execute("CREATE TABLE slot_assignments (at TEXT, slot_id INT, action TEXT, strategy_key TEXT, version INT, mode TEXT, reason TEXT)")
    c.executemany("INSERT INTO league_strategies VALUES (?,1,?,?,?,?)",
                  [("a", "Alpha", "fam", "2026-09-20T00:00:00", "factory_template"), ("b", "Beta", "fam", "2026-09-20T00:00:00", "x")])
    c.execute("INSERT INTO league_state VALUES ('a',1,'2026-09-21T00:00:00',NULL,'DISCOVERED','generated','t')")
    c.execute("INSERT INTO slot_assignments VALUES ('2026-09-22T00:00:00',1,'ASSIGN','a',1,'SIMULATION','eligible')")
    row = lambda k, sc: {"strategy_key": k, "version": 1, "score": sc, "passes_gate": True, "state": "PAPER"}
    c.execute("INSERT INTO prices VALUES ('SPY','2026-09-24',1)")
    journal.snapshot(c, {}, [row("a", 0.03), row("b", 0.02)])
    c.execute("INSERT INTO prices VALUES ('SPY','2026-09-25',1)")
    journal.snapshot(c, {}, [row("b", 0.04), row("a", 0.01)])
    m = journal.movement(c)
    ch = {r["strategy_key"]: r["change"] for r in m["top"]}
    check("movement: b rose one place, a fell one", ch == {"b": 1, "a": -1}, ch)
    check("snapshot is idempotent per date", journal.snapshot(c, {}, [row("b", 0.04), row("a", 0.01)]) == 2
          and c.execute("SELECT COUNT(*) FROM ranking_history").fetchone()[0] == 4)
    check("search by name", [r["strategy_key"] for r in journal.search(c, "alp")] == ["a"])
    t = journal.timeline(c, "a")
    kinds = [e["kind"] for e in t["events"]]
    check("timeline: registered, state, slot — oldest first", kinds == ["registered", "state", "slot"], kinds)
    check("timeline carries rank history", [r["rank"] for r in t["ranks"]] == [1, 2], t["ranks"])
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
