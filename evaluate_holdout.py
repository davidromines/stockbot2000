"""
The only process permitted to read the sealed window. Phase 6 section 10.

WHY A SEPARATE PROCESS
-----------------------
The sealed window is currently readable by anything with a database handle. The
rule that it may be touched once per strategy is enforced in `promote.py` by
refusing a second *recorded* evaluation — but nothing stops a curious query, and
a peek that leaves no record is the one that does the damage. You cannot un-see
a result, and a human who has seen the sealed window cannot honestly claim their
next decision was uninfluenced by it.

So the holdout gets its own frozen, read-only snapshot and its own entry point.
The normal research process does not import this module. If it ever needs to,
that is the signal that something has gone wrong.

WHAT IS ENFORCED, AND WHAT IS NOT
----------------------------------
Enforced: the snapshot is a separate read-only file with a recorded hash; every
evaluation is logged with the strategy id and a timestamp; a second evaluation
of the same strategy is refused and the refusal is recorded.

Not enforced: a determined person can open the main database and query the same
dates. This is a guard rail, not a sandbox — the realistic failure is idle
curiosity, and a guard rail stops that. Genuine isolation would need a separate
account or machine, which is recorded in the firewall as an open defect.

**Every evaluation is permanent.** There is no delete path. An evaluation that
produced a disappointing number still counts as a look, and removing it would be
the file-drawer problem applied to the one window that cannot be re-used.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import storage
import truth_set
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("holdout")


class SealError(RuntimeError):
    pass


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS holdout_log (
            strategy_id     TEXT NOT NULL,
            attempt         INTEGER NOT NULL,
            at              TEXT NOT NULL,
            truth_version   TEXT,
            permitted       INTEGER NOT NULL,
            reason          TEXT NOT NULL,
            results         TEXT,
            PRIMARY KEY (strategy_id, attempt)
        ) STRICT
    """)
    conn.commit()


def attempts(conn, strategy_id: str) -> int:
    init(conn)
    return conn.execute("SELECT COUNT(*) FROM holdout_log WHERE strategy_id=?",
                        (strategy_id,)).fetchone()[0]


def _record(conn, strategy_id: str, permitted: bool, reason: str,
            truth_version: str | None = None, results: dict | None = None) -> None:
    """
    Log every attempt, permitted or not.

    A refused attempt is logged too, deliberately: a pattern of refused attempts
    on one strategy is itself evidence about how a decision was reached, and
    hiding it would defeat the purpose.
    """
    init(conn)
    n = attempts(conn, strategy_id) + 1
    conn.execute("""INSERT INTO holdout_log (strategy_id, attempt, at,
        truth_version, permitted, reason, results) VALUES (?,?,?,?,?,?,?)""",
        (strategy_id, n, datetime.now(timezone.utc).isoformat(timespec="seconds"),
         truth_version, 1 if permitted else 0, reason,
         json.dumps(results, sort_keys=True) if results else None))
    conn.commit()


def may_evaluate(conn, strategy_id: str) -> tuple:
    """(permitted, reason). One permitted evaluation per strategy, ever."""
    init(conn)
    prior = conn.execute(
        "SELECT attempt, at FROM holdout_log WHERE strategy_id=? AND permitted=1 "
        "ORDER BY attempt LIMIT 1", (strategy_id,)).fetchone()
    if prior:
        return False, (f"already evaluated against the sealed window on "
                       f"{prior['at']}. There is no second evaluation — every "
                       f"peek costs statistical validity and there is no way "
                       f"to un-peek.")
    return True, "first evaluation"


SEALED_PREFIX = "sealed_"


def sealed_versions() -> list:
    """The sealed snapshots, newest name last."""
    return sorted(v for v in truth_set.load_manifest()["versions"]
                  if v.startswith(SEALED_PREFIX))


def _require_sealed(truth_version: str) -> None:
    """
    Refuse to spend an evaluation on anything but a sealed snapshot.

    Without this the single most costly operation in the project is one typo
    from being wasted: pass "v1" and the strategy burns its one and only look
    against data the search has already seen thousands of times, learning
    nothing and leaving no way to get the look back.
    """
    if not truth_version.startswith(SEALED_PREFIX):
        raise SealError(
            f"{truth_version!r} is not a sealed snapshot. An evaluation spends "
            f"a resource that cannot be refilled, and spending it on research "
            f"data buys nothing. Sealed snapshots: {sealed_versions()}")


def evaluate(conn, strategy_id: str, truth_version: str, runner=None) -> dict:
    """
    Evaluate one strategy against the sealed window, once.

    `runner` is injected so the scoring logic stays outside this module: this
    file's job is the seal, not the simulation, and mixing them would make the
    seal harder to audit.
    """
    # Checked before the seal is consulted: a bad version is a caller error, not
    # a look, and must not be logged as an attempt against the strategy.
    _require_sealed(truth_version)

    ok, reason = may_evaluate(conn, strategy_id)
    if not ok:
        _record(conn, strategy_id, False, reason, truth_version)
        raise SealError(reason)

    tconn = truth_set.open_version(truth_version)   # verifies the hash first
    try:
        results = runner(tconn) if runner else {"note": "no runner supplied"}
    finally:
        tconn.close()

    _record(conn, strategy_id, True, "evaluated", truth_version, results)
    log.warning(f"{strategy_id} has now used its ONE sealed evaluation against "
                f"truth set {truth_version}. This cannot be repeated.")
    return results


def report(conn) -> list:
    init(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM holdout_log ORDER BY at DESC")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--snapshots", action="store_true",
                    help="list the sealed snapshots available")
    ap.add_argument("--check", metavar="STRATEGY_ID")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.snapshots:
        vs = sealed_versions()
        print(f"\n  SEALED SNAPSHOTS ({len(vs)})")
        for v in vs:
            e = truth_set.load_manifest()["versions"][v]
            print(f"    {v:<14}{e['price_rows']:>12,} bars  "
                  f"{e['window'][0]}..{e['window'][1]}")
        if not vs:
            print("    none — build one with: truth_set.py --build sealed_v1 --sealed")
        conn.close(); return 0

    if a.check:
        ok, reason = may_evaluate(conn, a.check)
        print(f"\n  {a.check}: {'MAY evaluate' if ok else 'REFUSED'}")
        print(f"  {reason}")
        conn.close(); return 0 if ok else 1

    rows = report(conn)
    print(f"\n  SEALED HOLDOUT LOG ({len(rows)} attempts)")
    print("  " + "-" * 66)
    for r in rows:
        print(f"  {r['at']}  {r['strategy_id'][:16]:<18}"
              f"{'permitted' if r['permitted'] else 'REFUSED':<11}{r['reason'][:28]}")
    if not rows:
        print("  no strategy has been evaluated against the sealed window")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
