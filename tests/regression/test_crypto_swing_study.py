"""crypto_swing_study: signals use only this and earlier closes; fills buy at the next open at the ask and sell H hours
later at the bid; one position per coin at a time."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd

import crypto_swing_study as cs

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


close = np.array([100, 101, 102, 101, 110, 111, 109, 120], dtype=float)
b = cs.signals(close, "breakout", 3)
check("breakout fires on a close above the previous 3 closes (hours 4, 5 and 7)",
      list(np.flatnonzero(b)) == [4, 5, 7], list(np.flatnonzero(b)))
c2 = close.copy(); c2[7] = 50.0
check("a later close never changes an earlier signal (no look-ahead)", cs.signals(c2, "breakout", 3)[4])
m = cs.signals(np.r_[np.full(24, 100.0), [106.0]], "momentum", 0.05)
check("momentum: 24-hour return above +5% fires", m[-1] and not m[:-1].any())
d = cs.signals(np.r_[np.full(24, 100.0), [94.0]], "dip", 0.05)
check("dip: 24-hour return below -5% fires", d[-1] and not d[:-1].any())

n = 40
df = pd.DataFrame({"symbol": "BTC-USD", "open_time": np.arange(n) * 3600, "open": np.full(n, 100.0),
                   "close": np.r_[np.full(30, 100.0), np.full(10, 100.0)]})
df.loc[25, "close"] = 120.0                                     # one breakout at hour 25
df.loc[26:, "open"] = 110.0
tr = cs.trades(df, "breakout", 24, 12, {"BTC-USD": 0.01})
check("one trade: buy at the open of hour 26 x (1 + half spread), sell at the open of hour 38 x (1 - half spread)",
      len(tr) == 1 and abs(tr["ret"].iloc[0] - (110 * 0.99 / (110 * 1.01) - 1)) < 1e-12, tr.to_dict("records"))
check("a flat price loses the spread", tr["ret"].iloc[0] < 0)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
