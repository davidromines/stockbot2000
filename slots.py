"""
The five live slots. Addendum A §4, §8-14, §26; Addendum B §B4-B7, §B10-B11.

Which strategies should control the slots RIGHT NOW, and what changes that
implies. Covers build steps I1 (slot model), I2 (allocation), I3 (replacement),
I4 (P&L-first leaderboard) and I10 (daily reassessment).

THE RULES THAT ARE LOAD-BEARING
-------------------------------
1. **Rank, then fill (owner's rule, 2026-09-24; supersedes B3/B4/B6).** Every
   strategy is ranked by ranking.py: expected net return per trade, starting
   from its backtest and moving to its paper record as trades arrive. The five
   slots hold the five best that can be traded — on day one, with no evidence
   floor and no lifecycle state to reach first. Paper evidence de-ranks.
2. **What still blocks a slot protects money**: a backtest that loses net
   (step-1 gate), no valid stop plan, a strategy kill switch, accounting that
   disagrees with itself, evidence that stopped updating. A slot is cash only
   when fewer than five strategies clear those.
3. **Family cap (B7)**, `max_per_family` in config (4 at the owner's request).
4. **Rank on the score**, with gross / costs / net shown beside it.
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
    "min_advantage_score": 0.002,    # ... or by this much expected net return per trade (ranking.py)
    "min_hold_sessions": 5,          # a holder keeps its slot at least this long unless ineligible
    "max_replacements_per_day": 1,   # churn bound (§9)
    "max_evidence_lag_sessions": 3,  # evidence older than this is stale data (B19)
    "max_per_family": 1,             # slots one strategy family may hold (B7); configurable
    # Stage K: crypto scores +12..+22%/trade on 30-60 day holds against ~0.5% for stocks, so
    # armed it would take most slots on backtests carried by 2017 and 2020. At most this many
    # crypto slots, whatever the scores (the cap recommended before K7, built 2026-09-27).
    "max_crypto_slots": 1,
    # Five different bets, not five copies of one (strategy_diversity.py): a candidate whose
    # measured correlation (weekly returns, 2023 -> today) with a held or chosen strategy is
    # above this does not take a slot. Unmeasured pairs fall back to the family cap.
    "max_correlation": 0.7,
    # Per-family overrides of max_per_family. ETF rotation variants of one universe hold
    # the same few ETFs and cannot be measured by strategy_diversity (no stock rule), so
    # one slot per rotation universe.
    "family_caps": {"etf_rotation_sectors": 1, "etf_rotation_assets": 1},
    # Owner, 2026-09-28: a strategy the ranking predicts to lose (score below this, expected
    # net return per 20 sessions held) may not hold or take a slot. MACD Pullback held slot 5
    # at -0.69% because only a losing BACKTEST released a holder.
    "min_score": 0.0,
    # Owner, 2026-09-28: when a slot's own strategy has no buy signal, the trader may fill it
    # with the best eligible strategy not in a slot that does (a stand-in). The daily
    # reassessment records this many, best first, in slot_reviews.
    "standins": 5,
    # Owner, 2026-09-28: a strategy whose entry rule fired on fewer than this many of the
    # last `activity_sessions` sessions cannot hold or take a slot (a "December effect"
    # rule held slot 1 in September). Fund-type strategies are not measured. 0 = off.
    "min_active_sessions": 1,
    "activity_sessions": 60,
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


PAIR_RISK = {"stop_atr_multiple": 3.0}


def pair_risk(which: str = "pair_risk", cfg: dict | None = None) -> dict:
    """The stop a pair-fund (`slots.pair_risk`) or Value Fund (`slots.value_risk`) slot carries.
    Neither fund's own record has a stop."""
    if cfg is None:
        try:
            from universe import load_config
            cfg = load_config()
        except Exception:                                    # noqa: BLE001
            cfg = {}
    return dict((cfg.get("slots") or {}).get(which) or PAIR_RISK)


