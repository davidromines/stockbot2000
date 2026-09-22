"""
"What was knowable on this exact date?" Phase 9, item 24.

THE QUESTION THE SPEC DEMANDS AN ANSWER TO
--------------------------------------------
    "What financial information was publicly available as of this exact
     decision date?"  — not "what does the database know today?"

`daily_fundamentals` already answers a conservative version of that: every
filing is delayed by a blanket two calendar days, which is safe but crude. This
module answers the exact version, from the acceptance timestamp now stored on
every one of the 400,700 filings.

WHY A DATE WAS NEVER ENOUGH
----------------------------
The SEC stamps a filing's `filed` date using a 17:30 ET cutoff, not the 16:00
market close. Measured across the whole corpus:

    139,593 filings accepted between 16:00 and 16:59 -> 100% carry the SAME
            filed date
     61,067 accepted between 17:00 and 17:59 -> 88.4% carry the same filed date

So roughly 193,600 filings — 48% of the corpus — are stamped with a date on
which they were not tradeable information. A pipeline keying off `filed` alone
believes the market knew them a session early.

THE RULE, AND WHY IT IS NOT "THE NEXT DAY"
--------------------------------------------
This project fills at the next open. So the first session a filing can be acted
on is:

    accepted before the open on a trading day  -> that day's open
    accepted at any later time                 -> the next session's open

Both the 10:00 filing and the 16:30 filing therefore resolve to the next
session, because neither can be traded at an open that has already happened.
That collapses most of the distinction the timestamp provides — which is worth
stating plainly rather than implying the timestamp buys more than it does. What
it buys is the ~49,700 filings accepted before the opening bell, which are
genuinely actionable a session earlier than a blanket lag allows.

**This module does not loosen anything by default.** It reports the exact first
tradeable session; nothing is rewired to use it until a pre-registered
experiment says tightening the lag is worth testing. The existing two-day lag
stays in place, because a conservative error costs signal and an optimistic one
costs the truth of every number downstream.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pit_facts")

# US equities regular session. Held here rather than in config because these are
# facts about the exchange, not tuneable parameters.
MARKET_OPEN_HOUR = 9
MARKET_OPEN_MIN = 30


def _accepted_parts(accepted: str):
    """('YYYY-MM-DD', hour, minute) from an SEC acceptance stamp."""
    if not accepted or len(accepted) < 16:
        return None, None, None
    try:
        return accepted[:10], int(accepted[11:13]), int(accepted[14:16])
    except ValueError:
        return None, None, None


def first_tradeable_session(conn, accepted: str) -> str | None:
    """
    The first session on which a filing accepted at `accepted` can be traded.

    Uses the real session calendar from `prices` rather than weekday arithmetic,
    so holidays are handled by observation instead of assumption — the same rule
    the freshness gate learned the hard way: never infer a market fact that can
    be looked up.
    """
    day, hh, mm = _accepted_parts(accepted)
    if day is None:
        return None
    before_open = (hh, mm) < (MARKET_OPEN_HOUR, MARKET_OPEN_MIN)
    op = ">=" if before_open else ">"
    r = conn.execute(
        f"SELECT MIN(date) FROM prices WHERE ticker='SPY' AND date {op} ?",
        (day,)).fetchone()
    return r[0] if r and r[0] else None


def annotate(conn, limit: int | None = None) -> dict:
    """
    Store `first_tradeable` per filing.

    Computed once and stored because the session lookup is a query per filing;
    recomputing it inside a backtest loop would dominate the backtest.
    """
    have = {r[1] for r in conn.execute("PRAGMA table_info(sec_filings)")}
    if "first_tradeable" not in have:
        conn.execute("ALTER TABLE sec_filings ADD COLUMN first_tradeable TEXT")
        conn.commit()
        log.info("added sec_filings.first_tradeable")

    # Session calendar loaded once; a per-filing SQL lookup would be 400,700
    # queries for a list that fits comfortably in memory.
    sessions = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM prices WHERE ticker='SPY' ORDER BY date")]
    if not sessions:
        raise SystemExit("no SPY sessions — cannot resolve a trading calendar")
    import bisect

    rows = conn.execute(
        "SELECT adsh, accepted FROM sec_filings WHERE accepted IS NOT NULL"
        + (f" LIMIT {int(limit)}" if limit else "")).fetchall()
    out, unresolved = [], 0
    for r in rows:
        day, hh, mm = _accepted_parts(r["accepted"])
        if day is None:
            unresolved += 1
            continue
        before_open = (hh, mm) < (MARKET_OPEN_HOUR, MARKET_OPEN_MIN)
        i = (bisect.bisect_left(sessions, day) if before_open
             else bisect.bisect_right(sessions, day))
        out.append((sessions[i] if i < len(sessions) else None, r["adsh"]))
    conn.executemany("UPDATE sec_filings SET first_tradeable=? WHERE adsh=?", out)
    conn.commit()
    return {"annotated": len(out), "unresolved": unresolved}


def knowable(conn, as_of: str, ticker: str | None = None,
             include_superseded: bool = True) -> list:
    """
    Every filing tradeable on or before `as_of` — the spec's core question.

    `include_superseded` defaults True on purpose. A filing later amended WAS
    what the market had at the time, and excluding it would answer "what do we
    now believe about that date", which is precisely the substitution this
    subsystem exists to prevent. Set it False only to ask what was ultimately
    true, and never to drive a backtest.
    """
    q = ["SELECT adsh, ticker, cik, form, period, filed, accepted, "
         "first_tradeable, prevrpt, sic FROM sec_filings "
         "WHERE first_tradeable IS NOT NULL AND first_tradeable <= ?"]
    args = [as_of]
    if ticker:
        q.append("AND ticker = ?"); args.append(ticker)
    if not include_superseded:
        q.append("AND (prevrpt IS NULL OR prevrpt = 0)")
    q.append("ORDER BY first_tradeable DESC")
    return [dict(r) for r in conn.execute(" ".join(q), args)]


def compare_to_lag(conn, sample: int = 20000) -> dict:
    """
    How the exact rule differs from the blanket two-day lag now in use.

    Compared against the session the pipeline EFFECTIVELY uses, not against raw
    `filed + LAG_DAYS`. `fundamental_features` joins with `merge_asof(...,
    direction="backward")`, so a lagged date landing on a weekend resolves to
    the following session — and comparing against the raw date instead reported
    3,996 of 20,000 filings as look-ahead when the true figure is 2. That was
    the second false alarm of the day from a comparison that skipped a step the
    real code performs.

    The number that would matter is `current_is_optimistic`: filings the
    pipeline treats as knowable BEFORE they were tradeable.
    """
    import bisect
    import datetime as dt

    import fundamental_features as ff

    sessions = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM prices WHERE ticker='SPY' ORDER BY date")]
    if not sessions:
        raise SystemExit("no SPY sessions — cannot resolve a trading calendar")

    rows = conn.execute(
        "SELECT adsh, ticker, form, filed, accepted, first_tradeable "
        "FROM sec_filings WHERE first_tradeable IS NOT NULL AND filed IS NOT NULL "
        f"LIMIT {int(sample)}").fetchall()
    earlier = later = same = bad = 0
    offenders = []
    for r in rows:
        try:
            f = dt.date(int(r["filed"][:4]), int(r["filed"][4:6]),
                        int(r["filed"][6:8]))
        except (ValueError, TypeError):
            bad += 1
            continue
        raw = (f + dt.timedelta(days=ff.LAG_DAYS)).isoformat()
        i = bisect.bisect_left(sessions, raw)
        if i >= len(sessions):
            bad += 1
            continue
        effective, exact = sessions[i], r["first_tradeable"]
        if exact < effective:
            earlier += 1
        elif exact > effective:
            later += 1
            if len(offenders) < 5:
                offenders.append({"ticker": r["ticker"], "form": r["form"],
                                  "filed": r["filed"], "accepted": r["accepted"],
                                  "exact": exact, "pipeline": effective})
        else:
            same += 1
    return {"n": earlier + later + same, "exact_earlier": earlier,
            "exact_later": later, "same": same, "unparsed": bad,
            "current_is_optimistic": later, "offenders": offenders,
            "lag_days": ff.LAG_DAYS}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--annotate", action="store_true")
    ap.add_argument("--as-of", metavar="YYYY-MM-DD")
    ap.add_argument("--ticker")
    ap.add_argument("--compare", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.annotate:
        r = annotate(conn)
        print(f"\n  resolved a first tradeable session for {r['annotated']:,} "
              f"filings ({r['unresolved']:,} unresolved)")

    if a.compare:
        c = compare_to_lag(conn)
        print(f"\n  EXACT RULE vs THE BLANKET {c['lag_days']}-DAY LAG  "
              f"({c['n']:,} filings)")
        print("  " + "-" * 66)
        print(f"  exact is EARLIER (lag wastes signal) {c['exact_earlier']:>10,}")
        print(f"  identical                            {c['same']:>10,}")
        print(f"  exact is LATER (lag is OPTIMISTIC)   {c['exact_later']:>10,}")
        print()
        if c["current_is_optimistic"]:
            print("  These filings are treated as knowable BEFORE they were")
            print("  tradeable. Inspect each — an acceptance stamp far from its")
            print("  filed date is usually an SEC data defect, not a leak:")
            for o in c["offenders"]:
                print(f"    {o['ticker']:<8}{o['form']:<8}filed {o['filed']}  "
                      f"accepted {o['accepted'][:16]}  "
                      f"exact {o['exact']} vs pipeline {o['pipeline']}")
        else:
            print("  Nothing is treated as knowable before it was tradeable:")
            print("  the current lag is conservative everywhere it differs.")

    if a.as_of:
        rows = knowable(conn, a.as_of, a.ticker)
        print(f"\n  KNOWABLE AS OF {a.as_of}"
              + (f" — {a.ticker}" if a.ticker else "") + f"   {len(rows):,} filings")
        print("  " + "-" * 78)
        for r in rows[:15]:
            print(f"  {r['first_tradeable']}  {(r['ticker'] or '?'):<8}"
                  f"{r['form']:<9}period {r['period']}  accepted {r['accepted'][:16]}"
                  + ("  [superseded later]" if r["prevrpt"] else ""))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
