"""
REGRESSION: a truth set may not span the seal, and a failed build leaves nothing.

Two defects found 2026-09-22, both in code that already claimed to handle them.

1. The research snapshot's default window ended ON `sealed_start`, and SQL
   `BETWEEN` is inclusive at both ends — so the seal's first session belonged to
   both files. v1 escaped contamination only because 2023-01-01 was a Sunday.
   A calendar coincidence is not a control.

2. `build()` carried a comment promising that a failed build leaves no partial
   file. There was no `try` in the function. A crash left a readable stub, the
   next attempt hit the immutability guard, and the only way forward was to
   chmod and delete the file — training exactly the habit the guard prevents.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_seal_boundary.py
"""
import runtime  # noqa: F401
from pathlib import Path

import truth_set
from universe import load_config

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


cfg = load_config()
seal = cfg["lab"]["sealed_start"]

# --- the exclusive bound -----------------------------------------------------
check("_prev_day steps back one calendar day",
      truth_set._prev_day("2023-01-01") == "2022-12-31")
check("_prev_day crosses a month boundary",
      truth_set._prev_day("2023-03-01") == "2023-02-28")

# --- the straddle guard ------------------------------------------------------
def straddles(a, b):
    try:
        truth_set.build(None, cfg, "__probe__", a, b)
        return False
    except SystemExit as e:
        return "straddles the seal" in str(e)
    except Exception:
        return False   # got past the guard, failed later for another reason


check("a window ending ON sealed_start is REFUSED",
      straddles("2006-01-01", seal),
      "BETWEEN is inclusive — this is the overlap that v1 escaped by calendar luck")
check("a window spanning the seal entirely is REFUSED",
      straddles("2006-01-01", "2025-01-01"))
check("a research window ending the day before the seal is ALLOWED",
      not straddles("2006-01-01", truth_set._prev_day(seal)))
check("a sealed window starting ON the seal is ALLOWED",
      not straddles(seal, "2026-01-01"))

# --- no partial file on failure ---------------------------------------------
probe = truth_set.ROOT / "truth___partial__.db"
if probe.exists():
    probe.chmod(0o600); probe.unlink()

try:
    # conn=None crashes once the build starts querying — after the file is made.
    truth_set.build(None, cfg, "__partial__", "2006-01-01",
                    truth_set._prev_day(seal))
except BaseException:
    pass

check("a crashed build leaves no partial file behind", not probe.exists(),
      "the next attempt would hit the immutability guard, and the workaround "
      "is to delete the very file the guard protects")

if probe.exists():
    probe.chmod(0o600); probe.unlink()

# --- the built research set is actually clean --------------------------------
m = truth_set.load_manifest()
if "v1" in m["versions"]:
    import sqlite3
    c = sqlite3.connect(f"file:{m['versions']['v1']['file']}?mode=ro", uri=True)
    n = c.execute("SELECT COUNT(*) FROM prices WHERE date >= ?", (seal,)).fetchone()[0]
    c.close()
    check("the research truth set holds ZERO bars from the sealed window", n == 0,
          f"{n:,} sealed bars are visible to research")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
