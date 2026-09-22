"""
Every kill switch, including the ones that must fire on missing information.

The important assertions here are the negative ones: that an unreadable
portfolio halts, that a reconciliation which never ran halts, and that nothing
releases a switch automatically. A switch that only fires on a clean, known-bad
input is not a safety mechanism.

Run:  PYTHONPATH=. venv/bin/python tests/test_killswitch.py
"""
import runtime  # noqa: F401
import os
import sqlite3
import tempfile

import killswitch as ks

LIMITS = {"max_daily_loss_dollars": 15.0, "max_daily_loss_percent": 15.0,
          "max_drawdown_percent": 35.0, "max_consecutive_errors": 3}
OK = {"equity": 100.0, "daily_pnl": 0.0, "drawdown_percent": 0.0}

conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
ks.init(conn)
ks.KILL_FILE = __import__("pathlib").Path(tempfile.mktemp(suffix=".KILL"))

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}{('  — ' + detail) if detail and not cond else ''}")
    if not cond:
        fails.append(name)


# baseline: with everything healthy, trading must actually be allowed
v = ks.check(conn, OK, LIMITS, recent_errors=0, reconciled=True)
check("healthy state allows trading", v.trading_allowed, str(v.reasons))

# 1. file switch
ks.engage(conn, "test")
v = ks.check(conn, OK, LIMITS, recent_errors=0, reconciled=True)
check("KILL_SWITCH file halts trading", not v.trading_allowed)
check("file switch reported first and alone", len(v.reasons) == 1, str(v.reasons))
ks.release(conn, "test")
v = ks.check(conn, OK, LIMITS, recent_errors=0, reconciled=True)
check("release restores trading", v.trading_allowed, str(v.reasons))

# 2. env switch
os.environ["TRADING_ENABLED"] = "false"
v = ks.check(conn, OK, LIMITS, recent_errors=0, reconciled=True)
check("TRADING_ENABLED=false halts", not v.trading_allowed)
os.environ["TRADING_ENABLED"] = "true"

# 3. loss and drawdown
v = ks.check(conn, {**OK, "daily_pnl": -20.0}, LIMITS, 0, True)
check("daily dollar loss halts", not v.trading_allowed, str(v.reasons))
v = ks.check(conn, {**OK, "daily_pnl": -16.0}, LIMITS, 0, True)
check("daily percent loss halts", not v.trading_allowed, str(v.reasons))
v = ks.check(conn, {**OK, "drawdown_percent": 40.0}, LIMITS, 0, True)
check("drawdown halts", not v.trading_allowed, str(v.reasons))

# 4. error rate
v = ks.check(conn, OK, LIMITS, recent_errors=3, reconciled=True)
check("consecutive errors halt", not v.trading_allowed, str(v.reasons))

# 5. THE FAIL-CLOSED CASES — the point of the module
v = ks.check(conn, None, LIMITS, 0, True)
check("unreadable portfolio HALTS (does not pass)", not v.trading_allowed)

v = ks.check(conn, OK, LIMITS, 0, reconciled=None)
check("reconciliation never run HALTS", not v.trading_allowed,
      "None must not be treated as success")

v = ks.check(conn, OK, LIMITS, 0, reconciled=False)
check("reconciliation mismatch HALTS", not v.trading_allowed)

# 6. nothing releases a switch on its own
ks.engage(conn, "test-auto")
for _ in range(3):
    ks.check(conn, OK, LIMITS, 0, True)
check("repeated checks never auto-release", ks.KILL_FILE.exists())
ks.release(conn, "test")

# 7. events are recorded, so a halt is explicable afterwards
n = conn.execute("SELECT COUNT(*) FROM system_events").fetchone()[0]
check("kill switch activity is logged", n >= 4, f"only {n} events")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
