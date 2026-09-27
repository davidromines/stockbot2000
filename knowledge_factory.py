"""
The Knowledge Strategy Factory loop — Addendum E revision 2 (Stage O), N1/N4-N11.

Documented trading knowledge becomes testable Stockbot strategies that go through
the SAME pipeline as everything else. This module adds no backtester, no ranking
and no promotion path: it registers strategy objects (strategy_objects.register ->
DISCOVERED), and discovery.py / factory_pipeline.py / paper_all.py / ranking.py
take them from there. A famous source earns nothing here but a hypothesis.

What it adds, beside the existing knowledge_entries / knowledge_links tables:

  strategy_provenance     every strategy in the league: source type, how it was
                          made (reproduction / controlled variant / template /
                          machine / hybrid), its entry, lineage, parent, mutation
  knowledge_lineage       per documented entry: research lineage, relationship
                          (ORIGINAL / REPLICATION / ...), independence, overlap
  knowledge_reproductions the ORIGINAL REPRODUCTION of each translated entry, with
                          source / stockbot / data / implementation versions
  knowledge_lineage_stats per lineage, per day: hypotheses, variants, tests,
                          holdout uses, successes, failures, selection events —
                          failed variants are counted, never hidden (§11)

Rules that are load-bearing:
  - Reproduction first (§9): variants are generated only from a reproduction that
    has passed its own backtest (reached VALIDATED or beyond), never before.
  - Controlled variants (§10): a fixed, declared set per reproduction (at most
    len(VARIANTS)), each with mutation_type and mutation_parameters.
  - Lineage (§6-7): many papers on one idea are one lineage. Only an entry marked
    INDEPENDENT counts as independent evidence; the default for a later entry in a
    lineage is DERIVATIVE until someone records otherwise.
  - The frozen evolutionary search is not touched (§21); this module never imports
    evolve.py and the freeze-boundary test still holds.

    ./venv/bin/python knowledge_factory.py --cycle [--extract 40]
    ./venv/bin/python knowledge_factory.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import copy
import hashlib
import json
import logging
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import league
import strategy_objects as so

log = logging.getLogger("knowledge_factory")
ACTOR = "knowledge_factory"

ORIGIN_KINDS = ("ORIGINAL_REPRODUCTION", "CONTROLLED_VARIANT", "SOURCE_DERIVED_VARIANT", "TEMPLATE",
                "MACHINE_GENERATED", "MACHINE_MUTATION", "HYBRID", "FUND")
RELATIONSHIPS = ("ORIGINAL", "REPLICATION", "EXTENSION", "VARIANT", "DERIVATIVE", "COMBINATION",
                 "MUTATION", "HYBRID")
LEAGUE_OF = {"MOMENTUM": "momentum", "TREND": "momentum", "BREAKOUT": "momentum",
             "RELATIVE_VALUE": "momentum", "PAIRS": "momentum",
             "MEAN_REVERSION": "mean_reversion", "REVERSAL": "mean_reversion",
             "VALUE": "fundamental", "QUALITY": "fundamental", "FUNDAMENTAL": "fundamental",
             "FACTOR": "fundamental", "SIZE": "fundamental", "LOW_VOLATILITY": "fundamental",
             "LIQUIDITY": "fundamental", "EARNINGS_SURPRISE": "event", "ANALYST_REVISION": "event",
             "SEASONALITY": "event", "EVENT": "event"}
PASSED = ("VALIDATED", "PROMISING", "PAPER", "QUALIFIED", "LIVE_CANDIDATE", "LIVE")
# The declared variant set (§10). Nothing outside this list is ever generated.
VARIANTS = (("holding_period", {"hold_x": 0.5}), ("holding_period", {"hold_x": 2.0}),
            ("stop", {"stop_add": -1.0}), ("stop", {"stop_add": 1.0}),
            ("lookback", {"n_x": 0.5}), ("lookback", {"n_x": 1.5}),
            ("universe", {"filter": "large_cap"}), ("universe", {"filter": "liquid"}),
            ("exit", {"trailing_atr_multiple": 3.0}))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS strategy_provenance (
            strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            source_type TEXT, origin_kind TEXT NOT NULL, entry_id TEXT, lineage_id TEXT,
            parent_strategy_key TEXT, parent_version INTEGER,
            mutation_type TEXT, mutation_parameters TEXT, generated_by TEXT,
            recorded_at TEXT NOT NULL, PRIMARY KEY (strategy_key, version))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_lineage (
            entry_id TEXT PRIMARY KEY, lineage_id TEXT NOT NULL, relationship TEXT NOT NULL,
            independence_status TEXT NOT NULL, source_parent TEXT, citation_relationship TEXT,
            dataset_overlap TEXT, methodology_overlap TEXT, assigned_by TEXT NOT NULL,
            assigned_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_reproductions (
            entry_id TEXT PRIMARY KEY, strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            source_version TEXT, stockbot_version TEXT, data_version TEXT,
            implementation_version TEXT, reproduction_assumptions TEXT, created_at TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_lineage_stats (
            as_of TEXT NOT NULL, lineage_id TEXT NOT NULL, hypothesis_count INTEGER,
            independent_sources INTEGER, variant_count INTEGER, strategy_count INTEGER,
            test_count INTEGER, holdout_tests INTEGER, successful_variants INTEGER,
            failed_variants INTEGER, selection_events INTEGER, PRIMARY KEY (as_of, lineage_id))""")
    conn.commit()


