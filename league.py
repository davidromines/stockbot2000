"""
Strategy identity, immutable versioning and the lifecycle. Phase 7, items 11-12.

WHY IDENTITY IS A MODULE
-------------------------
The project currently identifies a strategy three incompatible ways: `paper_runs`
by a `run_id` with the genome inlined as JSON, `strategies` by a hex id from the
Lab, and `pair_funds` by a name. Nothing can answer "is this the same strategy as
that one" across those, which is exactly the question a league has to answer
before it can rank anything.

Two ideas, deliberately separated:

  **strategy_key** — WHO a strategy is. Stable for its whole life. Survives
  parameter changes, re-registrations and retirement.

  **version** — WHAT it was at a point in time. A material change to the
  definition mints a new version; the old row is never touched.

`definition_hash` decides when a change is material. It covers the fields that
change what the strategy DOES — entry, exit, sizing, holding period, universe —
and deliberately excludes labels, notes and hypothesis text. Renaming a strategy
must not fork its forward record, and editing its rule must not silently inherit
one.

**Nothing here updates a row.** `UPDATE` appears nowhere in this module. A
strategy that changes gets a new version; a strategy that moves state gets a new
transition record. The current state is a query over the transition log, not a
column someone can set. That costs a join and buys an audit trail that cannot be
quietly rewritten — which matters most for exactly the record a bad result would
tempt someone to tidy.

WHAT THIS DOES NOT DO
---------------------
It does not promote anything to live. Phase 7 is explicit that the league must
not be able to call the broker, and there is no code path from here to
`execution.py`.
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
log = logging.getLogger("league")


class LeagueError(RuntimeError):
    pass


# The lifecycle from the Phase 7 specification, in order.
DISCOVERED = "DISCOVERED"
BACKTESTING = "BACKTESTING"
VALIDATING = "VALIDATING"
PAPER = "PAPER"
ELIGIBLE = "ELIGIBLE"
LIVE_CANDIDATE = "LIVE_CANDIDATE"
LIVE = "LIVE"
DEMOTED = "DEMOTED"
SUSPENDED = "SUSPENDED"
RETIRED = "RETIRED"

# Phase 13 §14 lifecycle, added 2026-09-24. The spec prescribes these names
# exactly; the Phase 7 names above stay valid so the append-only log keeps
# meaning what it said. LEGACY_MAP reads an old state in the new vocabulary
# without rewriting a single log row.
SPECIFIED = "SPECIFIED"
BACKTESTED = "BACKTESTED"
VALIDATED = "VALIDATED"
PROMISING = "PROMISING"
QUALIFIED = "QUALIFIED"
REJECTED = "REJECTED"

PHASE13_CHAIN = (DISCOVERED, SPECIFIED, BACKTESTED, VALIDATED, PROMISING,
                 PAPER, QUALIFIED, LIVE_CANDIDATE, LIVE)
FAILURE_STATES = (REJECTED, DEMOTED, RETIRED)
LEGACY_MAP = {BACKTESTING: SPECIFIED, VALIDATING: BACKTESTED,
              ELIGIBLE: QUALIFIED, SUSPENDED: DEMOTED}

STATES = (DISCOVERED, BACKTESTING, VALIDATING, PAPER, ELIGIBLE,
          LIVE_CANDIDATE, LIVE, DEMOTED, SUSPENDED, RETIRED,
          SPECIFIED, BACKTESTED, VALIDATED, PROMISING, QUALIFIED, REJECTED)

# Allowed transitions. Everything not listed is refused.
#
# Three rules are encoded here rather than left to discipline:
#
#   A strategy cannot skip forward. PAPER is reachable only through VALIDATING,
#   so nothing arrives in the arena without having been validated first.
#
#   SUSPENDED is reachable from every live-ish state and returns only to PAPER.
#   An operational halt must not silently restore a strategy to LIVE; it goes
#   back to earning its place.
#
#   RETIRED is terminal. Retired strategies stay in the database — the spec is
#   explicit that nothing disappears for performing badly — but a retired
#   strategy that comes back comes back as a NEW VERSION. Reviving a row would
#   make the state log lie about what happened.
ALLOWED = {
    DISCOVERED:     {BACKTESTING, RETIRED},
    BACKTESTING:    {VALIDATING, RETIRED},
    VALIDATING:     {PAPER, RETIRED},
    PAPER:          {ELIGIBLE, SUSPENDED, RETIRED},
    ELIGIBLE:       {LIVE_CANDIDATE, PAPER, SUSPENDED, RETIRED},
    LIVE_CANDIDATE: {LIVE, ELIGIBLE, SUSPENDED, RETIRED},
    LIVE:           {DEMOTED, SUSPENDED},
    DEMOTED:        {PAPER, ELIGIBLE, RETIRED},
    SUSPENDED:      {PAPER, RETIRED},
    RETIRED:        set(),
}

# Phase 13 §14 transitions. Same rules: no skipping forward, and REJECTED and
# RETIRED are terminal — a failed idea returns as a NEW VERSION (recycling),
# never by reviving its row.
ALLOWED[DISCOVERED] = ALLOWED[DISCOVERED] | {SPECIFIED, REJECTED}
ALLOWED[SPECIFIED] = {BACKTESTED, REJECTED, RETIRED}
ALLOWED[BACKTESTED] = {VALIDATED, REJECTED, RETIRED}
ALLOWED[VALIDATED] = {PROMISING, REJECTED, RETIRED}
ALLOWED[PROMISING] = {PAPER, REJECTED, RETIRED}
ALLOWED[PAPER] = ALLOWED[PAPER] | {QUALIFIED, DEMOTED, REJECTED}
ALLOWED[QUALIFIED] = {LIVE_CANDIDATE, PAPER, DEMOTED, RETIRED}
ALLOWED[LIVE_CANDIDATE] = ALLOWED[LIVE_CANDIDATE] | {QUALIFIED, DEMOTED}
ALLOWED[DEMOTED] = ALLOWED[DEMOTED] | {QUALIFIED}
ALLOWED[REJECTED] = set()


def canonical(state: str | None) -> str | None:
    """A state in the Phase 13 vocabulary (legacy names mapped, not rewritten)."""
    return LEGACY_MAP.get(state, state)

# The fields that change what a strategy DOES. A change to any of these mints a
# new version; a change to anything else does not. Labels and hypothesis text
# are excluded on purpose — renaming must not fork a forward record.
MATERIAL = ("family", "universe", "entry_rule", "exit_rule", "position_sizing",
            "holding_period", "parameters", "required_data")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS league_strategies (
            strategy_key    TEXT NOT NULL,
            version         INTEGER NOT NULL,
            name            TEXT NOT NULL,
            family          TEXT,
            author          TEXT,
            created_at      TEXT NOT NULL,
            parent_key      TEXT,
            ancestry        TEXT,
            hypothesis      TEXT,
            universe        TEXT,
            entry_rule      TEXT,
            exit_rule       TEXT,
            position_sizing TEXT,
            holding_period  TEXT,
            required_data   TEXT,
            parameters      TEXT,
            definition_hash TEXT NOT NULL,
            source_kind     TEXT,
            source_ref      TEXT,
            supersedes      INTEGER,
            PRIMARY KEY (strategy_key, version)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS league_state (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            strategy_key  TEXT NOT NULL,
            version       INTEGER NOT NULL,
            at            TEXT NOT NULL,
            from_state    TEXT,
            to_state      TEXT NOT NULL,
            reason        TEXT NOT NULL,
            actor         TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_ls_key ON league_state(strategy_key)")
    conn.execute("CREATE INDEX IF NOT EXISTS ix_lstr_hash "
                 "ON league_strategies(definition_hash)")
    conn.commit()


def definition_hash(spec: dict) -> str:
    """
    Content hash over the material fields only.

    Missing keys hash as null rather than being skipped, so adding a field to a
    definition changes the hash. Skipping them would make {entry: X} and
    {entry: X, exit: Y} collide the moment exit was introduced.
    """
    material = {k: spec.get(k) for k in MATERIAL}
    return hashlib.sha256(
        json.dumps(material, sort_keys=True, default=str).encode()).hexdigest()[:16]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def register(conn, strategy_key: str, name: str, spec: dict,
             author: str = "system", source_kind: str | None = None,
             source_ref: str | None = None, parent_key: str | None = None,
             ancestry: list | None = None, hypothesis: str = "") -> dict:
    """
    Register a strategy, or mint a new version if its definition changed.

    Re-registering an unchanged strategy returns the existing version rather
    than creating a duplicate. That makes registration idempotent, which the
    project requires of every pipeline stage and which a migration run twice
    would otherwise violate by forking every strategy in the arena.
    """
    init(conn)
    h = definition_hash(spec)
    rows = conn.execute(
        "SELECT * FROM league_strategies WHERE strategy_key=? ORDER BY version DESC",
        (strategy_key,)).fetchall()
    if rows:
        latest = dict(rows[0])
        if latest["definition_hash"] == h:
            return latest
        version = latest["version"] + 1
        supersedes = latest["version"]
    else:
        version = 1
        supersedes = None

    row = {
        "strategy_key": strategy_key, "version": version, "name": name,
        "family": spec.get("family"), "author": author, "created_at": _now(),
        "parent_key": parent_key,
        "ancestry": json.dumps(ancestry or [], sort_keys=True),
        "hypothesis": hypothesis,
        "universe": json.dumps(spec.get("universe"), sort_keys=True, default=str),
        "entry_rule": json.dumps(spec.get("entry_rule"), sort_keys=True, default=str),
        "exit_rule": json.dumps(spec.get("exit_rule"), sort_keys=True, default=str),
        "position_sizing": json.dumps(spec.get("position_sizing"), sort_keys=True, default=str),
        "holding_period": json.dumps(spec.get("holding_period"), sort_keys=True, default=str),
        "required_data": json.dumps(spec.get("required_data"), sort_keys=True, default=str),
        "parameters": json.dumps(spec.get("parameters"), sort_keys=True, default=str),
        "definition_hash": h, "source_kind": source_kind, "source_ref": source_ref,
        "supersedes": supersedes,
    }
    cols = ",".join(row)
    ph = ",".join("?" * len(row))
    conn.execute(f"INSERT INTO league_strategies ({cols}) VALUES ({ph})",
                 tuple(row.values()))
    conn.commit()
    if version > 1:
        log.info(f"{strategy_key}: definition changed, minted v{version} "
                 f"(v{supersedes} left intact)")
    return row


def versions(conn, strategy_key: str) -> list:
    init(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM league_strategies WHERE strategy_key=? ORDER BY version",
        (strategy_key,))]


def latest(conn, strategy_key: str) -> dict:
    vs = versions(conn, strategy_key)
    if not vs:
        raise LeagueError(f"no strategy registered under {strategy_key!r}")
    return vs[-1]


def state(conn, strategy_key: str, version: int | None = None) -> str | None:
    """
    The current state, derived from the transition log rather than stored.

    A stored column is a thing someone can set; a log is a thing someone has to
    append to. For the record that decides what gets real money, the difference
    is the whole point.
    """
    init(conn)
    if version is None:
        r = conn.execute("SELECT to_state FROM league_state WHERE strategy_key=? "
                         "ORDER BY id DESC LIMIT 1", (strategy_key,)).fetchone()
    else:
        r = conn.execute("SELECT to_state FROM league_state WHERE strategy_key=? "
                         "AND version=? ORDER BY id DESC LIMIT 1",
                         (strategy_key, version)).fetchone()
    return r[0] if r else None


def transition(conn, strategy_key: str, to_state: str, reason: str,
               version: int | None = None, actor: str = "system") -> dict:
    """
    Move a strategy to a new state, or refuse.

    A reason is required. A state log whose entries do not say why is a list of
    timestamps, and the question anyone asks of it later is always "why did this
    get demoted", never "when".
    """
    init(conn)
    if to_state not in STATES:
        raise LeagueError(f"{to_state!r} is not a lifecycle state; have {list(STATES)}")
    if not reason.strip():
        raise LeagueError("a transition needs a reason — 'why' is the only "
                          "question anyone asks of a state log later")
    if version is None:
        version = latest(conn, strategy_key)["version"]

    cur = state(conn, strategy_key, version)
    if cur is None:
        # First entry. Only DISCOVERED is a legitimate starting point for a new
        # strategy; a migration of an existing forward record enters at PAPER
        # and says so explicitly.
        if to_state not in (DISCOVERED, PAPER):
            raise LeagueError(
                f"{strategy_key} has no state yet, so it cannot enter at "
                f"{to_state}. A new strategy starts at DISCOVERED; an existing "
                f"forward record migrates in at PAPER.")
    elif to_state not in ALLOWED[cur]:
        raise LeagueError(
            f"{strategy_key} cannot go {cur} -> {to_state}. "
            f"Allowed from {cur}: {sorted(ALLOWED[cur]) or 'nothing (terminal)'}")

    conn.execute("""INSERT INTO league_state (strategy_key, version, at,
        from_state, to_state, reason, actor) VALUES (?,?,?,?,?,?,?)""",
        (strategy_key, version, _now(), cur, to_state, reason, actor))
    conn.commit()
    return {"strategy_key": strategy_key, "version": version, "from": cur,
            "to": to_state, "reason": reason}


def history(conn, strategy_key: str) -> list:
    init(conn)
    return [dict(r) for r in conn.execute(
        "SELECT * FROM league_state WHERE strategy_key=? ORDER BY id",
        (strategy_key,))]


def roster(conn, in_state: str | None = None) -> list:
    """Every strategy with its current state. The league's membership list."""
    init(conn)
    out = []
    for r in conn.execute("SELECT DISTINCT strategy_key FROM league_strategies"):
        key = r[0]
        try:
            v = latest(conn, key)
        except LeagueError:
            continue
        st = state(conn, key)
        if in_state and st != in_state:
            continue
        out.append({"strategy_key": key, "name": v["name"], "family": v["family"],
                    "version": v["version"], "state": st,
                    "source_kind": v["source_kind"], "source_ref": v["source_ref"]})
    return sorted(out, key=lambda x: (x["state"] or "", x["name"]))


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roster", action="store_true")
    ap.add_argument("--state", metavar="STRATEGY_KEY")
    ap.add_argument("--states", action="store_true",
                    help="print the lifecycle and its allowed transitions")
    a = ap.parse_args()

    if a.states:
        print("\n  STRATEGY LIFECYCLE")
        print("  " + "-" * 62)
        for s in STATES:
            nxt = sorted(ALLOWED[s])
            print(f"  {s:<16} -> {', '.join(nxt) if nxt else '(terminal)'}")
        return 0

    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.state:
        v = latest(conn, a.state)
        print(f"\n  {a.state}  v{v['version']}  {v['name']}")
        print(f"  state: {state(conn, a.state)}")
        print("  " + "-" * 62)
        for h in history(conn, a.state):
            print(f"  {h['at']}  {str(h['from_state'] or '-'):<14} -> "
                  f"{h['to_state']:<14} {h['reason'][:34]}")
        conn.close(); return 0

    rows = roster(conn)
    print(f"\n  STRATEGY LEAGUE — {len(rows)} strategies")
    print("  " + "-" * 74)
    print(f"  {'name':<26}{'family':<14}{'state':<16}{'v':>3}  source")
    for r in rows:
        print(f"  {(r['name'] or '')[:25]:<26}{(r['family'] or '-')[:13]:<14}"
              f"{str(r['state'] or 'NO STATE'):<16}{r['version']:>3}  "
              f"{r['source_kind'] or '-'}")
    if not rows:
        print("  empty — run migrate_league.py to bring the forward record in")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
