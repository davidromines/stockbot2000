"""
FINRA daily short-sale volume (Reg SHO), the free public source for the
short_interest family (owner, 2026-09-27: "yes download and build").

Source: https://cdn.finra.org/equity/regsho/daily/ — one pipe-delimited file per
trading day, published the same evening:

    2018-08-01 on   CNMSshvolYYYYMMDD.txt    consolidated (all FINRA facilities)
    before that     FNSQ / FNQC / FNYX / FORF shvolYYYYMMDD.txt, one per facility, summed

Columns used: Symbol, ShortVolume, TotalVolume. This is short SELLING volume on
FINRA-reported (off-exchange) trades, not short interest (shares held short,
reported twice a month); the published signal built on it is Boehmer, Jones &
Zhang (2008, JF): heavily shorted stocks underperform, lightly shorted ones do not.

Stored raw per (ticker, date) for tickers in our symbol directory. The daily
feature is the 20-session ratio sum(short) / sum(total), known after each
close, so a signal on day t trades at the next open like every other signal.
Every file fetched (or missing) is logged, so the backfill resumes.

    ./venv/bin/python short_volume.py --backfill [--start 2010-01-04]
    ./venv/bin/python short_volume.py --daily
    ./venv/bin/python short_volume.py --status
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone

log = logging.getLogger("short_volume")
BASE = "https://cdn.finra.org/equity/regsho/daily/"
CONSOLIDATED_FROM = "2018-08-01"
FACILITIES = ("FNSQ", "FNQC", "FNYX", "FORF")
WINDOW = 20


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS short_volume (
            ticker TEXT NOT NULL, date TEXT NOT NULL, short_vol REAL NOT NULL, total_vol REAL NOT NULL,
            PRIMARY KEY (ticker, date)) WITHOUT ROWID""")
    conn.execute("CREATE INDEX IF NOT EXISTS short_volume_date ON short_volume (date)")
    conn.execute("""
        CREATE TABLE IF NOT EXISTS short_volume_log (
            date TEXT PRIMARY KEY, files INTEGER NOT NULL, rows INTEGER NOT NULL, at TEXT NOT NULL)""")
    conn.commit()


def _get(name: str) -> str | None:
    """A file's text, or None when FINRA has no such file (403/404)."""
    for i in range(4):
        try:
            with urllib.request.urlopen(BASE + name, timeout=60) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 404):
                return None
        except Exception:                                   # noqa: BLE001 — network: retry
            pass
        time.sleep(2 * (i + 1))
    raise RuntimeError(f"FINRA fetch failed: {name}")


def parse(text: str) -> dict:
    """{symbol: (short, total)} from one file; header and trailer lines skipped."""
    out = {}
    for line in text.splitlines()[1:]:
        f = line.split("|")
        if len(f) < 4 or not f[0].isdigit():
            continue
        sym = f[1].strip()
        try:
            short = float(f[2])
            total = float(f[4] if len(f) >= 6 else f[3])     # the consolidated file adds ShortExemptVolume
        except ValueError:
            continue
        s0, t0 = out.get(sym, (0.0, 0.0))
        out[sym] = (s0 + short, t0 + total)
    return out


