"""
Data freshness as a metric that can FAIL a run. Phase 6 section 8.

WHY THIS IS A MODULE AND NOT AN ASSERT
---------------------------------------
The previous pipeline measured freshness against `MAX(date)` in the very table
it was refreshing. That is circular, and it let the system operate a full
session behind while reporting SUCCESS every morning — 12,769 tickers sat at
2026-09-11 against a max of 2026-09-14, SPY and AAPL among them, and nothing
noticed because the check compared the table to itself.

The fix was to ask the data source for the last completed session. This module
makes that answer a recorded, thresholded, failing metric rather than a log line
someone might read.

**A run that is stale must not report success.** That is the entire point. A
pipeline that says SUCCESS while working on last week's prices is worse than one
that crashes, because the crash gets fixed.

WHAT IS MEASURED
----------------
  expected_latest_date   the newest COMPLETED session, from a liquid reference
                         ETF — never from our own tables
  actual_latest_date     the newest bar we hold
  lag_days               calendar days between them
  lag_sessions           trading sessions between them, which is the number
                         that matters over a weekend or a holiday
  missing_symbols        reference tickers with no bar on the expected date

Sessions rather than days because a Monday run against Friday's data has a lag
of three calendar days and zero sessions, and only one of those is a problem.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("freshness")


@dataclass
class Freshness:
    expected_latest_date: str | None
    actual_latest_date: str | None
    lag_days: int | None
    lag_sessions: int | None
    missing_symbols: list = field(default_factory=list)
    lag_method: str = ""
    reference_tickers: list = field(default_factory=list)
    threshold_sessions: int = 1
    ok: bool = False
    reason: str = ""
    checked_at: str = field(default_factory=lambda:
                            datetime.now(timezone.utc).isoformat(timespec="seconds"))


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS freshness_log (
            checked_at           TEXT PRIMARY KEY,
            expected_latest_date TEXT,
            actual_latest_date   TEXT,
            lag_days             INTEGER,
            lag_sessions         INTEGER,
            missing_symbols      INTEGER NOT NULL DEFAULT 0,
            ok                   INTEGER NOT NULL,
            reason               TEXT NOT NULL
        ) STRICT
    """)
    conn.commit()


def sessions_between(conn, a: str, b: str, reference: str = "SPY") -> tuple:
    """
    Trading sessions between two dates. Returns (count, how_it_was_counted).

    **The obvious implementation of this function is the bug it exists to
    detect.** Counting bars in our own `prices` table between `a` and `b` gives
    zero whenever we are behind — because being behind is precisely the state of
    having no bars in that range. The first version of this module did exactly
    that and reported "3 days / 0 sessions", which would have passed a
    one-session threshold while the database sat three days stale.

    That is the same circularity as the staleness bug in `stale_tickers`: a
    freshness measure must never be derived from the thing whose freshness is in
    question.

    So: use our own bars ONLY when they actually span the range. Otherwise fall
    back to counting weekdays, which over-counts across a holiday and is
    therefore conservative in the safe direction — it can raise a false alarm,
    never suppress a real one.
    """
    from datetime import date, timedelta
    if not a or not b or a >= b:
        return 0, "current"
    have = conn.execute(
        "SELECT COUNT(*) FROM prices WHERE ticker=? AND date>? AND date<=?",
        (reference, a, b)).fetchone()
    n_have = int(have[0]) if have else 0
    covers = conn.execute(
        "SELECT 1 FROM prices WHERE ticker=? AND date>=? LIMIT 1",
        (reference, b)).fetchone()
    if covers and n_have:
        return n_have, "counted from stored bars"
    d0 = date.fromisoformat(a); d1 = date.fromisoformat(b)
    weekdays = sum(1 for i in range((d1 - d0).days)
                   if (d0 + timedelta(days=i + 1)).weekday() < 5)
    return weekdays, "estimated from weekdays (our data does not span the gap)"


def check(conn, cfg: dict, expected: str | None = None) -> Freshness:
    """
    Compare what we hold against the last session the market actually held.

    `expected` is injectable so this can be tested without a network call and so
    a caller that already probed the source does not probe it twice.
    """
    init(conn)
    bcfg = cfg.get("backfill", {}) or {}
    refs = [t for t in (bcfg.get("reference_tickers") or ["SPY"]) if t]
    thresh = int((cfg.get("freshness", {}) or {}).get("max_lag_sessions", 1))

    if expected is None:
        import backfill
        expected = backfill.last_market_session(refs)

    actual = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]

    f = Freshness(expected_latest_date=expected, actual_latest_date=actual,
                  lag_days=None, lag_sessions=None, reference_tickers=refs,
                  threshold_sessions=thresh)

    if not expected:
        # Unknown is NOT fresh. The whole class of bug this guards against was a
        # check that could not tell "I don't know" from "everything is fine".
        f.ok = False
        f.reason = ("could not determine the last market session from "
                    f"{refs} — treating as STALE rather than assuming current")
        _store(conn, f)
        return f
    if not actual:
        f.ok = False; f.reason = "no price data at all"
        _store(conn, f); return f

    f.lag_days = (datetime.fromisoformat(expected).date()
                  - datetime.fromisoformat(actual).date()).days
    f.lag_sessions, f.lag_method = sessions_between(conn, actual, expected, refs[0])
    f.missing_symbols = [t for t in refs if not conn.execute(
        "SELECT 1 FROM prices WHERE ticker=? AND date=?", (t, expected)).fetchone()]

    if f.lag_sessions is None:
        f.ok = False; f.reason = "could not count sessions"
    elif f.lag_sessions > thresh:
        f.ok = False
        f.reason = (f"{f.lag_sessions} sessions behind (limit {thresh}): "
                    f"hold {actual}, market closed {expected}")
    elif f.missing_symbols:
        f.ok = False
        f.reason = (f"reference tickers missing the newest bar: "
                    f"{', '.join(f.missing_symbols)}")
    else:
        f.ok = True
        f.reason = f"current: {actual}, {f.lag_sessions} session(s) behind {expected}"
    _store(conn, f)
    return f


def _store(conn, f: Freshness) -> None:
    conn.execute("""INSERT OR REPLACE INTO freshness_log (checked_at,
        expected_latest_date, actual_latest_date, lag_days, lag_sessions,
        missing_symbols, ok, reason) VALUES (?,?,?,?,?,?,?,?)""",
        (f.checked_at, f.expected_latest_date, f.actual_latest_date, f.lag_days,
         f.lag_sessions, len(f.missing_symbols), 1 if f.ok else 0, f.reason))
    conn.commit()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--expected", help="override the market-session probe")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    f = check(conn, cfg, expected=a.expected)
    if a.json:
        print(json.dumps(asdict(f), indent=2))
    else:
        print(f"\n  DATA FRESHNESS  {'OK' if f.ok else 'STALE'}")
        print("  " + "-" * 58)
        print(f"  market closed    {f.expected_latest_date}")
        print(f"  we hold          {f.actual_latest_date}")
        print(f"  lag              {f.lag_days} days / {f.lag_sessions} sessions"
              f"   (limit {f.threshold_sessions})")
        print(f"  counted by       {f.lag_method}")
        if f.missing_symbols:
            print(f"  missing          {', '.join(f.missing_symbols)}")
        print(f"  {f.reason}")
    conn.close()
    # Non-zero on stale so a pipeline stage FAILS rather than logging and
    # continuing. This is the behaviour the whole module exists for.
    return 0 if f.ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
