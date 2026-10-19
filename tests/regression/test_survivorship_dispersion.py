"""survivorship_backtest: the dispersion columns (Stage AD3.2) — migration of an old table, by-name writes, the values."""
import runtime  # noqa: F401
import sqlite3

import numpy as np

import survivorship_backtest as sb

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.execute("""CREATE TABLE survivorship_backtests (strategy_key TEXT NOT NULL, version INTEGER NOT NULL, mode TEXT NOT NULL,
    generator TEXT NOT NULL, window TEXT NOT NULL, trades INTEGER, synthetic_trades INTEGER, gross_usd REAL, costs_usd REAL,
    net_usd REAL, per_trade REAL, share_deep REAL, computed_at TEXT NOT NULL,
    PRIMARY KEY (strategy_key, version, mode, generator, window))""")
c.execute("INSERT INTO survivorship_backtests VALUES ('old',1,'as_is','g','w',10,0,1,0.1,0.9,0.0045,0.1,'2026-10-01')")
sb.init(c)
cols = [r[1] for r in c.execute("PRAGMA table_info(survivorship_backtests)")]
check("an existing table gains the three columns", all(x in cols for x in sb.EXTRA_COLS), cols)
check("old rows keep their values and read NULL in the new columns",
      c.execute("SELECT per_trade, sd_per_trade, entry_dates FROM survivorship_backtests WHERE strategy_key='old'").fetchone()
      == (0.0045, None, None))
sb.init(c)
check("init is idempotent", [r[1] for r in c.execute("PRAGMA table_info(survivorship_backtests)")] == cols)

r = {"pnl_series": np.array([2.0, -1.0, 0.5, 1.5]), "avg_hold_days": 12.5, "entry_rows": np.array([0, 1, 2, 4])}
dates = np.array(["2016-01-04", "2016-01-04", "2016-01-05", "2016-01-06", "2016-01-06"])
d = sb.dispersion(r, 20.0, dates)
check("sd per trade is the sample sd of net return per trade", abs(d["sd_per_trade"] - np.std(r["pnl_series"] / 20, ddof=1)) < 1e-12, d)
check("holding days and distinct entry dates", d["avg_hold_days"] == 12.5 and d["entry_dates"] == 3.0, d)
check("no trades: all None", sb.dispersion({"pnl_series": np.array([]), "entry_rows": np.array([], dtype=int)}, 20, dates)
      == {"sd_per_trade": None, "avg_hold_days": None, "entry_dates": None})
sb.write_row(c, {"strategy_key": "new", "version": 1, "mode": "as_is", "generator": "g", "window": "w", "trades": 4,
                 "synthetic_trades": 0, "gross_usd": 3, "costs_usd": 0.1, "net_usd": 3.0, "per_trade": 0.0375,
                 "share_deep": 0.0, "computed_at": "2026-10-19", **d})
got = c.execute("SELECT per_trade, sd_per_trade, avg_hold_days, entry_dates FROM survivorship_backtests "
                "WHERE strategy_key='new'").fetchone()
check("rows are written by column name, new columns included", got[0] == 0.0375 and abs(got[1] - d["sd_per_trade"]) < 1e-12
      and got[2] == 12.5 and got[3] == 3.0, got)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
