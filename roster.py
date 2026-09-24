"""
RETIRED 2026-09-24 (owner's decision). The Phase 10 promotion path —
promotion_policy.py, roster.py, allocation.py, live_pipeline.py — is replaced
by ONE system: ranking.py scores every strategy and slots.py fills the five
slots from it. Kept, with its tests, as the record of what applied before;
daily.sh no longer runs it, and nothing trades from it.

The live roster: who holds a slot, who loses one. Phase 10, item 33.

The replacement cycle from the spec:

    a strategy enters the top five -> receives capital -> underperforms ->
    falls below the promotion threshold -> risk engine evaluates -> demoted ->
    capital becomes available -> best eligible paper strategy is promoted

`plan()` computes what the roster SHOULD be and what changes that implies.
`apply()` moves lifecycle states and records the reasoning. Neither places an
order: a promotion here moves a strategy to LIVE in the league, and a human
still places every trade.

Demotion is deliberately easier than promotion. A strategy leaves the roster
when it stops being eligible, when it falls below the demotion threshold, or
when the kill switch says so — and any of those is enough. Promotion needs
everything: readiness, eligibility, an open slot, and the correlation veto.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import allocation
import eligibility
import league as lg
import promotion_policy as pp
import scoreboard as sb
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("roster")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS roster_changes (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            strategy_key  TEXT NOT NULL,
            action        TEXT NOT NULL,
            reason        TEXT NOT NULL,
            dollars       REAL,
            applied       INTEGER NOT NULL
        )
    """)
    conn.commit()


def current(conn) -> list:
    """Whoever is LIVE right now."""
    return [r for r in lg.roster(conn) if r["state"] == lg.LIVE]


def plan(conn, cfg: dict, formula: str = sb.DEFAULT_FORMULA) -> dict:
    """What should change, and why. Reads only."""
    init(conn)
    live = current(conn)
    live_keys = {r["strategy_key"] for r in live}

    assessed = {r["strategy_key"]: r for r in eligibility.assess(conn, cfg, formula)}
    proposal = eligibility.propose(conn, cfg, formula)
    target = [r["strategy_key"] for r in proposal["roster"]]

    demote = []
    for k in live_keys:
        a = assessed.get(k)
        if a is None:
            demote.append((k, "no longer in the league"))
        elif not a["eligible"]:
            demote.append((k, f"no longer eligible: {a['reasons'][0]}"))
        elif k not in target:
            demote.append((k, "displaced by a better eligible strategy"))

    demote_keys = {k for k, _ in demote}
    promote = []
    for k in target:
        if k in live_keys and k not in demote_keys:
            continue
        if k in live_keys:
            continue
        d = pp.evaluate(conn, cfg, k, actor="roster.plan")
        if d["permitted"]:
            promote.append((k, "eligible, permitted, and a slot is open"))
        else:
            promote.append((k, f"BLOCKED: {d['blockers'][0]}"))

    alloc = allocation.allocate(conn, cfg, formula=formula)
    return {"live": live, "target": target, "demote": demote,
            "promote": promote, "allocation": alloc,
            "changes": len(demote) + len([p for p in promote
                                          if not p[1].startswith("BLOCKED")])}


def apply(conn, cfg: dict, formula: str = sb.DEFAULT_FORMULA,
          actor: str = "roster") -> dict:
    """
    Move lifecycle states. Demotions first, so capital is freed before it is
    committed — the other order can promote into a slot that is still occupied.
    """
    p = plan(conn, cfg, formula)
    at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    done = []

    for k, why in p["demote"]:
        try:
            lg.transition(conn, k, lg.DEMOTED, why, actor=actor)
            ok = 1
        except lg.LeagueError as e:
            why, ok = f"refused: {e}", 0
        conn.execute("""INSERT INTO roster_changes (at, strategy_key, action,
            reason, dollars, applied) VALUES (?,?,?,?,?,?)""",
            (at, k, "DEMOTE", why, None, ok))
        done.append(("DEMOTE", k, ok))

    dollars = {a["strategy_key"]: a["dollars"]
               for a in p["allocation"].get("allocations", [])}
    for k, why in p["promote"]:
        if why.startswith("BLOCKED"):
            conn.execute("""INSERT INTO roster_changes (at, strategy_key,
                action, reason, dollars, applied) VALUES (?,?,?,?,?,?)""",
                (at, k, "PROMOTE", why, None, 0))
            done.append(("PROMOTE", k, 0))
            continue
        try:
            # ELIGIBLE -> LIVE_CANDIDATE -> LIVE. The intermediate state is not
            # ceremony: it is where a human decides, and skipping it would make
            # promotion automatic, which Phase 10 forbids.
            if lg.state(conn, k) == lg.ELIGIBLE:
                lg.transition(conn, k, lg.LIVE_CANDIDATE, why, actor=actor)
            ok = 1
        except lg.LeagueError as e:
            why, ok = f"refused: {e}", 0
        conn.execute("""INSERT INTO roster_changes (at, strategy_key, action,
            reason, dollars, applied) VALUES (?,?,?,?,?,?)""",
            (at, k, "PROMOTE_CANDIDATE", why, dollars.get(k), ok))
        done.append(("PROMOTE_CANDIDATE", k, ok))

    conn.commit()
    return {"applied": done, "plan": p}


def history(conn, limit: int = 40) -> list:
    init(conn)
    return [dict(r) for r in conn.execute(
        f"SELECT * FROM roster_changes ORDER BY id DESC LIMIT {int(limit)}")]


def render(p: dict) -> str:
    L = ["", "  LIVE ROSTER PLAN", "  " + "-" * 68,
         f"  currently live : {len(p['live'])}",
         f"  target roster  : {len(p['target'])}"]
    if p["demote"]:
        L += ["", "  DEMOTE"]
        for k, why in p["demote"]:
            L.append(f"    {k[:24]:<26}{why[:40]}")
    if p["promote"]:
        L += ["", "  PROMOTE"]
        for k, why in p["promote"]:
            L.append(f"    {k[:24]:<26}{why[:40]}")
    if not p["demote"] and not p["promote"]:
        L += ["", "  No changes. Nothing is live and nothing is eligible."]
    L += ["", allocation.render(p["allocation"]).strip("\n"),
          "", "  A promotion here moves a strategy to LIVE_CANDIDATE in the",
          "  league. It places no order — a human still does that.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plan", action="store_true")
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.history:
        rows = history(conn)
        print(f"\n  ROSTER CHANGES ({len(rows)})")
        for r in rows:
            print(f"  {r['at'][:16]}  {r['action']:<18}{r['strategy_key'][:22]:<24}"
                  f"{'applied' if r['applied'] else 'refused'}")
        if not rows:
            print("  none")
        print()
        conn.close(); return 0

    if a.apply:
        res = apply(conn, cfg)
        print(render(res["plan"]))
        print(f"  applied {sum(1 for _, _, ok in res['applied'] if ok)} of "
              f"{len(res['applied'])} changes\n")
        conn.close(); return 0

    print(render(plan(conn, cfg)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