def _has(conn, table: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE name=?", (table,)).fetchone() is not None


def _git_head() -> str:
    try:
        return subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True,
                              text=True, timeout=10).stdout.strip() or "unknown"
    except Exception:                                            # noqa: BLE001
        return "unknown"


# --- lineage (N6, §6-7) -------------------------------------------------------------------------

def _signal(g: dict | None) -> str:
    """The idea's primary input: the first column its entry rule reads (e.g. book_to_market,
    close for momentum). Two sources ranking on the same column in the same family are the
    same lineage however their thresholds differ."""
    if not g:
        return "untranslated"
    stack = [g.get("entry")]
    while stack:
        n = stack.pop(0)
        if not isinstance(n, dict):
            continue
        if "col" in n:
            return n["col"]
        stack.extend(n.get("args") or [])
    return "none"


def assign_lineage(conn) -> int:
    """Lineage for every translated entry that has none. The earliest-dated source in a
    lineage is its ORIGINAL (INDEPENDENT); later ones are REPLICATION / DERIVATIVE until a
    person records otherwise. Never overwrites a recorded row."""
    if not _has(conn, "knowledge_translations"):
        return 0
    rows = conn.execute("""SELECT t.entry_id, t.family, t.genome, e.source_date, e.source_title
        FROM knowledge_translations t JOIN knowledge_entries e USING (entry_id)
        LEFT JOIN knowledge_lineage l USING (entry_id) WHERE l.entry_id IS NULL""").fetchall()
    n = 0
    for eid, fam, gtxt, sdate, _title in rows:
        g = json.loads(gtxt) if gtxt else None
        lid = f"{(fam or 'OTHER').upper()}:{_signal(g)}"
        first = conn.execute("""SELECT l.entry_id, e.source_date FROM knowledge_lineage l
            JOIN knowledge_entries e USING (entry_id) WHERE l.lineage_id=? AND l.relationship='ORIGINAL'""",
                             (lid,)).fetchone()
        if first is None:
            rel, ind, parent = "ORIGINAL", "INDEPENDENT", None
        elif sdate and first[1] and sdate < first[1]:
            # An older source than the current original: it becomes the original.
            conn.execute("UPDATE knowledge_lineage SET relationship='REPLICATION', independence_status="
                         "'DERIVATIVE', source_parent=? WHERE entry_id=? AND assigned_by=?", (eid, first[0], ACTOR))
            rel, ind, parent = "ORIGINAL", "INDEPENDENT", None
        else:
            rel, ind, parent = "REPLICATION", "DERIVATIVE", first[0]
        conn.execute("INSERT INTO knowledge_lineage VALUES (?,?,?,?,?,?,?,?,?,?)",
                     (eid, lid, rel, ind, parent, None, "unknown", "unknown", ACTOR, _now()))
        n += 1
    conn.commit()
    return n


