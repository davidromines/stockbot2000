"""
The five live slots. Addendum A §4, §8-14, §26; Addendum B §B4-B7, §B10-B11.

Which strategies should control the slots RIGHT NOW, and what changes that
implies. Covers build steps I1 (slot model), I2 (allocation), I3 (replacement),
I4 (P&L-first leaderboard) and I10 (daily reassessment).

THE RULES THAT ARE LOAD-BEARING
-------------------------------
1. **Eligibility comes first, ranking second (B4).** Only strategies with a
   forward record at league tier ELIGIBLE or ESTABLISHED — which already means
   >= 20 forward sessions, >= 10 closed trades, positive net P&L and drawdown
   under the league limit (B11) — enter the pool. A backtest never does (B3).
2. **Empty slots are valid (B6).** If two strategies qualify, three slots stay
   in cash. Standards are never lowered because capital is idle.
3. **One strategy per family (B7).** Five stop-width variants of one entry
   rule are one bet, not five.
4. **Rank on NET P&L (B5)**, with gross and costs shown beside it.
5. **Replacement is controlled (§9, B11).** An eligible holder keeps its slot
   unless a challenger beats it by `min_advantage_usd` AND the holder has had
   `min_hold_sessions`. A holder that stops being eligible is released at once:
   demotion is easier than promotion, on purpose.
6. **Every strategy needs a valid stop plan (§15)** — see stop_plans.py.
7. **This module places no order.** It decides assignments and records them.
   Trading a slot is slot_trader.py's job, through the existing execution and
   risk layer (B13). In SIMULATION and SHADOW an assignment does not move a
   strategy to LIVE in the league; only a LIVE-mode assignment does, and
   LIVE mode is armed by the user (B14).

STATE
-----
`slot_assignments` is append-only. A slot's current holder is its latest
ASSIGN not followed by a RELEASE — derived, never stored in a mutable column,
the same rule league.py follows for lifecycle state.

    python slots.py --plan            what should change, and why (reads only)
    python slots.py --apply           record the changes (SIMULATION by default)
    python slots.py --leaderboard     the P&L-first leaderboard (§10)
    python slots.py --status          current slot holders
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone

import factory_pipeline
import killswitch
import league
import leagues
import stop_plans
import strategy_objects as so

log = logging.getLogger("slots")

DEFAULTS = {
    "count": 5,
    "capital_per_slot": 20.0,
    "eligible_tiers": ["ELIGIBLE", "ESTABLISHED"],
    "min_advantage_usd": 2.0,        # challenger must beat the weakest holder by this much net
    "min_hold_sessions": 5,          # a holder keeps its slot at least this long unless ineligible
    "max_replacements_per_day": 1,   # churn bound (§9)
    "max_evidence_lag_sessions": 3,  # evidence older than this is stale data (B19)
}
MODES = ("SIMULATION", "SHADOW", "LIVE")


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("slots") or {})}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    leagues.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slot_assignments (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            slot_id       INTEGER NOT NULL,
            action        TEXT NOT NULL CHECK (action IN ('ASSIGN','RELEASE')),
            strategy_key  TEXT,
            version       INTEGER,
            capital_usd   REAL,
            mode          TEXT NOT NULL,
            reason        TEXT NOT NULL,
            evidence      TEXT
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slot_reviews (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            at       TEXT NOT NULL,
            mode     TEXT NOT NULL,
            summary  TEXT NOT NULL
        )""")
    conn.commit()


# --- I1: the slot model -------------------------------------------------------

def current(conn, cfg: dict | None = None) -> dict:
    """slot_id -> holder dict, or None for a slot in cash."""
    init(conn)
    n = settings(cfg or {})["count"]
    out = {i: None for i in range(1, n + 1)}
    cur = conn.execute("SELECT * FROM slot_assignments ORDER BY id")
    cols = [c[0] for c in cur.description]
    for r in cur.fetchall():
        r = dict(zip(cols, r))
        if r["action"] == "ASSIGN":
            out[r["slot_id"]] = {"strategy_key": r["strategy_key"], "version": r["version"],
                                 "capital_usd": r["capital_usd"], "since": r["at"],
                                 "mode": r["mode"]}
        else:
            out[r["slot_id"]] = None
    return out


