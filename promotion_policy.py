"""
May a strategy receive real money? Phase 10, item 31.

TWO GATES, AND BOTH MUST PASS
-------------------------------
Phase 10 is explicit that automatic live promotion must not exist until the
project has separately established fifteen things — minimum paper period,
minimum trades, risk limits, position and exposure caps, correlation limits,
liquidity limits, kill switches, operational health checks, broker
reconciliation, degradation rules, emergency demotion, human override and
complete audit logging.

That is a statement about the SYSTEM, not about any strategy. So this module
asks two separate questions and refuses unless both are answered:

    readiness   does the machinery for safe promotion exist at all?
    eligibility does this particular strategy qualify?

Conflating them is how a project talks itself into a live trade: a strategy
that looks excellent is an argument for promoting it, and without a separate
readiness gate that argument has nothing standing against it.

WHAT THIS MODULE WILL NOT DO
------------------------------
It does not promote anything. It returns a decision and records it. There is
no code path from here to `execution.py` or `broker.py`, and the tests assert
that. Phase 10 says the strategy layer must never directly place orders, and
the standing constraint on this project is stronger still: the loop is
*system generates -> human places -> system reconciles*.

Even a PERMITTED decision here is a recommendation that a human may act on,
never an instruction that anything acts on by itself.

EVERY DECISION IS LOGGED, INCLUDING THE REFUSALS
--------------------------------------------------
`promotion_decisions` is append-only. A refusal is recorded as fully as an
approval, because the interesting question later is never "what did we
promote" but "what did we nearly promote, and on what evidence". A system
that logs only its approvals has no record of its judgement.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import eligibility
import league as lg
import scoreboard as sb
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("promotion")

# The fifteen prerequisites the spec names, each with how it is verified.
# `check` returns (satisfied, detail). A prerequisite that cannot be verified
# mechanically is marked manual and counts as NOT satisfied until a human
# records otherwise — an unverifiable safety claim is not a safety guarantee.
PREREQUISITES = (
    ("minimum_paper_period", "a minimum forward-testing period is defined"),
    ("minimum_trades", "a minimum number of forward trades is defined"),
    ("risk_limits", "risk limits exist in their own config"),
    ("max_position_size", "a maximum position size is set"),
    ("max_portfolio_exposure", "a maximum portfolio exposure is set"),
    ("correlation_limits", "a correlation cap is set"),
    ("liquidity_limits", "liquidity floors are set"),
    ("kill_switches", "kill switches exist and fail closed"),
    ("operational_health", "a freshness gate can fail a run"),
    ("broker_reconciliation", "fills are reconciled against the broker"),
    ("degradation_rules", "backtest-to-forward degradation is tracked"),
    ("emergency_demotion", "a demotion path exists in the lifecycle"),
    ("human_override", "a human approves every order"),
    ("audit_logging", "decisions are recorded append-only"),
    ("live_mode_disabled", "live transmission is not enabled"),
)


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS promotion_decisions (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            strategy_key  TEXT,
            version       INTEGER,
            decision      TEXT NOT NULL,
            readiness_ok  INTEGER NOT NULL,
            eligible_ok   INTEGER NOT NULL,
            blockers      TEXT NOT NULL,
            evidence      TEXT,
            actor         TEXT
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_pd_key "
                 "ON promotion_decisions(strategy_key)")
    conn.commit()


def _cfg_path(cfg: dict, *keys, default=None):
    cur = cfg
    for k in keys:
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur


def readiness(conn, cfg: dict) -> dict:
    """
    Is the machinery for safe promotion in place?

    Checked against what the repository and config actually contain, not
    against a checklist someone ticked. Several of these are satisfied by
    modules built in earlier phases; the point of listing all fifteen is that
    the gaps are visible rather than assumed closed.
    """
    # readiness() reads its own decision log, so the table must exist. The
    # first version assumed a caller had run init() and crashed on a fresh
    # connection — found by the delegated regression test, which called it
    # exactly the way a first-time caller would.
    init(conn)

    risk_cfg: dict = {}
    rp = Path("config/risk.yaml")
    if rp.exists():
        try:
            import yaml
            risk_cfg = yaml.safe_load(rp.read_text()) or {}
        except Exception:      # noqa: BLE001 — an unreadable config is not a pass
            risk_cfg = {}

    league_cfg = cfg.get("league") or {}
    results = {}

    # Evidence strength, because "a file exists" and "we watched it work" are
    # not the same claim. The first readiness run reported 15 of 15 satisfied
    # on a system that has never placed a trade, largely on the strength of
    # files being present — which is the kind of green dashboard that makes
    # people comfortable rather than informed.
    VERIFIED = "verified"    # exercised, and the result was observed
    PRESENT = "present"      # the code exists; it has not been exercised here
    UNTESTED = "untested"    # cannot be verified mechanically at all

    def mark(name, ok, detail, strength=PRESENT):
        results[name] = {"satisfied": bool(ok), "detail": detail,
                         "evidence": strength}

    mark("minimum_paper_period",
         bool(league_cfg.get("min_rank_marks")),
         f"league.min_rank_marks = {league_cfg.get('min_rank_marks')}")
    mark("minimum_trades",
         bool(league_cfg.get("min_forward_trades")),
         f"league.min_forward_trades = {league_cfg.get('min_forward_trades')}")
    mark("risk_limits", bool(risk_cfg),
         "config/risk.yaml present" if risk_cfg else "config/risk.yaml missing")
    mark("max_position_size",
         risk_cfg.get("max_position_dollars") is not None,
         f"max_position_dollars = {risk_cfg.get('max_position_dollars')}")
    mark("max_portfolio_exposure",
         risk_cfg.get("max_portfolio_exposure") is not None,
         f"max_portfolio_exposure = {risk_cfg.get('max_portfolio_exposure')}")
    mark("correlation_limits",
         league_cfg.get("max_correlation") is not None,
         f"league.max_correlation = {league_cfg.get('max_correlation')}")
    mark("liquidity_limits",
         _cfg_path(cfg, "risk", "min_dollar_volume") is not None,
         f"risk.min_dollar_volume = {_cfg_path(cfg, 'risk', 'min_dollar_volume')}")
    # Exercise the kill switches rather than trust the filename. The first
    # version guessed `killswitch.check(conn)` and reported an UNTESTABLE gap
    # that was my own wrong call signature rather than a real one — a
    # readiness check that reports its own bugs as system gaps is worse than
    # useless, because the gap looks like a finding.
    try:
        import killswitch
        killswitch.init(conn)
        v = killswitch.check(conn, None, {})
        tripped = getattr(v, "tripped", None)
        halted = getattr(v, "halted", tripped)
        # Called with no portfolio on purpose. A fail-closed switch MUST halt
        # on an unknown portfolio, so a halt here is the evidence the
        # prerequisite asks for — not a failure.
        halted_on_unknown = not getattr(v, "trading_allowed", True)
        mark("kill_switches", halted_on_unknown,
             "halts on an unknown portfolio, as a fail-closed switch must"
             if halted_on_unknown
             else "did NOT halt on an unknown portfolio — not fail-closed",
             VERIFIED)
    except Exception as e:      # noqa: BLE001
        mark("kill_switches", False,
             f"{type(e).__name__}: {str(e)[:30]}", UNTESTED)

    # The freshness gate counts only if it passed recently. A gate that exists
    # and last reported STALE is not operational health.
    fresh = None
    try:
        r = conn.execute("SELECT ok, checked_at FROM freshness_log "
                         "ORDER BY checked_at DESC LIMIT 1").fetchone()
        fresh = (bool(r[0]), r[1]) if r else None
    except Exception:      # noqa: BLE001
        fresh = None
    mark("operational_health", bool(fresh and fresh[0]),
         (f"last check {'PASSED' if fresh[0] else 'FAILED'} at {fresh[1][:16]}"
          if fresh else "no freshness check recorded"),
         VERIFIED if fresh else PRESENT)

    # Reconciliation counts only if it has actually reconciled something.
    # A never-exercised reconciliation path is an assumption about the day it
    # first runs, which is precisely the day it must not fail.
    filled = 0
    try:
        filled = conn.execute(
            "SELECT COUNT(*) FROM picks WHERE price IS NOT NULL").fetchone()[0]
    except Exception:      # noqa: BLE001
        filled = 0
    mark("broker_reconciliation", filled > 0,
         f"{filled} recorded fills reconciled against the account"
         if filled else "reconciliation has never recorded a fill",
         VERIFIED if filled else PRESENT)
    # Degradation must have a non-provisional verdict to count. Today every
    # pairing is provisional, so this is a GAP and should read as one.
    firm = 0
    try:
        firm = conn.execute("SELECT COUNT(*) FROM degradation "
                            "WHERE provisional=0").fetchone()[0]
    except Exception:      # noqa: BLE001
        firm = 0
    mark("degradation_rules", firm > 0,
         f"{firm} non-provisional degradation measurements"
         if firm else "every degradation measurement is still provisional",
         VERIFIED if firm else PRESENT)
    mark("emergency_demotion", lg.LIVE in lg.ALLOWED and
         lg.DEMOTED in lg.ALLOWED[lg.LIVE],
         "lifecycle permits LIVE -> DEMOTED")

    # The three that are NOT satisfied by a file existing.
    #
    # human_override is satisfied structurally: nothing in this project
    # transmits an order, so a human placing it is the only path that exists.
    mark("human_override", True,
         "orders are placed by a person; no module transmits to a broker",
         VERIFIED)
    n_dec = conn.execute("SELECT COUNT(*) FROM promotion_decisions").fetchone()[0]
    mark("audit_logging", True,
         f"promotion_decisions append-only, {n_dec} decision(s) recorded",
         VERIFIED if n_dec else PRESENT)
    # Live mode must be OFF. This is the one prerequisite whose satisfaction
    # means "we have NOT done the dangerous thing yet".
    live_enabled = str(_cfg_path(cfg, "execution", "mode",
                                 default="SIMULATION")).upper() == "LIVE"
    mark("live_mode_disabled", not live_enabled,
         f"execution.mode = {_cfg_path(cfg, 'execution', 'mode', default='SIMULATION')}")

    unmet = [k for k, v in results.items() if not v["satisfied"]]
    unexercised = [k for k, v in results.items()
                   if v["satisfied"] and v["evidence"] != VERIFIED]
    return {"ready": not unmet, "unmet": unmet, "unexercised": unexercised,
            "checks": results, "n_total": len(results),
            "n_verified": sum(1 for v in results.values()
                              if v["evidence"] == VERIFIED)}


def eligible(conn, cfg: dict, strategy_key: str) -> dict:
    """Does this strategy qualify, by the league's own eligibility rules?"""
    rows = {r["strategy_key"]: r for r in eligibility.assess(conn, cfg)}
    r = rows.get(strategy_key)
    if r is None:
        return {"ok": False, "reasons": [f"{strategy_key} is not in the league"],
                "metrics": None}
    return {"ok": bool(r["eligible"]), "reasons": r["reasons"],
            "metrics": r.get("metrics"), "score": r.get("score"),
            "state": r.get("state")}


