"""
The slot trader. Addendum A §15-17, §23; Addendum B §B13-B14; build steps I6
(position monitor) and I8 (execution, confirmation, recovery, reconciliation).

It trades whatever slots.py has assigned, and nothing else, through the one
execution path this project has: Signal -> ExecutionEngine -> kill switches ->
duplicate check -> RiskEngine (incl. the account-rule guard) -> broker. It adds
no execution or risk logic of its own (B13).

    --trade      at the open: exits first (released slots, breached stops, time
                 and strategy exits), then one entry per empty-handed slot
    --monitor    intraday, every few minutes: stops only — risk overrides the
                 strategy, and no new position is opened (§16-17)
    --status     open slot positions and the reconciliation verdict

Modes (B14): SIMULATION trades a ledger-backed simulated account at LIVE
prices; SHADOW runs the same decisions and risk checks and places nothing;
LIVE is refused unless config/risk.yaml `execution_mode: LIVE`, which is the
user's step, and even then the Robinhood adapter only builds the order
specification — transmission is an operator step (docs/ROBINHOOD_AGENTIC.md).

STATE
-----
`slot_trades` is append-only: an OPEN row per entry fill and a CLOSE row per
exit fill. A slot's position is its latest OPEN without a later CLOSE.
`slot_marks` records every monitor observation (price, running high, stop), so
the trailing high a stop was computed from is on record. On restart the broker
is rebuilt from the orders ledger and compared with slot_trades; any
disagreement halts trading (reconciled=False trips the kill switch) rather than
guessing which side is right.

Fills never happen at a stored close: outside market hours LiveQuotes returns
None and nothing trades.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
from datetime import datetime, timezone

import broker as bk
import execution as ex
import quotes as qt
import risk_engine
import signals as sg
import slots
import stop_plans

log = logging.getLogger("slot_trader")
MAX_TRIES = 5                # candidates tried per slot per entry pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    ex.init(conn)
    slots.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slot_trades (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            at           TEXT NOT NULL,
            mode         TEXT NOT NULL,
            slot_id      INTEGER NOT NULL,
            strategy_key TEXT NOT NULL,
            version      INTEGER NOT NULL,
            symbol       TEXT NOT NULL,
            action       TEXT NOT NULL CHECK (action IN ('OPEN','CLOSE')),
            quantity     REAL NOT NULL,
            price        REAL NOT NULL,
            atr          REAL,
            stop_plan    TEXT,
            reason       TEXT NOT NULL,
            signal_id    TEXT NOT NULL
        )""")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS slot_marks (
            id        INTEGER PRIMARY KEY AUTOINCREMENT,
            at        TEXT NOT NULL,
            mode      TEXT NOT NULL,
            slot_id   INTEGER NOT NULL,
            symbol    TEXT NOT NULL,
            price     REAL,
            high      REAL,
            stop      REAL,
            verdict   TEXT NOT NULL
        )""")
    conn.commit()


def open_positions(conn, mode: str) -> dict:
    """slot_id -> the open position, from the append-only trade log."""
    out = {}
    cur = conn.execute("SELECT * FROM slot_trades WHERE mode=? ORDER BY id", (mode,))
    cols = [c[0] for c in cur.description]
    for r in cur.fetchall():
        r = dict(zip(cols, r))
        if r["action"] == "OPEN":
            r["stop_plan"] = json.loads(r["stop_plan"] or "[]")
            out[r["slot_id"]] = r
        else:
            out.pop(r["slot_id"], None)
    for slot, p in out.items():
        h = conn.execute("SELECT MAX(high) FROM slot_marks WHERE mode=? AND slot_id=? AND symbol=? "
                         "AND at >= ?", (mode, slot, p["symbol"], p["at"])).fetchone()[0]
        p["high_since_entry"] = max(float(h or 0), float(p["price"]))
    return out


def reconcile(conn, broker, mode: str) -> tuple:
    """(ok, differences) between the slot trade log and the broker's positions."""
    want = {}
    for p in open_positions(conn, mode).values():
        want[p["symbol"]] = want.get(p["symbol"], 0.0) + float(p["quantity"])
    have = {s: float(p["quantity"]) for s, p in broker.get_positions().items()}
    if mode == "LIVE":
        # The real account may hold shares this system did not buy (placed by
        # hand). They are not slot positions and are never sold by it. What
        # must hold: the account has AT LEAST what the slot log says it bought.
        diffs = [f"{s}: slots hold {q:.6f} but the account has {have.get(s, 0):.6f}"
                 for s, q in want.items() if have.get(s, 0) + 1e-6 < q]
        return (not diffs), diffs
    diffs = [f"{s}: log {want.get(s, 0):.6f} vs broker {have.get(s, 0):.6f}"
             for s in set(want) | set(have) if abs(want.get(s, 0) - have.get(s, 0)) > 1e-6]
    return (not diffs), diffs


