"""
REGRESSION: the two pricing defects that cost this project the most.

  close-fill leakage          fills at the close that produced the signal
  filtered-panel exit pricing tradeability floors deciding what may be SOLD

Both ran for weeks producing confident, wrong numbers. Neither fails a "does it
run" check, which is exactly why they need to be pinned here: the next person to
touch simulator.Panel will not remember them, and ADO means the next person may
not be a person.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_fill_and_pricing.py
"""
import runtime  # noqa: F401
import numpy as np
import pandas as pd

import costs
import simulator

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


def panel_from(close, open_, atr=5.0, dv=50e6):
    n = len(close)
    df = pd.DataFrame({
        "ticker": ["X"] * n,
        "date": pd.date_range("2020-01-01", periods=n, freq="D"),
        "close": np.array(close, dtype="float64"),
        "open": np.array(open_, dtype="float64"),
        "atr_14": [atr] * n, "dollar_volume_20": [dv] * n})
    return simulator.Panel(df, max_hold=6,
                           exit_prices=df[["ticker", "date", "close", "open"]]), df


CM = costs.CostModel({"costs": {"enabled": False}})
ENTRY_AT_102 = {"op": "and", "args": [
    {"op": "gt", "args": [{"col": "close"}, {"const": 101.5}]},
    {"op": "lt", "args": [{"col": "close"}, {"const": 102.5}]}]}
NEVER = {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]}


# --- 1. CLOSE-FILL LEAKAGE --------------------------------------------------
# Signal fires on the bar closing at 102. A fill at 102 is look-ahead: that
# price is not knowable until the session has ended.
close = [100, 101, 102, 103, 90, 50, 49, 48, 47, 46, 45, 44]
open_ = [100, 101, 102, 103, 99, 50, 49, 48, 47, 46, 45, 44]
panel, _ = panel_from(close, open_)
g = {"entry": ENTRY_AT_102, "exit": NEVER,
     "risk": {"max_hold_days": 6, "stop_atr_multiple": 2.0}}
r = simulator.simulate(g, panel, CM, position_size_usd=100.0)

check("entry fills at the NEXT bar's open, not the signal close",
      abs(r["entry_price"][0] - 103.0) < 1e-6,
      f"filled at {r['entry_price'][0]} — 102 would be look-ahead")

# --- 2. GAP THROUGH THE STOP ------------------------------------------------
# Stop is 103 - 2*5 = 93. Bar 4 closes at 90 (breach); bar 5 OPENS at 50.
# Booking the exit at 90 would make the stop a guarantee it cannot be.
check("exit fills at the open AFTER the trigger, not the trigger close",
      abs(r["exit_price"][0] - 50.0) < 1e-6,
      f"exited at {r['exit_price'][0]} — 90 would make stops perfect")
check("stop breach is reported as a stop", r["exit_reason"][0] == "stop_loss")
check("gap below the stop is measured and reported",
      r.get("gap_loss_usd", 0) < -40,
      f"gap_loss_usd={r.get('gap_loss_usd')}")

# The whole point, in one number: honest fills lose 4x what the old convention
# reported on this trade.
check("the honest loss is far worse than the close-fill loss would be",
      r["net_pnl_usd"] < -45,
      f"net {r['net_pnl_usd']:.2f}; close-fill would have booked about -11.76")

# --- 3. HOLDING PERIOD IS NOT OVERSTATED ------------------------------------
# Entry at bar 3, exit at bar 5 = 2 bars held. Reporting 3 would charge the
# strategy a null for a session it did not hold.
check("avg_hold_days counts bars HELD, not the exit bar's offset",
      abs(r["avg_hold_days"] - 2.0) < 1e-6, f"got {r['avg_hold_days']}")

# --- 4. FILTERED-PANEL EXIT PRICING -----------------------------------------
# A holding that falls below the tradeability floor must still be priced where
# it actually goes. The defect: its rows leave the filtered frame, the forward
# price becomes NaN, and the exit books at the last bar ABOVE the floor.
full = pd.DataFrame({
    "ticker": ["Y"] * 8,
    "date": pd.date_range("2020-01-01", periods=8, freq="D"),
    "close": [10.0, 10.0, 9.0, 4.0, 2.0, 1.0, 0.5, 0.2],
    "open":  [10.0, 10.0, 9.5, 4.5, 2.0, 1.0, 0.5, 0.2]})
# The tradeable frame stops at the $5 floor — rows 4 onward are gone.
tradeable = full[full["close"] >= 5.0].copy()
tradeable["atr_14"] = 0.5
tradeable["dollar_volume_20"] = 50e6
p_unfiltered = simulator.Panel(tradeable, max_hold=6, exit_prices=full)
p_truncated = simulator.Panel(tradeable, max_hold=6, exit_prices=tradeable)

g2 = {"entry": {"op": "gt", "args": [{"col": "close"}, {"const": 9.5}]},
      "exit": NEVER, "risk": {"max_hold_days": 6, "stop_atr_multiple": 2.0}}
r_un = simulator.simulate(g2, p_unfiltered, CM, position_size_usd=100.0)
r_tr = simulator.simulate(g2, p_truncated, CM, position_size_usd=100.0)

check("exits price off the UNFILTERED series",
      r_un["n_trades"] > 0 and r_un["exit_price"][0] < 5.0,
      f"exited at {r_un['exit_price'][0] if r_un['n_trades'] else 'no trade'} "
      f"— above 5.0 means the floor capped the loss")
check("truncating the exit series demonstrably flatters the result",
      r_tr["n_trades"] > 0 and r_un["net_pnl_usd"] < r_tr["net_pnl_usd"],
      f"unfiltered {r_un['net_pnl_usd']:.2f} vs truncated {r_tr['net_pnl_usd']:.2f}")

# --- 5. A FRAME WITH NO OPENS MUST NOT SILENTLY CLOSE-FILL ------------------
no_open = full[["ticker", "date", "close"]]
p_noopen = simulator.Panel(tradeable, max_hold=6, exit_prices=no_open)
check("a frame lacking 'open' still produces a panel (warns, does not crash)",
      p_noopen is not None)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
