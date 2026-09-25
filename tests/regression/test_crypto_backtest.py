"""Regression tests for crypto_backtest (Stage K3)."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import crypto_backtest as cb  # noqa: E402
import crypto_data  # noqa: E402

FAILURES = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILURES.append(name)


DAY = 86400
START = 1451606400  # 2016-01-01 UTC


def _bars(conn, symbol, n, start_price, drift):
    rows = []
    price = start_price
    for i in range(n):
        o = price
        c = price * (1.0 + drift)
        h = max(o, c) * 1.01
        l = min(o, c) * 0.99
        rows.append((symbol, START + i * DAY, "1d", DAY, o, h, l, c, 1000.0, 1000.0, 10, "binance"))
        price = c
    conn.executemany(
        "INSERT OR REPLACE INTO crypto_prices "
        "(symbol, open_time, interval, bar_seconds, open, high, low, close, volume, quote_volume, trades, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows,
    )
    conn.commit()


def _conn():
    conn = sqlite3.connect(":memory:")
    crypto_data.init(conn)
    cb.init(conn)
    return conn


def main():
    gs = cb.genomes()
    check("genomes has 36 entries", len(gs) == 36, "got %d" % len(gs))
    ids = [cb.strategy_id(g) for g in gs]
    check("strategy ids unique", len(set(ids)) == 36, "got %d unique" % len(set(ids)))
    check("strategy_id stable for equal genome",
          cb.strategy_id(dict(gs[0])) == cb.strategy_id(dict(gs[0])))

    conn = _conn()
    _bars(conn, "BTC-USD", 400, 100.0, 0.004)
    _bars(conn, "ETH-USD", 300, 50.0, -0.003)

    syms = cb.symbols_1d(conn)
    check("symbols_1d sorted", syms == ["BTC-USD", "ETH-USD"], str(syms))
    bars = cb.load_bars(conn, "BTC-USD")
    check("load_bars returns arrays", bars is not None and len(bars[0]) == 400)
    check("load_bars None for unknown", cb.load_bars(conn, "NOPE-USD") is None)

    genome = {"family": "trend_sma", "n": 20, "stop_atr": 3.0, "universe": "btc_eth"}
    row = cb.run_one(conn, genome)
    check("run_one returns all columns",
          set(row) == set(cb._COLUMNS) - {"run_at"}, str(sorted(row)))
    check("run_one window_start echoed", row["window_start"] == "2016-01-01")
    check("run_one symbols json", row["symbols"] == '["BTC-USD", "ETH-USD"]', row["symbols"])
    check("run_one by_year json", isinstance(row["by_year"], str) and row["by_year"].startswith("{"))
    if row["net_per_trade"] is not None and row["gross_per_trade"] is not None:
        check("costs charged on rising series", row["net_per_trade"] < row["gross_per_trade"],
              "net=%s gross=%s" % (row["net_per_trade"], row["gross_per_trade"]))
    else:
        check("costs charged on rising series", False, "no trades produced")
    if row["net_per_trade"] is not None and row["null_per_trade"] is not None:
        check("excess = net - null",
              abs(row["excess_per_trade"] - (row["net_per_trade"] - row["null_per_trade"])) < 1e-12)
    else:
        check("excess = net - null", False, "missing net or null")

    rows = cb.run(conn, only={cb.strategy_id(genome)})
    check("run writes one row", len(rows) == 1 and conn.execute(
        "SELECT COUNT(*) FROM crypto_backtests").fetchone()[0] == 1)
    cb.run(conn, only={cb.strategy_id(genome)})
    check("re-run replaces not duplicates",
          conn.execute("SELECT COUNT(*) FROM crypto_backtests").fetchone()[0] == 1)

    stored = cb.result(conn, cb.strategy_id(genome))
    check("result returns stored row", stored is not None and stored["strategy_id"] == cb.strategy_id(genome))
    check("result None for unknown", cb.result(conn, "ctrend_deadbeef00") is None)

    # A window that starts after the data ends must produce no entries at all.
    late = cb.run_one(conn, genome, window_start="2030-01-01")
    check("window_start excludes earlier entries", late["trades"] == 0, "trades=%s" % late["trades"])

    conn.close()

    if FAILURES:
        print("\n%d FAILED" % len(FAILURES))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
