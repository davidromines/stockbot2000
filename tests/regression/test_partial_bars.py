"""
An in-progress session must never be stored as a close.

2026-09-23: an intraday top-up stored 41 partial bars. They would have been
permanent, since a ticker whose newest bar is today never looks stale again,
so the partial close would never have been re-fetched.
"""
import inspect
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import pandas as pd  # noqa: E402

import backfill  # noqa: E402

failures = 0


def check(name, ok):
    global failures
    print(f"  {'PASS' if ok else 'FAIL'}  {name}")
    failures += 0 if ok else 1


real = backfill.session_today
backfill.session_today = lambda: "2026-09-23"
try:
    df = pd.DataFrame({"ticker": ["SPY"] * 3,
                       "date": pd.to_datetime(["2026-09-21", "2026-09-22", "2026-09-23"]),
                       "close": [1.0, 2.0, 3.0]})
    kept = list(pd.to_datetime(backfill.completed_bars(df)["date"]).dt.strftime("%Y-%m-%d"))
    check("today's in-progress bar is dropped", kept == ["2026-09-21", "2026-09-22"])
    fut = pd.DataFrame({"ticker": ["X"], "date": ["2026-09-24"], "close": [1.0]})
    check("a future-dated bar is dropped", backfill.completed_bars(fut).empty)
    old = pd.DataFrame({"ticker": ["X"], "date": ["2026-09-22"], "close": [1.0]})
    check("a completed bar is kept", len(backfill.completed_bars(old)) == 1)
finally:
    backfill.session_today = real

s = backfill.session_today()
check("session_today is an ISO date", len(s) == 10 and s[4] == "-")
check("session boundary is exchange time, not UTC",
      "America/New_York" in inspect.getsource(backfill.session_today))
check("the write path applies the guard",
      "completed_bars(" in inspect.getsource(backfill.run_backfill))
check("last_market_session uses the same boundary",
      "session_today()" in inspect.getsource(backfill.last_market_session))

sys.exit(1 if failures else 0)