def _session(conn) -> str:
    return datetime.now(qt.NY).date().isoformat()


def _sessions_held(conn, entry_at: str) -> int:
    return int(conn.execute("SELECT COUNT(DISTINCT date) FROM prices WHERE ticker='SPY' AND date >= ?",
                            (entry_at[:10],)).fetchone()[0] or 0)


def _atr(conn, symbol: str) -> float | None:
    r = conn.execute("SELECT atr_14 FROM features WHERE ticker=? AND atr_14 IS NOT NULL "
                     "ORDER BY date DESC LIMIT 1", (symbol,)).fetchone()
    return float(r[0]) if r and r[0] else None


class LiveNotWired(RuntimeError):
    """LIVE was requested but no real broker connection is configured."""


def _build(conn, cfg, mode: str, provider):
    s = slots.settings(cfg)
    limits = risk_engine.load_limits()
    if mode == "LIVE":
        # The simulated ledger broker must never stand in for the account: a
        # LIVE run against it would record simulated fills as live trades. LIVE
        # needs the owner's arming (execution_mode) AND a configured account.
        account = (limits.get("robinhood") or {}).get("account_number")
        if str(limits.get("execution_mode", "SIMULATION")).upper() != "LIVE" or not account:
            raise LiveNotWired("LIVE needs execution_mode: LIVE and robinhood.account_number in "
                               "config/risk.yaml")
        import robinhood_live
        broker = robinhood_live.LiveBroker(conn, account, provider=provider)
        engine = ex.ExecutionEngine(conn, broker, risk_engine.RiskEngine(limits), mode=mode,
                                    session=_session(conn))
        return broker, engine
    broker = bk.LedgerSimulatedBroker(conn, capital=s["count"] * s["capital_per_slot"],
                                      mode=mode, quote_provider=provider)
    engine = ex.ExecutionEngine(conn, broker, risk_engine.RiskEngine(limits), mode=mode,
                                session=_session(conn))
    return broker, engine


def _record_trade(conn, mode, slot, holder, symbol, action, res, reason, plan=None, atr=None):
    o = res.get("order")
    if res.get("status") not in ("filled", "partially_filled") or not o or not o.filled_quantity:
        return False
    conn.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, "
                 "quantity, price, atr, stop_plan, reason, signal_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (_now(), mode, slot, holder["strategy_key"], holder["version"], symbol, action,
                  float(o.filled_quantity), float(o.avg_fill_price), atr,
                  json.dumps(plan) if plan is not None else None, reason, res["signal_id"]))
    conn.commit()
    if mode == "LIVE":
        try:
            import notify
            notify.notify("Stockbot2000 LIVE fill", f"slot {slot} {action} {symbol}: "
                          f"{float(o.filled_quantity):.6f} @ ${float(o.avg_fill_price):.2f} — {reason}")
        except Exception as e:                               # noqa: BLE001
            log.warning(f"fill alert failed: {type(e).__name__}")
    return True


