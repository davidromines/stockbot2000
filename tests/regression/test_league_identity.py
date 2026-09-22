"""
REGRESSION: strategy identity is immutable and the lifecycle cannot be skipped.

The league decides which strategies eventually receive real money, so the two
things it must never do are lose track of what a strategy WAS, and let one
arrive somewhere it did not earn.

Three properties are pinned here:

1. **A material change mints a new version and leaves the old row intact.**
   Renaming does not, because a rename that forked the forward record would
   silently reset a strategy's track record to zero.

2. **State is derived from an append-only log, not stored in a column.** A
   column is a thing someone can set. For the record that justifies allocating
   capital, that difference is the whole point.

3. **Transitions are whitelisted.** Nothing reaches PAPER without VALIDATING,
   nothing returns from SUSPENDED straight to LIVE, and RETIRED is terminal.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_league_identity.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import league as lg

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
lg.init(conn)

SPEC = {"family": "momentum", "universe": ["common_stock"],
        "entry_rule": {"op": ">", "a": "rsi_14", "b": 30},
        "exit_rule": {"op": "<", "a": "rsi_14", "b": 70},
        "position_sizing": {"usd": 20}, "holding_period": {"max_days": 10},
        "parameters": {"k": 1}, "required_data": ["prices", "features"]}

# --- registration and versioning --------------------------------------------
r1 = lg.register(conn, "mom-001", "Momentum One", SPEC)
check("a new strategy registers at version 1", r1["version"] == 1)

r2 = lg.register(conn, "mom-001", "Momentum One", SPEC)
check("re-registering an UNCHANGED strategy does not fork it",
      r2["version"] == 1,
      "registration must be idempotent — a migration run twice would otherwise "
      "fork every strategy in the arena")

r3 = lg.register(conn, "mom-001", "Renamed Entirely", SPEC)
check("a RENAME does not mint a new version", r3["version"] == 1,
      "renaming would reset the strategy's forward record to zero")

changed = dict(SPEC, entry_rule={"op": ">", "a": "rsi_14", "b": 35})
r4 = lg.register(conn, "mom-001", "Momentum One", changed)
check("a MATERIAL change mints version 2", r4["version"] == 2)
check("version 2 records what it supersedes", r4["supersedes"] == 1)

vs = lg.versions(conn, "mom-001")
check("both versions survive — the old row is never overwritten", len(vs) == 2)
check("version 1 still holds its ORIGINAL rule",
      '"b": 30' in vs[0]["entry_rule"] or '"b":30' in vs[0]["entry_rule"],
      vs[0]["entry_rule"])

# Adding a field must change the hash, or definitions collide as they grow.
h_small = lg.definition_hash({"entry_rule": "X"})
h_big = lg.definition_hash({"entry_rule": "X", "exit_rule": "Y"})
check("adding a material field changes the definition hash", h_small != h_big,
      "skipping missing keys would collide across a schema change")

# --- the lifecycle ----------------------------------------------------------
check("a strategy with no state reports None", lg.state(conn, "mom-001") is None)

try:
    lg.transition(conn, "mom-001", lg.LIVE, "straight to live")
    check("a new strategy cannot enter the lifecycle at LIVE", False,
          "entry points must be DISCOVERED or PAPER")
except lg.LeagueError:
    check("a new strategy cannot enter the lifecycle at LIVE", True)

lg.transition(conn, "mom-001", lg.DISCOVERED, "unit test")
check("state is readable after the first transition",
      lg.state(conn, "mom-001") == lg.DISCOVERED)

try:
    lg.transition(conn, "mom-001", lg.PAPER, "skip validation")
    check("DISCOVERED cannot skip straight to PAPER", False,
          "nothing may reach the arena without being validated")
except lg.LeagueError as e:
    check("DISCOVERED cannot skip straight to PAPER", True)
    check("the refusal lists what IS allowed", "BACKTESTING" in str(e), str(e))

for s in (lg.BACKTESTING, lg.VALIDATING, lg.PAPER, lg.ELIGIBLE):
    lg.transition(conn, "mom-001", s, "unit test")
check("a strategy can walk the ladder in order",
      lg.state(conn, "mom-001") == lg.ELIGIBLE)

lg.transition(conn, "mom-001", lg.SUSPENDED, "operational halt")
try:
    lg.transition(conn, "mom-001", lg.LIVE, "resume")
    check("SUSPENDED cannot return directly to LIVE", False,
          "an operational halt must not silently restore live status")
except lg.LeagueError:
    check("SUSPENDED cannot return directly to LIVE", True)

lg.transition(conn, "mom-001", lg.PAPER, "resumed, re-earning its place")
check("SUSPENDED returns to PAPER", lg.state(conn, "mom-001") == lg.PAPER)

# --- a reason is mandatory --------------------------------------------------
try:
    lg.transition(conn, "mom-001", lg.ELIGIBLE, "   ")
    check("a transition without a reason is refused", False)
except lg.LeagueError:
    check("a transition without a reason is refused", True)

# --- RETIRED is terminal ----------------------------------------------------
lg.transition(conn, "mom-001", lg.RETIRED, "superseded by v2 research")
check("a retired strategy reports RETIRED", lg.state(conn, "mom-001") == lg.RETIRED)
for target in (lg.PAPER, lg.LIVE, lg.ELIGIBLE, lg.DISCOVERED):
    try:
        lg.transition(conn, "mom-001", target, "revive")
        check(f"RETIRED cannot be revived to {target}", False,
              "a revived strategy must come back as a new version")
        break
    except lg.LeagueError:
        pass
else:
    check("RETIRED is terminal for every target", True)

check("the retired strategy is still in the database",
      len(lg.versions(conn, "mom-001")) == 2,
      "nothing disappears for performing badly")

# --- the state log is append-only ------------------------------------------
h = lg.history(conn, "mom-001")
check("every transition is recorded", len(h) >= 8, f"{len(h)}")
check("each record carries its reason", all(x["reason"].strip() for x in h))
check("each record carries where it came from",
      h[0]["from_state"] is None and h[1]["from_state"] == lg.DISCOVERED)

import inspect
src = inspect.getsource(lg)
check("the module never UPDATEs a strategy or a state row",
      "UPDATE " not in src.upper(),
      "identity and history are append-only; a change makes a new row")

# --- the league cannot reach the broker ------------------------------------
check("the league does not import the execution path",
      "import execution" not in src and "import broker" not in src,
      "Phase 7 is explicit that the league must not be able to call the broker")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
