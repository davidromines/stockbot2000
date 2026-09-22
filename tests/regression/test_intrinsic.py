"""
REGRESSION: a DCF must announce how much of itself is assumption.

Everything else in this project measures what already happened. A DCF
forecasts, and it will produce a confident-looking number from inputs nobody
can validate. This project's whole record is of confident numbers that were
artifacts, so the guards are built in rather than offered:

  * the terminal-value share is reported every time, and flagged above 75% —
    at that point you are valuing a perpetuity assumption with a decade of
    detail stapled to the front;
  * sensitivity is returned with every valuation, never on request, because a
    point estimate without its range IS the artifact;
  * erratic history is flagged — Ford's free cash flow swings 39x its own
    average, so the tidy -0.3% CAGR fitted to it describes the endpoints and
    nothing in between;
  * refusal is expected. A DCF on negative or sign-changing cash flow values
    the assumption that it turns around, not the business.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_intrinsic.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import intrinsic as iv

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


def company(ticker, ocf_by_year, capex=100.0, sic="3571", shares=1000.0,
            cash=500.0, debt=200.0):
    for i, (yr, ocf) in enumerate(ocf_by_year):
        adsh = f"{ticker}{yr}"
        conn.execute("INSERT INTO sec_filings VALUES (?,?,?,?,?,?,?,?,?)",
                     (adsh, ticker, "10-K", f"{yr}1231", f"{yr+1}0201",
                      f"{yr+1}-02-01 08:00:00.0", f"{yr+1}-02-02", 0, sic))
        for tag, q, v in [("NetCashProvidedByUsedInOperatingActivities", 4, ocf),
                          ("PaymentsToAcquirePropertyPlantAndEquipment", 4, capex),
                          ("NetIncomeLoss", 4, ocf * 0.6),
                          ("Revenues", 4, ocf * 4)]:
            conn.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)",
                         (adsh, tag, f"{yr}1231", q, v))
        for tag, v in [("CommonStockSharesOutstanding", shares),
                       ("StockholdersEquity", 2000.0),
                       ("CashAndCashEquivalentsAtCarryingValue", cash),
                       ("LongTermDebtNoncurrent", debt), ("Assets", 5000.0)]:
            conn.execute("INSERT INTO sec_facts VALUES (?,?,?,?,?)",
                         (adsh, tag, f"{yr}1231", 0, v))
    conn.execute("INSERT INTO prices VALUES (?,?,?)", (ticker, "2026-06-01", 10.0))
    conn.commit()


AS_OF = "2026-06-01"
company("GOOD", [(y, 1000.0 * (1.05 ** i)) for i, y in enumerate(range(2016, 2026))])
company("NEG", [(y, -500.0) for y in range(2016, 2026)])
company("FLIP", [(y, 1000.0 if y % 2 else -800.0) for y in range(2016, 2026)])
company("SHORT", [(y, 1000.0) for y in range(2024, 2026)])
company("NODEBT", [(y, 1000.0 * (1.05 ** i)) for i, y in enumerate(range(2016, 2026))],
        cash=None if False else 500.0, debt=200.0)

# --- history -----------------------------------------------------------------
h = iv.annual_history(conn, "GOOD", AS_OF, "ocf")
check("annual history is oldest-first", h == sorted(h))
check("ten years of history are found", len(h) == 10, str(len(h)))
check("history is deduplicated by period", len({p for p, _ in h}) == len(h))

check("CAGR across a sign change is refused",
      iv._cagr([("a", -100.0), ("b", 100.0)]) is None,
      "a company going from -100 to +100 has no growth rate, just a turnaround")
check("CAGR on a clean series is right",
      abs(iv._cagr([("a", 100.0), ("b", 121.0)]) - 0.21) < 1e-9)

# --- refusals ----------------------------------------------------------------
r = iv.dcf(conn, "NEG", AS_OF)
check("negative free cash flow is REFUSED", r["refused"])
check("the refusal says what a DCF on it would actually value",
      "turns around" in r["reason"], r["reason"])

r = iv.dcf(conn, "FLIP", AS_OF)
check("sign-changing cash flow is REFUSED", r["refused"], r.get("reason", ""))

r = iv.dcf(conn, "SHORT", AS_OF)
check("too little history is REFUSED", r["refused"])
check("the refusal names how many years are needed",
      str(iv.MIN_HISTORY_YEARS) in r["reason"], r["reason"])

r = iv.dcf(conn, "GOOD", AS_OF, discount=0.03, terminal_growth=0.05)
check("terminal growth above the discount rate is REFUSED", r["refused"],
      "the perpetuity is infinite and the model has no answer")

# --- a working valuation, and its health reporting --------------------------
d = iv.dcf(conn, "GOOD", AS_OF)
check("a healthy company IS valued", not d["refused"], d.get("reason", ""))
check("the terminal share is always reported", d["terminal_share"] is not None)
check("the terminal share is a fraction of the total",
      0 < d["terminal_share"] < 1, str(d["terminal_share"]))
check("every assumption is returned with the value",
      {"discount_rate", "growth", "terminal_growth", "years", "base_fcf",
       "history_years"} <= set(d["assumptions"]))
check("the equity bridge subtracts debt and adds cash",
      abs(d["equity_value"] - (d["enterprise_value"] - 200.0 + 500.0)) < 1e-6)

hi = iv.dcf(conn, "GOOD", AS_OF, terminal_growth=0.039, discount=0.04001)
check("a long perpetuity pushes the terminal share up",
      hi["refused"] or hi["terminal_share"] > d["terminal_share"])

# growth capping
fast = iv.dcf(conn, "GOOD", AS_OF, growth=0.80)
check("an implausible growth rate is capped",
      fast["assumptions"]["growth"] == iv.MAX_SANE_GROWTH)
check("the cap is REPORTED, not applied silently",
      fast["assumptions"]["growth_capped"] is True)

# --- sensitivity is mandatory and informative -------------------------------
s = iv.sensitivity(conn, "GOOD", AS_OF)
check("sensitivity returns a grid", s["usable"] and len(s["grid"]) == 5)
check("the grid spans discount rates", len(s["grid"][0]["values"]) == 5)
check("a spread ratio is reported", s["spread_ratio"] is not None)
check("the spread is greater than 1 for any real model", s["spread_ratio"] > 1.0)
check("low and high bracket the median", s["low"] <= s["median"] <= s["high"])

t = iv.triangulate(conn, "GOOD", AS_OF)
check("triangulate always attaches sensitivity when the DCF ran",
      t["sensitivity"] is not None,
      "a point estimate without its range is the artifact this guards against")
check("triangulate runs every method", set(t["methods"]) ==
      {"dcf", "earnings", "fcf_perpetuity", "asset"})
check("the spread between methods is reported when more than one works",
      t["n_methods"] < 2 or t.get("method_spread") is not None)

# --- stability --------------------------------------------------------------
# Swings of three orders of magnitude, closer to what real cyclicals produce:
# Ford's measured variability is 38.8, far above the 2.0 threshold.
_wild = [20.0, 4000.0, 30.0, 6000.0, 25.0, 5000.0, 40.0, 7000.0, 35.0, 8000.0]
company("WILD", list(zip(range(2016, 2026), _wild)), capex=10.0)
w = iv.dcf(conn, "WILD", AS_OF)
if not w["refused"]:
    check("erratic cash flow raises the stability alarm",
          w["stability_alarm"] is True,
          f"variability {w['fcf_stability']}")
else:
    check("erratic cash flow is either refused or flagged", True)
check("a steady company does NOT raise the stability alarm",
      d["stability_alarm"] is False, str(d["fcf_stability"]))

# --- nothing is defaulted ---------------------------------------------------
import inspect
src = inspect.getsource(iv)
check("the module never substitutes a default discount rate mid-calculation",
      src.count("or DISCOUNT_RATE") == 0)
check("refusals carry a reason every time",
      all("reason" in m for m in
          [iv.dcf(conn, "NEG", AS_OF), iv.dcf(conn, "SHORT", AS_OF)]))
check("the output says these are not recommendations",
      "not" in iv.render(t).lower() and "recommendation" in iv.render(t).lower())

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
