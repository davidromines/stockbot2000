"""
REGRESSION: "not reported" is never zero, and capex is subtracted.

A company that did not disclose R&D is not a company that spent nothing on it.
This project has already been bitten twice by treating an unknown as an average
or a zero — TNON cleared the size floor as "unmeasured", and an unknown
liquidity would have done the same. So every figure here is either a number or
None, and any ratio with a missing input is None rather than a filled-looking
column.

The sign convention is the other trap. Capex is reported as a POSITIVE outflow
in the cash-flow statement. Adding it to operating cash flow instead of
subtracting it turns the most capital-hungry companies in the database into its
best free-cash-flow generators — a ranking that would look plausible and be
exactly inverted.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_statements.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import statements as st

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
CREATE TABLE prices (ticker TEXT, date TEXT);
""")


def fact(adsh, tag, qtrs, value):
    conn.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)",
                 (adsh, tag, "20251231", qtrs, value))


# A complete-ish filer.
for tag, q, v in [("Revenues", 4, 1000.0), ("CostOfRevenue", 4, 600.0),
                  ("OperatingIncomeLoss", 4, 250.0), ("NetIncomeLoss", 4, 200.0),
                  ("DepreciationAndAmortization", 4, 50.0),
                  ("NetCashProvidedByUsedInOperatingActivities", 4, 300.0),
                  ("PaymentsToAcquirePropertyPlantAndEquipment", 4, 120.0),
                  ("Assets", 0, 2000.0), ("StockholdersEquity", 0, 800.0),
                  ("CashAndCashEquivalentsAtCarryingValue", 0, 150.0),
                  ("LongTermDebtNoncurrent", 0, 400.0),
                  ("ShortTermBorrowings", 0, 100.0),
                  ("Goodwill", 0, 300.0), ("AssetsCurrent", 0, 700.0),
                  ("LiabilitiesCurrent", 0, 400.0)]:
    fact("f1", tag, q, v)
conn.commit()

s = st.statement(conn, "f1")

# --- levels and construction ------------------------------------------------
check("revenue is read", s["revenue"] == 1000.0)
check("gross profit is derived when not tagged", s["gross_profit"] == 400.0,
      f"{s['gross_profit']} — revenue minus cost of revenue")
check("EBITDA is constructed from operating income plus D&A",
      s["ebitda"] == 300.0, f"{s['ebitda']} — it is never tagged directly")
check("total debt sums long and short term", s["debt"] == 500.0, str(s["debt"]))
check("net debt subtracts cash", s["net_debt"] == 350.0, str(s["net_debt"]))
check("tangible book value removes goodwill",
      s["tangible_book_value"] == 500.0, str(s["tangible_book_value"]))
check("working capital is current assets minus current liabilities",
      s["working_capital"] == 300.0)

# --- the sign trap ----------------------------------------------------------
check("free cash flow SUBTRACTS capex", s["free_cash_flow"] == 180.0,
      f"{s['free_cash_flow']} — adding it would give 420 and invert the ranking")
check("FCF is below operating cash flow for a capital-spending company",
      s["free_cash_flow"] < s["operating_cash_flow"])

fact("f2", "NetCashProvidedByUsedInOperatingActivities", 4, 300.0)
fact("f2", "PaymentsToAcquirePropertyPlantAndEquipment", 4, -120.0)
conn.commit()
check("a NEGATIVE capex sign still reduces FCF",
      st.statement(conn, "f2")["free_cash_flow"] == 180.0,
      "filers disagree on the sign; abs() makes the direction unambiguous")

# --- absence is never zero --------------------------------------------------
check("an undisclosed R&D is None, not 0", s["rd"] is None)
check("a ratio with a missing input is None, not 0", s["rd_intensity"] is None,
      "a zero would rank a non-discloser as spending nothing on R&D")
check("an empty filing yields None everywhere, not zeros",
      all(v is None for k, v in st.statement(conn, "nothing").items()
          if k != "adsh"))
check("division by zero gives None", st._div(5, 0) is None)
check("division by a missing value gives None", st._div(5, None) is None)
check("subtraction with a missing operand gives None", st._sub(5, None) is None)

# Net debt must not be manufactured out of missing cash.
check("missing cash does NOT default to zero in net debt",
      st._net_debt(500.0, None) is None,
      "defaulting cash to zero would invent leverage a company does not have")
check("missing debt gives no net debt figure", st._net_debt(None, 100.0) is None)

# --- point-in-time selection ------------------------------------------------
conn.execute("INSERT INTO sec_filings VALUES ('f1','AAA','10-K','20251231',"
             "'20260115','2026-01-15 08:00:00.0','2026-01-15',0,'3571')")
conn.execute("INSERT INTO sec_filings VALUES ('f2','AAA','10-Q','20260331',"
             "'20260501','2026-05-01 08:00:00.0','2026-05-01',0,'3571')")
conn.commit()
a = st.analyse(conn, "AAA", "2026-03-01")
check("the newest filing TRADEABLE by the date is chosen",
      a["filing"]["adsh"] == "f1", str(a.get("filing", {}).get("adsh")))
check("a later date sees the later filing",
      st.analyse(conn, "AAA", "2026-06-01")["filing"]["adsh"] == "f2")
check("a date before any filing reports unavailable, not empty numbers",
      st.analyse(conn, "AAA", "2020-01-01")["available"] is False)
check("an unknown ticker reports unavailable",
      st.analyse(conn, "NOPE", "2026-06-01")["available"] is False)

check("the industry is attached to the analysis",
      a["industry"]["division"] == "manufacturing", str(a["industry"]))
check("a manufacturer carries no special-accounting caveat",
      a.get("caveat") is None)

conn.execute("UPDATE sec_filings SET sic='6021' WHERE adsh='f1'")
conn.commit()
bank = st.analyse(conn, "AAA", "2026-03-01")
check("a financial DOES carry a special-accounting caveat",
      bool(bank.get("caveat")), "book value means something different for a lender")
check("the caveat warns rather than silently adjusting the numbers",
      bank["statement"]["book_value"] == s["book_value"],
      "quietly normalising a bank's ratios would hide what a reader most needs")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