def mark_independent(conn, entry_id: str, independent: bool, note: str, by: str = "owner") -> None:
    """A person's ruling on source independence (§7). Recorded, never inferred."""
    conn.execute("UPDATE knowledge_lineage SET independence_status=?, citation_relationship=?, "
                 "assigned_by=?, assigned_at=? WHERE entry_id=?",
                 ("INDEPENDENT" if independent else "DERIVATIVE", note, by, _now(), entry_id))
    conn.commit()


# --- reproduction (N4, §9) ----------------------------------------------------------------------

def _obj(entry: dict, tr: dict, g: dict, key: str, name: str, source: str, parent: str | None,
         hypothesis: str) -> dict:
    import storage
    fam = (tr.get("family") or "OTHER").upper()
    return {"strategy_key": key, "name": name[:80], "family": f"kf_{fam.lower()}",
            "league": LEAGUE_OF.get(fam, "tactical"), "genome": g,
            "parameters": {"entry_id": entry["entry_id"]}, "source": source,
            "source_ref": entry["entry_id"], "parent_key": parent, "hypothesis": hypothesis,
            "data_requirements": ["features"] + (["daily_fundamentals"] if storage.needs_panel(g) else []),
            "universe": "common stock, price and liquidity floors",
            "position_sizing": "$20 per position (slot rule)"}


def reproduce(conn) -> list:
    """Register the ORIGINAL REPRODUCTION of every translatable entry that has none."""
    if not _has(conn, "knowledge_translations"):
        return []
    rows = conn.execute("""SELECT t.*, e.strategy_name, e.source_type AS stype, e.original_claim,
        e.source_title FROM knowledge_translations t JOIN knowledge_entries e USING (entry_id)
        LEFT JOIN knowledge_reproductions r USING (entry_id)
        WHERE r.entry_id IS NULL AND t.genome IS NOT NULL
          AND t.machine_translatable IN ('YES','PARTIAL') AND t.data_available LIKE 'YES%'""").fetchall()
    head, data_v = _git_head(), conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    out = []
    for r in rows:
        r = dict(r)
        g = json.loads(r["genome"])
        key = so.key_for(f"kf_{(r['family'] or 'other').lower()}", {"entry_id": r["entry_id"]})
        claim = (r.get("original_claim") or "")[:160]
        hyp = (f"ORIGINAL REPRODUCTION of '{r.get('source_title') or r['strategy_name']}' — a hypothesis "
               f"from a documented source, not evidence. Source claim: {claim or 'none stated'}. "
               f"Translation {r['machine_translatable']}, confidence {r['translation_confidence']:.2f}.")
        obj = _obj(r, r, g, key, f"{r['strategy_name']} · reproduction", "knowledge_reproduction", None, hyp)
        # Two sources that translate to the identical rule are one strategy, tested once:
        # the later entry points at the existing reproduction instead of minting a twin.
        twin = next(((k, v) for k, v in conn.execute(
            "SELECT DISTINCT strategy_key, version FROM knowledge_reproductions").fetchall()
            if so.genome(conn, k, v) == g and (so.meta(conn, k, v) or {}).get("family") == obj["family"]), None)
        if twin:
            reg, key, new = {"version": twin[1]}, twin[0], False
        else:
            reg, new = so.register(conn, obj, author=ACTOR), True
        src_v = hashlib.sha256((r.get("original_definition") or "").encode()).hexdigest()[:16]
        conn.execute("INSERT OR REPLACE INTO knowledge_reproductions VALUES (?,?,?,?,?,?,?,?,?)",
                     (r["entry_id"], key, reg["version"], src_v, head, data_v,
                      f"knowledge_extract prompt {r['prompt_version']} / knowledge_factory 1",
                      r.get("assumptions"), _now()))
        conn.execute("INSERT OR IGNORE INTO knowledge_links VALUES (?,?,?,?,?)",
                     (r["entry_id"], key, reg["version"], "SOURCE_REPRODUCTION", _now()))
        if new:
            lid = conn.execute("SELECT lineage_id FROM knowledge_lineage WHERE entry_id=?",
                               (r["entry_id"],)).fetchone()
            _provenance(conn, key, reg["version"], r.get("stype"), "ORIGINAL_REPRODUCTION", r["entry_id"],
                        lid[0] if lid else None, None, None, None, None)
            out.append(key)
    conn.commit()
    return out