def fetch_day(conn, date: str, known: set) -> int:
    """Download, sum and store one trading day. Returns rows stored (0 if no file)."""
    ymd = date.replace("-", "")
    names = [f"CNMSshvol{ymd}.txt"] if date >= CONSOLIDATED_FROM else [f"{f}shvol{ymd}.txt" for f in FACILITIES]
    agg, files = {}, 0
    for n in names:
        text = _get(n)
        if text is None:
            continue
        files += 1
        for sym, (s, t) in parse(text).items():
            s0, t0 = agg.get(sym, (0.0, 0.0))
            agg[sym] = (s0 + s, t0 + t)
    # Our tickers write class shares with a dash (BRK-B); FINRA uses a dot (BRK.B).
    rows = [(sym.replace(".", "-"), date, s, t) for sym, (s, t) in agg.items()
            if sym.replace(".", "-") in known and t > 0]
    conn.executemany("INSERT OR REPLACE INTO short_volume VALUES (?,?,?,?)", rows)
    conn.execute("INSERT OR REPLACE INTO short_volume_log VALUES (?,?,?,?)",
                 (date, files, len(rows), datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    return len(rows)


def backfill(conn, start: str = "2010-01-04", end: str | None = None, redo_empty_after: str | None = None) -> dict:
    init(conn)
    known = {r[0] for r in conn.execute("SELECT ticker FROM symbols")}
    q = "SELECT date FROM prices WHERE ticker='SPY' AND date >= ?" + (" AND date <= ?" if end else "") + " ORDER BY date"
    dates = [r[0] for r in conn.execute(q, (start, end) if end else (start,))]
    done = {d: n for d, n in conn.execute("SELECT date, rows FROM short_volume_log")}
    todo = [d for d in dates if d not in done or (redo_empty_after and d >= redo_empty_after and done[d] == 0)]
    got = 0
    for i, d in enumerate(todo, 1):
        got += bool(fetch_day(conn, d, known))
        if i % 100 == 0:
            log.info(f"short volume: {i}/{len(todo)} days, latest {d}")
    return {"days": len(todo), "with_data": got}


def attach(conn, df, lo: str, hi: str, tickers: list):
    """short_volume_ratio_20 on a (ticker, date) frame: 20-session sum of short over
    total volume, through each date. NaN where FINRA reports nothing."""
    import pandas as pd
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE name='short_volume'").fetchone():
        df["short_volume_ratio_20"] = float("nan")
        return df
    start = (pd.Timestamp(lo) - pd.Timedelta(days=45)).strftime("%Y-%m-%d")
    parts = []
    for i in range(0, len(tickers), 900):
        chunk = tickers[i:i + 900]
        ph = ",".join("?" * len(chunk))
        parts.append(pd.read_sql_query(
            f"SELECT ticker AS _t, date AS _d, short_vol, total_vol FROM short_volume "
            f"WHERE date BETWEEN ? AND ? AND ticker IN ({ph})", conn, params=(start, hi, *chunk)))
    s = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame()
    if s.empty:
        df["short_volume_ratio_20"] = float("nan")
        return df
    s = s.sort_values(["_t", "_d"])
    g = s.groupby("_t", sort=False)
    sv = g["short_vol"].transform(lambda x: x.rolling(WINDOW, min_periods=WINDOW // 2).sum())
    tv = g["total_vol"].transform(lambda x: x.rolling(WINDOW, min_periods=WINDOW // 2).sum())
    s["short_volume_ratio_20"] = (sv / tv).astype("float32")
    return df.merge(s[["_t", "_d", "short_volume_ratio_20"]], on=["_t", "_d"], how="left")


def status(conn) -> dict:
    init(conn)
    r = conn.execute("SELECT COUNT(*), MIN(date), MAX(date), SUM(rows > 0) FROM short_volume_log").fetchone()
    return {"days_logged": r[0], "from": r[1], "to": r[2], "days_with_data": r[3],
            "rows": conn.execute("SELECT COUNT(*) FROM short_volume").fetchone()[0]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--start", default="2010-01-04")
    ap.add_argument("--daily", action="store_true", help="the newest sessions (re-asks recent empty days)")
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=120)
    init(conn)
    if a.backfill:
        print(json.dumps(backfill(conn, a.start)))
    if a.daily:
        recent = [r[0] for r in conn.execute("SELECT date FROM prices WHERE ticker='SPY' ORDER BY date DESC LIMIT 5")]
        print(json.dumps(backfill(conn, min(recent), redo_empty_after=min(recent))))
    if a.status:
        print(json.dumps(status(conn), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