def _sessions_since(conn, iso_ts: str) -> int:
    day = (iso_ts or "")[:10]
    return int(conn.execute("SELECT COUNT(DISTINCT date) FROM prices WHERE ticker='SPY' AND date > ?",
                            (day,)).fetchone()[0] or 0)


def genome_for(conn, key: str, version: int) -> dict | None:
    """The rules a strategy trades, wherever they are stored."""
    g = None
    if key.startswith("fx_"):
        g = so.genome(conn, key, version)
    else:
        ref = leagues.fund_ref(conn, key, version)
        if ref and ref[0] == "paper":
            row = conn.execute("SELECT strategy FROM paper_runs WHERE run_id=?", (ref[1],)).fetchone()
            try:
                g = json.loads(row[0]) if row and row[0] else None
            except (TypeError, ValueError):
                g = None
    return g if isinstance(g, dict) else None


# --- I2: eligibility and ranking ---------------------------------------------

def _latest_session(conn) -> str | None:
    return conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]


def assess(conn, cfg: dict) -> list:
    """
    Every forward strategy with the verdict on each gate. Nothing is dropped
    silently: an excluded strategy carries the first reason it failed, so the
    report can say why a slot is in cash.
    """
    s = settings(cfg)
    latest = _latest_session(conn)
    rows = []
    for rs in leagues.standings(conn, cfg).values():
        rows.extend(rs)
    out = []
    for r in rows:
        key, ver = r["strategy_key"], r["version"]
        reasons = []
        state = league.canonical(r["state"])
        # The evidence gap first: it is the cause, the lifecycle state follows from it.
        if r["tier"] not in s["eligible_tiers"]:
            lc = cfg["leagues"].get(r["league"], cfg["leagues"]["tactical"])
            reasons.append(f"tier {r['tier']} ({r.get('sessions') or 0}/{lc['min_forward_sessions']} "
                           f"sessions, {r.get('closed_trades') or 0}/{lc['min_closed_trades']} trades)")
        if state not in (league.LIVE_CANDIDATE, league.LIVE):
            reasons.append(f"state {state}: not a live candidate")
        halted = killswitch.strategy_halted(conn, key)
        if halted:
            reasons.append(f"strategy kill switch: {halted}")
        if r.get("recon_status") in ("ACCOUNTING_PROBLEM", "NO_ACCOUNTING"):
            reasons.append(f"accounting {r.get('recon_status')}")
        if r.get("as_of") and latest:
            lag = int(conn.execute("SELECT COUNT(DISTINCT date) FROM prices WHERE ticker='SPY' "
                                   "AND date > ? AND date <= ?", (r["as_of"], latest)).fetchone()[0])
            if lag > s["max_evidence_lag_sessions"]:
                reasons.append(f"stale evidence: {lag} sessions behind")
        plan = stop_plans.from_genome(genome_for(conn, key, ver))
        ok, why = stop_plans.validate(plan)
        if not ok:
            reasons.append(f"stop plan: {why[0]}")
        out.append({**r, "eligible": not reasons, "reasons": reasons, "stop_plan": plan})
    # Rank on net (B5); more forward sessions breaks ties — more evidence wins.
    out.sort(key=lambda x: (-(x.get("net_usd") if x.get("net_usd") is not None else -1e9),
                            -(x.get("sessions") or 0)))
    return out


# --- I3: allocation and replacement -------------------------------------------

