"""
Regression tests for strategy_objects.py — Phase 13 H3 (metadata, metrics,
§37 decisions). Plain script, no pytest, in-memory database only.

The load-bearing behaviours under test are the ones a measurement bug would
hide behind: register() must be idempotent (a re-run must not fork a forward
record), a changed genome must mint a new version while leaving v1 readable,
and decide() must write its row even when the state machine refuses the move —
a refused transition that leaves no trace is indistinguishable from a decision
nobody made.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import league
import strategy_factory as sf
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def fresh():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    so.init(conn)
    return conn


def obj(key, genome, params=None):
    return {"strategy_key": key, "name": "Test Strategy", "family": "rsi_reversion",
            "league": "mean_reversion", "genome": genome,
            "parameters": params or {"rsi": 30}, "source": "factory_template",
            "source_ref": "rsi_reversion", "hypothesis": "oversold reverts",
            "universe": "tradeable common stock"}


def genome_a():
    return sf.G(sf.gt(sf.col("rsi_14"), sf.k(50)))


def genome_b():
    # Only the constant differs; that is a material change and must mint v2.
    return sf.G(sf.gt(sf.col("rsi_14"), sf.k(60)))


def main():
    # 1. key_for determinism
    k1 = so.key_for("rsi_reversion", {"rsi": 30})
    k2 = so.key_for("rsi_reversion", {"rsi": 30})
    k3 = so.key_for("rsi_reversion", {"rsi": 25})
    check("key_for deterministic", k1 == k2, f"{k1} != {k2}")
    check("key_for differs on params", k1 != k3, f"{k1} == {k3}")
    check("key_for prefix fx_", k1.startswith("fx_"), k1)

    # 2. register idempotent
    conn = fresh()
    key = k1
    r1 = so.register(conn, obj(key, genome_a()))
    r2 = so.register(conn, obj(key, genome_a()))
    check("register first new True", r1["new"] is True, str(r1))
    check("register second new False", r2["new"] is False, str(r2))
    check("register second same version", r1["version"] == r2["version"],
          f"{r1['version']} != {r2['version']}")

    # 3. changed genome mints v2, v1 meta still readable
    r3 = so.register(conn, obj(key, genome_b()))
    check("changed genome new True", r3["new"] is True, str(r3))
    check("changed genome version 2", r3["version"] == 2, str(r3["version"]))
    m1 = so.meta(conn, key, 1)
    check("v1 meta still readable", m1 is not None and m1["version"] == 1,
          str(m1))

    # 4. first version enters at DISCOVERED
    check("state v1 DISCOVERED", league.state(conn, key, 1) == league.DISCOVERED,
          str(league.state(conn, key, 1)))

    # 5. genome round-trips
    g = so.genome(conn, key, 1)
    check("genome entry round-trips",
          g is not None and g["entry"] == genome_a()["entry"],
          str(g))

    # 6. metrics append-only, latest wins
    so.record_metrics(conn, key, 1, "backtest", net_usd=100.0, as_of="2026-01-01")
    m = so.latest_metrics(conn, key, 1, "backtest")
    check("latest_metrics first net_usd", m is not None and m["net_usd"] == 100.0,
          str(m))
    so.record_metrics(conn, key, 1, "backtest", net_usd=250.0, as_of="2026-02-01")
    m2 = so.latest_metrics(conn, key, 1, "backtest")
    check("latest_metrics newer net_usd", m2 is not None and m2["net_usd"] == 250.0,
          str(m2))

    # 7. legal transition via decide
    d = so.decide(conn, key, 1, "CONTINUE", "spec written",
                  to_state=league.SPECIFIED)
    check("decide legal to SPECIFIED", d["to"] == league.SPECIFIED, str(d))
    check("decide legal refused None", d["refused"] is None, str(d))
    check("state now SPECIFIED", league.state(conn, key, 1) == league.SPECIFIED,
          str(league.state(conn, key, 1)))

    # 8. illegal transition is refused but still logged
    d2 = so.decide(conn, key, 1, "PROMOTE", "skip ahead", to_state=league.PAPER)
    check("decide illegal refused not None", d2["refused"] is not None, str(d2))
    check("decide illegal state unchanged",
          league.state(conn, key, 1) == league.SPECIFIED,
          str(league.state(conn, key, 1)))
    row = conn.execute(
        "SELECT reason FROM strategy_decisions WHERE strategy_key=? AND decision='PROMOTE' "
        "ORDER BY id DESC LIMIT 1", (key,)).fetchone()
    check("refused decision still logged",
          row is not None and "transition refused" in row["reason"],
          str(row["reason"] if row else None))

    # 9. unknown decision / classification raise
    raised = False
    try:
        so.decide(conn, key, 1, "NOT_A_DECISION", "x")
    except ValueError:
        raised = True
    check("unknown decision raises ValueError", raised)

    raised = False
    try:
        so.decide(conn, key, 1, "CONTINUE", "x", classification="NOT_A_CLASS")
    except ValueError:
        raised = True
    check("unknown classification raises ValueError", raised)

    # 10. classification before and after a classified decision
    conn2 = fresh()
    key2 = so.key_for("rsi_reversion", {"rsi": 25})
    so.register(conn2, obj(key2, genome_a(), params={"rsi": 25}))
    check("classification default UNTESTED",
          so.classification(conn2, key2, 1) == "UNTESTED",
          so.classification(conn2, key2, 1))
    so.decide(conn2, key2, 1, "CONTINUE", "profitable so far",
              classification="PROFITABLE")
    check("classification latest PROFITABLE",
          so.classification(conn2, key2, 1) == "PROFITABLE",
          so.classification(conn2, key2, 1))

    # 11. in_state
    pairs = so.in_state(conn, league.SPECIFIED)
    check("in_state SPECIFIED contains (key,1)", (key, 1) in pairs, str(pairs))

    conn.close()
    conn2.close()

    if FAILED:
        print(f"\n  {len(FAILED)} FAILED")
        return 1
    print("\n  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
