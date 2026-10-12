"""
Real option orders for proven option strategies (Stage R7; owner 2026-09-27: "let's
get options fully up"; "if we have a proven track record I will invest $1,000").

It mirrors the option PAPER funds (options_lab.py) into the Agentic account:

    entries  a proven strategy's paper trade opened on the newest option date is
             bought for real: whole contracts, as many as `per_trade_usd` buys at
             the live ask, one limit order per leg (a straddle is two orders)
    exits    when the paper trade closes — or a leg is within
             `exit_before_expiry_days` of expiring — the contracts are sold at the
             live bid; an unfilled sell is re-priced to the new bid after 30 minutes

It places NOTHING unless every gate holds, checked on every run:

    config/risk.yaml allow_options: true          the owner's switch (off)
    the account has option_level_2 or higher      the owner applies in the app
    no kill switch engaged                        touch data/KILL_SWITCH stops it
    the strategy is PROVEN on paper               >= min_paper_trades closed, net > 0
    the options book is inside its limits         open positions, daily loss, drawdown
    broker positions match the ledger             any mismatch halts new orders

Orders follow the live stock path's rules: review first, then place with a fixed
ref_id (UUIDv5 of the ledger row), so a retry is the same Robinhood order; an order
whose outcome is unknown is never resent — it is resolved by asking Robinhood, and
new orders wait until it is. Every order is a row in option_live_orders.

    ./venv/bin/python options_live.py --status
    ./venv/bin/python options_live.py --auto            # from cron in market hours
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
import math
import sqlite3
import sys
import uuid

log = logging.getLogger("options_live")
DEFAULTS = {"capital_usd": 1000.0, "per_trade_usd": 100.0, "max_open": 10, "max_daily_loss_usd": 150.0,
            "max_drawdown_pct": 35.0, "min_paper_trades": 20, "min_paper_net_usd": 0.01,
            "exit_before_expiry_days": 1, "reprice_after_min": 30}
OPEN_STATES = ("NEW", "SUBMITTED", "PARTIALLY_FILLED", "UNKNOWN")
STATE = {"queued": "SUBMITTED", "unconfirmed": "SUBMITTED", "confirmed": "SUBMITTED", "new": "SUBMITTED",
         "pending_cancelled": "SUBMITTED", "partially_filled": "PARTIALLY_FILLED", "filled": "FILLED",
         "cancelled": "CANCELLED", "canceled": "CANCELLED", "voided": "CANCELLED", "rejected": "REJECTED",
         "failed": "REJECTED"}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **((cfg.get("options") or {}).get("live") or {})}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS option_live_orders (
            id INTEGER PRIMARY KEY AUTOINCREMENT, trade_id INTEGER NOT NULL, strategy TEXT NOT NULL,
            symbol TEXT NOT NULL, exp TEXT NOT NULL, strike REAL NOT NULL, cp TEXT NOT NULL,
            option_id TEXT, purpose TEXT NOT NULL, side TEXT NOT NULL, quantity INTEGER NOT NULL,
            limit_price REAL, ref_id TEXT NOT NULL, broker_order_id TEXT, state TEXT NOT NULL,
            filled_qty INTEGER NOT NULL DEFAULT 0, avg_price REAL, created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL, note TEXT)""")
    conn.commit()


