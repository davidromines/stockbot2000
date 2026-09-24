"""
End-to-end regression test for slot_trader.py (Addendum A I6, I8, I14 on
SIMULATION), through the real ExecutionEngine, RiskEngine and kill switches.

Pinned: an assigned slot buys its strategy's first candidate at a live quote;
a breached stop closes it and the sale is sized (not a zero-share fill);
the simulated account is rebuilt from the ledger after a restart and
reconciles; a released slot's position is closed; SHADOW places nothing; LIVE
is refused without the operator's execution_mode.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import broker as bk
import paper_trading as pt
import quotes as qt
import slot_trader as st
import slots

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


GENOME = {"entry": {"op": "gt"}, "exit": {"op": "lt"},
          "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20}}


def fixture():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    for d in ("2026-09-22", "2026-09-23"):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, 1,1,1,1,1,'t')", (d,))
    for t, atr in (("AAA", 2.0), ("BBB", 3.0)):
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', ?, 5e7)", (t, atr))
        c.execute("INSERT INTO fundamentals VALUES (?, '2026-01-01', 5e9)", (t,))
    st.init(c)
    return c


def assign(c, slot, key):
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, "
              "mode, reason) VALUES ('2026-09-23T00:00:00', ?, 'ASSIGN', ?, 1, 20.0, 'SIMULATION', 't')",
              (slot, key))
    c.commit()


def main():
    slots.genome_for = lambda conn, k, v: GENOME
    pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": ["AAA", "BBB"]}), set())
    cfg = {}
    c = fixture()
    assign(c, 1, "fx_test")

    r = st.trade(c, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
    buys = [x for x in r if x["action"] == "BUY"]
    check("slot 1 buys its first candidate", buys and buys[0]["symbol"] == "AAA"
          and buys[0]["status"] == "filled", r)
    pos = st.open_positions(c, "SIMULATION")
    check("OPEN recorded with $20 of shares", 1 in pos and abs(pos[1]["quantity"] - 0.4) < 1e-9, pos)
    check("stop plan and ATR stored with the entry", pos[1]["stop_plan"][0]["type"] == "atr"
          and pos[1]["atr"] == 2.0, pos.get(1))

    b = bk.LedgerSimulatedBroker(c, 100.0, "SIMULATION", qt.FixedQuotes({"AAA": 50.0}, conn=c))
    ok, diffs = st.reconcile(c, b, "SIMULATION")
    check("ledger broker reconciles with the slot log", ok and abs(b.cash - 80.0) < 1e-6, (diffs, b.cash))

    r = st.monitor(c, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 51.0}, conn=c))
    check("inside the stop: no exit", not [x for x in r if x["action"] == "CLOSE"], r)
    r = st.monitor(c, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 45.0}, conn=c))
    closes = [x for x in r if x["action"] == "CLOSE"]
    check("breached ATR stop closes the position", closes and closes[0]["status"] == "filled", r)
    check("slot is flat after the stop", 1 not in st.open_positions(c, "SIMULATION"))
    b = bk.LedgerSimulatedBroker(c, 100.0, "SIMULATION", qt.FixedQuotes({}, conn=c))
    check("exit actually sold the shares (cash 80 + 0.4 x 45)", abs(b.cash - 98.0) < 1e-6 and not b.positions,
          (b.cash, b.positions))
    p = st.pnl(c, cfg, "SIMULATION")
    check("slot P&L: gross -2.00 on the stopped trade, costs shown beside it",
          p["gross_usd"] == -2.0 and p["costs_usd"] > 0 and abs(p["net_usd"] - (p["gross_usd"] - p["costs_usd"])) < 0.011, p)

    # Reopen, then release the slot: the next pass must close the position.
    c.execute("DELETE FROM signals")   # new decisions, not duplicates of the first
    c.execute("DELETE FROM orders")
    c.execute("DELETE FROM slot_trades")
    c.commit()
    st.trade(c, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, "
              "mode, reason) VALUES ('2026-09-23T01:00:00', 1, 'RELEASE', 'fx_test', 1, NULL, "
              "'SIMULATION', 'test release')")
    c.commit()
    r = st.monitor(c, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 50.0}, conn=c))
    check("released slot's position is closed", any(x["action"] == "CLOSE" and x["status"] == "filled"
                                                    for x in r), r)

    # SHADOW: same decisions, nothing placed.
    c2 = fixture()
    assign(c2, 1, "fx_test")
    r = st.trade(c2, cfg, "SHADOW", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c2))
    check("SHADOW approves but places nothing", any(x["status"] == "shadow" for x in r)
          and not st.open_positions(c2, "SHADOW"), r)

    # No live quote: nothing trades (no stale fills).
    c3 = fixture()
    assign(c3, 1, "fx_test")
    r = st.trade(c3, cfg, "SIMULATION", qt.FixedQuotes({}, conn=c3))
    check("no quote -> no entry", not st.open_positions(c3, "SIMULATION")
          and any(x["status"] == "skipped" for x in r), r)

    check("LIVE refused without the operator's execution_mode", st.main(["--status", "--mode", "LIVE"]) == 2)
    try:
        st._build(c, cfg, "LIVE", qt.FixedQuotes({}))
        check("LIVE never runs on the simulated broker", False)
    except st.LiveNotWired:
        check("LIVE never runs on the simulated broker", True)

    # --- §25 emergency: the env switch, never the real data/KILL_SWITCH file ---
    import notify
    alerts = []
    notify.notify = lambda title, body, html=None: alerts.append(body) or []
    c4 = fixture()
    assign(c4, 1, "fx_test")
    assign(c4, 2, "fx_other")
    st.trade(c4, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c4))
    check("two slot positions open before the switch", len(st.open_positions(c4, "SIMULATION")) == 2)
    os.environ["TRADING_ENABLED"] = "false"
    try:
        r = st.trade(c4, cfg, "SIMULATION", qt.FixedQuotes({"AAA": 49.0, "BBB": 61.0}, conn=c4))
        closes = [x for x in r if x["action"] == "CLOSE" and x["status"] == "filled"]
        check("kill switch flattens every slot position", len(closes) == 2
              and not st.open_positions(c4, "SIMULATION"), r)
        check("no entry while the switch is on", not [x for x in r if x["action"] == "BUY"], r)
        check("user alerted once", len(alerts) == 1, alerts)
        st.monitor(c4, cfg, "SIMULATION", qt.FixedQuotes({}, conn=c4))
        check("alert not repeated in the same session", len(alerts) == 1, alerts)
        slots.assess = lambda conn, cfg: [{"strategy_key": "new", "version": 1, "net_usd": 50, "family": "z",
                                           "eligible": True, "reasons": [], "sessions": 30}]
        p = slots.plan(c4, cfg)
        check("promotions frozen: no slot assigned", not p["assign"], p["assign"])
        b = bk.LedgerSimulatedBroker(c4, 100.0, "SIMULATION", qt.FixedQuotes({}, conn=c4))
        ok, diffs = st.reconcile(c4, b, "SIMULATION")
        check("emergency exits reconcile with the ledger", ok and not b.positions, diffs)
    finally:
        os.environ.pop("TRADING_ENABLED", None)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
