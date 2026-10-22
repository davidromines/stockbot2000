"""options_liquid_test: variant names never collide with a strategy's own backtest; the pre-registered pass rule
(mean > 0, date-clustered t >= 2.8, positive in >= 4 years); dollars per contract from the per-share cost."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd

import options_liquid_test as olt

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


check("a variant name is not the strategy's own name", olt.variant("opt_signal_call", "B") == "opt_signal_call__liqB")
check("A removes the cap; B also limits the gap to 5%", olt.SETTINGS["A"] == {"max_contract_cost_usd": None}
      and olt.SETTINGS["B"]["max_spread_frac"] == 0.05)
import options_lab as ol
check("the tested strategies are exactly the ones allowed to trade (one long call or put)",
      set(olt.strategies()) == {n for n, p in ol.STRATEGIES.items() if p["legs"] in ("C", "P") and ol.tradeable(p)}
      and len(olt.strategies()) == 10, olt.strategies())

days = pd.bdate_range("2020-01-02", "2026-06-30").strftime("%Y-%m-%d")
rng = np.random.default_rng(1)
spread_days = days[np.linspace(0, len(days) - 1, 700).astype(int)]          # 700 dates across all seven years
good = pd.DataFrame({"opened": spread_days, "cost": 5.0, "ret": 0.10 + rng.normal(0, 0.3, 700)})
s = olt.stats(good)
check("a steady +10% a trade across the years passes", s["pass"] and s["t"] > olt.T_NEED and s["years_positive"] >= 4, s)
check("dollars per contract = return x per-share cost x 100", abs(s["mean_usd_per_contract"] - s["mean"] * 500) < 1e-6)
noise = good.assign(ret=rng.normal(0, 0.5, 700))
check("noise does not pass", not olt.stats(noise)["pass"])
lottery = good.assign(ret=np.where(np.arange(700) % 50 == 0, 30.0, -0.5))
lot = olt.stats(lottery)
check("a positive mean from a few huge winners still has to clear the t", lot["mean"] > 0 and (lot["t"] < olt.T_NEED) == (not lot["pass"] or lot["t"] >= olt.T_NEED))
check("fewer than 10 trades never passes", not olt.stats(good.head(9))["pass"])

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
