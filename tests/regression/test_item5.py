"""Regression test for item5.py against nine hand-labelled 10-K filings."""

import runtime  # noqa: F401

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import item5  # noqa: E402

FIXTURES = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "fixtures", "item5")

_failures = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + (("  " + detail) if detail else ""))
        _failures.append(name)


def main():
    with open(os.path.join(FIXTURES, "expected.json")) as fh:
        expected = json.load(fh)

    complete = 0
    for fname in sorted(expected):
        spec = expected[fname]
        with open(os.path.join(FIXTURES, fname)) as fh:
            text = fh.read()
        rows = item5.parse(text, fye_month=spec["fye_month"])
        got = {(r["year"], r["quarter"]): r for r in rows}

        # Precision: every parsed row must match an expected row exactly.
        wrong = []
        for key, r in got.items():
            exp = None
            for e in spec["rows"]:
                if (e["year"], e["quarter"]) == key:
                    exp = e
                    break
            if exp is None:
                wrong.append("%s not expected" % (key,))
            elif abs(r["high"] - exp["high"]) > 0.005 or \
                 abs(r["low"] - exp["low"]) > 0.005:
                wrong.append("%s got %s/%s want %s/%s" %
                             (key, r["high"], r["low"], exp["high"], exp["low"]))
        check("precision " + fname, not wrong, "; ".join(wrong))

        # Completeness: every expected row must be found.
        missing = []
        for e in spec["rows"]:
            key = (e["year"], e["quarter"])
            if key not in got:
                missing.append(str(key))
        if not missing:
            complete += 1
        check("complete " + fname, not missing, "missing " + ",".join(missing))

    check("at least 7 of 9 complete", complete >= 7, "got %d" % complete)

    check("quarter_end 2016Q4 fye8", item5.quarter_end(2016, 4, 8) == "2016-08-31")
    check("quarter_end 2009Q1 fye12", item5.quarter_end(2009, 1, 12) == "2009-03-31")
    check("parse empty text", item5.parse("") == [])
    check("parse no table", item5.parse("This filing has no price table at all.") == [])

    if _failures:
        print("\n%d FAILED" % len(_failures))
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
