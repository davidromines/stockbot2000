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
        "paper_runs", "paper_equity", "paper_positions", "paper_trades", "paper_pending",
        "pair_funds", "pair_fund_equity",
        "picks", "claude_fund", "claude_fund_meta",
        # what the system decided, and why, for money that actually moved
        "signals", "orders", "fills", "risk_events", "system_events",
        "experiments", "experiment_trades",
        # which strategies were promoted, when, under which gate
        "promotions", "lab_runs",
        # the other forward funds (Phase 9 value fund, Phase 12 crypto fund)
        "value_fund", "value_fund_equity", "value_fund_positions", "value_fund_trades",
        "crypto_fund", "crypto_fund_equity", "crypto_fund_open", "crypto_fund_trades",
        "crypto_spreads",           # Stage K1: measured Robinhood spreads, not recomputable
        "crypto_slot_trades",       # Stage K5: the crypto slot trade log (append-only)
        "trader_runs",              # N1: one heartbeat per slot_trader run
        "option_funds", "option_fund_equity", "option_trades",   # Stage R: option paper funds (+ backtests)
        "option_backtests_history",  # option backtests as they were before each re-run (append-only)
        "intraday_trades",          # Stage Q2: same-day SHADOW trade book
        "ranking_history",          # N3: daily ranking snapshots (leaderboard movement)
        # append-only decision logs: identity, lifecycle, every §37 decision,
        # the authoritative accounting and the pre-registered experiments.
        # A lifecycle state is DERIVED from league_state, so losing that log
        # loses every strategy's state history. Added 2026-09-24; the League
        # and Phase 13 had been running outside the backup since 09-22.
        "league_strategies", "league_state", "league_standings",
        "strategy_meta", "strategy_metrics", "strategy_decisions", "strategy_ancestry",
        "fund_accounting", "experiment_registry", "failure_log",
        "scoreboard_snapshots", "degradation",
        # Addendum A: the slot record — which strategy held which slot, every
        # slot trade (LIVE included: real money since 2026-09-24), the stop
        # marks behind each exit, and the live account's equity snapshots.
        "slot_assignments", "slot_reviews", "slot_trades", "slot_marks", "live_equity",
        # Stage Q3: free minute history reaches back only ~7 days, so every collected
        # bar is irreplaceable once it ages out of the source.
        "minute_bars", "minute_bars_log",
        # Stage O rev 2: model translations (paid calls), lineage rulings (a person's
        # independence rulings among them), reproductions, provenance, the ledger.
        "knowledge_translations", "knowledge_lineage", "knowledge_reproductions",
        "strategy_provenance", "knowledge_lineage_stats",
        "strategy_failures",        # Stage T: why each strategy failed, day by day
        "capital_gate_shadow",      # Addendum F C1: daily shadow verdict of the capital-eligibility gate
        "hypothesis_scorecard",     # Addendum F E2: lineage scorecard, by date
        "holdout_results",          # one look per strategy at 2023 -> today: the record IS the rule
        "market_checks",            # bull-market checks per strategy (recomputable, kept for history)
        # Addendum G: the Intraday Runners' decision record — every qualifying signal (traded or
        # refused), the service heartbeat and open-position state. Added 2026-10-19 (Stage AD1.4).
        "intraday_runner_signals", "intraday_heartbeat", "intraday_state",
        # Stage AD4 / AD6: the signal registry, its append-only trial ledger (the multiple-testing denominator) and
        # the allocator's daily shadow decisions.
        "alpha_signals", "alpha_trials", "allocator_shadow",
        "paper_trades_restated",
        "timing_shadow", "prediction_log", "prediction_models",   # Stage AD4/AD5 shadow records    # Addendum F G1: the next-open restatement the decision layers now read
    ],
    "listings": [
        # a missed day of the directory loses that day's delistings permanently,
        # and the Archive replays took hours of rate-limited fetching
        "symbols", "historical_listings", "archive_snapshots", "delistings",
    ],
}
TABLES = [t for g in GROUPS.values() for t in g]

