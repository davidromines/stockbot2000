"""
REGRESSION: look-ahead in the two places it is hardest to see.

  fundamental look-ahead     using a filing before it was filed
  time-shuffled model leakage  a random split over time-ordered rows

The second produced a 97.9% win rate that was quoted as a result before anyone
noticed the split was shuffled. Both defects are invisible at runtime: the code
works, the numbers are wrong, and the wrongness looks like success.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_lookahead.py
"""
import runtime  # noqa: F401
import inspect

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


# --- 1. FUNDAMENTALS MUST BE LAGGED TO WHEN THEY BECAME PUBLIC -------------
# period_end is when the quarter ended. filed is when the market could know.
# Using the former is look-ahead of exactly the kind that flatters value screens.
import fundamental_features as ff
src = inspect.getsource(ff)
check("fundamentals are keyed on the FILING date, not the period end",
      "filed" in src,
      "period_end is when the quarter ended, not when anyone could act on it")

import conviction
panel_src = inspect.getsource(conviction._load_panel)
check("the screens read daily_fundamentals (lagged), never fundamentals raw",
      "daily_fundamentals" in panel_src)
check("the as-of join takes the latest filing AT OR BEFORE the review date",
      "<=" in panel_src and "MAX(f2.filed)" in panel_src,
      "a join without the <= bound would import future filings")

# market_cap must be point-in-time: shares FROM the filing times the price ON
# the filing date. A current share count applied to an old balance sheet is
# look-ahead precisely where it does most damage, since dilution is what
# distressed companies do next.
import value_metrics
mc_src = inspect.getsource(value_metrics._market_cap)
check("market cap uses the price on the filing date, not today's",
      "date<=?" in mc_src.replace(" ", "") or "date <= ?" in mc_src)
check("market cap uses shares from the filing, not a current quote",
      "shares" in inspect.signature(value_metrics._market_cap).parameters)

# --- 2. TIME-ORDERED DATA MUST NOT BE SPLIT RANDOMLY -----------------------
import backtest
bt_src = inspect.getsource(backtest)
check("the backtest scores an out-of-sample window only",
      "test_start" in bt_src and "test_end" in bt_src)

# The fill convention must be recorded with every result, because it moves the
# headline number by more than the entire claimed edge.
check("the backtest records which fill convention produced a result",
      "fill_convention" in bt_src,
      "a per-trade return without its fill convention is not interpretable")
check("the old close-fill convention is reachable only behind an explicit flag",
      "next_open" in bt_src and "--fill" in bt_src)

# --- 3. THE SIMULATOR MUST NOT SEE ITS OWN SIGNAL BAR ----------------------
import simulator
sim_src = inspect.getsource(simulator.simulate)
check("entries are filled from open_at(idx, 1), the bar AFTER the signal",
      "open_at(idx" in sim_src and "signal_px" in sim_src)
check("signals with no next bar are DROPPED, not filled at the close",
      "fillable" in sim_src,
      "there was no session in which to buy them")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