def genome_for(conn, key: str, version: int) -> dict | None:
    """
    The rules a strategy trades, wherever they are stored.

    A pair fund (`pair:<name>`) has no genome: it holds whichever ETF of its
    pair its signal picks. Its slot rules are {"pair": name} — slot_trader asks
    pair_funds.next_leg() for the ETF — plus a price stop from `slots.pair_risk`
    (§15: no slot without one) and the fund's switch as the strategy exit.
    """
    g = None
    if key.startswith("pair:"):
        return {"pair": key.split(":", 1)[1], "risk": pair_risk(), "exit": "switch when the fund switches"}
    if key.startswith("option:"):
        # Stage R: options strategies are bounded by their own expiry and time stop;
        # options_live.py handles P&L-based exits. The option_expiry stop type tells
        # the risk engine "this position has a structural loss floor" without comparing
        # it to a stock price level.
        import options_lab
        name = key.split(":", 1)[1]
        spec = options_lab.STRATEGIES.get(name) or {}
        hold = int(spec.get("hold") or 20)
        tp = spec.get("take_profit")
        risk = {"option_expiry": True, "max_hold_days": hold}
        if tp:
            risk["take_profit_pct"] = float(tp) * 100  # spec stores 0.50 = 50%
        return {"option": name, "risk": risk, "exit": "options_lab exit signal"}
    if key.startswith("value:"):
        # Owner's option C (2026-09-24): the slot holds the Value Fund's
        # top-ranked current holding, with a price stop the fund itself does
        # NOT use (a slot must have one, §15), and sells when the fund does.
        return {"value": key.split(":", 1)[1], "risk": pair_risk("value_risk"),
                "exit": "sell when the fund sells it"}
    if key.startswith("crypto:"):
        # Stage K5: a crypto trend fund's slot mirrors the fund's holding
        # (crypto_slot_trader.py); its price stop is the fund's own ATR stop,
        # resting at the broker. The grid fund has no stop and stays out.
        r = conn.execute("SELECT strategy FROM crypto_fund WHERE name=?", (key.split(":", 1)[1],)).fetchone() \
            if conn.execute("SELECT 1 FROM sqlite_master WHERE name='crypto_fund'").fetchone() else None
        try:
            st = json.loads(r[0]) if r else {}
        except (TypeError, ValueError):
            st = {}
        cg = st.get("genome") if st.get("engine") == "crypto_trend" else None
        if not cg or not cg.get("stop_atr"):
            return None
        return {"crypto": key.split(":", 1)[1], "risk": {"stop_atr_multiple": float(cg["stop_atr"])},
                "exit": "sell when the fund closes the position"}
    if key.startswith("fx_"):
        # ETF rotation strategies store their rule as parameters, not entry/exit trees;
        # so.genome() drops the "rotation" marker, and a rotation slot or stand-in was
        # then treated as a stock rule with no exit (TypeError, found 2026-09-28).
        m = so.meta(conn, key, version)
        if m and m.get("source") == "etf_rotation" and isinstance(m.get("parameters"), dict):
            import rotation_funds
            return rotation_funds.genome(m["parameters"])
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
    Every strategy, ranked (ranking.py), with the verdict on each LIVE gate.
    Nothing is dropped silently: an excluded strategy carries the first reason
    it failed, so the report can say why it is not in a slot.

    The owner's rule (2026-09-24): the five slots always hold the five best
    strategies that can be traded. There is no evidence floor and no lifecycle
    state to reach first; the ranking starts from the backtest and paper
    evidence moves it. What still blocks a slot is what protects money:
    a backtest that loses (the step-1 gate), no valid stop plan (so no way to
    trade it with a price stop), a strategy kill switch, broken accounting, or
    evidence that has stopped updating.
    """
    import ranking
    s = settings(cfg)
    latest = _latest_session(conn)
    out = []
    for r in ranking.rank(conn, cfg):
        key, ver = r["strategy_key"], r["version"]
        reasons = []
        if not r["passes_gate"]:
            reasons.append(r["gate"])
        halted = killswitch.strategy_halted(conn, key)
        if halted:
            reasons.append(f"strategy kill switch: {halted}")
        # A strategy too new to have an accounting row ranks on its backtest;
        # only accounting that DISAGREES with itself blocks it.
        if r.get("recon_status") == "ACCOUNTING_PROBLEM":
            reasons.append("accounting ACCOUNTING_PROBLEM")
        if r.get("as_of") and latest:
            lag = int(conn.execute("SELECT COUNT(DISTINCT date) FROM prices WHERE ticker='SPY' "
                                   "AND date > ? AND date <= ?", (r["as_of"], latest)).fetchone()[0])
            if lag > s["max_evidence_lag_sessions"]:
                reasons.append(f"stale evidence: {lag} sessions behind")
        if r.get("score") is not None and r["score"] < s["min_score"]:
            reasons.append(f"predicted to lose: score {r['score']:+.2%} per 20 sessions held")
        if key.startswith("crypto:") and not _crypto_armed():
            reasons.append("crypto not armed: config/risk.yaml allow_crypto is false (Stage K7, owner)")
        if key.startswith("option:") and not _options_armed():
            reasons.append("options not armed: config/risk.yaml allow_options is false (R7, owner)")
        plan = stop_plans.from_genome(genome_for(conn, key, ver))
        ok, why = stop_plans.validate(plan)
        if not ok:
            reasons.append(f"not tradeable in a slot — stop plan: {why[0]}")
        out.append({**r, "eligible": not reasons, "reasons": reasons, "stop_plan": plan})
    # Rank on the score; more forward trades breaks ties — more evidence wins.
    out.sort(key=lambda x: (-_rank_value(x), -(x.get("forward_trades") or 0)))
    return out


def standins(conn) -> list:
    """[(key, version)] the latest reassessment recorded as stand-ins, best first."""
    try:
        r = conn.execute("SELECT summary FROM slot_reviews ORDER BY id DESC LIMIT 1").fetchone()
    except sqlite3.Error:
        return []
    if not r:
        return []
    return [tuple(x) for x in (json.loads(r[0]).get("standins") or [])]


def _crypto_armed() -> bool:
    """The operator's switch. Unknown (unreadable limits) counts as off."""
    try:
        import risk_engine
        return bool(risk_engine.load_limits().get("allow_crypto"))
    except Exception:                                        # noqa: BLE001 — fail closed
        return False