# A THIRD shape, found 2026-11-18: forward.sql.gz had grown to 80 MB (51 MB on 11-01) against GitHub's hard 100 MB
# per-file limit, so within days it could no longer be pushed. These forward tables are append-only by a date column
# and make up ~3/4 of it (minute bars alone ~40%). Each is archived one MONTH per file in backups/monthly/; a file is
# rewritten only when that month's rows change, so git stores a past month once. forward.sql.gz keeps their schema and
# indexes with no rows. Restore: forward first, then the monthly files (see main()).
MONTHLY = {"minute_bars": "ts", "fund_accounting": "as_of", "prediction_log": "date",
           "scoreboard_snapshots": "at", "degradation": "at", "ranking_history": "date",
           "capital_gate_shadow": "as_of", "league_standings": "as_of", "strategy_failures": "as_of",
           "intraday_heartbeat": "at"}
MONTHLY_DIR = OUT_DIR / "monthly"


def _sql_value(v) -> str:
    if v is None:
        return "NULL"
    if isinstance(v, (int, float)):
        return repr(v)
    if isinstance(v, bytes):
        return "X'" + v.hex() + "'"
    return "'" + str(v).replace("'", "''") + "'"


def dump(conn, path: Path, tables: list, schema_only=()) -> dict:
    """Write a gzipped SQL dump of `tables` only, and report what went in. Tables in `schema_only` get their
    schema and indexes but no rows (their rows are in the monthly archives)."""
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
            cur = conn.execute(f"SELECT * FROM {t}" + (" LIMIT 0" if t in schema_only else ""))
            cols = [d[0] for d in cur.description]
            collist = ",".join(f'"{c}"' for c in cols)
            for row in cur:
                fh.write(f"INSERT INTO {t} ({collist}) VALUES ({','.join(_sql_value(v) for v in row)});\n")
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


