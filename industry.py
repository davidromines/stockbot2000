"""
Industry classification from SIC. Phase 9, item 25.

WHY THIS EXISTS
---------------
Item 27 wants valuation multiples compared within industry, and that is the
whole difference between "this bank looks cheap" and "this bank looks cheap
for a bank". A price/book of 0.9 is unremarkable for a regional lender and
extraordinary for a software company; ranked together, the screen simply
discovers that banks exist.

The data was already here and unused: every one of the 5,280 tickers in
`sec_filings` carries a SIC code, 436 distinct codes across the corpus.

WHY SIC, KNOWING WHAT IS WRONG WITH IT
----------------------------------------
SIC is the worst industry taxonomy still in common use. It was designed for
1930s manufacturing, it puts Amazon in retail and has no code that means
"internet platform", and the SEC lets each filer self-select. GICS is better
and costs money this project does not have.

The honest position is that SIC is a **peer-grouping heuristic, not a truth**.
It is used here only to form comparison sets, never as a feature, and a
valuation that depends on which bucket a company landed in is reporting the
bucket rather than the company.

POINT-IN-TIME, BECAUSE COMPANIES RECLASSIFY
---------------------------------------------
A company's SIC changes when its business changes, and `sic` is recorded per
FILING rather than per company. So the classification is looked up as of a
date, like everything else in this subsystem. Taking today's SIC and applying
it to 2011 would be the same substitution — "what we know now" for "what was
known then" — that the point-in-time requirement exists to forbid.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("industry")

# SIC division ranges, per the SEC's own office assignments. Coarse on purpose:
# a finer split makes peer sets too thin to rank within, and this database has
# a median of a few hundred names with fundamentals on any given date.
DIVISIONS = (
    (100, 999, "agriculture", "Agriculture, Forestry, Fishing"),
    (1000, 1499, "mining", "Mining"),
    (1500, 1799, "construction", "Construction"),
    (2000, 3999, "manufacturing", "Manufacturing"),
    (4000, 4999, "utilities_transport", "Transportation, Communications, Utilities"),
    (5000, 5199, "wholesale", "Wholesale Trade"),
    (5200, 5999, "retail", "Retail Trade"),
    (6000, 6799, "finance", "Finance, Insurance, Real Estate"),
    (7000, 8999, "services", "Services"),
    (9100, 9999, "public_admin", "Public Administration"),
)

# Groups where the standard multiples do not mean what they normally mean.
# Flagged rather than excluded: a screen must know that book value is the
# operating substance of a bank and nearly meaningless for a consultancy.
SPECIAL_ACCOUNTING = {
    "finance": "Book value is the operating substance of a lender and leverage "
               "is the business model, so P/B and debt ratios do not compare "
               "with non-financials. EV is not meaningful where debt is inventory.",
    "utilities_transport": "Rate-regulated returns and heavy capitalisation make "
                           "these look permanently cheap on earnings yield and "
                           "permanently indebted on leverage.",
}


def division_of(sic) -> tuple:
    """(key, label) for a SIC code, or ('unknown', ...) — never a guess."""
    try:
        s = int(sic)
    except (TypeError, ValueError):
        return "unknown", "Unclassified"
    for lo, hi, key, label in DIVISIONS:
        if lo <= s <= hi:
            return key, label
    return "unknown", "Unclassified"


def major_group(sic) -> str | None:
    """The 2-digit SIC major group — finer than a division, still not GICS."""
    try:
        return f"{int(sic) // 100:02d}"
    except (TypeError, ValueError):
        return None


def classify_as_of(conn, ticker: str, as_of: str) -> dict:
    """
    A ticker's industry as recorded by the newest filing TRADEABLE by `as_of`.

    Keyed on `first_tradeable` rather than `filed`, so a reclassification is
    visible exactly when the market could have seen it — and never before.
    """
    r = conn.execute("""SELECT sic, first_tradeable, form FROM sec_filings
        WHERE ticker=? AND sic IS NOT NULL AND first_tradeable IS NOT NULL
          AND first_tradeable <= ? ORDER BY first_tradeable DESC LIMIT 1""",
        (ticker, as_of)).fetchone()
    if not r:
        # Unknown is reported as unknown. The project rule is that a missing
        # measurement is never an average one, and an unclassified company
        # silently dropped into "manufacturing" would be ranked against peers
        # it has nothing to do with.
        return {"ticker": ticker, "sic": None, "division": "unknown",
                "label": "Unclassified", "major_group": None,
                "as_of_filing": None, "special_accounting": None}
    key, label = division_of(r["sic"])
    return {"ticker": ticker, "sic": r["sic"], "division": key, "label": label,
            "major_group": major_group(r["sic"]),
            "as_of_filing": r["first_tradeable"],
            "special_accounting": SPECIAL_ACCOUNTING.get(key)}


def peers(conn, ticker: str, as_of: str, level: str = "major_group") -> list:
    """
    The comparison set for a ticker on a date.

    Returns [] rather than a fallback group when the company is unclassified or
    the peer set is too thin. A rank against four peers is not a percentile, and
    silently widening to a coarser level to find company would compare a
    speciality lender against every insurer and REIT in the market.
    """
    me = classify_as_of(conn, ticker, as_of)
    if me["division"] == "unknown":
        return []
    col = "major_group" if level == "major_group" else "division"
    rows = conn.execute("""SELECT DISTINCT ticker, sic FROM sec_filings
        WHERE ticker IS NOT NULL AND sic IS NOT NULL
          AND first_tradeable IS NOT NULL AND first_tradeable <= ?""",
        (as_of,)).fetchall()
    out = []
    for r in rows:
        if r["ticker"] == ticker:
            continue
        cand = (major_group(r["sic"]) if col == "major_group"
                else division_of(r["sic"])[0])
        if cand and cand == me[col]:
            out.append(r["ticker"])
    return sorted(set(out))


def coverage(conn, as_of: str) -> dict:
    rows = conn.execute("""SELECT ticker, sic FROM (
        SELECT ticker, sic, ROW_NUMBER() OVER (PARTITION BY ticker
            ORDER BY first_tradeable DESC) rn
        FROM sec_filings WHERE ticker IS NOT NULL AND sic IS NOT NULL
          AND first_tradeable IS NOT NULL AND first_tradeable <= ?
        ) WHERE rn = 1""", (as_of,)).fetchall()
    by_div: dict = {}
    for r in rows:
        key, _ = division_of(r["sic"])
        by_div[key] = by_div.get(key, 0) + 1
    return {"as_of": as_of, "classified": len(rows), "by_division": by_div}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--as-of", default="2026-09-21")
    ap.add_argument("--ticker")
    ap.add_argument("--peers", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.ticker:
        c = classify_as_of(conn, a.ticker, a.as_of)
        print(f"\n  {a.ticker} as of {a.as_of}")
        print("  " + "-" * 62)
        print(f"  SIC            {c['sic']}")
        print(f"  division       {c['division']}  ({c['label']})")
        print(f"  major group    {c['major_group']}")
        print(f"  from filing    {c['as_of_filing']}")
        if c["special_accounting"]:
            print(f"\n  SPECIAL ACCOUNTING: {c['special_accounting']}")
        if a.peers:
            p = peers(conn, a.ticker, a.as_of)
            print(f"\n  {len(p)} peers in major group {c['major_group']}")
            print("   ", ", ".join(p[:24]) + (" ..." if len(p) > 24 else ""))
        conn.close(); return 0

    c = coverage(conn, a.as_of)
    print(f"\n  INDUSTRY COVERAGE as of {c['as_of']} — {c['classified']:,} tickers")
    print("  SIC is a peer-grouping heuristic, not a truth. It is used to form")
    print("  comparison sets and is never a feature.")
    print("  " + "-" * 62)
    for k, n in sorted(c["by_division"].items(), key=lambda kv: -kv[1]):
        flag = "  <- special accounting" if k in SPECIAL_ACCOUNTING else ""
        print(f"  {k:<24}{n:>6,}{flag}")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