def _options_armed() -> bool:
    """The operator's switch (R7). Off until the owner sets allow_options: true."""
    try:
        import risk_engine
        return bool(risk_engine.load_limits().get("allow_options"))
    except Exception:                                        # noqa: BLE001 — fail closed
        return False


def _rank_value(r: dict) -> float:
    """The ranking score where one exists, else net P&L (older callers and tests)."""
    if r.get("score") is not None:
        return float(r["score"])
    return float(r["net_usd"]) if r.get("net_usd") is not None else -1e9


# --- I3: allocation and replacement -------------------------------------------

def _idle_check(conn, cfg, s):
    """A cached function row -> reason string if the strategy's entry rule is idle, else ''.
    Fails open (''): the rule is about wasted slots, not risk, and a measurement error must
    not empty the slots."""
    n, window = int(s.get("min_active_sessions") or 0), int(s.get("activity_sessions") or 60)
    cache, frame = {}, {}

    def idle(r):
        if n <= 0:
            return ""
        k = (r["strategy_key"], r["version"])
        if k not in cache:
            if "df" not in frame:
                try:
                    import paper_trading as pt
                    frame["df"] = pt._recent_frame(conn, cfg)
                except (KeyError, TypeError):
                    frame["df"] = None   # cfg incomplete — fail open silently
                except Exception as e:  # noqa: BLE001
                    log.warning(f"activity frame: {type(e).__name__}: {e}")
                    frame["df"] = None
            if frame.get("df") is None:
                cache[k] = ""
            else:
                try:
                    import signal_activity as sa
                    a = sa.activity(conn, cfg, k[0], k[1], df=frame["df"], sessions=window)
                    cache[k] = (f"entry rule fired on {a['active_sessions']} of the last {window} sessions"
                                if a["measurable"] and "error" not in a and (a["active_sessions"] or 0) < n else "")
                except Exception as e:                       # noqa: BLE001 — fail open
                    log.warning(f"activity check {k[0]}: {type(e).__name__}: {e}")
                    cache[k] = ""
        return cache[k]
    return idle