def plan(conn, cfg: dict) -> dict:
    """What the slots should be, and the releases and assignments that implies."""
    s = settings(cfg)
    init(conn)
    held = current(conn, cfg)
    ranked = assess(conn, cfg)
    by_key = {(r["strategy_key"], r["version"]): r for r in ranked}
    eligible = [r for r in ranked if r["eligible"]]

    releases, keep = [], {}
    for slot, h in held.items():
        if h is None:
            continue
        r = by_key.get((h["strategy_key"], h["version"]))
        if r is None:
            releases.append((slot, h, "no longer in the forward pool"))
        elif not r["eligible"]:
            releases.append((slot, h, f"no longer eligible: {r['reasons'][0]}"))
        else:
            keep[slot] = {**h, "row": r}

    held_keys = {(h["strategy_key"], h["version"]) for h in keep.values()}
    held_fams = {h["row"]["family"] for h in keep.values()}
    challengers = [r for r in eligible if (r["strategy_key"], r["version"]) not in held_keys]

    assigns = []
    # Fill empty slots first, best first, one per family.
    free = [slot for slot in held if slot not in keep]
    for r in challengers:
        if not free:
            break
        if r["family"] in held_fams:
            continue
        slot = free.pop(0)
        assigns.append((slot, r, "eligible and a slot is open"))
        held_fams.add(r["family"])
    taken = {(r["strategy_key"], r["version"]) for _, r, _ in assigns}

    # Controlled replacement of the weakest holder (§8-9, B10-B11).
    replacements = 0
    today = _now()[:10]
    done_today = int(conn.execute("SELECT COUNT(*) FROM slot_assignments WHERE action='RELEASE' "
                                  "AND reason LIKE 'replaced%' AND substr(at,1,10)=?",
                                  (today,)).fetchone()[0])
    for r in challengers:
        if (r["strategy_key"], r["version"]) in taken:
            continue
        if replacements + done_today >= s["max_replacements_per_day"] or not keep:
            break
        weakest_slot = min(keep, key=lambda k: keep[k]["row"].get("net_usd") or 0)
        w = keep[weakest_slot]
        adv = (r.get("net_usd") or 0) - (w["row"].get("net_usd") or 0)
        family_clash = r["family"] in {h["row"]["family"] for sl, h in keep.items() if sl != weakest_slot}
        held_for = _sessions_since(conn, w["since"])
        if adv < s["min_advantage_usd"] or family_clash or held_for < s["min_hold_sessions"]:
            continue
        releases.append((weakest_slot, w, f"replaced by {r['strategy_key']}: "
                                          f"net ${r['net_usd']:+.2f} vs ${w['row']['net_usd']:+.2f}"))
        assigns.append((weakest_slot, r, f"replaces {w['strategy_key']} "
                                         f"(+${adv:.2f} net, holder had {held_for} sessions)"))
        del keep[weakest_slot]
        taken.add((r["strategy_key"], r["version"]))
        replacements += 1

    cash = [slot for slot in held if slot not in keep and slot not in {a[0] for a in assigns}]
    return {"held": held, "keep": {k: {kk: vv for kk, vv in v.items() if kk != "row"} for k, v in keep.items()},
            "release": releases, "assign": assigns, "cash_slots": cash,
            "eligible": len(eligible), "assessed": len(ranked), "ranked": ranked,
            "settings": s}


def apply(conn, cfg: dict, mode: str = "SIMULATION", actor: str = "slots") -> dict:
    """Record the plan. Releases first, so a slot is free before it is refilled."""
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    p = plan(conn, cfg)
    s = p["settings"]
    at = _now()
    for slot, h, why in p["release"]:
        conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, "
                     "capital_usd, mode, reason) VALUES (?,?,?,?,?,?,?,?)",
                     (at, slot, "RELEASE", h["strategy_key"], h["version"], None, mode, why))
    for slot, r, why in p["assign"]:
        ev = {k: r.get(k) for k in ("net_usd", "gross_usd", "costs_usd", "sessions", "closed_trades",
                                    "max_drawdown_pct", "tier", "family", "league")}
        conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, "
                     "capital_usd, mode, reason, evidence) VALUES (?,?,?,?,?,?,?,?,?)",
                     (at, slot, "ASSIGN", r["strategy_key"], r["version"], s["capital_per_slot"],
                      mode, why, json.dumps(ev, default=str)))
        if mode == "LIVE" and league.canonical(league.state(conn, r["strategy_key"], r["version"])) \
                == league.LIVE_CANDIDATE:
            so.decide(conn, r["strategy_key"], r["version"], "PROMOTE",
                      f"assigned slot {slot} in LIVE mode", to_state=league.LIVE,
                      classification="LIVE", actor=actor)
    summary = {"released": len(p["release"]), "assigned": len(p["assign"]),
               "cash_slots": p["cash_slots"], "eligible": p["eligible"], "assessed": p["assessed"]}
    conn.execute("INSERT INTO slot_reviews (at, mode, summary) VALUES (?,?,?)",
                 (at, mode, json.dumps(summary)))
    conn.commit()
    return {**summary, "plan": p}


