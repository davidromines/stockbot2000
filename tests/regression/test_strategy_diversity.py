"""
strategy_diversity.py + slots.plan: weekly series from simulated trades, correlation only
over enough shared weeks, and a slot plan that skips a candidate too correlated with one
already chosen — taking the next different strategy instead; an unmeasured pair does not
block. slots.assess is stubbed; in-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import slots
import strategy_diversity as sd

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def row(key, fam, score):
    return {"strategy_key": key, "version": 1, "family": fam, "score": score, "eligible": True,
            "net_usd": 0.0, "stop_plan": [{"type": "atr", "atr_multiple": 3.0}]}


def main():
    dates = pd.date_range("2024-01-01", periods=10, freq="D").to_numpy()
    r = {"n_trades": 3, "entry_rows": np.array([0, 1, 8]), "pnl_series": np.array([2.0, 4.0, -2.0])}
    w = sd.weekly(r, dates)
    check("weekly series: mean trade return by entry week", len(w) == 2 and abs(w.iloc[0] - 0.15) < 1e-9, w)
    rng = np.random.default_rng(1)
    idx = [f"2024-W{i:02d}" for i in range(1, 41)]
    a = pd.Series(rng.normal(size=40), index=idx)
    c, n = sd.corr(a, a * 2 + rng.normal(scale=0.1, size=40))
    check("near-identical strategies correlate near 1", c > 0.95 and n == 40, (c, n))
    check("fewer than MIN_WEEKS shared weeks is no measurement", sd.corr(a[:10], a[:10])[0] is None)
    check("the bear windows use their own (lower) minimum", sd.corr(a[:16], a[:16], sd.MIN_WEEKS_BEAR)[0] is not None
          and sd.corr(a[:16], a[:16])[0] is None)

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT)")
    sd.init(conn)
    ranked = [row("fx_es1", "earnings_surprise", 0.050), row("fx_es2", "earnings_surprise", 0.049),
              row("fx_es3", "earnings_surprise", 0.048), row("fx_fcf", "fcf_to_price", 0.030),
              row("fx_mom", "momentum_9_1", 0.020), row("fx_val", "value_book", 0.015),
              row("fx_q", "quality_roa", 0.010)]
    corr_rows = [("fx_es1", "fx_es2", 0.93), ("fx_es1", "fx_es3", 0.88), ("fx_es2", "fx_es3", 0.9),
                 ("fx_es1", "fx_fcf", 0.35), ("fx_es1", "fx_mom", 0.2), ("fx_fcf", "fx_mom", 0.1),
                 ("fx_es1", "fx_val", 0.3), ("fx_fcf", "fx_val", 0.75), ("fx_mom", "fx_val", 0.1)]
    conn.executemany("INSERT INTO strategy_correlation (key_a, ver_a, key_b, ver_b, corr, weeks, computed_at) "
                     "VALUES (?,1,?,1,?,52,'t')", corr_rows)
    check("lookup works in either order", sd.lookup(conn, ("fx_es2", 1), ("fx_es1", 1)) == 0.93)
    slots.assess = lambda c, cfg: ranked
    p = slots.plan(conn, {"slots": {"max_per_family": 4}})
    keys = [a[1]["strategy_key"] for a in p["assign"]]
    check("the best strategy is taken", keys[0] == "fx_es1", keys)
    check("its near-copies are skipped though they score higher",
          "fx_es2" not in keys and "fx_es3" not in keys, keys)
    check("a strategy too correlated with a chosen one (value vs FCF 0.75) is skipped", "fx_val" not in keys, keys)
    check("five different bets fill the slots... or fewer than five if only four differ",
          set(keys) == {"fx_es1", "fx_fcf", "fx_mom", "fx_q"}, keys)
    check("each skip is recorded with its correlation",
          {k for k, _, _ in p["skipped_correlated"]} >= {"fx_es2", "fx_es3", "fx_val"}, p["skipped_correlated"])
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