def _now(now=None) -> str:
    return (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds")


def _find(obj, *keys):
    import robinhood_live
    return robinhood_live.find(obj, *keys)


def _rows(obj, *keys) -> list:
    import robinhood_live
    return robinhood_live.rows(obj, *keys)


def _num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def tick(price: float, up: bool) -> float:
    """A valid option price: pennies under $3, nickels from $3 (the older tick rule —
    always valid). Buys round up, sells round down, so the limit never crosses less."""
    step = 0.01 if price < 3 else 0.05
    n = price / step
    return round((math.ceil(n - 1e-9) if up else math.floor(n + 1e-9)) * step, 2)


# --- gates ------------------------------------------------------------------------
def gates(conn, cfg: dict, call, account: str) -> str | None:
    """None when real option orders are allowed right now, else the reason they are not."""
    import killswitch
    import quotes
    import risk_engine
    if not risk_engine.load_limits().get("allow_options"):
        return "options not armed: config/risk.yaml allow_options is false (owner)"
    ks = killswitch.global_engaged()
    if ks:
        return f"kill switch engaged: {ks}"
    if not quotes.market_open():
        return "market closed"
    accts = _rows(call("get_accounts", {}), "accounts", "results")
    acct = next((a for a in accts if str(a.get("account_number")) == str(account)), None)
    lvl = str((acct or {}).get("option_level") or "")
    if lvl not in ("option_level_2", "option_level_3"):
        return f"account has no options access (option_level '{lvl or 'none'}') — apply in the Robinhood app"
    return None


def proven(conn, s: dict) -> list:
    """Option strategies whose PAPER record qualifies them for real money."""
    rows = conn.execute("SELECT strategy, COUNT(*), SUM(usd) FROM option_trades WHERE mode='PAPER' AND "
                        "ret IS NOT NULL GROUP BY strategy").fetchall()
    return [r[0] for r in rows if r[1] >= s["min_paper_trades"] and (r[2] or 0) >= s["min_paper_net_usd"]]


# --- the ledger --------------------------------------------------------------------
def held(conn) -> dict:
    """{(trade_id, option_id or leg key): contracts held} from filled buys minus filled sells."""
    out = {}
    for tid, sym, exp, k, cp, oid, side, q in conn.execute(
            "SELECT trade_id, symbol, exp, strike, cp, option_id, side, filled_qty FROM option_live_orders "
            "WHERE filled_qty > 0"):
        key = (tid, sym, exp, k, cp, oid)
        out[key] = out.get(key, 0) + (q if side == "buy" else -q)
    return {k: v for k, v in out.items() if v}


def _record(conn, trade, leg, purpose, side, qty, limit, option_id, now, note=None) -> int:
    cur = conn.execute(
        "INSERT INTO option_live_orders (trade_id, strategy, symbol, exp, strike, cp, option_id, purpose, side, "
        "quantity, limit_price, ref_id, state, created_at, updated_at, note) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (trade["id"], trade["strategy"], trade["symbol"], leg["exp"], leg["strike"], leg["cp"], option_id, purpose,
         side, qty, limit, "pending", "NEW", _now(now), _now(now), note))
    rid = cur.lastrowid
    ref = str(uuid.uuid5(uuid.NAMESPACE_URL, f"stockbot2000:option:{rid}"))
    conn.execute("UPDATE option_live_orders SET ref_id=? WHERE id=?", (ref, rid))
    conn.commit()
    return rid


def _set(conn, rid, now, **kw) -> None:
    sets = ", ".join(f"{k}=?" for k in kw)
    conn.execute(f"UPDATE option_live_orders SET {sets}, updated_at=? WHERE id=?", (*kw.values(), _now(now), rid))
    conn.commit()


# --- broker calls --------------------------------------------------------------------
def option_id(call, symbol: str, leg: dict) -> str | None:
    r = call("get_option_instruments", {"chain_symbol": symbol, "expiration_dates": leg["exp"],
                                        "strike_price": f"{leg['strike']:.4f}",
                                        "type": "call" if leg["cp"] == "C" else "put"})
    inst = _rows(r, "instruments", "results", "data")
    return str(_find(inst[0], "id")) if inst else None


def quote(call, oid: str) -> tuple:
    r = call("get_option_quotes", {"instrument_ids": [oid]})
    q = _rows(r, "quotes", "results", "data")
    q = q[0] if q else r
    return _num(_find(q, "bid_price", "bid")), _num(_find(q, "ask_price", "ask"))


def submit(conn, call, account: str, rid: int, now=None) -> str:
    """Review, then place with the row's ref_id. Returns the row's new state."""
    import robinhood_mcp as rh
    o = dict(zip([d[0] for d in conn.execute("SELECT * FROM option_live_orders WHERE id=?", (rid,)).description],
                 conn.execute("SELECT * FROM option_live_orders WHERE id=?", (rid,)).fetchone()))
    args = {"account_number": account, "quantity": str(o["quantity"]), "type": "limit",
            "price": f"{o['limit_price']:.2f}", "time_in_force": "gfd",
            "legs": [{"option_id": o["option_id"], "side": o["side"], "position_effect": o["purpose"]}]}
    try:
        call("review_option_order", {**args, "chain_symbol": o["symbol"], "underlying_type": "equity"})
    except rh.RobinhoodError as e:
        _set(conn, rid, now, state="REJECTED", note=f"review: {e}")
        return "REJECTED"
    try:
        r = call("place_option_order", {**args, "ref_id": o["ref_id"]})
    except rh.RobinhoodError as e:
        _set(conn, rid, now, state="REJECTED", note=f"place: {e}")
        return "REJECTED"
    except Exception as e:                                  # noqa: BLE001 — sent or not: unknown
        _set(conn, rid, now, state="UNKNOWN", note=f"transport after submit: {type(e).__name__}: {e}")
        return "UNKNOWN"
    bid = str(_find(r, "id", "order_id") or "") or None
    st = STATE.get(str(_find(r, "state") or "").lower(), "SUBMITTED")
    _set(conn, rid, now, broker_order_id=bid, state=st if bid else "UNKNOWN")
    return st


