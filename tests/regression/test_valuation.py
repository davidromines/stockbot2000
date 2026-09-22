"""
REGRESSION: a market cap divided by a QUARTER is not a P/E, and an EV ranking
over a quarter of the universe is not a valuation.

Two failures, both of which produced output that looked entirely reasonable.

1. **The flow-period mixup.** The newest tradeable filing is usually a 10-Q,
   which reports `qtrs=1` (one quarter) and `qtrs=2` (a half year) and no
   annual figure. Dividing a full market cap by a single quarter's earnings
   gave Apple a P/E of 168 against a real figure near 44 — exactly 4x.
   `value_metrics._pick` carries a docstring warning about this precise error
   and it happened anyway, which is why it is pinned here rather than trusted
   to a comment.

2. **Missingness that correlates with size.** EV multiples are computable for
   about a quarter of the universe, and that quarter has a median market cap
   of $2.20B against $0.88B for the rest. A market-wide EV ranking therefore
   sorts on size and disclosure quality while presenting itself as a
   valuation — the September "value ranks were size ranks" bug in a form that
   hides in missing data, where a correlation check would not find it.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_valuation.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import valuation as val

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE sec_facts (adsh TEXT, tag TEXT, ddate TEXT, qtrs INT, value REAL);
CREATE TABLE sec_filings (adsh TEXT, ticker TEXT, form TEXT, period TEXT,
    filed TEXT, accepted TEXT, first_tradeable TEXT, prevrpt INT, sic TEXT);
CREATE TABLE prices (ticker TEXT, date TEXT, close REAL);
""")


def fact(adsh, tag, qtrs, value):
    conn.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)",
                 (adsh, tag, "20251231", qtrs, value))


# An annual filing, then a later quarterly one — the real-world shape.
conn.execute("INSERT INTO sec_filings VALUES ('ann','AAA','10-K','20251231',"
             "'20260201','2026-02-01 08:00:00.0','2026-02-02',0,'3571')")
conn.execute("INSERT INTO sec_filings VALUES ('qtr','AAA','10-Q','20260331',"
             "'20260501','2026-05-01 08:00:00.0','2026-05-01',0,'3571')")
for tag, q, v in [("NetIncomeLoss", 4, 400.0), ("Revenues", 4, 4000.0),
                  ("OperatingIncomeLoss", 4, 500.0),
                  ("DepreciationAndAmortization", 4, 100.0),
                  ("NetCashProvidedByUsedInOperatingActivities", 4, 600.0),
                  ("PaymentsToAcquirePropertyPlantAndEquipment", 4, 200.0)]:
    fact("ann", tag, q, v)
# The quarter reports one-quarter and half-year figures and NO annual figure.
for tag, q, v in [("NetIncomeLoss", 1, 100.0), ("NetIncomeLoss", 2, 210.0),
                  ("Revenues", 1, 1000.0)]:
    fact("qtr", tag, q, v)
for adsh in ("ann", "qtr"):
    fact(adsh, "Assets", 0, 5000.0)
    fact(adsh, "StockholdersEquity", 0, 2000.0)
    fact(adsh, "CashAndCashEquivalentsAtCarryingValue", 0, 300.0)
    fact(adsh, "LongTermDebtNoncurrent", 0, 700.0)
    fact(adsh, "CommonStockSharesOutstanding", 0, 1000.0)
conn.execute("INSERT INTO prices VALUES ('AAA','2026-06-01',8.0)")
conn.commit()

# --- the flow-period rule ---------------------------------------------------
v, period, _ = val.annual_flow(conn, "AAA", "2026-06-01", "net_income")
check("annual_flow finds the FULL-YEAR figure, not the quarter",
      v == 400.0, f"{v} — 100.0 would be one quarter, 210.0 a half year")
check("it reports which period the figure came from", period == "20251231")

m = val.multiples(conn, "AAA", "2026-06-01")
cap = m["market_cap"]
check("market cap uses the price at the VALUATION date, not the filing date",
      cap == 8000.0, f"{cap}")
