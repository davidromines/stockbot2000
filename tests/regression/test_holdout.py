"""
holdout.py (the unseen 2023 -> today window): only strategies past validation are
candidates; each version gets ONE look (a second is refused and the stored result is
never overwritten); the ranking fails a strategy that loses there and uses the unseen
result as its prior. Synthetic panel and in-memory database; no real data.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import holdout
import league
import ranking
import simulator
import strategy_factory as sf
import strategy_objects as so

FAILED = []
CFG = {"risk": {"position_size_usd": 20.0}, "factory": {"max_entries_per_backtest": 5000},
       "costs": {"enabled": False}}


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def panel(up: bool):
    n = 60
    close = 100 * np.cumprod(np.full(n, 1.01 if up else 0.99))
    df = pd.DataFrame({"ticker": ["X"] * n, "date": pd.date_range("2023-01-02", periods=n, freq="B"),
                       "close": close, "open": close, "atr_14": [1.0] * n, "dollar_volume_20": [5e7] * n})
    return simulator.Panel(df, max_hold=10, exit_prices=df[["ticker", "date", "close", "open"]])


def main():
    import factory_pipeline as fp
    fp._null_excess = lambda *a, **k: None
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    c.execute("INSERT INTO prices VALUES ('SPY','2026-09-24',1)")
    so.init(c); league.init(c); holdout.init(c)
    g = sf.G(sf.gt(sf.col("close"), sf.k(0)), None, 50.0, 10)            # always in, 10-day hold
    for key in ("fx_a", "fx_b", "fx_new"):
        so.register(c, {"strategy_key": key, "name": key, "family": "f", "league": "momentum", "genome": g})
    for key in ("fx_a", "fx_b"):
        for st in (league.SPECIFIED, league.BACKTESTED, league.VALIDATED):
            so.decide(c, key, 1, "PROMOTE", "t", to_state=st)
    cands = [k for k, _, _ in holdout.candidates(c)]
    check("only strategies past validation are candidates", sorted(cands) == ["fx_a", "fx_b"], cands)
    ra = holdout.evaluate(c, CFG, "fx_a", 1, panel(up=True), "2026-09-24")
    rb = holdout.evaluate(c, CFG, "fx_b", 1, panel(up=False), "2026-09-24")
    check("a rising window is net positive", ra["net_usd"] > 0 and ra["per_trade"] > 0, ra)
    check("a falling window is net negative", rb["net_usd"] < 0, rb)
    try:
        holdout.evaluate(c, CFG, "fx_a", 1, panel(up=False), "2026-09-24")
        refused = False
    except RuntimeError:
        refused = True
    check("a second look is refused", refused)
    check("the stored result is unchanged", abs(holdout.result(c, "fx_a", 1)["net_usd"] - ra["net_usd"]) < 1e-9)
    check("a looked-at strategy is no longer a candidate", holdout.candidates(c) == [])
    check("recorded as a holdout metric", so.latest_metrics(c, "fx_a", 1, "holdout") is not None)

    import leagues
    leagues.evidence = lambda conn, k, v: {}
    leagues.family_of = lambda conn, k, v: "f"
    leagues.league_of = lambda conn, cfg, k, v: "momentum"
    ranking.survivorship = lambda conn, k, v: {"backtest": 0.01}
    rows = {r["strategy_key"]: r for r in ranking.rank(c, {"ranking": {"normalize_hold_days": None}})}   # per-trade view
    check("losing on the unseen window fails the gate", not rows["fx_b"]["passes_gate"]
          and "unseen" in rows["fx_b"]["gate"], rows["fx_b"])
    check("the unseen result is the prior (score) and the backtest is still shown",
          abs(rows["fx_a"]["score"] - ra["per_trade"]) < 1e-9 and rows["fx_a"]["backtest"] == 0.01, rows["fx_a"])
    check("a strategy with no look ranks on its backtest", rows["fx_new"]["score"] == 0.01 and rows["fx_new"]["holdout"] is None)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
