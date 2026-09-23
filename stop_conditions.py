"""
When should the search stop? Phase 6 section 27.

The spec says the system must be able to produce this output, and treat it as
a legitimate answer rather than a failure:

    DO NOT SEARCH
    COLLECT MORE FORWARD DATA

Four conditions, any one of which is sufficient:

    trial count exceeds its configured threshold
    research has reached diminishing returns
    data quality is insufficient
    validation failures exceed their threshold

Each is evaluated from the live database rather than asserted. The trial
ledger is append-only, so the first condition is permanent once crossed: 1.03M
trials do not become fewer by archiving strategies, and the multiple-testing
bar they created does not come down.

The useful property here is that this module can say STOP while the search
would happily continue. A search that stops only when it fails has no way to
notice that it is succeeding at the wrong thing.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import multiple_testing as mt
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("stop")

DEFAULTS = {
    "max_trials": 1_000_000,
    # Survivors that later prove to be artifacts, as a share of survivors. The
    # project's own record is that essentially all of them were.
    "max_void_rate": 0.25,
    # Below this fraction of the knowable universe, a backtest is measuring a
    # sample that excludes the failures. 2008 coverage here is 22.6%.
    "min_universe_coverage": 0.60,
    # Forward marks the league needs before a ranking means anything.
    "min_forward_marks": 60,
}


def _cfg(cfg: dict) -> dict:
    out = dict(DEFAULTS)
    out.update((cfg.get("search") or {}).get("stop_conditions", {}) or {})
    return out


def evaluate(conn, cfg: dict) -> dict:
    """Every condition, with the number behind it."""
    c = _cfg(cfg)
    reasons, checks = [], {}

    trials = mt.count(conn)["total_trials"]
    hit = trials >= c["max_trials"]
    checks["trial_count"] = {"value": trials, "threshold": c["max_trials"],
                             "stop": hit,
                             "detail": f"{trials:,} cumulative trials against a "
                                       f"threshold of {c['max_trials']:,}"}
    if hit:
        reasons.append(f"trial count {trials:,} exceeds {c['max_trials']:,}; the "
                       f"ledger is append-only so this does not come down")

    # Diminishing returns: survivors that were later voided.
    try:
        tot = conn.execute("SELECT COUNT(*) FROM promotions "
                           "WHERE stage='validation'").fetchone()[0]
        void = conn.execute("SELECT COUNT(*) FROM promotions WHERE "
                            "stage='validation' AND decision='void'").fetchone()[0]
    except Exception:      # noqa: BLE001
        tot = void = 0
    rate = (void / tot) if tot else 0.0
    hit = tot > 0 and rate >= c["max_void_rate"]
    checks["diminishing_returns"] = {
        "value": rate, "threshold": c["max_void_rate"], "stop": hit,
        "detail": f"{void} of {tot} validation survivors were later voided "
                  f"({rate:.0%})"}
    if hit:
        reasons.append(f"{rate:.0%} of validation survivors were later voided; "
                       f"more search produces more artifacts, not more edge")

    # Data quality: point-in-time universe coverage at the search window's start.
    cov = None
    try:
        import pit_universe
        cov = pit_universe.coverage(conn, cfg["lab"]["search_start"])
        # The key is `coverage_pct` and it is a PERCENT, not a fraction. The
        # first version read a non-existent "coverage" key, so this condition
        # silently never fired — a stop condition that cannot evaluate is worse
        # than one that is absent, because the report shows it as passing.
        pct = cov.get("coverage_pct") if isinstance(cov, dict) else None
        frac = (pct / 100.0) if pct is not None else None
    except Exception:      # noqa: BLE001
        frac = None
    # A coverage of 0.0% almost always means UNMEASURABLE rather than
    # catastrophic: the Internet Archive snapshots begin in 2008 and the search
    # window opens in 2006, so there is no directory to compare against. The
    # first version reported that as "0.0% of the universe is priceable", which
    # is the unknown-as-zero substitution this project keeps rediscovering.
    #
    # It still stops — an unmeasurable universe is not a safe one — but the
    # reason says which of the two situations it is.
    knowable = cov.get("knowable") if isinstance(cov, dict) else None
    unmeasurable = frac is None or not knowable
    hit = unmeasurable or frac < c["min_universe_coverage"]
    checks["data_quality"] = {
        "value": None if unmeasurable else frac,
        "threshold": c["min_universe_coverage"], "stop": hit,
        "detail": ("coverage is UNMEASURABLE at "
                   f"{cfg['lab']['search_start']} — no directory snapshot "
                   f"exists before it" if unmeasurable else
                   f"{frac:.1%} of the knowable universe is priceable at "
                   f"{cfg['lab']['search_start']}")}
    if hit and unmeasurable:
        reasons.append(f"universe coverage cannot be measured at "
                       f"{cfg['lab']['search_start']}: the directory snapshots "
                       f"begin in 2008 and the search window opens earlier. "
                       f"Unknown coverage is treated as insufficient, not as "
                       f"acceptable")
    elif hit:
        reasons.append(f"only {frac:.1%} of the knowable universe is priceable at "
                       f"the start of the search window; a backtest there is "
                       f"measuring the survivors")

    # Validation failures: random strategies clearing the gate.
    try:
        n = conn.execute("SELECT COUNT(*) FROM random_control").fetchone()[0]
        passed = conn.execute("SELECT COALESCE(SUM(passed_gate),0) "
                              "FROM random_control").fetchone()[0]
    except Exception:      # noqa: BLE001
        n = passed = 0
    fp = (passed / n) if n else 0.0
    hit = n >= 100 and fp > 0.05
    checks["validation_failures"] = {
        "value": fp, "threshold": 0.05, "stop": hit,
        "detail": f"{passed} of {n} random strategies cleared the gate ({fp:.1%})"}
    if hit:
        reasons.append(f"{fp:.1%} of random strategies clear the validation gate; "
                       f"the gate is admitting noise")

    return {"stop": bool(reasons), "reasons": reasons, "checks": checks,
            "thresholds": c}


def render(r: dict) -> str:
    L = ["", "  SEARCH STOP CONDITIONS", "  " + "-" * 70]
    for name, c in r["checks"].items():
        mark = "STOP" if c["stop"] else "ok  "
        L.append(f"  {mark} {name:<22}{c['detail'][:44]}")
    L.append("  " + "-" * 70)
    if r["stop"]:
        L += ["", "  DO NOT SEARCH", "  COLLECT MORE FORWARD DATA", ""]
        for x in r["reasons"]:
            L.append(f"  - {x}")
        L += ["", "  This is a legitimate output, not a failure. Forward time is",
              "  the only measurement here with no survivorship bias and no",
              "  look-ahead, and it accrues at one day per day whatever the",
              "  search does."]
    else:
        L += ["", "  No stop condition is met. Search may proceed under the",
              "  governance in factory.py, which is a separate question."]
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    r = evaluate(conn, cfg)
    if a.json:
        import json as _j
        print(_j.dumps(r, indent=2, default=str))
    else:
        print(render(r))
    conn.close()
    # Non-zero when the answer is STOP, so a pipeline stage can act on it.
    return 1 if r["stop"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
