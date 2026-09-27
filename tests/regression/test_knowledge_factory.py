"""
knowledge_factory.py (Addendum E rev 2): lineage (original vs derivative), reproduction
first, a declared variant set only after the reproduction passed, provenance for every
strategy, the multiple-testing ledger counting failures, no link to the frozen search.
In-memory database only; no model calls.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)

import knowledge_extract as ke
import knowledge_factory as kf
import knowledge_library as kl
import league
import strategy_objects as so

FAILED = []
BM = {"entry": {"op": "gt", "args": [{"op": "rank", "args": [{"col": "book_to_market"}]}, {"const": 0.8}]},
      "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0}]},
      "risk": {"stop_atr_multiple": 3.0, "max_hold_days": 21}}
MOM = {"entry": {"op": "gt", "args": [{"op": "rank", "args": [
    {"op": "pct_change", "args": [{"col": "close"}], "n": 126}]}, {"const": 0.9}]},
       "exit": BM["exit"], "risk": {"stop_atr_multiple": 3.0, "max_hold_days": 21}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def entry(conn, eid, date, fam, g):
    kl.upsert(conn, {"entry_id": eid, "source": "test", "strategy_name": eid.upper(),
                     "source_type": "ACADEMIC_PAPER", "source_title": f"Paper {eid}", "source_date": date,
                     "provenance": {"t": 1}})
    conn.execute("INSERT INTO knowledge_translations (entry_id, translated_at, model, prompt_version, "
                 "original_definition, fields, genome, assumptions, ambiguities, missing_information, "
                 "translation_confidence, machine_translatable, family, data_available, errors) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (eid, "t", "m", "4", f"title: Paper {eid}", "{}", json.dumps(g) if g else None, "[]", "[]", "[]",
                  0.6, "YES" if g else "NO", fam, "YES" if g else "NO: futures", "[]"))


def main():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    conn.execute("INSERT INTO prices VALUES ('SPY', '2026-09-24', 1.0)")
    kl.init(conn); ke.init(conn); so.init(conn); league.init(conn); kf.init(conn)
    entry(conn, "e1", "1993-03-01", "VALUE", BM)
    entry(conn, "e2", "2005-01-01", "VALUE", BM)
    entry(conn, "e3", "1990-01-01", "MOMENTUM", MOM)
    entry(conn, "e4", "2000-01-01", "OTHER", None)
    conn.commit()

    check("lineage assigned to every translated entry", kf.assign_lineage(conn) == 4)
    lin = {r["entry_id"]: dict(r) for r in conn.execute("SELECT * FROM knowledge_lineage")}
    check("two sources on one idea share a lineage", lin["e1"]["lineage_id"] == lin["e2"]["lineage_id"]
          == "VALUE:book_to_market", lin)
    check("the earlier source is the ORIGINAL and independent",
          lin["e1"]["relationship"] == "ORIGINAL" and lin["e1"]["independence_status"] == "INDEPENDENT")
    check("the later one is a REPLICATION and derivative, citing the original",
          lin["e2"]["relationship"] == "REPLICATION" and lin["e2"]["independence_status"] == "DERIVATIVE"
          and lin["e2"]["source_parent"] == "e1")
    check("a re-run assigns nothing twice", kf.assign_lineage(conn) == 0)

    keys = kf.reproduce(conn)
    check("one reproduction per translatable entry (untranslatable skipped)", len(keys) == 3, keys)
    k1 = conn.execute("SELECT strategy_key, version FROM knowledge_reproductions WHERE entry_id='e1'").fetchone()
    check("a reproduction enters the pipeline at DISCOVERED",
          league.canonical(league.state(conn, k1[0], k1[1])) == league.DISCOVERED)
    check("reproductions use fx_ keys the ranking reads", all(k.startswith("fx_kf_") for k in keys), keys)
    pv = conn.execute("SELECT * FROM strategy_provenance WHERE strategy_key=?", (k1[0],)).fetchone()
    check("provenance records ORIGINAL_REPRODUCTION, source type, entry and lineage",
          pv["origin_kind"] == "ORIGINAL_REPRODUCTION" and pv["source_type"] == "ACADEMIC_PAPER"
          and pv["entry_id"] == "e1" and pv["lineage_id"] == "VALUE:book_to_market", dict(pv))
    rp = conn.execute("SELECT * FROM knowledge_reproductions WHERE entry_id='e1'").fetchone()
    check("reproduction records source / stockbot / data / implementation versions",
          all(rp[c] for c in ("source_version", "stockbot_version", "data_version", "implementation_version")))
    check("reproduce is idempotent", kf.reproduce(conn) == [])

    check("no variants before the reproduction has passed its backtest", kf.make_variants(conn) == [])
    for st in (league.SPECIFIED, league.BACKTESTED, league.VALIDATED):
        so.decide(conn, k1[0], k1[1], "PROMOTE", "test walk", to_state=st)
    vs = kf.make_variants(conn)
    check("variants only from the declared set", 0 < len(vs) <= len(kf.VARIANTS), len(vs))
    vp = conn.execute("SELECT * FROM strategy_provenance WHERE origin_kind='CONTROLLED_VARIANT'").fetchall()
    check("each variant records parent, mutation type and parameters",
          all(r["parent_strategy_key"] == k1[0] and r["mutation_type"] and r["mutation_parameters"] for r in vp))
    check("variants are made once", kf.make_variants(conn) == [])
    check("a lookback variant is skipped when the rule has no lookback",
          kf.variant(BM, "lookback", {"n_x": 0.5}) is None)
    lv = kf.variant(MOM, "lookback", {"n_x": 0.5})
    check("a lookback variant halves the formation window", lv["entry"]["args"][0]["args"][0]["n"] == 63)
    uv = kf.variant(BM, "universe", {"filter": "large_cap"})
    check("a universe variant adds a large-cap filter", "market_cap" in json.dumps(uv["entry"]))

    so.register(conn, {"strategy_key": "fx_value_book_x", "name": "VB", "family": "value_book",
                       "league": "fundamental", "genome": BM, "source": "factory_template"})
    league.register(conn, "paper:abc", "lab", {"family": "lab_search", "entry_rule": "x"},
                    source_kind="lab_validation", source_ref="sid1")
    n = kf.backfill(conn)
    check("backfill records provenance for strategies it did not make", n == 2, n)
    kinds = dict(conn.execute("SELECT strategy_key, origin_kind FROM strategy_provenance"
                              " WHERE strategy_key IN ('fx_value_book_x','paper:abc')").fetchall())
    check("a template is TEMPLATE, a search survivor MACHINE_GENERATED",
          kinds == {"fx_value_book_x": "TEMPLATE", "paper:abc": "MACHINE_GENERATED"}, kinds)

    k2 = conn.execute("SELECT strategy_key, version FROM knowledge_reproductions WHERE entry_id='e2'").fetchone()
    so.decide(conn, k2[0], k2[1], "REJECT", "test", to_state=league.REJECTED)
    stats = {s["lineage_id"]: s for s in kf.lineage_stats(conn)}
    v = stats["VALUE:book_to_market"]
    check("ledger: two hypotheses, one independent source", v["hypothesis_count"] == 2
          and v["independent_sources"] == 1, v)
    check("ledger: variants counted and the rejected reproduction counted as a failure",
          v["variant_count"] == len(vs) and v["failed_variants"] >= 1, v)
    check("ledger snapshot recorded", conn.execute("SELECT COUNT(*) FROM knowledge_lineage_stats").fetchone()[0] > 0)
    kf.mark_independent(conn, "e2", True, "separate dataset (owner review)")
    check("a person can record independence",
          conn.execute("SELECT independence_status FROM knowledge_lineage WHERE entry_id='e2'").fetchone()[0]
          == "INDEPENDENT")
    src = open(os.path.join(ROOT, "knowledge_factory.py")).read()
    check("the factory never imports the frozen search", "import evolve" not in src and "from evolve" not in src)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
