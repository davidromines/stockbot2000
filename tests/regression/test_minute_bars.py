"""Regression tests for Stage Q3 minute bar collection (no network, no real DB)."""

import runtime  # noqa: F401

import os
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import minute_bars as mb  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


def frame(day="2026-09-25", tickers=("AAA", "BBB"), closes=None):
    """Synthetic yfinance-shaped frame: UTC index, (ticker, field) columns."""
    stamps = pd.date_range("%s 13:25" % day, periods=40, freq="1min", tz="UTC")
    cols = pd.MultiIndex.from_product([list(tickers), list(mb.FIELDS)])
    data = {}
    for tk in tickers:
        for field in mb.FIELDS:
            if field == "Close":
                data[(tk, field)] = [100.0 + i * 0.1 for i in range(len(stamps))]
            elif field == "Volume":
                data[(tk, field)] = [1000.0] * len(stamps)
            else:
                data[(tk, field)] = [100.0] * len(stamps)
    df = pd.DataFrame(data, index=stamps, columns=cols)
    if closes:
        for (tk, field), value in closes.items():
            df.loc[df.index[20], (tk, field)] = value
    return df


NOW = datetime(2026, 9, 25, 20, 0, tzinfo=timezone.utc)  # 16:00 ET


def test_normalize():
    df = frame()
    out = mb.normalize(df, now=NOW)
    times = set(out["ts"].str[-5:])
    check("normalize keeps 09:30", "09:30" in times)
    check("normalize drops 16:00", "16:00" not in times)
    check("normalize drops pre-market", all(t >= "09:30" for t in times))
    check("normalize ts is New York", out["ts"].iloc[0].startswith("2026-09-25 09:30"),
          out["ts"].iloc[0])
    check("normalize covers both tickers", set(out["ticker"]) == {"AAA", "BBB"})

    # 15:59 ET bar is still open at 15:59:30 ET.
    partial = mb.normalize(df, now=datetime(2026, 9, 25, 19, 59, 30, tzinfo=timezone.utc))
    check("normalize drops still-open minute", "15:59" not in set(partial["ts"].str[-5:]))

    bad = frame(closes={("AAA", "High"): 1.0})
    check("normalize drops high<low", len(mb.normalize(bad, now=NOW)) < len(out))

    single = mb.normalize(frame(tickers=("AAA",))["AAA"], now=NOW, ticker="AAA")
    check("normalize accepts single ticker", set(single["ticker"]) == {"AAA"})


def test_collect():
    conn = sqlite3.connect(":memory:")
    mb.init(conn)
    calls = []

    def download(tickers):
        calls.append(list(tickers))
        return frame()

    first = mb.collect(conn, tickers=["AAA", "BBB"], download=download, now=NOW)
    check("collect stores rows", first["rows_new"] > 0, first)
    check("collect calls download once", len(calls) == 1)
    stored = conn.execute("SELECT COUNT(*) FROM minute_bars").fetchone()[0]
    check("collect row count matches", stored == first["rows_new"])

    second = mb.collect(conn, tickers=["AAA", "BBB"], download=download, now=NOW)
    check("second collect adds 0 rows", second["rows_new"] == 0, second)

    def download_changed(tickers):
        return frame(closes={("AAA", "Close"): 999.0})

    mb.collect(conn, tickers=["AAA", "BBB"], download=download_changed, now=NOW)
    close = conn.execute(
        "SELECT close FROM minute_bars WHERE ticker='AAA' AND ts='2026-09-25 09:50'"
    ).fetchone()[0]
    check("collect never overwrites", close != 999.0, close)

    def boom(tickers):
        raise RuntimeError("network down")

    failed = mb.collect(conn, tickers=["AAA"], download=boom, now=NOW)
    check("raising download returns rows_new 0", failed["rows_new"] == 0, failed)
    note = conn.execute(
        "SELECT note FROM minute_bars_log ORDER BY run_at DESC LIMIT 1"
    ).fetchone()[0]
    check("raising download is logged", "network down" in note, note)


def test_queries():
    conn = sqlite3.connect(":memory:")
    mb.init(conn)
    rows = []
    for day in ("2026-09-24", "2026-09-25"):
        bars = mb.normalize(frame(day=day), now=NOW)
        rows.extend(bars.itertuples(index=False, name=None))
    conn.executemany(
        "INSERT OR IGNORE INTO minute_bars VALUES (?,?,?,?,?,?,?)", rows)
    conn.commit()

    cov = {r["ticker"]: r for r in mb.coverage(conn)}
    check("coverage counts sessions", cov["AAA"]["sessions"] == 2, cov)
    check("coverage counts bars", cov["AAA"]["bars"] == 2 * 35, cov)

    one = mb.session(conn, "AAA", "2026-09-25")
    check("session returns one day", set(one["ts"].str[:10]) == {"2026-09-25"})
    check("session is sorted", list(one["ts"]) == sorted(one["ts"]))

    seen = []
    for ts, bucket in mb.replay(conn, "2026-09-25"):
        seen.append(ts)
        for row in bucket.values():
            if row["ts"] > ts:
                check("replay has no look-ahead", False, row["ts"])
    check("replay is increasing", seen == sorted(seen) and len(seen) == 35, len(seen))   # 09:30-10:04 ET in the fixture
    check("replay yields bars", len(seen) > 0)


test_normalize()
test_collect()
test_queries()

if FAILED:
    print("FAILED: %d" % len(FAILED))
    sys.exit(1)
print("ALL PASS")
