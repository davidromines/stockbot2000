"""
Regression tests for allocation.py and roster.py — Phase 10, items 32 and 33.

Three properties are pinned here, each because the alternative fails silently:

  * the allocator never invents capital,
  * demotion is easier than promotion,
  * promotion stops at LIVE_CANDIDATE.

The modules under test reach into eligibility, scoreboard and promotion_policy,
which read the real database. Rather than stand up a synthetic league — which
would test the fixtures, not the code — the collaborators are stubbed at the
module boundary and the tests assert on what allocation.py and roster.py do
with the answers. The stubs are deliberately dumb: they return fixed rosters
and fixed verdicts, so a failure here is a failure in the module under test.

Run: PYTHONPATH=. venv/bin/python tests/regression/test_allocation_roster.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas

import ast
import os
import sqlite3
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import allocation
import league as lg
import roster

PASS = 0
FAIL = 0


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        print(f"  FAIL  {name}" + (f"  — {detail}" if detail else ""))


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def cfg(position_size_usd=20.0, max_open_positions=5):
    return {"risk": {"position_size_usd": position_size_usd,
                     "max_open_positions": max_open_positions}}


def row(key, name=None, score=0.0, volatility=None):
    r = {"strategy_key": key, "name": name or key, "score": score}
    if volatility is not None:
        r["metrics"] = {"volatility": volatility}
    return r


# --------------------------------------------------------------------------
# Stubs. Each replaces a module-level collaborator for the duration of a test.
# --------------------------------------------------------------------------

class Stub:
    def __init__(self, module, name, value):
        self.module, self.name, self.value = module, name, value

    def __enter__(self):
        self.saved = getattr(self.module, self.name)
        setattr(self.module, self.name, self.value)
        return self.value

    def __exit__(self, *exc):
        setattr(self.module, self.name, self.saved)
        return False


def stub_roster(roster_rows):
    """eligibility.propose -> a fixed roster; eligibility.assess -> all eligible."""
    def propose(conn_, cfg_, formula=None):
        return {"roster": roster_rows}

    def assess(conn_, cfg_, formula=None):
        return [{"strategy_key": r["strategy_key"], "eligible": True,
                 "reasons": []} for r in roster_rows]

    return [Stub(allocation.eligibility, "propose", propose),
            Stub(roster.eligibility, "propose", propose),
            Stub(roster.eligibility, "assess", assess)]


def stub_promotion(permitted=True, blockers=None):
    def evaluate(conn_, cfg_, key, actor=None):
        return {"permitted": permitted,
                "blockers": blockers or ([] if permitted else ["not ready"])}
    return Stub(roster.pp, "evaluate", evaluate)


def stub_live(keys):
    """league.roster -> the given keys, all LIVE."""
    def league_roster(conn_):
        return [{"strategy_key": k, "state": lg.LIVE} for k in keys]
    return Stub(roster.lg, "roster", league_roster)


# --------------------------------------------------------------------------
# allocation.py
# --------------------------------------------------------------------------

def test_capital():
    check("capital is position_size_usd * max_open_positions",
          allocation.capital(cfg(20.0, 5)) == 100.0,
          allocation.capital(cfg(20.0, 5)))
    check("capital follows config, not a constant",
          allocation.capital(cfg(7.5, 4)) == 30.0,
          allocation.capital(cfg(7.5, 4)))


def test_schemes_sum_to_one():
    rows = [row("a", score=3.0, volatility=0.02),
            row("b", score=1.0, volatility=0.04),
            row("c", score=0.0, volatility=0.08)]
    for name, fn in sorted(allocation.SCHEMES.items()):
        shares = fn(rows)
        total = sum(shares.values())
        check(f"scheme {name!r} shares sum to 1.0",
              abs(total - 1.0) < 1e-9, total)
        check(f"scheme {name!r} covers every roster slot",
              set(shares) == {"a", "b", "c"}, sorted(shares))


def test_score_falls_back_to_equal():
    rows = [row("a", score=0.0), row("b", score=0.0), row("c", score=0.0)]
    shares = allocation._score(rows)
    check("_score falls back to equal when every score is zero",
          all(abs(v - 1.0 / 3) < 1e-9 for v in shares.values()), shares)

    rows = [row("a", score=-5.0), row("b", score=-1.0)]
    shares = allocation._score(rows)
    check("_score falls back to equal when every score is negative",
          all(abs(v - 0.5) < 1e-9 for v in shares.values()), shares)


def test_risk_parity_inverse_vol():
    rows = [row("calm", volatility=0.01), row("wild", volatility=0.10)]
    shares = allocation._risk_parity(rows)
    check("_risk_parity gives the lower-vol strategy the larger share",
          shares["calm"] > shares["wild"], shares)
    check("_risk_parity weights are inverse to volatility",
          abs(shares["calm"] / shares["wild"] - 10.0) < 1e-6, shares)

    rows = [row("a", volatility=0.0), row("b", volatility=0.0)]
    shares = allocation._risk_parity(rows)
    check("_risk_parity falls back to equal when no vol is measured",
          all(abs(v - 0.5) < 1e-9 for v in shares.values()), shares)


def test_allocate_never_exceeds_cap():
    rows = [row(f"s{i}", score=float(i + 1)) for i in range(5)]
    with stub_roster(rows)[0], stub_roster(rows)[1], stub_roster(rows)[2]:
        c = conn()
        r = allocation.allocate(c, cfg(20.0, 5), scheme="score")
        c.close()
    total = sum(a["dollars"] for a in r["allocations"])
    check("allocate never allocates more than the account cap",
          total <= r["capital"] + 1e-9, (total, r["capital"]))
    check("allocate caps each slot at position_size_usd",
          all(a["dollars"] <= 20.0 + 1e-9 for a in r["allocations"]),
          [a["dollars"] for a in r["allocations"]])
    check("allocate reports the unallocated remainder",
          abs(r["allocated"] + r["unallocated"] - r["capital"]) < 1e-9,
          (r["allocated"], r["unallocated"], r["capital"]))


def test_allocate_empty_roster():
    with stub_roster([])[0], stub_roster([])[1], stub_roster([])[2]:
        c = conn()
        r = allocation.allocate(c, cfg())
        c.close()
    check("allocate with an empty roster funds nothing",
          r["roster_empty"] and r["allocations"] == []
          and r["unallocated"] == r["capital"], r)


def test_allocate_unknown_scheme():
    raised = False
    try:
        allocation.allocate(conn(), cfg(), scheme="no_such_scheme")
    except SystemExit:
        raised = True
    check("allocate raises SystemExit on an unknown scheme", raised)


def test_record_writes_one_row_per_allocation():
    rows = [row("a", score=1.0), row("b", score=1.0)]
    with stub_roster(rows)[0], stub_roster(rows)[1], stub_roster(rows)[2]:
        c = conn()
        r = allocation.allocate(c, cfg(), scheme="equal")
        n = allocation.record(c, cfg(), r, note="test")
        stored = c.execute("SELECT * FROM allocations").fetchall()
        c.close()
    check("record writes one row per allocation",
          n == len(r["allocations"]) == len(stored), (n, len(stored)))
    check("record stores the scheme and the capital on every row",
          all(s["scheme"] == "equal" and s["capital_usd"] == r["capital"]
              for s in stored), [dict(s) for s in stored])


# --------------------------------------------------------------------------
# roster.py
# --------------------------------------------------------------------------

def test_current_is_live_only():
    def league_roster(conn_):
        return [{"strategy_key": "live1", "state": lg.LIVE},
                {"strategy_key": "cand1", "state": lg.LIVE_CANDIDATE},
                {"strategy_key": "elig1", "state": lg.ELIGIBLE},
                {"strategy_key": "dem1", "state": lg.DEMOTED}]
    with Stub(roster.lg, "roster", league_roster):
        c = conn()
        cur = roster.current(c)
        c.close()
    check("current returns only LIVE strategies",
          [r["strategy_key"] for r in cur] == ["live1"],
          [r["strategy_key"] for r in cur])


def test_demotion_is_easier_than_promotion():
    """One failure demotes; promotion needs every gate."""
    rows = [row("newbie", score=1.0)]
    with stub_roster(rows)[0], stub_roster(rows)[1], stub_roster(rows)[2], \
            stub_live(["stale"]), stub_promotion(permitted=False):
        c = conn()
        p = roster.plan(c, cfg())
        c.close()
    demoted = {k for k, _ in p["demote"]}
    check("a live strategy absent from the league is demoted",
          "stale" in demoted, p["demote"])
    check("a blocked promotion is reported, not applied",
          any(k == "newbie" and why.startswith("BLOCKED")
              for k, why in p["promote"]), p["promote"])
    check("a blocked promotion does not count as a change",
          p["changes"] == len(p["demote"]), p["changes"])


def test_apply_never_reaches_live():
    """The whole point of the intermediate state."""
    rows = [row("newbie", score=1.0)]
    transitions = []

    def transition(conn_, key, to_state, reason, actor=None):
        transitions.append((key, to_state))
        return None

    def state(conn_, key):
        return lg.ELIGIBLE

    with stub_roster(rows)[0], stub_roster(rows)[1], stub_roster(rows)[2], \
            stub_live([]), stub_promotion(permitted=True), \
            Stub(roster.lg, "transition", transition), \
            Stub(roster.lg, "state", state):
        c = conn()
        roster.apply(c, cfg())
        c.close()

    check("apply transitions a promoted strategy to LIVE_CANDIDATE",
          ("newbie", lg.LIVE_CANDIDATE) in transitions, transitions)
    check("apply never transitions any strategy to LIVE",
          all(to != lg.LIVE for _, to in transitions), transitions)


def test_apply_demotes_before_promoting():
    rows = [row("newbie", score=1.0)]
    order = []

    def transition(conn_, key, to_state, reason, actor=None):
        order.append((key, to_state))

    with stub_roster(rows)[0], stub_roster(rows)[1], stub_roster(rows)[2], \
            stub_live(["stale"]), stub_promotion(permitted=True), \
            Stub(roster.lg, "transition", transition), \
            Stub(roster.lg, "state", lambda c_, k: lg.ELIGIBLE):
        c = conn()
        roster.apply(c, cfg())
        c.close()

    demote_at = next((i for i, (k, _) in enumerate(order) if k == "stale"), None)
    promote_at = next((i for i, (k, _) in enumerate(order) if k == "newbie"), None)
    check("apply demotes before it promotes",
          demote_at is not None and promote_at is not None
          and demote_at < promote_at, order)


def test_history_newest_first():
    c = conn()
    roster.init(c)
    for i in range(2):
        c.execute("""INSERT INTO roster_changes (at, strategy_key, action,
            reason, dollars, applied) VALUES (?,?,?,?,?,?)""",
            (f"2026-09-2{i}T00:00:00+00:00", f"s{i}", "DEMOTE", "test", None, 1))
    c.commit()
    rows = roster.history(c)
    c.close()
    check("history returns rows newest first",
          [r["strategy_key"] for r in rows] == ["s1", "s0"],
          [r["strategy_key"] for r in rows])


# --------------------------------------------------------------------------
# Structural guards
# --------------------------------------------------------------------------

def test_no_broker_import():
    root = os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))))
    for name in ("allocation.py", "roster.py"):
        path = os.path.join(root, name)
        with open(path) as fh:
            tree = ast.parse(fh.read(), filename=path)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imported.update(a.name.split(".")[0] for a in node.names)
            elif isinstance(node, ast.ImportFrom) and node.module:
                imported.add(node.module.split(".")[0])
        check(f"{name} does not import the broker",
              "broker" not in imported, sorted(imported))


def main():
    print("\n  ALLOCATION / ROSTER REGRESSION\n  " + "-" * 60)
    test_capital()
    test_schemes_sum_to_one()
    test_score_falls_back_to_equal()
    test_risk_parity_inverse_vol()
    test_allocate_never_exceeds_cap()
    test_allocate_empty_roster()
    test_allocate_unknown_scheme()
    test_record_writes_one_row_per_allocation()
    test_current_is_live_only()
    test_demotion_is_easier_than_promotion()
    test_apply_never_reaches_live()
    test_apply_demotes_before_promoting()
    test_history_newest_first()
    test_no_broker_import()
    print("  " + "-" * 60)
    print(f"  {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
