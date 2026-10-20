"""paper_trading.step re-anchors open positions to the adjusted price series (Stage AD item 4). A 2-for-1 split after
entry back-adjusts the history: the old engine booked it as a -48% loss and fired the stop at once. Now the entry and
the stop move onto the adjusted series, the dollars paid are unchanged, and a later real drop still stops it out."""
import runtime  # noqa: F401
import copy
import json
import sqlite3

import pandas as pd

import paper_trading as pt
from universe import load_config

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)

cfg = copy.deepcopy(load_config())
c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
pt.init(c)
c.execute("INSERT INTO prices VALUES ('SPY','2026-09-30',100,100,100,100,1)")
G = {"entry": {"op": "gt"}, "exit": {"op": "lt"}, "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 60}}
run = pt.start(c, cfg, "split_fund", strategy=json.dumps(G))
run_b = pt.start(c, cfg, "plain_fund", strategy=json.dumps(G))
state = {"day": "2026-10-01", "px": {"AAA": 100.0, "BBB": 100.0}, "cands": ["AAA", "BBB"]}


def put(day, t, close):
    c.execute("DELETE FROM prices WHERE ticker=? AND date=?", (t, day))
    c.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,1)", (t, day, close, close, close, close))


def market(conn, cfg_):
    return pd.DataFrame({"ticker": list(state["px"]), "date": state["day"], "close": list(state["px"].values()),
                         "dollar_volume_20": 5e7, "atr_14": 5.0, "score": 50.0})


def signals(conn, cfg_, g):
    rows = [{"ticker": t, "close": state["px"][t], "atr_14": 5.0} for t in state["cands"]]
    return pd.DataFrame(rows), set()


pt._latest_scores = market
pt._genome_signals = signals
for t in ("AAA", "BBB", "SPY"):
    put("2026-10-01", t, 100.0)
pt.step(c, cfg)
pos = {r["ticker"]: dict(r) for r in c.execute("SELECT * FROM paper_positions WHERE run_id=?", (run,))}
check("day 1: both names bought at the close, stop 2 x ATR below", pos["AAA"]["entry_price"] == 100 and pos["AAA"]["stop_price"] == 90)

# a 2-for-1 split in AAA: the history is back-adjusted (day-1 close becomes 50); the day-2 close is 52
put("2026-10-01", "AAA", 50.0)
for t, px in (("AAA", 52.0), ("BBB", 105.0), ("SPY", 100.0)):
    put("2026-10-02", t, px)
state.update(day="2026-10-02", px={"AAA": 52.0, "BBB": 105.0}, cands=[])
pt.step(c, cfg)
held = {r["ticker"] for r in c.execute("SELECT ticker FROM paper_positions WHERE run_id=?", (run,))}
check("the split is not a stop-out (52 is above the adjusted stop of 45)", "AAA" in held, held)
eq = c.execute("SELECT positions_usd FROM paper_equity WHERE run_id=? AND date='2026-10-02'", (run,)).fetchone()[0]
check("marked on the adjusted series: $20 x 52/50 + $20 x 105/100 = $41.80", abs(eq - 41.80) < 1e-9, eq)
check("no trade was booked for the split", c.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 0)

# a real drop below the adjusted stop
for t, px in (("AAA", 44.0), ("BBB", 105.0), ("SPY", 100.0)):
    put("2026-10-05", t, px)
state.update(day="2026-10-05", px={"AAA": 44.0, "BBB": 105.0})
pt.step(c, cfg)
tr = dict(c.execute("SELECT * FROM paper_trades WHERE run_id=? AND ticker='AAA'", (run,)).fetchone())
check("a real drop below the adjusted stop still exits", tr["exit_reason"] == "stop_loss", tr)
check("the trade is recorded on one series: entry 50, exit 44, -12%", tr["entry_price"] == 50 and tr["exit_price"] == 44
      and abs(tr["pnl_pct"] - (-12.0)) < 1e-9, tr)
check("dollars: $20 paid, gross -$2.40, shares on the adjusted series (0.4)",
      abs(tr["gross_pnl_usd"] - (-2.40)) < 1e-9 and abs(tr["shares"] - 0.4) < 1e-9, tr)
cash = c.execute("SELECT cash_usd FROM paper_runs WHERE run_id=?", (run,)).fetchone()[0]
start = c.execute("SELECT capital_usd FROM paper_runs WHERE run_id=?", (run,)).fetchone()[0]
check("cash gets back what the position was worth, less costs", abs(cash - (start - 40 + 17.60 - tr["costs_usd"])) < 1e-9,
      (cash, start, tr["costs_usd"]))
check("an unadjusted name is unaffected (BBB still held, marked 105/100)",
      c.execute("SELECT COUNT(*) FROM paper_positions WHERE run_id=? AND ticker='BBB'", (run,)).fetchone()[0] == 1)
check("a data defect (factor outside the range) leaves the recorded price", pt.adjusted_entry(c, "BBB", "2026-10-01", 1e6) == 1e6)

# the shared helpers the rotation and conviction steps now use
put("2026-10-01", "CCC", 50.0)                 # back-adjusted from a recorded 100 (2-for-1)
p = {"ticker": "CCC", "entry_date": "2026-10-01", "entry_price": 100.0, "shares": 0.2}
e, sh, g, notional = pt._exit_values(c, p, 55.0)
check("exit helper: entry 50 on the adjusted series, 0.4 shares, +$2.00 on $20", (e, round(sh, 9), round(g, 9), notional)
      == (50.0, 0.4, 2.0, 20.0), (e, sh, g, notional))
check("mark helper: $20 x 55/50 = $22; at cost without a price", abs(pt._mark_value(c, p, 55.0) - 22.0) < 1e-9
      and pt._mark_value(c, p, None) == 20.0)
check("a position bought today (no entry date yet) marks on its own price",
      pt._mark_value(c, {"ticker": "CCC", "entry_price": 50.0, "shares": 0.4}, 55.0) == 22.0)

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
