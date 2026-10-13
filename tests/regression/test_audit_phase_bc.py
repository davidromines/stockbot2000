"""Addendum F phases B and C: ranking audit estimators, the shadow capital gate, the funnel and the portfolio helpers.
Synthetic data only; no production database."""
import runtime  # noqa: F401
import inspect
import sqlite3
import numpy as np
import pandas as pd

import audit_pipeline as ap
import audit_portfolio as apo
import audit_ranking as ar
import capital_gate as cg

FAILS = []
def check(name, ok):
    print(("  PASS  " if ok else "  FAIL  ") + name)
    if not ok: FAILS.append(name)

rng = np.random.default_rng(7)

# --- audit_ranking.eb_estimates / outcomes ---
rows = []
for r in range(40):                                       # 40 funds, 10 dates each, true mean 0.3
    for d in range(10):
        rows.append({"run_id": f"r{r}", "ticker": "A", "entry_date": f"2026-10-{d + 1:02d}", "net_pct": rng.normal(0.3, 2.0)})
rows.append({"run_id": "one", "ticker": "B", "entry_date": "2026-10-01", "net_pct": 90.0})   # one lucky date
rows.append({"run_id": "good", "ticker": "C", "entry_date": "2026-10-01", "net_pct": 5.0})
tr = pd.DataFrame(rows)
for d in range(2, 12):                                    # a steady winner on 10 dates
    tr = pd.concat([tr, pd.DataFrame([{"run_id": "steady", "ticker": "S", "entry_date": f"2026-10-{d:02d}", "net_pct": 3.0 + rng.normal(0, .2)}])])
eb = ar.eb_estimates(tr, "2026-11-01")
pool = tr.groupby(["run_id", "entry_date"])["net_pct"].mean().mean() / 100
check("a single lucky date (+90%) is shrunk and winsorised far below its raw value", eb["one"] < 0.03 and eb["one"] < 0.9 / 10)
check("a steady winner on many dates keeps most of its mean", eb["steady"] > 0.02 and eb["steady"] > eb["one"])
tr2 = tr.copy(); later = ar.outcomes(tr2, "2026-10-08")
check("outcomes need >= 3 later trades", (later["later_trades"] >= ar.MIN_LATER).all())

# --- capital_gate: UNKNOWN blocks, no live import, shadow only ---
conn = sqlite3.connect(":memory:")
conn.execute("CREATE TABLE paper_equity (run_id TEXT, date TEXT, cash_usd REAL, positions_usd REAL, equity_usd REAL, open_positions INT)")
for i in range(10):
    conn.execute("INSERT INTO paper_equity VALUES ('x', ?, 0, 0, ?, 0)", (f"2026-10-{i + 1:02d}", 100 + i))
st = cg.DEFAULTS
strong = pd.DataFrame({"entry_date": [f"2026-10-{d:02d}" for d in range(1, 11)] * 3, "net_pct": 1.5, "cost_pct": 0.15, "retro": False})
res, why = cg.assess_one(conn, {"run_id": "x"}, strong, {"fam": 0.01}, "fam", ("COMPLETE", {"fam"}), 0.01, True, st)
check("only 10 dates cannot satisfy C4 whatever the return", res["C4"] == cg.FAIL and res["C3"] == cg.PASS)
many = pd.DataFrame({"entry_date": [f"2026-{m:02d}-{d:02d}" for m in (9, 10, 11) for d in range(1, 11)] * 2, "net_pct": 1.5, "cost_pct": 0.15, "retro": False})
res2, _ = cg.assess_one(conn, {"run_id": "x"}, many, {"fam": 0.01}, "fam", ("COMPLETE", {"fam"}), 0.01, True, st)
check("30 dates, all criteria met -> every assessed criterion passes", all(res2[c] == cg.PASS for c in ("C1", "C2", "C3", "C4", "C6", "C8", "C9", "C11", "C12", "C13")))
res3, _ = cg.assess_one(conn, {"run_id": "x"}, many, {"fam": 0.01}, "fam", ("REGISTERED", set()), 0.01, True, st)
check("an unfinished prospective test is UNKNOWN, which blocks", res3["C13"] == cg.UNKNOWN)
res4, _ = cg.assess_one(conn, {"run_id": "x"}, many, {}, "fam", ("COMPLETE", {"fam"}), None, None, st)
check("missing family p, survivorship and reconciliation are UNKNOWN, not PASS", res4["C6"] == cg.UNKNOWN and res4["C9"] == cg.UNKNOWN and res4["C1"] == cg.UNKNOWN)
fragile = many.assign(net_pct=0.1)
res5, _ = cg.assess_one(conn, {"run_id": "x"}, fragile, {"fam": 0.01}, "fam", ("COMPLETE", {"fam"}), 0.01, True, st)
check("a +0.1% edge with 0.15% costs fails the 2x cost stress", res5["C8"] == cg.FAIL)
src = inspect.getsource(cg)
check("capital_gate imports no broker / execution / trader", not any(w in src for w in ("import execution", "import broker", "robinhood", "slot_trader", "risk_engine")))
check("slots.py does not read the gate", "capital_gate" not in open("slots.py").read() and "capital_gate" not in open("slot_trader.py").read() and "capital_gate" not in open("risk_engine.py").read())

