"""Addendum F phase D: survivorship dependence and execution realism helpers (synthetic data)."""
import runtime  # noqa: F401
import numpy as np
import pandas as pd
import audit_execution as ae
import audit_survivorship as asv

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

# --- survivorship: verdict changes and generator sensitivity ---
rows = []
for i, (ex, ai, ze) in enumerate([(.02, .01, .005), (.01, .004, -.01), (.01, -.004, -.02), (-.01, -.02, -.03)]):
    for mode, v in (("exclude", ex), ("as_is", ai), ("zero", ze)):
        rows.append({"strategy_key": f"s{i}", "version": 1, "mode": mode, "generator": "g2", "trades": 100, "synthetic_trades": 0 if mode == "exclude" else 40,
                     "per_trade": v, "share_deep": 0.0, "computed_at": "2026-10-02"})
d = pd.DataFrame(rows)
w, gen = asv.latest_by_mode(d)
vc = asv.verdict_changes(w)
check("positive counts per mode", vc["pos"] == {"exclude": 3, "as_is": 2, "zero": 1})
check("positive as_is but non-positive worst case counted (s1 only)", vc["as_is_pos_zero_neg"] == 1)
check("positive survivors-only but negative as_is counted (s2 only)", vc["exclude_pos_as_is_neg"] == 1)
check("synthetic share = synthetic trades / trades", abs(w["synth_share"].iloc[0] - 0.4) < 1e-9)
old = d[d["mode"] == "as_is"].assign(generator="g1", computed_at="2026-09-25", per_trade=lambda x: -x["per_trade"])
gs = asv.generator_sensitivity(pd.concat([d, old]))
check("sign flips between generators are counted", gs["flips"] == 4 and gs["n_multi"] == 4)
check("generator labels are readable", "v5" in asv.gen_label("synthetic_v5.parquet:465003674|fund:1|vol:2") and "fundamentals" in asv.gen_label("synthetic_v5.parquet:1|fund:1|vol:2"))

# --- execution: signed adverse move ---
t = pd.DataFrame({"id": [1, 2], "at": ["2026-10-02T13:35:00", "2026-10-02T13:36:00"], "slot_id": [1, 2], "symbol": ["A", "B"],
                  "action": ["OPEN", "CLOSE"], "quantity": 1.0, "price": [101.0, 99.0], "reason": ["entry", "exit"]})
t["date"] = t["at"].str[:10]; t["standin"] = False
import sqlite3
c = sqlite3.connect(":memory:")
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, close REAL)")
for tk in "AB":
    c.execute("INSERT INTO prices VALUES (?,?,?,?)", (tk, "2026-10-01", 100, 100))
    c.execute("INSERT INTO prices VALUES (?,?,?,?)", (tk, "2026-10-02", 100, 100))
g = ae.fill_gaps(c, t)
check("buying 1% above the open and selling 1% below it are both +1% adverse", np.allclose(g["adverse_vs_open_pct"], [1.0, 1.0]))
check("fill vs prior close is computed", np.allclose(g["vs_prev_close_pct"], [1.0, -1.0]))
o = sqlite3.connect(":memory:")
o.execute("CREATE TABLE orders (side TEXT, mode TEXT, quote_price REAL, avg_fill_price REAL)")
o.execute("INSERT INTO orders VALUES ('BUY','LIVE',100,100.5)"); o.execute("INSERT INTO orders VALUES ('SELL','LIVE',100,99.5)")
q = ae.quote_gaps(o)
check("quote-to-fill adverse sign: buy above and sell below are positive", np.allclose(q["adverse_pct"], [0.5, 0.5]))
print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
