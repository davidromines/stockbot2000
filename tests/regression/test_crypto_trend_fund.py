"""Regression tests for crypto_trend_fund (Stage K4)."""
import runtime  # noqa: F401

import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import crypto_data
import crypto_fund
import crypto_trend_fund

DAY = 86400
BASE = 1_600_000_000
FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def make_conn():
    conn = sqlite3.connect(":memory:")
    crypto_data.init(conn)
    crypto_fund.init(conn)
    return conn


def add_bars(conn, symbol, closes, start=BASE):
    for i, c in enumerate(closes):
        o = closes[i - 1] if i else c
        conn.execute(
            "INSERT INTO crypto_prices (symbol, open_time, interval, bar_seconds,"
            " open, high, low, close, volume, quote_volume, trades)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (symbol, start + i * DAY, "1d", DAY, o, max(o, c) * 1.01,
             min(o, c) * 0.99, c, 1000.0, 1000.0 * c, 10),
        )
    conn.execute(
        "INSERT OR REPLACE INTO crypto_listings (symbol, status, trading_disabled,"
        " first_seen, last_seen) VALUES (?,?,?,?,?)",
        (symbol, "online", 0, "2020-01-01", "2020-01-01"),
    )
    conn.commit()


def rising_then_falling(n=60):
    up = [100.0 * (1.02 ** i) for i in range(n // 2)]
    down = [up[-1] * (0.97 ** i) for i in range(1, n // 2 + 1)]
    return up + down


def main():
    genome = {"family": "trend_sma", "n": 5, "stop_atr": 3.0, "atr_n": 3, "universe": "all"}

    conn = make_conn()
    add_bars(conn, "AAA/USD", rising_then_falling())
    info = crypto_trend_fund.open_fund(conn, "f1", genome, capital=100.0,
                                       symbols=["AAA/USD"], started_ts=BASE)
    row = conn.execute(
        "SELECT interval, strategy, library_ref, symbols, status FROM crypto_fund"
        " WHERE name = 'f1'").fetchone()
    strat = json.loads(row[1])
    check("open_fund writes one row with interval 1d", row[0] == "1d", row[0])
    check("open_fund records engine crypto_trend", strat.get("engine") == "crypto_trend", strat)
    check("open_fund freezes hs in strategy json", "hs" in strat and "AAA/USD" in strat["hs"], strat)
    check("open_fund returns what it opened", info["name"] == "f1" and info["symbols"] == ["AAA/USD"], info)

    try:
        crypto_trend_fund.open_fund(conn, "f1", genome, symbols=["AAA/USD"],
                                    started_ts=BASE)
        check("opening the same name again raises SystemExit", False, "no raise")
    except SystemExit:
        check("opening the same name again raises SystemExit", True)

    # started_ts after every bar: no entry may be produced.
    late = BASE + 1000 * DAY
    crypto_trend_fund.open_fund(conn, "late", genome, symbols=["AAA/USD"],
                                started_ts=late)
    res = crypto_trend_fund.step(conn, "late")
    n_late = conn.execute(
        "SELECT COUNT(*) FROM crypto_fund_trades WHERE name = 'late'").fetchone()[0]
    check("step with started_ts after all bars records no trades",
          res["stepped"] and n_late == 0, (res, n_late))

    res = crypto_trend_fund.step(conn, "f1")
    n1 = conn.execute(
        "SELECT COUNT(*) FROM crypto_fund_trades WHERE name = 'f1'").fetchone()[0]
    check("step records at least one closed trade", n1 >= 1, n1)
    res2 = crypto_trend_fund.step(conn, "f1")
    n2 = conn.execute(
        "SELECT COUNT(*) FROM crypto_fund_trades WHERE name = 'f1'").fetchone()[0]
    check("re-running step adds no trades", n2 == n1 and res2["new_trades"] == 0,
          (n1, n2, res2))

    bad = conn.execute(
        "SELECT COUNT(*) FROM crypto_fund_trades WHERE name = 'f1' AND entry_ts < ?",
        (BASE,)).fetchone()[0]
    check("no trade has entry_ts before started_ts", bad == 0, bad)

    m = crypto_trend_fund.mark(conn, "f1", date="2020-09-13")
    eq = conn.execute(
        "SELECT equity_usd, realised_usd, unrealised_usd FROM crypto_fund_equity"
        " WHERE name = 'f1' AND date = '2020-09-13'").fetchone()
    check("mark writes equity = capital + realised + unrealised",
          abs(eq[0] - (100.0 + eq[1] + eq[2])) < 1e-9, eq)
    check("mark returns the values it wrote",
          abs(m["equity_usd"] - eq[0]) < 1e-9, (m, eq))

    conn.execute(
        "INSERT INTO crypto_fund (name, capital_usd, started_ts, interval, strategy,"
        " library_ref, symbols, status, last_step, created_at)"
        " VALUES ('grid1', 100.0, ?, '1d', ?, NULL, ?, 'open', NULL, '2020-01-01')",
        (BASE, json.dumps({"grid": {"levels": 5}}), json.dumps(["AAA/USD"])))
    conn.commit()
    ends = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE reason='end'").fetchone()[0]
    check("a position still open at the last bar is never booked as closed", ends == 0, ends)
    names = crypto_trend_fund.funds(conn)
    check("funds() lists the crypto_trend fund", "f1" in names, names)
    check("funds() excludes a fund whose strategy json lacks engine",
          "grid1" not in names, names)

    unknown = crypto_trend_fund.step(conn, "nope")
    check("step on an unknown fund reports not stepped",
          unknown["stepped"] is False, unknown)

    conn.close()
    if FAILED:
        print(f"\n{len(FAILED)} FAILED")
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
