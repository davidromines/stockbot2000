"""
Continuous discovery. Phase 13 §22-25; Addendum B §B17. Step H9.

Decides WHAT TO TEST NEXT, which is the question Phase 13 exists to answer
(§41). Four parts:

PRIORITY (§25) — every queued item is scored from its family's record:
    +7 a family never tested          +6 a family under-tested
    +4 a stated rationale, untested   +2 a cross-family combination
    +1 external research (library)    -5 a family explored without evidence
    -3 a recycled variant             blocked: no rationale, or data missing

BUDGETS (§24) — per run: `max_backtests_per_run` in total and at most
`per_family_per_run` from any one family, so one idea cannot eat the compute.
Once a family has `family_explored_after` tested variants with nothing
validated, its priority drops and compute moves to under-explored families.

FAILURE RECORDS (B17) — every rejection writes why, which family, which
parameters, which window, what data, and what it might suggest next.

RECYCLING (§23) — a rejected strategy may be mutated into a NEW VERSION of
the same strategy_key (league.register mints it; the rejected version is
untouched), at most `max_recycles_per_strategy` times. Mutations are drawn
from a fixed list in order, never searched.

    python discovery.py --plan      reprioritise the queue
    python discovery.py --status    families explored / ignored, diversity
    python discovery.py --recycle   mutate eligible rejected strategies
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import copy
import json
import math
import sqlite3
from datetime import datetime, timezone

import league
import research_queue as rq
import storage
import strategy_factory as sf
import strategy_objects as so
from universe import load_config

PER_FAMILY_PER_RUN = 2
TESTED_STATES = {league.BACKTESTED, league.VALIDATED, league.PROMISING, league.PAPER,
                 league.QUALIFIED, league.LIVE_CANDIDATE, league.LIVE, league.REJECTED,
                 league.DEMOTED, league.RETIRED}
GOOD_STATES = {league.VALIDATED, league.PROMISING, league.PAPER, league.QUALIFIED,
               league.LIVE_CANDIDATE, league.LIVE}

# §23 mutations, applied in this order, one per recycle.
MUTATIONS = (
    ("longer_hold", "double the holding period"),
    ("trend_filter", "add a price-above-200-day filter"),
    ("quality_filter", "add a gross-profitability filter (top half)"),
    ("wider_stop", "widen the ATR stop by half"),
)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    rq.init(conn)
    so.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS failure_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            at TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            family TEXT, stage TEXT NOT NULL, reason TEXT NOT NULL,
            parameters TEXT, window TEXT, regimes TEXT, data TEXT, suggests TEXT)""")
    conn.commit()


def record_failure(conn, key: str, version: int, stage: str, reason: str,
                   window=None, regimes=None, suggests: str | None = None) -> None:
    init(conn)
    m = so.meta(conn, key, version) or {}
    conn.execute("INSERT INTO failure_log (at, strategy_key, version, family, stage, reason, "
                 "parameters, window, regimes, data, suggests) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                 (_now(), key, version, m.get("family"), stage, reason,
                  json.dumps(m.get("parameters"), default=str), json.dumps(window),
                  json.dumps(regimes, default=str), json.dumps(m.get("data_requirements")),
                  suggests))
    conn.commit()