def refresh(conn, call, account: str, now=None) -> None:
    """Bring every open ledger row up to date from Robinhood."""
    for rid, boid, created in conn.execute(
            "SELECT id, broker_order_id, created_at FROM option_live_orders WHERE state IN (%s)"
            % ",".join("?" * len(OPEN_STATES)), OPEN_STATES).fetchall():
        if not boid:
            continue                        # UNKNOWN without an id: stays blocking until resolved by hand
        recs = _rows(call("get_option_orders", {"account_number": account, "order_id": boid}), "orders", "results")
        if not recs:
            continue
        rec = recs[0]
        st = STATE.get(str(_find(rec, "state") or "").lower())
        q = _num(_find(rec, "processed_quantity", "cumulative_quantity", "filled_quantity")) or 0
        px = _num(_find(rec, "average_price", "processed_premium_per_contract"))
        _set(conn, rid, now, state=st or "SUBMITTED", filled_qty=int(q), avg_price=px)


def reconcile(conn, call, account: str) -> str | None:
    """None when broker option positions equal the ledger's holdings, else the difference."""
    ours = {}
    for (tid, sym, exp, k, cp, oid), q in held(conn).items():
        ours[oid] = ours.get(oid, 0) + q
    theirs = {}
    for p in _rows(call("get_option_positions", {"account_number": account, "nonzero": True}), "positions", "results"):
        oid = str(_find(p, "option_id") or str(_find(p, "option") or "").rstrip("/").split("/")[-1])
        q = int(_num(_find(p, "quantity")) or 0)
        if q:
            theirs[oid] = theirs.get(oid, 0) + q
    diff = {k: (ours.get(k, 0), theirs.get(k, 0)) for k in set(ours) | set(theirs) if ours.get(k, 0) != theirs.get(k, 0)}
    return None if not diff else f"ledger vs broker (ours, theirs): {diff}"


