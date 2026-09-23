"""
Regression tests for stop_conditions.py and compute_priority.py.

Phase 6 sections 27 and 28.

The two defects this file exists to pin down both reported the check as
PASSING while it was broken:

  - stop_conditions read a dict key that does not exist, so the data-quality
    condition never fired at all;
  - reading the right key then rendered UNMEASURABLE coverage as "0.0%",
    which is the unknown-as-zero substitution this project keeps
    rediscovering.

A stop condition that cannot evaluate is worse than one that is absent,
because the report shows it as green. So the tests below assert on the
*reason text* as well as the boolean: a check that fires for the wrong
reason is still a broken check.

Trial count is driven through the config threshold rather than by inserting
rows. `multiple_testing.count()` does not read a trial ledger — it counts
`evaluations`, `promotions` and backtest/sweep records — so a fixture table
would leave total_trials at 0 and the "above threshold" case could never
fire. Setting `max_trials` to 0 or to a huge number exercises the comparison
itself, which is the behaviour that matters, without a million rows.

Run: PYTHONPATH=. venv/bin/python tests/regression/test_stop_and_compute.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import sqlite3
import sys
import traceback

import compute_priority as cp
import stop_conditions as sc

PASSED = 0
FAILED = 0


def check(name, fn):
    global PASSED, FAILED
    try:
        fn()
    except Exception:  # noqa: BLE001
        FAILED += 1
        print(f"  FAIL {name}")
        traceback.print_exc()
    else:
        PASSED += 1
        print(f"  PASS {name}")


def conn():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    return c


def cfg(**over):
    """
    A config shaped like config.yaml, with the stop thresholds overridable.

    `lab.search_start` is always present: evaluate() reads it unconditionally,
    so a cfg without it raises rather than failing a condition.
    """
    base = {
        "database": {"market_data_path": ":memory:"},
        "lab": {"search_start": "2006-01-01"},
        "search": {"stop_conditions": {}},
    }
    for k, v in over.items():
        if k == "stop_conditions":
            base["search"]["stop_conditions"].update(v)
        else:
            base[k] = v
    return base


# --------------------------------------------------------------------------
# Fixtures. stop_conditions queries the trial ledger (via
# multiple_testing.count), promotions, pit_universe.coverage and
# random_control. We create the tables it touches and stub the two modules it
# imports lazily, so the module can be exercised without the real database.
# --------------------------------------------------------------------------

def make_promotions(c, total, void):
    c.execute("""CREATE TABLE IF NOT EXISTS promotions (
        strategy_id TEXT NOT NULL,
        stage TEXT NOT NULL,
        decision TEXT NOT NULL,
        evidence TEXT,
        decided_at TEXT NOT NULL,
        PRIMARY KEY (strategy_id, stage)
    )""")
    rows = []
    for i in range(total):
        rows.append((f"v{i}", "validation",
                     "void" if i < void else "pass", None,
                     "2026-01-01T00:00:00+00:00"))
    c.executemany("INSERT OR REPLACE INTO promotions "
                  "(strategy_id, stage, decision, evidence, decided_at) "
                  "VALUES (?,?,?,?,?)", rows)
    c.commit()


def make_random_control(c, n, passed):
    c.execute("""CREATE TABLE IF NOT EXISTS random_control (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        strategy_id TEXT NOT NULL,
        passed_gate INTEGER NOT NULL
    )""")
    c.executemany("INSERT INTO random_control (strategy_id, passed_gate) "
                  "VALUES (?, ?)",
                  [(f"r{i}", 1 if i < passed else 0) for i in range(n)])
    c.commit()


class _StubCoverage:
    """
    Stands in for pit_universe.coverage(). The real function returns a dict
    with `coverage_pct` (a PERCENT) and `knowable`. The first defect was
    reading a key that does not exist; the second was treating a missing or
    zero `knowable` as 0.0% coverage rather than UNMEASURABLE.
    """

    def __init__(self, result):
        self.result = result

    def __call__(self, conn, date):
        return self.result


def with_coverage(result):
    """Patch pit_universe.coverage for one test."""
    import types
    mod = types.ModuleType("pit_universe")
    mod.coverage = _StubCoverage(result)
    sys.modules["pit_universe"] = mod
    return mod


def without_coverage():
    """Make `import pit_universe` fail, as it would with no snapshots at all."""
    sys.modules.pop("pit_universe", None)
    sys.modules["pit_universe"] = None  # import returns None -> AttributeError


# --------------------------------------------------------------------------
# stop_conditions.evaluate
# --------------------------------------------------------------------------

def test_trial_count_stops():
    """
    max_trials 0 makes any trial count trip the condition. The comparison is
    what is under test; the ledger's absolute size is not.
    """
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 90.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 0}))
    assert r["stop"] is True, "a trial count at or above the threshold must stop"
    assert r["checks"]["trial_count"]["stop"] is True
    assert any("trial count" in x for x in r["reasons"]), r["reasons"]
    c.close()


def test_trial_count_below_threshold_does_not_stop():
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 90.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["checks"]["trial_count"]["stop"] is False
    assert r["stop"] is False, r["reasons"]
    c.close()


def test_void_rate_stops():
    c = conn()
    make_promotions(c, total=100, void=40)   # 40% > 25% default
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 90.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["stop"] is True
    assert r["checks"]["diminishing_returns"]["stop"] is True
    assert any("voided" in x for x in r["reasons"]), r["reasons"]
    c.close()


def test_void_rate_below_threshold_does_not_stop():
    c = conn()
    make_promotions(c, total=100, void=5)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 90.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["checks"]["diminishing_returns"]["stop"] is False
    assert r["stop"] is False, r["reasons"]
    c.close()


def test_validation_failures_stop():
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, n=200, passed=40)   # 20% > 5%
    with_coverage({"coverage_pct": 90.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["stop"] is True
    assert r["checks"]["validation_failures"]["stop"] is True
    assert any("random strategies" in x for x in r["reasons"]), r["reasons"]
    c.close()


def test_validation_failures_need_a_sample():
    """Fewer than 100 random controls is not evidence either way."""
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, n=10, passed=10)   # 100% but n < 100
    with_coverage({"coverage_pct": 90.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["checks"]["validation_failures"]["stop"] is False
    assert r["stop"] is False, r["reasons"]
    c.close()


def test_data_quality_stops_on_low_coverage():
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 22.6, "knowable": 5000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["stop"] is True
    dq = r["checks"]["data_quality"]
    assert dq["stop"] is True
    assert dq["value"] is not None
    assert abs(dq["value"] - 0.226) < 1e-9, dq["value"]
    assert any("priceable" in x for x in r["reasons"]), r["reasons"]
    c.close()


def test_data_quality_unmeasurable_is_not_zero():
    """
    The defect: a date before the directory snapshots exist has UNMEASURABLE
    coverage, not 0.0% coverage. It must still stop — an unmeasurable universe
    is not a safe one — but the reason must say which situation it is, and the
    value must be None rather than a fabricated zero.
    """
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 0.0, "knowable": 0})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    dq = r["checks"]["data_quality"]
    assert dq["stop"] is True
    assert dq["value"] is None, (
        "unmeasurable coverage must be None, not 0.0 — unknown is not zero")
    assert "UNMEASURABLE" in dq["detail"], dq["detail"]
    assert any("cannot be measured" in x for x in r["reasons"]), r["reasons"]
    c.close()


def test_data_quality_missing_module_is_unmeasurable():
    """No pit_universe at all is also UNMEASURABLE, and still stops."""
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    without_coverage()
    try:
        r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    finally:
        sys.modules.pop("pit_universe", None)
    dq = r["checks"]["data_quality"]
    assert dq["stop"] is True
    assert dq["value"] is None
    assert "UNMEASURABLE" in dq["detail"], dq["detail"]
    c.close()


def test_data_quality_uses_coverage_pct_not_a_missing_key():
    """
    The first defect: the module read a key that does not exist, so the
    condition never fired. A dict with only `coverage_pct` must be read.
    """
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 95.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    dq = r["checks"]["data_quality"]
    assert dq["stop"] is False, dq["detail"]
    assert abs(dq["value"] - 0.95) < 1e-9, dq["value"]
    c.close()


def test_any_single_condition_is_sufficient():
    """
    Only the trial count is breached; everything else is healthy. The answer
    must still be STOP, and there must be exactly one reason — a second reason
    would mean another condition fired for a reason the fixture did not set up.
    """
    c = conn()
    make_promotions(c, total=100, void=0)
    make_random_control(c, n=200, passed=0)
    with_coverage({"coverage_pct": 99.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 0}))
    assert r["stop"] is True
    assert r["checks"]["trial_count"]["stop"] is True
    assert r["checks"]["diminishing_returns"]["stop"] is False
    assert r["checks"]["data_quality"]["stop"] is False
    assert r["checks"]["validation_failures"]["stop"] is False
    assert len(r["reasons"]) == 1, r["reasons"]
    c.close()


def test_all_conditions_clear_does_not_stop():
    c = conn()
    make_promotions(c, total=100, void=0)
    make_random_control(c, n=200, passed=0)
    with_coverage({"coverage_pct": 99.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    assert r["stop"] is False, r["reasons"]
    assert r["reasons"] == []
    c.close()


def test_thresholds_are_configurable():
    """
    Thresholds come from config, not from the module's defaults. An
    unspecified key must still fall back to DEFAULTS — a config that silently
    zeroed the other thresholds would stop the search for the wrong reason.
    """
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 99.0, "knowable": 1000})
    merged = sc._cfg(cfg(stop_conditions={"max_trials": 10}))
    assert merged["max_trials"] == 10
    assert merged["max_void_rate"] == sc.DEFAULTS["max_void_rate"]
    assert merged["min_universe_coverage"] == sc.DEFAULTS["min_universe_coverage"]
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 0}))
    assert r["stop"] is True
    assert r["thresholds"]["max_trials"] == 0
    c.close()


def test_render_says_do_not_search():
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 99.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 0}))
    assert r["stop"] is True
    out = sc.render(r)
    assert "DO NOT SEARCH" in out
    assert "COLLECT MORE FORWARD DATA" in out
    assert "legitimate output" in out
    c.close()


def test_render_when_not_stopping():
    c = conn()
    make_promotions(c, 0, 0)
    make_random_control(c, 0, 0)
    with_coverage({"coverage_pct": 99.0, "knowable": 1000})
    r = sc.evaluate(c, cfg(stop_conditions={"max_trials": 10_000_000}))
    out = sc.render(r)
    assert "DO NOT SEARCH" not in out
    assert "No stop condition is met" in out
    c.close()


# --------------------------------------------------------------------------
# compute_priority
# --------------------------------------------------------------------------

def test_tier_of_maps_search_last():
    assert cp.TIER_OF["evolve.py"] == (6, "strategy_search")
    assert cp.TIER_OF["lab_loop.sh"] == (6, "strategy_search")
    assert cp.TIER_OF["factory.py"] == (6, "strategy_search")
    assert cp.TIER_OF["universe.py"] == (1, "data_integrity")
    assert cp.TIER_OF["run_tests.sh"] == (3, "regression_tests")
    assert cp.TIER_OF["stop_conditions.py"] == (4, "independent_validation")


def test_tiers_are_ordered_data_first_search_last():
    names = [name for _, name, _ in cp.TIERS]
    assert names[0] == "data_integrity"
    assert names[-1] == "strategy_search"
    assert [n for n, _, _ in cp.TIERS] == sorted(n for n, _, _ in cp.TIERS)


def test_record_writes_the_right_tier():
    c = conn()
    cp.record(c, "evolve.py", 12.5, ok=True)
    row = c.execute("SELECT * FROM compute_log").fetchone()
    assert row["stage"] == "evolve.py"
    assert row["tier"] == 6
    assert row["tier_name"] == "strategy_search"
    assert abs(row["seconds"] - 12.5) < 1e-9
    assert row["ok"] == 1
    c.close()


def test_record_unknown_stage_is_unclassified():
    c = conn()
    cp.record(c, "not_a_real_stage.py", 1.0)
    row = c.execute("SELECT * FROM compute_log").fetchone()
    assert row["tier"] == 99
    assert row["tier_name"] == "unclassified"
    c.close()


def test_record_failure_is_recorded_as_failure():
    c = conn()
    cp.record(c, "universe.py", 3.0, ok=False)
    row = c.execute("SELECT * FROM compute_log").fetchone()
    assert row["ok"] == 0
    c.close()


def test_may_run_true_when_higher_tiers_succeeded():
    c = conn()
    cp.record(c, "universe.py", 10.0, ok=True)
    cp.record(c, "run_tests.sh", 5.0, ok=True)
    ok, why = cp.may_run(c, 6)
    assert ok is True, why
    c.close()


def test_may_run_false_when_a_higher_tier_failed():
    c = conn()
    cp.record(c, "universe.py", 10.0, ok=False)
    ok, why = cp.may_run(c, 6)
    assert ok is False
    assert "data_integrity" in why, why
    c.close()


def test_may_run_ignores_lower_tiers():
    """A failed search must not block the data-integrity work that outranks it."""
    c = conn()
    cp.record(c, "evolve.py", 10.0, ok=False)
    ok, why = cp.may_run(c, 1)
    assert ok is True, why
    c.close()


def test_may_run_true_with_no_history():
    c = conn()
    ok, why = cp.may_run(c, 6)
    assert ok is True
    assert "no higher-priority stage" in why, why
    c.close()


def test_may_run_ignores_work_outside_the_window():
    c = conn()
    cp.init(c)
    c.execute("""INSERT INTO compute_log (at, stage, tier, tier_name, seconds, ok)
                 VALUES (datetime('now', '-72 hours'), 'universe.py', 1,
                         'data_integrity', 10.0, 0)""")
    c.commit()
    ok, why = cp.may_run(c, 6, window_hours=24)
    assert ok is True, why
    c.close()


def test_spend_computes_search_share_and_honoured():
    c = conn()
    cp.record(c, "universe.py", 90.0, ok=True)     # tier 1
    cp.record(c, "evolve.py", 10.0, ok=True)       # tier 6
    s = cp.spend(c, window_hours=24)
    assert abs(s["total_seconds"] - 100.0) < 1e-9
    assert abs(s["search_share"] - 0.10) < 1e-9, s["search_share"]
    assert s["honoured"] is True
    c.close()


def test_spend_flags_search_majority():
    c = conn()
    cp.record(c, "universe.py", 10.0, ok=True)
    cp.record(c, "evolve.py", 90.0, ok=True)
    s = cp.spend(c, window_hours=24)
    assert abs(s["search_share"] - 0.90) < 1e-9, s["search_share"]
    assert s["honoured"] is False
    c.close()


def test_spend_with_no_search_is_honoured():
    c = conn()
    cp.record(c, "universe.py", 10.0, ok=True)
    s = cp.spend(c, window_hours=24)
    assert s["search_share"] == 0.0
    assert s["honoured"] is True
    c.close()


def test_spend_empty_log_does_not_divide_by_zero():
    c = conn()
    s = cp.spend(c, window_hours=24)
    assert s["total_seconds"] == 0.0
    assert s["search_share"] == 0.0
    assert s["honoured"] is True
    c.close()


def test_render_flags_a_search_majority():
    c = conn()
    cp.record(c, "universe.py", 10.0, ok=True)
    cp.record(c, "evolve.py", 90.0, ok=True)
    out = cp.render(cp.spend(c, window_hours=24))
    assert "SEARCH TOOK" in out
    assert "data-quality problem remains" in out
    c.close()


def test_render_when_ordering_is_honoured():
    c = conn()
    cp.record(c, "universe.py", 90.0, ok=True)
    cp.record(c, "evolve.py", 10.0, ok=True)
    out = cp.render(cp.spend(c, window_hours=24))
    assert "SEARCH TOOK" not in out
    assert "ordering is honoured" in out
    c.close()


def main():
    print("\n  STOP CONDITIONS AND COMPUTE PRIORITY")
    print("  " + "-" * 70)

    check("trial count above threshold stops", test_trial_count_stops)
    check("trial count below threshold does not stop",
          test_trial_count_below_threshold_does_not_stop)
    check("void rate above threshold stops", test_void_rate_stops)
    check("void rate below threshold does not stop",
          test_void_rate_below_threshold_does_not_stop)
    check("random strategies clearing the gate stops",
          test_validation_failures_stop)
    check("validation failures need a sample",
          test_validation_failures_need_a_sample)
    check("low coverage stops", test_data_quality_stops_on_low_coverage)
    check("unmeasurable coverage is not zero",
          test_data_quality_unmeasurable_is_not_zero)
    check("missing pit_universe is unmeasurable",
          test_data_quality_missing_module_is_unmeasurable)
    check("coverage_pct is the key that is read",
          test_data_quality_uses_coverage_pct_not_a_missing_key)
    check("any single condition is sufficient",
          test_any_single_condition_is_sufficient)
    check("all conditions clear does not stop",
          test_all_conditions_clear_does_not_stop)
    check("thresholds come from config", test_thresholds_are_configurable)
    check("render says DO NOT SEARCH", test_render_says_do_not_search)
    check("render when not stopping", test_render_when_not_stopping)

    check("TIER_OF maps search last", test_tier_of_maps_search_last)
    check("tiers are ordered data first, search last",
          test_tiers_are_ordered_data_first_search_last)
    check("record writes the right tier", test_record_writes_the_right_tier)
    check("record unknown stage is unclassified",
          test_record_unknown_stage_is_unclassified)
    check("record failure is recorded as failure",
          test_record_failure_is_recorded_as_failure)
    check("may_run true when higher tiers succeeded",
          test_may_run_true_when_higher_tiers_succeeded)
    check("may_run false when a higher tier failed",
          test_may_run_false_when_a_higher_tier_failed)
    check("may_run ignores lower tiers", test_may_run_ignores_lower_tiers)
    check("may_run true with no history", test_may_run_true_with_no_history)
    check("may_run ignores work outside the window",
          test_may_run_ignores_work_outside_the_window)
    check("spend computes search_share and honoured",
          test_spend_computes_search_share_and_honoured)
    check("spend flags a search majority", test_spend_flags_search_majority)
    check("spend with no search is honoured",
          test_spend_with_no_search_is_honoured)
    check("spend empty log does not divide by zero",
          test_spend_empty_log_does_not_divide_by_zero)
    check("render flags a search majority", test_render_flags_a_search_majority)
    check("render when ordering is honoured",
          test_render_when_ordering_is_honoured)

    print("  " + "-" * 70)
    print(f"  {PASSED} passed, {FAILED} failed")
    print("  ALL PASS" if FAILED == 0 else "  FAILURES")
    print("")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
