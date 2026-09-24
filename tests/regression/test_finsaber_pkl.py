"""
Regression tests for finsaber_pkl.stream — the restricted, streaming pickle VM.

What is pinned: the streamed items equal a full load (protocols 3-5, batches
over pickle's 1000-item SETITEMS limit, strings shared across dates, long ones
included); an unknown global is refused rather than executed; and a reference
to an entry the LRU has already dropped raises instead of yielding a wrong
object. Plus the importer: invalid bars rejected, never repaired; rerun
idempotent.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import datetime
import io
import os
import pickle
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import finsaber
import finsaber_pkl as fp

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def sample(n=2500):
    long_shared = "".join(["z"] * 300)   # one object, referenced from every date
    out = {}
    for i in range(n):
        day = datetime.date(2000, 1, 1) + datetime.timedelta(days=i)
        out[day] = {
            "price": {"AAPL": {"open": 1.0 + i, "high": 3.0 + i, "low": 0.5, "close": 2.0 + i,
                               "adjusted_close": 1.9, "volume": 10 ** 10 + i}},
            "news": {"AAPL": [f"h{i}", "shared headline", long_shared]},
            "filing_k": {"AAPL": "k" * (i % 3) * 100},
            "filing_q": {},
        }
    return out


def main():
    data = sample()
    for proto in (3, 4, 5):
        got = dict(fp.stream(io.BytesIO(pickle.dumps(data, protocol=proto))))
        check(f"stream equals full load, protocol {proto}", got == data)

    try:
        list(fp.stream(io.BytesIO(pickle.dumps({1: print}, protocol=4))))
        check("disallowed global refused", False, "no error raised")
    except fp.PickleFormatError as e:
        check("disallowed global refused", "not allowed" in str(e), str(e))

    try:
        list(fp.stream(io.BytesIO(pickle.dumps(data, protocol=4)), long_budget=0))
        check("dropped long string raises", False, "no error raised")
    except fp.PickleFormatError as e:
        check("dropped long string raises", "dropped memo entry" in str(e), str(e))

    bad = sample(3)
    first = next(iter(bad))
    bad[first]["price"]["BAD"] = {"open": 1.0, "high": 0.5, "low": 1.0, "close": 1.0,
                                  "adjusted_close": 1.0, "volume": 1}
    with tempfile.TemporaryDirectory() as tmp:
        pkl = os.path.join(tmp, "t.pkl")
        with open(pkl, "wb") as f:
            pickle.dump(bad, f, protocol=4)
        conn = finsaber.connect(os.path.join(tmp, "f.db"))
        stats = fp.import_pkl(conn, pkl, "t")
        check("inverted bar rejected", stats["rejected_bars"] == 1, stats)
        n = conn.execute("SELECT COUNT(*) FROM finsaber_pkl_prices WHERE symbol='BAD'").fetchone()[0]
        check("rejected bar not stored", n == 0)
        again = fp.import_pkl(conn, pkl, "t")
        check("rerun after completion is a no-op", again.get("skipped") == "complete", again)
        rows = conn.execute("SELECT COUNT(*) FROM finsaber_news").fetchone()[0]
        check("news rows stored once", rows == 9, rows)
        conn.close()

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
