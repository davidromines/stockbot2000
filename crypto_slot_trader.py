"""
Crypto slots (Stage K5 / K6): a slot held by a crypto trend fund trades the
fund's current holding in the Agentic account's crypto, 24/7, from its own
hourly cron line. Inert until the owner sets `allow_crypto: true` (K7).

WHAT THE SLOT HOLDS
-------------------
The same rule as pair and value slots: the slot mirrors its fund. The fund
(crypto_trend_fund.py) is a deterministic replay of the strategy over daily
bars; whatever pair it holds open, the slot holds, and when the fund's position
closes, the slot sells. The live position therefore never trades a rule the
backtest did not — it trades the rule's own state.

    fund holds X, slot flat          -> BUY $capital of X (most recent entry first)
    slot holds X, fund no longer does -> SELL (strategy exit)
    slot holds X, price <= fund stop  -> SELL (backup to the resting stop)
    slot released / reassigned        -> SELL

THE STOP RESTS AT THE BROKER
----------------------------
Unlike dollar-based equity orders, Robinhood crypto accepts a resting
`stop_loss` order (gtc, up to 90 days). Every crypto slot position gets one at
the fund's stop immediately after the buy fills; if it cannot be placed, the
position is sold at once — no position without a price stop (Addendum A §15).
Every run also checks the price against the stop, in case the resting order is
missing, and re-places a missing one.

ISOLATION FROM THE EQUITY TRADER
--------------------------------
Orders go through the same ExecutionEngine and RiskEngine (asset_type crypto,
so `allow_crypto` and the crypto liquidity floor apply). Positions live in
`crypto_slot_trades`, not `slot_trades`, so the equity trader's reconcile never
sees them; signals carry the strategy prefix `cslot`, not `slot`, so the equity
ledger simulator never replays them.
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
import risk_engine
import signals as sg
import slots

log = logging.getLogger("crypto_slot_trader")
PREFIX = "cslot"
STOP_BUFFER = 0.02           # never buy within 2% of the fund's stop


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    ex.init(conn)
    slots.init(conn)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS crypto_slot_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            at            TEXT NOT NULL,
            mode          TEXT NOT NULL,
            slot_id       INTEGER NOT NULL,
            strategy_key  TEXT NOT NULL,
            version       INTEGER NOT NULL,
            symbol        TEXT NOT NULL,
            action        TEXT NOT NULL CHECK (action IN ('OPEN','CLOSE','STOP')),
            quantity      REAL NOT NULL,
            price         REAL,
            stop          REAL,
            stop_order_id TEXT,
            reason        TEXT NOT NULL,
            signal_id     TEXT
        )""")
    conn.commit()


def open_positions(conn, mode: str) -> dict:
    """slot_id -> open position (OPEN not yet followed by CLOSE); STOP rows update the stop."""
    out = {}
    cur = conn.execute("SELECT * FROM crypto_slot_trades WHERE mode=? ORDER BY id", (mode,))
    cols = [c[0] for c in cur.description]
    for r in cur.fetchall():
        r = dict(zip(cols, r))
        if r["action"] == "OPEN":
            out[r["slot_id"]] = r
        elif r["action"] == "STOP" and r["slot_id"] in out:
            out[r["slot_id"]] = {**out[r["slot_id"]], "stop": r["stop"], "stop_order_id": r["stop_order_id"]}
        elif r["action"] == "CLOSE":
            out.pop(r["slot_id"], None)
    return out


def _log(conn, mode, slot, holder, symbol, action, qty, price, reason, stop=None, stop_order_id=None,
         signal_id=None) -> None:
    conn.execute("INSERT INTO crypto_slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, "
                 "quantity, price, stop, stop_order_id, reason, signal_id) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                 (_now(), mode, slot, holder["strategy_key"], holder["version"], symbol, action, float(qty),
                  price, stop, stop_order_id, reason, signal_id))
    conn.commit()
    if mode == "LIVE" and action in ("OPEN", "CLOSE"):
        try:
            import notify
            notify.notify("Stockbot2000 LIVE crypto", f"slot {slot} {action} {symbol}: {float(qty):.8f}"
                          + (f" @ ${float(price):,.2f}" if price else "") + f" — {reason}")
        except Exception as e:                               # noqa: BLE001 — an alert never blocks a trade
            log.error(f"alert failed: {type(e).__name__}: {e}")


