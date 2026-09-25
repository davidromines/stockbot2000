"""
Regression tests for factory_pipeline.py — Phase 13 H11-H13.

Covers the three things the pipeline can get wrong without failing loudly:
enrolment (idempotent, one link row), forward promotion (backtests admit,
forward evidence qualifies), and the family concentration limit (one live
candidate per family, the best one).

Everything runs against an in-memory database. The pipeline's own init()
helpers create most tables; the few the pipeline reads but does not create
(prices, paper_equity, fund_accounting) are made here.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import accounting
import factory_pipeline as fp
import league
import leagues
import paper_trading
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


CFG = {
    "risk": {"position_size_usd": 20, "max_open_positions": 5},
    "leagues": {
        "momentum": {"min_forward_sessions": 2, "min_closed_trades": 1,
                     "established_sessions": 60, "max_drawdown_pct": 15},
        "tactical": {"min_forward_sessions": 2, "min_closed_trades": 1,
                     "established_sessions": 60, "max_drawdown_pct": 15},
    },
    "league_families": {},
}


def connect():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    # Tables the pipeline reads but does not create. paper_trading.start needs
    # MAX(date) from prices; leagues.evidence needs paper_equity and
    # fund_accounting (accounting.init creates the latter, but only when called).
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    conn.execute("INSERT INTO prices VALUES ('AAA', '2026-09-23', 10.0)")
    conn.execute("""CREATE TABLE paper_equity (
        run_id TEXT, date TEXT, cash_usd REAL, positions_usd REAL,
        equity_usd REAL, open_positions INTEGER)""")
    conn.commit()
    return conn


def make_strategy(conn, key, family, name=None):
    """Register a strategy and walk it to PAPER through the allowed chain."""
    so.register(conn, {
        "strategy_key": key, "name": name or key, "family": family,
        "league": "momentum", "genome": {"entry": {"col": "close"},
                                         "exit": {"col": "close"},
                                         "risk": {"stop_atr_multiple": 2.0,
                                                  "max_hold_days": 20}},
        "parameters": {}, "data_requirements": ["features"],
    })
    for state in (league.SPECIFIED, league.BACKTESTED, league.VALIDATED,
                  league.PROMISING, league.PAPER):
        so.decide(conn, key, 1, "PROMOTE", f"test walk to {state}", to_state=state)
    return key


def give_evidence(conn, key, net_usd, closed_trades, sessions=3):
    """Link a paper run to the strategy and give it accounting + equity rows."""
    run_id = fp.enroll(conn, CFG, key, 1, {"family": key}, {"entry": {}, "exit": {}, "risk": {}})
    for i in range(sessions):
        conn.execute("INSERT INTO paper_equity VALUES (?,?,?,?,?,?)",
                     (run_id, f"2026-09-{10 + i:02d}", 100.0, 0.0, 100.0, 0))
    accounting.init(conn)
    conn.execute("""INSERT INTO fund_accounting
        (as_of, fund_kind, fund_id, capital_usd, gross_usd, costs_realized, costs_open,
         costs_usd, net_usd, equity_restated, closed_trades, cost_basis, reconciled,
         accounting_version, computed_at)
        VALUES ('2026-09-23','paper',?,100.0,?,0.0,0.0,0.0,?,?,?,'modeled',1,1,'now')""",
        (run_id, net_usd, net_usd, 100.0 + net_usd, closed_trades))
    conn.commit()
    return run_id


def test_enroll(conn):
    key = make_strategy(conn, "fx_enroll", "enroll_fam")
    run_id = fp.enroll(conn, CFG, key, 1, {"family": "enroll_fam"},
                       {"entry": {}, "exit": {}, "risk": {}})
    links = conn.execute("SELECT COUNT(*) FROM factory_paper_link WHERE strategy_key=?",
                         (key,)).fetchone()[0]
    check("enroll returns a run_id", bool(run_id))
    check("enroll writes exactly one link row", links == 1, f"got {links}")
    check("enroll moves the strategy to PAPER",
          league.canonical(league.state(conn, key, 1)) == league.PAPER,
          str(league.state(conn, key, 1)))

    again = fp.enroll(conn, CFG, key, 1, {"family": "enroll_fam"},
                      {"entry": {}, "exit": {}, "risk": {}})
    links2 = conn.execute("SELECT COUNT(*) FROM factory_paper_link WHERE strategy_key=?",
                          (key,)).fetchone()[0]
    check("enroll is idempotent (same run_id)", again == run_id, f"{again} != {run_id}")
    check("enroll writes no second link row", links2 == 1, f"got {links2}")


def test_forward_promotion(conn):
    key = make_strategy(conn, "fx_good", "good_fam")
    give_evidence(conn, key, net_usd=5.0, closed_trades=2, sessions=3)
    fp.evaluate_forward(conn, CFG)
    # evaluate_forward() ends by calling promote_candidates(), so a lone
    # qualifying strategy in an uncontested family correctly advances past
    # QUALIFIED to LIVE_CANDIDATE in the same pass. Either is a pass here.
    check("positive forward evidence promotes PAPER to QUALIFIED or beyond",
          league.canonical(league.state(conn, key, 1)) in (league.QUALIFIED,
                                                           league.LIVE_CANDIDATE),
          str(league.state(conn, key, 1)))

    bad = make_strategy(conn, "fx_bad", "bad_fam")
    give_evidence(conn, bad, net_usd=-2.0, closed_trades=2, sessions=3)
    fp.evaluate_forward(conn, CFG)
    check("negative forward evidence stays PAPER",
          league.canonical(league.state(conn, bad, 1)) == league.PAPER,
          str(league.state(conn, bad, 1)))


def test_family_limit(conn):
    # Two QUALIFIED strategies in one family, different net_usd. Only the
    # higher one may become LIVE_CANDIDATE.
    a = make_strategy(conn, "fx_fam_a", "shared_fam", name="Shared A")
    b = make_strategy(conn, "fx_fam_b", "shared_fam", name="Shared B")
    give_evidence(conn, a, net_usd=10.0, closed_trades=2, sessions=3)
    give_evidence(conn, b, net_usd=3.0, closed_trades=2, sessions=3)
    fp.evaluate_forward(conn, CFG)
    # The tests share one connection, so promote_candidates() also returns the
    # earlier test's good_fam winner. Filter to this family before asserting.
    cands = [r for r in fp.promote_candidates(conn, CFG) if r["family"] == "shared_fam"]
    states = {r["strategy_key"]: league.canonical(r["state"]) for r in cands}
    check("only one candidate per family", len(cands) == 1, f"got {len(cands)}")
    check("the higher-net strategy is the candidate",
          cands and cands[0]["strategy_key"] == a, str(states))
    check("the lower-net strategy stays QUALIFIED",
          league.canonical(league.state(conn, b, 1)) == league.QUALIFIED,
          str(league.state(conn, b, 1)))


def test_demotion(conn):
    key = make_strategy(conn, "fx_demote", "demote_fam")
    give_evidence(conn, key, net_usd=5.0, closed_trades=2, sessions=3)
    fp.evaluate_forward(conn, CFG)
    fp.promote_candidates(conn, CFG)
    check("strategy reached LIVE_CANDIDATE before demotion",
          league.canonical(league.state(conn, key, 1)) == league.LIVE_CANDIDATE,
          str(league.state(conn, key, 1)))

    # Accounting falls to a loss. A new row, not an update — the table is
    # append-only and evidence() reads the latest by as_of.
    run_id = conn.execute("SELECT run_id FROM factory_paper_link WHERE strategy_key=?",
                          (key,)).fetchone()[0]
    conn.execute("""INSERT INTO fund_accounting
        (as_of, fund_kind, fund_id, capital_usd, gross_usd, costs_realized, costs_open,
         costs_usd, net_usd, equity_restated, closed_trades, cost_basis, reconciled,
         accounting_version, computed_at)
        VALUES ('2026-09-24','paper',?,100.0,-1.0,0.0,0.0,0.0,-1.0,99.0,2,'modeled',1,1,'now')""",
        (run_id,))
    conn.commit()
    fp.evaluate_forward(conn, CFG)
    check("falling to NOT_ELIGIBLE demotes LIVE_CANDIDATE",
          league.canonical(league.state(conn, key, 1)) == league.DEMOTED,
          str(league.state(conn, key, 1)))


def test_live_candidates(conn):
    rows = fp.live_candidates(conn, CFG)
    states = {league.canonical(r["state"]) for r in rows}
    check("live_candidates returns only LIVE_CANDIDATE or LIVE",
          states <= {league.LIVE_CANDIDATE, league.LIVE}, str(states))


def test_no_broker_import():
    path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "factory_pipeline.py")
    with open(path) as fh:
        src = fh.read()
    check("factory_pipeline does not import broker", "import broker" not in src)
    check("factory_pipeline does not import execution", "import execution" not in src)


def main():
    conn = connect()
    so.init(conn)
    leagues.init(conn)
    paper_trading.init(conn)
    test_enroll(conn)
    test_forward_promotion(conn)
    test_family_limit(conn)
    test_demotion(conn)
    test_live_candidates(conn)
    test_no_broker_import()
    conn.close()
    if FAILED:
        print(f"\n  {len(FAILED)} FAILED")
        return 1
    print("\n  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
