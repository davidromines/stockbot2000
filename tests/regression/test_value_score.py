"""
REGRESSION: a negative ratio is not a cheap one, and a 4-of-9 score is not a
9-of-9 score.

Two failures found by the engine's own explain() output, which is the argument
for the spec's demand that the system explain WHY each company ranks where it
does — neither was visible in the composite number.

1. **Negative price ratios ranked as cheapest.** AbbVie has negative equity, so
   its P/B is -73.26. Ranked "lower is cheaper" that put it at the 96th
   percentile for value: the cheapest company in its industry, by virtue of
   having no book value at all. `valuation.rank_within` already filtered these;
   the guard did not carry across, which is how one defect appears twice in one
   codebase.

2. **Incomparable denominators.** Most companies cannot be scored on all nine
   dimensions, and averaging whatever exists compares a 4-of-9 score directly
   against a 9-of-9 one. The missing dimensions are usually where thin
   disclosure and weak fundamentals travel together, so the thin company wins.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_value_score.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import value_score as vs

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- the percentile primitive ------------------------------------------------
peers = [1.0, 2.0, 3.0, 4.0, 5.0]
check("higher-is-better ranks a large value high",
      vs._percentile(peers, 5.0, True) == 80.0)
check("lower-is-better ranks a small value high",
      vs._percentile(peers, 1.0, False) == 80.0)
check("direction actually inverts",
      vs._percentile(peers, 5.0, True) != vs._percentile(peers, 5.0, False))

check("a thin peer set yields no percentile",
      vs._percentile([1.0, 2.0], 1.0, True) is None,
      "a percentile against two companies is not a percentile")
check("a missing value yields no percentile",
      vs._percentile(peers, None, True) is None)

# The defect itself.
with_neg = [-73.0, 5.0, 10.0, 15.0, 20.0, 25.0]
check("a NEGATIVE price ratio is not ranked at all",
      vs._percentile(with_neg, -73.0, False, positive_only=True) is None,
      "ranking it 'cheapest' is how negative equity became the best value")
check("negatives are also removed from the PEER SET",
      vs._percentile(with_neg, 5.0, False, positive_only=True) == 80.0,
      "leaving them in would shift every other company's percentile")
# Unguarded, the negative outranks every positive peer. 83.3 rather than 100
# because the value counts itself in the denominator — the exact figure does
# not matter, being near the top is the whole defect.
_unguarded = vs._percentile(with_neg, -73.0, False)
check("without the flag a negative ratio outranks every positive peer",
      _unguarded > 80.0, f"{_unguarded} — this is what ranked AbbVie cheapest")
check("zero is excluded too, not just negatives",
      vs._percentile([0.0, 5.0, 10.0, 15.0, 20.0, 25.0], 0.0, False,
                     positive_only=True) is None)

check("the positive-only set covers the price ratios",
      {"pb", "pe", "ps"} <= vs.POSITIVE_ONLY)
check("it covers leverage ratios, which invert on negative equity",
      {"debt_to_equity", "debt_to_ebitda"} <= vs.POSITIVE_ONLY)

# --- the nine dimensions and the weightings ---------------------------------
check("all nine dimensions from the spec are present",
      len(vs.DIMENSIONS) == 9, str(sorted(vs.DIMENSIONS)))
for d in ("value", "quality", "profitability", "growth", "balance_sheet",
          "cash_flow", "capital_alloc", "risk", "margin_safety"):
    check(f"dimension {d} is defined", d in vs.DIMENSIONS)

check("more than one weighting is registered", len(vs.WEIGHTINGS) >= 3)
check("a control weighting exists", "equal" in vs.WEIGHTINGS,
      "an elaborate formula that cannot beat equal weighting adds nothing")
check("the default IS the control", vs.DEFAULT_WEIGHTING == "equal",
      "the spec says the formula must not be finalised")
for name, w in vs.WEIGHTINGS.items():
    check(f"weighting '{name}' covers every dimension",
          set(w) == set(vs.DIMENSIONS), f"missing {set(vs.DIMENSIONS) - set(w)}")

# --- composite rules ---------------------------------------------------------
conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE sec_filings (adsh TEXT, ticker TEXT, form TEXT, period TEXT,
    filed TEXT, accepted TEXT, first_tradeable TEXT, prevrpt INT, sic TEXT);
CREATE TABLE sec_facts (adsh TEXT, tag TEXT, ddate TEXT, qtrs INT, value REAL);
CREATE TABLE prices (ticker TEXT, date TEXT, close REAL);
""")
conn.execute("INSERT INTO sec_filings VALUES ('a','OLD','10-K','20211231',"
             "'20221101','2022-11-01 08:00:00.0','2022-11-17',0,'3571')")