def armed(limits: dict) -> bool:
    return bool(limits.get("allow_crypto"))


def holders(conn, cfg) -> dict:
    """slot_id -> holder, for slots whose current holder is a crypto strategy."""
    return {s: h for s, h in slots.current(conn, cfg).items() if h and str(h["strategy_key"]).startswith("crypto:")}


def fund_holdings(conn, fund: str) -> list:
    """The fund's open positions, newest entry first: [{symbol, entry_ts, entry_px, stop}]."""
    out = []
    for sym, ts, st in conn.execute("SELECT symbol, entry_ts, state FROM crypto_fund_open WHERE name=? "
                                    "ORDER BY entry_ts DESC, symbol", (fund,)):
        try:
            s = json.loads(st)
        except (TypeError, ValueError):
            continue
        if s.get("stop") is not None and s.get("entry_px"):
            out.append({"symbol": sym, "entry_ts": int(ts), "entry_px": float(s["entry_px"]),
                        "stop": float(s["stop"])})
    return out


def refresh(conn, funds: list) -> None:
    """Top up daily bars for the funds' pairs and replay the funds (both idempotent)."""
    import crypto_data
    import crypto_trend_fund
    syms = set()
    for f in funds:
        r = conn.execute("SELECT symbols FROM crypto_fund WHERE name=?", (f,)).fetchone()
        syms |= set(json.loads(r[0])) if r else set()
    try:
        if syms:
            crypto_data.load(conn, sorted(syms), "1d", max_bars=10)
    except Exception as e:                                   # noqa: BLE001 — stale bars: the fund simply does not move
        log.warning(f"1d top-up failed: {type(e).__name__}: {e}")
    for f in funds:
        crypto_trend_fund.step(conn, f)


class _BarQuotes:
    """SIMULATION quotes from the newest stored bar (the live path uses Robinhood)."""

    def __init__(self, conn):
        self.conn = conn

    def get(self, symbol):
        rows = self.conn.execute("SELECT close, volume FROM crypto_prices WHERE symbol=? AND interval='1d' "
                                 "ORDER BY open_time DESC LIMIT 20", (symbol,)).fetchall()
        if not rows:
            return None
        return {"symbol": symbol, "price": float(rows[0][0]), "source": "bars",
                "dollar_volume_20": (sum(float(c) * float(v or 0) for c, v in rows) / len(rows)
                                     if len(rows) >= 5 else None)}


def build(conn, cfg, mode: str, limits: dict | None = None):
    limits = limits if limits is not None else risk_engine.load_limits()
    session = datetime.now(timezone.utc).date().isoformat()
    if mode == "LIVE":
        account = (limits.get("robinhood") or {}).get("account_number")
        if str(limits.get("execution_mode", "SIMULATION")).upper() != "LIVE" or not account:
            raise RuntimeError("LIVE needs execution_mode: LIVE and robinhood.account_number in config/risk.yaml")
        import crypto_broker
        broker = crypto_broker.CryptoBroker(conn, account)
    else:
        s = slots.settings(cfg)
        broker = bk.LedgerSimulatedBroker(conn, capital=s["count"] * s["capital_per_slot"], mode=mode,
                                          quote_provider=_BarQuotes(conn), prefix=PREFIX)
    return broker, ex.ExecutionEngine(conn, broker, risk_engine.RiskEngine(limits), mode=mode, session=session)


def _execute(engine, slot, holder, symbol, action, reason, notional=None, quantity=None, emergency=False):
    # Under the kill switch only an emergency exit passes the engine (Addendum A §25):
    # action CLOSE, strategy ending ":EMERGENCY", sized to the slot's own quantity.
    strategy = f"{PREFIX}{slot}:EMERGENCY" if emergency else f"{PREFIX}{slot}:{holder['strategy_key']}"
    sig = sg.Signal(symbol=symbol, action="CLOSE" if emergency else action, strategy=strategy,
                    asset_type="crypto", reason=reason, notional_value=notional, quantity=quantity,
                    session=engine.session)
    return engine.execute(sig, reconciled=True)


