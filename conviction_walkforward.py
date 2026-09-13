"""
Walk-forward the conviction screens. The test the backtest cannot pass on its own.

`conviction.py` reported deep_value at +18.4% CAGR against SPY's +14.1% over
2010-2026. That is one number from one window, and this project has produced six
of those which were all wrong. The Lab has 31-fold walk-forward machinery for
exactly this reason; the conviction book had none, and that gap is the difference
between "a backtest that beat SPY" and "a result".

WHAT THIS ACTUALLY TESTS, AND WHAT IT CANNOT
--------------------------------------------
These screens have **no fitted parameters**. Piotroski's nine tests, Novy-Marx's
gross profitability, Greenblatt's two ranks — all were published before our data
begins, so there is no in-sample period to overfit and no coefficients to leak.
Walk-forward here is therefore not testing for parameter overfitting. It is
testing something more useful: **regime stability**. Does the edge exist in every
period, or is one lucky stretch carrying the whole sixteen years?

That distinction matters because 2010-2026 is mostly one long bull market. A
strategy that beat SPY only in 2020-2021 and lost the rest of the time would show
an excellent full-period CAGR and be worthless going forward.

Each window is scored against SPY over the *same dates*, because a screen earning
12% in a year the market made 25% has lost, and one losing 5% while the market
lost 20% has won. Absolute returns per window would mostly measure what the
market did.

Usage:
    python conviction_walkforward.py --screen quality_value
    python conviction_walkforward.py --all
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import conviction as cv
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("conv_wf")


def windows(start="2010-01-01", end="2026-09-11", years=2, step=1):
    """Rolling, overlapping windows. Overlap gives more observations from a
    short history; the cost is that adjacent windows are not independent, which
    is why the headline below is the win *count*, not a t-statistic."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    out = []
    cur = s
    while cur + pd.DateOffset(years=years) <= e:
        out.append((str(cur.date()), str((cur + pd.DateOffset(years=years)).date())))
        cur = cur + pd.DateOffset(years=step)
    return out


def run(cfg, screen: str, years=2, step=1, n_hold=20) -> dict:
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    wins = windows(years=years, step=step)
    log.info(f"{screen}: {len(wins)} rolling {years}-year windows")

    rows = []
    for a, b in wins:
        try:
            r = cv.backtest(conn, cfg, screen, a, b, n_hold)
        except SystemExit:
            continue
        bench = cv._benchmark(conn, a, b)
        if not bench:
            continue
        rows.append({"start": a[:7], "end": b[:7], "cagr": r["cagr"],
                     "spy": bench["cagr"], "excess": r["cagr"] - bench["cagr"],
                     "dd": r["max_dd"], "spy_dd": bench["max_dd"],
                     "turnover": r["monthly_turnover"]})
    conn.close()
    if not rows:
        raise SystemExit(f"{screen}: no usable windows.")
    df = pd.DataFrame(rows)
    return {"screen": screen, "windows": df,
            "beat": int((df["excess"] > 0).sum()), "n": len(df),
            "mean_excess": float(df["excess"].mean()),
            "median_excess": float(df["excess"].median()),
            "worst": float(df["excess"].min()),
            "mean_turnover": float(df["turnover"].mean())}


def report(results: list) -> None:
    print(f"\n  CONVICTION WALK-FORWARD — rolling 2-year windows vs SPY over the same dates\n")
    print(f"  {'screen':<20}{'beat SPY':>11}{'mean excess':>14}{'median':>10}"
          f"{'worst':>10}{'turnover':>10}")
    print("  " + "-" * 76)
    for r in sorted(results, key=lambda x: -x["mean_excess"]):
        won = f"{r['beat']}/{r['n']}"
        print(f"  {r['screen']:<20}{won:>11}"
              f"{r['mean_excess']:>+13.1%}{r['median_excess']:>+10.1%}"
              f"{r['worst']:>+10.1%}{r['mean_turnover']:>9.0%}")
    print("\n  `beat SPY` is the number to read. A screen winning in most windows has")
    print("  an edge that survives regimes; one winning in half is indistinguishable")
    print("  from a coin, however good its full-period CAGR looks.")
    print("\n  These screens have no fitted parameters — Piotroski, Novy-Marx and")
    print("  Greenblatt all published before our data begins — so this is not a test")
    print("  for overfitting. It is a test for whether one lucky stretch is carrying")
    print("  sixteen years.")
    print("\n  Windows overlap, so they are not independent observations. Read the win")
    print("  count as a description, not as a significance test.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--screen")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--years", type=int, default=2)
    ap.add_argument("--detail", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    names = list(cv.SCREENS) if (a.all or not a.screen) else [a.screen]
    out = []
    for n in names:
        if n not in cv.SCREENS:
            log.error(f"unknown screen: {n}"); continue
        try:
            r = run(cfg, n, a.years)
            out.append(r)
            log.info(f"  {n}: beat SPY in {r['beat']}/{r['n']} windows, "
                     f"mean excess {r['mean_excess']:+.1%}")
            if a.detail:
                print(r["windows"].to_string(index=False))
        except SystemExit as e:
            log.error(e)
    if out:
        report(out)


if __name__ == "__main__":
    main()
