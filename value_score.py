"""
The multi-dimensional value score and watchlist. Phase 9, item 29.

THE SPEC'S OWN INSTRUCTION GOVERNS THIS FILE
----------------------------------------------
    "Do NOT finalize the scoring formula now. The scoring system itself must
     eventually become an experiment."

So there is no final formula here. `WEIGHTINGS` holds several, every score
records which one produced it, and `--weighting` switches between them. The
same architecture as `scoreboard.FORMULAS`, for the same reason: the weighting
is a hypothesis about what matters, and a hypothesis that cannot be changed
without rewriting history is not being tested.

`equal` ships as the control. A considered weighting that cannot beat weighting
every dimension the same is not adding anything, and this project has learned
repeatedly that elaborate scoring usually encodes the author's priors rather
than the market's.

A SCORE OVER THREE DIMENSIONS IS NOT A SCORE OVER NINE
--------------------------------------------------------
Most companies cannot be scored on everything. Debt is tagged for 38% of
filers, EBITDA for 58%, and an intrinsic value needs four years of positive
free cash flow. The tempting move is to average whatever dimensions happen to
exist and print a number between 0 and 100.

That is the error this whole project keeps rediscovering in new clothes: an
unknown treated as an average. A company scored on VALUE and QUALITY alone
would be compared directly against one scored on all nine, and the first would
usually win, because the dimensions it is missing are the ones where thin
disclosure and weak fundamentals travel together.

So `dimensions_scored` is returned with every score, `MIN_DIMENSIONS` is
enforced, and the watchlist prints the count in its own column. A score is
never comparable across different denominators and the output says so.

EVERY RANKING IS WITHIN INDUSTRY
----------------------------------
The spec asks the system to explain WHY a company ranks where it does.
`explain()` returns each dimension's percentile, its inputs and its
contribution, so a rank can be traced to the figures that produced it rather
than accepted as a verdict.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import statistics

import industry
import intrinsic
import statements as stm
import storage
import valuation as val
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("value_score")

# A company must be scoreable on at least this many of the nine dimensions
# before a composite is reported at all.
MIN_DIMENSIONS = 4

# A filer more than this far behind has effectively stopped reporting. An
# annual filer is late at 12 months and clearly gone at 18; AATC surfaced in
# the first watchlist run ranked on a filing from 2022-11-17, nearly four years
# stale, scored against peers reporting quarterly. Its fundamentals are not
# wrong, they are about a different company than the one trading today.
STALE_FILING_DAYS = 550

# (dimension, statement field or multiple, higher_is_better)
# Each is a percentile WITHIN the company's industry, never across the market.
DIMENSIONS = {
    "value":         [("pb", False), ("pe", False), ("ps", False)],
    "quality":       [("gross_profitability", True), ("roic", True)],
    "profitability": [("operating_margin", True), ("net_margin", True),
                      ("roe", True)],
    "growth":        [("revenue_growth", True)],
    "balance_sheet": [("debt_to_equity", False), ("current_ratio", True)],
    "cash_flow":     [("fcf_margin", True), ("cash_conversion", True)],
    "capital_alloc": [("roce", True), ("asset_turnover", True)],
    "risk":          [("debt_to_ebitda", False), ("fcf_to_net_income", True)],
    "margin_safety": [("margin_of_safety", True)],
}

# Metrics where a NEGATIVE value is not a better value but a different
# situation entirely. A company with negative equity has a negative P/B, and
# ranking "lower is cheaper" put AbbVie at the 96th percentile for value on a
# P/B of -73.26 — the cheapest company in its industry, by virtue of having no
# book value at all. `valuation.rank_within` already filters these out; the
# guard did not carry across, which is how the same defect appears twice in one
# codebase.
#
# These are scored as UNAVAILABLE rather than as worst: negative equity is a
# fact about the balance sheet, not a verdict on cheapness, and forcing it to a
# rank either flatters or condemns it without evidence.
POSITIVE_ONLY = {"pb", "pe", "ps", "debt_to_equity", "debt_to_ebitda",
                 "current_ratio", "cash_conversion", "fcf_to_net_income"}

WEIGHTINGS = {
    # The control. Anything more elaborate must beat this to justify itself.
    "equal": {k: 1.0 for k in DIMENSIONS},
    # A Graham-ish lean: cheapness and balance sheet first.
    "deep_value": {"value": 3.0, "balance_sheet": 2.0, "margin_safety": 2.0,
                   "quality": 1.0, "profitability": 1.0, "cash_flow": 1.0,
                   "growth": 0.5, "capital_alloc": 0.5, "risk": 1.0},
    # A quality-at-a-reasonable-price lean.
    "quality_first": {"quality": 3.0, "profitability": 2.0, "cash_flow": 2.0,
                      "capital_alloc": 1.5, "value": 1.0, "balance_sheet": 1.0,
                      "growth": 1.0, "risk": 1.0, "margin_safety": 0.5},
}
DEFAULT_WEIGHTING = "equal"


def _metric(conn, ticker: str, as_of: str, name: str, cache: dict):
    """One raw metric for one company, from whichever engine owns it."""
    if name in cache:
        return cache[name]
    v = None
    if name in val.ALL_MULTIPLES:
        m = cache.get("_mult") or val.multiples(conn, ticker, as_of)
        cache["_mult"] = m
        if m.get("available"):
            # A multiple excluded for this industry is NOT scored. Ranking a
            # bank on EV/EBITDA would rank it on an artefact.
            if name not in m.get("excluded_for_industry", []):
                v = m["multiples"].get(name)
    elif name == "margin_of_safety":
        t = cache.get("_iv") or intrinsic.triangulate(conn, ticker, as_of)
        cache["_iv"] = t
        if t.get("median") and t.get("price"):
            v = t["median"] / t["price"] - 1.0
    elif name == "revenue_growth":
        h = intrinsic.annual_history(conn, ticker, as_of, "revenue")
        v = intrinsic._cagr(h) if len(h) >= 3 else None
    else:
        s = cache.get("_stm") or stm.analyse(conn, ticker, as_of)
        cache["_stm"] = s
        if s.get("available"):
            v = s["statement"].get(name)
            if v is None and name == "roic":
                v = s["statement"].get("roce")
    cache[name] = v
    return v


def _panel_metrics(conn, as_of: str, division: str, limit: int) -> dict:
    """Every metric for every company in one industry. Built once per run."""
    tickers = [r[0] for r in conn.execute(
        "SELECT DISTINCT ticker FROM sec_filings WHERE ticker IS NOT NULL "
        "AND first_tradeable IS NOT NULL AND first_tradeable <= ? "
        f"ORDER BY ticker LIMIT {int(limit)}", (as_of,))]
    wanted = {m for spec in DIMENSIONS.values() for m, _ in spec}
    out = {}
    for t in tickers:
        ind = industry.classify_as_of(conn, t, as_of)
        if ind["division"] != division:
            continue
        cache: dict = {}
        out[t] = {m: _metric(conn, t, as_of, m, cache) for m in wanted}
    return out


def _percentile(values: list, x, higher_is_better: bool,
                positive_only: bool = False):
    """Where x sits among peers, 0-100. None when x or the peer set is absent."""
    if x is None:
        return None
    if positive_only and x <= 0:
        return None
    peers = [v for v in values if v is not None
             and (not positive_only or v > 0)]
    if len(peers) < 5:
        # A percentile against four companies is not a percentile. Returning
        # one would let a thin industry manufacture extreme scores.
        return None
    # "Better than" depends on the metric: a low P/E is good, a low margin is
    # not. Getting this backwards would rank the worst companies highest and
    # the output would look entirely reasonable.
    below = (sum(1 for v in peers if v < x) if higher_is_better
             else sum(1 for v in peers if v > x))
    return 100.0 * below / len(peers)


def _filing_age(conn, ticker: str, as_of: str):
    """Days between the newest tradeable filing and the valuation date."""
    import datetime as dt
    r = conn.execute("""SELECT MAX(first_tradeable) FROM sec_filings
        WHERE ticker=? AND first_tradeable IS NOT NULL
          AND first_tradeable <= ?""", (ticker, as_of)).fetchone()
    if not r or not r[0]:
        return None
    try:
        return (dt.date.fromisoformat(as_of) - dt.date.fromisoformat(r[0])).days
    except ValueError:
        return None


def score_division(conn, as_of: str, division: str,
                   weighting: str = DEFAULT_WEIGHTING, limit: int = 600) -> list:
    if weighting not in WEIGHTINGS:
        raise SystemExit(f"unknown weighting {weighting!r}; "
                         f"have {sorted(WEIGHTINGS)}")
    w = WEIGHTINGS[weighting]
    panel = _panel_metrics(conn, as_of, division, limit)
    if not panel:
        return []

    by_metric = {m: [d.get(m) for d in panel.values()]
                 for m in {mm for spec in DIMENSIONS.values() for mm, _ in spec}}

    rows = []
    for t, metrics in panel.items():
        dims, detail = {}, {}
        for dim, spec in DIMENSIONS.items():
            parts = []
            for m, higher in spec:
                p = _percentile(by_metric[m], metrics.get(m), higher,
                                positive_only=m in POSITIVE_ONLY)
                raw = metrics.get(m)
                detail[m] = {"raw": raw, "percentile": p,
                             "higher_is_better": higher, "dimension": dim,
                             "excluded_negative": bool(
                                 m in POSITIVE_ONLY and raw is not None
                                 and raw <= 0)}
                if p is not None:
                    parts.append(p)
            dims[dim] = statistics.fmean(parts) if parts else None
        scored = [d for d, v in dims.items() if v is not None]
        composite = None
        if len(scored) >= MIN_DIMENSIONS:
            num = sum(dims[d] * w.get(d, 1.0) for d in scored)
            den = sum(w.get(d, 1.0) for d in scored)
            composite = num / den if den else None
        stale_days = _filing_age(conn, t, as_of)
        rows.append({"ticker": t, "division": division, "as_of": as_of,
                     "weighting": weighting, "composite": composite,
                     "filing_age_days": stale_days,
                     "stale": bool(stale_days is not None
                                   and stale_days > STALE_FILING_DAYS),
                     "dimensions": dims, "detail": detail,
                     "dimensions_scored": len(scored),
                     "dimensions_total": len(DIMENSIONS)})
    rows.sort(key=lambda r: (r["composite"] is None, -(r["composite"] or 0)))
    return rows


def explain(row: dict) -> str:
    """Why this company scores what it scores. The spec asks for this by name."""
    L = ["", f"  {row['ticker']} — value score under '{row['weighting']}'",
         f"  industry: {row['division']}",
         f"  scored on {row['dimensions_scored']} of {row['dimensions_total']} "
         f"dimensions",
         f"  newest filing is {row.get('filing_age_days')} days old"
         + ("   *** STALE ***" if row.get("stale") else ""),
         "  " + "-" * 66]
    if row["composite"] is None:
        L += [f"  NO COMPOSITE. Fewer than {MIN_DIMENSIONS} dimensions could be",
              "  scored, and averaging whatever happens to exist would compare",
              "  this company against others measured on more."]
    else:
        L.append(f"  COMPOSITE {row['composite']:.1f} / 100")
    L += ["", f"  {'dimension':<16}{'score':>8}   inputs"]
    for dim, v in row["dimensions"].items():
        val_txt = "—" if v is None else f"{v:.0f}"
        ins = []
        for m, d in row["detail"].items():
            if d["dimension"] != dim:
                continue
            raw = "—" if d["raw"] is None else format(d["raw"], ",.2f")
            if d.get("excluded_negative"):
                ins.append(f"{m}={raw}(negative — not ranked)")
            else:
                pc = ("" if d["percentile"] is None
                      else format(d["percentile"], ".0f"))
                ins.append(f"{m}={raw}({pc})")
        L.append(f"  {dim:<16}{val_txt:>8}   {', '.join(ins)}")
    L += ["", "  Each number in brackets is a percentile WITHIN this industry,",
          "  never across the market. A dash means the input was not reported —",
          "  which is not the same as it being zero or average.", ""]
    return "\n".join(L)


def watchlist(conn, as_of: str, division: str, weighting: str = DEFAULT_WEIGHTING,
              top: int = 15, limit: int = 600) -> dict:
    rows = score_division(conn, as_of, division, weighting, limit)
    scored = [r for r in rows if r["composite"] is not None]
    enriched = []
    for r in scored[:top]:
        t = intrinsic.triangulate(conn, r["ticker"], as_of)
        s = stm.analyse(conn, r["ticker"], as_of)
        enriched.append({
            **r, "price": t.get("price"), "intrinsic": t.get("median"),
            "margin_of_safety": (t["median"] / t["price"] - 1.0)
            if (t.get("median") and t.get("price")) else None,
            "n_methods": t.get("n_methods", 0),
            "method_spread": t.get("method_spread"),
            "filing_date": (s.get("filing") or {}).get("first_tradeable")
            if s.get("available") else None,
        })
    return {"division": division, "as_of": as_of, "weighting": weighting,
            "rows": enriched, "n_scored": len(scored), "n_in_division": len(rows)}


def render_watchlist(wl: dict) -> str:
    L = ["", f"  VALUE WATCHLIST — {wl['division']} as of {wl['as_of']}",
         f"  weighting '{wl['weighting']}' — one of several under test, not a "
         f"final formula",
         f"  {wl['n_scored']} of {wl['n_in_division']} companies could be scored "
         f"at all", "  " + "-" * 92,
         f"  {'ticker':<8}{'score':>7}{'dims':>6}{'price':>10}{'intrinsic':>11}"
         f"{'margin':>9}{'spread':>8}  filing"]
    for r in wl["rows"]:
        f = lambda v, p=",.2f": "—" if v is None else format(v, p)  # noqa: E731
        L.append(f"  {r['ticker']:<8}{r['composite']:>7.1f}"
                 f"{r['dimensions_scored']:>4}/{r['dimensions_total']:<1}"
                 f"{f(r['price']):>10}{f(r['intrinsic']):>11}"
                 f"{('—' if r['margin_of_safety'] is None else format(r['margin_of_safety'], '+.0%')):>9}"
                 f"{('—' if r['method_spread'] is None else format(r['method_spread'], '.1f') + 'x'):>8}"
                 f"  {r['filing_date'] or '—'}"
                 + ("   STALE" if r.get("stale") else ""))
    L += ["  " + "-" * 92,
          "  'dims' is how many of the nine dimensions could be scored. A score",
          "  over four dimensions is NOT comparable to one over nine — the",
          "  dimensions a company is missing are usually the ones where thin",
          "  disclosure and weak fundamentals travel together.",
          "",
          f"  STALE means the newest filing is over {STALE_FILING_DAYS} days old.",
          "  Those fundamentals are not wrong, they describe a different company",
          "  than the one trading today.",
          "",
          "  'spread' is how far the intrinsic-value methods disagree. Above 3x",
          "  the intrinsic figure is an assumption, not an estimate.", ""]
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--division", default="manufacturing")
    ap.add_argument("--as-of", default="2026-09-21")
    ap.add_argument("--weighting", default=DEFAULT_WEIGHTING)
    ap.add_argument("--explain", metavar="TICKER")
    ap.add_argument("--weightings", action="store_true")
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--limit", type=int, default=600)
    a = ap.parse_args()

    if a.weightings:
        print("\n  WEIGHTINGS UNDER TEST (none is final — the spec says the")
        print("  scoring system must itself become an experiment)")
        for k, w in WEIGHTINGS.items():
            top = ", ".join(f"{d} {v:g}" for d, v in
                            sorted(w.items(), key=lambda kv: -kv[1])[:4])
            mark = "  <- control" if k == "equal" else ""
            print(f"    {k:<16}{top}{mark}")
        return 0

    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    if a.explain:
        ind = industry.classify_as_of(conn, a.explain, a.as_of)
        rows = score_division(conn, a.as_of, ind["division"], a.weighting, a.limit)
        row = next((r for r in rows if r["ticker"] == a.explain), None)
        if not row:
            print(f"\n  {a.explain} is not in the {ind['division']} panel\n")
            conn.close(); return 1
        print(explain(row))
        conn.close(); return 0

    print(render_watchlist(watchlist(conn, a.as_of, a.division, a.weighting,
                                     a.top, a.limit)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