# --- I4: the P&L-first leaderboard --------------------------------------------

def leaderboard(conn, cfg: dict) -> list:
    """Every forward strategy, ranked on net P&L, with slot or status beside it (§10)."""
    held = {(h["strategy_key"], h["version"]): slot for slot, h in current(conn, cfg).items() if h}
    rows = []
    for i, r in enumerate(assess(conn, cfg), 1):
        slot = held.get((r["strategy_key"], r["version"]))
        status = f"SLOT {slot}" if slot else ("ELIGIBLE" if r["eligible"] else league.canonical(r["state"]))
        rows.append({"rank": i, "strategy": r.get("name") or r["strategy_key"], "key": r["strategy_key"],
                     "version": r["version"], "status": status, "family": r["family"],
                     "gross_usd": r.get("gross_usd"), "costs_usd": r.get("costs_usd"),
                     "net_usd": r.get("net_usd"), "max_drawdown_pct": r.get("max_drawdown_pct"),
                     "trades": r.get("closed_trades"), "sessions": r.get("sessions"),
                     "why_not": None if r["eligible"] else r["reasons"][0]})
    return rows


def _m(v):
    return "—" if v is None else f"{v:+.2f}"


def render_leaderboard(rows: list, limit: int = 40) -> str:
    out = ["LEADERBOARD (ranked on net P&L; gross / costs / net side by side)",
           f"{'#':>3} {'strategy':<30} {'status':<16} {'gross':>8} {'costs':>7} {'net':>8} "
           f"{'dd%':>6} {'trades':>6} {'sess':>5}  why not eligible"]
    for r in rows[:limit]:
        out.append(f"{r['rank']:>3} {str(r['strategy'])[:30]:<30} {r['status'][:16]:<16} "
                   f"{_m(r['gross_usd']):>8} {_m(-(r['costs_usd'] or 0) if r['costs_usd'] is not None else None):>7} "
                   f"{_m(r['net_usd']):>8} {(r['max_drawdown_pct'] or 0):>6.2f} {r['trades'] or 0:>6} "
                   f"{r['sessions'] or 0:>5}  {r['why_not'] or ''}")
    return "\n".join(out)


def render_plan(p: dict) -> str:
    out = [f"SLOTS — {p['eligible']} eligible of {p['assessed']} forward strategies"]
    for slot in sorted(p["held"]):
        h = p["held"][slot]
        out.append(f"  slot {slot}: " + (f"{h['strategy_key']} v{h['version']} (${h['capital_usd']:.0f})"
                                         if h else "CASH"))
    for slot, h, why in p["release"]:
        out.append(f"  RELEASE slot {slot}: {h['strategy_key']} — {why}")
    for slot, r, why in p["assign"]:
        out.append(f"  ASSIGN  slot {slot}: {r['strategy_key']} v{r['version']} "
                   f"net {_m(r.get('net_usd'))} — {why}")
    if p["cash_slots"]:
        out.append(f"  stays CASH: slots {p['cash_slots']} — no further eligible strategy (B6)")
    return "\n".join(out)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[1])
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--mode", default="SIMULATION", choices=MODES)
    ap.add_argument("--leaderboard", action="store_true")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    if args.mode == "LIVE":
        # Arming LIVE is the user's step (B14). It is refused here unless the
        # operator has set it in config/risk.yaml, never by a flag alone.
        import risk_engine
        if str(risk_engine.load_limits().get("execution_mode", "SIMULATION")).upper() != "LIVE":
            print("LIVE refused: config/risk.yaml execution_mode is not LIVE (arming is the user's step)")
            return 2
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    init(conn)
    if args.apply:
        r = apply(conn, cfg, args.mode)
        print(render_plan(r["plan"]))
        print(f"  recorded in {args.mode}: {r['released']} released, {r['assigned']} assigned")
    elif args.plan or not (args.leaderboard or args.status):
        print(render_plan(plan(conn, cfg)))
    if args.leaderboard:
        print(render_leaderboard(leaderboard(conn, cfg)))
    if args.status:
        for slot, h in current(conn, cfg).items():
            print(f"slot {slot}: " + (f"{h['strategy_key']} v{h['version']} since {h['since']} [{h['mode']}]"
                                      if h else "CASH"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