def dump_monthly(conn, out_dir: Path, tables: dict) -> list:
    """Archive each append-only table one month per file: out_dir/<table>_<YYYY-MM>.sql.gz.

    One pass per table routes rows to per-month files in a scratch directory. A file holds CREATE TABLE IF NOT
    EXISTS and its rows (no DROP, no indexes), so the files restore after forward.sql.gz in any order. The bytes
    are deterministic (no timestamp, gzip mtime 0): a month whose rows did not change produces an identical file
    and is left alone, so git stores it once. A changed or new month replaces its file only after a restore of it
    reads back the same row count. Returns (path, rows, status) per month; status is unchanged / written / FAILED."""
    import re
    out_dir.mkdir(parents=True, exist_ok=True)
    present = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    results = []
    for t, col in tables.items():
        if t not in present:
            log.warning(f"{t}: not present, skipped")
            continue
        schema = conn.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone()[0]
        create = re.sub(r"^\s*CREATE\s+TABLE\s+(IF\s+NOT\s+EXISTS\s+)?", "CREATE TABLE IF NOT EXISTS ", schema,
                        count=1, flags=re.IGNORECASE)
        cur = conn.execute(f"SELECT COALESCE(substr({col}, 1, 7), 'unknown'), * FROM {t}")
        cols = [d[0] for d in cur.description][1:]
        collist = ",".join(f'"{c}"' for c in cols)
        scratch = Path(tempfile.mkdtemp(dir=out_dir))
        writers, counts = {}, {}
        try:
            for row in cur:
                m = re.sub(r"[^0-9A-Za-z-]", "_", str(row[0]))
                if m not in writers:
                    raw = open(scratch / f"{t}_{m}.sql.gz", "wb")
                    gz = gzip.GzipFile(filename="", mode="wb", fileobj=raw, compresslevel=9, mtime=0)
                    gz.write(f"-- stockbot2000 monthly archive: {t} {m}\nPRAGMA foreign_keys=OFF;\n"
                             f"BEGIN TRANSACTION;\n{create};\n".encode())
                    writers[m], counts[m] = (raw, gz), 0
                writers[m][1].write(f"INSERT INTO {t} ({collist}) VALUES "
                                    f"({','.join(_sql_value(v) for v in row[1:])});\n".encode())
                counts[m] += 1
            for raw, gz in writers.values():
                gz.write(b"COMMIT;\n")
                gz.close()
                raw.close()
            total = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            if sum(counts.values()) != total:      # rows written while dumping: the next run catches them
                log.warning(f"{t}: {sum(counts.values()):,} rows archived of {total:,} counted")
            for m in sorted(counts):
                new, dest = scratch / f"{t}_{m}.sql.gz", out_dir / f"{t}_{m}.sql.gz"
                if dest.exists() and dest.read_bytes() == new.read_bytes():
                    results.append((dest, counts[m], "unchanged"))
                    continue
                ok, problems = verify(new, {t: counts[m]})
                if ok:
                    shutil.move(str(new), dest)
                    log.info(f"  {dest.name:<44}{counts[m]:>9,} rows written")
                else:
                    log.error(f"  {dest.name}: {problems}")
                results.append((dest, counts[m], "written" if ok else "FAILED"))
        finally:
            for raw, gz in writers.values():
                if not raw.closed:
                    gz.close()
                    raw.close()
            shutil.rmtree(scratch, ignore_errors=True)
    return results


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
        counts = dump(conn, path, tables, schema_only=set(MONTHLY) if group == "forward" else ())
        ok, problems = verify(path, counts)
        all_ok = all_ok and ok
        digest = hashlib.sha256(path.read_bytes()).hexdigest()[:16]
        if group != "forward" and ok:
            shutil.copy2(path, OUT_DIR / f"{group}_latest.sql.gz")
        lines.append((group, path, path.stat().st_size, sum(counts.values()),
                      len(counts), digest, ok, problems))
        for old in sorted(OUT_DIR.glob(f"{group}_2*.sql.gz"))[:-a.keep]:
            old.unlink(); log.info(f"pruned {old.name}")

    log.info(f"dumping monthly archives: {len(MONTHLY)} tables -> {MONTHLY_DIR}/")
    monthly = dump_monthly(conn, MONTHLY_DIR, MONTHLY)
    m_failed = [p.name for p, _, st in monthly if st == "FAILED"]
    all_ok = all_ok and not m_failed

    print(f"\n  BACKUP {'VERIFIED' if all_ok else 'FAILED VERIFICATION'}")
    print("  " + "-" * 62)
    for g, path, size, rows, ntab, digest, ok, problems in lines:
        print(f"  {g:<10}{size/1024:>8,.0f} KB{rows:>10,} rows  {ntab:>2} tables  "
              f"{digest}  {'ok' if ok else 'FAILED'}")
        print(f"             {path}")
        for x in problems:
            print("             PROBLEM:", x)
    n_w = sum(1 for _, _, st in monthly if st == "written")
    print(f"  {'monthly':<10}{sum(p.stat().st_size for p, _, st in monthly if p.exists())/1024:>8,.0f} KB"
          f"{sum(n for _, n, _ in monthly):>10,} rows  {len(MONTHLY):>2} tables  {len(monthly)} files, "
          f"{n_w} written  {'ok' if not m_failed else 'FAILED'}")
    print(f"             {MONTHLY_DIR}/")
    for x in m_failed:
        print("             PROBLEM: verification failed for", x)
    print("  " + "-" * 62)
    print("  restore:  gunzip -c backups/forward.sql.gz backups/monthly/*.sql.gz | sqlite3 restored.db")
    print("  forward + monthly are committed to git, so a push puts them off this")
    print("  machine. Listings is large and static; copy it deliberately.")
    conn.close()
    raise SystemExit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