# --- one run ----------------------------------------------------------------------
def run(conn, cfg: dict, call, account: str, now=None) -> dict:
    import killswitch
    import notify
    init(conn)
    s = settings(cfg)
    now = now or dt.datetime.now(dt.timezone.utc)
    out = {"entries": 0, "exits": 0, "skipped": [], "halt": None}
    why = gates(conn, cfg, call, account)
    if why:
        out["halt"] = why
        return out
    refresh(conn, call, account, now)
    if conn.execute("SELECT COUNT(*) FROM option_live_orders WHERE state='UNKNOWN'").fetchone()[0]:
        out["halt"] = "an order's outcome is unknown — resolve it in the Robinhood app first"
    mismatch = reconcile(conn, call, account)
    if mismatch:
        out["halt"] = mismatch
        killswitch.record_event(conn, "options_reconcile_failed", mismatch, "critical")
        notify.notify("Options halted", mismatch)
        return out

    # --- exits: the paper trade closed, or expiry is near ---------------------------
    today = now.date()
    for (tid, sym, exp, k, cp, oid), q in held(conn).items():
        closed = conn.execute("SELECT closed FROM option_trades WHERE id=?", (tid,)).fetchone()
        near = (dt.date.fromisoformat(exp) - today).days <= s["exit_before_expiry_days"]
        if not ((closed and closed[0]) or near):
            continue
        pend = conn.execute("SELECT id, created_at, broker_order_id FROM option_live_orders WHERE trade_id=? AND "
                            "option_id=? AND side='sell' AND state IN ('NEW','SUBMITTED','PARTIALLY_FILLED')",
                            (tid, oid)).fetchone()
        if pend:
            age = (now - dt.datetime.fromisoformat(pend[1])).total_seconds() / 60
            if age < s["reprice_after_min"] or not pend[2]:
                continue
            try:
                call("cancel_option_order", {"account_number": account, "order_id": pend[2]})
                _set(conn, pend[0], now, state="CANCELLED", note="re-priced")
            except Exception as e:                          # noqa: BLE001
                log.warning(f"cancel {pend[2]}: {e}")
                continue
        bid, _ = quote(call, oid)
        if not bid:
            continue
        trade = {"id": tid, "strategy": conn.execute("SELECT strategy FROM option_trades WHERE id=?", (tid,)).fetchone()[0],
                 "symbol": sym}
        rid = _record(conn, trade, {"exp": exp, "strike": k, "cp": cp}, "close", "sell", q, tick(bid, up=False),
                      oid, now, "paper trade closed" if closed and closed[0] else "expiry near")
        submit(conn, call, account, rid, now)
        out["exits"] += 1

    if out["halt"]:
        return out
    # --- book limits -------------------------------------------------------------
    day = now.date().isoformat()
    realized_today = 0.0
    for tid in {r[0] for r in conn.execute("SELECT trade_id FROM option_live_orders WHERE side='sell' AND "
                                           "filled_qty > 0 AND substr(updated_at,1,10)=?", (day,))}:
        cost = conn.execute("SELECT COALESCE(SUM(filled_qty*avg_price),0) FROM option_live_orders WHERE trade_id=? "
                            "AND side='buy'", (tid,)).fetchone()[0]
        got = conn.execute("SELECT COALESCE(SUM(filled_qty*avg_price),0) FROM option_live_orders WHERE trade_id=? "
                           "AND side='sell'", (tid,)).fetchone()[0]
        realized_today += (got - cost) * 100
    if realized_today <= -s["max_daily_loss_usd"]:
        out["halt"] = f"options daily loss ${-realized_today:.2f} reached the ${s['max_daily_loss_usd']:.0f} limit"
        return out
    # Drawdown on REALIZED results: round trips whose contracts are all sold. Open
    # contracts are capital at work; their premium is bounded by per_trade_usd.
    still_held = {k[0] for k in held(conn)}
    realized_all = 0.0
    for tid in {r[0] for r in conn.execute("SELECT DISTINCT trade_id FROM option_live_orders WHERE filled_qty > 0")}:
        if tid in still_held:
            continue
        realized_all += (conn.execute("SELECT COALESCE(SUM(filled_qty*avg_price*CASE side WHEN 'sell' THEN 1 "
                                      "ELSE -1 END),0) FROM option_live_orders WHERE trade_id=?", (tid,)).fetchone()[0]
                         * 100)
    if realized_all <= -s["capital_usd"] * s["max_drawdown_pct"] / 100:
        out["halt"] = f"options book down ${-realized_all:.2f}: past the {s['max_drawdown_pct']:.0f}% drawdown limit"
        return out
    open_trades = still_held | {r[0] for r in conn.execute(
        "SELECT trade_id FROM option_live_orders WHERE side='buy' AND state IN ('NEW','SUBMITTED','PARTIALLY_FILLED')")}

    # --- entries: newest paper trades of proven strategies ---------------------------
    ok = proven(conn, s)
    if not ok:
        out["skipped"].append("no option strategy is proven on paper yet "
                              f"(needs {s['min_paper_trades']} closed paper trades and a positive total)")
        return out
    newest = conn.execute("SELECT MAX(opened) FROM option_trades WHERE mode='PAPER'").fetchone()[0]
    ph = ",".join("?" * len(ok))
    for t in conn.execute(f"SELECT id, strategy, symbol, legs FROM option_trades WHERE mode='PAPER' AND "
                          f"closed IS NULL AND opened=? AND strategy IN ({ph}) ORDER BY id", (newest, *ok)).fetchall():
        tid, strat, sym, legs = t
        if conn.execute("SELECT 1 FROM option_live_orders WHERE trade_id=?", (tid,)).fetchone():
            continue
        if len(open_trades) >= s["max_open"]:
            out["skipped"].append(f"{sym}: {s['max_open']} option positions already open")
            break
        legs = json.loads(legs)
        priced = []
        for leg in legs:
            oid = option_id(call, sym, leg)
            _, ask = quote(call, oid) if oid else (None, None)
            if not oid or not ask:
                priced = None
                break
            priced.append((leg, oid, ask))
        if not priced:
            out["skipped"].append(f"{sym}: no live quote for a leg")
            continue
        per_set = sum(tick(a, up=True) for _, _, a in priced) * 100
        qty = int(s["per_trade_usd"] // per_set) if per_set > 0 else 0
        if qty < 1:
            out["skipped"].append(f"{sym}: one contract set costs ${per_set:.2f}, over ${s['per_trade_usd']:.0f}")
            continue
        trade = {"id": tid, "strategy": strat, "symbol": sym}
        for leg, oid, ask in priced:
            rid = _record(conn, trade, leg, "open", "buy", qty, tick(ask, up=True), oid, now, "mirrors paper trade")
            submit(conn, call, account, rid, now)
        open_trades.add(tid)
        out["entries"] += 1
    return out


def status(conn) -> list:
    init(conn)
    return [dict(zip(("strategy", "symbol", "exp", "strike", "cp", "side", "qty", "limit", "state", "filled", "at"), r))
            for r in conn.execute("SELECT strategy, symbol, exp, strike, cp, side, quantity, limit_price, state, "
                                  "filled_qty, updated_at FROM option_live_orders ORDER BY id DESC LIMIT 20")]


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--auto", action="store_true")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    import risk_engine
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    init(conn)
    if a.status:
        s = settings(cfg)
        print(f"proven on paper: {proven(conn, s) or 'none yet'}")
        for r in status(conn):
            print("  ", r)
    if a.auto:
        import robinhood_mcp as rh
        account = str((risk_engine.load_limits().get("robinhood") or {}).get("account_number") or "")
        with rh.session():
            r = run(conn, cfg, rh.call, account)
        print(json.dumps(r))
    return 0


if __name__ == "__main__":
    sys.exit(main())
