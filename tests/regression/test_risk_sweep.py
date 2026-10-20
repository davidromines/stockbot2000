"""risk_sweep (Stage AD3.5 / AD3.6): report sessions, the skip masks' boundaries, coverage, the predicted-date mask, and
the two pre-registered verdict rules."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd

import risk_sweep as rs

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


sessions = np.array(pd.bdate_range("2017-01-02", "2017-12-29").strftime("%Y-%m-%d"), dtype=str)
pos = {d: i for i, d in enumerate(sessions)}
ev = pd.DataFrame({"ticker": ["AAA", "AAA", "AAA", "BBB", "AAA"],
                   "day": ["2017-03-01", "2017-03-04", "2017-06-01", "2017-03-01", "2017-09-01"],
                   "after_close": [False, False, True, False, False]})
rep = rs.report_sessions(ev, sessions)
check("a report before the open belongs to its own session", pos["2017-03-01"] in rep["AAA"], rep["AAA"])
check("a weekend date maps to the next session (Saturday 03-04 -> Monday 03-06)", pos["2017-03-06"] in rep["AAA"])
check("after the close: the next session (06-01 -> 06-02)", pos["2017-06-02"] in rep["AAA"] and pos["2017-06-01"] not in rep["AAA"])
cov = rs.covered(ev)
check("covered = at least 3 reports in the year", ("AAA", "2017") in cov and ("BBB", "2017") not in cov, cov)

R = pos["2017-06-02"]
sig = np.array([R - 1, R - 5, R - 6, R, -1])
m = rs.skip_mask(["AAA"] * 5, sig, rep, 5)
check("skip N=5: fill on the report session is skipped (signal the day before)", m[0])
check("...a report on the 5th session from the fill is skipped", m[1])
check("...the 6th is not", not m[2])
check("...a signal ON the report session is not (the reaction is already in its price)", not m[3])
check("...an unmapped signal is never skipped", not m[4])
check("a ticker without report data is never skipped", not rs.skip_mask(["ZZZ"], np.array([R - 1]), rep, 5)[0])

# predicted: the last report on or before the signal + 91 calendar days
last = pos["2017-06-02"]
p_day = (pd.Timestamp("2017-06-02") + pd.Timedelta(days=91)).strftime("%Y-%m-%d")     # 2017-09-01, a Friday
P = int(np.searchsorted(sessions, p_day))
pm = rs.predicted_mask(["AAA", "AAA", "AAA"], np.array([P - 1, P - 6, last + 1]), rep, sessions, 5)
check("predicted date: skipped just before the predicted session, not 6 sessions before", pm[0] and not pm[1], pm)
check("predicted date uses only reports on or before the signal (none ahead = no prediction from the future)",
      not rs.predicted_mask(["AAA"], np.array([pos["2017-01-03"]]), rep, sessions, 5)[0])

# earn_summary / earn_verdict
rng = np.random.default_rng(0)
alt = np.where(np.arange(400) % 2 == 0, 1.0, -1.0)                      # deterministic +/- spread, balanced in every year
ret = 0.004 + 0.05 * alt
years = np.array(["2016"] * 100 + ["2017"] * 100 + ["2018"] * 100 + ["2019"] * 100)
cov_ = np.ones(400, bool)
removed = np.zeros(400, bool)
removed[::5] = True                                                      # 20 a year, alternating signs among them
ret_bad = ret.copy()
ret_bad[removed] = -0.005 + 0.15 * np.where(np.arange(removed.sum()) % 2 == 0, 1.0, -1.0)   # lower mean, 3x dispersion
s_good = rs.earn_summary(ret_bad, years, cov_, {"skip5": removed, "pred5": removed})
check("summary: the rule removes 80 and keeps 320", s_good["rules"]["skip5"]["removed"] == 80
      and s_good["rules"]["skip5"]["kept"] == 320)
check("summary: dropping high-dispersion, low-mean trades raises the Sharpe", s_good["rules"]["skip5"]["d_sharpe"] > 0)
v = rs.earn_verdict([s_good] * 3)
check("verdict PASS when all four conditions hold", v["call"].startswith("PASS") and v["a"] and v["b"] and v["c"] and v["d"], v)
ret_good = ret.copy()
ret_good[removed] = 0.03 + 0.02 * np.where(np.arange(removed.sum()) % 2 == 0, 1.0, -1.0)   # the best trades
s_bad = rs.earn_summary(ret_good, years, cov_, {"skip5": removed, "pred5": removed})
v2 = rs.earn_verdict([s_bad] * 3)
check("verdict FAIL when the rule throws away the better trades (b)", v2["call"] == "FAIL" and not v2["b"], v2)
v3 = rs.earn_verdict([rs.earn_summary(ret_bad, years, cov_, {"skip5": removed, "pred5": np.zeros(400, bool)})] * 3)
check("verdict FAIL when the predicted-date version does not agree (d)", v3["call"] == "FAIL" and not v3["d"], v3)
few = np.zeros(400, bool)
few[:10] = True
check("strategies with fewer than MIN_REMOVED removed trades do not vote",
      rs.earn_verdict([rs.earn_summary(ret, years, cov_, {"skip5": few, "pred5": few})])["call"] == "NO DATA")

# stop_summary / stop_verdict (paired by trade)
dates = np.repeat(pd.bdate_range("2016-01-04", periods=200).strftime("%Y-%m-%d"), 2)
yrs = np.array([d[:4] for d in dates])
base = rng.normal(0.002, 0.04, 400)
better = base + 0.004 + rng.normal(0, 0.002, 400)
s = rs.stop_summary(base, better, dates, yrs)
check("stop cell: a consistent +0.4%/trade gain is adoptable", rs.stop_verdict(s) and s["t"] > rs.T_NEED, s)
noise = base + rng.normal(0, 0.03, 400)
check("stop cell: noise is not adoptable", not rs.stop_verdict(rs.stop_summary(base, noise, dates, yrs)))

g = {"entry": {"op": "gt", "args": [{"col": "rsi_14"}, {"const": 50}]}, "risk": {"stop_atr_multiple": 3.0, "max_hold_days": 20}}
g2 = rs.with_stop(g, 1.5)
check("with_stop changes only the stop multiple and leaves the original untouched",
      g2["risk"] == {"stop_atr_multiple": 1.5, "max_hold_days": 20} and g["risk"]["stop_atr_multiple"] == 3.0)
check("about_earnings: a rule reading sue is about earnings; rsi is not",
      rs.about_earnings({"entry": {"col": "sue"}}) and not rs.about_earnings(g))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
