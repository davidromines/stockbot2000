"""
Paper-track every strategy idea (owner, 2026-09-26: "I don't want to lose any
paper tracking of ideas").

The factory pipeline enrols a strategy in paper trading only after it passes
backtest, validation and robustness — 12 a day — so 229 discovered strategies
(including the slot holders the ranking picks from backtests) had no forward
record, and 42 rejected ones would never get one. A forward record accrues only
in calendar time and cannot be back-filled, so every idea gets a paper fund now.

Enrolment here records NO lifecycle change: a DISCOVERED strategy stays
DISCOVERED and still goes through the pipeline; a REJECTED one stays REJECTED
(out of the slots) while its forward record keeps accruing. The fund is linked
through factory_paper_link, so leagues.fund_ref / ranking.py read its evidence
like any other. Idempotent: a strategy with a fund is skipped.

    ./venv/bin/python paper_all.py [--dry-run]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
import sqlite3
import sys

import leagues
import paper_trading
import strategy_objects as so

log = logging.getLogger("paper_all")


def untracked(conn) -> list:
    """(key, version, state, name) for every strategy version with no forward fund."""
    rows = conn.execute("""
        SELECT s.strategy_key, s.version, s.to_state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state
              GROUP BY strategy_key, version) m ON m.mid = s.id""").fetchall()
    out = []
    for key, ver, state in rows:
        # RETIRED is a deliberate removal (a duplicate, or a withdrawn idea), not an
        # untested one: it keeps any record it has but gets no new fund.
        if state == "RETIRED":
            continue
        if leagues.fund_ref(conn, key, ver) is not None:
            continue
        name = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                             (key, ver)).fetchone() or [key])[0]
        out.append((key, ver, state, name))
    return out


def enrol(conn, cfg, key: str, ver: int, name: str) -> str | None:
    g = so.genome(conn, key, ver)
    if not g:
        return None
    m = so.meta(conn, key, ver) or {}
    run_id = paper_trading.start(conn, cfg, name=f"{key} v{ver}", strategy=json.dumps(g, sort_keys=True))
    conn.execute("UPDATE paper_runs SET label=?, family=? WHERE run_id=?",
                 (str(name)[:60], m.get("family"), run_id))
    conn.execute("INSERT INTO factory_paper_link VALUES (?,?,?,?)", (key, ver, run_id, dt.date.today().isoformat()))
    conn.commit()
    return run_id


def run(conn, cfg, dry_run: bool = False) -> dict:
    leagues.init(conn)
    paper_trading.init(conn)
    todo = untracked(conn)
    done, no_genome = {}, []
    for key, ver, state, name in todo:
        if dry_run:
            done[state] = done.get(state, 0) + 1
            continue
        if enrol(conn, cfg, key, ver, name):
            done[state] = done.get(state, 0) + 1
        else:
            no_genome.append(f"{key} v{ver}")
    return {"untracked": len(todo), "enrolled_by_state": done, "no_genome": no_genome, "dry_run": dry_run}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    print(json.dumps(run(conn, cfg, a.dry_run), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
