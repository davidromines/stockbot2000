"""
REGRESSION: seed ancestry must stay detectable, freshness must stay honest.

Both modules were written because the system could not previously tell the
difference between a discovery and an echo, or between fresh data and a check
that could not see it was stale.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_ancestry_and_freshness.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile
from datetime import date, timedelta

import ancestry
import freshness
import storage

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- ANCESTRY ---------------------------------------------------------------
fp = ancestry.seed_fingerprints()
check("seed shapes are indexed", len(fp["shapes"]) >= 15, f"{len(fp['shapes'])}")
check("the contaminating constant rsi_14=40 is in the index",
      ("rsi_14", 40.0) in fp["constants"],
      "if this vanishes the detector is testing nothing")

DISC = {"rsi_14", "macd", "roc_10", "sma_200"}

# A rule carrying the seed's discriminating constant is seed-descended.
seeded = {"entry": {"op": "lt", "args": [{"col": "rsi_14"}, {"const": 40.0}]}}
r = ancestry.classify(seeded, fp, discriminating=DISC)
check("a rule carrying rsi_14=40 is flagged SEED_LITERAL",
      r["origin"] == ancestry.SEED_LITERAL, r["origin"])
check("the flag carries checkable evidence",
      "rsi_14" in r["evidence"] and "momentum_pullback" in r["evidence"],
      r["evidence"])

# A learned threshold on the same column is not.
learned = {"entry": {"op": "lt", "args": [{"col": "rsi_14"}, {"const": 33.7}]}}
r = ancestry.classify(learned, fp, discriminating=DISC)
check("a LEARNED threshold on the same column is INDEPENDENT",
      r["origin"] == ancestry.INDEPENDENT, r["origin"])

# The false positive that made the first version useless: 0.5 on a binary column
# is the only sensible threshold, not an inherited choice.
binary = {"entry": {"op": "gt", "args": [{"col": "price_above_sma200"},
                                         {"const": 0.5}]}}
r = ancestry.classify(binary, fp, discriminating=DISC)
check("0.5 on a BINARY column is not treated as descent",
      r["origin"] == ancestry.INDEPENDENT,
      "flagging this marked 217 survivors contaminated for writing the only "
      "possible threshold")

# Lineage beats inference.
r = ancestry.classify(learned, fp, parent_origins=[ancestry.SEED_LITERAL],
                      discriminating=DISC)
check("a seeded ANCESTOR makes a descendant seed-descended",
      r["origin"] == ancestry.SEED_LINEAGE, r["origin"])

# Unclassified must not read as independent.
conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
ancestry.init(conn)
check("an UNCLASSIFIED strategy is NOT independent",
      not ancestry.is_independent(conn, "never-seen"),
      "absence of evidence is not evidence of independence — this assumption "
      "produced the retraction")
ancestry.record(conn, "s1", {"origin": ancestry.INDEPENDENT, "evidence": "t"})
check("a classified independent strategy reads as independent",
      ancestry.is_independent(conn, "s1"))

# --- FRESHNESS --------------------------------------------------------------
c2 = sqlite3.connect(tempfile.mktemp(suffix=".db"))
c2.row_factory = sqlite3.Row
storage.init_db(c2)
freshness.init(c2)
today = date(2026, 9, 21)
for i in range(30, 2, -1):
    d = today - timedelta(days=i)
    if d.weekday() < 5:
        c2.execute("INSERT INTO prices (ticker,date,open,high,low,close,volume,source)"
                   " VALUES ('SPY',?,1,1,1,1,1,'t')", (d.isoformat(),))
c2.commit()
cfg = {"backfill": {"reference_tickers": ["SPY"]}, "freshness": {"max_lag_sessions": 1}}

f = freshness.check(c2, cfg, expected="2026-09-18")
check("data current to the expected session is OK", f.ok, f.reason)

f = freshness.check(c2, cfg, expected="2026-09-21")
check("data three days behind is reported STALE", not f.ok, f.reason)
check("lag_sessions is NOT zero when we are behind",
      (f.lag_sessions or 0) > 0,
      "counting sessions from our own stale table returns 0 — the same "
      "circularity as the original staleness bug")
check("the counting METHOD is recorded", bool(f.lag_method), f.lag_method)

f = freshness.check(c2, cfg, expected=None)
check("an UNKNOWN market session is treated as STALE, not as fine", not f.ok,
      f.reason)

check("freshness.main returns non-zero on stale so a stage FAILS",
      "return 0 if f.ok else 1" in open("freshness.py").read())

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
