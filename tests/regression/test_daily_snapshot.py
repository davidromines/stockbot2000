"""
daily_snapshot.py: the one-page image report (owner, 2026-10-12).

No network, no real database: an in-memory SQLite store and a fake config. The one
real correctness risk is scoping — a slot gets reassigned to a different strategy
over time, so a trade placed under the PREVIOUS occupant must never leak into the
CURRENT occupant's P&L or sparkline.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import daily_snapshot as ds
import killswitch
import slots
import slot_trader

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def db():
    c = sqlite3.connect(":memory:")
    slots.init(c)
    slot_trader.init(c)
    c.execute("CREATE TABLE live_equity (at TEXT, session TEXT, equity REAL, buying_power REAL)")
    c.execute("CREATE TABLE paper_runs (run_id TEXT, label TEXT, name TEXT, family TEXT)")

    # live_equity: two sessions, up overall, down today (exercises both colors at once)
    for at, session, eq in [
        ("2026-10-01T14:00:00+00:00", "2026-10-01", 100.0),
        ("2026-10-01T19:00:00+00:00", "2026-10-01", 103.0),
        ("2026-10-02T14:00:00+00:00", "2026-10-02", 104.0),
        ("2026-10-02T19:00:00+00:00", "2026-10-02", 101.0),
    ]:
        c.execute("INSERT INTO live_equity VALUES (?,?,?,?)", (at, session, eq, eq))

    # slot 1: reassigned mid-stream. The OLD occupant closed a trade; the NEW
    # occupant has an open position. Only the new one's numbers must show up.
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
             "reason, evidence) VALUES ('2026-09-28T10:00:00+00:00', 1, 'ASSIGN', 'fx_old_strategy', 1, "
             "20, 'LIVE', 'r', 'e')")
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
             "reason, evidence) VALUES ('2026-10-01T10:00:00+00:00', 1, 'RELEASE', 'fx_old_strategy', 1, "
             "20, 'LIVE', 'r', 'e')")
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
             "reason, evidence) VALUES ('2026-10-01T10:00:00+00:00', 1, 'ASSIGN', 'fx_new_strategy', 1, "
             "20, 'LIVE', 'r', 'e')")
    c.execute("INSERT INTO league_strategies (strategy_key, version, name, created_at, definition_hash) "
             "VALUES ('fx_new_strategy', 1, 'New Strategy Name', '2026-09-01T00:00:00+00:00', 'hash1')")

    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, "
             "price, atr, stop_plan, reason, signal_id) VALUES ('2026-09-29T14:00:00+00:00','LIVE',1,"
             "'fx_old_strategy',1,'OLD','OPEN',1.0,50.0,1,'{}','r','s1')")
    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, "
             "price, atr, stop_plan, reason, signal_id) VALUES ('2026-09-30T14:00:00+00:00','LIVE',1,"
             "'fx_old_strategy',1,'OLD','CLOSE',1.0,40.0,1,'{}','r','s2')")   # a real loss, must not leak
    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, "
             "price, atr, stop_plan, reason, signal_id) VALUES ('2026-10-01T15:00:00+00:00','LIVE',1,"
             "'fx_new_strategy',1,'NEW','OPEN',2.0,10.0,1,'{}','r','s3')")
    for at, price in [("2026-10-01T16:00:00+00:00", 10.0), ("2026-10-01T18:00:00+00:00", 11.0),
                      ("2026-10-02T18:00:00+00:00", 12.0)]:
        c.execute("INSERT INTO slot_marks (at, mode, slot_id, symbol, price, high, stop, verdict) VALUES "
                 "(?, 'LIVE', 1, 'NEW', ?, ?, 8.0, 'hold')", (at, price, price))

    # slot 3: a Lab-discovered paper fund, whose own name is a raw rule expression
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, "
             "reason, evidence) VALUES ('2026-10-01T10:00:00+00:00', 3, 'ASSIGN', 'paper:abc123', 1, 20, "
             "'LIVE', 'r', 'e')")
    c.execute("INSERT INTO paper_runs VALUES ('abc123', 'Lab abc123: ((rank(x) > 0.5))', 'lab_abc123de', "
             "'lab_search')")
    # slots 2, 4, 5 stay unassigned -> CASH

    c.commit()
    return c


def main():
    cfg = {}
    killswitch.global_engaged = lambda: None
    c = db()

    data = ds.collect(c, cfg, "LIVE")

    acct = data["account"]
    check("account P&L: 101 - 100 = +1.00", abs(acct["pnl_usd"] - 1.0) < 1e-9, acct["pnl_usd"])
    # Today is measured from the previous session's close (103), as the end-of-day report does — not from today's
    # first mark (104), which would leave the overnight move out of "today".
    check("today's P&L: 101 - 103 (previous close) = -2.00", abs(acct["today_pnl_usd"] - (-2.0)) < 1e-9,
         acct["today_pnl_usd"])
    check("dollar signs are escaped for matplotlib (no mathtext between two $)",
          ds._esc("$82.27 vs $90.26") == r"\$82.27 vs \$90.26")
    check("a value that rounds to zero prints +0.00, never -0.00", ds._money(-0.001) == "+0.00" and ds._money(-0.31) == "-0.31")
    check("days_live counts distinct sessions (2)", data["days_live"] == 2, data["days_live"])

    s1 = data["slots"][1]
    check("slot 1 resolves the NEW strategy's human name", s1["name"] == "New Strategy Name", s1["name"])
    check("slot 1 symbol is the new occupant's (NEW, not OLD)", s1["symbol"] == "NEW", s1["symbol"])
    check("slot 1 net P&L excludes the old occupant's closed trade (no -10 leak)",
         s1["net_usd"] is not None and s1["net_usd"] > 0, s1["net_usd"])
    check("slot 1 unrealized gross is correct: (12-10)*2 = +4.00", abs(s1["net_usd"] - 4.0) < 1e-9, s1["net_usd"])
    check("slot 1 sparkline starts at 0 (the entry) and has the new marks only",
         s1["spark"][0] == 0.0 and len(s1["spark"]) == 4, s1["spark"])

    s2 = data["slots"][2]
    check("slot 2 (never assigned) renders as CASH", s2.get("empty") is True, s2)

    s3 = data["slots"][3]
    check("slot 3's Lab-discovered name is humanized, not the raw rule text",
         s3["name"] == "Lab-discovered strategy (abc123de)", s3["name"])
    check("slot 3 has no open position (no trades recorded)", s3["net_usd"] is None, s3)

    render_path = "/tmp/claude_test_daily_snapshot.png"
    try:
        os.remove(render_path)
    except OSError:
        pass
    ds.render(data, render_path)
    check("render() writes a non-empty PNG", os.path.exists(render_path) and os.path.getsize(render_path) > 1000,
         os.path.getsize(render_path) if os.path.exists(render_path) else "missing")
    os.remove(render_path)

    killswitch.global_engaged = lambda: "manual halt (test)"
    footer = ds._footer_line(ds.collect(c, cfg, "LIVE"))
    check("kill switch halt leads the footer line", footer.startswith("⚠ Trading halted"), footer)
    killswitch.global_engaged = lambda: None

    sent = {"called": False}

    def _fake_send(path, caption=None):
        sent["called"] = True
        return True
    import notify
    notify.send_telegram_photo = _fake_send
    rc = ds.main(["--dry-run"])
    check("--dry-run exits 0 and never calls notify", rc == 0 and sent["called"] is False, sent)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