def family_record(conn) -> dict:
    """family -> {generated, tested, good, rejected, data_problem, combo}."""
    rec = {f: {"generated": 0, "tested": 0, "good": 0, "rejected": 0,
               "data_problem": 0, "combo": sf.F[f]["combo"]} for f in sf.F}
    rows = conn.execute("""
        SELECT m.family, s.strategy_key, s.version, s.to_state FROM league_state s
        JOIN (SELECT strategy_key, version, MAX(id) mid FROM league_state
              GROUP BY strategy_key, version) x ON x.mid = s.id
        JOIN strategy_meta m ON m.strategy_key = s.strategy_key AND m.version = s.version
    """).fetchall()
    dp = {(k, v) for k, v in conn.execute(
        "SELECT strategy_key, version FROM strategy_decisions WHERE decision='DATA_PROBLEM'")}
    for fam, key, ver, st in rows:
        fam = json.loads(fam) if fam and fam.startswith('"') else fam
        r = rec.setdefault(fam, {"generated": 0, "tested": 0, "good": 0, "rejected": 0,
                                 "data_problem": 0, "combo": False})
        r["generated"] += 1
        st = league.canonical(st)
        if st in TESTED_STATES:
            r["tested"] += 1
        if st in GOOD_STATES:
            r["good"] += 1
        if st == league.REJECTED:
            r["rejected"] += 1
        if (key, ver) in dp:
            r["data_problem"] += 1
    return rec


def priority(fam: str, rec: dict, cfg: dict, source: str) -> float | None:
    """§25. None = blocked (no rationale, or the data does not exist)."""
    f = sf.F.get(fam)
    if f is None or not f.get("rationale"):
        return None
    if not f["data_available"]:
        return None
    explored_after = int((cfg.get("factory") or {}).get("family_explored_after", 8))
    r = rec.get(fam, {})
    p = 0.0
    if r.get("tested", 0) == 0:
        p += 7
    elif r["tested"] < explored_after:
        p += 6
    if r.get("tested", 0) >= explored_after and r.get("good", 0) == 0:
        p -= 5
    p += 4 if r.get("tested", 0) == 0 else 0
    p += 2 if f["combo"] else 0
    p += 1 if source == "library" else 0
    p -= 3 if source == "recycle" else 0
    return p


def plan(conn, cfg) -> dict:
    """Reprioritise every queued item; enqueue un-queued DISCOVERED factory objects."""
    init(conn)
    # Every generated object is an idea waiting; make sure each is queued once.
    for key, ver in so.in_state(conn, league.DISCOVERED):
        m = so.meta(conn, key, ver)
        if m and m.get("source") in ("factory_template", "recycle"):
            rq.enqueue(conn, "recycle" if m["source"] == "recycle" else "template",
                       m["family"], family=m["family"], strategy_key=key, version=ver)
    rec = family_record(conn)
    stats = {"reprioritised": 0, "blocked": 0}
    for item in rq.pending(conn, limit=100000):
        p = priority(item["family"], rec, cfg, item["source"])
        if p is None:
            rq.set_status(conn, item["id"], "blocked",
                          sf.F.get(item["family"], {}).get("missing") or "no rationale")
            stats["blocked"] += 1
        else:
            rq.reprioritize(conn, item["id"], p)
            stats["reprioritised"] += 1
    return stats


def take(conn, cfg, n: int | None = None) -> list:
    """The next batch, within the run budget and at most PER_FAMILY_PER_RUN per family."""
    budget = n or int((cfg.get("factory") or {}).get("max_backtests_per_run", 12))
    chosen, per_fam, seen = [], {}, set()
    for item in rq.pending(conn, limit=100000):
        if len(chosen) >= budget:
            break
        k = (item["strategy_key"], item["version"])
        if not item["strategy_key"] or k in seen:
            continue
        # Only objects still waiting to be tested.
        if league.canonical(league.state(conn, item["strategy_key"], item["version"])) != league.DISCOVERED:
            rq.set_status(conn, item["id"], "done", "already past DISCOVERED")
            continue
        if per_fam.get(item["family"], 0) >= PER_FAMILY_PER_RUN:
            continue
        per_fam[item["family"]] = per_fam.get(item["family"], 0) + 1
        seen.add(k)
        rq.set_status(conn, item["id"], "taken")
        chosen.append(item)
    return chosen


