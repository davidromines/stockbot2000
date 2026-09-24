"""
Regression test for regimes.py (Phase 6 §21) and the rate regimes in robustness.

Pinned: definitions come from config and are fixed levels, not window
percentiles; the rate known on a date is the latest published ON OR BEFORE it
(no look-ahead); a missing series is UNAVAILABLE, never guessed; FRED's '.'
days are dropped; the fallback runs only when the primary returns nothing;
a regime with enough observations and negative net is flagged.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import regimes

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def db():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    days = pd.bdate_range("2021-01-01", periods=500).strftime("%Y-%m-%d")
    px = 100 * np.cumprod(1 + np.r_[np.full(300, 0.002), np.full(200, -0.003)])
    for d, p in zip(days, px):
        c.execute("INSERT INTO prices VALUES ('SPY', ?, ?)", (d, p))
    return c, list(days)       # deliberately uncommitted: a missing-table probe must not roll it back


def main():
    csv = "DATE,DGS3MO\n2021-01-04,0.09\n2021-01-05,.\n2022-06-01,1.10\n2022-09-01,3.00\n"
    f = regimes.parse_fred(csv, "DGS3MO")
    check("FRED '.' days dropped", len(f) == 3 and f["value"].tolist() == [0.09, 1.10, 3.00])
    f2 = regimes.parse_fred(csv.replace("DATE", "observation_date"), "DGS3MO")
    check("FRED's newer header accepted", len(f2) == 3)

    c, days = db()
    check("no rates series: rate regimes unavailable",
          regimes.labels(c, days[260], days[-1])["high_rate"].isna().all())

    calls = []
    r = regimes.load_rates(c, {}, fetchers=[
        ("DGS3MO", "fred", lambda: calls.append("fred") or pd.DataFrame(columns=["date", "value"])),
        ("DGS3MO", "yfinance_^IRX", lambda: calls.append("irx") or f)])
    check("fallback used only when the primary is empty", calls == ["fred", "irx"] and r["source"] == "yfinance_^IRX")
    regimes.load_rates(c, {}, fetchers=[("DGS3MO", "fred", lambda: f)])
    check("reload is idempotent", c.execute("SELECT COUNT(*) FROM rates").fetchone()[0] == 3)

    lab = regimes.labels(c, days[260], days[-1], {"regimes": {"high_rate_pct": 2.0}})
    by = dict(zip(lab["date"], lab["high_rate"]))
    check("rate known on a date = latest published on or before it",
          by.get("2022-06-01") == False and by.get("2022-08-31") == False and by.get("2022-09-01") == True,  # noqa: E712
          (by.get("2022-06-01"), by.get("2022-09-01")))
    lab5 = regimes.labels(c, days[260], days[-1], {"regimes": {"high_rate_pct": 1.0}})
    check("threshold comes from config", dict(zip(lab5["date"], lab5["high_rate"])).get("2022-06-01") == True)  # noqa: E712
    check("SPY regimes present", {"bull", "high_vol", "crisis"} <= set(lab.columns) and lab["bull"].any()
          and (~lab["bull"]).any())

    pnl = pd.DataFrame({"date": lab["date"], "pnl_usd": np.where(lab["bull"], 1.0, -1.0)})
    b = regimes.breakdown(pnl, lab, min_obs=20)
    check("bear flagged negative, bull not", "bear" in b["negative_regimes"] and "bull" not in b["negative_regimes"], b)
    check("all eight regimes reported", set(b["by_regime"]) == {"bull", "bear", "high_vol", "low_vol", "crisis",
                                                                 "normal", "high_rate", "low_rate"})

    c.execute("CREATE TABLE paper_equity (run_id TEXT, date TEXT, equity_usd REAL)")
    for i, d in enumerate(days[400:420]):
        c.execute("INSERT INTO paper_equity VALUES ('r1', ?, ?)", (d, 100 + i))
    fw = regimes.forward(c, {})
    check("forward breakdown per fund", "paper:r1" in fw and sum(v.get("obs", 0) for k, v in
          fw["paper:r1"]["by_regime"].items() if k in ("bull", "bear")) == 19, fw)
    print(regimes.render_forward(fw))

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
