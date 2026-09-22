"""
Industry-aware valuation multiples. Phase 9, item 27.

THE CONSTRAINT THAT SHAPES THIS ENTIRE MODULE
-----------------------------------------------
The spec asks for EV/EBITDA, EV/EBIT and EV/Sales alongside the equity
multiples. Measured on this database over 600 companies:

    P/B          98.3%        EV/Sales     31.2%
    P/E          93.0%        EV/EBIT      29.3%
    P/S          73.7%        EV/EBITDA    24.8%

Low coverage alone would be survivable. The problem is that the covered quarter
is **not a random sample**:

    EV/EBITDA computable : 131 companies, median market cap  $2.20B
    not computable       : 314 companies, median market cap  $0.88B

and coverage runs from 7.5% of financials to 53.8% of wholesalers. Companies
that tag their debt properly are systematically the larger ones.

So a market-wide EV/EBITDA ranking on this data would rank a large-cap-tilted,
industry-skewed subset **while presenting itself as a valuation of the
universe**. That is structurally the September finding that value ranks were
size ranks in disguise, in a form that hides in MISSINGNESS rather than in
correlation — so a Spearman check against size would not have caught it.

FOUR RULES, ENFORCED RATHER THAN INTENDED
-------------------------------------------
1. **No market-wide EV ranking.** `rank_within` requires an industry, and
   `rank_universe` refuses EV multiples outright rather than returning a number
   somebody would quote.
2. **Coverage travels with every rank.** A percentile computed over 25% of an
   industry is labelled as such. A rank whose coverage is unstated will be read
   as a universe rank, because that is what a percentile normally means.
3. **Equity multiples carry the weight**, since they clear 74-98%.
4. **Missing debt is never imputed.** Zero would show 314 smaller companies as
   unlevered with an artificially low enterprise value — the most flattering
   possible error, applied to the companies we know least about.

MARKET CAP IS POINT-IN-TIME ON BOTH LEGS
------------------------------------------
Shares come from the newest filing tradeable by the valuation date; the price
is the close on that date. Not the filing-date price, which would value a
company at what it was worth three months ago, and never a current share count
against an old balance sheet — dilution is precisely what distressed companies
do in between.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import industry
import statements as stm
import storage
import value_metrics as vm
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("valuation")

# Multiples that need enterprise value, and therefore debt. Named explicitly
# because the coverage rules below key off this set rather than off a guess.
EV_MULTIPLES = ("ev_to_sales", "ev_to_ebitda", "ev_to_ebit")
EQUITY_MULTIPLES = ("pe", "pb", "ps", "p_tangible_book", "fcf_yield",
                    "earnings_yield")
ALL_MULTIPLES = EQUITY_MULTIPLES + EV_MULTIPLES

# Lower is cheaper for a price ratio; higher is cheaper for a yield. Getting
# this backwards would rank the most expensive companies as the best value and
# the output would look entirely reasonable.
HIGHER_IS_CHEAPER = {"fcf_yield", "earnings_yield"}

# Multiples that do not mean what they usually mean for a given industry. These
# are EXCLUDED from that industry's rankings rather than quietly included: for a
# lender debt is inventory, so enterprise value is not a meaningful quantity and
# a bank ranked on EV/EBITDA is being ranked on an artefact.
INDUSTRY_EXCLUSIONS = {
    "finance": set(EV_MULTIPLES),
    "utilities_transport": {"ev_to_ebitda"},
}


def _div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def market_cap(conn, ticker: str, as_of: str):
    """
    Shares from the newest tradeable filing, priced at `as_of`.

    Both legs point-in-time. Using the filing-date price would value a company
    at what it was worth when it last reported, which for a quarterly filer is
    up to three months stale.
    """
    r = conn.execute("""SELECT adsh FROM sec_filings WHERE ticker=?
        AND first_tradeable IS NOT NULL AND first_tradeable <= ?
        ORDER BY first_tradeable DESC LIMIT 1""", (ticker, as_of)).fetchone()
    if not r:
        return None, None
    facts = vm._facts_for(conn, r["adsh"])
    shares = stm._pick(facts, "shares", stm.BALANCE) or stm._pick(facts, "shares")
    if not shares or shares <= 0:
        return None, None
    p = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? "
                     "AND close>0 ORDER BY date DESC LIMIT 1",
                     (ticker, as_of)).fetchone()
    if not p:
        return None, None
    return float(p[0]) * float(shares), float(shares)


def enterprise_value(cap, debt, cash):
    """
    EV = market cap + debt - cash. None if debt or cash is absent.

    Deliberately NOT defaulting either leg. Missing debt treated as zero
    understates EV and makes a company look cheap on every EV multiple; missing
    cash overstates it. Both errors are invisible in the output.
    """
    if cap is None or debt is None or cash is None:
        return None
    return cap + debt - cash


ANNUAL = (4,)


def annual_flow(conn, ticker: str, as_of: str, key: str, max_back: int = 8):
    """
    The newest FULL-YEAR value of a flow, searching back through filings.

    A price multiple divides a market capitalisation by an annual flow. The
    newest tradeable filing is usually a 10-Q, which reports `qtrs=1` (one
    quarter) and `qtrs=2` (a half year) and no annual figure at all. Taking
    whichever flow was present produced a P/E of 168 for Apple against a real
    figure near 42 — exactly 4x, because a full market cap was divided by a
    single quarter's earnings. `value_metrics._pick` carries a docstring
    warning about precisely this, and it still happened.

    Returns (value, period, adsh) or (None, None, None). It is the LAST
    REPORTED FULL YEAR, not a trailing twelve months: assembling TTM needs
    period arithmetic across filings, and a lagging-but-correct denominator is
    worth more than a current-looking wrong one.
    """
    rows = conn.execute("""SELECT adsh, period, form FROM sec_filings
        WHERE ticker=? AND first_tradeable IS NOT NULL AND first_tradeable <= ?
        ORDER BY first_tradeable DESC LIMIT ?""",
        (ticker, as_of, int(max_back))).fetchall()
    for r in rows:
        facts = vm._facts_for(conn, r["adsh"])
        v = stm._pick(facts, key, ANNUAL)
        if v is not None:
            return v, r["period"], r["adsh"]
    return None, None, None


def multiples(conn, ticker: str, as_of: str) -> dict:
    a = stm.analyse(conn, ticker, as_of)
    if not a.get("available"):
        return {"ticker": ticker, "as_of": as_of, "available": False,
                "reason": a.get("reason")}
    s = a["statement"]
    cap, shares = market_cap(conn, ticker, as_of)
    ev = enterprise_value(cap, s.get("debt"), s.get("cash"))

    # Flows come from the newest FULL-YEAR figure, never from the statement's
    # own flow, which in a 10-Q is a single quarter. Balances (book value,
    # tangible book) are point-in-time and come straight from the statement.
    net_income, ni_period, _ = annual_flow(conn, ticker, as_of, "net_income")
    revenue, _, _ = annual_flow(conn, ticker, as_of, "revenue")
    op_income, _, _ = annual_flow(conn, ticker, as_of, "op_income")
    dep, _, _ = annual_flow(conn, ticker, as_of, "dep_amort")
    ocf, _, _ = annual_flow(conn, ticker, as_of, "ocf")
    capex, _, _ = annual_flow(conn, ticker, as_of, "capex")
    ebitda = None if (op_income is None or dep is None) else op_income + dep
    fcf = None if (ocf is None or capex is None) else ocf - abs(capex)

    m = {
        "pe": _div(cap, net_income),
        "pb": _div(cap, s.get("book_value")),
        "ps": _div(cap, revenue),
        "p_tangible_book": _div(cap, s.get("tangible_book_value")),
        "fcf_yield": _div(fcf, cap),
        "earnings_yield": _div(net_income, cap),
        "ev_to_sales": _div(ev, revenue),
        "ev_to_ebitda": _div(ev, ebitda),
        "ev_to_ebit": _div(ev, op_income),
    }
    ind = a["industry"]
    excluded = INDUSTRY_EXCLUSIONS.get(ind["division"], set())
    return {"ticker": ticker, "as_of": as_of, "available": True,
            "market_cap": cap, "shares": shares, "enterprise_value": ev,
            "industry": ind, "multiples": m,
            "annual_period": ni_period,
            "excluded_for_industry": sorted(excluded),
            "caveat": a.get("caveat"), "filing": a["filing"]}


def _panel(conn, as_of: str, division: str | None, limit: int) -> list:
    q = ["SELECT DISTINCT ticker FROM sec_filings WHERE ticker IS NOT NULL",
         "AND first_tradeable IS NOT NULL AND first_tradeable <= ?"]
    rows = [r[0] for r in conn.execute(" ".join(q) + f" ORDER BY ticker LIMIT {int(limit)}",
                                       (as_of,))]
    out = []
    for t in rows:
        v = multiples(conn, t, as_of)
        if not v.get("available"):
            continue
        if division and v["industry"]["division"] != division:
            continue
        out.append(v)
    return out


def rank_within(conn, division: str, multiple: str, as_of: str,
                limit: int = 600) -> dict:
    """
    Percentile rank of one multiple, WITHIN one industry, among companies where
    it is actually computable.

    The denominator is stated in the result. A percentile normally implies a
    complete population, so a rank over a quarter of an industry that does not
    say so will be read as something it is not.
    """
    if multiple not in ALL_MULTIPLES:
        raise SystemExit(f"unknown multiple {multiple!r}; have {list(ALL_MULTIPLES)}")
    if multiple in INDUSTRY_EXCLUSIONS.get(division, set()):
        return {"division": division, "multiple": multiple, "as_of": as_of,
                "refused": True,
                "reason": (f"{multiple} is excluded for {division}: enterprise "
                           f"value is not a meaningful quantity where debt is "
                           f"the business, so the ranking would be of an "
                           f"artefact")}
    panel = _panel(conn, as_of, division, limit)
    vals = [(v["ticker"], v["multiples"][multiple]) for v in panel
            if v["multiples"].get(multiple) is not None]
    # A negative price ratio means negative earnings or negative book value.
    # It is not "infinitely cheap" — it is a different situation entirely, and
    # leaving it in sorts the most distressed companies to the top.
    if multiple not in HIGHER_IS_CHEAPER:
        vals = [(t, x) for t, x in vals if x > 0]
    reverse = multiple in HIGHER_IS_CHEAPER
    vals.sort(key=lambda kv: kv[1], reverse=reverse)
    n = len(vals)
    ranked = [{"ticker": t, "value": x, "percentile": (i + 1) / n}
              for i, (t, x) in enumerate(vals)] if n else []
    return {"division": division, "multiple": multiple, "as_of": as_of,
            "refused": False, "ranked": ranked,
            "n_ranked": n, "n_in_division": len(panel),
            "coverage": (n / len(panel)) if panel else 0.0,
            "higher_is_cheaper": reverse}


def rank_universe(conn, multiple: str, as_of: str, limit: int = 600) -> dict:
    """
    Market-wide ranking — permitted for equity multiples ONLY.

    An EV multiple is refused rather than returned with a warning. A warning
    beside a number gets separated from it the moment anyone quotes the number,
    and this particular number would be a large-cap-tilted subset wearing the
    label of a universe.
    """
    if multiple in EV_MULTIPLES:
        return {"multiple": multiple, "refused": True,
                "reason": (f"{multiple} is computable for about a quarter of "
                           f"the universe, and that quarter has a median market "
                           f"cap of $2.20B against $0.88B for the rest. A "
                           f"market-wide ranking would sort on size and "
                           f"disclosure quality while looking like a valuation. "
                           f"Use rank_within(division, ...) instead.")}
    if multiple not in ALL_MULTIPLES:
        raise SystemExit(f"unknown multiple {multiple!r}")
    panel = _panel(conn, as_of, None, limit)
    vals = [(v["ticker"], v["multiples"][multiple]) for v in panel
            if v["multiples"].get(multiple) is not None]
    if multiple not in HIGHER_IS_CHEAPER:
        vals = [(t, x) for t, x in vals if x > 0]
    vals.sort(key=lambda kv: kv[1], reverse=multiple in HIGHER_IS_CHEAPER)
    n = len(vals)
    return {"multiple": multiple, "as_of": as_of, "refused": False,
            "ranked": [{"ticker": t, "value": x, "percentile": (i + 1) / n}
                       for i, (t, x) in enumerate(vals)],
            "n_ranked": n, "n_universe": len(panel),
            "coverage": (n / len(panel)) if panel else 0.0}


def coverage_report(conn, as_of: str, limit: int = 600) -> dict:
    panel = _panel(conn, as_of, None, limit)
    out: dict = {}
    for mult in ALL_MULTIPLES:
        by_div: dict = {}
        for v in panel:
            d = v["industry"]["division"]
            ok = v["multiples"].get(mult) is not None
            a, b = by_div.get(d, (0, 0))
            by_div[d] = (a + (1 if ok else 0), b + 1)
        tot_ok = sum(a for a, _ in by_div.values())
        out[mult] = {"total": tot_ok, "n": len(panel),
                     "share": tot_ok / len(panel) if panel else 0.0,
                     "by_division": by_div}
    return {"as_of": as_of, "panel": len(panel), "multiples": out}


def _fmt(v):
    return "—" if v is None else (f"{v:,.2f}" if abs(v) < 1e4 else f"{v:,.0f}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker")
    ap.add_argument("--as-of", default="2026-09-21")
    ap.add_argument("--rank", metavar="MULTIPLE")
    ap.add_argument("--division")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--limit", type=int, default=600)
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.ticker:
        v = multiples(conn, a.ticker, a.as_of)
        if not v.get("available"):
            print(f"\n  {a.ticker}: {v['reason']}\n"); conn.close(); return 1
        print(f"\n  {a.ticker} — valuation as of {a.as_of}")
        print(f"  {v['industry']['label']} (SIC {v['industry']['sic']})")
        print(f"  market cap {_fmt(v['market_cap'])}   "
              f"enterprise value {_fmt(v['enterprise_value'])}")
        print(f"  flows from the last full year reported: "
              f"{v.get('annual_period') or 'none found'}")
        print("  " + "-" * 56)
        for k in ALL_MULTIPLES:
            mark = ""
            if k in v["excluded_for_industry"]:
                mark = "  (excluded for this industry)"
            print(f"  {k:<20}{_fmt(v['multiples'][k]):>16}{mark}")
        if v.get("caveat"):
            print(f"\n  INDUSTRY CAVEAT: {v['caveat']}")
        print()
        conn.close(); return 0

    if a.rank:
        if a.division:
            r = rank_within(conn, a.division, a.rank, a.as_of, a.limit)
            if r.get("refused"):
                print(f"\n  REFUSED: {r['reason']}\n"); conn.close(); return 1
            print(f"\n  {r['multiple']} within {r['division']} as of {r['as_of']}")
            print(f"  ranked {r['n_ranked']} of {r['n_in_division']} companies "
                  f"in this division — COVERAGE {r['coverage']:.1%}")
            print(f"  {'cheapest first' if not r['higher_is_cheaper'] else 'highest yield first'}")
            print("  " + "-" * 56)
            for x in r["ranked"][:12]:
                print(f"  {x['ticker']:<8}{_fmt(x['value']):>14}"
                      f"{x['percentile']:>10.1%}")
            print(f"\n  A percentile here is within this division and among the")
            print(f"  {r['coverage']:.0%} where the multiple is computable — not a")
            print(f"  universe rank.")
        else:
            r = rank_universe(conn, a.rank, a.as_of, a.limit)
            if r.get("refused"):
                print(f"\n  REFUSED: {r['reason']}\n"); conn.close(); return 1
            print(f"\n  {r['multiple']} across the universe as of {r['as_of']}")
            print(f"  ranked {r['n_ranked']} of {r['n_universe']} — "
                  f"COVERAGE {r['coverage']:.1%}")
            print("  " + "-" * 56)
            for x in r["ranked"][:12]:
                print(f"  {x['ticker']:<8}{_fmt(x['value']):>14}"
                      f"{x['percentile']:>10.1%}")
        print()
        conn.close(); return 0

    if a.coverage:
        c = coverage_report(conn, a.as_of, a.limit)
        print(f"\n  MULTIPLE COVERAGE — {c['panel']} companies as of {c['as_of']}")
        print("  Coverage is not a nuisance here: the covered subset has a")
        print("  median market cap 2.5x the uncovered one.")
        print("  " + "-" * 60)
        for m, d in sorted(c["multiples"].items(), key=lambda kv: -kv[1]["share"]):
            tag = "  EV" if m in EV_MULTIPLES else ""
            print(f"  {m:<20}{d['total']:>5}/{d['n']:<5}{d['share']:>7.1%}{tag}")
        print("\n  by division, EV/EBITDA:")
        for d, (ok, tot) in sorted(
                c["multiples"]["ev_to_ebitda"]["by_division"].items(),
                key=lambda kv: -kv[1][1]):
            if tot < 10:
                continue
            excl = " (excluded)" if "ev_to_ebitda" in INDUSTRY_EXCLUSIONS.get(d, set()) else ""
            print(f"    {d:<22}{ok:>4}/{tot:<5}{ok/tot:>7.1%}{excl}")
        print()
        conn.close(); return 0

    print("  give --ticker, --rank MULTIPLE [--division D], or --coverage")
    conn.close(); return 1


if __name__ == "__main__":
    raise SystemExit(main())
