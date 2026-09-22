"""
Pre-registration: lock an experiment before it runs. Phase 6 sections 11 and 12.

THE PROBLEM IT SOLVES
---------------------
Researcher degrees of freedom. Every choice made *after* seeing a result — which
metric to report, which window, which holding period, whether to re-run with a
different seed — converts a test into a search, and a search that reports itself
as a test.

This project has the pattern in its own history. The momentum+pullback
"convergence" was derived from survivors and reported as a finding in the same
breath; only a separate check revealed it came from a seed. `consensus.py` was
written to split those two steps, and this generalises that discipline to every
experiment.

WHAT LOCKING ACTUALLY MEANS
----------------------------
Once an experiment is REGISTERED, its locked fields cannot change. Not "should
not" — `update()` refuses, and the hash recorded at registration is re-checked
before results may be attached. Changing a locked field requires a NEW version
of the experiment, which appears in the registry alongside the old one.

That last part is the point. The cost of changing your mind is not that you
cannot; it is that the record shows you did. A registry that permitted silent
edits would be a diary, and a diary is not evidence.

STATES
------
    DRAFT       being written; anything may change
    REGISTERED  locked; results may now be attached
    RUNNING     execution started
    COMPLETE    results recorded
    REJECTED    abandoned, with a reason — kept, never deleted

Abandoned experiments stay in the registry. An experiment that disappeared
because it did not work is the file-drawer problem, and this project already has
a rule about that: the trial counter is append-only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
from datetime import datetime, timezone

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("registry")

DRAFT, REGISTERED, RUNNING, COMPLETE, REJECTED = (
    "DRAFT", "REGISTERED", "RUNNING", "COMPLETE", "REJECTED")

TRANSITIONS = {
    DRAFT: {REGISTERED, REJECTED},
    REGISTERED: {RUNNING, REJECTED},
    RUNNING: {COMPLETE, REJECTED},
    COMPLETE: set(),      # terminal: a completed experiment is history
    REJECTED: set(),
}

# The fields that define what is being tested. Changing any of them after
# registration changes the experiment, not its details — which is why a change
# requires a new version rather than an edit.
LOCKED = ("hypothesis", "primary_metric", "universe", "entry_rule", "exit_rule",
          "holding_period", "cost_assumptions", "evaluation_period",
          "data_version", "stopping_rule", "sample_size", "holdout_policy")


class RegistryError(RuntimeError):
    pass


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS experiment_registry (
            experiment_id   TEXT NOT NULL,
            version         INTEGER NOT NULL,
            status          TEXT NOT NULL,
            hypothesis      TEXT NOT NULL,
            researcher      TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            registered_at   TEXT,
            completed_at    TEXT,
            spec            TEXT NOT NULL,
            spec_hash       TEXT NOT NULL,
            results         TEXT,
            conclusion      TEXT,
            supersedes      INTEGER,
            PRIMARY KEY (experiment_id, version)
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_exreg_status "
                 "ON experiment_registry(status)")
    conn.commit()


def _hash(spec: dict) -> str:
    """Hash of the LOCKED fields only. Notes may change; the experiment may not."""
    locked = {k: spec.get(k) for k in LOCKED}
    return hashlib.sha256(json.dumps(locked, sort_keys=True).encode()).hexdigest()


def create(conn, experiment_id: str, hypothesis: str, researcher: str,
           spec: dict) -> dict:
    init(conn)
    if not hypothesis.strip():
        raise RegistryError(
            "an experiment needs a hypothesis. Without one there is nothing to "
            "be wrong about, and a test you cannot fail is not a test.")
    prior = conn.execute("SELECT MAX(version) FROM experiment_registry "
                         "WHERE experiment_id=?", (experiment_id,)).fetchone()[0]
    version = (prior or 0) + 1
    full = {**spec, "hypothesis": hypothesis}
    row = {"experiment_id": experiment_id, "version": version, "status": DRAFT,
           "hypothesis": hypothesis, "researcher": researcher,
           "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
           "spec": json.dumps(full, sort_keys=True), "spec_hash": _hash(full),
           "supersedes": prior}
    conn.execute("""INSERT INTO experiment_registry (experiment_id, version,
        status, hypothesis, researcher, created_at, spec, spec_hash, supersedes)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (row["experiment_id"], row["version"], row["status"], row["hypothesis"],
         row["researcher"], row["created_at"], row["spec"], row["spec_hash"],
         row["supersedes"]))
    conn.commit()
    return row


def get(conn, experiment_id: str, version: int | None = None) -> dict:
    init(conn)
    if version is None:
        r = conn.execute("SELECT * FROM experiment_registry WHERE experiment_id=? "
                         "ORDER BY version DESC LIMIT 1", (experiment_id,)).fetchone()
    else:
        r = conn.execute("SELECT * FROM experiment_registry WHERE experiment_id=? "
                         "AND version=?", (experiment_id, version)).fetchone()
    if not r:
        raise RegistryError(f"no such experiment {experiment_id!r}")
    return dict(r)


