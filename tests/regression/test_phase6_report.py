"""
Regression test for phase6_report.py (Phase 6 §31).

Pinned: the report renders on a fresh, empty database without inventing
figures; the §30 checklist maps each item to the test files that evidence it
and reads PASS only when all of them passed; a missing test file is MISSING,
never PASS; an unrun suite is UNRUN; LIVE armed reads SUPERSEDED, not PASS.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import pair_funds
import paper_trading
import phase6_report as p6
import storage

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    from universe import load_config
    cfg = load_config()
    path = os.path.join(tempfile.mkdtemp(), "empty.db")
    conn = storage.connect(path)
    storage.init_db(conn)
    paper_trading.init(conn)
    pair_funds.init(conn)
    conn.row_factory = sqlite3.Row

    d = p6.gather(conn, cfg, None)
    text = p6.render(d)
    check("renders on an empty database", "# STOCKBOT2000 PHASE 6 REPORT" in text and "## REMAINING RISKS" in text)
    check("no tests run -> checklist UNRUN, not PASS",
          all(s in ("UNRUN", "PASS", "FAIL", "SUPERSEDED") for _, s, _ in p6.checklist(d))
          and any(s == "UNRUN" for _, s, _ in p6.checklist(d)))
    check("closing rule is in the report", "Infrastructure working is not success" in text)

    files = {f for _, fs, _ in p6.CHECKLIST for f in fs}
    d["tests"] = {"by_file": {f: "PASS" for f in files}, "passed": len(files), "failed": []}
    d["seed_free"] = {"A_seeded": {}, "B_seed_free": {}}
    d["firewall_doc"] = True
    d["execution"]["mode"] = "LIVE"
    rows = dict((i, s) for i, s, _ in p6.checklist(d))
    check("all evidence passing -> PASS", rows["Regime analysis works"] == "PASS")
    check("LIVE armed -> SUPERSEDED, not PASS", rows["Live mode remains disabled"] == "SUPERSEDED")
    d["tests"]["by_file"]["regression/test_lookahead"] = "FAIL"
    rows = dict((i, s) for i, s, _ in p6.checklist(d))
    check("one failing evidence file -> FAIL", rows["Fundamental availability dates enforced"] == "FAIL")
    del d["tests"]["by_file"]["regression/test_tnon"]
    rows = dict((i, s) for i, s, _ in p6.checklist(d))
    check("a missing test file -> MISSING, never PASS", rows["TNON regression test works"] == "MISSING")

    here = {os.path.relpath(os.path.join(dp, f), "tests")[:-3]
            for dp, _, fs in os.walk(os.path.join(ROOT, "tests")) for f in fs if f.startswith("test_")}
    missing = sorted(f for f in files if f not in here)
    check("every file the checklist cites exists", not missing, missing)

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