# --- controlled variants (N5, §10) --------------------------------------------------------------

def _scale_n(node, x: float):
    if isinstance(node, dict):
        if "n" in node:
            node["n"] = max(2, int(round(node["n"] * x)))
        for a in node.get("args") or []:
            _scale_n(a, x)


def variant(g: dict, kind: str, p: dict) -> dict | None:
    """One declared variant of a genome, or None when the variant does not apply."""
    v = copy.deepcopy(g)
    risk = v.setdefault("risk", {})
    if kind == "holding_period":
        risk["max_hold_days"] = int(min(252, max(1, round(risk.get("max_hold_days", 20) * p["hold_x"]))))
    elif kind == "stop":
        risk["stop_atr_multiple"] = float(min(6.0, max(1.5, risk.get("stop_atr_multiple", 2.5) + p["stop_add"])))
    elif kind == "lookback":
        before = json.dumps(v["entry"])
        _scale_n(v["entry"], p["n_x"])
        if json.dumps(v["entry"]) == before:
            return None                                     # no lookback to vary
    elif kind == "universe":
        colname = {"large_cap": "market_cap", "liquid": "dollar_volume_20"}[p["filter"]]
        v["entry"] = {"op": "and", "args": [v["entry"], {"op": "gt", "args": [
            {"op": "rank", "args": [{"col": colname}]}, {"const": 0.5}]}]}
    elif kind == "exit":
        risk["trailing_atr_multiple"] = float(p["trailing_atr_multiple"])
    return None if v == g else v


def make_variants(conn) -> list:
    """Declared variants for every reproduction that passed its own backtest and has none yet."""
    out = []
    for eid, key, ver in conn.execute("SELECT entry_id, strategy_key, version FROM knowledge_reproductions").fetchall():
        st = league.canonical(league.state(conn, key, ver))
        if st not in PASSED:
            continue
        if conn.execute("SELECT 1 FROM strategy_provenance WHERE parent_strategy_key=? AND "
                        "origin_kind='CONTROLLED_VARIANT'", (key,)).fetchone():
            continue
        g = so.genome(conn, key, ver)
        m = so.meta(conn, key, ver) or {}
        tr = {"family": (m.get("family") or "kf_other")[3:].upper()}
        entry = {"entry_id": eid}
        prov = conn.execute("SELECT source_type, lineage_id FROM strategy_provenance WHERE strategy_key=? "
                            "AND version=?", (key, ver)).fetchone() or (None, None)
        for kind, p in VARIANTS:
            vg = variant(g, kind, p)
            if vg is None:
                continue
            vkey = so.key_for(m.get("family") or "kf_other", {"entry_id": eid, "variant": [kind, p]})
            hyp = f"CONTROLLED VARIANT of {key} ({kind} {json.dumps(p)}); declared set of {len(VARIANTS)}."
            base = (conn.execute("SELECT name FROM league_strategies WHERE strategy_key=? AND version=?",
                                 (key, ver)).fetchone() or [key])[0]
            reg = so.register(conn, _obj(entry, tr, vg, vkey, f"{base} · {kind} {list(p.values())[0]}",
                                         "knowledge_variant", key, hyp), author=ACTOR)
            conn.execute("INSERT OR IGNORE INTO knowledge_links VALUES (?,?,?,?,?)",
                         (eid, vkey, reg["version"], "CONTROLLED_VARIANT", _now()))
            _provenance(conn, vkey, reg["version"], prov[0], "CONTROLLED_VARIANT", eid, prov[1], key, ver,
                        kind, p)
            out.append(vkey)
    conn.commit()
    return out