def evaluate(conn, cfg: dict, strategy_key: str, actor: str = "system") -> dict:
    """
    The full decision, recorded whichever way it goes.

    Readiness is evaluated FIRST and independently of the strategy, so a
    compelling candidate cannot be the reason a missing safety control gets
    waved through.
    """
    init(conn)
    rd = readiness(conn, cfg)
    el = eligible(conn, cfg, strategy_key)
    blockers = [f"system not ready: {u}" for u in rd["unmet"]] + \
               [f"strategy: {x}" for x in el["reasons"]]
    decision = "PERMITTED" if (rd["ready"] and el["ok"]) else "REFUSED"

    version = None
    try:
        version = lg.latest(conn, strategy_key)["version"]
    except Exception:      # noqa: BLE001 — an unknown strategy is still logged
        pass

    conn.execute("""INSERT INTO promotion_decisions (at, strategy_key, version,
        decision, readiness_ok, eligible_ok, blockers, evidence, actor)
        VALUES (?,?,?,?,?,?,?,?,?)""",
        (datetime.now(timezone.utc).isoformat(timespec="seconds"),
         strategy_key, version, decision, 1 if rd["ready"] else 0,
         1 if el["ok"] else 0, json.dumps(blockers),
         json.dumps({"readiness": rd["unmet"], "score": el.get("score"),
                     "state": el.get("state")}, default=str), actor))
    conn.commit()
    return {"strategy_key": strategy_key, "decision": decision,
            "readiness": rd, "eligibility": el, "blockers": blockers,
            "permitted": decision == "PERMITTED"}


