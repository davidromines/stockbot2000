"""Regression checks for live_feedback (TASK-044). In-memory DB only."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import live_feedback as lf  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


SCHEMA = """
CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INTEGER,
  strategy_key TEXT, version INTEGER, symbol TEXT, action TEXT, quantity REAL,
  price REAL, atr REAL, stop_plan TEXT, reason TEXT, signal_id TEXT);
CREATE TABLE orders (client_order_id TEXT, signal_id TEXT, created_at TEXT, session TEXT,
  symbol TEXT, side TEXT, asset_type TEXT, notional REAL, quantity REAL, state TEXT,
  broker_order_id TEXT, filled_quantity REAL, avg_fill_price REAL, mode TEXT, note TEXT);
CREATE TABLE signals (signal_id TEXT, timestamp TEXT, session TEXT, symbol TEXT,
  asset_type TEXT, action TEXT, quantity REAL, notional_value REAL, confidence REAL,
  strategy TEXT, reason TEXT);
CREATE TABLE slot_marks (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INTEGER,
  symbol TEXT, price REAL, high REAL, stop REAL, verdict TEXT);
"""


def build():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    # OPEN: mark 100 at 09:00, order created 09:00:00, filled 09:00:30 at 101.
    conn.execute("INSERT INTO slot_marks VALUES (1,'2026-09-25T09:00:00+00:00','LIVE',1,'AAA',100.0,101.0,NULL,NULL)")
    conn.execute("INSERT INTO orders VALUES ('c1','s1','2026-09-25T09:00:00+00:00','r','AAA','buy','equity',20,0.2,'filled','b1',0.2,101.0,'LIVE',NULL)")
    conn.execute("INSERT INTO slot_trades VALUES (1,'2026-09-25T09:00:30+00:00','LIVE',1,'S1',1,'AAA','OPEN',0.2,101.0,NULL,NULL,'entry','s1')")
    # CLOSE: mark 100 at 10:00, filled 99 at 10:00:10 -> expected/fill - 1 = +101.01 bps.
    conn.execute("INSERT INTO slot_marks VALUES (2,'2026-09-25T10:00:00+00:00','LIVE',1,'AAA',100.0,100.0,NULL,NULL)")
    conn.execute("INSERT INTO orders VALUES ('c2','s2','2026-09-25T10:00:00+00:00','r','AAA','sell','equity',20,0.2,'filled','b2',0.2,99.0,'LIVE',NULL)")
    conn.execute("INSERT INTO slot_trades VALUES (2,'2026-09-25T10:00:10+00:00','LIVE',1,'S1',1,'AAA','CLOSE',0.2,99.0,NULL,NULL,'target','s2')")
    # A fill with no mark at all, and no order: expected None, delay None.
    conn.execute("INSERT INTO slot_trades VALUES (3,'2026-09-25T11:00:00+00:00','LIVE',2,'S2',1,'BBB','OPEN',0.1,50.0,NULL,NULL,'entry',NULL)")
    # A second strategy round trip: OPEN 100 -> CLOSE 110.
    conn.execute("INSERT INTO slot_marks VALUES (3,'2026-09-25T12:00:00+00:00','LIVE',3,'CCC',100.0,100.0,NULL,NULL)")
    conn.execute("INSERT INTO slot_trades VALUES (4,'2026-09-25T12:00:00+00:00','LIVE',3,'S3',1,'CCC','OPEN',0.2,100.0,NULL,NULL,'entry',NULL)")
    conn.execute("INSERT INTO slot_marks VALUES (4,'2026-09-26T12:00:00+00:00','LIVE',3,'CCC',110.0,110.0,NULL,NULL)")
    conn.execute("INSERT INTO slot_trades VALUES (5,'2026-09-26T12:00:00+00:00','LIVE',3,'S3',1,'CCC','CLOSE',0.2,110.0,NULL,NULL,'stop','s9')")
    # A SHADOW row that must not appear in LIVE output.
    conn.execute("INSERT INTO slot_trades VALUES (6,'2026-09-25T13:00:00+00:00','SHADOW',1,'S1',1,'AAA','OPEN',0.2,100.0,NULL,NULL,'entry',NULL)")
    return conn


def main():
    conn = build()
    tr = lf.trades(conn, "LIVE")
    check("trades returns one row per LIVE slot_trade", len(tr) == 5, len(tr))
    by_id = {t["id"]: t for t in tr}

    check("OPEN 101 vs mark 100 -> +100.00 bps",
          abs(by_id[1]["slippage_bps"] - 100.0) < 1e-6, by_id[1]["slippage_bps"])
    check("CLOSE 99 vs mark 100 -> +101.01 bps",
          abs(by_id[2]["slippage_bps"] - 101.01010101) < 1e-4, by_id[2]["slippage_bps"])
    check("delay_s is order created_at to fill",
          abs(by_id[1]["delay_s"] - 30.0) < 1e-6, by_id[1]["delay_s"])
    check("fill with no mark has expected None",
          by_id[3]["expected"] is None and by_id[3]["slippage_bps"] is None)
    check("fill with no order has delay_s None", by_id[3]["delay_s"] is None)
    check("SHADOW rows excluded from LIVE", 6 not in by_id)

    rt = lf.round_trips(conn, "LIVE")
    check("round_trips pairs OPEN->CLOSE", len(rt) == 2, len(rt))
    s3 = [r for r in rt if r["strategy_key"] == "S3"][0]
    check("gross_return 100 -> 110 is 0.10", abs(s3["gross_return"] - 0.10) < 1e-9, s3["gross_return"])
    check("exit_reason is the CLOSE reason", s3["exit_reason"] == "stop", s3["exit_reason"])
    check("holding_days is calendar days", abs(s3["holding_days"] - 1.0) < 1e-9, s3["holding_days"])

    # Another mode's earlier order for the same signal must not set the delay, and a mark
    # older than the window (or from another mode) is not the price the decision saw.
    c2 = sqlite3.connect(":memory:")
    for t in ("CREATE TABLE slot_trades (id, at, mode, slot_id, strategy_key, version, symbol, action, quantity, "
              "price, atr, stop_plan, reason, signal_id)",
              "CREATE TABLE orders (client_order_id, signal_id, created_at, session, symbol, side, asset_type, "
              "notional, quantity, state, broker_order_id, filled_quantity, avg_fill_price, mode, note)",
              "CREATE TABLE slot_marks (id, at, mode, slot_id, symbol, price, high, stop, verdict)"):
        c2.execute(t)
    c2.execute("INSERT INTO slot_trades VALUES (1,'2026-09-25T13:34:50+00:00','LIVE',1,'K','1','ZZZ','OPEN',1,10.0,"
               "NULL,NULL,'e','sig')")
    c2.execute("INSERT INTO orders VALUES ('a','sig','2026-09-25T13:20:00+00:00','d','ZZZ','BUY','equity',20,NULL,"
               "'FILLED',NULL,1,10,'SIMULATION',NULL)")
    c2.execute("INSERT INTO orders VALUES ('b','sig','2026-09-25T13:34:46+00:00','d','ZZZ','BUY','equity',20,NULL,"
               "'FILLED',NULL,1,10,'LIVE',NULL)")
    c2.execute("INSERT INTO slot_marks VALUES (1,'2026-09-24T19:00:00+00:00','LIVE',1,'ZZZ',9.0,9.0,8.0,'HOLD')")
    c2.execute("INSERT INTO slot_marks VALUES (2,'2026-09-25T13:33:00+00:00','SHADOW',1,'ZZZ',9.5,9.5,8.0,'HOLD')")
    t2 = lf.trades(c2, "LIVE")[0]
    check("delay measured from the same mode's order", abs(t2["delay_s"] - 4.0) < 1e-6, t2["delay_s"])
    check("stale or other-mode mark is not the expected price", t2["expected"] is None, t2["expected"])

    bs = lf.by_strategy(conn, "LIVE")
    check("by_strategy covers every strategy", set(bs) == {"S1", "S2", "S3"}, sorted(bs))
    # S1 has two fills, both with marks: mean of +100.00 and +101.01.
    check("mean_slippage_bps averages only fills with an expected price",
          abs(bs["S1"]["mean_slippage_bps"] - 100.5050505) < 1e-4, bs["S1"]["mean_slippage_bps"])
    check("strategy with no marked fill has mean_slippage_bps None",
          bs["S2"]["mean_slippage_bps"] is None, bs["S2"]["mean_slippage_bps"])
    check("win_rate counts positive round trips",
          bs["S3"]["win_rate"] == 1.0 and bs["S1"]["win_rate"] == 0.0, bs["S3"]["win_rate"])
    check("exit_reasons tallies the CLOSE reason",
          bs["S3"]["exit_reasons"] == {"stop": 1}, bs["S3"]["exit_reasons"])

    text = lf.render(conn, "LIVE")
    check("render lines are at most 72 characters",
          all(len(line) <= 72 for line in text.splitlines()),
          max(len(line) for line in text.splitlines()))
    check("render names the worst slippage", "WORST SLIPPAGE" in text)

    conn.close()
    if FAILED:
        print("\n%d FAILED" % len(FAILED))
        return 1
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
