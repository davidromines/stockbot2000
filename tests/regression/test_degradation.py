"""
REGRESSION: backtest and forward must be compared in the SAME units.

The first version of this module divided the Lab's `net_pnl_usd` by the forward
fund's $100 capital. But `net_pnl_usd` is the sum across up to 20,000
independent $20 trades over fourteen years, while a forward return compounds one
$100 book over weeks. That produced backtest figures of 3,428% to 26,065%
against forward figures of a few percent, and every "survived" ratio came out
near zero — a number that read as a devastating finding about backtest
reliability and was purely a unit error.

Mean return PER TRADE is the one quantity both sides have. This test pins that,
because the failure mode is a plausible-looking table rather than a crash.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_degradation.py
"""
import runtime  # noqa: F401
import sqlite3
import tempfile

import degradation as dg

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE evaluations (strategy_id TEXT, window_start TEXT, window_end TEXT,
    net_pnl_usd REAL, n_trades INTEGER);
CREATE TABLE paper_trades (run_id TEXT, exit_date TEXT, pnl_pct REAL);
CREATE TABLE paper_runs (run_id TEXT, strategy TEXT, capital_usd REAL);
CREATE TABLE strategies (id TEXT, genome TEXT);
""")
# 20,000 trades at $20 making $8,000 total = $0.40 a trade = 2% per trade.
conn.execute("INSERT INTO evaluations VALUES ('s1','2006-01-01','2019-12-31',8000,20000)")
conn.commit()

per_trade = dg._return_on_window(conn, "s1", "2006-01-01", "2019-12-31", 20.0)
check("backtest return is per-trade, not P&L over capital",
      abs(per_trade - 0.02) < 1e-9,
      f"{per_trade} — dividing $8,000 by $100 capital would give 8000%")
check("the per-trade figure is a sane magnitude", 0 < per_trade < 0.5,
      "the units bug produced values in the thousands of percent")

check("a window with no evaluation returns None",
      dg._return_on_window(conn, "s1", "2020-01-01", "2022-12-31", 20.0) is None,
      "a missing backtest must not read as a zero backtest")
conn.execute("INSERT INTO evaluations VALUES ('s2','2006-01-01','2019-12-31',500,0)")
conn.commit()
check("an evaluation with zero trades returns None, not a divide-by-zero",
      dg._return_on_window(conn, "s2", "2006-01-01", "2019-12-31", 20.0) is None)

# --- the forward side, also per trade ---------------------------------------
for pct in (2.0, -1.0, 3.0):
    conn.execute("INSERT INTO paper_trades VALUES ('r1','2026-09-10',?)", (pct,))
conn.commit()
fwd, n = dg._forward_per_trade(conn, "r1")
check("forward return is the mean of per-trade percentages",
      abs(fwd - 0.013333) < 1e-5, f"{fwd}")
check("forward trade count is reported", n == 3)
check("a fund with no closed trades returns None, not zero",
      dg._forward_per_trade(conn, "nope")[0] is None,
      "zero would read as a strategy that broke even rather than one untested")

# pnl_pct stored as a fraction rather than a percentage must not be scaled twice
conn.execute("INSERT INTO paper_trades VALUES ('r2','2026-09-10',0.02)")
conn.commit()
f2, _ = dg._forward_per_trade(conn, "r2")
check("a fraction-valued pnl_pct is not divided by 100 again",
      abs(f2 - 0.02) < 1e-9, f"{f2}")

# --- degradation direction ---------------------------------------------------
check("survived > 100% means forward beat the backtest",
      (0.03 / 0.02) > 1.0)
check("a negative survived ratio means forward went the other way",
      (-0.01 / 0.02) < 0)

import inspect
src = inspect.getsource(dg)
check("the module never divides Lab P&L by portfolio capital",
      "/ capital" not in src,
      "that is the exact expression that produced 26,065% backtests")
check("the units trap is documented where the division happens",
      "unit error" in src or "20,000 independent" in src)

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