def plan(conn, cfg: dict) -> dict:
    """What the slots should be, and the releases and assignments that implies."""
    s = settings(cfg)
    init(conn)
    held = current(conn, cfg)
    ranked = assess(conn, cfg)
    by_key = {(r["strategy_key"], r["version"]): r for r in ranked}
    eligible = [r for r in ranked if r["eligible"]]

    idle = _idle_check(conn, cfg, s)
    releases, keep = [], {}
    for slot, h in held.items():
        if h is None:
            continue
        r = by_key.get((h["strategy_key"], h["version"]))
        if r is None:
            releases.append((slot, h, "no longer in the forward pool"))
        elif not r["eligible"]:
            releases.append((slot, h, f"no longer eligible: {r['reasons'][0]}"))
        elif idle(r):
            releases.append((slot, h, f"no longer eligible: {idle(r)}"))
        else:
            keep[slot] = {**h, "row": r}

    held_keys = {(h["strategy_key"], h["version"]) for h in keep.values()}
    from collections import Counter
    held_fams = Counter(h["row"]["family"] for h in keep.values())
    is_crypto = lambda k: str(k).startswith("crypto:")                      # noqa: E731
    fam_cap = lambda f: int((s.get("family_caps") or {}).get(f, s["max_per_family"]))  # noqa: E731
    held_crypto = sum(1 for h in keep.values() if is_crypto(h["strategy_key"]))
    challengers = [r for r in eligible if (r["strategy_key"], r["version"]) not in held_keys]

    assigns = []
    skipped_corr = []

    def too_similar(r, others):
        """(correlation, key) of the first chosen strategy r is too correlated with, or None."""
        import strategy_diversity as sd
        for o in others:
            c = sd.lookup(conn, (r["strategy_key"], r["version"]), (o["strategy_key"], o["version"]))
            if c is not None and c > s["max_correlation"]:
                return c, o["strategy_key"]
        return None

    # Fill empty slots first, best first, one per family.
    free = [slot for slot in held if slot not in keep]
    for r in challengers:
        if not free:
            break
        if held_fams[r["family"]] >= fam_cap(r["family"]):
            continue
        sim = too_similar(r, [h for h in keep.values()] + [a[1] for a in assigns])
        if sim:
            skipped_corr.append((r["strategy_key"], sim[0], sim[1]))
            continue
        if is_crypto(r["strategy_key"]) and held_crypto >= s["max_crypto_slots"]:
            continue
        if idle(r):                          # measured last: only candidates about to be assigned
            continue
        slot = free.pop(0)
        assigns.append((slot, r, "eligible and a slot is open"))
        held_fams[r["family"]] += 1
        held_crypto += is_crypto(r["strategy_key"])
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
        weakest_slot = min(keep, key=lambda k: _rank_value(keep[k]["row"]))
        w = keep[weakest_slot]
        scored = r.get("score") is not None and w["row"].get("score") is not None
        adv = _rank_value(r) - _rank_value(w["row"])
        need = s["min_advantage_score"] if scored else s["min_advantage_usd"]
        others = Counter(h["row"]["family"] for sl, h in keep.items() if sl != weakest_slot)
        sim = too_similar(r, [h for sl, h in keep.items() if sl != weakest_slot] + [a[1] for a in assigns])
        if sim:
            skipped_corr.append((r["strategy_key"], sim[0], sim[1]))
            continue
        family_clash = others[r["family"]] >= fam_cap(r["family"]) or (
            is_crypto(r["strategy_key"]) and not is_crypto(w["strategy_key"])
            and sum(1 for sl, h in keep.items() if sl != weakest_slot and is_crypto(h["strategy_key"]))
            >= s["max_crypto_slots"])
        held_for = _sessions_since(conn, w["since"])
        if adv < need or family_clash or held_for < s["min_hold_sessions"] or idle(r):
            continue
        unit = (lambda v: f"{v:+.2%}/trade") if scored else (lambda v: f"${v:+.2f} net")
        releases.append((weakest_slot, w, f"replaced by {r['strategy_key']}: "
                                          f"{unit(_rank_value(r))} vs {unit(_rank_value(w['row']))}"))
        assigns.append((weakest_slot, r, f"replaces {w['strategy_key']} "
                                         f"({unit(adv)} better, holder had {held_for} sessions)"))
        del keep[weakest_slot]
        taken.add((r["strategy_key"], r["version"]))
        replacements += 1

    # Stand-ins (owner, 2026-09-28): the best eligible strategies not in a slot, for a
    # slot whose own strategy has no buy signal. Plain stock rules only — pair, value,
    # rotation and crypto slots have their own signal and exit paths.
    # One per family, and none from a family already in a slot: a variant of a holder
    # whose rule has no signal usually has none either (found 09-28: all five stand-ins
    # were earnings-surprise variants).
    held_now = held_keys | taken
    used_fams = {h["row"]["family"] for h in keep.values()} | {r["family"] for _, r, _ in assigns}
    standins = []
    for r in eligible:
        if len(standins) >= s["standins"]:
            break
        k = (r["strategy_key"], r["version"])
        if k in held_now or str(r["strategy_key"]).startswith("crypto:") or r.get("family") in used_fams:
            continue
        g = genome_for(conn, *k) or {}
        if g.get("pair") or g.get("value") or g.get("crypto") or idle(r):
            continue
        standins.append(list(k))
        used_fams.add(r.get("family"))

    halted = killswitch.global_engaged()
    if halted:
        # §25: promotions freeze while the global switch is on. Releases still
        # happen; nothing new is assigned.
        assigns = []
        releases = [x for x in releases if not x[2].startswith("replaced by")]
    cash = [slot for slot in held if slot not in keep and slot not in {a[0] for a in assigns}]
    return {"held": held, "keep": {k: {kk: vv for kk, vv in v.items() if kk != "row"} for k, v in keep.items()},
            "release": releases, "assign": assigns, "cash_slots": cash, "skipped_correlated": skipped_corr,
            "standins": standins,
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
               "cash_slots": p["cash_slots"], "eligible": p["eligible"], "assessed": p["assessed"],
               "standins": p["standins"]}
    conn.execute("INSERT INTO slot_reviews (at, mode, summary) VALUES (?,?,?)",
                 (at, mode, json.dumps(summary)))
    conn.commit()
    return {**summary, "plan": p}