# --- provenance for every strategy (N1, N10) ----------------------------------------------------

def _provenance(conn, key, ver, stype, kind, entry_id, lineage, parent, pver, mtype, mparams,
                by: str = ACTOR) -> None:
    conn.execute("INSERT OR REPLACE INTO strategy_provenance VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 (key, ver, stype, kind, entry_id, lineage, parent, pver, mtype,
                  json.dumps(mparams, sort_keys=True) if mparams is not None else None, by, _now()))


def backfill(conn) -> int:
    """Provenance for every league strategy that has none, from what the league records."""
    anc = {}
    if _has(conn, "strategy_ancestry"):
        anc = dict(conn.execute("SELECT strategy_id, seed_origin FROM strategy_ancestry"))
    rows = conn.execute("""SELECT s.strategy_key, s.version, s.source_kind, s.source_ref, s.parent_key, s.family
        FROM league_strategies s LEFT JOIN strategy_provenance p
        ON p.strategy_key=s.strategy_key AND p.version=s.version WHERE p.strategy_key IS NULL""").fetchall()
    published = set()
    try:
        import factory_families_l as ffl
        published = set(ffl.PUBLISHED)
    except Exception:                                            # noqa: BLE001
        pass
    for key, ver, kind, ref, parent, fam in rows:
        m = so.meta(conn, key, ver) or {}
        family = m.get("family") or fam or ""
        if kind == "lab_validation" or (kind == "paper_runs" and str(fam or "") in ("lab", "lab_search")):
            seeded = anc.get(ref) == "SEED_LITERAL"
            _provenance(conn, key, ver, "HYBRID" if seeded else "MACHINE_GENERATED",
                        "HYBRID" if seeded else "MACHINE_GENERATED", None, "MACHINE:search", None, None,
                        None, None, "backfill")
        elif kind == "recycle":
            _provenance(conn, key, ver, "KNOWN_FACTOR", "CONTROLLED_VARIANT", None, f"TEMPLATE:{family}",
                        key, ver - 1 if ver > 1 else None, "recycle", None, "backfill")
        elif kind == "experiment":
            _provenance(conn, key, ver, "KNOWN_FACTOR", "CONTROLLED_VARIANT", None, f"TEMPLATE:{family}",
                        parent, None, "exit", {"source": ref}, "backfill")
        elif kind in ("knowledge_reproduction", "knowledge_variant"):
            continue                                            # written when registered
        elif kind in ("pair_funds", "crypto_fund", "value_fund", "paper_runs"):
            _provenance(conn, key, ver, "TRADING_SYSTEM" if kind != "value_fund" else "KNOWN_FACTOR",
                        "FUND", None, f"FUND:{kind}", None, None, None, None, "backfill")
        else:                                                   # factory templates and anything else
            _provenance(conn, key, ver, "PUBLISHED_SIGNAL" if family in published else "KNOWN_FACTOR",
                        "TEMPLATE", None, f"TEMPLATE:{family}", parent, None, None, None, "backfill")
    conn.commit()
    return len(rows)


# --- multiple-testing ledger (N7, §11) ----------------------------------------------------------