def resolve_pending(conn, cfg, broker, mode: str) -> list:
    """
    Orders from an earlier run that were not final (SUBMITTED / PARTIALLY_FILLED /
    UNKNOWN): ask the broker what happened — never resubmit — and record a fill
    in the slot log. Restart recovery for a real account.
    """
    done = []
    rows = conn.execute(
        "SELECT o.client_order_id, o.broker_order_id, o.side, o.symbol, o.state, s.strategy "
        "FROM orders o JOIN signals s ON s.signal_id = o.signal_id WHERE o.mode=? "
        "AND o.state IN ('SUBMITTED','PARTIALLY_FILLED','UNKNOWN') AND s.strategy LIKE 'slot%'",
        (mode,)).fetchall()
    for cid, boid, side, symbol, state, strategy in rows:
        if not boid:
            continue
        try:
            rec = broker.get_order(boid)
        except Exception as e:                               # noqa: BLE001
            log.warning(f"pending {cid}: {type(e).__name__}: {e}")
            continue
        if not rec or not rec.get("state") or rec["state"] == state:
            continue
        conn.execute("UPDATE orders SET state=?, filled_quantity=?, avg_fill_price=? WHERE client_order_id=?",
                     (rec["state"], rec.get("filled_quantity") or 0, rec.get("avg_fill_price"), cid))
        conn.commit()
        if rec["state"] == bk.FILLED and rec.get("filled_quantity") and rec.get("avg_fill_price"):
            slot_s, key = strategy.split(":", 1)
            slot = int(slot_s.replace("slot", ""))
            ver = (conn.execute("SELECT version FROM slot_assignments WHERE strategy_key=? ORDER BY id DESC "
                                "LIMIT 1", (key,)).fetchone() or [1])[0]
            o = bk.Order(signal_id=cid, symbol=symbol, side=side)
            o.filled_quantity, o.avg_fill_price = rec["filled_quantity"], rec["avg_fill_price"]
            plan = stop_plans.from_genome(slots.genome_for(conn, key, ver)) if side == "BUY" else None
            _record_trade(conn, mode, slot, {"strategy_key": key, "version": ver}, symbol,
                          "OPEN" if side == "BUY" else "CLOSE", {"status": "filled", "order": o, "signal_id": cid},
                          "resolved after submission", plan=plan, atr=_atr(conn, symbol) if side == "BUY" else None)
            done.append((cid, symbol, side))
    return done


def _exit(conn, engine, mode, slot, pos, reason, reconciled, results):
    # SELL the slot's shares, not CLOSE: a CLOSE sells everything held in the
    # symbol, which in a real account can include shares this system never bought.
    sig = sg.Signal(symbol=pos["symbol"], action="SELL", strategy=f"slot{slot}:{pos['strategy_key']}",
                    reason=reason, quantity=float(pos["quantity"]), session=engine.session)
    res = engine.execute(sig, reconciled=reconciled)
    _record_trade(conn, mode, slot, pos, pos["symbol"], "CLOSE", res, reason)
    results.append({"slot": slot, "action": "CLOSE", "symbol": pos["symbol"], "reason": reason,
                    "status": res["status"], "why": res.get("reasons")})


def monitor(conn, cfg, mode: str, provider, results=None, strategy_exits=None) -> list:
    """Stops only (I6). Risk exits outrank any strategy HOLD (§17)."""
    init(conn)
    results = [] if results is None else results
    import killswitch as ks
    why = ks.global_engaged()
    if why:
        return results + emergency(conn, cfg, mode, provider, why)
    broker, engine = _build(conn, cfg, mode, provider)
    if mode == "LIVE":
        resolve_pending(conn, cfg, broker, mode)
    ok, diffs = reconcile(conn, broker, mode)
    if not ok:
        log.error(f"reconciliation failed, trading halts: {diffs}")
    held = slots.current(conn, cfg)
    for slot, pos in open_positions(conn, mode).items():
        holder = held.get(slot)
        if holder is None or (holder["strategy_key"], holder["version"]) != (pos["strategy_key"], pos["version"]):
            _exit(conn, engine, mode, slot, pos, "slot released or reassigned", ok, results)
            continue
        q = provider.get(pos["symbol"])
        price = q["price"] if q else None
        high = max(pos["high_since_entry"], float((q or {}).get("high") or 0), price or 0)
        v = stop_plans.check(pos["stop_plan"], {"entry_price": pos["price"], "atr": pos["atr"],
                                                "high_since_entry": high},
                             price, _sessions_held(conn, pos["at"]),
                             strategy_exit=pos["symbol"] in (strategy_exits or {}).get(slot, set()))
        conn.execute("INSERT INTO slot_marks (at, mode, slot_id, symbol, price, high, stop, verdict) "
                     "VALUES (?,?,?,?,?,?,?,?)", (_now(), mode, slot, pos["symbol"], price, high,
                                                  v["stop_price"], v["reason"]))
        conn.commit()
        if price is None:
            # No live quote: cannot judge the stop, and cannot fill honestly
            # either. Logged; the next poll tries again.
            results.append({"slot": slot, "action": "HOLD", "symbol": pos["symbol"],
                            "reason": "no live quote", "status": "skipped"})
            continue
        if v["exit"]:
            _exit(conn, engine, mode, slot, pos, v["reason"], ok, results)
    return results


