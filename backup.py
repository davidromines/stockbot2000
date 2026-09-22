"""
Back up the data that cannot be regenerated. Everything else is re-fetchable.

WHAT IS AND IS NOT IRREPLACEABLE
---------------------------------
`prices` and `features` are 35M and 33M rows and take hours to rebuild — but they
CAN be rebuilt, by re-running the backfill. Losing them costs time.

These cannot be rebuilt at any price:

  forward records   paper_equity, pair_fund_equity, picks, claude_fund and the
                    trade tables. They accrue only in calendar time. A paper fund
                    that has run 14 days cannot be made to have run 14 days by
                    running anything; the dates have to pass. This is the only
                    unbiased measurement the project has and it is the single
                    most expensive thing here to lose.

  point-in-time     symbols, historical_listings, archive_snapshots. The daily
  listings          directory snapshot is what stamps a ticker inactive on the
                    day it disappears, and CLAUDE.md is explicit that a missed
                    day loses that day's delistings PERMANENTLY. The Internet
                    Archive replays behind historical_listings took hours of
                    rate-limited fetching and archive.org is under no obligation
                    to serve them the same way again.

  execution record  signals, orders, fills, risk_events. What the system decided
                    and why, for the money that actually moved.

  ladder decisions  promotions and lab_runs. The genomes themselves are
                    reproducible in principle and worth little — six searches
                    produced six artifacts — but WHICH ones were promoted, when,
                    and under which gate is the audit trail for every claim this
                    project has made.

`evaluations` and `strategies` are deliberately excluded. A million rows of
mostly-artifact scores, reproducible by re-running the search, and they would
dominate the archive while being the least valuable thing in it.

A BACKUP THAT HAS NEVER BEEN RESTORED IS NOT A BACKUP
------------------------------------------------------
Every run restores its own output into a scratch database and compares row counts
table by table. A dump that cannot be read back fails loudly here rather than on
the day it is needed. `--verify-only` re-checks an existing archive without
making a new one.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import gzip
import hashlib
import logging
import shutil
import sqlite3
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("backup")

OUT_DIR = Path("backups")

# TWO archives, because the two halves have opposite shapes.
#
# `forward` changes every single day and is about 2,500 rows — small enough to
# commit on every run, which is what actually gets it off this machine. `listings`
# is half a million rows and changes only when the directory or the Internet
# Archive replay runs, so re-committing it daily would add gigabytes a year to
# the repo to store something that did not change.
#
# Splitting them is the difference between a backup that is pushed to GitHub
# every morning and one that sits on the same disk as the thing it protects.
GROUPS = {
    "forward": [
        # accrues only in calendar time; cannot be recomputed at any price
        "paper_runs", "paper_equity", "paper_positions", "paper_trades",
        "pair_funds", "pair_fund_equity",
        "picks", "claude_fund", "claude_fund_meta",
        # what the system decided, and why, for money that actually moved
        "signals", "orders", "fills", "risk_events", "system_events",
        "experiments", "experiment_trades",
        # which strategies were promoted, when, under which gate
        "promotions", "lab_runs",
    ],
    "listings": [
        # a missed day of the directory loses that day's delistings permanently,
        # and the Archive replays took hours of rate-limited fetching
        "symbols", "historical_listings", "archive_snapshots", "delistings",
    ],
}
TABLES = [t for g in GROUPS.values() for t in g]


def dump(conn, path: Path, tables: list) -> dict:
    """Write a gzipped SQL dump of `tables` only, and report what went in."""
    counts = {}
    present = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    with gzip.open(path, "wt", encoding="utf-8", compresslevel=9) as fh:
        fh.write("-- stockbot2000 irreplaceable-data backup\n")
        fh.write(f"-- created {datetime.now(timezone.utc).isoformat()}\n")
        fh.write("PRAGMA foreign_keys=OFF;\nBEGIN TRANSACTION;\n")
        for t in tables:
            if t not in present:
                log.warning(f"{t}: not present, skipped")
                continue
            n = 0
            # iterdump on a whole connection would pull in prices and features.
            # Per-table statements keep the archive to what is actually at risk.
            schema = conn.execute(
                "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
                (t,)).fetchone()
            if schema and schema[0]:
                fh.write(f"DROP TABLE IF EXISTS {t};\n{schema[0]};\n")
            cur = conn.execute(f"SELECT * FROM {t}")
            cols = [d[0] for d in cur.description]
            collist = ",".join(f'"{c}"' for c in cols)
            for row in cur:
                vals = []
                for v in row:
                    if v is None:
                        vals.append("NULL")
                    elif isinstance(v, (int, float)):
                        vals.append(repr(v))
                    elif isinstance(v, bytes):
                        vals.append("X'" + v.hex() + "'")
                    else:
                        vals.append("'" + str(v).replace("'", "''") + "'")
                fh.write(f"INSERT INTO {t} ({collist}) VALUES ({','.join(vals)});\n")
                n += 1
            for idx in conn.execute(
                    "SELECT sql FROM sqlite_master WHERE type='index' AND tbl_name=? "
                    "AND sql IS NOT NULL", (t,)):
                fh.write(idx[0] + ";\n")
            counts[t] = n
            log.info(f"  {t:<22}{n:>8,} rows")
        fh.write("COMMIT;\n")
    return counts


def verify(path: Path, expected: dict) -> tuple[bool, list]:
    """
    Restore into a scratch database and compare row counts table by table.

    This is the part that makes it a backup rather than a file. A dump that
    cannot be read back is discovered here, on a day when it does not matter.
    """
    problems = []
    tmp = Path(tempfile.mkdtemp()) / "verify.db"
    try:
        con = sqlite3.connect(tmp)
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            con.executescript(fh.read())
        for t, want in expected.items():
            got = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if got != want:
                problems.append(f"{t}: dumped {want:,}, restored {got:,}")
        con.close()
    except Exception as e:      # noqa: BLE001 — any failure is a failed backup
        problems.append(f"restore failed: {type(e).__name__}: {e}")
    finally:
        shutil.rmtree(tmp.parent, ignore_errors=True)
    return (not problems), problems


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--keep", type=int, default=14, help="dated archives to retain")
    ap.add_argument("--verify-only", metavar="FILE")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    OUT_DIR.mkdir(exist_ok=True)

    if a.verify_only:
        p = Path(a.verify_only)
        counts = {}
        with gzip.open(p, "rt", encoding="utf-8") as fh:
            for line in fh:
                if line.startswith("INSERT INTO "):
                    t = line.split()[2]
                    counts[t] = counts.get(t, 0) + 1
        ok, probs = verify(p, counts)
        print(f"\n  {'VERIFIED' if ok else 'FAILED'}  {p}")
        for x in probs:
            print("   ", x)
        raise SystemExit(0 if ok else 1)

    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    all_ok, lines = True, []
    for group, tables in GROUPS.items():
        # `forward` is committed, so it keeps a stable name that git can track
        # across runs. `listings` is dated and retained, because it is large and
        # rewriting it in place would make an old copy unrecoverable.
        path = (OUT_DIR / f"{group}.sql.gz" if group == "forward"
                else OUT_DIR / f"{group}_{stamp}.sql.gz")
        log.info(f"dumping {group}: {len(tables)} tables -> {path}")
        counts = dump(conn, path, tables)
        ok, problems = verify(path, counts)
        all_ok = all_ok and ok
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if group != "forward" and ok:
            shutil.copy2(path, OUT_DIR / f"{group}_latest.sql.gz")
        lines.append((group, path, path.stat().st_size, sum(counts.values()),
                      len(counts), digest, ok, problems))
        for old in sorted(OUT_DIR.glob(f"{group}_2*.sql.gz"))[:-a.keep]:
            old.unlink(); log.info(f"pruned {old.name}")

    print(f"\n  BACKUP {'VERIFIED' if all_ok else 'FAILED VERIFICATION'}")
    print("  " + "-" * 62)
    for g, path, size, rows, ntab, digest, ok, problems in lines:
        print(f"  {g:<10}{size/1024:>8,.0f} KB{rows:>10,} rows  {ntab:>2} tables  "
              f"{digest}  {'ok' if ok else 'FAILED'}")
        print(f"             {path}")
        for x in problems:
            print("             PROBLEM:", x)
    print("  " + "-" * 62)
    print("  restore:  gunzip -c backups/forward.sql.gz | sqlite3 restored.db")
    print("  The forward archive is committed to git, so a push puts it off this")
    print("  machine. Listings is large and static; copy it deliberately.")
    conn.close()
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
