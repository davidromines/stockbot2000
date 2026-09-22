"""
Backfill filing provenance from the cached SEC zips. Phase 9, item 24.

WHAT WAS MISSING
----------------
`sec_filings` stored `filed` — a DATE. The spec requires the accepted
date/time, and the difference is not pedantic: the SEC's own data shows
submissions accepted at 17:44 and stamped with the NEXT day's filed date. A
filing accepted after the 16:00 close cannot be traded on the day it was
accepted, and one accepted at 09:00 can be traded that same session. A date
alone cannot tell those apart, and the current pipeline papers over it with a
blunt two-day lag applied to everything.

Three fields are recovered from `sub.txt`, all already on disk:

    accepted   the acceptance timestamp, to the minute
    prevrpt    1 when this submission was later superseded by an amendment
    detail     1 when the submission carried detailed tagging

`prevrpt` is the amendment status the spec asks for, and it is better than
inferring one from the form string: a 10-K that was later amended is still
form "10-K", so form alone cannot tell you a filing was superseded.

**Nothing here changes a number.** It adds provenance to filings already
stored. The point-in-time machinery was verified correct before this ran —
429 of 429 sampled daily rows matched the newest filing actually available by
their date — so this makes the record auditable rather than fixing a leak.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import csv
import io
import logging
import zipfile
from pathlib import Path

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pit_backfill")

CACHE = Path("data/sec_fundamentals")


def add_columns(conn) -> None:
    """Idempotent: SQLite has no ADD COLUMN IF NOT EXISTS."""
    have = {r[1] for r in conn.execute("PRAGMA table_info(sec_filings)")}
    for col, decl in (("accepted", "TEXT"), ("prevrpt", "INTEGER"),
                      ("detail", "INTEGER")):
        if col not in have:
            conn.execute(f"ALTER TABLE sec_filings ADD COLUMN {col} {decl}")
            log.info(f"added sec_filings.{col}")
    conn.commit()


def backfill(conn, limit: int | None = None) -> dict:
    add_columns(conn)
    files = sorted(CACHE.glob("*.zip"))
    if limit:
        files = files[:limit]
    known = {r[0] for r in conn.execute("SELECT adsh FROM sec_filings")}
    log.info(f"{len(files)} quarters to scan; {len(known):,} filings stored")

    updated = seen = 0
    for n, path in enumerate(files, 1):
        rows = []
        try:
            with zipfile.ZipFile(path) as z, z.open("sub.txt") as f:
                for r in csv.DictReader(io.TextIOWrapper(f, "latin-1"),
                                        delimiter="\t"):
                    adsh = r.get("adsh")
                    if adsh not in known:
                        continue
                    seen += 1
                    rows.append((r.get("accepted") or None,
                                 int(r["prevrpt"]) if r.get("prevrpt", "").isdigit() else None,
                                 int(r["detail"]) if r.get("detail", "").isdigit() else None,
                                 adsh))
        except (zipfile.BadZipFile, KeyError) as e:
            log.warning(f"{path.name}: {e}")
            continue
        if rows:
            # Only provenance columns are written. The filing's identity and its
            # figures are untouched by design — this is an annotation pass.
            conn.executemany("UPDATE sec_filings SET accepted=?, prevrpt=?, "
                             "detail=? WHERE adsh=?", rows)
            conn.commit()
            updated += len(rows)
        if n % 10 == 0:
            log.info(f"  {n}/{len(files)} quarters | {updated:,} annotated")
    return {"quarters": len(files), "matched": seen, "updated": updated}


def coverage(conn) -> dict:
    tot = conn.execute("SELECT COUNT(*) FROM sec_filings").fetchone()[0]
    have = {r[1] for r in conn.execute("PRAGMA table_info(sec_filings)")}
    if "accepted" not in have:
        return {"total": tot, "with_accepted": 0, "note": "not yet backfilled"}
    acc = conn.execute("SELECT COUNT(*) FROM sec_filings "
                       "WHERE accepted IS NOT NULL").fetchone()[0]
    sup = conn.execute("SELECT COUNT(*) FROM sec_filings "
                       "WHERE prevrpt=1").fetchone()[0]
    # The whole reason the timestamp matters: a filing accepted at or after the
    # close is not tradeable information until the next session.
    late = conn.execute("""SELECT COUNT(*) FROM sec_filings
        WHERE accepted IS NOT NULL
          AND CAST(substr(accepted, 12, 2) AS INTEGER) >= 16""").fetchone()[0]
    return {"total": tot, "with_accepted": acc, "superseded": sup,
            "accepted_after_close": late,
            "after_close_share": (late / acc) if acc else 0.0}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--limit", type=int)
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.run:
        r = backfill(conn, a.limit)
        print(f"\n  annotated {r['updated']:,} filings across {r['quarters']} quarters")

    c = coverage(conn)
    print(f"\n  FILING PROVENANCE")
    print("  " + "-" * 62)
    print(f"  filings stored           {c['total']:>10,}")
    print(f"  with an accepted time    {c['with_accepted']:>10,}")
    if c.get("with_accepted"):
        print(f"  superseded by amendment  {c['superseded']:>10,}")
        print(f"  accepted AT/AFTER 16:00  {c['accepted_after_close']:>10,}"
              f"  ({c['after_close_share']:.1%})")
        print()
        print("  Those late filings are the reason a date is not enough: they")
        print("  are not tradeable information until the following session.")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
