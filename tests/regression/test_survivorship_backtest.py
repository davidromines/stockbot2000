"""
Regression test: backtests include the synthetic dead companies, and the
ranking uses that result (owner, 2026-09-24: "use the synthetic data").

Pinned:
  - synthetic companies get indicators and trade as SYN:<company_id>, never
    under a ticker a real company holds
  - unknown volume stays unknown: volume indicators NaN, liquidity at the floor
  - a strategy that buys a dying company loses money in as_is, more in zero,
    and none of it in exclude — the three modes differ exactly by the dead
  - ranking.py scores and gates on the dead-companies-included result, shows
    the worst case, and falls back to the old backtest only when none exists
  - the drawdown exposure gate the old promotion ladder had is in the ranking

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
import tempfile

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import features
import ranking
import survivorship_backtest as sb
import universe_loader as ul
from train_model import FEATURE_COLS

FAILED = []
WINDOW = ("2016-01-04", "2016-12-30")
CFG = {"factory": {"backtest_window": list(WINDOW), "max_entries_per_backtest": 5000},
       "risk": {"position_size_usd": 20.0, "min_price": 5.0, "min_dollar_volume": 1e6},
       "costs": {"enabled": False}, "survivorship": {"max_drawdown_exposure": 0.35}}
GENOME = {"entry": {"op": "gt", "args": [{"col": "close"}, {"const": 0.0}]},
          "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]},
          "risk": {"stop_atr_multiple": 50.0, "max_hold_days": 20}}


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def synthetic_file(path):
    days = pd.bdate_range("2015-01-02", "2016-10-31")
    n = len(days)
    rows = []
    # DEAD: falls ~0.4%/day, then a -55% delisting bar. REUSE: same idea, ticker a real company holds.
    for cid, tick in (("C1", "DEAD"), ("C2", "REAL")):
        close = 60 * 0.996 ** np.arange(n)
        close[-1] = close[-2] * 0.45
        prev = np.concatenate([[60.0], close[:-1]])
        rows.append(pd.DataFrame({
            "company_id": cid, "ticker": tick, "date": days.strftime("%Y-%m-%d"), "open": prev,
            "high": np.maximum(prev, close) * 1.001, "low": np.minimum(prev, close) * 0.999, "close": close,
            "volume": np.nan, "is_synthetic": True, "data_source": "synthetic_test", "cohort_id": "t",
            "synthetic_reason": "performance", "is_delisting_bar": np.arange(n) == n - 1}))
    pd.concat(rows, ignore_index=True).to_parquet(path, index=False)


def real_frames():
    """One real survivor rising 0.1%/day, shaped like load_training_frame + load_exit_prices."""
    days = pd.bdate_range("2015-01-02", "2017-06-30")
    close = 50 * 1.001 ** np.arange(len(days))
    raw = pd.DataFrame({"ticker": "REAL", "date": days, "open": close, "high": close * 1.001,
                        "low": close * 0.999, "close": close, "volume": 1e6})
    f = features.compute_features_for_ticker(raw)
    f["dollar_volume_20"] = 5e7
    ex = f[["ticker", "date", "close", "open"]].copy()
    inwin = (f["date"] >= pd.Timestamp(WINDOW[0])) & (f["date"] <= pd.Timestamp(WINDOW[1]))
    df = f[inwin][["ticker", "date", "close", "open", *FEATURE_COLS, "dollar_volume_20"]].dropna().copy()
    df["ticker"] = df["ticker"].astype("category")
    return df, ex


def main():
    tmp = tempfile.mkdtemp()
    path = os.path.join(tmp, "synthetic_v4.parquet")
    synthetic_file(path)
    ul.SYNTH = path
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT)")
    conn.execute("INSERT INTO symbols VALUES ('REAL','common_stock',NULL)")

    rows, exits = sb.synthetic_frames(conn, CFG, WINDOW, "as_is")
    tick = set(rows["ticker"])
    check("synthetic rows trade as SYN:<company_id>, never a real ticker", tick == {"SYN:C1", "SYN:C2"}, tick)
    check("volume indicators unknown (NaN), liquidity at the floor",
          rows[list(sb.VOLUME_COLS)].isna().all().all() and (rows["dollar_volume_20"] == 1e6).all())
    check("indicators computed (sma_200, rsi_14 present)", rows[["sma_200", "rsi_14"]].notna().all().all())
    check("only in-window rows above the price floor",
          rows["date"].min() >= pd.Timestamp(WINDOW[0]) and (rows["close"] >= 5.0).all())
    _, zex = sb.synthetic_frames(conn, CFG, WINDOW, "zero")
    last = zex[zex["ticker"] == "SYN:C1"].sort_values("date").iloc[-1]
    check("zero mode: the delisting bar is a total loss", last["close"] == 0.0, last["close"])

    real = real_frames()
    sb._real = lambda c, cfg, w, fund: real
    sb.strategies = lambda c: [("fx_all", 1, GENOME, False)]
    out = sb.run(conn, CFG)
    check("three modes written", out["rows_written"] == 3, out)
    r = {m: sb.result(conn, "fx_all", 1, m) for m in sb.MODES}
    check("exclude trades no synthetic company", r["exclude"]["synthetic_trades"] == 0, r["exclude"])
    check("as_is trades the dead companies", r["as_is"]["synthetic_trades"] > 0, r["as_is"])
    check("dead companies cost money: exclude > as_is > zero",
          r["exclude"]["net_usd"] > r["as_is"]["net_usd"] > r["zero"]["net_usd"],
          {m: round(x["net_usd"], 2) for m, x in r.items()})
    check("re-run computes nothing new (resumable)", sb.run(conn, CFG)["rows_written"] == 0)

    sv = ranking.survivorship(conn, "fx_all", 1)
    check("ranking reads the dead-companies-included backtest and the worst case",
          sv["backtest"] == r["as_is"]["per_trade"] and sv["worst_case"] == r["zero"]["per_trade"], sv)
    check("a strategy never run that way: no survivorship result (old backtest is the fallback)",
          ranking.survivorship(conn, "fx_other", 1) == {})
    ok, why = ranking.gate(0.01, 0.50, 0.35)
    check("exposure gate: >= limit of entries in deep drawdowns is out", not ok and "200-day high" in why, why)
    check("under the limit and profitable passes", ranking.gate(0.01, 0.10, 0.35)[0])

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
