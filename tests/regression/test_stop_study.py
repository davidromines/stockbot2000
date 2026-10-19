"""stop_study (Stage AD3.6): excursions in ATR units from the restated record, per-family winners/losers statistics."""
import runtime  # noqa: F401
import json
import sqlite3

import pandas as pd

import stop_study as ss

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.executescript("""CREATE TABLE paper_trades_restated (version TEXT, run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT,
  entry_open_next REAL, exit_open_next REAL, gross_pct REAL, cost_pct REAL, net_pct REAL, net_usd REAL, corporate_action INT,
  computed_at TEXT);
CREATE TABLE paper_runs (run_id TEXT, strategy TEXT, family TEXT);
CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL);""")
c.execute("INSERT INTO paper_runs VALUES ('r1', ?, 'fam')", (json.dumps({"risk": {"stop_atr_multiple": 4.0}}),))
days = [f"2026-10-{d:02d}" for d in (1, 2, 5, 6, 7)]
for k in range(40):
    t = f"T{k}"
    win = k % 2 == 0
    for d in days:
        c.execute("INSERT INTO features VALUES (?,?,1.0)", (t, d))
    # entry 100 at the next open; path: winners dip to 99 (-1 ATR), losers to 97 (-3 ATR) and recover partly
    path = {"2026-10-02": (101, 99 if win else 97), "2026-10-05": (104 if win else 100.5, 100 if win else 97.5),
            "2026-10-06": (105 if win else 99, 103 if win else 98)}
    for d, (h, l) in path.items():
        c.execute("INSERT INTO prices VALUES (?,?,100,?,?,100,1)", (t, d, h, l))
    c.execute("INSERT INTO paper_trades_restated VALUES ('v2_next_open','r1',?,'2026-10-01','2026-10-06',100,0,0,0,?,0,0,'x')",
              (t, 3.0 if win else -2.0))
c.execute("INSERT INTO paper_trades_restated VALUES ('v2_next_open','r1','CA','2026-10-01','2026-10-06',100,0,0,0,-80,0,1,'x')")
tr = ss.trades(c)
check("corporate-action trades are excluded", "CA" not in set(tr.ticker) and len(tr) == 40)
check("the configured stop multiple is read from the fund's genome", (tr["stop_mult"] == 4.0).all())
x = ss.excursions(c, tr)
w = x[x.net_pct > 0]
check("MAE in ATR units: winners -1, losers -3", abs(w.mae_atr.min() + 1) < 1e-9 and abs(x[x.net_pct <= 0].mae_atr.min() + 3) < 1e-9)
check("MFE in ATR units: winners +5", abs(w.mfe_atr.max() - 5) < 1e-9)
s = ss.summarize(x).set_index("family").loc["fam"]
check("winners' MAE p90 and losers beyond it", abs(s.winners_mae_p90 + 1) < 1e-9 and s.losers_beyond == 1.0 and s.loss_beyond == -2.0, s)
check("losers' MFE p50 (what a trailing stop could have kept)", abs(s.losers_mfe_p50 - 1.0) < 1e-9, s.losers_mfe_p50)
check("report renders", "Stop study" in ss.render(ss.summarize(x)))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
