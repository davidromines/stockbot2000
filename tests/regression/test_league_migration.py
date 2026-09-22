"""
REGRESSION: migrating the forward record must not touch the forward record.

The 16 paper funds and 5 pair funds are the only measurement in this project
with no survivorship bias and no look-ahead, and they accrue at one day per day.
Item 13 runs before item 14 for that reason: migrate the record before changing
the thing that writes it.

The migration therefore MOVES NO DATA. It registers each fund's identity in the
league and points at the existing tables. Nothing is copied, so nothing can be
copied wrongly, and the worst bug available here is a league row pointing
somewhere useless — which `verify()` catches.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_league_migration.py
"""
import runtime  # noqa: F401
import inspect
import sqlite3
import tempfile

import league as lg
import migrate_league as ml

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE paper_runs (run_id TEXT, name TEXT, strategy TEXT, capital_usd REAL,
    cash_usd REAL, started_on TEXT, last_step_on TEXT, status TEXT,
    created_at TEXT, last_review TEXT, label TEXT, family TEXT);
CREATE TABLE paper_equity (run_id TEXT, date TEXT, equity_usd REAL);
CREATE TABLE pair_funds (name TEXT, label TEXT, bull TEXT, bear TEXT,
    signal TEXT, method TEXT, param REAL, min_hold INTEGER, capital_usd REAL,
    started_on TEXT, status TEXT, search_note TEXT);
CREATE TABLE pair_fund_equity (name TEXT, date TEXT, equity_usd REAL);
""")
conn.execute("""INSERT INTO paper_runs VALUES ('r1','n1',
    '{"entry":{"op":">","a":"rsi_14","b":30},"exit":{"op":"<"},"risk":{"max_hold_days":10}}',
    100,50,'2026-09-01','2026-09-21','open','2026-09-01',NULL,'Momo One','momentum')""")
conn.execute("""INSERT INTO paper_runs VALUES ('r2','n2','model',100,50,
    '2026-09-01','2026-09-21','open','2026-09-01',NULL,'Classifier','model')""")
conn.execute("""INSERT INTO paper_runs VALUES ('r3','n3','{"conviction":"deep_value"}',
    100,0,'2026-09-01','2026-09-21','closed','2026-09-01',NULL,'Deep Value','conviction')""")
conn.execute("INSERT INTO pair_funds VALUES ('p1','Pair One','SPY','SH','sma','x',1.0,3,100,'2026-09-01','open','')")
for r in ("r1", "r2", "r3"):
    conn.execute("INSERT INTO paper_equity VALUES (?,?,?)", (r, "2026-09-21", 100.0))
conn.execute("INSERT INTO pair_fund_equity VALUES ('p1','2026-09-21',100.0)")
conn.commit()
lg.init(conn)


def counts():
    return {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            for t in ("paper_runs", "paper_equity", "pair_funds", "pair_fund_equity")}


before = counts()

# --- a dry run writes nothing ----------------------------------------------
res = ml.migrate(conn, dry_run=True)
check("a dry run finds every fund", res["found"] == 4, str(res["found"]))
check("a dry run registers nothing", res["registered"] == 0)
check("a dry run leaves the league empty", len(lg.roster(conn)) == 0)

# --- the real migration -----------------------------------------------------
res = ml.migrate(conn, dry_run=False)
check("every fund is registered", res["registered"] == 4)
check("every fund enters the lifecycle", res["transitioned"] == 4)

check("the forward record is UNCHANGED", counts() == before,
      f"{before} -> {counts()}")

check("funds enter at PAPER, not DISCOVERED",
      lg.state(conn, "paper:r1") == lg.PAPER,
      "walking them through DISCOVERED would write a history that did not happen")
check("a fund already closed is retired",
      lg.state(conn, "paper:r3") == lg.RETIRED)
check("the retired fund still passed THROUGH paper",
      [h["to_state"] for h in lg.history(conn, "paper:r3")] == [lg.PAPER, lg.RETIRED],
      "RETIRED is not reachable from nothing, so both steps must be recorded")

# --- idempotency ------------------------------------------------------------
again = ml.migrate(conn, dry_run=False)
check("a second run re-transitions nothing", again["transitioned"] == 0)
check("a second run recognises everything as already present",
      again["already_in_league"] == 4)
check("a second run does not fork any strategy",
      all(len(lg.versions(conn, r["strategy_key"])) == 1 for r in lg.roster(conn)),
      "the obvious way to fix a botched migration is to run it again")
check("the forward record is STILL unchanged", counts() == before)

# --- the specs distinguish the three paper-fund shapes ----------------------
specs = {r["strategy_key"]: lg.latest(conn, r["strategy_key"]) for r in lg.roster(conn)}
check("a genome fund, a classifier and a screen get DIFFERENT definitions",
      len({specs["paper:r1"]["definition_hash"],
           specs["paper:r2"]["definition_hash"],
           specs["paper:r3"]["definition_hash"]}) == 3,
      "collapsing them would make three unrelated strategies one")
check("the classifier is recorded as its own family",
      specs["paper:r2"]["family"] == "model")
check("the pair fund records both legs",
      "SPY" in specs["pair:p1"]["universe"] and "SH" in specs["pair:p1"]["universe"])

# --- verify() catches a broken link ----------------------------------------
check("verify passes on a good migration", ml.verify(conn) == [])
conn.execute("DELETE FROM paper_runs WHERE run_id='r1'")
conn.commit()
check("verify catches a league row pointing at nothing",
      any("paper:r1" in p for p in ml.verify(conn)),
      "this is the only damage this migration can actually cause")

# --- it must not write to the source tables --------------------------------
src = inspect.getsource(ml)
for verb, table in [("INSERT INTO paper", "paper_runs"),
                    ("UPDATE paper", "paper_runs"),
                    ("DELETE FROM paper", "paper_runs"),
                    ("INSERT INTO pair", "pair_funds"),
                    ("UPDATE pair", "pair_funds"),
                    ("DELETE FROM pair", "pair_funds")]:
    check(f"the migration never runs `{verb}...`", verb.upper() not in src.upper(),
          "the forward record is read-only to this module")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