def register(conn, experiment_id: str) -> dict:
    """Lock it. After this, the locked fields are fixed for this version."""
    e = get(conn, experiment_id)
    _transition(e, REGISTERED)
    conn.execute("""UPDATE experiment_registry SET status=?, registered_at=?
        WHERE experiment_id=? AND version=?""",
        (REGISTERED, datetime.now(timezone.utc).isoformat(timespec="seconds"),
         experiment_id, e["version"]))
    conn.commit()
    log.info(f"{experiment_id} v{e['version']} REGISTERED — locked fields are now fixed")
    return get(conn, experiment_id)


def update(conn, experiment_id: str, changes: dict) -> dict:
    """
    Edit a DRAFT. Refuses to touch a locked field on a registered experiment.

    The refusal is the feature. `new_version()` is the supported way to change
    your mind, and it leaves both versions in the record.
    """
    e = get(conn, experiment_id)
    spec = json.loads(e["spec"])
    if e["status"] != DRAFT:
        locked_changes = [k for k in changes if k in LOCKED
                          and changes[k] != spec.get(k)]
        if locked_changes:
            raise RegistryError(
                f"{experiment_id} is {e['status']}; cannot change locked fields "
                f"{locked_changes}. Use new_version() — the record should show "
                f"that the experiment changed, not hide it.")
    spec.update(changes)
    conn.execute("""UPDATE experiment_registry SET spec=?, spec_hash=?,
        hypothesis=? WHERE experiment_id=? AND version=?""",
        (json.dumps(spec, sort_keys=True), _hash(spec),
         spec.get("hypothesis", e["hypothesis"]), experiment_id, e["version"]))
    conn.commit()
    return get(conn, experiment_id)


def new_version(conn, experiment_id: str, hypothesis: str, researcher: str,
                spec: dict, reason: str) -> dict:
    """Supersede an experiment. Both versions stay in the registry."""
    row = create(conn, experiment_id, hypothesis, researcher,
                 {**spec, "supersede_reason": reason})
    log.info(f"{experiment_id} v{row['version']} created, superseding "
             f"v{row['supersedes']}: {reason}")
    return row


def _transition(e: dict, new: str) -> None:
    if new not in TRANSITIONS.get(e["status"], set()):
        raise RegistryError(f"illegal transition {e['status']} -> {new} "
                            f"for {e['experiment_id']} v{e['version']}")


def start(conn, experiment_id: str) -> dict:
    e = get(conn, experiment_id); _transition(e, RUNNING)
    conn.execute("UPDATE experiment_registry SET status=? WHERE experiment_id=? "
                 "AND version=?", (RUNNING, experiment_id, e["version"]))
    conn.commit(); return get(conn, experiment_id)


def complete(conn, experiment_id: str, results: dict, conclusion: str) -> dict:
    """
    Attach results. Refuses if the spec changed since registration.

    The hash check is what makes pre-registration mean something: results can
    only be attached to the experiment that was actually registered, not to one
    quietly adjusted in between.
    """
    e = get(conn, experiment_id)
    _transition(e, COMPLETE)
    if _hash(json.loads(e["spec"])) != e["spec_hash"]:
        raise RegistryError(
            f"{experiment_id} v{e['version']} spec has changed since "
            f"registration. Results cannot be attached to an experiment that "
            f"is not the one that was registered.")
    conn.execute("""UPDATE experiment_registry SET status=?, results=?,
        conclusion=?, completed_at=? WHERE experiment_id=? AND version=?""",
        (COMPLETE, json.dumps(results, sort_keys=True), conclusion,
         datetime.now(timezone.utc).isoformat(timespec="seconds"),
         experiment_id, e["version"]))
    conn.commit(); return get(conn, experiment_id)


def reject(conn, experiment_id: str, reason: str) -> dict:
    e = get(conn, experiment_id); _transition(e, REJECTED)
    conn.execute("UPDATE experiment_registry SET status=?, conclusion=? "
                 "WHERE experiment_id=? AND version=?",
                 (REJECTED, reason, experiment_id, e["version"]))
    conn.commit(); return get(conn, experiment_id)


def listing(conn) -> list:
    init(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM experiment_registry ORDER BY created_at DESC")]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--show")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)
    if a.show:
        e = get(conn, a.show)
        print(json.dumps({**e, "spec": json.loads(e["spec"])}, indent=2))
        return 0
    rows = listing(conn)
    print(f"\n  EXPERIMENT REGISTRY ({len(rows)})")
    print("  " + "-" * 74)
    for r in rows:
        print(f"  {r['experiment_id']:<22}v{r['version']:<3}{r['status']:<12}"
              f"{r['hypothesis'][:36]}")
    if not rows:
        print("  empty — no experiment has been pre-registered yet")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
