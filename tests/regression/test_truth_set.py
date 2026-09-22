"""
REGRESSION: the truth set must be immutable, versioned and verified.

Its purpose is protection against DRIFT, not loss: the slow invisible kind where
a repair to one module silently changes what an experiment from three weeks ago
was measuring. A snapshot whose hash is not checked, or whose file can be edited
in place, provides none of that.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_truth_set.py
"""
import runtime  # noqa: F401
import sqlite3
import stat
from pathlib import Path

import truth_set as ts

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


m = ts.load_manifest()
check("a manifest exists with at least one version", bool(m.get("versions")),
      str(list(m.get("versions", {}))))

if m.get("versions"):
    v = sorted(m["versions"])[0]
    e = m["versions"][v]
    p = Path(e["file"])

    check("the snapshot file exists", p.exists(), str(p))
    check("the manifest records a sha256", len(e.get("sha256", "")) == 64)
    check("the manifest records the window", len(e.get("window", [])) == 2)
    check("the manifest records row counts", e.get("price_rows", 0) > 0,
          str(e.get("price_rows")))

    mode = p.stat().st_mode
    writable = bool(mode & (stat.S_IWUSR | stat.S_IWGRP | stat.S_IWOTH))
    check("the file is READ-ONLY on disk", not writable,
          "immutability must be enforced, not merely intended")

    check("verify() passes on an untouched set", ts.verify(v) == [])

    # The property that matters: a write must fail.
    try:
        c = sqlite3.connect(str(p))
        c.execute("INSERT INTO prices VALUES ('ZZZ','2020-01-01',1,1,1,1,1)")
        c.commit()
        c.close()
        check("writing to the truth set FAILS", False,
              "the snapshot accepted a write — it is not immutable")
    except Exception:
        check("writing to the truth set FAILS", True)

    # Opening read-only must work, and must verify first.
    conn = ts.open_version(v)
    n = conn.execute("SELECT COUNT(*) FROM prices").fetchone()[0]
    check("open_version returns a usable read-only handle", n > 0, f"{n} rows")
    try:
        conn.execute("DELETE FROM prices")
        check("a read-only handle rejects writes", False)
    except Exception:
        check("a read-only handle rejects writes", True)
    conn.close()

    check("securities carry listing status", ts.open_version(v).execute(
        "SELECT COUNT(*) FROM securities WHERE listing_status IS NOT NULL"
    ).fetchone()[0] > 0)

    # Rebuilding an existing version must be refused, or immutability is a
    # convention rather than a property.
    import io, contextlib
    refused = False
    try:
        import storage
        from universe import load_config
        cfg = load_config()
        c = storage.connect(cfg["database"]["market_data_path"])
        with contextlib.redirect_stderr(io.StringIO()):
            ts.build(c, cfg, v, "2020-01-01", "2020-02-01")
    except SystemExit:
        refused = True
    except Exception:
        refused = True
    check("rebuilding an EXISTING version is refused", refused,
          "results cite a version; silently rebuilding it invalidates them")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