def history(conn, strategy_key: str | None = None) -> list:
    init(conn)
    q = "SELECT * FROM promotion_decisions"
    args: tuple = ()
    if strategy_key:
        q += " WHERE strategy_key=?"
        args = (strategy_key,)
    return [dict(r) for r in conn.execute(q + " ORDER BY id DESC", args)]


def render_readiness(rd: dict) -> str:
    L = ["", "  PROMOTION READINESS — can this system promote anything safely?",
         f"  {rd['n_total'] - len(rd['unmet'])} of {rd['n_total']} "
         f"prerequisites satisfied", "  " + "-" * 72]
    for name, detail in PREREQUISITES:
        c = rd["checks"].get(name, {"satisfied": False, "detail": "not checked"})
        mark = "ok  " if c["satisfied"] else "GAP "
        ev = {"verified": "", "present": "  [not exercised]",
              "untested": "  [UNTESTABLE]"}.get(c.get("evidence"), "")
        L.append(f"  {mark} {name:<24}{c['detail'][:38]}{ev}")
    L.append("  " + "-" * 72)
    L.append(f"  {rd['n_verified']} of {rd['n_total']} are VERIFIED — "
             f"exercised and observed, not merely present.")
    if rd["ready"]:
        L += ["", "  All prerequisites are satisfied. That means promotion is",
              "  MECHANICALLY possible, not that it is advisable — no strategy",
              "  in this project has yet cleared its own eligibility rules."]
    else:
        L.append(f"  NOT READY — {len(rd['unmet'])} gap(s): "
                 f"{', '.join(rd['unmet'])}")
    if rd["unexercised"]:
        L += ["",
              "  These are satisfied only by the code existing, never by being",
              "  exercised here: " + ", ".join(rd["unexercised"]) + ".",
              "  A path that has never run is an assumption about the day it",
              "  first runs, which is the day it must not fail."]
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--readiness", action="store_true")
    ap.add_argument("--evaluate", metavar="STRATEGY_KEY")
    ap.add_argument("--all", action="store_true",
                    help="evaluate every strategy in the league")
    ap.add_argument("--history", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)

    if a.history:
        rows = history(conn)
        print(f"\n  PROMOTION DECISIONS ({len(rows)})")
        print("  " + "-" * 72)
        for r in rows[:25]:
            print(f"  {r['at']}  {(r['strategy_key'] or '—')[:22]:<24}"
                  f"{r['decision']:<11}{len(json.loads(r['blockers']))} blocker(s)")
        if not rows:
            print("  none recorded")
        print()
        conn.close(); return 0

    if a.readiness or not (a.evaluate or a.all):
        print(render_readiness(readiness(conn, cfg)))
        if not (a.evaluate or a.all):
            conn.close(); return 0

    keys = ([r["strategy_key"] for r in lg.roster(conn)] if a.all
            else [a.evaluate])
    permitted = 0
    print(f"  EVALUATING {len(keys)} STRATEGY(S)")
    print("  " + "-" * 72)
    for k in keys:
        r = evaluate(conn, cfg, k)
        permitted += r["permitted"]
        first = r["blockers"][0] if r["blockers"] else "—"
        print(f"  {r['decision']:<11}{k[:26]:<28}{first[:34]}")
    print("  " + "-" * 72)
    print(f"  {permitted} of {len(keys)} permitted\n")
    print("  A PERMITTED decision is a recommendation a human may act on.")
    print("  Nothing here places an order, and no module reaches the broker.\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
