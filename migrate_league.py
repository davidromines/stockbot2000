"""
Bring the existing forward record into the league. Phase 7, item 13.

WHY THIS RUNS BEFORE THE ARENA IS SCALED
-----------------------------------------
The 16 paper funds and 5 pair funds are the most valuable and least replaceable
data in this project: the only measurement here with no survivorship bias and no
look-ahead, and it accrues at one day per day. Item 13 comes before item 14 for
that reason — migrate the record before changing the thing that writes it.

**This migration moves no data.** `paper_runs`, `paper_equity`, `paper_trades`,
`pair_funds` and `pair_fund_equity` are not read for their rows and never
written. The league registers each fund's IDENTITY and points at the existing
tables through `source_kind` / `source_ref`. Nothing is copied, so nothing can be
copied wrongly, and a bug here cannot damage the forward record — the worst case
is a league row that points somewhere useless.

It is also idempotent: `league.register` returns the existing version when the
definition is unchanged, and a fund already in PAPER is not re-transitioned.
Running it twice is a no-op, which the project requires of every stage and which
matters more than usual here, since the obvious way to "fix" a botched migration
is to run it again.

WHERE EACH FUND ENTERS THE LIFECYCLE
-------------------------------------
At PAPER, not DISCOVERED. These funds are already forward-testing with real
elapsed calendar time behind them, and walking them through DISCOVERED ->
BACKTESTING -> VALIDATING would write a history that did not happen. `league`
permits PAPER as an entry point precisely for this case and records the reason
on the transition.

Usage:
    python migrate_league.py --dry-run
    python migrate_league.py --run
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging

import league as lg
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("migrate")

PAPER_PREFIX = "paper"
PAIR_PREFIX = "pair"


def _paper_spec(run: dict) -> dict:
    """
    The strategy definition behind a paper fund.

    `paper_runs.strategy` holds either a genome as JSON, the literal "model" for
    the classifier, or {"conviction": name} for a screen. All three are real
    strategies and all three belong in the league; the shape is recorded so the
    definition hash distinguishes them rather than collapsing them.
    """
    raw = run.get("strategy") or "model"
    if raw == "model":
        return {"family": "model", "kind": "classifier",
                "entry_rule": "xgboost top_n", "exit_rule": "atr_stop",
                "universe": ["common_stock"], "parameters": {}}
    try:
        g = json.loads(raw)
    except (ValueError, TypeError):
        return {"family": run.get("family") or "unknown", "entry_rule": raw}
    if isinstance(g, dict) and g.get("conviction"):
        return {"family": "conviction", "kind": "screen",
                "entry_rule": f"conviction:{g['conviction']}",
                "exit_rule": "drops out of top 40%",
                "universe": ["common_stock"],
                "parameters": {"screen": g["conviction"]}}
    return {"family": run.get("family") or "lab", "kind": "genome",
            "entry_rule": g.get("entry"), "exit_rule": g.get("exit"),
            "position_sizing": {"usd": run.get("capital_usd")},
            "holding_period": (g.get("risk") or {}).get("max_hold_days"),
            "universe": ["common_stock"], "parameters": g.get("risk")}


def _pair_spec(f: dict) -> dict:
    return {"family": "pair_switching", "kind": "etf_pair",
            "entry_rule": f"hold whichever of {f['bull']}/{f['bear']} is rising",
            "exit_rule": f"switch when {f['signal']} flips",
            "universe": [f["bull"], f["bear"]],
            "holding_period": {"min_hold": f["min_hold"]},
            "parameters": {"signal": f["signal"], "method": f["method"],
                           "param": f["param"], "min_hold": f["min_hold"]}}


def plan(conn) -> list:
    """What would be migrated. Reads only; writes nothing."""
    lg.init(conn)
    items = []
    for r in conn.execute("SELECT * FROM paper_runs ORDER BY label"):
        run = dict(r)
        key = f"{PAPER_PREFIX}:{run['run_id']}"
        items.append({
            "strategy_key": key,
            "name": run.get("label") or run.get("name") or run["run_id"],
            "spec": _paper_spec(run), "source_kind": "paper_runs",
            "source_ref": run["run_id"], "status": run.get("status"),
            "started_on": run.get("started_on"),
            "already": lg.state(conn, key)})
    for r in conn.execute("SELECT * FROM pair_funds ORDER BY label"):
        f = dict(r)
        key = f"{PAIR_PREFIX}:{f['name']}"
        items.append({
            "strategy_key": key,
            "name": f.get("label") or f["name"],
            "spec": _pair_spec(f), "source_kind": "pair_funds",
            "source_ref": f["name"], "status": f.get("status"),
            "started_on": f.get("started_on"),
            "already": lg.state(conn, key)})
    return items


def migrate(conn, dry_run: bool = True) -> dict:
    items = plan(conn)
    registered = transitioned = skipped = 0

    for it in items:
        if dry_run:
            continue
        row = lg.register(
            conn, it["strategy_key"], it["name"], it["spec"],
            author="migration", source_kind=it["source_kind"],
            source_ref=it["source_ref"],
            hypothesis=f"Forward record opened {it['started_on']}; migrated "
                       f"into the league 2026-09-22 without moving any data.")
        registered += 1

        cur = lg.state(conn, it["strategy_key"])
        if cur is not None:
            skipped += 1
            continue
        # An open fund enters at PAPER; a closed one is RETIRED, which it can
        # reach from PAPER but not from nothing, so it takes both steps.
        lg.transition(conn, it["strategy_key"], lg.PAPER,
                      f"migrated with its forward record intact, open since "
                      f"{it['started_on']}", version=row["version"],
                      actor="migration")
        if (it["status"] or "open") != "open":
            lg.transition(conn, it["strategy_key"], lg.RETIRED,
                          f"already closed before migration "
                          f"(status={it['status']})", actor="migration")
        transitioned += 1

    return {"found": len(items), "registered": registered,
            "transitioned": transitioned, "already_in_league": skipped,
            "items": items}


def verify(conn) -> list:
    """
    Confirm the forward record is reachable from the league and unaltered.

    Checks the link rather than the contents: the migration does not touch the
    source tables, so the failure it can actually cause is a league row that
    points at nothing.
    """
    problems = []
    for r in lg.roster(conn):
        kind, ref = r["source_kind"], r["source_ref"]
        if kind == "paper_runs":
            n = conn.execute("SELECT COUNT(*) FROM paper_runs WHERE run_id=?",
                             (ref,)).fetchone()[0]
            eq = conn.execute("SELECT COUNT(*) FROM paper_equity WHERE run_id=?",
                              (ref,)).fetchone()[0]
        elif kind == "pair_funds":
            n = conn.execute("SELECT COUNT(*) FROM pair_funds WHERE name=?",
                             (ref,)).fetchone()[0]
            eq = conn.execute("SELECT COUNT(*) FROM pair_fund_equity WHERE name=?",
                              (ref,)).fetchone()[0]
        else:
            problems.append(f"{r['strategy_key']}: unknown source kind {kind!r}")
            continue
        if n != 1:
            problems.append(f"{r['strategy_key']}: source row not found ({kind}={ref})")
        if eq == 0:
            problems.append(f"{r['strategy_key']}: no equity marks — forward "
                            f"record is empty, not merely unmigrated")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--verify", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    lg.init(conn)

    if a.verify:
        probs = verify(conn)
        print(f"\n  {'ALL LINKS GOOD' if not probs else 'PROBLEMS'}")
        for p in probs:
            print("   ", p)
        conn.close(); return 0 if not probs else 1

    res = migrate(conn, dry_run=not a.run)
    print(f"\n  LEAGUE MIGRATION{'  (DRY RUN — nothing written)' if not a.run else ''}")
    print("  " + "-" * 76)
    print(f"  {'name':<26}{'source':<14}{'ref':<16}{'state'}")
    for it in res["items"]:
        print(f"  {it['name'][:25]:<26}{it['source_kind']:<14}"
              f"{str(it['source_ref'])[:15]:<16}{it['already'] or '(new)'}")
    print("  " + "-" * 76)
    print(f"  found {res['found']}   registered {res['registered']}   "
          f"entered PAPER {res['transitioned']}   already in league "
          f"{res['already_in_league']}")
    if not a.run:
        print("\n  No data is moved by this migration. The league points at the")
        print("  existing tables; the forward record stays where it is.")
        print("  Re-run with --run to apply.")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
