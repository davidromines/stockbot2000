"""
Paper-track every strategy that survived the Lab's out-of-sample validation
(owner, 2026-09-27: "do paper tracking on all survivors. this should have been
implemented from the start").

Stage T found the gap: 953 search strategies passed the 2020-2022 validation
gate (649 of them under the honest simulator — next-open fills, true exits),
and none was ever paper-traded, sealed-tested or ranked. `lab_loop.sh` promoted
at most a handful per run, and the search was frozen before most runs reached
that step. A forward record accrues only in calendar time, so every survivor
gets a paper fund now.

Each survivor gets:
  - a paper fund named lab_<id8> (the prefix ranking.from_search reads: a
    search strategy scores on its paper record only, never its backtest);
  - a league identity paper:<run_id> at PAPER, source_kind 'lab_validation',
    source_ref = the Lab strategy id, ancestry = seed classification + parent;
  - its validation evidence and simulator era in the hypothesis text.

No gate is changed and nothing reaches a slot except through ranking.py.
Idempotent: a survivor that already has a lab_<id8> fund is skipped.

    ./venv/bin/python lab_survivors.py [--dry-run]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys

log = logging.getLogger("lab_survivors")
ACTOR = "lab_survivors"
FAMILY = "lab_search"
# Next-open fills landed 2026-09-15 (exit pricing on 09-12); validation run
# before this date used a simulator since superseded.
HONEST_FROM = "2026-09-16"


def survivors(conn) -> list:
    """Every Lab strategy that passed validation, best out-of-sample excess first."""
    rows = conn.execute("""
        SELECT s.id, s.genome, s.entry_desc, s.exit_desc, s.parent_id, p.evidence, p.decided_at
        FROM promotions p JOIN strategies s ON s.id = p.strategy_id
        WHERE p.stage = 'validation' AND p.decision = 'pass'""").fetchall()
    out = []
    for sid, genome, entry, exit_, parent, ev, at in rows:
        e = json.loads(ev or "{}")
        out.append({"id": sid, "genome": genome, "entry": entry or "", "exit": exit_ or "",
                    "parent": parent, "evidence": e, "decided_at": at,
                    "honest": (at or "")[:10] >= HONEST_FROM})
    out.sort(key=lambda r: -(r["evidence"].get("excess_pnl_usd") or 0))
    return out


def _seed(conn, sid: str) -> str:
    try:
        r = conn.execute("SELECT seed_origin FROM strategy_ancestry WHERE strategy_id=?", (sid,)).fetchone()
    except sqlite3.Error:
        return "UNCLASSIFIED"
    return r[0] if r else "UNCLASSIFIED"


def hypothesis(s: dict, seed: str) -> str:
    e = s["evidence"]
    n = int(e.get("n_trades") or 0)
    size = 20.0
    per = (e.get("net_pnl_usd") or 0) / (n * size) * 100 if n else 0.0
    era = "honest simulator" if s["honest"] else "SUPERSEDED simulator (close fills) — treat as unvalidated"
    return (f"Lab search survivor {s['id']}: passed validation "
            f"{(e.get('window') or ['2020-01-01', '2022-12-31'])[0]}..{(e.get('window') or ['', '2022-12-31'])[1]} "
            f"on {s['decided_at'][:10]} ({era}); net {per:+.2f}%/trade over {n} trades, "
            f"excess over null ${e.get('excess_pnl_usd') or 0:+,.0f}, Sharpe {e.get('sharpe') or 0:.2f}; "
            f"ancestry {seed}. Scores on paper only (search strategy).")


def enrol(conn, cfg, s: dict) -> str | None:
    import league
    import migrate_league
    import paper_trading
    name = f"lab_{s['id'][:8]}"
    if conn.execute("SELECT 1 FROM paper_runs WHERE name=?", (name,)).fetchone():
        return None
    label = f"Lab {s['id'][:6]}: {s['entry']}"[:60]
    run_id = paper_trading.start(conn, cfg, name, strategy=s["genome"])
    conn.execute("UPDATE paper_runs SET label=?, family=? WHERE run_id=?", (label, FAMILY, run_id))
    conn.commit()
    run = {"strategy": s["genome"], "family": FAMILY, "capital_usd": None}
    seed = _seed(conn, s["id"])
    key = f"paper:{run_id}"
    league.register(conn, key, label, migrate_league._paper_spec(run), author=ACTOR,
                    source_kind="lab_validation", source_ref=s["id"], parent_key=None,
                    ancestry=[x for x in (s["parent"], seed) if x], hypothesis=hypothesis(s, seed))
    league.transition(conn, key, "PAPER", "Lab validation survivor enrolled for paper tracking "
                      "(owner 2026-09-27)", actor=ACTOR)
    return run_id


def run(conn, cfg, dry_run: bool = False) -> dict:
    import paper_trading
    import league
    paper_trading.init(conn)
    league.init(conn)
    todo = [s for s in survivors(conn)
            if not conn.execute("SELECT 1 FROM paper_runs WHERE name=?", (f"lab_{s['id'][:8]}",)).fetchone()]
    out = {"survivors": len(survivors(conn)), "to_enrol": len(todo),
           "honest": sum(s["honest"] for s in todo), "superseded": sum(not s["honest"] for s in todo),
           "enrolled": 0, "dry_run": dry_run}
    if dry_run:
        return out
    for s in todo:
        if enrol(conn, cfg, s):
            out["enrolled"] += 1
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Paper-track every Lab validation survivor.")
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s:%(name)s:%(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    print(json.dumps(run(conn, cfg, a.dry_run), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