def emergency(conn, cfg, mode: str, provider, why: str) -> list:
    """
    The global switch is on (§25): no new orders; cancel what is still open;
    under the flatten policy, close every slot position; alert the user once
    per session. Promotions are frozen in slots.py and factory_pipeline.py.
    """
    import killswitch as ks
    results = []
    broker, engine = _build(conn, cfg, mode, provider)
    for (cid, boid) in conn.execute(
            "SELECT client_order_id, broker_order_id FROM orders WHERE mode=? AND state NOT IN "
            "('FILLED','CANCELLED','REJECTED','FAILED')", (mode,)).fetchall():
        try:
            done = broker.cancel_order(boid or cid)
        except Exception as e:                               # noqa: BLE001
            done = False
            log.error(f"cancel {cid} failed: {type(e).__name__}")
        results.append({"slot": "-", "action": "CANCEL", "symbol": cid, "reason": why,
                        "status": "cancelled" if done else "cancel_failed"})
    if ks.emergency_policy(risk_engine.load_limits()) == "flatten":
        for slot, pos in open_positions(conn, mode).items():
            sig = sg.Signal(symbol=pos["symbol"], action="CLOSE", strategy=f"slot{slot}:EMERGENCY",
                            reason=f"emergency policy: {why}", quantity=float(pos["quantity"]),
                            session=engine.session)
            res = engine.execute(sig, reconciled=None)
            _record_trade(conn, mode, slot, pos, pos["symbol"], "CLOSE", res, sig.reason)
            results.append({"slot": slot, "action": "CLOSE", "symbol": pos["symbol"],
                            "reason": sig.reason, "status": res["status"], "why": res.get("reasons")})
    day = _session(conn)
    seen = conn.execute("SELECT COUNT(*) FROM system_events WHERE kind='emergency_alert' AND "
                        "substr(at,1,10)=?", (day,)).fetchone()[0]
    if not seen:
        ks.record_event(conn, "emergency_alert", why, "critical")
        try:
            import notify
            notify.notify("Stockbot2000 KILL SWITCH", f"Global kill switch engaged: {why}. "
                          f"{len([r for r in results if r['action'] == 'CLOSE'])} slot position(s) closed.")
        except Exception as e:                               # noqa: BLE001
            log.error(f"alert failed: {type(e).__name__}: {e}")
    return results


def trade(conn, cfg, mode: str, provider) -> list:
    """At the open: exits, then entries (I8)."""
    init(conn)
    import paper_trading as pt
    held = slots.current(conn, cfg)
    exits_by_slot, cands_by_slot = {}, {}
    for slot, h in held.items():
        if h is None:
            continue
        g = slots.genome_for(conn, h["strategy_key"], h["version"])
        if not g:
            continue
        cands, exits = pt._genome_signals(conn, cfg, g)
        exits_by_slot[slot], cands_by_slot[slot] = exits, (cands, g)

    results = monitor(conn, cfg, mode, provider, strategy_exits=exits_by_slot)
    import killswitch as ks
    if ks.global_engaged():
        return results                      # emergency handled in monitor(); no entries

    broker, engine = _build(conn, cfg, mode, provider)
    ok, diffs = reconcile(conn, broker, mode)
    positions = open_positions(conn, mode)
    taken = {p["symbol"] for p in positions.values()}
    for slot, h in held.items():
        if h is None or slot in positions or slot not in cands_by_slot:
            continue
        cands, g = cands_by_slot[slot]
        plan = stop_plans.from_genome(g)
        picks = [str(t) for t in cands["ticker"] if str(t) not in taken][:MAX_TRIES] if len(cands) else []
        if not picks:
            results.append({"slot": slot, "action": "NONE", "reason": "entry rule fired on nothing new",
                            "status": "no_action"})
            continue
        # A candidate the risk engine rejects (e.g. unknown market cap) or that
        # has no live quote is skipped for the strategy's NEXT candidate, rather
        # than leaving the slot empty for the session.
        for pick in picks:
            if provider.get(pick) is None:
                results.append({"slot": slot, "action": "NONE", "symbol": pick, "reason": "no live quote",
                                "status": "skipped"})
                continue
            sig = sg.Signal(symbol=pick, action="BUY", strategy=f"slot{slot}:{h['strategy_key']}",
                            reason=f"entry rule of {h['strategy_key']} v{h['version']}",
                            notional_value=float(h["capital_usd"]), session=engine.session)
            res = engine.execute(sig, reconciled=ok)
            results.append({"slot": slot, "action": "BUY", "symbol": pick, "reason": sig.reason,
                            "status": res["status"], "why": res.get("reasons")})
            if _record_trade(conn, mode, slot, h, pick, "OPEN", res, sig.reason, plan=plan,
                             atr=_atr(conn, pick)):
                taken.add(pick)
                break
            if res["status"] not in ("rejected", "duplicate"):
                break                   # halted / failed / shadow: do not keep trying
    return results


