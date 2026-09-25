"""Regression checks for crypto_trend.py (Stage K3)."""
import runtime  # noqa: F401

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import numpy as np

import crypto_trend as ct

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + ("  " + detail if detail else ""))
        FAILED.append(name)


def arr(x):
    return np.array(x, dtype=float)


# --- entry fills at o[i+1], not c[i] -------------------------------------
# Rising closes so trend_sma fires at i=2 (n=2); bar 3 opens well above c[2].
o = arr([10, 10, 10, 20, 20, 20])
h = arr([11, 11, 11, 21, 21, 21])
l = arr([9, 9, 9, 19, 19, 19])
c = arr([10, 10, 12, 20, 20, 20])
g = {"family": "trend_sma", "n": 2, "stop_atr": 100.0, "atr_n": 2}
r = ct.simulate(o, h, l, c, g, 0.0, start_i=0, close_at_end=True)
t0 = r["trades"][0]
check("entry fills at next open", t0["entry_i"] == 3 and t0["entry_px"] == 20.0,
      str(t0))
check("entry not at signal close", t0["entry_px"] != c[2], str(t0["entry_px"]))

# --- signal exit fills at the next bar's open ----------------------------
# c[3]=20 keeps the entry condition true, c[4]=5 breaks it -> exit signal at 4,
# fill at o[5].
o2 = arr([10, 10, 10, 20, 20, 30])
h2 = arr([11, 11, 11, 21, 21, 31])
l2 = arr([9, 9, 9, 19, 19, 29])
c2 = arr([10, 10, 12, 20, 5, 30])
r2 = ct.simulate(o2, h2, l2, c2, g, 0.0, start_i=0, close_at_end=True)
sig = [t for t in r2["trades"] if t["reason"] == "signal"]
check("signal exit at next open", len(sig) == 1 and sig[0]["exit_i"] == 5
      and sig[0]["exit_px"] == 30.0, str(sig))

# --- stop with open below the stop fills at the open (gap-through) -------
# ATR at i=2 is 2.0, entry at o[3]=20 -> stop 18. Bar 4 opens at 15.
o3 = arr([10, 10, 10, 20, 15, 15])
h3 = arr([11, 11, 11, 21, 16, 16])
l3 = arr([9, 9, 9, 19, 14, 14])
c3 = arr([10, 10, 12, 20, 15, 15])
g3 = {"family": "trend_sma", "n": 2, "stop_atr": 1.0, "atr_n": 2}
r3 = ct.simulate(o3, h3, l3, c3, g3, 0.0, start_i=0, close_at_end=True)
s3 = [t for t in r3["trades"] if t["reason"] == "stop"]
check("gap-through stop fills at open", len(s3) == 1 and s3[0]["exit_px"] == 15.0
      and s3[0]["exit_i"] == 4, str(s3))

# --- stop with open above the stop fills at the stop ---------------------
o4 = arr([10, 10, 10, 20, 20, 20])
h4 = arr([11, 11, 11, 21, 21, 21])
l4 = arr([9, 9, 9, 19, 17, 19])
c4 = arr([10, 10, 12, 20, 20, 20])
r4 = ct.simulate(o4, h4, l4, c4, g3, 0.0, start_i=0, close_at_end=True)
s4 = [t for t in r4["trades"] if t["reason"] == "stop"]
check("stop fills at stop price", len(s4) == 1 and abs(s4[0]["exit_px"] - 18.0) < 1e-12,
      str(s4))

# --- no entry from a signal before start_i -------------------------------
r5 = ct.simulate(o, h, l, c, g, 0.0, start_i=4, close_at_end=True)
check("no entry before start_i", all(t["entry_i"] >= 4 for t in r5["trades"]),
      str(r5["trades"]))

# --- after a stop, no re-entry until the entry signal has been False -----
# Stop fires at bar 4; bars 5-6 still satisfy the entry condition, so no
# re-entry is allowed until it goes False.
o6 = arr([10, 10, 10, 20, 15, 15, 15, 15, 15])
h6 = arr([11, 11, 11, 21, 16, 16, 16, 16, 16])
l6 = arr([9, 9, 9, 19, 14, 14, 14, 14, 14])
c6 = arr([10, 10, 12, 20, 15, 15, 15, 15, 15])
r6 = ct.simulate(o6, h6, l6, c6, g3, 0.0, start_i=0, close_at_end=True)
check("no re-entry while waiting for reset", len(r6["trades"]) == 1,
      str(r6["trades"]))

# --- a real reset: stop at bar 4 while the trend is still up; entry True at 5-6
# is ignored, False at 7 resets, True at 8 re-enters at o[9].
o9 = arr([10, 10, 10, 20, 20, 22, 23, 20, 15, 20, 21])
c9 = arr([10, 10, 12, 20, 21, 22, 23, 15, 20, 21, 22])
h9 = np.maximum(o9, c9) + 1
l9 = np.minimum(o9, c9) - 1
l9[4] = 16.5                                   # through the 17.0 stop (ATR 3), then closes higher
r9 = ct.simulate(o9, h9, l9, c9, g3, 0.0, start_i=0, close_at_end=True)
t9 = r9["trades"]
check("stop at bar 4 at the stop price", t9 and t9[0]["reason"] == "stop" and t9[0]["exit_i"] == 4
      and t9[0]["exit_px"] == t9[0]["stop"] == 17.0, str(t9))
check("re-entry only after the signal reset (fill o[9])", len(t9) == 2 and t9[1]["entry_i"] == 9, str(t9))

# --- close_at_end False returns an open position -------------------------
o7 = arr([10, 10, 10, 20, 25, 30])
c7 = arr([10, 10, 12, 20, 25, 30])
r7 = ct.simulate(o7, np.maximum(o7, c7) + 1, np.minimum(o7, c7) - 1, c7, g, 0.0,
                 start_i=0, close_at_end=False)
check("close_at_end False leaves position open",
      r7["open"] is not None and r7["open"]["entry_i"] == 3
      and r7["open"]["entry_px"] == 20.0, str(r7["open"]))

# --- net equals the cost formula for hs = 0.01 ---------------------------
hs = 0.01
r8 = ct.simulate(o2, h2, l2, c2, g, hs, start_i=0, close_at_end=True)
t8 = r8["trades"][0]
expect = t8["exit_px"] * (1 - hs) / (t8["entry_px"] * (1 + hs)) - 1
check("net matches cost formula", abs(t8["net"] - expect) < 1e-12, str(t8["net"]))

# --- null_per_trade on a constant-price series ---------------------------
flat = arr([100.0] * 20)
trades = [{"bars": 3}]
npt = ct.null_per_trade(flat, trades, hs, 0, 19)
check("null on constant prices", abs(npt - ((1 - hs) / (1 + hs) - 1)) < 1e-12, str(npt))

# --- buy_and_hold matches its formula ------------------------------------
bh = ct.buy_and_hold(o2, c2, 0, 5, hs)
check("buy_and_hold formula", abs(bh - (c2[5] * (1 - hs) / (o2[0] * (1 + hs)) - 1)) < 1e-12,
      str(bh))

# --- summarize on an empty trade list ------------------------------------
s = ct.summarize([])
check("summarize empty", s["trades"] == 0 and s["net_per_trade"] is None, str(s))

if FAILED:
    print("FAILED: " + ", ".join(FAILED))
    sys.exit(1)
print("ALL PASS")
