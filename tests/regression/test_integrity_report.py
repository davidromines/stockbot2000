"""integrity_report (Stage AD1): runs on a sparse database without failing, and reports what it finds."""
import runtime  # noqa: F401
import sqlite3

import integrity_report as ir

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
c.executescript("""CREATE TABLE paper_trades (run_id TEXT, ticker TEXT, entry_date TEXT, pnl_pct REAL);
CREATE TABLE paper_trades_restated (version TEXT, run_id TEXT, ticker TEXT, entry_date TEXT, net_pct REAL, corporate_action INT);
CREATE TABLE survivorship_backtests (strategy_key TEXT, trades INT, sd_per_trade REAL);""")
c.executemany("INSERT INTO paper_trades VALUES ('r','T',?,1.0)", [(f"2026-10-{d:02d}",) for d in range(1, 11)])
c.executemany("INSERT INTO paper_trades_restated VALUES ('v2','r',?,'2026-10-01',1.0,?)", [("VZ", 1), ("A", 0), ("B", 0), ("C", 0)])
c.executemany("INSERT INTO survivorship_backtests VALUES ('s', ?, ?)", [(10, None), (10, 0.05), (1, None)])
c.commit()          # pandas rolls the connection back when a read fails (no slot_trades here): commit the fixture first
d = ir.collect(c)
check("restatement coverage = restated / closed", d["restated"]["restated"] == 4 and abs(d["restated"]["share"] - 0.4) < 1e-12)
check("corporate-action flags are counted with their tickers", d["restated"]["corporate_action"] == 1
      and d["restated"]["ca_top"][0][0] == "VZ")
check("dispersion coverage counts rows with 2+ trades", d["dispersion"] == {"rows": 2, "with_sd": 1}, d["dispersion"])
check("tables expected in the backup are checked", "missing" in d["backup"] and "absent" in d["backup"])
t = ir.render(d)
check("the report renders every section on a sparse database", all(f"## {i}." in t for i in range(1, 9)), t[:200])

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