def _filled(res) -> tuple:
    o = res.get("order")
    if res.get("status") in ("filled", "partially_filled") and o and o.filled_quantity:
        return float(o.filled_quantity), (float(o.avg_fill_price) if o.avg_fill_price else None)
    return 0.0, None


def _sell(conn, broker, engine, mode, slot, holder, pos, reason, results):
    if mode == "LIVE" and pos.get("stop_order_id"):
        broker.cancel_order(pos["stop_order_id"])            # a resting stop would sell the shares twice
    res = _execute(engine, slot, holder, pos["symbol"], "SELL", reason, quantity=float(pos["quantity"]),
                   emergency=reason.startswith("emergency"))
    q, px = _filled(res)
    if q:
        _log(conn, mode, slot, holder, pos["symbol"], "CLOSE", q, px, reason, signal_id=res["signal_id"])
    results.append({"slot": slot, "action": "SELL", "symbol": pos["symbol"], "reason": reason,
                    "status": res.get("status"), "why": res.get("reasons")})


def _place_stop(conn, broker, mode, slot, holder, symbol, qty, stop) -> str | None:
    if mode != "LIVE":
        return "sim"
    r = broker.place_stop(symbol, qty, stop, f"{PREFIX}{slot}:{symbol}:{_now()}")
    oid = (r or {}).get("order_id")
    ok = oid and (r or {}).get("state") in (bk.SUBMITTED, bk.PARTIALLY_FILLED)
    return oid if ok else None


def reconcile(conn, broker, mode, positions: dict, holder_of) -> tuple:
    """Detect slot positions the broker no longer has (a resting stop filled). Others must match."""
    have = broker.get_positions()
    closed, diffs = [], []
    for slot, p in positions.items():
        held = float((have.get(p["symbol"]) or {}).get("quantity") or 0.0)
        if held + 1e-9 >= float(p["quantity"]) * 0.999:
            continue
        rec = broker.get_order(p["stop_order_id"]) if mode == "LIVE" and p.get("stop_order_id") else None
        if held <= 1e-9 and rec and rec.get("state") == bk.FILLED:
            _log(conn, mode, slot, holder_of(slot, p), p["symbol"], "CLOSE", p["quantity"],
                 rec.get("avg_fill_price"), "stop filled at the broker")
            closed.append(slot)
        else:
            diffs.append(f"slot {slot} {p['symbol']}: log {float(p['quantity']):.8f} vs account {held:.8f}")
    return closed, diffs


