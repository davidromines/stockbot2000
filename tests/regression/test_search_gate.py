"""
search_gate.py: the search runs only when ACTIVE, within its daily budget, and
never inside (or into) the daily job or market hours. Pure function; no database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import search_gate as sg

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def at(s):
    return dt.datetime.fromisoformat(s).replace(tzinfo=dt.timezone.utc)


def main():
    on = {"search": {"mode": "ACTIVE", "schedule": {"runs_per_day": 1, "run_hours": 4}}}
    check("FROZEN stops the loop", sg.decide({"search": {"mode": "FROZEN"}}, at("2026-09-26 12:00"), 0).startswith("STOP"))
    check("missing mode counts as FROZEN", sg.decide({}, at("2026-09-26 12:00"), 0).startswith("STOP"))
    check("Saturday noon: run", sg.decide(on, at("2026-09-26 12:00"), 0).startswith("RUN 50 300 3"))
    check("daily budget used: wait", sg.decide(on, at("2026-09-26 12:00"), 1).startswith("WAIT daily budget"))
    check("weekday market hours: wait", "blocked" in sg.decide(on, at("2026-09-28 15:00"), 0))
    check("weekday daily job: wait", "blocked" in sg.decide(on, at("2026-09-28 07:30"), 0))
    check("weekday evening after the close: run", sg.decide(on, at("2026-09-28 22:00"), 0).startswith("RUN"))
    r = sg.decide(on, at("2026-09-29 04:00"), 0)
    check("too close to the 06:45 daily job: wait", "would not finish" in r, r)
    r = sg.decide(on, at("2026-09-28 03:30"), 0)
    check("Monday 03:30: the 06:45 daily job is too close", "would not finish" in r, r)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
