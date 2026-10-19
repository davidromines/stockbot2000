"""The nightly backup covers every irreplaceable forward record, including the Intraday Runners' (Stage AD1.4)."""
import runtime  # noqa: F401

import backup

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

T = backup.TABLES
check("the Runners' signal log, heartbeat and state are backed up",
      {"intraday_runner_signals", "intraday_heartbeat", "intraday_state"} <= set(T))
check("minute bars stay in the backup (free history ages out of the source)", "minute_bars" in T)
check("the live slot record is backed up", {"slot_assignments", "slot_trades", "slot_marks", "live_equity", "orders"} <= set(T))
check("no table is listed twice", len(T) == len(set(T)))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
