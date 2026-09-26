"""
paper_all.py: every strategy without a forward fund gets one, with no lifecycle
change; a strategy it tracked still reaches PAPER through the pipeline on the
same fund. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import factory_pipeline as fp
import league
import leagues
import paper_all
import paper_trading
import strategy_objects as so

FAILED = []
CFG = {"risk": {"position_size_usd": 20, "max_open_positions": 5}}
G = {"entry": {"col": "close"}, "exit": {"col": "close"}, "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def reg(conn, key):
    so.register(conn, {"strategy_key": key, "name": key.upper(), "family": "fam", "league": "momentum",
                       "genome": G, "parameters": {}, "data_requirements": ["features"]})


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    conn.execute("INSERT INTO prices VALUES ('AAA', '2026-09-25', 10.0)")
    so.init(conn); leagues.init(conn); paper_trading.init(conn)
    reg(conn, "fx_new")
    reg(conn, "fx_bad")
    so.decide(conn, "fx_bad", 1, "REJECT", "test", to_state=league.REJECTED)
    s0 = {k: league.state(conn, k, 1) for k in ("fx_new", "fx_bad")}
    r = paper_all.run(conn, CFG)
    check("both untracked strategies enrolled", r["untracked"] == 2 and sum(r["enrolled_by_state"].values()) == 2, r)
    check("each has a linked fund", all(leagues.fund_ref(conn, k, 1) for k in ("fx_new", "fx_bad")))
    check("no lifecycle change", {k: league.state(conn, k, 1) for k in s0} == s0)
    lab = conn.execute("SELECT label FROM paper_runs p JOIN factory_paper_link l ON l.run_id=p.run_id "
                       "WHERE l.strategy_key='fx_new'").fetchone()[0]
    check("fund labelled with the strategy's name", lab == "FX_NEW", lab)
    again = paper_all.run(conn, CFG)
    check("idempotent: nothing enrolled twice", again["untracked"] == 0, again)
    fund = leagues.fund_ref(conn, "fx_new", 1)[1]
    for st in (league.SPECIFIED, league.BACKTESTED, league.VALIDATED, league.PROMISING):
        so.decide(conn, "fx_new", 1, "PROMOTE", "walk", to_state=st)
    rid = fp.enroll(conn, CFG, "fx_new", 1, {"family": "fam"}, G)
    check("pipeline enrol reuses the tracked fund", rid == fund, (rid, fund))
    check("and still moves the strategy to PAPER", league.canonical(league.state(conn, "fx_new", 1)) == league.PAPER,
          league.state(conn, "fx_new", 1))
    check("re-enrol of a PAPER strategy is a no-op", fp.enroll(conn, CFG, "fx_new", 1, {"family": "fam"}, G) == fund)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
