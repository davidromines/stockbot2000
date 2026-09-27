"""
funnel.py (Stage T): factory rejections become structured failure reasons (several per
strategy), a small validation loss is a near miss, the Lab chain counts shortlist and
paper, and nothing in it changes a lifecycle state. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import funnel
import league
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    so.init(conn); league.init(conn); funnel.init(conn)
    ev = {"failures": ["cost_stress", "holding_period"], "tests": {"cost_stress": {"net_usd": -10.0},
                                                                   "holding_period": {"nets": [-5, 3]}}}
    rows = [("fx_a", "FRAGILE: cost_stress, holding_period", json.dumps(ev)),
            ("fx_b", "validation net $-4.96 over 5000 trades", None),
            ("fx_c", "validation net $-900.00 over 5000 trades", None),
            ("fx_d", "0 trades on ('2016-01-01', '2019-12-31') (< min)", None)]
    for k, reason, e in rows:
        conn.execute("INSERT INTO strategy_decisions (at, strategy_key, version, decision, from_state, to_state, "
                     "reason, evidence) VALUES ('t', ?, 1, 'REJECT', 'X', 'REJECTED', ?, ?)", (k, reason, e))
    conn.commit()
    import ranking
    ranking.rank = lambda conn, cfg: []          # no league pool in this test
    f = {r["strategy_key"]: r for r in funnel.failures(conn, "2026-09-27")}
    check("a FRAGILE rejection gives one reason per failed test", f["fx_a"]["reasons"] == ["FAILED_COSTS", "FAILED_ROBUSTNESS"], f["fx_a"])
    check("a small cost-stress loss is a near miss", f["fx_a"]["near_miss"])
    check("a tiny validation loss is a near miss", f["fx_b"]["near_miss"] and f["fx_b"]["reasons"] == ["FAILED_VALIDATION"])
    check("a large validation loss is not", not f["fx_c"]["near_miss"])
    check("no trades is INSUFFICIENT_TRADES", f["fx_d"]["reasons"] == ["INSUFFICIENT_TRADES"])
    check("failures are recorded", conn.execute("SELECT COUNT(*) FROM strategy_failures").fetchone()[0] == 4)
    b = funnel.bottlenecks({"evaluated": 100, "net_positive": 90, "shortlisted": 10, "validated_all": [10, 2],
                            "paper_funds": 2}, {"steps": []}, {})
    check("the Lab chain includes the shortlist and paper", any("shortlisted" in d[0] for d in b)
          and any("paper funds" in d[0] for d in b), b)
    check("the funnel changes no lifecycle state", conn.execute("SELECT COUNT(*) FROM league_state").fetchone()[0] == 0)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