def pnl(conn, cfg, mode: str) -> dict:
    """
    The slot account's gross / costs / net (I13, B5). Realised round trips at
    their fill prices; open positions marked at the last stored close. Costs
    are MODELED (costs.CostModel) until live fills exist to measure them, and
    are labelled so.
    """
    import costs as costs_mod
    cm = costs_mod.CostModel(cfg)
    opens, gross, costs, trades = {}, 0.0, 0.0, 0
    for r in conn.execute("SELECT slot_id, symbol, action, quantity, price FROM slot_trades "
                          "WHERE mode=? ORDER BY id", (mode,)).fetchall():
        slot, sym, action, q, px = r[0], r[1], r[2], float(r[3]), float(r[4])
        if action == "OPEN":
            opens[slot] = (sym, q, px)
        elif slot in opens:
            _, q0, p0 = opens.pop(slot)
            gross += (px - p0) * q0
            costs += cm.round_trip(q0 * p0, None, q0)
            trades += 1
    unreal = 0.0
    for sym, q, p0 in opens.values():
        last = conn.execute("SELECT close FROM prices WHERE ticker=? ORDER BY date DESC LIMIT 1",
                            (sym,)).fetchone()
        if last:
            unreal += (float(last[0]) - p0) * q
            costs += cm.round_trip(q * p0, None, q)
    return {"mode": mode, "closed_trades": trades, "open_positions": len(opens),
            "gross_usd": round(gross + unreal, 2), "costs_usd": round(costs, 2),
            "net_usd": round(gross + unreal - costs, 2), "costs_basis": "modeled"}


