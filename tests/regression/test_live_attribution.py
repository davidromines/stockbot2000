"""live_attribution: trade pairing, the SPY counterfactual, exit classification and the review's four answers (Stage AD9)."""
import runtime  # noqa: F401
import json
import sqlite3

import live_attribution as la

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

c = sqlite3.connect(":memory:")
c.executescript("""
CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INT, strategy_key TEXT, version INT,
  symbol TEXT, action TEXT, quantity REAL, price REAL, atr REAL, stop_plan TEXT, reason TEXT, signal_id TEXT);
CREATE TABLE slot_marks (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INT, symbol TEXT, price REAL, high REAL, stop REAL, verdict TEXT);
CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL);
CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL);
CREATE TABLE symbols (ticker TEXT, security_type TEXT);
CREATE TABLE risk_metrics (ticker TEXT, date TEXT, beta REAL, ivol REAL, alpha REAL);
CREATE TABLE orders (created_at TEXT, mode TEXT, symbol TEXT, side TEXT, avg_fill_price REAL, quote_price REAL);
CREATE TABLE live_equity (at TEXT, session TEXT, equity REAL, buying_power REAL);
""")
for d, o, cl in (("2026-10-01", 100, 101), ("2026-10-02", 101, 102), ("2026-10-05", 102, 103), ("2026-10-06", 103, 104)):
    c.execute("INSERT INTO prices VALUES ('SPY',?,?,?,?,?,1)", (d, o, cl, o, cl))
for t, p in (("AAA", 50.0), ("BBB", 20.0), ("CCC", 10.0)):
    c.execute("INSERT INTO symbols VALUES (?, 'common_stock')", (t,))
    for d in ("2026-10-01", "2026-10-05"):
        c.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,1)", (t, d, p, p, p, p))
c.executemany("INSERT INTO features VALUES (?,?,?,?)", [("AAA", "2026-10-01", 3.5, 5e7), ("BBB", "2026-10-01", 0.2, 5e7),
                                                        ("CCC", "2026-10-01", 0.3, 5e7)])
plan = json.dumps([{"type": "atr", "atr_multiple": 3.0}])
rows = [("2026-10-01T13:35:00", 1, "fx_a", "AAA", "OPEN", 0.4, 50.0, 3.5, plan, "entry rule"),
        ("2026-10-02T13:35:00", 1, "fx_a", "AAA", "CLOSE", 0.4, 45.0, None, None, "slot released or reassigned"),
        ("2026-10-01T13:36:00", 2, "fx_b", "BBB", "OPEN", 1.0, 20.0, 0.2, plan, "entry rule"),
        ("2026-10-05T13:36:00", 2, "fx_b", "BBB", "CLOSE", 1.0, 22.0, None, None, "strategy exit signal"),
        ("2026-10-05T13:37:00", 3, "fx_c", "CCC", "OPEN", 2.0, 10.0, 0.3, plan, "entry rule")]
for i, r in enumerate(rows):
    c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, atr, "
              "stop_plan, reason) VALUES (?,?,?,?,1,?,?,?,?,?,?,?)", (r[0], "LIVE", *r[1:]))
c.execute("INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol, action, quantity, price, reason) "
          "VALUES ('2026-10-01T13:00:00','SIMULATION',5,'fx_z',1,'ZZZ','OPEN',1,1,'sim')")
c.execute("INSERT INTO slot_marks (at, mode, slot_id, symbol, price) VALUES ('2026-10-06T15:00:00','LIVE',3,'CCC',11.0)")
c.execute("INSERT INTO orders VALUES ('2026-10-01T13:35:00','LIVE','AAA','BUY',50.0,49.5)")
c.execute("INSERT INTO risk_metrics VALUES ('CCC','2026-09-30',1.5,0.3,0)")
c.execute("INSERT INTO live_equity VALUES ('2026-10-01T13:30:00','2026-10-01',100,100)")
c.execute("INSERT INTO live_equity VALUES ('2026-10-06T20:00:00','2026-10-06',101.8,0)")

r = la.build(c, "LIVE")
t = r["trades"].set_index("symbol")
check("pairs OPEN with CLOSE per slot and symbol, LIVE only", set(t.index) == {"AAA", "BBB", "CCC"})
check("trade return is fill to fill", abs(t.loc["AAA", "ret"] - (-0.10)) < 1e-12 and abs(t.loc["BBB", "ret"] - 0.10) < 1e-12)
check("an open trade is marked at the newest live mark", t.loc["CCC", "kind"] == "open" and t.loc["CCC", "exit"] == 11.0)
check("SPY counterfactual = entry-day open to exit-day close", abs(t.loc["BBB", "spy"] - (103 / 100 - 1)) < 1e-12, t.loc["BBB", "spy"])
check("excess = return - SPY", abs(t.loc["AAA", "excess"] - (-0.10 - (102 / 100 - 1))) < 1e-12)
check("exit kinds: reassignment, strategy exit, open",
      (t.loc["AAA", "kind"], t.loc["BBB", "kind"], t.loc["CCC", "kind"]) == ("reassignment", "strategy exit", "open"))
check("stop width = 3 x ATR / entry", abs(t.loc["AAA", "stop_width"] - 0.21) < 1e-12)
check("volatility percentile at entry: the most volatile name ranks highest", t.loc["AAA", "vol_pct"] > t.loc["BBB", "vol_pct"])
check("fill vs decision-time quote (buys: positive = paid more)", abs(t.loc["AAA", "fill_vs_quote"] - (50 / 49.5 - 1)) < 1e-12)
a = r["account"]
check("account change and drawdown from live_equity", abs(a["change"] - 1.8) < 1e-9 and a["drawdown_pct"] == 0)
check("ledger: realised + unrealised, and the gap to the equity change",
      abs(a["realised"] - (-2.0 + 2.0)) < 1e-9 and abs(a["unrealised"] - 2.0) < 1e-9 and abs(a["ledger_gap"] - (-0.2)) < 1e-9, a)
check("book beta from risk_metrics", abs(a["book_beta"] - 1.5) < 1e-12)
v = " ".join(la.verdict(r))
check("the four review answers are stated", all(k in v for k in ("Prediction:", "Turnover:", "Execution:", "Allocation:")), v)
check("render and the summary line work", "Live attribution" in la.render(r) and "SPY" in la.summary_line(r))
empty = sqlite3.connect(":memory:")
empty.executescript("CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INT, strategy_key TEXT, "
                    "version INT, symbol TEXT, action TEXT, quantity REAL, price REAL, atr REAL, stop_plan TEXT, reason TEXT)")
check("no trades: no crash", la.verdict(la.build(empty)) == ["no live trades"])

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
