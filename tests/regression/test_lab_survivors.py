"""
lab_survivors.py: every Lab validation survivor gets a lab_<id8> paper fund and a
league identity at PAPER; the ranking treats it as a search strategy (paper-only
score); failures are not enrolled; a second run enrols nothing. In-memory only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import lab_survivors as ls
import league
import ledger
import paper_trading
import ranking

FAILED = []
CFG = {"risk": {"position_size_usd": 20, "max_open_positions": 5}}
G = {"entry": {"col": "close"}, "exit": {"col": "close"}, "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def strat(conn, sid, decision, at, excess):
    conn.execute("INSERT INTO strategies (id, parent_id, run_id, generation, origin, genome, complexity, "
                 "entry_desc, exit_desc, created_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (sid, None, "r1", 1, "random", json.dumps(G), 3, f"entry {sid}", "exit", at))
    ev = {"net_pnl_usd": 40.0, "excess_pnl_usd": excess, "sharpe": 1.1, "n_trades": 100,
          "window": ["2020-01-01", "2022-12-31"]}
    conn.execute("INSERT INTO promotions VALUES (?,?,?,?,?)", (sid, "validation", decision, json.dumps(ev), at))


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    conn.execute("INSERT INTO prices VALUES ('AAA', '2026-09-25', 10.0)")
    ledger.init(conn); paper_trading.init(conn); league.init(conn)
    strat(conn, "aaaaaaaa11", "pass", "2026-09-20T00:00:00", 3000.0)
    strat(conn, "bbbbbbbb22", "pass", "2026-09-13T00:00:00", 5000.0)
    strat(conn, "cccccccc33", "fail", "2026-09-20T00:00:00", 100.0)
    conn.commit()

    dry = ls.run(conn, CFG, dry_run=True)
    check("dry run counts both survivors, enrols none", dry["to_enrol"] == 2 and dry["enrolled"] == 0, dry)
    check("honest vs superseded simulator split", dry["honest"] == 1 and dry["superseded"] == 1, dry)
    r = ls.run(conn, CFG)
    check("both survivors enrolled", r["enrolled"] == 2, r)
    names = {x[0] for x in conn.execute("SELECT name FROM paper_runs")}
    check("fund names use the lab_ prefix", names == {"lab_aaaaaaaa", "lab_bbbbbbbb"}, names)
    check("a validation failure is not enrolled", "lab_cccccccc" not in names)
    rows = conn.execute("SELECT strategy_key, source_kind, source_ref, hypothesis FROM league_strategies").fetchall()
    check("registered in the league as lab_validation", {x[1] for x in rows} == {"lab_validation"}, rows)
    check("source_ref is the Lab strategy id", {x[2] for x in rows} == {"aaaaaaaa11", "bbbbbbbb22"})
    sup = [x[3] for x in rows if x[2] == "bbbbbbbb22"][0]
    check("superseded-simulator survivor is labelled so", "SUPERSEDED" in sup, sup)
    keys = [x[0] for x in rows]
    check("each is at PAPER", all(league.canonical(league.state(conn, k, 1)) == league.PAPER for k in keys))
    check("ranking treats them as search strategies (paper-only score)", all(ranking.from_search(conn, k) for k in keys))
    again = ls.run(conn, CFG)
    check("idempotent: second run enrols nothing", again["to_enrol"] == 0 and again["enrolled"] == 0, again)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