def report(conn, cfg, mode: str = "SIMULATION") -> str:
    """Slots, today's slot trades, replacements, risk events and P&L (I13)."""
    init(conn)
    day = datetime.now(qt.NY).date().isoformat()
    lines = [f"SLOTS ({mode})"]
    for slot, h in slots.current(conn, cfg).items():
        lines.append(f"  slot {slot}: " + (f"{h['strategy_key']} v{h['version']} ${h['capital_usd']:.0f}"
                                           if h else "CASH"))
    for r in conn.execute("SELECT at, slot_id, action, strategy_key, reason FROM slot_assignments "
                          "WHERE substr(at,1,10)=? ORDER BY id", (day,)):
        lines.append(f"  {r[2]} slot {r[1]}: {r[3]} — {r[4]}")
    for r in conn.execute("SELECT slot_id, action, symbol, quantity, price, reason FROM slot_trades "
                          "WHERE mode=? AND substr(at,1,10)=? ORDER BY id", (mode, day)):
        lines.append(f"  trade slot {r[0]}: {r[1]} {r[2]} {r[3]:.4f} @ {r[4]:.2f} — {r[5]}")
    n = conn.execute("SELECT decision, COUNT(*) FROM risk_events WHERE substr(at,1,10)=? GROUP BY 1",
                     (day,)).fetchall() if conn.execute(
        "SELECT 1 FROM sqlite_master WHERE name='risk_events'").fetchone() else []
    lines.append("  risk events today: " + (", ".join(f"{d} {c}" for d, c in n) or "none"))
    p = pnl(conn, cfg, mode)
    lines.append(f"  P&L: gross {p['gross_usd']:+.2f}  costs {-p['costs_usd']:+.2f} ({p['costs_basis']})  "
                 f"net {p['net_usd']:+.2f}  closed {p['closed_trades']}  open {p['open_positions']}")
    import killswitch as ks
    g = ks.global_engaged()
    lines.append(f"  global kill switch: {'ENGAGED — ' + g if g else 'off'}")
    return "\n".join(lines)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trade the five slots through the execution engine.")
    ap.add_argument("--trade", action="store_true")
    ap.add_argument("--monitor", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--auto", action="store_true",
                    help="cron entry point: the entry pass once per session, the stop monitor after")
    ap.add_argument("--mode", default="SIMULATION", choices=slots.MODES)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    limits = risk_engine.load_limits()
    if args.mode == "LIVE" and str(limits.get("execution_mode", "SIMULATION")).upper() != "LIVE":
        print("LIVE refused: config/risk.yaml execution_mode is not LIVE (arming is the user's step, B14)")
        return 2
    if args.mode == "LIVE" and not (limits.get("robinhood") or {}).get("account_number"):
        print("LIVE refused: robinhood.account_number is not set in config/risk.yaml")
        return 2
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    init(conn)
    if args.mode == "LIVE":
        import robinhood_live
        provider = robinhood_live.RobinhoodQuotes(conn)
    else:
        provider = qt.LiveQuotes(conn)
    if (args.trade or args.monitor) and not qt.market_open():
        print("market closed — nothing trades outside the regular session (no stale fills)")
        return 0
    out = []
    if args.auto and not qt.market_open():
        print("market closed — nothing trades outside the regular session")
        return 0
    if args.auto:
        # The entry pass loads a year of the universe to evaluate rules, so it
        # runs once per session; every later poll is the cheap stop monitor.
        import killswitch as ks
        day = _session(conn)
        last = conn.execute("SELECT MAX(at) FROM system_events WHERE kind='slot_entry_pass' AND "
                            "detail=?", (f"{args.mode}:{day}",)).fetchone()[0]
        # Re-run the entry pass when the slots changed after it: slots filled at
        # 14:40 after a 13:30 pass otherwise waited until the next session
        # (found 2026-09-24).
        changed = conn.execute("SELECT MAX(at) FROM slot_assignments").fetchone()[0]
        if last and not (changed and changed > last):
            args.monitor = True
        else:
            args.trade = True
            ks.record_event(conn, "slot_entry_pass", f"{args.mode}:{day}")
        try:
            import intraday
            intraday.scan(conn)
        except Exception as e:                               # noqa: BLE001
            log.warning(f"intraday scan failed: {type(e).__name__}: {e}")
    try:
        if args.trade:
            out = trade(conn, cfg, args.mode, provider)
        elif args.monitor:
            out = monitor(conn, cfg, args.mode, provider)
    except Exception as e:                                   # noqa: BLE001
        if args.mode != "LIVE":
            raise
        # Fail closed, loudly: no trading, and the owner is told once a day
        # (an expired Robinhood sign-in, an unreadable account, a transport error).
        import killswitch as ks
        day = _session(conn)
        seen = conn.execute("SELECT COUNT(*) FROM system_events WHERE kind='live_halt' AND "
                            "substr(at,1,10)=?", (day,)).fetchone()[0]
        ks.record_event(conn, "live_halt", f"{type(e).__name__}: {e}", "critical")
        if not seen:
            try:
                import notify
                notify.notify("Stockbot2000 LIVE halted", f"{type(e).__name__}: {e}")
            except Exception:                                # noqa: BLE001
                pass
        print(f"LIVE halted: {type(e).__name__}: {e}")
        return 3
    for r in out:
        print(f"  slot {r['slot']}: {r['action']:<5} {r.get('symbol', ''):<7} {r['status']:<14} "
              f"{r['reason']}" + (f"  [{'; '.join(r['why'])}]" if r.get("why") else ""))
    if args.status or not out:
        pos = open_positions(conn, args.mode)
        broker, _ = _build(conn, cfg, args.mode, provider if args.mode == "LIVE" else qt.DatabaseQuotes(conn))
        ok, diffs = reconcile(conn, broker, args.mode)
        cash = broker.get_buying_power() if args.mode == "LIVE" else broker.cash
        print(f"  {args.mode}: {len(pos)} open slot position(s), cash ${cash:,.2f}, "
              f"reconciled {'OK' if ok else 'FAILED: ' + '; '.join(diffs)}")
        for slot, p in sorted(pos.items()):
            print(f"    slot {slot}: {p['symbol']} {p['quantity']:.6f} @ {p['price']:.2f} "
                  f"({p['strategy_key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
