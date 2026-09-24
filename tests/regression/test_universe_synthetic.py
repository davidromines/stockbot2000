"""
Regression test for universe_synthetic.generate() — the v4 final-year template.

Pinned: a clean exit (merger) ends with a real donor's final year, whole,
with the market component re-applied on its OWN dates and the donor's
no-change days kept; that year is not bent to a cohort percentile; a
performance death keeps the v3 block method (no real failing year exists to
copy); every row says which it got; paths are reproducible from their seed.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import universe_synthetic as us

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    rng = np.random.default_rng(1)
    days = pd.bdate_range("2015-01-01", periods=900).strftime("%Y-%m-%d")
    spy = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.01, len(days))), index=days)
    # The donor's real final year: noise, a +30% announcement jump, then quiet.
    fin = np.r_[rng.normal(0, 0.02, 150), [0.30], rng.normal(0.0002, 0.002, 101)]
    ff = np.zeros(252, dtype=bool)
    ff[200:205] = True
    fin[ff] = 0.0
    donor = {"e": rng.standard_normal(800), "beta": 0.8, "vol": 0.02, "flat": 0.0,
             "e_final": fin, "flat_final": ff}
    art = {"settings": {}, "cohorts": {"all": {"final_year_return": {"p5": -0.6, "p25": -0.3, "p50": 0.0,
                                                                     "p75": 0.1, "p95": 0.3}}}}
    s = {**us.DEFAULTS, "scope_end": "2024-12-31"}
    starts = np.array([10.0, 20.0, 50.0])
    base = {"first_seen": days[0], "last_seen": days[-1], "sic": None, "exchange": "NYSE"}

    m = us.generate({**base, "company_id": "M1", "ticker": "MMM1", "delisting_reason": "acquisition"},
                    spy, [donor], art, starts, s)
    body = m[~m["is_delisting_bar"]]
    r = body["close"].pct_change().to_numpy()[-251:]
    mkt = spy.pct_change().reindex(body["date"]).to_numpy()[-251:]
    # The template covers the last 252 dates; the last one is the delisting bar,
    # so the body's last 251 returns are the template's first 251.
    want = 0.8 * mkt + fin[:-1]
    want[ff[:-1]] = 0.0
    check("merger: final year = beta x ITS market + the donor's real final year",
          np.allclose(r, want, atol=1e-9), float(np.max(np.abs(r - want))))
    check("the announcement jump survives", float(np.max(r)) > 0.25, float(np.max(r)))
    check("the donor's no-change days stay no-change", int((np.abs(r) < 1e-12).sum()) >= 5)
    check("tagged donor_template, v4", set(m["final_year"]) == {"donor_template"}
          and set(m["data_source"]) == {"synthetic_v4"} and set(m["generation_method"]) == {us.METHOD})
    check("merger delisting bar still applied", bool(m["is_delisting_bar"].iloc[-1]))

    p = us.generate({**base, "company_id": "P1", "ticker": "PPP1", "delisting_reason": "bankruptcy"},
                    spy, [donor], art, starts, s)
    check("performance death keeps the v3 blocks", set(p["final_year"]) == {"blocks"})
    pb = p[~p["is_delisting_bar"]]["close"]
    fy = float(pb.iloc[-1] / pb.iloc[-252] - 1)
    check("... and its final year is shaped into the lower tail (p5..p25)", -0.62 <= fy <= -0.28, fy)

    m2 = us.generate({**base, "company_id": "M1", "ticker": "MMM1", "delisting_reason": "acquisition"},
                     spy, [donor], art, starts, s)
    check("reproducible from the seed", m["close"].equals(m2["close"]))

    nd = {**donor, "e_final": None, "flat_final": None}
    b = us.generate({**base, "company_id": "M2", "ticker": "MMM2", "delisting_reason": "acquisition"},
                    spy, [nd], art, starts, s)
    check("no donor with a full final year -> falls back to blocks, tagged so", set(b["final_year"]) == {"blocks"})

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
