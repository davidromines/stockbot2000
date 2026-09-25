"""
The Stockbot2000 Control Center (Addendum D, Stage N1). Read-only.

One page that shows what the machine is doing right now: the broker account,
the five slots and why each strategy holds its slot, every live event in
order, the whole strategy ranking, the next possible replacements, research
activity and system health.

    python monitor.py --serve          # http://localhost:8787  (this page)
    python control_center.py --json    # the same snapshot as JSON
    python control_center.py --once    # a terminal summary

WHAT IT READS — nothing here is computed twice
----------------------------------------------
- slots, positions, trades   slot_assignments, slot_trades, slot_marks (slot_trader.py)
- orders, risk decisions     orders, signals, risk_events (execution.py, risk_engine.py)
- account                    trader_runs (one row per trader run) and live_equity (robinhood_live.py)
- ranking, replacements      slots.plan() -> ranking.rank(); cached, it takes ~7 s
- paper / research           fund_accounting (accounting.py), strategy_decisions (factory)

THREE BOOKS, NEVER MIXED (§3)
-----------------------------
BROKER ACCOUNT is the real Robinhood account and its LIVE slot trades only.
SIMULATED/PAPER is the forward funds' restated accounting. RESEARCH is counts
and decisions, never dollars. No figure from one book is added to another.

Deliberately read-only: the database is opened with mode=ro, it makes no
broker call, and it imports nothing that can place an order.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).parent
PLAN_TTL = 60                # seconds between slots.plan() recomputations
STALE_HEARTBEAT_MIN = 15     # a trader heartbeat older than this, in market hours, is a failure

_cache = {"at": 0.0, "plan": None, "error": None}
_lock = threading.Lock()


def _db(cfg):
    p = cfg["database"]["market_data_path"]
    c = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=5)
    c.row_factory = sqlite3.Row
    return c


def _rows(c, sql, args=()):
    try:
        return [dict(r) for r in c.execute(sql, args)]
    except sqlite3.OperationalError:
        return []          # a table another module has not created yet


def _one(c, sql, args=()):
    r = _rows(c, sql, args)
    return r[0] if r else {}


def _now():
    return datetime.now(timezone.utc)


def _age_min(iso):
    if not iso:
        return None
    try:
        return (_now() - datetime.fromisoformat(str(iso).replace("Z", "+00:00"))).total_seconds() / 60
    except ValueError:
        return None


def _market_open():
    try:
        import quotes
        return bool(quotes.market_open())
    except Exception:                                        # noqa: BLE001
        return False


def _risk_limits():
    try:
        import risk_engine
        return risk_engine.load_limits()
    except Exception:                                        # noqa: BLE001
        return {}


# --- ranking and plan (slow; cached) ---------------------------------------------

def _plan(cfg):
    with _lock:
        if _cache["plan"] is not None and time.time() - _cache["at"] < PLAN_TTL:
            return _cache["plan"], _cache["error"]
        try:
            import slots
            c = _db(cfg)
            p = slots.plan(c, cfg)
            c.close()
            _cache.update(at=time.time(), plan=p, error=None)
        except Exception as e:                               # noqa: BLE001
            _cache.update(at=time.time(), error=f"{type(e).__name__}: {e}")
        return _cache["plan"], _cache["error"]


# --- the broker book ----------------------------------------------------------------

def _spread(c, symbol):
    import costs
    r = _one(c, "SELECT dollar_volume_20 FROM features WHERE ticker=? AND dollar_volume_20 IS NOT NULL "
                "ORDER BY date DESC LIMIT 1", (symbol,))
    return float(costs.estimate_spread_pct(float(r.get("dollar_volume_20") or 0)))


def live_positions(c):
    """Open LIVE slot positions from the append-only trade log, marked at the latest monitor price."""
    opens, closed = {}, []
    for t in _rows(c, "SELECT * FROM slot_trades WHERE mode='LIVE' ORDER BY id"):
        if t["action"] == "OPEN":
            opens[t["slot_id"]] = t
        else:
            o = opens.pop(t["slot_id"], None)
            if o:
                q = float(t["quantity"])
                gross = (float(t["price"]) - float(o["price"])) * q
                cost = (_spread(c, t["symbol"]) / 2) * (float(o["price"]) + float(t["price"])) * q
                closed.append({**t, "entry_price": o["price"], "entry_at": o["at"], "gross": gross,
                               "cost": cost, "net": gross - cost, "strategy_key": o["strategy_key"]})
    pos = {}
    for slot, o in opens.items():
        m = _one(c, "SELECT price, stop, verdict, at FROM slot_marks WHERE mode='LIVE' AND slot_id=? "
                    "AND symbol=? ORDER BY id DESC LIMIT 1", (slot, o["symbol"]))
        q, entry = float(o["quantity"]), float(o["price"])
        px = float(m["price"]) if m.get("price") else None
        plan = json.loads(o["stop_plan"] or "[]")
        tp = next((p.get("pct") or p.get("take_profit_pct") for p in plan if p.get("type") == "take_profit"), None)
        max_hold = next((p.get("max_hold_days") for p in plan if p.get("type") == "time"), None)
        spread = _spread(c, o["symbol"])
        gross = (px - entry) * q if px else None
        cost = spread / 2 * (entry + (px or entry)) * q
        pos[slot] = {"slot": slot, "symbol": o["symbol"], "quantity": q, "entry_price": entry,
                     "entry_at": o["at"], "price": px, "price_at": m.get("at"), "stop": m.get("stop"),
                     "verdict": m.get("verdict"), "take_profit_pct": tp,
                     "take_profit_price": entry * (1 + float(tp) / 100) if tp else None,   # pct, as stop_plans "max_hold_days": max_hold,
                     "cost_basis": entry * q, "market_value": px * q if px else None,
                     "unrealized_gross": gross, "est_costs": cost,
                     "unrealized_net": gross - cost if gross is not None else None,
                     "strategy_key": o["strategy_key"], "version": o["version"], "stop_plan": plan,
                     "reason": o["reason"]}
    return pos, closed


def broker_book(c):
    runs = _rows(c, "SELECT * FROM trader_runs WHERE mode='LIVE' ORDER BY id DESC LIMIT 200")
    last = runs[0] if runs else {}
    sync = next((r for r in runs if r.get("equity") is not None), {})
    eq_rows = _rows(c, "SELECT * FROM live_equity ORDER BY at DESC LIMIT 1")
    eq = eq_rows[0] if eq_rows else {}
    equity = sync.get("equity") if sync else eq.get("equity")
    cash = sync.get("cash") if sync else eq.get("buying_power")
    unsettled = sync.get("unsettled")
    session = (eq.get("session") or "")
    prev = _one(c, "SELECT equity FROM live_equity WHERE session < ? ORDER BY at DESC LIMIT 1", (session,))
    first = _one(c, "SELECT equity, at FROM live_equity ORDER BY at LIMIT 1")
    pos, closed = live_positions(c)
    unreal_g = sum(p["unrealized_gross"] or 0 for p in pos.values())
    unreal_c = sum(p["est_costs"] for p in pos.values())
    real_g = sum(t["gross"] for t in closed)
    real_c = sum(t["cost"] for t in closed)
    return {
        "equity": equity, "available_cash": cash, "unsettled": unsettled,
        "settled_cash": (cash - unsettled) if (cash is not None and unsettled is not None) else None,
        "invested": sum(p["market_value"] or p["cost_basis"] for p in pos.values()),
        "unrealized_pnl": unreal_g, "realized_pnl": real_g,
        "today_pnl": (equity - prev["equity"]) if (equity is not None and prev.get("equity")) else None,
        "cumulative_pnl_equity": (equity - first["equity"]) if (equity is not None and first.get("equity")) else None,
        "since": first.get("at"),
        "gross_pnl": unreal_g + real_g, "est_costs": unreal_c + real_c,
        "net_pnl": unreal_g + real_g - unreal_c - real_c,
        "positions": len(pos), "closed_trades": len(closed),
        "last_sync": sync.get("at") or eq.get("at"), "last_heartbeat": last.get("at"),
        "last_outcome": last.get("outcome"), "reconciled": sync.get("reconciled"),
        "diffs": sync.get("diffs"), "open": pos, "closed": closed[-20:],
    }


def paper_book(c, plan):
    """
    Forward (paper) evidence PER STRATEGY — never a total across strategies.

    A sum over unrelated paper funds answers no question this system asks. Paper
    trading exists to say which strategies make money forward, whether that is
    growing, and which could take a live slot. So: how many are positive, the
    best by forward return per trade (with the trade count beside it), and the
    live holders' own paper record.
    """
    ranked = (plan or {}).get("ranked") or []
    fw = [r for r in ranked if (r.get("forward_trades") or 0) > 0 and r.get("forward") is not None]
    top = sorted(fw, key=lambda r: -r["forward"])[:6]
    held = {(h["strategy_key"], h["version"]) for h in ((plan or {}).get("held") or {}).values() if h}
    pick = lambda r: {k: r.get(k) for k in ("name", "family", "forward", "forward_trades", "net_usd",  # noqa: E731
                                            "max_drawdown_pct", "sessions", "eligible")}
    return {"with_forward": len(fw), "positive": sum(1 for r in fw if r["forward"] > 0),
            "no_forward": len(ranked) - len(fw), "top": [pick(r) for r in top],
            "live_holders": [pick(r) for r in ranked if (r["strategy_key"], r["version"]) in held],
            "problems": sum(1 for r in ranked if r.get("recon_status") == "ACCOUNTING_PROBLEM")}


def research_book(c, plan):
    ranked = (plan or {}).get("ranked") or []
    decisions = _rows(c, "SELECT at, strategy_key, version, decision, to_state, reason FROM strategy_decisions "
                         "ORDER BY id DESC LIMIT 15")
    states = {}
    for r in ranked:
        states[r.get("state") or "?"] = states.get(r.get("state") or "?", 0) + 1
    last_factory = _tail(ROOT / "logs/daily.log", r"\[9f/10\]")
    return {"ranked": len(ranked), "eligible": sum(1 for r in ranked if r.get("eligible")),
            "states": states, "recent_decisions": decisions, "last_factory_line": last_factory,
            "last_decision_at": decisions[0]["at"] if decisions else None}


# --- slots, ranking, replacements ------------------------------------------------------

def _why(row, rank):
    if not row:
        return None
    return {"rank": rank, "score": row.get("score"), "backtest": row.get("backtest"),
            "backtest_source": row.get("backtest_source"), "forward": row.get("forward"),
            "forward_trades": row.get("forward_trades"), "net_usd": row.get("net_usd"),
            "max_drawdown_pct": row.get("max_drawdown_pct"), "worst_case": row.get("worst_case"),
            "eligible": row.get("eligible"), "reasons": row.get("reasons") or []}


def slot_view(c, cfg, plan, book):
    import slots
    held = slots.current(c, cfg)
    ranked = (plan or {}).get("ranked") or []
    pos_rank = {(r["strategy_key"], r["version"]): (i, r) for i, r in enumerate(ranked, 1)}
    count = int(slots.settings(cfg)["count"])
    out = []
    for slot in range(1, count + 1):
        h = held.get(slot)
        if not h:
            out.append({"slot": slot, "status": "CASH", "why": "no qualified strategy assigned"})
            continue
        key, ver = h["strategy_key"], h["version"]
        rank, row = pos_rank.get((key, ver), (None, None))
        p = book["open"].get(slot)
        trades = [t for t in book["closed"] if t.get("strategy_key") == key]
        wins = sum(1 for t in trades if t["net"] > 0)
        assign = _one(c, "SELECT at, reason, evidence FROM slot_assignments WHERE slot_id=? AND action='ASSIGN' "
                         "AND strategy_key=? ORDER BY id DESC LIMIT 1", (slot, key))
        status = "IN POSITION" if p else ("WAITING FOR ENTRY" if row and row.get("eligible") else "HELD, NOT ELIGIBLE")
        days = None
        if p:
            days = round((_age_min(p["entry_at"]) or 0) / 1440, 1)
        out.append({
            "slot": slot, "status": status, "strategy_key": key, "version": ver,
            "name": (row or {}).get("name") or key, "family": (row or {}).get("family"),
            "capital": h.get("capital_usd"), "since": h.get("since"), "position": p,
            "hold_days": days, "live_trades": len(trades),
            "live_win_rate": wins / len(trades) if trades else None,
            "live_avg_trade": sum(t["net"] for t in trades) / len(trades) if trades else None,
            "live_net": sum(t["net"] for t in trades),
            "paper": {k: (row or {}).get(k) for k in ("net_usd", "gross_usd", "costs_usd", "closed_trades",
                                                     "sessions", "max_drawdown_pct")},
            "selected_because": _why(row, rank), "assigned_reason": assign.get("reason"),
            "assigned_at": assign.get("at"),
        })
    return out


def leaderboard(plan, slot_rows):
    ranked = (plan or {}).get("ranked") or []
    in_slot = {(s.get("strategy_key"), s.get("version")): s["slot"] for s in slot_rows if s.get("strategy_key")}
    top5 = {(r["strategy_key"], r["version"]) for r in [x for x in ranked if x.get("eligible")][:5]}
    out = []
    for i, r in enumerate(ranked, 1):
        k = (r["strategy_key"], r["version"])
        status = "LIVE" if k in in_slot else (r.get("state") or "?")
        out.append({"rank": i, "name": r.get("name"), "strategy_key": r["strategy_key"], "version": r["version"],
                    "family": r.get("family"), "status": status, "state": r.get("state"),
                    "score": r.get("score"), "backtest": r.get("backtest"), "backtest_source": r.get("backtest_source"),
                    "worst_case": r.get("worst_case"), "paper": r.get("forward"), "trades": r.get("forward_trades"),
                    "net_usd": r.get("net_usd"), "drawdown": r.get("max_drawdown_pct"), "as_of": r.get("as_of"),
                    "eligible": r.get("eligible"), "reasons": r.get("reasons") or [],
                    "slot": in_slot.get(k), "challenger": k not in in_slot and k in top5})
    return out


def replacements(c, plan, board):
    """What slots.plan() would do now, plus the nearest challenger per held slot and what blocks it."""
    if not plan:
        return {"pending": [], "challengers": []}
    s = plan["settings"]
    pending = [{"slot": sl, "action": "RELEASE", "strategy": h.get("strategy_key"), "reason": why}
               for sl, h, why in plan["release"]]
    pending += [{"slot": sl, "action": "ASSIGN", "strategy": r.get("strategy_key"), "name": r.get("name"),
                 "reason": why} for sl, r, why in plan["assign"]]
    import slots
    live = [b for b in board if b["slot"]]
    chall = [b for b in board if not b["slot"] and b["eligible"]][:5]
    rows = []
    today = _now().date().isoformat()
    done_today = int(_one(c, "SELECT COUNT(*) n FROM slot_assignments WHERE action='RELEASE' AND reason LIKE "
                             "'replaced%' AND substr(at,1,10)=?", (today,)).get("n") or 0)
    if live and chall:
        weakest = min(live, key=lambda b: b["score"] if b["score"] is not None else -1e9)
        since = (plan["held"].get(weakest["slot"]) or {}).get("since")
        held_for = slots._sessions_since(c, since) if since else 0
        for ch in chall:
            adv = (ch["score"] or 0) - (weakest["score"] or 0)
            need = s["min_advantage_score"]
            blocks = []
            if adv < need:
                blocks.append(f"advantage {adv:+.2%}/trade < required {need:+.2%}")
            fams = [b["family"] for b in live if b["slot"] != weakest["slot"]]
            if fams.count(ch["family"]) >= s["max_per_family"]:
                blocks.append(f"family {ch['family']} already holds {s['max_per_family']} slots")
            if held_for < s["min_hold_sessions"]:
                blocks.append(f"current holder has {held_for} of {s['min_hold_sessions']} sessions")
            if done_today >= s["max_replacements_per_day"]:
                blocks.append(f"{done_today} replacements today (max {s['max_replacements_per_day']})")
            rows.append({"current_slot": weakest["slot"], "current": weakest["name"], "current_rank": weakest["rank"],
                         "current_score": weakest["score"], "candidate": ch["name"], "candidate_rank": ch["rank"],
                         "candidate_score": ch["score"], "candidate_trades": ch["trades"], "advantage": adv,
                         "status": "ELIGIBLE" if not blocks else "BLOCKED", "blocked_by": blocks})
    return {"pending": pending, "challengers": rows,
            "rules": {k: s[k] for k in ("min_advantage_score", "min_hold_sessions", "max_replacements_per_day",
                                         "max_per_family")}}


def replacement_history(c):
    return _rows(c, "SELECT at, slot_id, action, strategy_key, version, mode, reason, evidence FROM slot_assignments "
                    "ORDER BY id DESC LIMIT 30")


# --- the live event feed ------------------------------------------------------------------

def feed(c, mode="LIVE", limit=150):
    ev = []
    for r in _rows(c, "SELECT created_at at, symbol, action, notional_value, strategy, reason FROM signals "
                      "WHERE strategy LIKE 'slot%' ORDER BY created_at DESC LIMIT ?", (limit,)):
        ev.append({"at": r["at"], "kind": "SIGNAL", "sev": "info",
                   "text": f"{r['strategy'].split(':')[0].upper()} {r['action']} {r['symbol']}"
                           + (f" ${r['notional_value']:.2f}" if r.get("notional_value") else "") + f" — {r['reason']}"})
    for r in _rows(c, "SELECT created_at at, symbol, side, notional, state, filled_quantity, avg_fill_price, note "
                      "FROM orders WHERE mode=? ORDER BY created_at DESC LIMIT ?", (mode, limit)):
        fill = (f" {r['filled_quantity']:.6f} @ ${r['avg_fill_price']:.2f}" if r.get("avg_fill_price") else "")
        sev = "bad" if r["state"] in ("REJECTED", "FAILED", "CANCELLED") else "good" if r["state"] == "FILLED" else "info"
        ev.append({"at": r["at"], "kind": f"ORDER {r['state']}", "sev": sev,
                   "text": f"{r['side']} {r['symbol']}" + (f" ${r['notional']:.2f}" if r.get("notional") else "")
                           + fill + (f" — {r['note']}" if r.get("note") else "")})
    for r in _rows(c, "SELECT at, slot_id, symbol, action, quantity, price, reason, stop_plan FROM slot_trades "
                      "WHERE mode=? ORDER BY id DESC LIMIT ?", (mode, limit)):
        kind = "POSITION OPENED" if r["action"] == "OPEN" else "TRADE CLOSED"
        ev.append({"at": r["at"], "kind": kind, "sev": "good" if r["action"] == "OPEN" else "info",
                   "text": f"SLOT {r['slot_id']} {r['symbol']} {r['quantity']:.6f} @ ${r['price']:.2f} — {r['reason']}"})
    for r in _rows(c, "SELECT at, symbol, decision, reasons FROM risk_events ORDER BY id DESC LIMIT ?", (limit,)):
        if r["decision"] == "APPROVED":
            continue
        why = "; ".join(json.loads(r["reasons"] or "[]"))
        ev.append({"at": r["at"], "kind": f"RISK {r['decision']}", "sev": "warn", "text": f"{r['symbol']}: {why}"})
    for r in _rows(c, "SELECT at, kind, detail, severity FROM system_events ORDER BY id DESC LIMIT ?", (limit,)):
        ev.append({"at": r["at"], "kind": r["kind"].upper().replace("_", " "),
                   "sev": "bad" if r["severity"] == "critical" else "info", "text": r["detail"]})
    for r in _rows(c, "SELECT at, slot_id, action, strategy_key, reason FROM slot_assignments ORDER BY id DESC LIMIT ?",
                   (limit,)):
        ev.append({"at": r["at"], "kind": f"SLOT {r['action']}", "sev": "info",
                   "text": f"SLOT {r['slot_id']} {r['strategy_key']} — {r['reason']}"})
    # Stop checks: one line per slot per hour, not one per five-minute poll.
    seen = set()
    for r in _rows(c, "SELECT at, slot_id, symbol, price, stop, verdict FROM slot_marks WHERE mode=? "
                      "ORDER BY id DESC LIMIT 400", (mode,)):
        k = (r["slot_id"], r["at"][:13])
        if k in seen and r["verdict"] == "within plan":
            continue
        seen.add(k)
        ev.append({"at": r["at"], "kind": "POSITION MONITOR", "sev": "info" if r["verdict"] == "within plan" else "warn",
                   "text": f"SLOT {r['slot_id']} {r['symbol']} ${r['price']:.2f}, stop ${r['stop']:.2f} — {r['verdict']}"})
    for r in _rows(c, "SELECT at, outcome, error, diffs FROM trader_runs WHERE mode=? AND outcome NOT IN "
                      "('ok','market_closed') ORDER BY id DESC LIMIT 50", (mode,)):
        ev.append({"at": r["at"], "kind": r["outcome"].upper().replace("_", " "), "sev": "bad",
                   "text": r.get("error") or r.get("diffs") or ""})
    ev.sort(key=lambda e: e["at"], reverse=True)
    return ev[:limit]


# --- system health ------------------------------------------------------------------------

def _tail(path, pattern=None):
    if not path.exists():
        return ""
    try:
        lines = path.read_text(errors="replace").splitlines()[-4000:]
    except OSError:
        return ""
    if pattern:
        lines = [x for x in lines if re.search(pattern, x)]
    return lines[-1] if lines else ""


def _log_counts(path, day):
    err = warn = 0
    if path.exists():
        for line in path.read_text(errors="replace").splitlines()[-20000:]:
            if not line.startswith(day):
                continue
            if " ERROR " in line or " CRITICAL " in line:
                err += 1
            elif " WARNING " in line and "Session termination failed" not in line:
                warn += 1
    return err, warn


def health(c, cfg, plan_error):
    now = _now()
    mkt = _market_open()
    limits = _risk_limits()
    checks = []

    def add(name, ok, detail, warn=False):
        checks.append({"name": name, "state": "ok" if ok else ("warn" if warn else "fail"), "detail": detail})

    for mode in ("LIVE", "SHADOW", "SIMULATION"):
        r = _one(c, "SELECT at, outcome FROM trader_runs WHERE mode=? ORDER BY id DESC LIMIT 1", (mode,))
        age = _age_min(r.get("at"))
        if not r:
            add(f"{mode} trader heartbeat", not mkt, "no heartbeat recorded yet", warn=True)
        else:
            fresh = age is not None and (age < STALE_HEARTBEAT_MIN or not mkt)
            add(f"{mode} trader heartbeat", fresh and r["outcome"] in ("ok", "market_closed"),
                f"{r['outcome']}, {age:.0f} min ago")
    sync = _one(c, "SELECT at, reconciled, diffs FROM trader_runs WHERE mode='LIVE' AND reconciled IS NOT NULL "
                   "ORDER BY id DESC LIMIT 1")
    if sync:
        add("LIVE reconciliation", sync["reconciled"] == 1,
            f"{'OK' if sync['reconciled'] else 'FAILED: ' + (sync.get('diffs') or '')}, {_age_min(sync['at']):.0f} min ago")
    else:
        add("LIVE reconciliation", False, "not recorded yet", warn=True)
    last_order = _one(c, "SELECT created_at, state, symbol FROM orders WHERE mode='LIVE' ORDER BY created_at DESC LIMIT 1")
    last_fill = _one(c, "SELECT created_at, symbol FROM orders WHERE mode='LIVE' AND state='FILLED' "
                        "ORDER BY created_at DESC LIMIT 1")
    last_mark = _one(c, "SELECT at, symbol FROM slot_marks WHERE mode='LIVE' ORDER BY id DESC LIMIT 1")
    bar = _one(c, "SELECT MAX(date) d FROM prices WHERE ticker='SPY'").get("d")
    add("data: newest SPY bar", bool(bar), str(bar))
    add("ranking engine", plan_error is None, plan_error or f"recomputed every {PLAN_TTL}s")
    daily = _tail(ROOT / "logs/daily.log", r"Daily capture complete|WITH FAILURES|FAILED")
    add("daily job (07:00 UTC)", "complete" in daily and "FAIL" not in daily, daily[:120] or "no run found")
    tok = Path.home() / ".config/stockbot2000/robinhood_oauth.json"
    add("Robinhood sign-in token", tok.exists(), "present" if tok.exists() else "missing — run robinhood_mcp.py --login")
    kill = (ROOT / "data/KILL_SWITCH").exists() or os.environ.get("TRADING_ENABLED", "true").lower() == "false"
    add("kill switch", not kill, "ENGAGED — trading stopped" if kill else "off")
    add("execution mode", True, str(limits.get("execution_mode", "?")))

    du = shutil.disk_usage("/")
    mem = Path("/proc/meminfo").read_text()
    tot = int(re.search(r"MemTotal:\s+(\d+)", mem).group(1)) / 1048576
    av = int(re.search(r"MemAvailable:\s+(\d+)", mem).group(1)) / 1048576
    ram_pct = (tot - av) / tot * 100
    add("RAM", ram_pct < 90, f"{tot - av:.1f} / {tot:.1f} GB ({ram_pct:.0f}%)", warn=ram_pct < 97)
    add("disk", du.free / 1e9 > 10, f"{du.free / 1e9:.0f} GB free ({du.used / du.total * 100:.0f}% used)")
    load = os.getloadavg()[0]
    cores = os.cpu_count() or 1
    add("CPU load", load < cores * 1.5, f"{load:.2f} on {cores} cores", warn=True)
    day = now.date().isoformat()
    err, warn = _log_counts(ROOT / "logs/slot_trader_live.log", day)
    add("LIVE log today", err == 0, f"{err} errors, {warn} warnings (MCP session-close noise excluded)",
        warn=err < 3)
    procs = []
    try:
        ps = subprocess.run(["ps", "-eo", "pid,etime,pcpu,rss,args"], capture_output=True, text=True, timeout=5).stdout
        for line in ps.splitlines()[1:]:
            m = re.search(r"(\w+\.py|daily\.sh|lab_loop\.sh)", line)
            if m and "control_center" not in line and "monitor.py" not in line and "venv/bin/python" in line \
                    or (m and ".sh" in m.group(1)):
                f = line.split(None, 4)
                procs.append({"pid": f[0], "elapsed": f[1], "cpu": f[2], "rss_gb": int(f[3]) / 1048576,
                              "what": m.group(1)})
    except Exception:                                        # noqa: BLE001
        pass
    return {"market_open": mkt, "checks": checks, "processes": procs,
            "last": {"quote/mark": last_mark.get("at"), "order": last_order.get("created_at"),
                     "fill": last_fill.get("created_at"), "reconciliation": sync.get("at") if sync else None,
                     "ranking": datetime.fromtimestamp(_cache["at"], timezone.utc).isoformat() if _cache["at"] else None,
                     "strategy decision": (_one(c, "SELECT MAX(at) a FROM strategy_decisions").get("a"))},
            "failures": sum(1 for x in checks if x["state"] == "fail")}


# --- the snapshot -----------------------------------------------------------------------------

def snapshot(cfg=None) -> dict:
    from universe import load_config
    cfg = cfg or load_config()
    plan, plan_error = _plan(cfg)
    c = _db(cfg)
    try:
        book = broker_book(c)
        slot_rows = slot_view(c, cfg, plan, book)
        board = leaderboard(plan, slot_rows)
        return {
            "generated_at": _now().isoformat(), "execution_mode": _risk_limits().get("execution_mode"),
            "broker": {k: v for k, v in book.items() if k not in ("open", "closed")},
            "positions": list(book["open"].values()), "closed_trades": book["closed"],
            "paper": paper_book(c, plan), "research": research_book(c, plan),
            "slots": slot_rows, "leaderboard": board, "replacements": replacements(c, plan, board),
            "replacement_history": replacement_history(c), "feed": feed(c), "health": health(c, cfg, plan_error),
        }
    finally:
        c.close()


def page() -> str:
    return (ROOT / "control_center.html").read_text()


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Stockbot2000 Control Center (read-only).")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--once", action="store_true")
    a = ap.parse_args(argv)
    s = snapshot()
    if a.json:
        print(json.dumps(s, indent=1, default=str))
        return 0
    b = s["broker"]
    f = lambda v: "—" if v is None else f"${v:,.2f}"            # noqa: E731
    print(f"\n  BROKER ACCOUNT ({s['execution_mode']})  equity {f(b['equity'])}  cash {f(b['available_cash'])}  "
          f"net P&L {f(b['net_pnl'])}  last sync {b['last_sync']}")
    for sl in s["slots"]:
        p = sl.get("position") or {}
        print(f"  slot {sl['slot']}: {sl['status']:<18} {str(sl.get('name', ''))[:30]:<30} "
              f"{p.get('symbol', ''):<6} {f(p.get('unrealized_net')) if p else ''}")
    print(f"  health: {s['health']['failures']} failing check(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
