"""
Constructed fundamental indicators. Everything a value investor actually looks at.

Raw XBRL facts are not signals. `Assets` is a number; `GrossProfit / Assets` is
Novy-Marx's gross profitability, which predicts returns. This module turns
19 million stored facts into the roughly thirty-five ratios and scores the
literature has actually tested.

WHY THESE, AND WHAT THE EVIDENCE SAYS
-------------------------------------
Grouped by family, each with its source and the reason it is here:

*Valuation* — book-to-market is the original Fama-French (1993) value factor.
Greenblatt's earnings yield (EBIT/EV) is the valuation half of the Magic Formula.
EV/EBITDA is the multiple practitioners actually quote, and is the reason EBITDA
has to be constructed at all: it is non-GAAP and never tagged in XBRL.

*Profitability* — gross profitability (Novy-Marx 2013) is "the other side of
value" and has roughly the same power as book-to-market while being nearly
uncorrelated with it, which makes the pair far stronger than either alone. ROIC
is the quality half of the Magic Formula.

*Quality scores* — Piotroski's F-Score (2000) is nine binary accounting tests;
high scores (8-9) inside high book-to-market earned **13.4% mean annual
market-adjusted return, beating the full value portfolio by 7.5% and low-F-Score
names by 23%**. Mohanram's G-Score is its counterpart for growth stocks.

*Earnings quality* — Sloan's accruals (1996): earnings not backed by cash
predict poor returns. Net operating assets (Hirshleifer et al. 2004) is the
balance-sheet version of the same idea. Beneish's M-Score flags manipulation.

*Investment* — asset growth (Cooper et al. 2008) is reported as the strongest of
the balance-sheet growth measures, beating both capital investment and net
operating asset growth. Net share issuance (Daniel & Titman) captures dilution.

*Distress* — Altman Z and Ohlson O are here because they are famous, **and the
literature is unkind to both**: "the accounting based approaches of Altman's
Z-Score and Ohlson's O-Score are highly ineffective... the use of the Campbell,
Hilscher and Szilagyi model is recommended." CHS is implemented as well, and it
matters more here than anywhere else: it predicts *bankruptcy, delisting or a D
rating*, which is precisely the event our delisting registry records and our
price history is missing.

*Shareholder yield* — Faber: dividends plus net buybacks, which beat
dividend-only screens.

WHAT IS DELIBERATELY NOT PROMISED
--------------------------------
Coverage will be uneven and is reported rather than hidden. XBRL lets companies
choose among synonyms — revenue appears under at least four tags depending on
company and era — so every input has a fallback chain, and some companies still
will not compute. A value screen that silently drops half the market is not a
screen, so `--coverage` prints what resolved and what did not.

All of it is keyed on the **filing date**, never the period end. A June quarter
is published weeks later, and aligning to period end would let a backtest read a
balance sheet before it existed.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("value")

# Fallback chains. Order matters: the first tag present wins. These exist because
# XBRL is a vocabulary, not a schema — two companies reporting the same economic
# quantity routinely choose different tags, and an older filing uses tags that
# have since been deprecated.
CHAINS = {
    "assets":        ["Assets"],
    "assets_cur":    ["AssetsCurrent"],
    "liab":          ["Liabilities"],
    "liab_cur":      ["LiabilitiesCurrent"],
    "equity":        ["StockholdersEquity",
                      "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"],
    "lt_debt":       ["LongTermDebtNoncurrent", "LongTermDebt"],
    "cash":          ["CashAndCashEquivalentsAtCarryingValue"],
    "retained":      ["RetainedEarningsAccumulatedDeficit"],
    "inventory":     ["InventoryNet"],
    "revenue":       ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                      "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet"],
    "cogs":          ["CostOfGoodsAndServicesSold", "CostOfRevenue", "CostOfGoodsSold"],
    "gross_profit":  ["GrossProfit"],
    "op_income":     ["OperatingIncomeLoss"],
    "net_income":    ["NetIncomeLoss"],
    "pretax":        ["IncomeLossFromContinuingOperationsBeforeIncomeTaxes"
                      "ExtraordinaryItemsNoncontrollingInterest"],
    "interest":      ["InterestExpense"],
    "tax":           ["IncomeTaxExpenseBenefit"],
    "ocf":           ["NetCashProvidedByUsedInOperatingActivities",
                      "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations"],
    "dep_amort":     ["DepreciationDepletionAndAmortization",
                      "DepreciationAmortizationAndAccretionNet",
                      "DepreciationAndAmortization", "Depreciation"],
    "shares":        ["CommonStockSharesOutstanding",
                      "WeightedAverageNumberOfSharesOutstandingBasic",
                      "CommonStockSharesIssued"],
    "eps":           ["EarningsPerShareBasic"],
}

# Every metric this module produces, so the schema and the coverage report stay
# in step with the code automatically.
METRICS = [
    # valuation (need market cap)
    "book_to_market", "earnings_yield", "sales_to_price", "fcf_yield",
    "ebit_to_ev", "ev_to_ebitda", "ev_to_sales",
    # profitability
    "roa", "roe", "roic", "gross_profitability", "gross_margin",
    "operating_margin", "net_margin", "cash_roa",
    # earnings quality
    "accruals", "net_operating_assets", "earnings_quality",
    # investment and growth
    "asset_growth", "revenue_growth", "earnings_growth", "book_growth",
    "net_share_issuance",
    # leverage and liquidity
    "debt_to_equity", "debt_to_ebitda", "current_ratio", "quick_ratio",
    "interest_coverage", "cash_to_assets",
    # efficiency
    "asset_turnover", "inventory_turnover",
    # constructed aggregates
    "ebitda", "piotroski_f", "altman_z", "ohlson_o", "chs_distress",
]


def init(conn) -> None:
    cols = ",\n            ".join(f"{m} REAL" for m in METRICS)
    conn.execute(f"""
        CREATE TABLE IF NOT EXISTS fundamentals (
            ticker      TEXT NOT NULL,
            adsh        TEXT NOT NULL,
            filed       TEXT NOT NULL,   -- POINT-IN-TIME KEY. Never use `period`.
            period      TEXT,
            form        TEXT,
            market_cap  REAL,
            {cols},
            PRIMARY KEY (ticker, filed, adsh)
        ) STRICT, WITHOUT ROWID
    """)
    have = {r[1] for r in conn.execute("PRAGMA table_info(fundamentals)")}
    for m in METRICS:
        if m not in have:
            conn.execute(f"ALTER TABLE fundamentals ADD COLUMN {m} REAL")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fund_filed ON fundamentals(filed)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_fund_ticker ON fundamentals(ticker)")
    conn.commit()


def _pick(facts: dict, key: str, want_qtrs=None):
    """
    Resolve one economic quantity through its fallback chain.

    `qtrs` distinguishes a point-in-time balance (0) from a flow measured over
    one quarter (1) or a year (4). Asking for the wrong one silently mixes a
    quarterly profit with an annual one, which is the kind of error that produces
    a ratio four times too large and no exception at all.
    """
    for tag in CHAINS.get(key, []):
        for q, v in facts.get(tag, {}).items():
            if want_qtrs is None or q in want_qtrs:
                return v
    return None


def _safe(num, den, cap=1e6):
    """Ratio guarded against the zero denominators that pervade filings."""
    if num is None or den is None:
        return None
    try:
        den = float(den)
        if abs(den) < 1e-6:
            return None
        r = float(num) / den
        return r if abs(r) < cap and np.isfinite(r) else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def compute(cur, prev, market_cap=None, mkt: dict | None = None) -> dict:
    """
    All constructed indicators for one filing, given the prior year's for deltas.

    `cur` and `prev` are {tag: {qtrs: value}} maps. `prev` may be None, in which
    case every change-based metric — the growth rates, most of the F-Score — is
    left null rather than guessed at. A first filing has no history and should
    say so.
    """
    g = lambda k, q=None: _pick(cur, k, q)          # noqa: E731
    p = lambda k, q=None: _pick(prev, k, q) if prev else None   # noqa: E731

    assets, equity = g("assets", {0}), g("equity", {0})
    liab, liab_cur = g("liab", {0}), g("liab_cur", {0})
    assets_cur, cash = g("assets_cur", {0}), g("cash", {0})
    inv, lt_debt = g("inventory", {0}), g("lt_debt", {0})
    retained = g("retained", {0})
    rev, cogs = g("revenue", {1, 4}), g("cogs", {1, 4})
    gp, op_inc = g("gross_profit", {1, 4}), g("op_income", {1, 4})
    ni, ocf = g("net_income", {1, 4}), g("ocf", {1, 4})
    interest, tax = g("interest", {1, 4}), g("tax", {1, 4})
    da = g("dep_amort", {1, 4})
    shares = g("shares", {0, 1, 4})

    # Gross profit is frequently absent even when both its inputs are present.
    if gp is None and rev is not None and cogs is not None:
        gp = rev - cogs

    # ANNUALISED flows, for every ratio against a balance or a market value.
    # `{1, 4}` above takes whichever period a filing reports first: a 10-Q's
    # quarter, a 10-K's year. Divided by assets or market cap, that made every
    # stock-based ratio jump 4x after each annual report and fall back after
    # the next 10-Q (AAPL earnings yield 0.007 -> 0.036 -> 0.012 around each
    # November, 2023-2025), so cross-sectional ranks mixed two scales and a
    # company ranked higher for having just filed a 10-K. Found 2026-09-24.
    # The reported full year where the filing has it, else the quarter x 4 —
    # seasonal, but on one scale. Flow-to-flow ratios (margins, coverage,
    # earnings quality) are scale-free and keep the raw values.
    def ann(key, raw):
        v4 = g(key, {4})
        if v4 is not None:
            return v4
        v1 = g(key, {1})
        return v1 * 4 if v1 is not None else (raw if raw is None else None)
    rev_a, ni_a, ocf_a = ann("revenue", rev), ann("net_income", ni), ann("ocf", ocf)
    op_a, da_a, cogs_a = ann("op_income", op_inc), ann("dep_amort", da), ann("cogs", cogs)
    gp_a = ann("gross_profit", gp)
    if gp_a is None and rev_a is not None and cogs_a is not None:
        gp_a = rev_a - cogs_a
    ebitda_a = (op_a + da_a) if (op_a is not None and da_a is not None) else None

    # EBITDA: never tagged, always constructed. Operating income plus D&A is the
    # standard build; without D&A it cannot be computed and is left null rather
    # than quietly approximated by operating income, which would flatter every
    # capital-intensive company.
    ebitda = (op_inc + da) if (op_inc is not None and da is not None) else None

    m = {k: None for k in METRICS}
    m["ebitda"] = ebitda

    # -- profitability -----------------------------------------------------
    m["roa"] = _safe(ni_a, assets)
    m["roe"] = _safe(ni_a, equity)
    m["gross_profitability"] = _safe(gp_a, assets)        # Novy-Marx (2013)
    m["gross_margin"] = _safe(gp, rev)
    m["operating_margin"] = _safe(op_inc, rev)
    m["net_margin"] = _safe(ni, rev)
    m["cash_roa"] = _safe(ocf_a, assets)
    invested = None
    if equity is not None and lt_debt is not None:
        invested = equity + lt_debt
    m["roic"] = _safe(op_a, invested)                     # Greenblatt's quality half

    # -- earnings quality --------------------------------------------------
    if ni is not None and ocf is not None:
        m["accruals"] = _safe(ni_a - ocf_a, assets)       # Sloan (1996)
    m["earnings_quality"] = _safe(ocf, ni)
    if assets is not None and cash is not None and liab is not None and lt_debt is not None:
        m["net_operating_assets"] = _safe((assets - cash) - (liab - lt_debt), assets)

    # -- leverage, liquidity, efficiency -----------------------------------
    m["debt_to_equity"] = _safe(lt_debt, equity)
    m["debt_to_ebitda"] = _safe(lt_debt, ebitda_a)
    m["current_ratio"] = _safe(assets_cur, liab_cur)
    if assets_cur is not None and inv is not None:
        m["quick_ratio"] = _safe(assets_cur - inv, liab_cur)
    m["interest_coverage"] = _safe(op_inc, interest)
    m["cash_to_assets"] = _safe(cash, assets)
    m["asset_turnover"] = _safe(rev_a, assets)
    m["inventory_turnover"] = _safe(cogs_a, inv)

    # -- growth, versus the same quarter a year earlier ---------------------
    pa, pr, pni, peq, psh = (p("assets", {0}), p("revenue", {1, 4}),
                             p("net_income", {1, 4}), p("equity", {0}),
                             p("shares", {0, 1, 4}))
    if pa:
        m["asset_growth"] = _safe(assets - pa, pa) if assets is not None else None
    if pr:
        m["revenue_growth"] = _safe(rev - pr, abs(pr)) if rev is not None else None
    if pni:
        m["earnings_growth"] = _safe(ni - pni, abs(pni)) if ni is not None else None
    if peq:
        m["book_growth"] = _safe(equity - peq, abs(peq)) if equity is not None else None
    if psh:
        m["net_share_issuance"] = _safe(shares - psh, psh) if shares is not None else None

    # -- valuation, which needs a market capitalisation ---------------------
    if market_cap and market_cap > 0:
        m["book_to_market"] = _safe(equity, market_cap)
        m["earnings_yield"] = _safe(ni_a, market_cap)
        m["sales_to_price"] = _safe(rev_a, market_cap)
        if ocf_a is not None:
            m["fcf_yield"] = _safe(ocf_a, market_cap)
        ev = market_cap + (lt_debt or 0) - (cash or 0)
        m["ebit_to_ev"] = _safe(op_a, ev)                 # Greenblatt earnings yield
        m["ev_to_ebitda"] = _safe(ev, ebitda_a)
        m["ev_to_sales"] = _safe(ev, rev_a)

    m["piotroski_f"] = _piotroski(cur, prev, m)
    m["altman_z"] = _altman(assets, liab, liab_cur, assets_cur, retained, op_a,
                            rev_a, market_cap)
    m["ohlson_o"] = _ohlson(assets, liab, liab_cur, assets_cur, ni_a, ocf_a)
    if mkt is not None:
        m["chs_distress"] = chs_distress(
            ni, liab, cash, equity, market_cap,
            mkt.get("excess"), mkt.get("sigma"), mkt.get("price"), mkt.get("rel_size"))
    return m


def _piotroski(cur, prev, m) -> float | None:
    """
    Piotroski's F-Score: nine binary tests, one point each.

    Four on profitability, three on leverage and liquidity, two on operating
    efficiency. Piotroski (2000) found high scores (8-9) inside high
    book-to-market earned 13.4% mean annual market-adjusted return, beating the
    full value portfolio by 7.5 points and low-F-Score names by 23.

    Returns None rather than a partial score when there is no prior year: four of
    the nine tests are year-on-year changes, and scoring 5 out of a possible 5
    would rank a company with no history above a genuinely strong one.
    """
    if prev is None:
        return None
    g = lambda k, q=None: _pick(cur, k, q)          # noqa: E731
    p = lambda k, q=None: _pick(prev, k, q)         # noqa: E731

    assets, ni, ocf = g("assets", {0}), g("net_income", {1, 4}), g("ocf", {1, 4})
    pa, pni = p("assets", {0}), p("net_income", {1, 4})
    if assets is None or ni is None:
        return None

    roa = _safe(ni, assets)
    proa = _safe(pni, pa)
    score = 0
    # profitability
    if roa is not None and roa > 0:                       score += 1
    if ocf is not None and ocf > 0:                       score += 1
    if roa is not None and proa is not None and roa > proa: score += 1
    if ocf is not None and ni is not None and ocf > ni:    score += 1   # accruals
    # leverage, liquidity, source of funds
    lev, plev = _safe(g("lt_debt", {0}), assets), _safe(p("lt_debt", {0}), pa)
    if lev is not None and plev is not None and lev < plev: score += 1
    cr = _safe(g("assets_cur", {0}), g("liab_cur", {0}))
    pcr = _safe(p("assets_cur", {0}), p("liab_cur", {0}))
    if cr is not None and pcr is not None and cr > pcr:   score += 1
    sh, psh = g("shares", {0, 1, 4}), p("shares", {0, 1, 4})
    if sh is not None and psh is not None and sh <= psh * 1.001: score += 1
    # operating efficiency
    gm = m.get("gross_margin")
    pgm = _safe(_pick(prev, "gross_profit", {1, 4}), _pick(prev, "revenue", {1, 4}))
    if gm is not None and pgm is not None and gm > pgm:   score += 1
    at, pat = m.get("asset_turnover"), _safe(p("revenue", {1, 4}), pa)
    if at is not None and pat is not None and at > pat:   score += 1
    return float(score)


def _altman(assets, liab, liab_cur, assets_cur, retained, ebit, rev, mcap):
    """
    Altman Z-Score. Included because it is famous, with a caveat attached.

    Z = 1.2*WC/TA + 1.4*RE/TA + 3.3*EBIT/TA + 0.6*MVE/TL + 1.0*Sales/TA
    Below 1.81 is the distress zone, above 2.99 the safe zone.

    **The literature is unkind to it**: Z and Ohlson's O are reported as "highly
    ineffective" relative to the Campbell-Hilscher-Szilagyi model, which is
    implemented separately. Kept for comparison, not as the recommended measure.
    """
    if not assets or assets <= 0:
        return None
    wc = (assets_cur - liab_cur) if (assets_cur is not None and liab_cur is not None) else None
    parts = [(1.2, _safe(wc, assets)), (1.4, _safe(retained, assets)),
             (3.3, _safe(ebit, assets)), (0.6, _safe(mcap, liab)),
             (1.0, _safe(rev, assets))]
    vals = [(w, v) for w, v in parts if v is not None]
    if len(vals) < 3:
        return None
    return float(sum(w * v for w, v in vals))


def _ohlson(assets, liab, liab_cur, assets_cur, ni, ocf):
    """
    Ohlson's O-Score, the 1980 logit alternative to Z. Same caveat as Altman.

    Simplified: the original uses a GNP price-level deflator and two dummies that
    are almost always zero. The deflator shifts every company's score by the same
    amount in a given year, so it cannot change a cross-sectional ranking, which
    is the only way this is used here.
    """
    if not assets or assets <= 0:
        return None
    tlta = _safe(liab, assets)
    wcta = _safe((assets_cur - liab_cur), assets) if (
        assets_cur is not None and liab_cur is not None) else None
    clca = _safe(liab_cur, assets_cur)
    nita = _safe(ni, assets)
    futl = _safe(ocf, liab)
    if tlta is None or nita is None:
        return None
    o = (-1.32 - 0.407 * np.log(max(assets, 1.0)) + 6.03 * tlta
         - 1.43 * (wcta or 0) + 0.076 * (clca or 0) - 1.72 * (1.0 if (liab or 0) > assets else 0.0)
         - 2.37 * nita - 1.83 * (futl or 0))
    return float(o) if np.isfinite(o) else None


# Campbell, Hilscher & Szilagyi (2008), "In Search of Distress Risk", Table 4.
# Twelve-month-ahead specification, transcribed from the paper rather than from
# memory. This is the model the comparative literature recommends over Altman's
# Z and Ohlson's O, both of which it calls "highly ineffective" beside it.
#
# It matters more here than anywhere else in this project: CHS predicts
# *bankruptcy, delisting, or a D rating* — precisely the event our delisting
# registry records and our price history is missing. A company scoring high here
# is one whose absence from the database would most distort a backtest.
CHS = {
    "const": -9.164,
    "NIMTAAVG": -20.264,   # profitability, market-scaled
    "TLMTA":      1.416,   # leverage, market-scaled
    "EXRETAVG":  -7.129,   # excess return over the S&P
    "SIGMA":      1.411,   # annualised 3-month return volatility
    "RSIZE":     -0.045,   # log relative size
    "CASHMTA":   -2.132,   # liquidity
    "MB":         0.075,   # market-to-book
    "PRICE":     -0.058,   # log price, capped
}


def chs_distress(ni, liab, cash, equity, mcap, excess_ret, sigma, price,
                 rel_size) -> float | None:
    """
    CHS failure probability. Higher means likelier to fail, delist or be downgraded.

    Scaling is by **market** value of total assets (MTA = market equity + book
    liabilities), not book assets. The paper is explicit that the market-valued
    series outperforms the book-valued one for both profitability and leverage,
    which is the main reason this model beats the purely accounting-based scores.

    Book equity is adjusted as in Cohen, Polk & Vuolteenaho: add 10% of the gap
    between market and book equity, which stops tiny or mismeasured book values
    from producing enormous ratios when used as denominators. The paper also
    winsorises every input at the 5th and 95th percentiles; that is a
    cross-sectional operation and is applied at query time, not here.

    Returns the logit probability, or None when the inputs are not all present —
    a partial CHS is not a CHS.
    """
    if None in (ni, liab, mcap) or not mcap or mcap <= 0:
        return None
    mta = mcap + liab
    if mta <= 0:
        return None
    nimta = ni / mta
    tlmta = liab / mta
    cashmta = (cash / mta) if cash is not None else 0.0
    # Market-to-book with the Cohen-Polk-Vuolteenaho adjustment.
    mb = None
    if equity is not None:
        adj = equity + 0.1 * (mcap - equity)
        mb = mcap / adj if adj > 1e-6 else None
    # The paper caps log price at $15: below that, price level carries distress
    # information; above it, it does not.
    logp = np.log(min(price, 15.0)) if (price and price > 0) else None

    x = (CHS["const"]
         + CHS["NIMTAAVG"] * nimta
         + CHS["TLMTA"] * tlmta
         + CHS["CASHMTA"] * cashmta
         + CHS["EXRETAVG"] * (excess_ret if excess_ret is not None else 0.0)
         + CHS["SIGMA"] * (sigma if sigma is not None else 0.0)
         + CHS["RSIZE"] * (rel_size if rel_size is not None else 0.0)
         + CHS["MB"] * (mb if mb is not None else 0.0)
         + CHS["PRICE"] * (logp if logp is not None else 0.0))
    if not np.isfinite(x):
        return None
    return float(1.0 / (1.0 + np.exp(-x)))


def _market_context(conn, ticker: str, filed: str) -> dict:
    """
    The market-side CHS inputs: excess return, volatility, price, relative size.

    All measured strictly *before* the filing date. CHS mixes accounting and
    market data, and the market half is the easier of the two to leak: reading a
    return window that ends after the filing would be exactly the look-ahead this
    project has already produced six false results from.
    """
    d = f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}" if len(filed) == 8 else filed
    rows = conn.execute(
        "SELECT date, close FROM prices WHERE ticker=? AND date<=? AND close>0 "
        "ORDER BY date DESC LIMIT 65", (ticker, d)).fetchall()
    if len(rows) < 25:
        return {}
    px = np.array([r[1] for r in rows], dtype="float64")[::-1]
    rets = np.diff(np.log(px))
    # Annualised, centred on zero rather than the rolling mean, per the paper.
    sigma = float(np.sqrt(252.0 * np.mean(rets ** 2))) if rets.size else None
    spy = conn.execute(
        "SELECT date, close FROM prices WHERE ticker='SPY' AND date<=? AND close>0 "
        "ORDER BY date DESC LIMIT 65", (d,)).fetchall()
    excess = None
    if len(spy) >= 25:
        s = np.array([r[1] for r in spy], dtype="float64")[::-1]
        excess = float(np.log(px[-1] / px[0]) - np.log(s[-1] / s[0]))
    return {"sigma": sigma, "excess": excess, "price": float(px[-1])}


def _facts_for(conn, adsh: str) -> dict:
    """{tag: {qtrs: value}} for one filing, most recent period per (tag, qtrs)."""
    out: dict = {}
    for tag, ddate, qtrs, val in conn.execute(
            "SELECT tag, ddate, qtrs, value FROM sec_facts WHERE adsh=? ORDER BY ddate", (adsh,)):
        out.setdefault(tag, {})[qtrs] = val
    return out


def _market_cap(conn, ticker: str, filed: str, shares) -> float | None:
    """
    Market cap from point-in-time shares and the price on the filing date.

    Shares come from the filing itself, never from a current quote API: a quote
    API reports today's share count, and using it for a 2012 balance sheet is
    look-ahead of the worst kind, because dilution is exactly what distressed
    companies do between then and now.
    """
    if not shares or shares <= 0:
        return None
    d = f"{filed[:4]}-{filed[4:6]}-{filed[6:8]}" if len(filed) == 8 else filed
    r = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? AND close>0 "
                     "ORDER BY date DESC LIMIT 1", (ticker, d)).fetchone()
    return float(r[0]) * float(shares) if r else None


def build(conn, limit: int | None = None, since: str | None = None) -> None:
    init(conn)
    q = ("SELECT adsh, ticker, filed, period, form, cik FROM sec_filings "
         "WHERE ticker IS NOT NULL")
    params: list = []
    if since:
        q += " AND filed >= ?"; params.append(since)
    q += " ORDER BY ticker, filed"
    if limit:
        q += f" LIMIT {int(limit)}"
    rows = conn.execute(q, params).fetchall()
    log.info(f"Computing metrics for {len(rows):,} filings")

    # Prior-year filing per company, for the change-based metrics. Keyed on CIK
    # rather than ticker because tickers get reused and reassigned; a CIK does not.
    prev_by_cik: dict = {}
    out, n, ok = [], 0, 0
    for r in rows:
        cur = _facts_for(conn, r["adsh"])
        if not cur:
            continue
        prev = prev_by_cik.get(r["cik"])
        shares = _pick(cur, "shares", {0, 1, 4})
        mcap = _market_cap(conn, r["ticker"], r["filed"], shares)
        mkt = _market_context(conn, r["ticker"], r["filed"]) if mcap else None
        if mkt and mcap:
            # Relative size: log of market equity against a fixed large-cap scale.
            # The paper uses total S&P 500 valuation; a constant scale preserves
            # the cross-sectional ordering, which is all this is used for.
            mkt["rel_size"] = float(np.log(max(mcap, 1.0) / 1e13))
        m = compute(cur, prev, mcap, mkt)
        prev_by_cik[r["cik"]] = cur

        vals = [r["ticker"], r["adsh"], r["filed"], r["period"], r["form"], mcap]
        vals += [m.get(k) for k in METRICS]
        out.append(tuple(vals))
        n += 1
        ok += sum(1 for k in METRICS if m.get(k) is not None) > 5
        if len(out) >= 5000:
            _flush(conn, out); out = []
            log.info(f"  {n:,}/{len(rows):,}")
    if out:
        _flush(conn, out)
    conn.commit()
    log.info(f"Wrote {n:,} rows; {ok:,} resolved more than five metrics")


def _flush(conn, rows) -> None:
    cols = "ticker,adsh,filed,period,form,market_cap," + ",".join(METRICS)
    ph = ",".join("?" * (6 + len(METRICS)))
    conn.executemany(f"INSERT OR REPLACE INTO fundamentals ({cols}) VALUES ({ph})", rows)
    conn.commit()


def coverage(conn) -> None:
    init(conn)
    tot = conn.execute("SELECT COUNT(*) FROM fundamentals").fetchone()[0]
    if not tot:
        raise SystemExit("Nothing computed — run --build first.")
    print(f"\n  CONSTRUCTED FUNDAMENTAL INDICATORS — {tot:,} filings\n")
    print(f"  {'metric':<26}{'resolved':>12}{'coverage':>11}")
    print("  " + "-" * 50)
    rows = []
    for m in METRICS:
        c = conn.execute(f"SELECT COUNT({m}) FROM fundamentals").fetchone()[0]
        rows.append((m, c))
    for m, c in sorted(rows, key=lambda t: -t[1]):
        print(f"  {m:<26}{c:>12,}{c/tot:>10.0%}")
    print("\n  Coverage is uneven because XBRL is a vocabulary, not a schema: two")
    print("  companies reporting the same quantity often pick different tags, and")
    print("  older filings use tags since deprecated. Reported rather than hidden —")
    print("  a screen that silently drops half the market is not a screen.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--since", default=None)
    ap.add_argument("--coverage", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)
    if a.build:
        build(conn, a.limit, a.since)
    if a.coverage or not a.build:
        coverage(conn)
    conn.close()


if __name__ == "__main__":
    main()