# --- audit_pipeline.funnel: forward chain starts from every fund ---
c2 = sqlite3.connect(":memory:")
c2.execute("CREATE TABLE knowledge_entries (entry_id TEXT)")
c2.execute("INSERT INTO knowledge_entries VALUES ('a')")
s = pd.DataFrame({"strategy_key": list("abcd"), "version": 1, "family": ["f1", "f1", "f2", "f3"],
                  "sb_exclude": [.01, .01, -.01, np.nan], "sb_as_is": [.01, -.01, np.nan, np.nan], "sb_zero": [.01, np.nan, np.nan, np.nan],
                  "holdout": [.01, np.nan, np.nan, np.nan], "bt_net": [np.nan] * 4, "run_id": ["r1", "r2", None, "r4"],
                  "fw_n": [30, 5, np.nan, 40], "fw_mean": [1.0, 0.5, np.nan, 2.0], "fw_dates": [4, 2, np.nan, 25]})
fr = ap.funnel(c2, s)
d = {r["stage"][:25]: r["strategies"] for r in fr}
check("backtest chain is cumulative (3 backtested, 2 positive, 1 as_is, 1 zero, 1 unseen)", [r["strategies"] for r in fr[2:8]] == [3, 2, 1, 1, 1, 3] or [r["strategies"] for r in fr[2:7]] == [3, 2, 1, 1, 1])
check("forward chain restarts from all funds (3 funds, 2 with >=20 trades, 2 positive, 1 with 20+ dates)", [r["strategies"] for r in fr[7:]] == [3, 2, 2, 1])

# --- audit_portfolio helpers ---
sess = [f"2026-10-{d:02d}" for d in range(1, 11)]
h = apo.hold_sessions(pd.DataFrame({"entry_date": ["2026-10-01", "2026-10-02"], "exit_date": ["2026-10-04", "2026-10-02"]}), sess)
check("hold = sessions between entry and exit, minimum 1", list(h) == [3, 1])
c3 = sqlite3.connect(":memory:")
c3.execute("CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT, slot_id INT, symbol TEXT, action TEXT, quantity REAL, price REAL)")
for i, (sl, a, sym) in enumerate([(1, "OPEN", "AAA"), (2, "OPEN", "BBB"), (1, "CLOSE", "AAA"), (1, "OPEN", "CCC")], 1):
    c3.execute("INSERT INTO slot_trades VALUES (?,?,?,?,?,?,?,?)", (i, "2026-10-0%d" % i, "LIVE", sl, sym, a, 1, 10.0))
c3.execute("INSERT INTO slot_trades VALUES (9,'2026-10-09','SHADOW',3,'ZZZ','OPEN',1,10)")
lh = apo.live_holdings(c3)
check("live holdings = latest OPEN without a later CLOSE, LIVE rows only", sorted(lh["symbol"]) == ["BBB", "CCC"])

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
