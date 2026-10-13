"""profit_report: one set of trade statistics for live and research (synthetic data)."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd
import profit_report as pr

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

r = pd.Series([2.0, -1.0, 3.0, -2.0, 4.0])
usd = pd.Series([0.4, -0.2, 0.6, -0.4, 0.8])
st = pr.trade_stats(r, usd, pd.Series([2, 1, 3, 2, 4]), pd.Series([20.0] * 5))
check("n, mean, win rate", st["n"] == 5 and abs(st["mean"] - 1.2) < 1e-9 and abs(st["win_rate"] - 0.6) < 1e-9)
check("average win and loss", abs(st["avg_win"] - 3.0) < 1e-9 and abs(st["avg_loss"] + 1.5) < 1e-9)
check("profit factor = gross wins / gross losses", abs(st["profit_factor"] - 3.0) < 1e-9)
check("per dollar-session = net dollars / (stake x sessions)", abs(st["per_dollar_session"] - (1.2 / (20 * 12)) * 100) < 1e-9)
check("no losses -> profit factor undefined, not infinite", np.isnan(pr.trade_stats(pd.Series([1.0, 2.0]))["profit_factor"]))
check("empty input is handled", pr.trade_stats(pd.Series([], dtype=float)) == {"n": 0})
d = pd.DataFrame({"run_id": ["a"] * 6, "date": [f"2026-10-0{i}" for i in range(1, 7)], "positions_usd": 90.0, "equity_usd": [100, 101, 99, 98, 102, 104.0]})
fl = pr.fund_level(d, ["a"])
check("fund return, drawdown and utilisation", abs(fl["ret_med"] - 4.0) < 1e-9 and abs(fl["dd_med"] - (101 - 98) / 101 * 100) < 1e-9 and abs(fl["util_med"] - float((90.0 / d["equity_usd"]).mean())) < 1e-9)
check("funds with fewer than 5 marks are skipped", pr.fund_level(d.head(4), ["a"]) == {})
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