def owner_replace(conn, cfg: dict, slot: int, key: str, version: int, reason: str,
                  mode: str = "LIVE", rows: list | None = None) -> dict:
    """
    The owner's explicit replacement of one slot's holder (2026-09-28: slot 5, MACD Pullback
    -> Free Cash Flow to Price). Skips the min-hold and advantage rules — that is the owner's
    call — but never the gates that protect money: the new strategy must be eligible
    (assess), not already in a slot, and not correlated above max_correlation with another
    holder. Recorded like any replacement: RELEASE then ASSIGN, reason naming the owner.
    """
    s = settings(cfg)
    if mode not in MODES:
        raise ValueError(f"mode must be one of {MODES}")
    held = current(conn, cfg)
    if slot not in held:
        raise ValueError(f"no slot {slot}")
    rows = rows if rows is not None else assess(conn, cfg)
    r = next((x for x in rows if x["strategy_key"] == key and x["version"] == version), None)
    if r is None:
        raise ValueError(f"{key} v{version} is not in the ranking")
    if not r["eligible"]:
        raise ValueError(f"{key} v{version} is not eligible: {r['reasons'][0]}")
    for sl, h in held.items():
        if h and sl != slot and (h["strategy_key"], h["version"]) == (key, version):
            raise ValueError(f"{key} v{version} already holds slot {sl}")
    import strategy_diversity as sd
    for sl, h in held.items():
        if h and sl != slot:
            c = sd.lookup(conn, (key, version), (h["strategy_key"], h["version"]))
            if c is not None and c > s["max_correlation"]:
                raise ValueError(f"correlation {c:.2f} with slot {sl} ({h['strategy_key']}) "
                                 f"is above {s['max_correlation']}")
    at = _now()
    old = held[slot]
    if old:
        conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, "
                     "capital_usd, mode, reason) VALUES (?,?,?,?,?,?,?,?)",
                     (at, slot, "RELEASE", old["strategy_key"], old["version"], None, mode,
                      f"replaced by owner: {reason}"))
    ev = {k: r.get(k) for k in ("net_usd", "gross_usd", "costs_usd", "sessions", "closed_trades",
                                "max_drawdown_pct", "tier", "family", "league", "score")}
    conn.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, "
                 "capital_usd, mode, reason, evidence) VALUES (?,?,?,?,?,?,?,?,?)",
                 (at, slot, "ASSIGN", key, version, s["capital_per_slot"], mode,
                  f"owner decision: {reason}", json.dumps(ev, default=str)))
    conn.commit()
    return {"slot": slot, "released": old, "assigned": (key, version), "score": r.get("score")}


