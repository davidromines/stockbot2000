"""
The ERX/ERY switching fund: search momentum methods, pick the best, prove it or kill it.

THE IDEA
--------
Hold ERX (2x long energy) when momentum says energy rises, ERY (2x inverse
energy) when it says energy falls. **Never both at once** — a switch, not a
hedge. It matters because ERY gives a cash-only, long-only account a bear
position it otherwise cannot take.

WHY THIS IS A HARDER TEST THAN IT LOOKS
---------------------------------------
Two leveraged inverse ETFs both bleed. ERX and ERY have each lost most of their
value since 2008 through volatility decay; holding either forever is ruinous.
That makes the null *strongly negative* — random switching loses badly — which is
the opposite of the stock universe, where buying at random made money and made
every naive backtest look brilliant. A bar that is genuinely hard to clear is
worth more than one that flatters everything.

`paired_etf.py` already tested ONE pre-registered switching rule and it FAILED.
This is not a re-run of that: it searches a grid of momentum methods and
parameters, which is a different and broader question. It is also a more
dangerous one — searching hundreds of variants against fixed history is exactly
how this project has fooled itself six times before, so the protocol below is not
optional decoration.

PROTOCOL — fixed before any result is looked at
-----------------------------------------------
  search    2008-2019   choose the method and parameters here, and only here
  validate  2020-2022   the chosen method is run once; if it fails, it is dead
  sealed    2023+       touched once, at the very end, never for selection

  A method must beat the RANDOM-SWITCH NULL, matched to its own switch
  frequency, not merely be positive. Random switching at 40 trades a year has a
  different expected loss than at 4, so an unmatched null would reward or punish
  turnover rather than skill.

**Signal from XLE, not from ERX.** XLE is the unleveraged sector. ERX's own price
carries the leverage decay, so momentum measured on it is partly a measurement of
its own bleed rather than of energy.

**Fills at the next open**, matching simulator.py. A signal computed from a close
cannot be traded at that close.

Usage:
    python erx_momentum.py --search          # grid over the search window
    python erx_momentum.py --validate        # run the winner once on 2020-2022
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import itertools
import logging

import numpy as np
import pandas as pd

import costs as costs_mod
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("erx")

SEARCH = ("2008-11-19", "2019-12-31")
VALIDATE = ("2020-01-01", "2022-12-31")
SEALED = ("2023-01-01", "2099-12-31")


def load(conn, start: str, end: str) -> pd.DataFrame:
    """XLE signal source joined to ERX/ERY open and close on the same dates."""
    q = """SELECT ticker, date, "open" AS open, close FROM prices
           WHERE ticker IN ('XLE','ERX','ERY') AND date BETWEEN ? AND ? AND close > 0"""
    df = pd.read_sql_query(q, conn, params=(start, end))
    if df.empty:
        return df
    wide = df.pivot(index="date", columns="ticker", values=["open", "close"])
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    wide = wide.dropna().sort_index()
    return wide


# --- momentum methods -------------------------------------------------------
# Each returns a boolean Series: True = bullish on energy = hold ERX.

def m_sma_cross(px: pd.Series, n: int) -> pd.Series:
    return px > px.rolling(n).mean()


def m_roc(px: pd.Series, n: int) -> pd.Series:
    return px.pct_change(n) > 0


def m_dual_sma(px: pd.Series, n: int, slow_mult: int = 4) -> pd.Series:
    return px.rolling(n).mean() > px.rolling(n * slow_mult).mean()


def m_breakout(px: pd.Series, n: int) -> pd.Series:
    return px >= px.rolling(n).max()


def m_macd_sign(px: pd.Series, n: int) -> pd.Series:
    fast = px.ewm(span=max(2, n // 2), adjust=False).mean()
    slow = px.ewm(span=n, adjust=False).mean()
    return fast > slow


METHODS = {
    "sma_cross": (m_sma_cross, (10, 20, 50, 100, 150, 200)),
    "roc":       (m_roc,       (5, 10, 20, 40, 60, 120)),
    "dual_sma":  (m_dual_sma,  (5, 10, 20, 30, 50)),
    "breakout":  (m_breakout,  (10, 20, 40, 60, 120)),
    "macd_sign": (m_macd_sign, (10, 20, 40, 60, 120)),
}


def run_switch(wide: pd.DataFrame, bullish: pd.Series, cost_model,
               capital: float = 100.0, min_hold: int = 1) -> dict:
    """
    Simulate the switch. Fully invested in exactly one of ERX/ERY at all times.

    Signals are read at a close and acted on at the NEXT open, so the position
    held over day t was decided by day t-1's data. `min_hold` suppresses
    whipsaw by refusing to flip more often than every N sessions — turnover is
    what kills a leveraged pair, so it is a real parameter, not a nicety.
    """
    sig = bullish.reindex(wide.index).ffill()
    if sig.isna().all():
        return {"n_switches": 0, "final": capital, "cagr": 0.0, "equity": None}

    dates = wide.index.to_numpy()
    o_erx = wide["open_ERX"].to_numpy(); c_erx = wide["close_ERX"].to_numpy()
    o_ery = wide["open_ERY"].to_numpy(); c_ery = wide["close_ERY"].to_numpy()
    want = sig.fillna(False).to_numpy().astype(bool)

    equity = capital
    held = None          # 'ERX' | 'ERY'
    shares = 0.0
    last_switch = -10**9
    curve, switches = [], 0

    for i in range(1, len(dates)):
        target = "ERX" if want[i - 1] else "ERY"
        # Mark to this bar's open before deciding, so a switch is priced there.
        if held is not None:
            equity = shares * (o_erx[i] if held == "ERX" else o_ery[i])
        if target != held and (i - last_switch) >= min_hold:
            if held is not None:
                # One round trip's worth of friction per switch: sell one leg,
                # buy the other. Spread is estimated from these ETFs' liquidity,
                # which is high — but 2x funds still cost more than plain ones.
                equity -= cost_model.round_trip(equity, dollar_volume=20_000_000,
                                                shares=shares)
                switches += 1
            px = o_erx[i] if target == "ERX" else o_ery[i]
            if px <= 0:
                continue
            shares = equity / px
            held = target
            last_switch = i
        if held is not None:
            equity = shares * (c_erx[i] if held == "ERX" else c_ery[i])
        curve.append(equity)

    years = max((pd.Timestamp(dates[-1]) - pd.Timestamp(dates[0])).days / 365.25, 1e-9)
    cagr = (equity / capital) ** (1 / years) - 1 if equity > 0 else -1.0
    eq = np.array(curve, dtype="float64")
    dd = float(np.max(1 - eq / np.maximum.accumulate(eq))) if eq.size else 0.0
    return {"n_switches": switches, "final": float(equity), "cagr": float(cagr),
            "max_dd": dd, "equity": eq, "years": years,
            # Where the replay ended: the leg held and the bar index of the last
            # switch, so a caller can apply the same min_hold rule to the NEXT open.
            "held": held, "last_switch": last_switch, "bars": len(dates)}


def random_null(wide: pd.DataFrame, n_switches: int, cost_model,
                trials: int = 200, seed: int = 7) -> dict:
    """
    What random switching at the SAME frequency earns. The bar to clear.

    Matched on switch count rather than run at some arbitrary cadence: random
    switching 4 times a year and 400 times a year have very different expected
    losses in a leveraged pair, so an unmatched null would be scoring turnover
    instead of skill.
    """
    rng = np.random.default_rng(seed)
    n = len(wide)
    out = []
    for _ in range(trials):
        flips = np.zeros(n, dtype=bool)
        if n_switches > 0:
            idx = rng.choice(np.arange(1, n), size=min(n_switches, n - 1), replace=False)
            flips[idx] = True
        state = rng.random() < 0.5
        want = np.empty(n, dtype=bool)
        for i in range(n):
            if flips[i]:
                state = not state
            want[i] = state
        r = run_switch(wide, pd.Series(want, index=wide.index), cost_model)
        out.append(r["cagr"])
    a = np.array(out)
    return {"mean": float(a.mean()), "p95": float(np.percentile(a, 95)),
            "p50": float(np.median(a))}


def search(conn, cfg) -> list:
    cost_model = costs_mod.CostModel(cfg)
    wide = load(conn, *SEARCH)
    log.info(f"Search window {SEARCH[0]} -> {SEARCH[1]}: {len(wide):,} sessions")
    xle = wide["close_XLE"]
    rows = []
    for name, (fn, params) in METHODS.items():
        for p in params:
            for mh in (1, 5, 10, 20):
                try:
                    sig = fn(xle, p)
                except Exception:
                    continue
                r = run_switch(wide, sig, cost_model, min_hold=mh)
                rows.append({"method": name, "param": p, "min_hold": mh,
                             "cagr": r["cagr"], "final": r["final"],
                             "switches": r["n_switches"], "max_dd": r.get("max_dd", 0)})
    rows.sort(key=lambda x: -x["cagr"])
    return rows, wide, cost_model


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--search", action="store_true")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--top", type=int, default=12)
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])

    rows, wide, cost_model = search(conn, cfg)
    print(f"\n  ERX/ERY MOMENTUM SEARCH — {SEARCH[0]} to {SEARCH[1]}, $100 start")
    print("  " + "-" * 74)
    print(f"  {'method':<12}{'param':>6}{'minhold':>8}{'switches':>10}"
          f"{'CAGR':>9}{'final $':>11}{'maxDD':>8}")
    for r in rows[:a.top]:
        print(f"  {r['method']:<12}{r['param']:>6}{r['min_hold']:>8}{r['switches']:>10}"
              f"{r['cagr']*100:>8.2f}%{r['final']:>11,.0f}{r['max_dd']*100:>7.1f}%")

    best = rows[0]
    print(f"\n  BEST ON SEARCH: {best['method']}({best['param']}) min_hold={best['min_hold']}")
    null = random_null(wide, best["switches"], cost_model)
    print(f"  Random-switch null at {best['switches']} switches: "
          f"median {null['p50']*100:+.2f}%/yr, 95th pct {null['p95']*100:+.2f}%/yr")
    verdict = ("BEATS the null" if best["cagr"] > null["p95"]
               else "does NOT beat the null's 95th percentile")
    print(f"  Verdict on the search window: {verdict}")
    print("\n  A search-window result is not evidence. Run --validate to spend the")
    print("  2020-2022 window on this one method, once.")

    if a.validate:
        fn, _ = METHODS[best["method"]]
        for label, win in (("VALIDATE", VALIDATE), ("SEALED", SEALED)):
            w = load(conn, *win)
            if w.empty:
                continue
            r = run_switch(w, fn(w["close_XLE"], best["param"]), cost_model,
                           min_hold=best["min_hold"])
            n = random_null(w, r["n_switches"], cost_model)
            ok = r["cagr"] > n["p95"]
            print(f"\n  {label} {win[0]} -> {win[1]}")
            print(f"    CAGR {r['cagr']*100:+.2f}%   final ${r['final']:,.0f}   "
                  f"switches {r['n_switches']}   maxDD {r['max_dd']*100:.1f}%")
            print(f"    null median {n['p50']*100:+.2f}%  95th {n['p95']*100:+.2f}%"
                  f"   -> {'PASS' if ok else 'FAIL'}")
            if label == "VALIDATE" and not ok:
                print("    Stopping. A method that fails validation does not get")
                print("    to see the sealed window.")
                break
    conn.close()


if __name__ == "__main__":
    main()
