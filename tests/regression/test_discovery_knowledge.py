"""
discovery.py: a documented-source reproduction (family kf_*) is queued and prioritised,
not blocked; its declared variants are queued as 'variant' below it; N7 weak spots (a
near miss in strategy_failures) raise a family's priority without bypassing anything.
In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import discovery
import funnel
import league
import research_queue as rq
import strategy_factory as sf
import strategy_objects as so

FAILED = []
G = sf.G(sf.gt(sf.rank(sf.col("book_to_market")), sf.k(0.8)), None, 3.0, 21)
CFG = {"factory": {"family_explored_after": 8}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def reg(conn, key, fam, source):
    so.register(conn, {"strategy_key": key, "name": key, "family": fam, "league": "fundamental",
                       "genome": G, "source": source})


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    so.init(conn); league.init(conn); rq.init(conn); funnel.init(conn); discovery.init(conn)
    reg(conn, "fx_kf_value_a", "kf_value", "knowledge_reproduction")
    reg(conn, "fx_kf_value_b", "kf_value", "knowledge_variant")
    reg(conn, "fx_value_book_c", "value_book", "factory_template")
    discovery.plan(conn, CFG)
    q = {r["strategy_key"]: dict(r) for r in rq.pending(conn, limit=100)}
    check("a knowledge reproduction is queued as 'library'", q.get("fx_kf_value_a", {}).get("source") == "library", q)
    check("its variant is queued as 'variant'", q.get("fx_kf_value_b", {}).get("source") == "variant")
    check("a knowledge family is prioritised, not blocked",
          discovery.priority("kf_value", {}, CFG, "library") is not None)
    check("a variant ranks below its reproduction",
          discovery.priority("kf_value", {}, CFG, "variant") < discovery.priority("kf_value", {}, CFG, "library"))
    check("an unknown non-knowledge family is still blocked", discovery.priority("nope", {}, CFG, "template") is None)
    conn.execute("INSERT INTO strategy_failures VALUES ('2026-09-27','fx_value_book_c',1,'[\"FAILED_VALIDATION\"]',"
                 "-0.001,1,'[]')")
    w = discovery.weak_spots(conn)
    check("a near miss marks its family as a weak spot", w.get("value_book") == "near misses", w)
    base = discovery.priority("value_book", {}, CFG, "template")
    check("a weak spot raises priority by 2", discovery.priority("value_book", {}, CFG, "template", w) == base + 2)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