def _mutate(g: dict, how: str) -> dict:
    g = copy.deepcopy(g)
    if how == "longer_hold":
        g["risk"]["max_hold_days"] = int(g["risk"]["max_hold_days"]) * 2
    elif how == "trend_filter":
        g["entry"] = sf.and_(g["entry"], sf.gt(sf.col("price_above_sma200"), sf.k(0.5)))
    elif how == "quality_filter":
        g["entry"] = sf.and_(g["entry"], sf.gt(sf.rank(sf.col("gross_profitability")), sf.k(0.5)))
    elif how == "wider_stop":
        g["risk"]["stop_atr_multiple"] = round(float(g["risk"]["stop_atr_multiple"]) * 1.5, 2)
    return g


def recycle(conn, cfg) -> list:
    """Mutate rejected strategies into new versions, within the recycle limit (§23)."""
    init(conn)
    limit = int((cfg.get("factory") or {}).get("max_recycles_per_strategy", 2))
    made = []
    for key, ver in so.in_state(conn, league.REJECTED):
        if not key.startswith("fx_"):
            continue
        n_versions = len(league.versions(conn, key))
        if ver != n_versions or n_versions > limit:      # only the newest, and within budget
            continue
        # Do not recycle an idea rejected for missing data or a thin sample:
        # mutation cannot fix either.
        why = conn.execute("SELECT stage, reason FROM failure_log WHERE strategy_key=? AND version=? "
                           "ORDER BY id DESC LIMIT 1", (key, ver)).fetchone()
        if why and why[0] in ("data", "sample"):
            continue
        m = so.meta(conn, key, ver)
        how, what = MUTATIONS[(n_versions - 1) % len(MUTATIONS)]
        if how == "quality_filter" and "daily_fundamentals" not in (m.get("data_requirements") or []):
            how, what = MUTATIONS[n_versions % len(MUTATIONS)]
        g = _mutate(so.genome(conn, key, ver), how)
        obj = {"strategy_key": key, "name": f"{m.get('family')} v{n_versions + 1} ({how})",
               "family": m["family"], "league": m["league"], "genome": g,
               "parameters": {**(m.get("parameters") or {}), "mutation": how},
               "hypothesis": f"recycled: {what}", "economic_rationale": m.get("economic_rationale"),
               "data_requirements": m.get("data_requirements"), "universe": m.get("universe"),
               "source": "recycle", "source_ref": f"{key} v{ver}", "parent_key": key,
               "features": m.get("features"), "intraday": False}
        r = so.register(conn, obj, author="discovery.recycle")
        if r["new"]:
            rq.enqueue(conn, "recycle", key, family=m["family"], strategy_key=key,
                       version=r["version"], reason=what)
            made.append((key, r["version"], how))
    return made


def status(conn, cfg) -> dict:
    rec = family_record(conn)
    tested = {f: r["tested"] for f, r in rec.items() if r["tested"]}
    total = sum(tested.values())
    ent = -sum((n / total) * math.log(n / total) for n in tested.values()) if total else 0.0
    return {"families": len(rec),
            "explored": sorted(f for f, r in rec.items() if r["tested"]),
            "ignored": sorted(f for f, r in rec.items() if not r["tested"]),
            "data_blocked": sorted(f for f in sf.F if not sf.F[f]["data_available"]),
            "diversity_entropy": round(ent, 3),
            "diversity_max": round(math.log(len(tested)), 3) if tested else 0.0,
            "queue": rq.counts(conn)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--recycle", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    conn = storage.connect(cfg["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    if a.recycle:
        print(f"  recycled: {recycle(conn, cfg)}")
    if a.plan:
        print(f"  plan: {plan(conn, cfg)}")
    if a.status or not (a.plan or a.recycle):
        s = status(conn, cfg)
        print(f"  families {s['families']}, explored {len(s['explored'])}, ignored "
              f"{len(s['ignored'])}, data-blocked {len(s['data_blocked'])}")
        print(f"  diversity {s['diversity_entropy']} of max {s['diversity_max']}")
        print(f"  queue {s['queue']}")
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
