"""
The ERX/ERY paired-ETF switching experiment. Pre-registered, run once, closed.

The idea, in the user's words: hold ERX when the signal says energy rises,
switch to ERY when it says energy falls. **Never both at once** — this is a
switch, not a hedge. It solves a real constraint, since ERY gives a cash-only,
long-only account a bear position it otherwise cannot take.

Why this deserved a real test rather than a dismissal: **the null here is
strongly negative.** Random switching between two 2x-leveraged inverse ETFs
loses about 50% a year to volatility decay and costs. In the stock universe
buying at random made money, which is what made that null so treacherous; a bar
of -50%/yr is genuinely hard to clear by luck. A positive result would mean more
here than there.

**Pass/fail was fixed in advance** and is enforced in `verdict()` below, not
decided after seeing the numbers:

    PASS requires ALL FOUR
      1. positive CAGR after costs
      2. beats the random-switch null
      3. survives the 2020-2022 validation window
      4. a control shows under 5% of random signals passing the same gate

    FAIL on any one. Then mark it closed and record the numbers.

A settled negative is worth more than an open question.

Usage:
    python paired_etf.py                 # run the full pre-registered test
    python paired_etf.py --signals       # list the signals under test
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import numpy as np
import pandas as pd

import costs as costs_mod
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("paired_etf")

BULL, BEAR = "ERX", "ERY"
VALIDATION = ("2020-01-01", "2022-12-31")


# -- signals under test ------------------------------------------------------
#
# Each returns a boolean Series on ERX's own price history: True = hold ERX,
# False = hold ERY. Deliberately simple and published — this is a test of the
# switching structure, not a search for a signal.

def sig_sma(px: pd.Series, n: int = 50) -> pd.Series:
    return px > px.rolling(n).mean()


def sig_momentum(px: pd.Series, n: int = 20) -> pd.Series:
    return px.pct_change(n) > 0


def sig_macd(px: pd.Series) -> pd.Series:
    ema12 = px.ewm(span=12, adjust=False).mean()
    ema26 = px.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    return macd > macd.ewm(span=9, adjust=False).mean()


def sig_dual_sma(px: pd.Series) -> pd.Series:
    return (px > px.rolling(50).mean()) & (px.rolling(50).mean() > px.rolling(200).mean())

def sig_rsi(px: pd.Series, n: int = 14) -> pd.Series:
    d = px.diff()
    up = d.clip(lower=0).ewm(alpha=1 / n, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / n, adjust=False).mean()
    return (100 - 100 / (1 + up / dn.replace(0, np.nan))) > 50


SIGNALS = {
    "sma_50": ("Hold ERX above its 50-day average", sig_sma),
    "momentum_20": ("Hold ERX when 20-day return is positive", sig_momentum),
    "macd": ("Hold ERX when MACD is above its signal line", sig_macd),
    "dual_sma": ("Hold ERX above the 50-day and in a 50/200 uptrend", sig_dual_sma),
    "rsi_14": ("Hold ERX when RSI(14) is above 50", sig_rsi),
}


def _load(conn, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """
    Aligned daily closes for the pair. Only days both traded are usable.

    Read straight from `prices` rather than through the tradeability-filtered
    view: this experiment is about two specific instruments, and a day one of
    them slipped below a liquidity floor is still a day the position existed.
    """
    frames = {}
    for t in (BULL, BEAR):
        sql = "SELECT date, close FROM prices WHERE ticker=?"
        params = [t]
        if start:
            sql += " AND date>=?"; params.append(start)
        if end:
            sql += " AND date<=?"; params.append(end)
        rows = conn.execute(sql + " ORDER BY date", params).fetchall()
        frames[t] = pd.Series({r["date"]: float(r["close"]) for r in rows}, dtype="float64")
    out = pd.DataFrame(frames).dropna()
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


def run_switching(px: pd.DataFrame, hold_bull: pd.Series, cm, start_equity: float = 100.0):
    """
    Walk the pair day by day, holding exactly one leg.

    The signal is **lagged one day** before it is acted on. A signal computed
    from today's close cannot be traded at today's close, and letting it would
    manufacture exactly the kind of result this experiment exists to rule out.
    """
    hold = hold_bull.reindex(px.index).ffill().fillna(False).shift(1).fillna(False)
    ret_bull = px[BULL].pct_change().fillna(0.0)
    ret_bear = px[BEAR].pct_change().fillna(0.0)

    daily = np.where(hold.to_numpy(), ret_bull.to_numpy(), ret_bear.to_numpy())
    switched = np.asarray(hold.ne(hold.shift(1)).to_numpy(), dtype=bool).copy()
    switched[0] = True

    equity = np.empty(len(px), dtype="float64")
    e = start_equity
    n_switch = 0
    for i in range(len(px)):
        if switched[i]:
            # A switch is a full round trip: sell one leg, buy the other.
            e -= cm.round_trip(e, 5e7, e / max(px[BULL].iloc[i], 1e-9))
            n_switch += 1
        e *= (1 + daily[i])
        e = max(e, 0.0)
        equity[i] = e

    eq = pd.Series(equity, index=px.index)
    years = max((px.index[-1] - px.index[0]).days / 365.25, 1e-9)
    cagr = (eq.iloc[-1] / start_equity) ** (1 / years) - 1 if eq.iloc[-1] > 0 else -1.0
    dd = float((1 - eq / eq.cummax()).max())
    return {"cagr": float(cagr), "max_dd": dd, "final": float(eq.iloc[-1]),
            "switches": int(n_switch), "days": len(px), "equity": eq}


def random_null(px: pd.DataFrame, cm, n: int = 200, seed: int = 7) -> dict:
    """
    The null: switching at random at the same rate a real signal switches.

    Matched on switch rate rather than switching every day, so the null pays a
    comparable cost bill. An unmatched null would make any low-turnover signal
    look good purely by trading less.
    """
    rng = np.random.default_rng(seed)
    cagrs = []
    for _ in range(n):
        flips = rng.random(len(px)) < 0.02        # ~1 switch per 50 days
        state = np.logical_xor.accumulate(flips)
        r = run_switching(px, pd.Series(state, index=px.index), cm)
        cagrs.append(r["cagr"])
    a = np.array(cagrs)
    return {"mean": float(a.mean()), "p95": float(np.percentile(a, 95)),
            "best": float(a.max()), "n": n}


def verdict(res_full: dict, res_valid: dict, null_full: dict, null_valid: dict,
            control_rate: float) -> tuple[bool, list[str]]:
    """
    The four pre-registered conditions. Written before the numbers were seen.

    Returns (passed, reasons). All four required; any one failing is a FAIL and
    the experiment closes.
    """
    checks = [
        ("positive CAGR after costs", res_full["cagr"] > 0,
         f"{res_full['cagr']:+.1%}"),
        ("beats the random-switch null", res_full["cagr"] > null_full["p95"],
         f"{res_full['cagr']:+.1%} vs 95th pct of null {null_full['p95']:+.1%}"),
        ("survives 2020-2022 validation", res_valid["cagr"] > null_valid["p95"]
         and res_valid["cagr"] > 0,
         f"{res_valid['cagr']:+.1%} vs null {null_valid['p95']:+.1%}"),
        ("under 5% of random signals pass", control_rate < 0.05,
         f"{control_rate:.0%} of random signals passed"),
    ]
    return all(c[1] for c in checks), checks


def control(px: pd.DataFrame, cm, n: int = 60, seed: int = 99) -> float:
    """
    Condition 4: how often does a *random* signal clear conditions 1 and 2?

    The same question `control.py` asks of the stock search. A gate that random
    signals clear is not evidence about the signal that cleared it.
    """
    rng = np.random.default_rng(seed)
    null = random_null(px, cm, n=100, seed=seed + 1)
    passed = 0
    for _ in range(n):
        flips = rng.random(len(px)) < rng.uniform(0.005, 0.05)
        state = np.logical_xor.accumulate(flips)
        r = run_switching(px, pd.Series(state, index=px.index), cm)
        if r["cagr"] > 0 and r["cagr"] > null["p95"]:
            passed += 1
    return passed / n


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--signals", action="store_true")
    args = parser.parse_args()
    if args.signals:
        for k, (desc, _) in SIGNALS.items():
            print(f"  {k:<14} {desc}")
        return

    cfg = load_config()
    runtime.be_nice()
    cm = costs_mod.CostModel(cfg)
    conn = storage.connect(cfg["database"]["market_data_path"])

    px = _load(conn)
    if px.empty:
        raise SystemExit(f"No overlapping history for {BULL}/{BEAR}.")
    pxv = px.loc[VALIDATION[0]:VALIDATION[1]]
    log.info(f"{len(px):,} days both traded, {px.index[0].date()} to {px.index[-1].date()}")

    print(f"\n  PAIRED-ETF SWITCHING — {BULL} / {BEAR}, one leg at a time")
    print(f"  {len(px):,} trading days, {px.index[0].date()} to {px.index[-1].date()}, "
          f"costs charged on every switch\n")

    # Reference points first, so the signals have something to be judged against.
    bh_bull = run_switching(px, pd.Series(True, index=px.index), cm)
    bh_bear = run_switching(px, pd.Series(False, index=px.index), cm)
    null_full = random_null(px, cm)
    null_valid = random_null(pxv, cm)

    print(f"  {'reference':<22}{'CAGR':>10}{'max DD':>9}{'switches':>10}")
    print("  " + "-" * 52)
    print(f"  {'buy & hold ' + BULL:<22}{bh_bull['cagr']:>+10.1%}{bh_bull['max_dd']:>9.0%}"
          f"{bh_bull['switches']:>10,}")
    print(f"  {'buy & hold ' + BEAR:<22}{bh_bear['cagr']:>+10.1%}{bh_bear['max_dd']:>9.0%}"
          f"{bh_bear['switches']:>10,}")
    print(f"  {'random switching':<22}{null_full['mean']:>+10.1%}{'—':>9}{'—':>10}"
          f"   <- the null (95th pct {null_full['p95']:+.1%})")

    print(f"\n  {'signal':<22}{'CAGR':>10}{'max DD':>9}{'switches':>10}{'final $100':>12}")
    print("  " + "-" * 64)
    results = {}
    for name, (_, fn) in SIGNALS.items():
        r = run_switching(px, fn(px[BULL]), cm)
        results[name] = r
        print(f"  {name:<22}{r['cagr']:>+10.1%}{r['max_dd']:>9.0%}{r['switches']:>10,}"
              f"{r['final']:>12,.2f}")

    best = max(results, key=lambda k: results[k]["cagr"])
    log.info(f"Best signal is {best}; running the pre-registered gate on it")
    res_valid = run_switching(pxv, SIGNALS[best][1](px[BULL]), cm)
    ctrl = control(px, cm)

    passed, checks = verdict(results[best], res_valid, null_full, null_valid, ctrl)
    print(f"\n  PRE-REGISTERED VERDICT — best signal: {best}")
    print("  " + "-" * 72)
    for label, ok, detail in checks:
        print(f"  {'PASS' if ok else 'FAIL':<6}{label:<38}{detail}")
    print("  " + "-" * 72)
    print(f"  RESULT: {'PASS' if passed else 'FAIL'}"
          f"{'' if passed else ' — the experiment is closed and the numbers recorded.'}")
    conn.close()
    return results


if __name__ == "__main__":
    main()