conn.execute("INSERT INTO sec_filings VALUES ('b','NEW','10-K','20251231',"
             "'20260201','2026-02-01 08:00:00.0','2026-02-02',0,'3571')")
conn.commit()

check("a filing from years ago is measured as old",
      vs._filing_age(conn, "OLD", "2026-09-21") > vs.STALE_FILING_DAYS,
      str(vs._filing_age(conn, "OLD", "2026-09-21")))
check("a recent filing is not stale",
      vs._filing_age(conn, "NEW", "2026-09-21") < vs.STALE_FILING_DAYS)
check("an unknown ticker has no filing age",
      vs._filing_age(conn, "NOPE", "2026-09-21") is None)
check("the staleness threshold is beyond an annual filer's normal cycle",
      vs.STALE_FILING_DAYS > 365,
      "an annual filer is late at 12 months, not absent")

check("the minimum dimension count is enforced at more than one",
      vs.MIN_DIMENSIONS >= 4, str(vs.MIN_DIMENSIONS))

# A synthetic row exercising the composite rules directly.
def row(dims):
    return {"dimensions": dims,
            "dimensions_scored": len([v for v in dims.values() if v is not None])}


thin = {d: (50.0 if i < 2 else None)
        for i, d in enumerate(vs.DIMENSIONS)}
full = {d: 50.0 for d in vs.DIMENSIONS}
check("a company scored on 2 dimensions is below the minimum",
      row(thin)["dimensions_scored"] < vs.MIN_DIMENSIONS)
check("a company scored on all nine is above it",
      row(full)["dimensions_scored"] >= vs.MIN_DIMENSIONS)

# --- explain() is traceable --------------------------------------------------
fake = {"ticker": "T1", "division": "manufacturing", "weighting": "equal",
        "composite": 61.0, "dimensions_scored": 9, "dimensions_total": 9,
        "filing_age_days": 100, "stale": False,
        "dimensions": {d: 61.0 for d in vs.DIMENSIONS},
        "detail": {"pb": {"raw": -73.26, "percentile": None,
                          "higher_is_better": False, "dimension": "value",
                          "excluded_negative": True},
                   "pe": {"raw": 12.0, "percentile": 40.0,
                          "higher_is_better": False, "dimension": "value",
                          "excluded_negative": False}}}
txt = vs.explain(fake)
check("explain shows the raw input behind each dimension", "pe=12.00" in txt)
check("explain shows the percentile, not just the raw value", "(40)" in txt)
check("explain says WHY a negative input was not ranked",
      "negative — not ranked" in txt,
      "a bare dash would read as 'not reported'")
check("explain states the dimension count", "9 of 9" in txt)
check("explain says percentiles are within industry, not market-wide",
      "WITHIN this industry" in txt)

stale_row = {**fake, "stale": True, "filing_age_days": 1400,
             "composite": None, "dimensions_scored": 2}
txt2 = vs.explain(stale_row)
check("a stale company is marked in its explanation", "STALE" in txt2)
check("a sub-minimum company gets NO composite, with the reason",
      "NO COMPOSITE" in txt2 and str(vs.MIN_DIMENSIONS) in txt2)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