check("P/E divides by the ANNUAL figure",
      abs(m["multiples"]["pe"] - 20.0) < 1e-9,
      f"{m['multiples']['pe']} — dividing by the quarter would give 80, 4x too high")
check("P/S divides by annual revenue",
      abs(m["multiples"]["ps"] - 2.0) < 1e-9, str(m["multiples"]["ps"]))
check("EBITDA is built from annual operating income and D&A",
      abs(m["multiples"]["ev_to_ebitda"] - (8000 + 700 - 300) / 600.0) < 1e-9,
      str(m["multiples"]["ev_to_ebitda"]))
check("FCF yield subtracts capex from operating cash flow",
      abs(m["multiples"]["fcf_yield"] - 400.0 / 8000.0) < 1e-9,
      f"{m['multiples']['fcf_yield']} — 600-200 over cap")
check("balances still come from the newest filing, not the annual one",
      m["multiples"]["pb"] == 4.0)

# --- enterprise value refuses to impute -------------------------------------
check("EV needs debt", val.enterprise_value(100.0, None, 10.0) is None,
      "missing debt as zero understates EV and flatters every EV multiple")
check("EV needs cash", val.enterprise_value(100.0, 10.0, None) is None,
      "missing cash as zero manufactures leverage")
check("EV is cap + debt - cash", val.enterprise_value(100.0, 30.0, 10.0) == 120.0)

# --- market-wide EV rankings are refused ------------------------------------
for mult in val.EV_MULTIPLES:
    r = val.rank_universe(conn, mult, "2026-06-01")
    check(f"a market-wide {mult} ranking is REFUSED", r.get("refused") is True)
check("the refusal explains the size bias, not just 'low coverage'",
      "2.20B" in val.rank_universe(conn, "ev_to_ebitda", "2026-06-01")["reason"])

r = val.rank_universe(conn, "pb", "2026-06-01")
check("an equity multiple IS allowed market-wide", not r.get("refused"))
check("a universe ranking still reports its coverage", "coverage" in r)

# --- industry exclusions ----------------------------------------------------
for mult in val.EV_MULTIPLES:
    r = val.rank_within(conn, "finance", mult, "2026-06-01")
    check(f"{mult} is refused for finance", r.get("refused") is True)
check("the finance refusal explains WHY, not just that it is excluded",
      "debt is the business" in
      val.rank_within(conn, "finance", "ev_to_ebitda", "2026-06-01")["reason"])
check("a bank can still be ranked on an EQUITY multiple",
      not val.rank_within(conn, "finance", "pb", "2026-06-01").get("refused"))

r = val.rank_within(conn, "manufacturing", "pe", "2026-06-01")
check("a within-industry ranking reports coverage alongside the rank",
      "coverage" in r and "n_ranked" in r and "n_in_division" in r,
      "a percentile with no stated denominator reads as a universe rank")

# --- sign and direction -----------------------------------------------------
check("yields are ranked highest-first", val.HIGHER_IS_CHEAPER ==
      {"fcf_yield", "earnings_yield"},
      "ranking a yield cheapest-first would invert the whole result")
check("price ratios are NOT in the higher-is-cheaper set",
      "pe" not in val.HIGHER_IS_CHEAPER and "pb" not in val.HIGHER_IS_CHEAPER)

# A company with negative earnings must not sort to the top as "cheapest".
conn.execute("INSERT INTO sec_filings VALUES ('neg','NEG','10-K','20251231',"
             "'20260201','2026-02-01 08:00:00.0','2026-02-02',0,'3571')")
fact("neg", "NetIncomeLoss", 4, -500.0)
fact("neg", "CommonStockSharesOutstanding", 0, 1000.0)
fact("neg", "StockholdersEquity", 0, 1000.0)
conn.execute("INSERT INTO prices VALUES ('NEG','2026-06-01',5.0)")
conn.commit()
r = val.rank_within(conn, "manufacturing", "pe", "2026-06-01")
check("a NEGATIVE P/E is excluded, not ranked as infinitely cheap",
      all(x["ticker"] != "NEG" for x in r["ranked"]),
      "negative earnings is a different situation, not a bargain")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