# --- I4: the P&L-first leaderboard --------------------------------------------

def leaderboard(conn, cfg: dict) -> list:
    """Every strategy, in ranking order (score), with slot or status beside it (§10)."""
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
                     "score": r.get("score"), "backtest": r.get("backtest"), "paper": r.get("forward"),
                     "why_not": None if r["eligible"] else r["reasons"][0]})
    return rows


def _m(v):
    return "—" if v is None else f"{v:+.2f}"


def render_leaderboard(rows: list, limit: int = 40) -> str:
    def pc(v):
        return "     —" if v is None else f"{v:+.2%}"
    out = ["LEADERBOARD (ranked on score = expected net return per trade; gross / costs / net side by side)",
           f"{'#':>3} {'strategy':<30} {'status':<16} {'score':>7} {'bt':>7} {'paper':>7} {'gross':>8} {'costs':>7} "
           f"{'net':>8} {'dd%':>6} {'trades':>6} {'sess':>5}  why not eligible"]
    for r in rows[:limit]:
        out.append(f"{r['rank']:>3} {str(r['strategy'])[:30]:<30} {r['status'][:16]:<16} "
                   f"{pc(r.get('score')):>7} {pc(r.get('backtest')):>7} {pc(r.get('paper')):>7} "
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
    ap.add_argument("--owner-replace", nargs=3, metavar=("SLOT", "KEY", "VERSION"),
                    help="the owner's explicit replacement of one slot's holder (gates still apply)")
    ap.add_argument("--reason", default="owner's instruction")
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
    if args.owner_replace:
        sl, key, ver = args.owner_replace
        r = owner_replace(conn, cfg, int(sl), key, int(ver), args.reason, args.mode)
        old = r["released"]
        print(f"slot {r['slot']}: {old['strategy_key'] + ' v' + str(old['version']) if old else 'CASH'} "
              f"-> {key} v{ver} (score {r['score']:+.2%}) [{args.mode}]")
        return 0
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
