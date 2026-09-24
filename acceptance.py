"""
The pre-LIVE acceptance checklist. docs/ROBINHOOD_AGENTIC.md phase 25;
Addendum B §B13-B14.

Twenty-six items, each one EXECUTED — never asserted from memory, never marked
PASS without running (the spec's rule). Every functional item runs against an
isolated in-memory database and injected quotes, so the checklist can run any
time without touching the forward record or the account. The global kill
switch is exercised through the TRADING_ENABLED environment switch, never the
real data/KILL_SWITCH file.

The checklist is what arming LIVE should wait on. It does not arm anything:
LIVE stays disabled here, and item 1 FAILS if it is not. The last items are
evidence items — the full test suite, and a SHADOW track record of at least
`min_shadow_sessions` — so on a fresh build the verdict is correctly
NOT READY until the shadow record exists.

    python acceptance.py              run the checklist, write data/acceptance.json
    python acceptance.py --no-suite   skip item 25 (the full test suite)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import os
import sqlite3
import subprocess
import sys
from datetime import datetime, timezone

import pandas as pd

import account_rules
import broker as bk
import execution as ex
import killswitch as ks
import paper_trading as pt
import quotes as qt
import risk_engine
import signals as sg
import slot_trader as st
import slots
import stop_plans

OUT = "data/acceptance.json"
MIN_SHADOW_SESSIONS = 10
GENOME = {"entry": {"op": "gt"}, "exit": {"op": "lt"}, "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20}}
PORT = {"equity": 100.0, "buying_power": 100.0, "unsettled_proceeds": 0.0, "day_trades_5d": 0, "daily_pnl": 0.0,
        "drawdown_percent": 0.0, "positions": {}}
QUOTE = {"price": 50.0, "dollar_volume_20": 5e7, "market_cap": 5e9}


def _fixture():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    for d in ("2026-09-22", "2026-09-23"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
    for t in ("AAA", "BBB"):
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', 2.0, 5e7)", (t,))
        c.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', 5e9)", (t,))
    st.init(c)
    return c


def _assign(c, slot, key):
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
              "reason) VALUES ('2026-09-23T00:00:00', ?, 'ASSIGN', ?, 1, 20.0, 'SIMULATION', 'acceptance')",
              (slot, key))
    c.commit()


def _sig(**kw):
    base = dict(symbol="AAA", action="BUY", strategy="acceptance", reason="acceptance",
                notional_value=20.0, session="2026-09-24")
    base.update(kw)
    return sg.Signal(**base)


def _patch():
    slots.genome_for = lambda conn, k, v: GENOME
    pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": ["AAA", "BBB"]}), set())
    import notify
    notify.notify = lambda *a, **k: []


def run(with_suite: bool = True) -> list:
    _patch()
    L = risk_engine.load_limits()
    E = risk_engine.RiskEngine(L)
    items = []

    def item(n, name, fn):
        try:
            ok, detail = fn()
            items.append({"n": n, "item": name, "result": "PASS" if ok else "FAIL", "detail": detail})
        except Exception as e:                               # noqa: BLE001 — a crash is a FAIL, stated
            items.append({"n": n, "item": name, "result": "FAIL", "detail": f"{type(e).__name__}: {e}"})

    item(1, "LIVE is disabled (execution_mode is not LIVE)",
         lambda: (str(L.get("execution_mode", "SIMULATION")).upper() != "LIVE", L.get("execution_mode")))
    item(2, "account type configured", lambda: (L.get("account_type") in ("cash", "margin", "limited_margin"), L.get("account_type")))
    item(3, "risk limits present (trade, position, daily loss, drawdown)",
         lambda: (all(L.get(k) for k in ("max_trade_dollars", "max_position_dollars", "max_daily_loss_dollars",
                                         "max_drawdown_percent")), "all set"))

    def global_switch():
        os.environ["TRADING_ENABLED"] = "false"
        try:
            v = ks.check(None, PORT, L, 0, True)
        finally:
            os.environ.pop("TRADING_ENABLED", None)
        return (not v.trading_allowed, "; ".join(v.reasons))
    item(4, "global kill switch halts trading", global_switch)
    item(5, "unreadable portfolio halts (fail closed)",
         lambda: (not ks.check(None, None, L, 0, True).trading_allowed, "portfolio None"))
    item(6, "reconciliation mismatch halts",
         lambda: (not ks.check(None, PORT, L, 0, False).trading_allowed, "reconciled=False"))

    def strategy_switch():
        c = _fixture()
        ks.init(c)
        ks.engage_strategy(c, "fx_a", "acceptance")
        return (ks.strategy_halted(c, "fx_a") == "acceptance", "engaged and read back")
    item(7, "per-strategy kill switch", strategy_switch)

    def duplicate():
        c = _fixture()
        b = bk.SimulatedBroker(cash=100.0, quotes={"AAA": QUOTE})
        eng = ex.ExecutionEngine(c, b, E, "SIMULATION", "2026-09-24")
        r1, r2 = eng.execute(_sig(), True), eng.execute(_sig(), True)
        return (r1["status"] == "filled" and r2["status"] == "duplicate", f"{r1['status']} then {r2['status']}")
    item(8, "duplicate order suppressed (idempotent)", duplicate)
    item(9, "unknown liquidity rejected", lambda: (not E.validate(_sig(), PORT, {"price": 50.0, "market_cap": 5e9}).approved,
                                                  "no dollar_volume_20"))
    item(10, "unknown market cap rejected", lambda: (not E.validate(_sig(), PORT, {"price": 50.0,
                                                                                   "dollar_volume_20": 5e7}).approved,
                                                     "no market_cap"))

    def capped():
        r = E.validate(_sig(notional_value=500.0), PORT, QUOTE)
        return (r.approved and r.sized_notional <= float(L["max_trade_dollars"]), f"sized {r.sized_notional}")
    item(11, "oversized order capped by the risk engine", capped)

    def exit_sized():
        held = {**PORT, "positions": {"AAA": {"quantity": 0.4, "value": 20.0}}}
        r = E.validate(_sig(action="CLOSE", notional_value=None), held, None)
        return (r.approved and abs(r.sized_quantity - 0.4) < 1e-9, f"sized_quantity {r.sized_quantity}")
    item(12, "exits never blocked and sized from holdings", exit_sized)

    def settled():
        r = E.validate(_sig(), {**PORT, "unsettled_proceeds": 90.0}, QUOTE)
        return (r.approved and r.sized_notional == 10.0, f"sized {r.sized_notional} of $10 settled")
    item(13, "cash account buys with settled funds only", settled)
    item(14, "stop plan mandatory (no price stop = invalid)",
         lambda: (not stop_plans.validate([{"type": "time", "max_hold_days": 5}])[0], "time-only plan refused"))
    item(15, "risk exit outranks the strategy (§17)",
         lambda: ((lambda v: (v["kind"] == "stop", v["reason"]))(stop_plans.check(
             stop_plans.from_genome(GENOME), {"entry_price": 50.0, "atr": 2.0}, 40.0, 2, strategy_exit=True))))
    item(16, "market closed -> no live quote (no stale fills)",
         lambda: ((lambda now: (not qt.market_open(now), "Saturday 12:00 UTC"))(
             datetime(2026, 9, 26, 12, 0, tzinfo=timezone.utc))))

    def trade_cycle():
        c = _fixture()
        _assign(c, 1, "fx_a")
        r = st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
        opened = 1 in st.open_positions(c, "SIMULATION")
        r2 = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 40.0}, conn=c))
        closed = 1 not in st.open_positions(c, "SIMULATION")
        return (opened and closed, f"entry {r[-1]['status'] if r else '-'}, stop exit {r2[-1]['status'] if r2 else '-'}")
    item(17, "slot trade and stop exit end to end (SIMULATION)", trade_cycle)

    def recovery():
        c = _fixture()
        _assign(c, 1, "fx_a")
        st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
        b = bk.LedgerSimulatedBroker(c, 100.0, "SIMULATION", qt.FixedQuotes({}, conn=c))
        ok, diffs = st.reconcile(c, b, "SIMULATION")
        return (ok and abs(b.cash - 80.0) < 1e-6, f"cash {b.cash:.2f}, diffs {diffs}")
    item(18, "restart recovery rebuilds the account from the ledger", recovery)

    def emergency():
        c = _fixture()
        _assign(c, 1, "fx_a")
        st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
        os.environ["TRADING_ENABLED"] = "false"
        try:
            st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0}, conn=c))
            slots.assess = lambda conn, cfg: [{"strategy_key": "x", "version": 1, "net_usd": 9, "family": "f",
                                               "eligible": True, "reasons": [], "sessions": 30}]
            frozen = not slots.plan(c, {})["assign"]
        finally:
            os.environ.pop("TRADING_ENABLED", None)
            import importlib
            importlib.reload(slots)
            _patch()
        return (not st.open_positions(c, "SIMULATION") and frozen, "flattened; promotions frozen")
    item(19, "kill switch flattens slots and freezes promotions", emergency)

    def empty_ok():
        c = _fixture()
        slots.assess = lambda conn, cfg: []
        try:
            p = slots.plan(c, {})
        finally:
            import importlib
            importlib.reload(slots)
            _patch()
        return (p["cash_slots"] == [1, 2, 3, 4, 5], "nothing eligible -> all cash")
    item(20, "empty slots stay in cash (B6)", empty_ok)

    def family():
        c = _fixture()
        rows = [{"strategy_key": k, "version": 1, "net_usd": n, "family": "mom", "eligible": True, "reasons": [],
                 "sessions": 30} for k, n in (("a", 9), ("b", 8))]
        slots.assess = lambda conn, cfg: rows
        try:
            p = slots.plan(c, {})
        finally:
            import importlib
            importlib.reload(slots)
            _patch()
        return (len(p["assign"]) == 1, f"{len(p['assign'])} assigned from one family")
    item(21, "one slot per strategy family (B7)", family)

    def shadow():
        c = _fixture()
        _assign(c, 1, "fx_a")
        r = st.trade(c, {}, "SHADOW", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
        return (any(x["status"] == "shadow" for x in r) and not st.open_positions(c, "SHADOW"), "approved, none placed")
    item(22, "SHADOW decides and places nothing", shadow)
    item(23, "LIVE refused by the slot trader without execution_mode",
         lambda: (st.main(["--status", "--mode", "LIVE"]) == 2 if str(L.get("execution_mode")).upper() != "LIVE"
                  else False, "exit code 2"))

    def transmit():
        o = bk.Order(signal_id="x", symbol="AAA", side="BUY", notional=5.0)
        o.to(bk.VALIDATING); o.to(bk.APPROVED)
        o = bk.RobinhoodBroker("0000").place_order(o)
        return (o.state == bk.UNKNOWN, f"state {o.state}: the spec is built, transmission is the operator's")
    item(24, "Robinhood adapter never transmits on its own", transmit)

    def suite():
        if not with_suite:
            return (False, "UNVERIFIED — skipped (--no-suite)")
        r = subprocess.run(["./run_tests.sh"], capture_output=True, text=True, timeout=1800)
        tail = [ln for ln in r.stdout.splitlines() if "ALL PASS" in ln or "FAILED" in ln]
        return (r.returncode == 0, tail[-1].strip() if tail else f"exit {r.returncode}")
    item(25, "full regression suite passes", suite)

    def shadow_record():
        from universe import load_config
        cfg = load_config()
        c = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
        try:
            n = c.execute("SELECT COUNT(DISTINCT session) FROM orders WHERE mode='SHADOW'").fetchone()[0]
        except sqlite3.OperationalError:
            n = 0
        return (n >= MIN_SHADOW_SESSIONS, f"{n} SHADOW sessions of {MIN_SHADOW_SESSIONS} required")
    item(26, f"SHADOW track record >= {MIN_SHADOW_SESSIONS} sessions", shadow_record)
    return items


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Pre-LIVE acceptance checklist (26 executed items).")
    ap.add_argument("--no-suite", action="store_true")
    args = ap.parse_args(argv)
    items = run(with_suite=not args.no_suite)
    passed = sum(1 for i in items if i["result"] == "PASS")
    ready = passed == len(items)
    rep = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "passed": passed, "total": len(items),
           "ready_to_arm": ready, "items": items,
           "note": "Arming LIVE remains the account owner's step even when every item passes (B14)."}
    os.makedirs("data", exist_ok=True)
    json.dump(rep, open(OUT, "w"), indent=1)
    for i in items:
        print(f"  {i['result']:<4} {i['n']:>2}. {i['item']}  — {i['detail']}")
    print(f"\n  {passed}/{len(items)} passed — {'READY TO ARM (the owner decides)' if ready else 'NOT READY TO ARM'}")
    return 0 if ready else 1


if __name__ == "__main__":
    sys.exit(main())
