"""Regression test for eod_report.py (TASK-037).

Plain script, no pytest. Builds a minimal in-memory database with only the
tables the report needs, then checks the numbers the acceptance criteria name.
"""

import runtime  # noqa: F401

import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import eod_report  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


DAY = "2026-09-26"
PREV = "2026-09-25"


def make_db(with_system_events=True):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(
        """
        CREATE TABLE live_equity (at TEXT, session TEXT, equity REAL, buying_power REAL);
        CREATE TABLE trader_runs (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, pass INTEGER,
            outcome TEXT, actions TEXT, positions TEXT, reconciled INTEGER, diffs TEXT,
            cash REAL, equity REAL, unsettled REAL, error TEXT);
        CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INTEGER,
            strategy_key TEXT, version INTEGER, symbol TEXT, action TEXT, quantity REAL,
            price REAL, atr REAL, stop_plan TEXT, reason TEXT, signal_id TEXT);
        CREATE TABLE slot_marks (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INTEGER,
            symbol TEXT, price REAL, high REAL, stop REAL, verdict TEXT);
        CREATE TABLE slot_assignments (id INTEGER PRIMARY KEY, at TEXT, slot_id INTEGER,
            action TEXT, strategy_key TEXT, version INTEGER, capital_usd REAL, mode TEXT,
            reason TEXT, evidence TEXT);
        CREATE TABLE risk_events (id INTEGER PRIMARY KEY, at TEXT, signal_id TEXT, symbol TEXT,
            decision TEXT, reasons TEXT);
        CREATE TABLE league_state (id INTEGER PRIMARY KEY, strategy_key TEXT, version INTEGER,
            at TEXT, from_state TEXT, to_state TEXT, reason TEXT, actor TEXT);
        CREATE TABLE strategy_decisions (id INTEGER PRIMARY KEY, at TEXT, strategy_key TEXT,
            version INTEGER, decision TEXT, from_state TEXT, to_state TEXT, classification TEXT,
            reason TEXT, evidence TEXT);
        """
    )
    if with_system_events:
        conn.execute(
            "CREATE TABLE system_events (id INTEGER PRIMARY KEY, at TEXT, kind TEXT, "
            "detail TEXT, severity TEXT)"
        )

    conn.execute("INSERT INTO live_equity VALUES (?,?,?,?)", (PREV + "T20:00:00", PREV, 90.0, 10.0))
    conn.execute("INSERT INTO live_equity VALUES (?,?,?,?)", (DAY + "T20:00:00", DAY, 92.0, 12.0))
    conn.execute(
        "INSERT INTO trader_runs VALUES (1,?,?,1,'ok','','',1,'',5.0,92.0,0.0,NULL)",
        (DAY + "T20:00:00", "LIVE"),
    )
    # Yesterday's open, today's close: (44 - 40) * 0.5 = 2.00 gross.
    conn.execute(
        "INSERT INTO slot_trades VALUES (1,?,?,1,'k1',1,'AAA','OPEN',0.5,40.0,NULL,NULL,'entry',NULL)",
        (PREV + "T15:00:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO slot_trades VALUES (2,?,?,1,'k1',1,'AAA','CLOSE',0.5,44.0,NULL,NULL,'exit',NULL)",
        (DAY + "T15:00:00", "LIVE"),
    )
    # Today's open in slot 2, marked at 11: (11 - 10) * 1.0 = 1.00, +10.00%.
    conn.execute(
        "INSERT INTO slot_trades VALUES (3,?,?,2,'k2',1,'BBB','OPEN',1.0,10.0,NULL,NULL,'entry',NULL)",
        (DAY + "T15:05:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO slot_marks VALUES (1,?,?,2,'BBB',11.0,11.2,9.0,'HOLD')",
        (DAY + "T19:00:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO slot_assignments VALUES (1,?,1,'ASSIGN','k1',1,20.0,?,'seed',NULL)",
        (PREV + "T14:00:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO slot_assignments VALUES (2,?,2,'ASSIGN','k2',1,20.0,?,'seed',NULL)",
        (PREV + "T14:00:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO slot_assignments VALUES (3,?,3,'ASSIGN','k3',1,20.0,?,'seed',NULL)",
        (PREV + "T14:00:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO slot_assignments VALUES (4,?,3,'RELEASE','k3',1,20.0,?,'stop',NULL)",
        (DAY + "T14:00:00", "LIVE"),
    )
    conn.execute(
        "INSERT INTO risk_events VALUES (1,?,NULL,'CCC','REJECTED','too volatile')",
        (DAY + "T16:00:00",),
    )
    conn.execute(
        "INSERT INTO strategy_decisions VALUES (1,?, 'k1',1,'PROMOTE','PAPER','LIVE','ok','x',NULL)",
        (DAY + "T17:00:00",),
    )
    conn.execute(
        "INSERT INTO league_state VALUES (1,'k9',1,?,'BACKTEST','PAPER','passed','system')",
        (DAY + "T18:00:00",),
    )
    if with_system_events:
        conn.execute(
            "INSERT INTO system_events VALUES (1,?,'feed','stale feed','warning')",
            (DAY + "T18:30:00",),
        )
    conn.commit()
    return conn


def rank_fn(conn):
    return [
        {
            "name": "Alpha",
            "strategy_key": "k1",
            "score": 1.5,
            "backtest": 0.1,
            "forward": 0.05,
            "forward_trades": 12,
            "passes_gate": True,
            "gate": "ok",
        },
        {
            "name": "Beta",
            "strategy_key": "k2",
            "score": 1.0,
            "backtest": 0.08,
            "forward": 0.02,
            "forward_trades": 8,
            "passes_gate": False,
            "gate": "thin",
        },
    ]


def main():
    conn = make_db()
    now = datetime(2026, 9, 26, 20, 5, tzinfo=timezone.utc)
    report = eod_report.build(conn, DAY, "LIVE", rank_fn=rank_fn, now=now)

    check("realized gross is 2.00", report["pnl"]["realized_gross"] == 2.0, report["pnl"])
    check("one closed trade", report["pnl"]["closed_trades"] == 1, report["pnl"])
    check("net equity change is 2.00", report["pnl"]["net_equity_change"] == 2.0, report["pnl"])
    check("unrealized gross is 1.00", report["pnl"]["unrealized_gross"] == 1.0, report["pnl"])

    pos = report["positions"]
    check("one open position", len(pos) == 1, pos)
    check("unrealized pct is 10.00", pos and pos[0]["unrealized_pct"] == 10.0, pos)
    check("mark is 11.00", pos and pos[0]["mark"] == 11.0, pos)

    check("one failure", report["failures"]["n_risk_rejections"] == 1, report["failures"])
    check("slot 3 is empty", "slot 3 is empty" in report["next_actions"], report["next_actions"])
    check("slots 4 and 5 empty", "slot 4 is empty" in report["next_actions"] and "slot 5 is empty" in report["next_actions"], report["next_actions"])
    check("strategy performance has 2 slots", len(report["strategy_performance"]) == 2, report["strategy_performance"])
    check("ranking capped at 10", len(report["ranking"]) == 2, report["ranking"])

    text = eod_report.render(report)
    # Owner, 2026-09-28: the five slots first; research sections (ranking, research, new
    # candidates, paper books) are not in the message.
    order = [
        "FIVE SLOTS",
        "ACCOUNT",
        "P&L",
        "TRADES",
        "POSITIONS",
        "REPLACEMENTS",
        "FAILURES",
        "SYSTEM HEALTH",
        "NEXT ACTIONS",
    ]
    positions = [text.find("== %s ==" % h) for h in order]
    check("all headings present", all(p >= 0 for p in positions), positions)
    check("research sections left out", all(text.find("== %s ==" % h) < 0 for h in
                                             ("RANKING", "RESEARCH", "NEW CANDIDATES", "STRATEGY PERFORMANCE")))
    sl = report["slots"]
    check("five slot rows", len(sl) == 5, sl)
    held = [r for r in sl if r["symbol"]]
    check("open slot shows current return against its fill",
          len(held) == 1 and held[0]["current_pct"] == 10.0 and held[0]["current_usd"] is not None, held)
    check("slot shows its strategy's predicted score", any(r["predicted"] == 1.5 for r in sl), sl)
    check("headings in order", positions == sorted(positions), positions)
    check("no line over 60 chars", all(len(line) <= 60 for line in text.splitlines()), max(len(l) for l in text.splitlines()))

    conn2 = make_db(with_system_events=False)
    try:
        report2 = eod_report.build(conn2, DAY, "LIVE", rank_fn=rank_fn, now=now)
        check("missing system_events does not raise", report2["failures"]["system_events"] == [], report2["failures"])
    except Exception as exc:
        check("missing system_events does not raise", False, repr(exc))

    if FAILED:
        print("FAILED: %d" % len(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
