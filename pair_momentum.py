"""
Long/inverse ETF switching, across every pair and every leverage level we hold.

THE QUESTION THIS ANSWERS
-------------------------
"ERX and ERY are inverses — why not just hold whichever is going up? And why not
do the same with the S&P ETFs?"

The logic is sound and the first half of the evidence supports it. On ERX/ERY,
momentum switching cut the annual loss from the random-switch median of -26.2%
to -2.2%. It predicts direction usefully. What beat it was not bad prediction,
it was **volatility decay**: a 2x daily-rebalanced fund loses money in a choppy
market even when the index ends flat, so both legs of the pair bleed and every
whipsaw is punished twice — once in fees, once in decay.

That makes leverage the variable worth testing rather than the signal. The same
rule should improve as leverage falls, because the bar it must clear falls with
it. `--compare` runs one method across 1x, 2x and 3x pairs on the same index to
see whether that is actually true, instead of assuming it.

TWO BENCHMARKS, NOT ONE
-----------------------
  random switch   matched to the method's own switch count — does the signal
                  beat coin-flipping at the same turnover?
  buy and hold    the long leg, held throughout — does the switching earn its
                  complexity, or would sitting still have done better?

The second is the one that kills most switching strategies, and it was missing
from the ERX/ERY test. A strategy can beat random comfortably and still be worse
than doing nothing, and in a rising market that is the common case.

Usage:
    python pair_momentum.py --compare              # leverage ladder, S&P
    python pair_momentum.py --pair SPY SH SPY      # one pair
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import costs as costs_mod
import storage
from erx_momentum import METHODS, random_null, run_switch
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("pairs")

# bull, bear, signal source, label. The signal is the UNLEVERAGED index wherever
# one exists: a leveraged fund's own price carries its decay, so momentum
# measured on it is partly a measurement of the bleed rather than of the market.
PAIRS = [
    ("SPY",  "SH",   "SPY", "S&P 1x"),
    ("SSO",  "SDS",  "SPY", "S&P 2x"),
    ("SPXL", "SPXS", "SPY", "S&P 3x"),
    ("QQQ",  "PSQ",  "QQQ", "Nasdaq 1x"),
    ("QLD",  "QID",  "QQQ", "Nasdaq 2x"),
    ("TQQQ", "SQQQ", "QQQ", "Nasdaq 3x"),
    ("IWM",  "RWM",  "IWM", "Russell 1x"),
    ("ERX",  "ERY",  "XLE", "Energy 2x"),
]

SEARCH = ("2010-01-01", "2019-12-31")
VALIDATE = ("2020-01-01", "2022-12-31")


def load_pair(conn, bull, bear, sig, start, end) -> pd.DataFrame:
    tick = tuple({bull, bear, sig})
    ph = ",".join("?" * len(tick))
    df = pd.read_sql_query(
        f'SELECT ticker, date, "open" AS open, close FROM prices '
        f"WHERE ticker IN ({ph}) AND date BETWEEN ? AND ? AND close > 0",
        conn, params=(*tick, start, end))
    if df.empty:
        return df
    w = df.pivot(index="date", columns="ticker", values=["open", "close"])
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    w = w.dropna().sort_index()
    # run_switch is written against ERX/ERY column names; alias so one tested
    # implementation serves every pair rather than being copied per pair.
    w["open_ERX"], w["close_ERX"] = w[f"open_{bull}"], w[f"close_{bull}"]
    w["open_ERY"], w["close_ERY"] = w[f"open_{bear}"], w[f"close_{bear}"]
    w["close_XLE"] = w[f"close_{sig}"]
    return w


def buy_and_hold(w: pd.DataFrame, leg: str = "ERX") -> float:
    """CAGR of simply holding the long leg. The benchmark that kills switching."""
    o = w[f"open_{leg}"].to_numpy(); c = w[f"close_{leg}"].to_numpy()
    if len(c) < 2 or o[1] <= 0:
        return 0.0
    years = max((pd.Timestamp(w.index[-1]) - pd.Timestamp(w.index[0])).days / 365.25, 1e-9)
    return float((c[-1] / o[1]) ** (1 / years) - 1)


def best_method(conn, cfg, bull, bear, sig, window) -> dict:
    cm = costs_mod.CostModel(cfg)
    w = load_pair(conn, bull, bear, sig, *window)
    if w.empty or len(w) < 300:
        return {}
    px = w["close_XLE"]
    best = None
    for name, (fn, params) in METHODS.items():
        for p in params:
            for mh in (1, 5, 10, 20):
                try:
                    r = run_switch(w, fn(px, p), cm, min_hold=mh)
                except Exception:
                    continue
                if best is None or r["cagr"] > best["cagr"]:
                    best = {**r, "method": name, "param": p, "min_hold": mh}
    if not best:
        return {}
    best["bh"] = buy_and_hold(w)
    best["null"] = random_null(w, best["n_switches"], cm, trials=120)
    best["w"] = w
    return best


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--compare", action="store_true")
    ap.add_argument("--pair", nargs=3, metavar=("BULL", "BEAR", "SIGNAL"))
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    todo = ([(a.pair[0], a.pair[1], a.pair[2], "custom")] if a.pair else PAIRS)
    print(f"\n  LONG/INVERSE SWITCHING — search window {SEARCH[0]} to {SEARCH[1]}")
    print("  Best momentum method per pair, against BOTH benchmarks.")
    print("  " + "-" * 88)
    print(f"  {'pair':<14}{'best method':<18}{'switches':>9}{'CAGR':>9}"
          f"{'buy&hold':>10}{'null p95':>10}{'maxDD':>8}  verdict")
    results = []
    for bull, bear, sig, label in todo:
        b = best_method(conn, cfg, bull, bear, sig, SEARCH)
        if not b:
            print(f"  {label:<14}insufficient data")
            continue
        beats_null = b["cagr"] > b["null"]["p95"]
        beats_bh = b["cagr"] > b["bh"]
        verdict = ("BEATS BOTH" if (beats_null and beats_bh)
                   else "loses to buy&hold" if beats_null
                   else "loses to null" if beats_bh else "loses to both")
        print(f"  {label:<14}{b['method']+'('+str(b['param'])+')':<18}"
              f"{b['n_switches']:>9}{b['cagr']*100:>8.2f}%{b['bh']*100:>9.2f}%"
              f"{b['null']['p95']*100:>9.2f}%{b['max_dd']*100:>7.1f}%  {verdict}")
        results.append((label, b, beats_null, beats_bh))

    winners = [r for r in results if r[2] and r[3]]
    print()
    if winners:
        print(f"  {len(winners)} pair(s) beat BOTH benchmarks on the search window.")
        print("  Running each once on the validation window:")
        for label, b, _, _ in winners:
            bull, bear, sig = next((p[0], p[1], p[2]) for p in PAIRS if p[3] == label)
            w = load_pair(conn, bull, bear, sig, *VALIDATE)
            if w.empty:
                continue
            cm = costs_mod.CostModel(cfg)
            fn, _ = METHODS[b["method"]]
            r = run_switch(w, fn(w["close_XLE"], b["param"]), cm, min_hold=b["min_hold"])
            bh = buy_and_hold(w); nl = random_null(w, r["n_switches"], cm, trials=120)
            ok = r["cagr"] > nl["p95"] and r["cagr"] > bh
            print(f"    {label:<14}{r['cagr']*100:>+8.2f}%  buy&hold {bh*100:>+7.2f}%"
                  f"  null p95 {nl['p95']*100:>+7.2f}%  -> {'PASS' if ok else 'FAIL'}")
    else:
        print("  No pair beats both benchmarks. Nothing proceeds to validation.")
    conn.close()


if __name__ == "__main__":
    main()
