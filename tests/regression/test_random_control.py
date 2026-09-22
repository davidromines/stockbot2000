"""
REGRESSION: the random control must measure the strategies, not the pipeline's caps.

Section 17 asks how impressive random strategies can look after passing through
this exact pipeline. Two ways that measurement goes wrong silently:

1. **Turnover measured the sampling cap.** `simulate()` uniformly subsamples
   signals to `max_entries_per_eval`, so `n_trades` saturates and every busy
   strategy looks identically busy. The first control run returned p95, p99 and
   max turnover all equal to 20000/3 — a constant, printed as a distribution.
   Turnover must come from the pre-cap signal count.

2. **Rows pooled across pipeline changes.** A fitness, cost or gate change makes
   older rows describe a pipeline that no longer exists. Pooling them builds a
   calibration for something that was never run, and the result still looks like
   a distribution, so nothing announces the error.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_random_control.py
"""
import runtime  # noqa: F401
import copy
import sqlite3
import tempfile

import numpy as np

import random_control as rc
from universe import load_config

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


cfg = load_config()

# --- turnover comes from signals, not capped trades -------------------------
capped = {"n_trades": 20000, "n_signals": 91234, "entries_capped": True}
uncapped = {"n_trades": 300, "n_signals": 300, "entries_capped": False}

check("turnover uses the pre-cap signal count",
      rc._turnover(capped, 3.0) == 91234 / 3.0,
      f"got {rc._turnover(capped, 3.0):.1f} — the cap would give {20000/3.0:.1f}")
check("an uncapped strategy is unaffected",
      rc._turnover(uncapped, 3.0) == 100.0)
check("two strategies at the cap are still distinguishable",
      rc._turnover({"n_signals": 50000}, 3.0) != rc._turnover({"n_signals": 90000}, 3.0),
      "this is exactly what n_trades destroyed")
check("no signals means no turnover, not a divide-by-zero",
      rc._turnover({"n_signals": 0, "n_trades": 0}, 3.0) == 0.0)
check("a zero-length window does not divide by zero",
      rc._turnover({"n_signals": 10}, 0.0) == 0.0)

# --- the simulator actually reports the pre-cap count ------------------------
import simulator
import inspect
src = inspect.getsource(simulator.simulate)
check("simulate() records n_signals BEFORE applying the cap",
      src.index("n_signals = int(idx.size)") < src.index("idx = idx[(np.arange"),
      "recorded after subsampling, n_signals would just equal n_trades")
check("the empty result carries the same keys",
      "n_signals" in simulator._empty_result() and
      "entries_capped" in simulator._empty_result())

# --- the fingerprint separates pipelines ------------------------------------
base = rc.fingerprint(cfg)
check("the same config gives the same fingerprint", rc.fingerprint(cfg) == base)

for field, path in [("gates", ("lab", "gates")),
                    ("position size", ("risk", "position_size_usd")),
                    ("min_dollar_volume", ("risk", "min_dollar_volume"))]:
    c2 = copy.deepcopy(cfg)
    sect, key = path
    cur = c2[sect].get(key)
    c2[sect][key] = 999999 if not isinstance(cur, dict) else {"min_sharpe": 99}
    check(f"changing {field} changes the fingerprint",
          rc.fingerprint(c2) != base,
          "rows would pool across a pipeline change")

# --- place() refuses to calibrate on too little data ------------------------
conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
rc.init(conn)

try:
    rc.place(conn, base, "sharpe", 1.0)
    check("place() refuses an empty control set", False,
          "a percentile from nothing is not a calibration")
except SystemExit as e:
    check("place() refuses an empty control set", "too few" in str(e))

rows = [(f"2026-09-22T00:00:0{i%10}", base, "w", "{}", 10, 10, 0,
         float(i), float(i), i / 100.0, 0.1, 0.5, 100.0, 0)
        for i in range(100)]
conn.executemany("""INSERT INTO random_control (at, fingerprint, window, genome,
    n_trades, n_signals, entries_capped, net_pnl_usd, excess_pnl_usd, sharpe,
    max_drawdown, win_rate, turnover, passed_gate)
    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""", rows)
conn.commit()

# sharpe runs 0.00 .. 0.99
r = rc.place(conn, base, "sharpe", 0.95)
check("place() reports the share of noise that matched or beat the value",
      abs(r["beaten_by_noise"] - 0.05) < 1e-9,
      f"{r['beaten_by_noise']} — 5 of 100 samples are >= 0.95")
check("place() reports the noise maximum", abs(r["noise_max"] - 0.99) < 1e-9)

r0 = rc.place(conn, base, "sharpe", 0.0)
check("a value every noise sample matches is 100% beaten",
      abs(r0["beaten_by_noise"] - 1.0) < 1e-9)

# Drawdown inverts: smaller is better, so "beaten" means noise drew down LESS.
rd = rc.place(conn, base, "max_drawdown", 0.1)
check("drawdown is scored as smaller-is-better",
      abs(rd["beaten_by_noise"] - 1.0) < 1e-9,
      "every stored drawdown is 0.1, so all of noise matches it")

try:
    rc.place(conn, base, "not_a_metric", 1.0)
    check("an unknown metric is refused, not silently zero", False,
          "a typo would otherwise calibrate against an empty array")
except SystemExit as e:
    check("an unknown metric is refused, not silently zero",
          "unknown metric" in str(e))

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
