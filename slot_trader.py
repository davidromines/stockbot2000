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


def _build(conn, cfg, mode: str, provider):
    s = slots.settings(cfg)
    limits = risk_engine.load_limits()
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
    return True


def _exit(conn, engine, mode, slot, pos, reason, reconciled, results):
    sig = sg.Signal(symbol=pos["symbol"], action="CLOSE", strategy=f"slot{slot}:{pos['strategy_key']}",
                    reason=reason, quantity=float(pos["quantity"]), session=engine.session)
    res = engine.execute(sig, reconciled=reconciled)
    _record_trade(conn, mode, slot, pos, pos["symbol"], "CLOSE", res, reason)
    results.append({"slot": slot, "action": "CLOSE", "symbol": pos["symbol"], "reason": reason,
                    "status": res["status"], "why": res.get("reasons")})


def monitor(conn, cfg, mode: str, provider, results=None, strategy_exits=None) -> list:
    """Stops only (I6). Risk exits outrank any strategy HOLD (§17)."""
    results = [] if results is None else results
    broker, engine = _build(conn, cfg, mode, provider)
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


def trade(conn, cfg, mode: str, provider) -> list:
    """At the open: exits, then entries (I8)."""
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

    broker, engine = _build(conn, cfg, mode, provider)
    ok, diffs = reconcile(conn, broker, mode)
    positions = open_positions(conn, mode)
    taken = {p["symbol"] for p in positions.values()}
    for slot, h in held.items():
        if h is None or slot in positions or slot not in cands_by_slot:
            continue
        cands, g = cands_by_slot[slot]
        plan = stop_plans.from_genome(g)
        pick = next((str(t) for t in cands["ticker"] if str(t) not in taken), None) if len(cands) else None
        if pick is None:
            results.append({"slot": slot, "action": "NONE", "reason": "entry rule fired on nothing new",
                            "status": "no_action"})
            continue
        if provider.get(pick) is None:
            results.append({"slot": slot, "action": "NONE", "symbol": pick, "reason": "no live quote",
                            "status": "skipped"})
            continue
        sig = sg.Signal(symbol=pick, action="BUY", strategy=f"slot{slot}:{h['strategy_key']}",
                        reason=f"entry rule of {h['strategy_key']} v{h['version']}",
                        notional_value=float(h["capital_usd"]), session=engine.session)
        res = engine.execute(sig, reconciled=ok)
        if _record_trade(conn, mode, slot, h, pick, "OPEN", res, sig.reason, plan=plan, atr=_atr(conn, pick)):
            taken.add(pick)
        results.append({"slot": slot, "action": "BUY", "symbol": pick, "reason": sig.reason,
                        "status": res["status"], "why": res.get("reasons")})
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Trade the five slots through the execution engine.")
    ap.add_argument("--trade", action="store_true")
    ap.add_argument("--monitor", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mode", default="SIMULATION", choices=slots.MODES)
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    limits = risk_engine.load_limits()
    if args.mode == "LIVE" and str(limits.get("execution_mode", "SIMULATION")).upper() != "LIVE":
        print("LIVE refused: config/risk.yaml execution_mode is not LIVE (arming is the user's step, B14)")
        return 2
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    init(conn)
    provider = qt.LiveQuotes(conn)
    if (args.trade or args.monitor) and not qt.market_open():
        print("market closed — nothing trades outside the regular session (no stale fills)")
        return 0
    out = []
    if args.trade:
        out = trade(conn, cfg, args.mode, provider)
    elif args.monitor:
        out = monitor(conn, cfg, args.mode, provider)
    for r in out:
        print(f"  slot {r['slot']}: {r['action']:<5} {r.get('symbol', ''):<7} {r['status']:<14} "
              f"{r['reason']}" + (f"  [{'; '.join(r['why'])}]" if r.get("why") else ""))
    if args.status or not out:
        pos = open_positions(conn, args.mode)
        broker, _ = _build(conn, cfg, args.mode, qt.DatabaseQuotes(conn))
        ok, diffs = reconcile(conn, broker, args.mode)
        print(f"  {args.mode}: {len(pos)} open slot position(s), cash ${broker.cash:,.2f}, "
              f"reconciled {'OK' if ok else 'FAILED: ' + '; '.join(diffs)}")
        for slot, p in sorted(pos.items()):
            print(f"    slot {slot}: {p['symbol']} {p['quantity']:.6f} @ {p['price']:.2f} "
                  f"({p['strategy_key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
