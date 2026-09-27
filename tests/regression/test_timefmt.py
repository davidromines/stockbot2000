"""timefmt: stored UTC shown in Pacific, across the daylight-saving change; bare
dates and non-times are never shifted."""
import os
import sys
from datetime import datetime, timezone

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import timefmt as t

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    check("summer: UTC -> PDT", t.pt("2026-09-28T13:34:27+00:00") == "Mon 09-28 06:34 PDT", t.pt("2026-09-28T13:34:27+00:00"))
    check("winter: UTC -> PST", t.pt("2026-12-01T20:00:00Z") == "Tue 12-01 12:00 PST", t.pt("2026-12-01T20:00:00Z"))
    check("a naive stored time is UTC", t.pt("2026-09-22 07:00:46") == "Tue 09-22 00:00 PDT", t.pt("2026-09-22 07:00:46"))
    check("datetime input", t.pt_time(datetime(2026, 9, 28, 20, 0, tzinfo=timezone.utc)) == "13:00 PDT")
    check("a bare date is not shifted", t.pt("2026-09-24") == "2026-09-24")
    check("missing -> n/a; junk unchanged", t.pt(None) == "n/a" and t.pt("soon") == "soon")
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