def run(conn, cfg, mode: str, limits: dict | None = None, broker=None, engine=None) -> list:
    init(conn)
    limits = limits if limits is not None else risk_engine.load_limits()
    results = []
    hold = holders(conn, cfg)
    positions = open_positions(conn, mode)
    if not armed(limits) and not positions:
        return [{"action": "NONE", "reason": "crypto not armed (allow_crypto: false)", "status": "no_action"}]
    import killswitch as ks
    if broker is None:
        broker, engine = build(conn, cfg, mode, limits)
    funds = sorted({h["strategy_key"].split(":", 1)[1] for h in hold.values()})
    refresh(conn, funds)

    def holder_of(slot, p):
        return hold.get(slot) or {"strategy_key": p["strategy_key"], "version": p["version"]}

    closed, diffs = reconcile(conn, broker, mode, positions, holder_of)
    for s in closed:
        positions.pop(s, None)
    if diffs:
        ks.record_event(conn, "crypto_reconcile", "; ".join(diffs), "critical")
        return results + [{"action": "HALT", "reason": "reconciliation failed", "status": "halted", "why": diffs}]

    why = ks.global_engaged()
    for slot, p in list(positions.items()):
        h = hold.get(slot)
        fund = h["strategy_key"].split(":", 1)[1] if h else None
        target = {x["symbol"]: x for x in fund_holdings(conn, fund)} if fund else {}
        q = broker.get_quote(p["symbol"])
        px = q["price"] if q else None
        reason = None
        if why:
            reason = f"emergency policy: {why}"
        elif h is None or (h["strategy_key"], h["version"]) != (p["strategy_key"], p["version"]):
            reason = "slot released or reassigned"
        elif p["symbol"] not in target:
            reason = "strategy exit: the fund closed its position"
        elif px is not None and p.get("stop") and px <= float(p["stop"]):
            reason = f"price {px:,.4f} at or below stop {float(p['stop']):,.4f}"
        if reason:
            _sell(conn, broker, engine, mode, slot, holder_of(slot, p), p, reason, results)
            positions.pop(slot, None)
        elif mode == "LIVE" and not any(o.get("order_id") == p.get("stop_order_id") for o in broker.open_stops(p["symbol"])):
            oid = _place_stop(conn, broker, mode, slot, h, p["symbol"], p["quantity"], p["stop"])
            if oid:
                _log(conn, mode, slot, h, p["symbol"], "STOP", p["quantity"], None, "stop re-placed",
                     stop=p["stop"], stop_order_id=oid)
            else:
                _sell(conn, broker, engine, mode, slot, h, p, "stop could not be re-placed", results)
                positions.pop(slot, None)
    if why or not armed(limits):
        return results

    taken = {p["symbol"] for p in positions.values()}
    for slot, h in sorted(hold.items()):
        if slot in positions:
            continue
        fund = h["strategy_key"].split(":", 1)[1]
        for t in fund_holdings(conn, fund):
            if t["symbol"] in taken:
                continue
            q = broker.get_quote(t["symbol"])
            if not q or q["price"] <= t["stop"] * (1 + STOP_BUFFER):
                results.append({"slot": slot, "action": "NONE", "symbol": t["symbol"], "status": "skipped",
                                "reason": "no quote" if not q else "price within 2% of the fund's stop"})
                continue
            res = _execute(engine, slot, h, t["symbol"], "BUY", f"fund {fund} holds {t['symbol']}",
                           notional=float(h["capital_usd"] or 20.0))
            qty, fill = _filled(res)
            results.append({"slot": slot, "action": "BUY", "symbol": t["symbol"], "status": res.get("status"),
                            "why": res.get("reasons")})
            if not qty:
                break
            _log(conn, mode, slot, h, t["symbol"], "OPEN", qty, fill, f"fund {fund} holds it",
                 stop=t["stop"], signal_id=res["signal_id"])
            oid = _place_stop(conn, broker, mode, slot, h, t["symbol"], qty, t["stop"])
            if oid:
                _log(conn, mode, slot, h, t["symbol"], "STOP", qty, None, "resting stop placed",
                     stop=t["stop"], stop_order_id=oid)
            else:
                pos = open_positions(conn, mode)[slot]
                _sell(conn, broker, engine, mode, slot, h, pos, "no resting stop could be placed", results)
            taken.add(t["symbol"])
            break
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Crypto slots (Stage K5/K6).")
    ap.add_argument("--auto", action="store_true", help="one pass: reconcile, exits, entries")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--mode", default="SIMULATION", choices=("SIMULATION", "LIVE"))
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    conn.row_factory = sqlite3.Row
    init(conn)
    if a.auto:
        for r in run(conn, cfg, a.mode):
            print(f"  slot {r.get('slot', '-')}: {r['action']:<5} {r.get('symbol', ''):<9} {r.get('status', '')}"
                  f"  {r.get('reason', '')}" + (f"  {r['why']}" if r.get("why") else ""))
    if a.status or not a.auto:
        pos = open_positions(conn, a.mode)
        print(f"  {a.mode} crypto slots: {len(pos)} open")
        for s, p in sorted(pos.items()):
            print(f"    slot {s}: {p['symbol']} {float(p['quantity']):.8f} @ {p['price']}  stop {p['stop']}"
                  f"  ({p['strategy_key']})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
