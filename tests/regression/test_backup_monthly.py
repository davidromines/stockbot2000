"""The monthly archives (2026-11-18): forward.sql.gz had reached 80 MB against GitHub's 100 MB file limit, so the
append-only date tables are archived one month per file. Restoring forward + monthly must give back every row, an
unchanged month must produce a byte-identical file (git stores it once), and a changed month must be rewritten."""
import runtime  # noqa: F401

import gzip
import shutil
import sqlite3
import tempfile
from pathlib import Path

import backup

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

tmp = Path(tempfile.mkdtemp())
try:
    db = sqlite3.connect(tmp / "src.db")
    db.executescript("""
        CREATE TABLE minute_bars(ticker TEXT, ts TEXT, close REAL, PRIMARY KEY(ticker, ts)) WITHOUT ROWID;
        CREATE INDEX mb_ts ON minute_bars(ts);
        CREATE TABLE paper_runs(run_id TEXT PRIMARY KEY, name TEXT);
        INSERT INTO paper_runs VALUES ('r1', 'it''s quoted');
    """)
    rows = [("AAA", f"2026-{m:02d}-{d:02d} 09:{i:02d}", 10.0 + i) for m in (9, 10, 11) for d in (3, 20) for i in range(5)]
    db.executemany("INSERT INTO minute_bars VALUES (?,?,?)", rows)
    db.commit()

    out = tmp / "backups"
    out.mkdir()
    counts = backup.dump(db, out / "forward.sql.gz", ["paper_runs", "minute_bars"], schema_only={"minute_bars"})
    check("forward keeps the monthly table's schema with no rows", counts == {"paper_runs": 1, "minute_bars": 0})
    res = backup.dump_monthly(db, out / "monthly", {"minute_bars": "ts"})
    check("one file per month", sorted(p.name for p, _, _ in res) ==
          ["minute_bars_2026-09.sql.gz", "minute_bars_2026-10.sql.gz", "minute_bars_2026-11.sql.gz"])
    check("every month written and verified on the first run", all(st == "written" for _, _, st in res))
    check("rows split by month", [n for _, n, _ in res] == [10, 10, 10])

    # Restore exactly as main() prints it: forward first, then the monthly files.
    r = sqlite3.connect(tmp / "restored.db")
    sql = "".join(gzip.open(p, "rt").read() for p in [out / "forward.sql.gz"] + sorted((out / "monthly").glob("*.gz")))
    r.executescript(sql)
    check("restore gives back every row", sorted(r.execute("SELECT * FROM minute_bars").fetchall()) == sorted(rows))
    check("restore keeps the other forward tables", r.execute("SELECT name FROM paper_runs").fetchone()[0] == "it's quoted")
    check("restore keeps the index", r.execute("SELECT 1 FROM sqlite_master WHERE name='mb_ts'").fetchone() is not None)
    r.close()

    before = {p.name: p.read_bytes() for p in (out / "monthly").glob("*.gz")}
    res2 = backup.dump_monthly(db, out / "monthly", {"minute_bars": "ts"})
    check("an unchanged month is left alone", all(st == "unchanged" for _, _, st in res2))
    check("its bytes are identical (no timestamp, gzip mtime 0)",
          before == {p.name: p.read_bytes() for p in (out / "monthly").glob("*.gz")})

    db.execute("UPDATE minute_bars SET close=99 WHERE ts LIKE '2026-10%' AND ts LIKE '%09:00'")
    db.execute("INSERT INTO minute_bars VALUES ('BBB', '2026-12-01 09:30', 5.0)")
    db.commit()
    st = {p.name: s for p, _, s in backup.dump_monthly(db, out / "monthly", {"minute_bars": "ts"})}
    check("a changed past month is rewritten", st["minute_bars_2026-10.sql.gz"] == "written")
    check("untouched months stay unchanged",
          st["minute_bars_2026-09.sql.gz"] == st["minute_bars_2026-11.sql.gz"] == "unchanged")
    check("a new month gets its own file", st.get("minute_bars_2026-12.sql.gz") == "written")
    check("no scratch directories left behind", not [p for p in (out / "monthly").iterdir() if p.is_dir()])

    check("every MONTHLY table is in the forward group", set(backup.MONTHLY) <= set(backup.GROUPS["forward"]))
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
