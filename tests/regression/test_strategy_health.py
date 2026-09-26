"""Regression tests for strategy_health (Stage N5)."""
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


def make_conn():
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
        CREATE TABLE factory_paper_link (
            strategy_key TEXT, version INTEGER, run_id TEXT,
            enrolled_on TEXT, PRIMARY KEY (strategy_key, version));
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


S = dict(sh.DEFAULTS)


def test_classify():
    m = {"n": 3, "roll": -0.05, "allt": -0.05, "dd": 0.0,
         "recent_60d": 3, "prior_60d": 3}
    state, reason = sh.classify(m, 0.01, 15.0, S)
    check("classify n=3 -> HEALTHY", state == "HEALTHY", state)
    check("classify n=3 reason insufficient evidence",
          "insufficient evidence" in reason, reason)

    m = {"n": 8, "roll": 0.001, "allt": 0.002, "dd": 0.0,
         "recent_60d": 8, "prior_60d": 8}
    state, reason = sh.classify(m, 0.004, 15.0, S)
    check("classify n=8 roll<bt -> WATCH", state == "WATCH", state)

    m = {"n": 12, "roll": 0.001, "allt": 0.002, "dd": 0.0,
         "recent_60d": 12, "prior_60d": 12}
    state, reason = sh.classify(m, 0.004, 15.0, S)
    check("classify n=12 roll<half bt -> DEGRADING", state == "DEGRADING", state)

    m = {"n": 25, "roll": -0.01, "allt": -0.005, "dd": 0.0,
         "recent_60d": 25, "prior_60d": 25}
    state, reason = sh.classify(m, 0.004, 15.0, S)
    check("classify n=25 both negative -> FAILED", state == "FAILED", state)

    m = {"n": 3, "roll": 0.01, "allt": 0.01, "dd": 15.0,
         "recent_60d": 3, "prior_60d": 3}
    state, reason = sh.classify(m, 0.004, 15.0, S)
    check("classify dd at limit -> FAILED regardless of n", state == "FAILED", state)

    m = {"n": 8, "roll": -0.05, "allt": -0.05, "dd": 0.0,
         "recent_60d": 8, "prior_60d": 8}
    state, reason = sh.classify(m, None, 15.0, S)
    check("classify bt None skips backtest comparisons", state == "HEALTHY", state)

    m = {"n": 45, "roll": 0.01, "allt": 0.01, "dd": 0.0,
         "recent_60d": 1, "prior_60d": 10}
    state, reason = sh.classify(m, 0.004, 15.0, S)
    check("classify frequency drop -> WATCH", state == "WATCH", state)


def test_metrics():
    conn = make_conn()
    add_trade(conn, "r1", "AAA", "2026-01-02", 0.01)
    add_trade(conn, "r1", "BBB", "2026-01-03", -0.02)
    add_trade(conn, "r1", "CCC", "2026-01-04", 0.03)
    add_equity(conn, "r1", "2026-01-01", 100.0)
    add_equity(conn, "r1", "2026-01-02", 120.0)
    add_equity(conn, "r1", "2026-01-03", 90.0)
    m = sh.metrics(conn, "r1")
    check("metrics n counts closed trades", m["n"] == 3, m["n"])
    check("metrics allt is mean per-trade net",
          abs(m["allt"] - (0.01 - 0.02 + 0.03) / 3) < 1e-12, m["allt"])
    check("metrics dd is peak-to-trough percent",
          abs(m["dd"] - 25.0) < 1e-9, m["dd"])
    roll, wr = sh._roll_metrics(conn, "r1", 2)
    check("roll uses last window trades", abs(roll - 0.005) < 1e-12, roll)
    check("win_rate_roll counts winners", abs(wr - 0.5) < 1e-12, wr)
    check("metrics recent_60d present", m["recent_60d"] == 3, m["recent_60d"])
    check("metrics prior_60d present", m["prior_60d"] == 0, m["prior_60d"])


def test_run_id_for():
    conn = make_conn()
    conn.execute("INSERT INTO factory_paper_link VALUES ('fx_abc', 2, 'run42', '2026-01-01')")
    check("run_id_for paper: key", sh.run_id_for(conn, "paper:run7", 1) == "run7")
    check("run_id_for factory key", sh.run_id_for(conn, "fx_abc", 2) == "run42")
    check("run_id_for unknown family is None", sh.run_id_for(conn, "pair:AAA/BBB", 1) is None)


def test_record_and_evaluate():
    conn = make_conn()
    sh.init(conn)
    add_trade(conn, "run7", "AAA", "2026-01-02", 0.01)
    add_trade(conn, "run7", "BBB", "2026-01-03", -0.02)
    add_equity(conn, "run7", "2026-01-01", 100.0)
    add_equity(conn, "run7", "2026-01-02", 100.0)
    cfg = {"strategy_health": {}, "leagues": {"core": {"max_drawdown_pct": 15}}}
    rows = [
        {"strategy_key": "paper:run7", "version": 1, "name": "P7",
         "league": "core", "backtest": 0.004},
        {"strategy_key": "value:xyz", "version": 1, "name": "V",
         "league": "core", "backtest": 0.004},
    ]
    results = sh.evaluate(conn, cfg, rows)
    check("evaluate returns one row per input", len(results) == 2, len(results))
    unmeasured = [r for r in results if r["strategy_key"] == "value:xyz"][0]
    check("unmeasured row is HEALTHY with not-measured reason",
          unmeasured["state"] == "HEALTHY" and "not measured" in unmeasured["reason"],
          unmeasured["reason"])
    measured = [r for r in results if r["strategy_key"] == "paper:run7"][0]
    check("measured row carries metrics", measured["metrics"]["n"] == 2,
          measured["metrics"])

    n1 = sh.record(conn, results)
    check("record writes on first sight", n1 == 2, n1)
    n2 = sh.record(conn, results)
    check("record writes nothing when unchanged", n2 == 0, n2)

    results[0]["state"] = "FAILED"
    results[0]["reason"] = "changed"
    n3 = sh.record(conn, results)
    check("record writes again when state changes", n3 == 1, n3)

    lat = sh.latest(conn)
    check("latest returns newest state per strategy",
          lat[("paper:run7", 1)][0] == "FAILED", lat.get(("paper:run7", 1)))
    check("latest keeps unmeasured strategy", ("value:xyz", 1) in lat, list(lat))


def main():
    test_classify()
    test_metrics()
    test_run_id_for()
    test_record_and_evaluate()
    if FAILED:
        print("FAILED: %d" % len(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