def lineage_stats(conn, record: bool = True) -> list:
    """Per research lineage: how many hypotheses, variants and tests it took, and what failed.
    Knowledge lineages come from knowledge_lineage; templates, funds and the search are
    lineages of their own (TEMPLATE:<family>, FUND:<kind>, MACHINE:search)."""
    hyp = {}
    for lid, n, ind in conn.execute("SELECT lineage_id, COUNT(*), SUM(independence_status='INDEPENDENT') "
                                    "FROM knowledge_lineage GROUP BY 1"):
        hyp[lid] = (n, ind or 0)
    strat = {}
    for key, ver, lid, kind in conn.execute("SELECT strategy_key, version, lineage_id, origin_kind "
                                            "FROM strategy_provenance"):
        strat.setdefault(lid or "UNASSIGNED", []).append((key, ver, kind))
    tests = {}
    for key, n in conn.execute("SELECT strategy_key, COUNT(*) FROM strategy_decisions WHERE to_state IN "
                               "('BACKTESTED','VALIDATED','REJECTED','PROMISING') GROUP BY 1"):
        tests[key] = n
    sv = {}
    if _has(conn, "survivorship_backtests"):
        for key, n in conn.execute("SELECT strategy_key, COUNT(*) FROM survivorship_backtests GROUP BY 1"):
            sv[key] = n
    hold = 0
    if _has(conn, "holdout_log"):
        hold = conn.execute("SELECT COUNT(*) FROM holdout_log").fetchone()[0]
    sel = {}
    for key, n in conn.execute("SELECT strategy_key, COUNT(*) FROM league_state WHERE to_state IN "
                               "('PAPER','QUALIFIED','LIVE_CANDIDATE','LIVE') GROUP BY 1"):
        sel[key] = n
    if _has(conn, "slot_assignments"):
        for key, n in conn.execute("SELECT strategy_key, COUNT(*) FROM slot_assignments WHERE action='ASSIGN' "
                                   "GROUP BY 1"):
            sel[key] = sel.get(key, 0) + n
    out, today = [], datetime.now(timezone.utc).date().isoformat()
    for lid in sorted(set(hyp) | set(strat)):
        ss = strat.get(lid, [])
        states = [league.canonical(league.state(conn, k, v)) for k, v, _ in ss]
        row = {"lineage_id": lid, "hypothesis_count": hyp.get(lid, (0, 0))[0],
               "independent_sources": hyp.get(lid, (0, 0))[1],
               "variant_count": sum(1 for *_, kd in ss if kd in ("CONTROLLED_VARIANT", "MACHINE_MUTATION")),
               "strategy_count": len(ss),
               "test_count": sum(tests.get(k, 0) + sv.get(k, 0) for k, _, _ in ss),
               "holdout_tests": hold if lid == "MACHINE:search" else 0,
               "successful_variants": sum(1 for s in states if s in PASSED),
               "failed_variants": sum(1 for s in states if s == "REJECTED"),
               "selection_events": sum(sel.get(k, 0) for k, _, _ in ss)}
        out.append(row)
        if record:
            conn.execute("INSERT OR REPLACE INTO knowledge_lineage_stats VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                         (today, lid, *[row[c] for c in list(row)[1:]]))
    conn.commit()
    return out


# --- reporting (N9, §18-19) ---------------------------------------------------------------------

def report(conn) -> dict:
    """Activity and outcomes by source type — for research, never a promotion rule (§19)."""
    import ranking
    from universe import load_config
    tr = {}
    if _has(conn, "knowledge_translations"):
        tr = dict(conn.execute("SELECT machine_translatable, COUNT(*) FROM knowledge_translations GROUP BY 1"))
    ranked = {(r["strategy_key"], r["version"]): r for r in ranking.rank(conn, load_config())}
    live = set()
    if _has(conn, "slot_assignments"):
        import slots
        live = {(h["strategy_key"], h["version"]) for h in slots.current(conn, load_config()).values() if h}
    by = {}
    for key, ver, stype, kind in conn.execute("SELECT strategy_key, version, source_type, origin_kind "
                                              "FROM strategy_provenance"):
        b = by.setdefault(stype or "UNKNOWN", {"ideas": 0, "rejected": 0, "paper": 0, "forward_evidence": 0,
                                               "ranked_passing": 0, "live": 0})
        b["ideas"] += 1
        st = league.canonical(league.state(conn, key, ver))
        b["rejected"] += st == "REJECTED"
        b["paper"] += st in ("PAPER", "QUALIFIED", "LIVE_CANDIDATE", "LIVE")
        r = ranked.get((key, ver))
        if r:
            b["forward_evidence"] += bool(r.get("forward_trades"))
            b["ranked_passing"] += bool(r.get("passes_gate"))
        b["live"] += (key, ver) in live
    kr = conn.execute("SELECT COUNT(*) FROM knowledge_reproductions").fetchone()[0]
    kv = conn.execute("SELECT COUNT(*) FROM strategy_provenance WHERE origin_kind='CONTROLLED_VARIANT' "
                      "AND generated_by=?", (ACTOR,)).fetchone()[0]
    return {"entries": conn.execute("SELECT COUNT(*) FROM knowledge_entries").fetchone()[0],
            "translated": sum(tr.values()), "translated_yes": tr.get("YES", 0),
            "requiring_interpretation": tr.get("PARTIAL", 0), "not_translatable": tr.get("NO", 0),
            "reproductions": kr, "variants": kv, "by_source_type": by,
            "lineages": conn.execute("SELECT COUNT(DISTINCT lineage_id) FROM knowledge_lineage").fetchone()[0]}


def render(rep: dict, stats: list) -> str:
    lines = [f"KNOWLEDGE FACTORY  entries {rep['entries']:,}  translated {rep['translated']} "
             f"(yes {rep['translated_yes']}, needs interpretation {rep['requiring_interpretation']}, "
             f"no {rep['not_translatable']})  reproductions {rep['reproductions']}  variants {rep['variants']}  "
             f"lineages {rep['lineages']}", "",
             f"  {'source type':<22}{'ideas':>7}{'rejected':>9}{'paper+':>8}{'forward':>9}{'ranked':>8}{'live':>6}"]
    for k, b in sorted(rep["by_source_type"].items(), key=lambda x: -x[1]["ideas"]):
        lines.append(f"  {k:<22}{b['ideas']:>7}{b['rejected']:>9}{b['paper']:>8}{b['forward_evidence']:>9}"
                     f"{b['ranked_passing']:>8}{b['live']:>6}")
    lines += ["", "  Outcomes by source type are research data, not a ranking of sources (§19).", "",
              f"  {'lineage':<34}{'hyp':>5}{'indep':>6}{'strat':>6}{'var':>5}{'tests':>7}{'ok':>5}{'fail':>6}{'sel':>5}"]
    for s in sorted(stats, key=lambda s: -s["test_count"])[:25]:
        lines.append(f"  {s['lineage_id'][:33]:<34}{s['hypothesis_count']:>5}{s['independent_sources']:>6}"
                     f"{s['strategy_count']:>6}{s['variant_count']:>5}{s['test_count']:>7}"
                     f"{s['successful_variants']:>5}{s['failed_variants']:>6}{s['selection_events']:>5}")
    return "\n".join(lines)


# --- the loop (N11, §25) ------------------------------------------------------------------------

def cycle(conn, cfg, extract: int = 40) -> dict:
    """One pass: translate a budget of new entries, assign lineage, reproduce, vary the
    reproductions that passed, record provenance for everything, snapshot the ledger.
    The pipeline stages that follow in daily.sh test what this registers."""
    init(conn)
    out = {}
    if extract:
        try:
            import knowledge_extract as ke
            from llm import get_provider
            ke.init(conn)
            out["extract"] = ke.run(conn, get_provider(cfg), limit=extract, rates=cfg["ado"]["rates"])
        except Exception as e:                                   # noqa: BLE001 — never block the rest
            log.warning(f"extraction skipped: {type(e).__name__}: {e}")
            out["extract"] = {"error": str(e)[:200]}
    out["lineage_assigned"] = assign_lineage(conn)
    out["reproduced"] = len(reproduce(conn))
    out["variants"] = len(make_variants(conn))
    out["provenance_backfilled"] = backfill(conn)
    out["lineages"] = len(lineage_stats(conn))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cycle", action="store_true")
    ap.add_argument("--extract", type=int, default=40, help="entries to translate this cycle (0 = none)")
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from pathlib import Path
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    init(conn)
    if a.cycle:
        print(json.dumps(cycle(conn, cfg, a.extract), indent=2))
    if a.report or a.cycle:
        rep = report(conn)
        text = render(rep, lineage_stats(conn, record=False))
        Path("data/knowledge_factory.txt").write_text(text + "\n")
        Path("data/knowledge_factory.json").write_text(json.dumps(rep, indent=2))
        print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
