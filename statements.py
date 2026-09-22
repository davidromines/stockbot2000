"""
The financial statement analysis engine. Phase 9, item 26.

WHAT THIS ADDS THAT `value_metrics` DOES NOT
----------------------------------------------
`value_metrics` computes ~40 RATIOS and stores only those. The levels they were
built from — revenue, net income, book value, cash, debt, operating cash flow —
are discarded. That is fine for screening and useless for analysis: you cannot
ask "is this margin compression or revenue decline?" of a margin alone, and the
valuation work in item 27 needs the levels, not the ratios.

So this exposes the three statements themselves, per filing, point-in-time.

EVERY FIGURE IS EITHER A NUMBER OR ABSENT — NEVER ZERO
--------------------------------------------------------
A company that did not report R&D is not a company that spent nothing on R&D.
This project has been bitten by that substitution twice already: an unknown
market cap waved TNON through as "unmeasured", and an unknown liquidity would
have done the same. So `None` propagates: any ratio with a missing input is
`None`, and nothing is defaulted to zero to make a column look full.

The one deliberate exception is documented at `_net_debt`, where absent
short-term borrowings are treated as zero — and the reason it is safe there is
that it makes net debt LOOK BETTER, so a company failing a leverage screen on
this basis fails it on real debt.

INDUSTRY AWARENESS IS A WARNING, NOT AN ADJUSTMENT
----------------------------------------------------
Item 27 says not to assume one metric works for every industry. This engine
does not silently adjust a bank's ratios to look like a manufacturer's; it
attaches the industry and a flag saying which figures do not mean what they
usually mean. Book value IS the operating substance of a lender, and leverage
IS its business model. Quietly normalising that away would hide the thing a
reader most needs to know.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import industry
import storage
import value_metrics as vm
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("statements")

# Extra fallback chains for tags added 2026-09-22. Kept here rather than edited
# into value_metrics.CHAINS so the screens' behaviour does not change as a side
# effect of building an analysis view.
CHAINS = {
    **vm.CHAINS,
    "capex":        ["PaymentsToAcquirePropertyPlantAndEquipment",
                     "PaymentsToAcquireProductiveAssets"],
    "goodwill":     ["Goodwill"],
    "intangibles":  ["IntangibleAssetsNetExcludingGoodwill",
                     "FiniteLivedIntangibleAssetsNet"],
    "rd":           ["ResearchAndDevelopmentExpense"],
    "sga":          ["SellingGeneralAndAdministrativeExpense",
                     "GeneralAndAdministrativeExpense"],
    "st_debt":      ["ShortTermBorrowings", "DebtCurrent", "LongTermDebtCurrent",
                     "OtherShortTermBorrowings"],
    "eps_diluted":  ["EarningsPerShareDiluted"],
    "dividends":    ["PaymentsOfDividendsCommonStock", "PaymentsOfDividends"],
    "buybacks":     ["PaymentsForRepurchaseOfCommonStock"],
}

FLOW = (1, 4)      # quarterly or annual flows
BALANCE = (0,)     # point-in-time balances


def _pick(facts: dict, key: str, want_qtrs=None):
    for tag in CHAINS.get(key, []):
        for q, v in facts.get(tag, {}).items():
            if want_qtrs is None or q in want_qtrs:
                return v
    return None


def _div(a, b):
    """a/b, or None. Absent inputs and a zero denominator both give None."""
    if a is None or b is None or b == 0:
        return None
    return a / b


def _sub(a, b):
    return None if (a is None or b is None) else a - b


def _net_debt(total_debt, cash):
    """
    Net debt = debt - cash.

    Absent short-term borrowings are treated as zero inside `_total_debt`, which
    is a defaulting rule this module otherwise forbids. It is safe here in one
    direction only: omitting debt makes leverage look BETTER, so a company that
    fails a leverage test on this basis fails it on debt we can actually see.
    The reverse — defaulting missing cash to zero — is NOT done, because that
    would manufacture leverage a company does not have.
    """
    if total_debt is None or cash is None:
        return None
    return total_debt - cash


def _total_debt(facts):
    lt = _pick(facts, "lt_debt", BALANCE)
    st = _pick(facts, "st_debt", BALANCE)
    if lt is None and st is None:
        return None
    return (lt or 0) + (st or 0)


def statement(conn, adsh: str) -> dict:
    """The three statements plus derived analysis for one filing."""
    f = vm._facts_for(conn, adsh)
    g = lambda k, q=None: _pick(f, k, q)  # noqa: E731

    revenue = g("revenue", FLOW)
    cogs = g("cogs", FLOW)
    gross = g("gross_profit", FLOW)
    if gross is None:
        gross = _sub(revenue, cogs)
    op_inc = g("op_income", FLOW)
    dep = g("dep_amort", FLOW)
    net_inc = g("net_income", FLOW)
    ocf = g("ocf", FLOW)
    capex = g("capex", FLOW)
    # EBITDA is not a GAAP measure and is never tagged; it is constructed.
    ebitda = None if (op_inc is None or dep is None) else op_inc + dep
    # Capex is reported as a positive outflow in the cash-flow statement, so it
    # is SUBTRACTED. Adding it would turn the most capital-hungry companies into
    # the best free-cash-flow generators in the database.
    fcf = None if (ocf is None or capex is None) else ocf - abs(capex)

    assets = g("assets", BALANCE)
    equity = g("equity", BALANCE)
    cash = g("cash", BALANCE)
    goodwill = g("goodwill", BALANCE)
    intang = g("intangibles", BALANCE)
    debt = _total_debt(f)
    assets_cur = g("assets_cur", BALANCE)
    liab_cur = g("liab_cur", BALANCE)
    rd = g("rd", FLOW)
    sga = g("sga", FLOW)

    tangible_bv = equity
    if equity is not None:
        for x in (goodwill, intang):
            if x is not None:
                tangible_bv -= x

    return {
        "adsh": adsh,
        # --- income statement ---
        "revenue": revenue, "cogs": cogs, "gross_profit": gross,
        "operating_income": op_inc, "ebit": op_inc, "ebitda": ebitda,
        "net_income": net_inc, "rd": rd, "sga": sga,
        "eps_basic": g("eps"), "eps_diluted": g("eps_diluted"),
        "gross_margin": _div(gross, revenue),
        "operating_margin": _div(op_inc, revenue),
        "ebitda_margin": _div(ebitda, revenue),
        "net_margin": _div(net_inc, revenue),
        "rd_intensity": _div(rd, revenue),
        "sga_intensity": _div(sga, revenue),
        # --- balance sheet ---
        "assets": assets, "equity": equity, "book_value": equity,
        "tangible_book_value": tangible_bv,
        "cash": cash, "debt": debt, "net_debt": _net_debt(debt, cash),
        "net_cash": None if (cash is None or debt is None) else cash - debt,
        "goodwill": goodwill, "intangibles": intang,
        "working_capital": _sub(assets_cur, liab_cur),
        "current_ratio": _div(assets_cur, liab_cur),
        "debt_to_equity": _div(debt, equity),
        "debt_to_ebitda": _div(debt, ebitda),
        # --- cash flow ---
        "operating_cash_flow": ocf, "capex": capex, "free_cash_flow": fcf,
        "fcf_margin": _div(fcf, revenue),
        "capex_intensity": _div(abs(capex) if capex is not None else None, revenue),
        # Cash conversion: how much of reported profit arrives as cash. Well
        # below 1 over several periods is the classic accrual warning.
        "cash_conversion": _div(ocf, net_inc),
        "fcf_to_net_income": _div(fcf, net_inc),
        # --- returns ---
        "roe": _div(net_inc, equity),
        "roa": _div(net_inc, assets),
        "roce": _div(op_inc, _sub(assets, liab_cur)),
        "gross_profitability": _div(gross, assets),
        "asset_turnover": _div(revenue, assets),
    }


def analyse(conn, ticker: str, as_of: str) -> dict:
    """
    The newest statement TRADEABLE by `as_of`, with its industry context.

    Keyed on `first_tradeable`, so a filing accepted after the close is not
    visible on the day it was accepted.
    """
    r = conn.execute("""SELECT adsh, form, period, filed, accepted,
        first_tradeable, prevrpt FROM sec_filings
        WHERE ticker=? AND first_tradeable IS NOT NULL AND first_tradeable <= ?
        ORDER BY first_tradeable DESC LIMIT 1""", (ticker, as_of)).fetchone()
    if not r:
        return {"ticker": ticker, "as_of": as_of, "available": False,
                "reason": "no filing was tradeable by this date"}
    st = statement(conn, r["adsh"])
    ind = industry.classify_as_of(conn, ticker, as_of)
    reported = sum(1 for k, v in st.items() if k != "adsh" and v is not None)
    return {"ticker": ticker, "as_of": as_of, "available": True,
            "filing": dict(r), "industry": ind, "statement": st,
            "fields_reported": reported,
            "fields_total": len(st) - 1,
            "caveat": ind.get("special_accounting")}


def _fmt(v, money=True):
    if v is None:
        return "not reported"
    if not money:
        return f"{v:.3f}" if abs(v) < 100 else f"{v:,.1f}"
    a = abs(v)
    for div, suf in ((1e9, "B"), (1e6, "M"), (1e3, "K")):
        if a >= div:
            return f"${v/div:,.2f}{suf}"
    return f"${v:,.0f}"


def render(a: dict) -> str:
    if not a.get("available"):
        return f"\n  {a['ticker']}: {a['reason']}\n"
    st, fl, ind = a["statement"], a["filing"], a["industry"]
    L = ["", f"  {a['ticker']} — financial statements as of {a['as_of']}",
         f"  {fl['form']} for period {fl['period']}, accepted "
         f"{(fl['accepted'] or '')[:16]}, first tradeable {fl['first_tradeable']}",
         f"  industry: {ind['label']} (SIC {ind['sic']})",
         f"  {a['fields_reported']}/{a['fields_total']} fields reported"]
    if fl["prevrpt"]:
        L.append("  NOTE: this filing was later superseded by an amendment.")
    if a.get("caveat"):
        L += ["", f"  INDUSTRY CAVEAT: {a['caveat']}"]
    groups = (
        ("INCOME", ["revenue", "gross_profit", "operating_income", "ebitda",
                    "net_income", "rd", "sga"], True),
        ("MARGINS", ["gross_margin", "operating_margin", "ebitda_margin",
                     "net_margin", "rd_intensity"], False),
        ("BALANCE", ["assets", "equity", "tangible_book_value", "cash", "debt",
                     "net_debt", "goodwill", "working_capital"], True),
        ("CASH FLOW", ["operating_cash_flow", "capex", "free_cash_flow"], True),
        ("QUALITY", ["fcf_margin", "cash_conversion", "fcf_to_net_income",
                     "current_ratio", "debt_to_equity", "debt_to_ebitda"], False),
        ("RETURNS", ["roe", "roa", "roce", "gross_profitability",
                     "asset_turnover"], False),
    )
    for title, keys, money in groups:
        L += ["", f"  {title}", "  " + "-" * 52]
        for k in keys:
            L.append(f"  {k:<24}{_fmt(st.get(k), money):>26}")
    L += ["", "  'not reported' is not zero. A company that did not disclose",
          "  R&D is not a company that spent nothing on it.", ""]
    return "\n".join(L)


def coverage(conn, as_of: str, limit: int = 400) -> dict:
    """How complete the statements are across the universe."""
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM sec_filings WHERE ticker IS NOT NULL "
        "AND first_tradeable IS NOT NULL AND first_tradeable <= ? "
        f"ORDER BY ticker LIMIT {int(limit)}", (as_of,))]
    field_hits: dict = {}
    n = 0
    for t in tickers:
        a = analyse(conn, t, as_of)
        if not a.get("available"):
            continue
        n += 1
        for k, v in a["statement"].items():
            if k == "adsh":
                continue
            field_hits[k] = field_hits.get(k, 0) + (1 if v is not None else 0)
    return {"tickers": n, "fields": field_hits}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker")
    ap.add_argument("--as-of", default="2026-09-21")
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.coverage:
        c = coverage(conn, a.as_of)
        print(f"\n  STATEMENT COVERAGE — {c['tickers']} companies as of {a.as_of}")
        print("  A low number is a data gap, not a company that reported zero.")
        print("  " + "-" * 56)
        for k, v in sorted(c["fields"].items(), key=lambda kv: kv[1]):
            bar = "#" * int(28 * v / max(c["tickers"], 1))
            print(f"  {k:<24}{v:>5}  {bar}")
        conn.close(); return 0

    if not a.ticker:
        print("  give --ticker or --coverage"); conn.close(); return 1
    print(render(analyse(conn, a.ticker, a.as_of)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
