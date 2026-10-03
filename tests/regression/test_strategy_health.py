"""Regression tests for strategy_health (Stage N5) health alerts."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import strategy_health as sh  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


def make_conn(with_events=True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE paper_trades (
            run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT,
            entry_price REAL, exit_price REAL, shares REAL,
            gross_pnl_usd REAL, costs_usd REAL, net_pnl_usd REAL,
            pnl_pct REAL, exit_reason TEXT);
        CREATE TABLE paper_equity (
            run_id TEXT, date TEXT, equity_usd REAL);
    """)
    if with_events:
        conn.executescript("""
            CREATE TABLE system_events (
                id INTEGER PRIMARY KEY, at TEXT, kind TEXT,
                detail TEXT, severity TEXT);
        """)
    return conn


def add_trade(conn, run_id, ticker, exit_date, ret, entry=100.0, shares=1.0):
    net = ret * entry * shares
    conn.execute(
        "INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        (run_id, ticker, exit_date, exit_date, entry, entry * (1 + ret), shares,
         net, 0.0, net, ret * 100, "signal"))


def add_equity(conn, run_id, date, equity):
    conn.execute("INSERT INTO paper_equity VALUES (?,?,?)", (run_id, date, equity))


def failed_row():
    # 25 closed trades, all losing: n >= min_failed and both rolling and
    # all-time means negative, so classify() returns FAILED.
    return {"strategy_key": "paper:run7", "version": 1, "name": "P7",
            "league": "core", "backtest": 0.004}


def seed_failed(conn):
    for i in range(25):
        add_trade(conn, "run7", "T%02d" % i, "2026-01-%02d" % (i + 1), -0.01)
    add_equity(conn, "run7", "2026-01-01", 100.0)
    add_equity(conn, "run7", "2026-01-25", 80.0)


def events(conn):
    return conn.execute(
        "SELECT at, kind, detail, severity FROM system_events ORDER BY id").fetchall()


def test_alert_on_transition():
    conn = make_conn()
    sh.init(conn)
    seed_failed(conn)
    cfg = {"strategy_health": {}, "leagues": {"core": {"max_drawdown_pct": 15}}}
    rows = [failed_row()]

    results = sh.evaluate(conn, cfg, rows)
    check("evaluate classifies as FAILED", results[0]["state"] == "FAILED",
          results[0]["state"])

    n1 = sh.record(conn, results)
    check("first record writes one health row", n1 == 1, n1)
    ev = events(conn)
    check("HEALTHY -> FAILED writes exactly one event", len(ev) == 1, len(ev))
    if ev:
        check("event kind is health_alert", ev[0]["kind"] == "health_alert", ev[0]["kind"])
        check("event severity is critical", ev[0]["severity"] == "critical", ev[0]["severity"])
        check("event detail names key, version and state",
              "paper:run7" in ev[0]["detail"] and "v1" in ev[0]["detail"]
              and "FAILED" in ev[0]["detail"], ev[0]["detail"])
        check("event at is a UTC timestamp", str(ev[0]["at"]).endswith("Z"), ev[0]["at"])

    n2 = sh.record(conn, results)
    check("second record writes no health row", n2 == 0, n2)
    check("second run writes no additional event", len(events(conn)) == 1,
          len(events(conn)))
    conn.close()


def test_degrading_severity():
    conn = make_conn()
    sh.init(conn)
    # 12 trades at +0.1% against a 0.4% backtest: below half the backtest,
    # so DEGRADING, and drawdown stays under the watch threshold.
    for i in range(12):
        add_trade(conn, "run8", "T%02d" % i, "2026-02-%02d" % (i + 1), 0.001)
    add_equity(conn, "run8", "2026-02-01", 100.0)
    add_equity(conn, "run8", "2026-02-12", 100.0)
    cfg = {"strategy_health": {}, "leagues": {"core": {"max_drawdown_pct": 15}}}
    rows = [{"strategy_key": "paper:run8", "version": 1, "name": "P8",
             "league": "core", "backtest": 0.004}]
    results = sh.evaluate(conn, cfg, rows)
    check("evaluate classifies as DEGRADING", results[0]["state"] == "DEGRADING",
          results[0]["state"])
    sh.record(conn, results)
    ev = events(conn)
    check("DEGRADING writes one event", len(ev) == 1, len(ev))
    if ev:
        check("DEGRADING severity is warning", ev[0]["severity"] == "warning",
              ev[0]["severity"])
    conn.close()


def test_missing_system_events_is_silent():
    conn = make_conn(with_events=False)
    sh.init(conn)
    seed_failed(conn)
    cfg = {"strategy_health": {}, "leagues": {"core": {"max_drawdown_pct": 15}}}
    results = sh.evaluate(conn, cfg, [failed_row()])
    n = sh.record(conn, results)
    check("record still writes health row without system_events", n == 1, n)
    conn.close()


def main():
    test_alert_on_transition()
    test_degrading_severity()
    test_missing_system_events_is_silent()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
