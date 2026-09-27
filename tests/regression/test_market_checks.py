"""
market_checks.py: the bull-market checks are recorded and shown but never gate. Verdicts
(PASS / FAIL / NA below 30 trades); the unseen check reads holdout.py's stored result;
the bear check restricts ENTRIES to the window (lookbacks use the warm-up); a FAIL
leaves the ranking gate untouched. Synthetic data, in-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np
import pandas as pd

import costs
import holdout
import league
import market_checks as mc
import ranking
import simulator
import strategy_factory as sf
import strategy_objects as so

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    check("verdicts: beat random PASS, not FAIL, thin NA",
          (mc.verdict(100, 0.001), mc.verdict(100, -0.001), mc.verdict(10, 0.05), mc.verdict(100, None))
          == ("PASS", "FAIL", "NA", "NA"))

    # Entry restricted to the window by the flag; the lookback still uses the warm-up.
    n = 80
    df = pd.DataFrame({"ticker": ["X"] * n, "date": pd.date_range("2020-01-01", periods=n, freq="B"),
                       "close": np.linspace(100, 180, n), "open": np.linspace(100, 180, n),
                       "atr_14": [1.0] * n, "dollar_volume_20": [5e7] * n})
    p = simulator.Panel(df, max_hold=5, exit_prices=df[["ticker", "date", "close", "open"]])
    d = p.df["date"].astype(str).str[:10]
    p.df[mc.FLAG] = ((d >= "2020-03-02") & (d <= "2020-03-06")).astype("float32")
    g = sf.G(sf.gt(sf.pct(sf.col("close"), 40), sf.k(0)), None, 50.0, 5)   # needs 40 days of history
    r = simulator.simulate(mc._in_window(g), p, costs.CostModel({"costs": {"enabled": False}}), 20.0)
    ent = pd.to_datetime(pd.Series(r["entry_date"])) if "entry_date" in r else None
    check("entries only inside the window, lookback defined from the warm-up",
          r["n_trades"] == 5 and (ent is None or ent.dt.strftime("%Y-%m-%d").between("2020-03-02", "2020-03-09").all()),
          (r["n_trades"], None if ent is None else list(ent)))

    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    so.init(c); league.init(c); holdout.init(c); mc.init(c)
    so.register(c, {"strategy_key": "fx_a", "name": "A", "family": "f", "league": "momentum", "genome": g})
    c.execute("INSERT INTO holdout_results (strategy_key, version, window_start, window_end, trades, net_usd, "
              "per_trade, excess_vs_null_usd, evaluated_at) VALUES ('fx_a',1,'2023-01-01','2026-09-24',100,40,0.02,-60,'t')")
    check("unseen check reads the stored one-look result: net +2% but below random", mc.unseen_vs_random(c, "fx_a", 1) == "FAIL")
    got = mc.checks(c, "fx_a", 1)["unseen_vs_random"]
    check("excess and random baseline are recorded", abs(got["excess_per_trade"] + 0.03) < 1e-9
          and abs(got["null_per_trade"] - 0.05) < 1e-9, got)

    import leagues
    leagues.evidence = lambda conn, k, v: {}
    leagues.family_of = lambda conn, k, v: "f"
    leagues.league_of = lambda conn, cfg, k, v: "momentum"
    ranking.survivorship = lambda conn, k, v: {"backtest": 0.01}
    row = [r for r in ranking.rank(c, {}) if r["strategy_key"] == "fx_a"][0]
    check("the ranking shows the verdict", row["checks"].get("unseen_vs_random") == "FAIL", row["checks"])
    check("a FAIL does not disqualify: the gate passes on its own rules", row["passes_gate"], row["gate"])
    check("the report lists both checks", "bear_vs_random" in mc.report(c) and "never a gate" in mc.report(c))
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
