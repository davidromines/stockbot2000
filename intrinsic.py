"""
Intrinsic value: five methods, and the honesty machinery around them. Phase 9, item 28.

WHAT MAKES THIS DIFFERENT FROM EVERY OTHER MODULE HERE
--------------------------------------------------------
Everything else in this project measures what already happened. A DCF
**forecasts**: revenue growth, margins, a discount rate, a terminal growth
rate. It will produce a confident-looking number from assumptions nobody can
validate, and the number carries no warning that it is mostly assumption.

This project's entire record is of confident numbers that turned out to be
artifacts. A DCF is the easiest place yet to manufacture one, so three things
are built in rather than offered:

**1. The terminal-value share is reported with every DCF.** In a typical
10-year model the terminal value is 60-80% of the total. Above
`TERMINAL_SHARE_ALARM` the engine says plainly that the valuation is mostly a
guess about the far future — because at 85% you are not valuing a business, you
are valuing a perpetuity assumption with a decade of detail stapled to the
front.

**2. Sensitivity is mandatory, not optional.** Every DCF returns a grid over
discount rate and terminal growth. A value that swings 3x across plausible
inputs is reported as a range, and `spread_ratio` states it in one number. A
point estimate without that range is the specific artifact this guards against.

**3. Refusal is the common outcome.** A DCF needs several years of positive,
reasonably stable free cash flow. Most companies in this database do not have
that — debt is tagged for 38% of filers and EBITDA for 58% — so the engine is
expected to refuse more companies than it values. Padding with defaults would
convert "we cannot value this" into a number, which is the worst possible
trade.

WHY FIVE METHODS AND NOT ONE
------------------------------
`triangulate()` runs them all and reports the spread. Agreement between
independent methods is weak evidence; disagreement is strong evidence that at
least one is wrong. A single method cannot tell you which situation you are in,
and the spread is more informative than any individual point estimate.

**Nothing here is a recommendation.** These are estimates under stated
assumptions, and the assumptions are returned alongside every figure.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import statistics

import industry
import statements as stm
import storage
import valuation as val
import value_metrics as vm
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("intrinsic")

# Defaults, all overridable and all reported with the result. They are starting
# points for a sensitivity grid, never a house view about any company.
DISCOUNT_RATE = 0.10
TERMINAL_GROWTH = 0.025      # below long-run GDP: nothing grows faster forever
FORECAST_YEARS = 10
TAX_RATE = 0.21

MIN_HISTORY_YEARS = 4        # below this, a growth rate is one observation
TERMINAL_SHARE_ALARM = 0.75  # above this the DCF is mostly a perpetuity guess
MAX_SANE_GROWTH = 0.25       # a rate no company sustains for a decade
# Standard deviation of year-on-year LOG changes in free cash flow. Above this
# the history is too erratic for a compound rate to describe: the series has no
# trend, only endpoints. Roughly 0.1 is a steady compounder and 0.5 is lumpy.
STABILITY_ALARM = 0.75


def annual_history(conn, ticker: str, as_of: str, key: str,
                   max_filings: int = 40) -> list:
    """
    [(period, value)] of full-year figures, oldest first, deduplicated.

    Only filings tradeable by `as_of`, so a forecast built here could have been
    built then. Deduplicated by period because the same fiscal year appears in
    an original filing and again in any amendment.
    """
    rows = conn.execute("""SELECT adsh, period FROM sec_filings
        WHERE ticker=? AND first_tradeable IS NOT NULL AND first_tradeable <= ?
        ORDER BY first_tradeable DESC LIMIT ?""",
        (ticker, as_of, int(max_filings))).fetchall()
    seen, out = set(), []
    for r in rows:
        if r["period"] in seen:
            continue
        v = stm._pick(vm._facts_for(conn, r["adsh"]), key, val.ANNUAL)
        if v is not None:
            seen.add(r["period"])
            out.append((r["period"], float(v)))
    return sorted(out)


def _cagr(series: list):
    """Compound growth between first and last. None if signs make it nonsense."""
    if len(series) < 2:
        return None
    first, last = series[0][1], series[-1][1]
    if first <= 0 or last <= 0:
        # A growth rate across a sign change is not a growth rate. Reporting one
        # would give a company that went from -100 to +100 an enormous
        # "improvement" that says nothing about its future.
        return None
    years = len(series) - 1
    return (last / first) ** (1.0 / years) - 1.0


def _stability(series: list):
    """
    Volatility of year-on-year LOG changes in free cash flow. Lower is steadier.

    Not the coefficient of variation of growth rates, which was the first
    attempt and is unusable in both directions: it explodes when the mean
    growth rate is near zero (Ford scored 38.8 on an unremarkable series) and
    it SHRINKS when a company alternates violently, because the huge positive
    swings pull the mean up faster than the spread. A fixture swinging between
    $20M and $8,000M scored 0.93 — lower than a steadier one.

    Log changes are symmetric — a halving and a doubling are equal and
    opposite — and their standard deviation does not depend on the mean at all.
    Roughly: 0.1 is a steady compounder, 0.5 is lumpy, above 1.0 the series has
    no trend a compound rate can describe.
    """
    import math
    vals = [v for _, v in series if v > 0]
    if len(vals) < 3:
        return None
    logs = [math.log(b / a) for a, b in zip(vals, vals[1:])]
    if len(logs) < 2:
        return None
    return statistics.pstdev(logs)


def dcf(conn, ticker: str, as_of: str, discount: float = DISCOUNT_RATE,
        terminal_growth: float = TERMINAL_GROWTH,
        years: int = FORECAST_YEARS, growth: float | None = None) -> dict:
    """
    Discounted cash flow, following the spec's chain, with its own health
    reported alongside the answer.
    """
    def refuse(why):
        return {"ticker": ticker, "as_of": as_of, "method": "dcf",
                "value": None, "refused": True, "reason": why}

    if terminal_growth >= discount:
        return refuse(f"terminal growth {terminal_growth:.1%} is not below the "
                      f"discount rate {discount:.1%}; the perpetuity is "
                      f"infinite and the model has no answer")

    ocf_hist = annual_history(conn, ticker, as_of, "ocf")
    capex_hist = dict(annual_history(conn, ticker, as_of, "capex"))
    fcf_hist = [(p, v - abs(capex_hist[p])) for p, v in ocf_hist
                if p in capex_hist]
    if len(fcf_hist) < MIN_HISTORY_YEARS:
        return refuse(f"only {len(fcf_hist)} years of free cash flow available; "
                      f"{MIN_HISTORY_YEARS} are needed before a growth rate is "
                      f"anything but a single observation")
    if fcf_hist[-1][1] <= 0:
        return refuse("latest free cash flow is not positive; a DCF on negative "
                      "cash flow values the assumption that it turns around, "
                      "not the business")

    if growth is None:
        growth = _cagr(fcf_hist)
        if growth is None:
            return refuse("free cash flow changes sign across the history, so "
                          "no growth rate can be estimated from it")
    # A company cannot compound at 40% for a decade. Capping is itself an
    # assumption and is reported as one rather than applied silently.
    capped = growth > MAX_SANE_GROWTH
    growth = min(growth, MAX_SANE_GROWTH)

    base = fcf_hist[-1][1]
    flows, pv_sum = [], 0.0
    for t in range(1, years + 1):
        f = base * ((1 + growth) ** t)
        pv = f / ((1 + discount) ** t)
        flows.append({"year": t, "fcf": f, "pv": pv})
        pv_sum += pv
    terminal = (flows[-1]["fcf"] * (1 + terminal_growth)
                / (discount - terminal_growth))
    pv_terminal = terminal / ((1 + discount) ** years)
    ev = pv_sum + pv_terminal

    s = stm.analyse(conn, ticker, as_of)
    st = s.get("statement", {}) if s.get("available") else {}
    cash, debt = st.get("cash"), st.get("debt")
    equity_value = None if (cash is None or debt is None) else ev - debt + cash
    cap, shares = val.market_cap(conn, ticker, as_of)
    per_share = (equity_value / shares) if (equity_value is not None
                                            and shares) else None

    terminal_share = pv_terminal / ev if ev else None
    return {
        "ticker": ticker, "as_of": as_of, "method": "dcf", "refused": False,
        "enterprise_value": ev, "equity_value": equity_value,
        "value_per_share": per_share, "market_cap": cap,
        "upside": (None if (equity_value is None or not cap)
                   else equity_value / cap - 1.0),
        "assumptions": {"discount_rate": discount, "growth": growth,
                        "growth_capped": capped, "terminal_growth": terminal_growth,
                        "years": years, "base_fcf": base,
                        "history_years": len(fcf_hist)},
        "terminal_value_pv": pv_terminal, "terminal_share": terminal_share,
        "terminal_alarm": bool(terminal_share and terminal_share > TERMINAL_SHARE_ALARM),
        "fcf_stability": (stab := _stability(fcf_hist)),
        "stability_alarm": bool(stab is not None and stab > STABILITY_ALARM),
        "equity_bridge_available": equity_value is not None,
    }


def sensitivity(conn, ticker: str, as_of: str,
                discounts=(0.07, 0.09, 0.10, 0.11, 0.13),
                terminals=(0.01, 0.02, 0.025, 0.03, 0.035)) -> dict:
    """
    The DCF across plausible inputs. Returned with every valuation, never on
    request — a point estimate is the artifact this exists to prevent.
    """
    grid, vals = [], []
    for d in discounts:
        row = []
        for g in terminals:
            if g >= d:
                row.append(None)
                continue
            r = dcf(conn, ticker, as_of, discount=d, terminal_growth=g)
            v = None if r["refused"] else r.get("value_per_share")
            row.append(v)
            if v is not None and v > 0:
                vals.append(v)
        grid.append({"discount": d, "values": row})
    if not vals:
        return {"grid": grid, "terminals": list(terminals), "usable": False}
    lo, hi = min(vals), max(vals)
    return {"grid": grid, "terminals": list(terminals), "usable": True,
            "low": lo, "high": hi, "median": statistics.median(vals),
            # The number that matters. Above ~3 the model is not telling you
            # what a company is worth, it is telling you what you assumed.
            "spread_ratio": (hi / lo) if lo > 0 else None}


def earnings_value(conn, ticker: str, as_of: str, division: str | None = None,
                   limit: int = 400) -> dict:
    """Normalised earnings times the median P/E of its industry."""
    hist = annual_history(conn, ticker, as_of, "net_income")
    if len(hist) < 3:
        return {"method": "earnings", "value": None, "refused": True,
                "reason": f"only {len(hist)} years of earnings; a normalised "
                          f"figure needs at least 3"}
    norm = statistics.fmean([v for _, v in hist[-5:]])
    if norm <= 0:
        return {"method": "earnings", "value": None, "refused": True,
                "reason": "normalised earnings are not positive"}
    div = division or industry.classify_as_of(conn, ticker, as_of)["division"]
    r = val.rank_within(conn, div, "pe", as_of, limit)
    if r.get("refused") or not r["ranked"]:
        return {"method": "earnings", "value": None, "refused": True,
                "reason": f"no usable P/E distribution for {div}"}
    med = statistics.median([x["value"] for x in r["ranked"]])
    _, shares = val.market_cap(conn, ticker, as_of)
    return {"method": "earnings", "refused": False, "value": norm * med,
            "value_per_share": (norm * med / shares) if shares else None,
            "assumptions": {"normalised_earnings": norm, "industry": div,
                            "industry_median_pe": med,
                            "peers_in_median": r["n_ranked"],
                            "peer_coverage": r["coverage"]}}


def fcf_value(conn, ticker: str, as_of: str, discount: float = DISCOUNT_RATE,
              growth: float = TERMINAL_GROWTH) -> dict:
    """
    Sustainable FCF as a perpetuity. A deliberately crude cross-check on the
    DCF: no forecast period, so it cannot inherit the DCF's growth assumption.
    """
    ocf = annual_history(conn, ticker, as_of, "ocf")
    capex = dict(annual_history(conn, ticker, as_of, "capex"))
    fcf = [v - abs(capex[p]) for p, v in ocf if p in capex]
    if len(fcf) < 3:
        return {"method": "fcf_perpetuity", "value": None, "refused": True,
                "reason": f"only {len(fcf)} years of free cash flow"}
    sustainable = statistics.median(fcf[-5:])
    if sustainable <= 0:
        return {"method": "fcf_perpetuity", "value": None, "refused": True,
                "reason": "median free cash flow is not positive"}
    if growth >= discount:
        return {"method": "fcf_perpetuity", "value": None, "refused": True,
                "reason": "growth is not below the discount rate"}
    ev = sustainable * (1 + growth) / (discount - growth)
    _, shares = val.market_cap(conn, ticker, as_of)
    return {"method": "fcf_perpetuity", "refused": False, "value": ev,
            "value_per_share": (ev / shares) if shares else None,
            "assumptions": {"sustainable_fcf": sustainable,
                            "discount_rate": discount, "growth": growth,
                            "years_used": len(fcf[-5:])}}


def asset_value(conn, ticker: str, as_of: str) -> dict:
    """
    Tangible book value. Meaningful for asset-heavy businesses and close to
    meaningless for asset-light ones, which is stated rather than assumed away.
    """
    a = stm.analyse(conn, ticker, as_of)
    if not a.get("available"):
        return {"method": "asset", "value": None, "refused": True,
                "reason": a.get("reason")}
    tbv = a["statement"].get("tangible_book_value")
    if tbv is None:
        return {"method": "asset", "value": None, "refused": True,
                "reason": "tangible book value is not computable"}
    _, shares = val.market_cap(conn, ticker, as_of)
    div = a["industry"]["division"]
    light = div in ("services",)
    return {"method": "asset", "refused": False, "value": tbv,
            "value_per_share": (tbv / shares) if shares else None,
            "caveat": ("asset-light industry: tangible book understates a "
                       "business whose value is people and software"
                       if light else None),
            "assumptions": {"industry": div}}


def triangulate(conn, ticker: str, as_of: str) -> dict:
    """
    Every method, plus the spread between them.

    Disagreement is the useful signal. Methods agreeing is weak evidence;
    methods disagreeing by 5x is strong evidence that at least one set of
    assumptions is wrong, and a single method cannot tell you which.
    """
    d = dcf(conn, ticker, as_of)
    methods = {"dcf": d, "earnings": earnings_value(conn, ticker, as_of),
               "fcf_perpetuity": fcf_value(conn, ticker, as_of),
               "asset": asset_value(conn, ticker, as_of)}
    ps = {k: v.get("value_per_share") for k, v in methods.items()
          if not v.get("refused") and v.get("value_per_share")}
    cap, shares = val.market_cap(conn, ticker, as_of)
    price = (cap / shares) if (cap and shares) else None
    out = {"ticker": ticker, "as_of": as_of, "methods": methods,
           "price": price, "per_share": ps,
           "n_methods": len(ps), "sensitivity": None}
    if ps:
        lo, hi = min(ps.values()), max(ps.values())
        out.update({"low": lo, "high": hi,
                    "median": statistics.median(list(ps.values())),
                    "method_spread": (hi / lo) if lo > 0 else None})
    if not d["refused"]:
        out["sensitivity"] = sensitivity(conn, ticker, as_of)
    return out


def render(t: dict) -> str:
    price = t["price"]
    price_txt = "—" if price is None else format(price, ",.2f")
    L = ["", f"  {t['ticker']} — intrinsic value as of {t['as_of']}",
         f"  market price per share: {price_txt}",
         "  " + "-" * 64,
         f"  {'method':<18}{'per share':>14}{'vs price':>12}   note"]
    for name, m in t["methods"].items():
        if m.get("refused"):
            L.append(f"  {name:<18}{'REFUSED':>14}{'':>12}   {m['reason'][:34]}")
            continue
        v = m.get("value_per_share")
        rel = f"{v / price - 1:+.0%}" if (v and price) else "—"
        note = m.get("caveat") or ""
        L.append(f"  {name:<18}{(format(v, ',.2f') if v else '—'):>14}"
                 f"{rel:>12}   {note[:34]}")
    L.append("  " + "-" * 64)

    d = t["methods"]["dcf"]
    if not d["refused"]:
        a = d["assumptions"]
        L += ["", "  DCF HEALTH", "  " + "-" * 64,
              f"  growth from {a['history_years']} years of history: "
              f"{a['growth']:.1%}" + ("  (CAPPED)" if a["growth_capped"] else ""),
              f"  discount {a['discount_rate']:.1%}, terminal growth "
              f"{a['terminal_growth']:.1%}, {a['years']} years",
              f"  terminal value is {d['terminal_share']:.0%} of the total"]
        if d["terminal_alarm"]:
            L += ["",
                  "  *** THIS VALUATION IS MOSTLY A GUESS ABOUT THE FAR FUTURE.",
                  f"  {d['terminal_share']:.0%} of it is the perpetuity, not the "
                  f"forecast period. You are",
                  "  valuing an assumption with a decade of detail stapled to "
                  "the front. ***"]
        if d.get("fcf_stability") is not None:
            L.append(f"  FCF growth variability: {d['fcf_stability']:.2f} "
                     f"(a low number is steadier)")
        if d.get("stability_alarm"):
            L += ["",
                  "  *** THE GROWTH RATE IS ARITHMETIC, NOT A FORECAST.",
                  f"  Year-on-year free cash flow moves with a log volatility "
                  f"of {d['fcf_stability']:.2f},",
                  "  so a compound rate fitted to it describes the endpoints and "
                  "nothing",
                  "  in between. The DCF below inherits that. ***"]
        if not d["equity_bridge_available"]:
            L.append("  NOTE: debt or cash missing, so no equity value — "
                     "enterprise value only.")

    s = t.get("sensitivity")
    if s and s.get("usable"):
        L += ["", "  SENSITIVITY — per-share value across plausible inputs",
              "  " + "-" * 64,
              "  discount \\ terminal   " + "".join(f"{g:>10.1%}" for g in s["terminals"])]
        for row in s["grid"]:
            cells = "".join(f"{(format(v, ',.0f') if v else '—'):>10}"
                            for v in row["values"])
            L.append(f"  {row['discount']:>18.1%}   {cells}")
        L += ["", f"  range {s['low']:,.2f} to {s['high']:,.2f}   "
                  f"spread {s['spread_ratio']:.1f}x" if s.get("spread_ratio")
              else ""]
        if s.get("spread_ratio") and s["spread_ratio"] > 3:
            L.append("  A spread this wide means the model is reporting your "
                     "assumptions,")
            L.append("  not the company. Treat the range as the answer, not the "
                     "midpoint.")
    if t.get("method_spread"):
        L += ["", f"  {t['n_methods']} methods span {t['method_spread']:.1f}x "
                  f"({t['low']:,.2f} to {t['high']:,.2f}).",
              "  Disagreement between independent methods is the useful signal:",
              "  it means at least one set of assumptions is wrong."]
    L += ["", "  These are estimates under stated assumptions, not "
              "recommendations.", ""]
    return "\n".join(x for x in L if x is not None)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ticker", required=True)
    ap.add_argument("--as-of", default="2026-09-21")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    print(render(triangulate(conn, a.ticker, a.as_of)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
