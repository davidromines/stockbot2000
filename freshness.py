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

DERIVED TABLES NEED THEIR OWN CHECK
------------------------------------
Checking `prices` alone is not enough, and on 2026-09-22 that gap cost eleven
days: `daily_fundamentals` stopped being rebuilt on 2026-09-11 and nothing
noticed. Prices advanced every morning, the gate passed every morning, and both
conviction paper funds sat frozen while every conviction screen in the daily
book read eleven-day-old fundamentals. The pipeline reported success throughout
— the exact failure this module was written to end, in a table it did not watch.

The reference for a DERIVED table is the table it derives from, not the market.
`features` and `daily_fundamentals` are both built from `prices`, so each is
measured against `prices` in sessions. That keeps the rule from the staleness
bug intact: never derive a freshness reference from the thing whose freshness is
in question. `prices` is still measured against the market, never itself.
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


# Each derived table, the table it is built from, and how many sessions it may
# lag before that counts as broken. Fundamentals get more room than features:
# a filing-derived table legitimately has quiet days, while features are
# recomputed from every bar.
DERIVED = (
    ("features", "prices", 2),
    ("daily_fundamentals", "prices", 5),
)


def check_derived(conn, cfg: dict) -> list:
    """
    Is every table built from prices keeping up with prices?

    Returns one dict per table. A missing table is reported, not skipped — a
    check that silently passes when its subject is absent is not a check.
    """
    out = []
    for table, source, limit in DERIVED:
        exists = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (table,)).fetchone()
        if not exists:
            out.append({"table": table, "ok": False, "actual": None,
                        "source_latest": None, "lag_sessions": None,
                        "reason": f"{table} does not exist"})
            continue
        src = conn.execute(f"SELECT MAX(date) FROM {source}").fetchone()[0]
        act = conn.execute(f"SELECT MAX(date) FROM {table}").fetchone()[0]
        if not act or not src:
            out.append({"table": table, "ok": False, "actual": act,
                        "source_latest": src, "lag_sessions": None,
                        "reason": f"{table} is empty" if not act
                                  else f"{source} is empty"})
            continue
        lag, method = sessions_between(conn, act, src)
        ok = lag is not None and lag <= limit
        out.append({
            "table": table, "source": source, "actual": act,
            "source_latest": src, "lag_sessions": lag, "limit": limit,
            "method": method, "ok": ok,
            "reason": (f"current: {act}, {lag} session(s) behind {source}"
                       if ok else
                       f"{lag} sessions behind {source} (limit {limit}): "
                       f"holds {act}, {source} holds {src}")})
    return out


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

    if f.lag_days < 0:
        # Newer than the market is not "extra fresh". It means a partial bar
        # was stored as a close, or the reference itself is missing a session.
        # On 2026-09-23 this read OK at a lag of -2 days while 41 in-progress
        # bars sat in `prices`. Either cause makes the data untrustworthy.
        f.ok = False
        f.reason = (f"we hold {actual}, AFTER the last completed session "
                    f"{expected}: a partial bar was stored, or the reference "
                    f"is missing a session")
    elif f.lag_sessions is None:
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
    derived = check_derived(conn, cfg)
    if a.json:
        print(json.dumps({"prices": asdict(f), "derived": derived}, indent=2))
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

        print(f"\n  DERIVED TABLES (measured against the table they are built")
        print(f"  from, never against themselves)")
        print("  " + "-" * 58)
        for d in derived:
            mark = "OK   " if d["ok"] else "STALE"
            lag = "?" if d["lag_sessions"] is None else d["lag_sessions"]
            print(f"  {mark} {d['table']:<22}{str(d['actual'] or '-'):>12}"
                  f"   {lag} session(s) behind")
            if not d["ok"]:
                print(f"        {d['reason']}")
    conn.close()
    # Non-zero on stale so a pipeline stage FAILS rather than logging and
    # continuing. This is the behaviour the whole module exists for.
    #
    # Derived tables count toward that exit code. They did not until
    # 2026-09-22, and daily_fundamentals sat eleven days stale behind a gate
    # that passed every morning.
    return 0 if (f.ok and all(d["ok"] for d in derived)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
