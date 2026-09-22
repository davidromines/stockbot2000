"""
An immutable, versioned, hashed dataset the research system cannot modify.
Phase 6 section 4.

THE KEY PROPERTY
----------------
**The backtest engine does not build the truth set.** Everything else in this
project reads and writes one database, which means a bug anywhere can change the
data a result was computed on, and nobody would know. A frozen snapshot with a
hash removes that: a result cites a truth-set version, and that version either
still hashes to the same value or it does not.

This is not a backup. A backup protects against loss; this protects against
*drift* — the slow, invisible kind where a repair to one module silently changes
what an experiment from three weeks ago was measuring.

WHAT IMMUTABLE MEANS HERE
--------------------------
The snapshot is written once to its own SQLite file, the file is made read-only
at the filesystem level, and its SHA-256 is recorded in a manifest. Mutation
requires creating a new version; there is no in-place edit path, and `verify()`
fails loudly if a file's hash no longer matches its manifest entry.

Read-only permissions are a guard rail rather than a security boundary — anyone
with the account can chmod it back. The point is that it cannot happen by
accident, which is the failure mode that actually occurs.

WHAT GOES IN
------------
Prices with their OHLCV, the security type, and the listing status and delisting
date where known. Not features: those are derived, recomputable, and thirty
million rows. A truth set is the raw record, and derived values belong to
whatever computed them.

SCOPE IS DELIBERATELY BOUNDED
------------------------------
A full snapshot of 35.5M bars would be several gigabytes per version, which
makes versioning unaffordable and therefore unused. The default is the research
window over the tradeable universe, which is what experiments actually read.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
import os
import sqlite3
import stat
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("truth")

ROOT = Path("truth_sets")
MANIFEST = ROOT / "manifest.json"


def _hash(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while True:
            b = fh.read(chunk)
            if not b:
                break
            h.update(b)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST.exists():
        return json.loads(MANIFEST.read_text())
    return {"versions": {}}


def save_manifest(m: dict) -> None:
    ROOT.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(m, indent=2, sort_keys=True))


def _freeze(path: Path) -> None:
    """Read-only for everyone. A guard rail against accident, not an ACL."""
    path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)


def _prev_day(iso: str) -> str:
    """The calendar day before `iso`. Not a market session — an exclusive bound."""
    return (date.fromisoformat(iso) - timedelta(days=1)).isoformat()


def build(conn, cfg: dict, version: str, start: str, end: str,
          types: list | None = None) -> dict:
    ROOT.mkdir(parents=True, exist_ok=True)
    out = ROOT / f"truth_{version}.db"
    if out.exists():
        raise SystemExit(
            f"{out} already exists. Truth sets are immutable — create a new "
            f"version rather than rebuilding one that results may already cite.")

    types = types or cfg["universe"]["tradeable_types"]

    # A window may lie wholly before the seal or wholly on or after it, never
    # across it. `BETWEEN` is inclusive at both ends, so a research window
    # ending exactly on sealed_start would pull in the seal's first session —
    # one day, in both files, silently. The check is on the CALLER's dates
    # rather than on what came back, because an empty first session would hide
    # the overlap on a holiday and expose it on a Monday.
    seal = cfg["lab"]["sealed_start"]
    if start < seal <= end:
        raise SystemExit(
            f"window {start}..{end} straddles the seal at {seal}. The research "
            f"snapshot must end before it ({_prev_day(seal)}) and the sealed "
            f"snapshot must start on it. A snapshot spanning both is not a "
            f"holdout.")
    kind = "SEALED" if start >= seal else "research"
    log.info(f"building {kind} truth set {version}: {start}..{end}, types={types}")

    # A failed build must not leave a partial file behind: immutability would
    # then refuse the retry, and the obvious workaround is to chmod and delete
    # the very thing the guard exists to protect.
    try:
        return _build_into(conn, dst_path=out, version=version, start=start,
                           end=end, types=types)
    except BaseException:
        # The comment above was a promise the code did not keep: a crash mid-build
        # left a readable partial file, and the next attempt hit the immutability
        # guard instead. The only way forward then is to chmod and delete the
        # file — training exactly the habit the guard exists to prevent.
        if out.exists():
            out.chmod(0o600)
            out.unlink()
            log.warning(f"removed partial truth set {out}")
        raise


def _build_into(conn, dst_path, version: str, start: str, end: str,
                types: list) -> dict:
    out = dst_path
    dst = sqlite3.connect(out)
    dst.execute("""CREATE TABLE prices (
        ticker TEXT NOT NULL, date TEXT NOT NULL,
        open REAL, high REAL, low REAL, close REAL, volume INTEGER,
        PRIMARY KEY (ticker, date)) WITHOUT ROWID""")
    dst.execute("""CREATE TABLE securities (
        ticker TEXT PRIMARY KEY, security_type TEXT, exchange TEXT,
        first_seen TEXT, last_seen TEXT, is_active INTEGER,
        listing_status TEXT, delisting_date TEXT)""")

    ph = ",".join("?" * len(types))
    rows = conn.execute(f"""
        SELECT p.ticker, p.date, p.open, p.high, p.low, p.close, p.volume
        FROM prices p WHERE p.date BETWEEN ? AND ?
          AND p.ticker IN (SELECT ticker FROM symbols
                           WHERE security_type IN ({ph}) AND data_quality IS NULL)
    """, (start, end, *types))
    n = 0
    batch = []
    for r in rows:
        batch.append(tuple(r))
        if len(batch) >= 50_000:
            dst.executemany("INSERT OR IGNORE INTO prices VALUES (?,?,?,?,?,?,?)", batch)
            n += len(batch); batch = []
    if batch:
        dst.executemany("INSERT OR IGNORE INTO prices VALUES (?,?,?,?,?,?,?)", batch)
        n += len(batch)

    # Delisting status is joined in rather than left to a later lookup, because
    # the whole point is that a run can answer "what was listed then" from the
    # frozen file alone.
    sec = conn.execute(f"""
        SELECT s.ticker, s.security_type, s.exchange, s.first_seen, s.last_seen,
               s.is_active,
               CASE WHEN d.symbol IS NOT NULL THEN 'delisted'
                    WHEN s.is_active = 1 THEN 'listed' ELSE 'unknown' END,
               d.delisting_date
        FROM symbols s
        LEFT JOIN delistings d ON d.symbol = s.ticker
        WHERE s.security_type IN ({ph})""", tuple(types)).fetchall()
    dst.executemany("INSERT OR REPLACE INTO securities VALUES (?,?,?,?,?,?,?,?)",
                    [tuple(x) for x in sec])
    dst.commit()
    counts = {
        "price_rows": dst.execute("SELECT COUNT(*) FROM prices").fetchone()[0],
        "tickers": dst.execute("SELECT COUNT(DISTINCT ticker) FROM prices").fetchone()[0],
        "securities": dst.execute("SELECT COUNT(*) FROM securities").fetchone()[0],
        "delisted": dst.execute("SELECT COUNT(*) FROM securities "
                                "WHERE listing_status='delisted'").fetchone()[0],
    }
    dst.close()
    _freeze(out)
    if counts["price_rows"] == 0:
        out.chmod(0o600); out.unlink()
        raise SystemExit("truth set would be empty — refusing to record a "
                         "version that cites nothing")

    entry = {"version": version, "file": str(out), "sha256": _hash(out),
             "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
             "window": [start, end], "security_types": types,
             "bytes": out.stat().st_size, **counts}
    m = load_manifest(); m["versions"][version] = entry; save_manifest(m)
    log.info(f"  {counts['price_rows']:,} bars, {counts['tickers']:,} tickers, "
             f"{counts['securities']:,} securities ({counts['delisted']:,} delisted)")
    return entry


def verify(version: str | None = None) -> list:
    """Re-hash every version and report drift. A mismatch is a corrupted result trail."""
    m = load_manifest()
    problems = []
    for v, e in sorted(m["versions"].items()):
        if version and v != version:
            continue
        p = Path(e["file"])
        if not p.exists():
            problems.append(f"{v}: file missing ({p})"); continue
        got = _hash(p)
        if got != e["sha256"]:
            problems.append(f"{v}: HASH MISMATCH — every result citing this "
                            f"version is now unverifiable")
        writable = bool(p.stat().st_mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
        if writable:
            problems.append(f"{v}: file is WRITABLE — immutability not enforced")
    return problems


def open_version(version: str) -> sqlite3.Connection:
    """
    Open a truth set read-only, after verifying its hash.

    Verified on every open rather than once at build time: the cost is seconds
    and the alternative is discovering the drift in a result instead of in a
    check.
    """
    m = load_manifest()
    if version not in m["versions"]:
        raise SystemExit(f"unknown truth-set version {version!r}; "
                         f"have {sorted(m['versions'])}")
    probs = verify(version)
    if probs:
        raise SystemExit("truth set failed verification:\n  " + "\n  ".join(probs))
    p = Path(m["versions"][version]["file"])
    conn = sqlite3.connect(f"file:{p}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", metavar="VERSION")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--list", action="store_true")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--sealed", action="store_true",
                    help="build the SEALED carve-out (sealed_start..today) "
                         "instead of the research window")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()

    if a.build:
        conn = storage.connect(cfg["database"]["market_data_path"])
        lab = cfg["lab"]
        if a.sealed:
            # Defaults, not suggestions: the seal's bounds are a config decision
            # made long before any particular strategy wanted to cross them.
            start = a.start or lab["sealed_start"]
            end = a.end or date.today().isoformat()
        else:
            start = a.start or lab["search_start"]
            # Exclusive of the seal. The old default ended ON sealed_start and
            # BETWEEN is inclusive, so the seal's first session sat in both files.
            end = a.end or _prev_day(lab["sealed_start"])
        e = build(conn, cfg, a.build, start, end)
        conn.close()
        print(f"\n  TRUTH SET {a.build}" + ("  [SEALED]" if a.sealed else ""))
        print(f"    file    {e['file']}  ({e['bytes']/1e6:.1f} MB, read-only)")
        print(f"    sha256  {e['sha256'][:32]}...")
        print(f"    bars    {e['price_rows']:,} across {e['tickers']:,} tickers")
        print(f"    window  {e['window'][0]} .. {e['window'][1]}")
        if a.sealed:
            print("\n    Read this only through evaluate_holdout.py. One")
            print("    evaluation per strategy, ever, and no way to un-peek.")
        return 0
    if a.verify:
        probs = verify()
        print(f"\n  {'ALL VERIFIED' if not probs else 'PROBLEMS FOUND'}")
        for x in probs:
            print("   ", x)
        return 0 if not probs else 1
    m = load_manifest()
    print(f"\n  TRUTH SETS ({len(m['versions'])})")
    for v, e in sorted(m["versions"].items()):
        print(f"    {v:<12}{e['price_rows']:>12,} bars  {e['window'][0]}..{e['window'][1]}"
              f"  {e['sha256'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
