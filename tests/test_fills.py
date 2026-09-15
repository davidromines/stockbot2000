"""
Synthetic check of next-open fills and gap-through-stop.

Twelve bars of one invented ticker, chosen so every number below can be verified
by hand. The signal fires on bar 2 at a close of 102; the fill must land on bar
3's OPEN of 103. Bar 4 then closes at 90, breaching a stop of 93 — and bar 5
opens at 50, so the exit must fill at 50 rather than at the 90 that triggered it.

That single trade is the whole argument for this change. Under the old
close-to-close convention it booked -$11.76 and the stop looked like insurance.
Filled the way the account actually works it loses -$51.46. A stop that cannot
rest at the broker does not cap anything overnight, and until this test existed
the simulator assumed it did.

Run:  PYTHONPATH=. venv/bin/python tests/test_fills.py
"""
import runtime, numpy as np, pandas as pd, simulator, costs

# One ticker, 12 bars. Close rises to bar 3 then CRASHES with a huge overnight
# gap: bar 4 closes at 90 (below a stop), bar 5 OPENS at 50.
close = [100, 101, 102, 103,  90,  50,  49,  48,  47,  46,  45,  44]
open_ = [100, 101, 102, 103,  99,  50,  49,  48,  47,  46,  45,  44]
df = pd.DataFrame({
    "ticker": ["X"] * 12,
    "date": pd.date_range("2020-01-01", periods=12, freq="D"),
    "close": np.array(close, dtype="float64"),
    "open": np.array(open_, dtype="float64"),
    "atr_14": [5.0] * 12,
    "dollar_volume_20": [50_000_000.0] * 12,
})
panel = simulator.Panel(df, max_hold=6, exit_prices=df[["ticker", "date", "close", "open"]])

# Entry fires on bar 2 only (close == 102).
g = {"entry": {"op": "and", "args": [
         {"op": "gt", "args": [{"col": "close"}, {"const": 101.5}]},
         {"op": "lt", "args": [{"col": "close"}, {"const": 102.5}]}]},
     "exit":  {"op": "lt", "args": [{"col": "close"}, {"const": 0.0}]},
     "risk":  {"max_hold_days": 6, "stop_atr_multiple": 2.0}}

cm = costs.CostModel({"costs": {"enabled": False}})
r = simulator.simulate(g, panel, cm, position_size_usd=100.0)

print(f"  trades           {r['n_trades']}")
print(f"  entry price      {r['entry_price'][0]:.2f}   (expect 103.00 = open of bar 3, NOT 102 close)")
print(f"  exit price       {r['exit_price'][0]:.2f}   (expect  50.00 = open of bar 5, NOT the 90 close)")
print(f"  exit reason      {r['exit_reason'][0]}")
print(f"  stop level       {103 - 2*5:.2f}")
print(f"  gap loss $       {r['gap_loss_usd']:.2f}   (expect ~-42.7: filled 43 below a 93 stop)")
print(f"  entry slip $     {r['entry_slip_usd']:.2f}   (expect ~+0.98: paid 103 vs a 102 signal)")
print(f"  net P&L $        {r['net_pnl_usd']:.2f}")

ok = (abs(r["entry_price"][0] - 103.0) < 1e-6 and abs(r["exit_price"][0] - 50.0) < 1e-6
      and r["exit_reason"][0] == "stop_loss" and r["gap_loss_usd"] < -40)
print("\n  RESULT:", "PASS" if ok else "FAIL")

raise SystemExit(0 if ok else 1)
