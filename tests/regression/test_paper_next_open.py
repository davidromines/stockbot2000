"""paper_trading at NEXT-OPEN fills (Stage AD item 3): a step decides on the close and fills at the next step's open.
The trade keeps its decision dates, so restate_paper prices the same fill (no second shift) and an overnight gap is
not mistaken for a corporate action; a stop gaps through; a slot freed by a sale is refilled at the same open; the
holding limit matches the simulator's (trigger at the close of entry + max_hold, fill at the next open); a split after
a next-open fill re-anchors on the fill's open; an order with no bar is cancelled after three sessions; and the 'close'
switch rolls the engine back without mis-anchoring positions it did not open."""
import runtime  # noqa: F401
import copy
import json
import sqlite3

import pandas as pd

import forward_stats as fs
import paper_trading as pt
import restate_paper
from universe import load_config

FAILS = []
def check(name, ok, detail=""):
    print(("  PASS  " if ok else "  FAIL  ") + name + ("" if ok else f"  ({detail})"))
    if not ok: FAILS.append(name)


cfg = copy.deepcopy(load_config())
cfg.setdefault("paper", {})["fills"] = "next_open"
SIZE = float(cfg["risk"]["position_size_usd"])
c = sqlite3.connect(":memory:")
c.row_factory = sqlite3.Row
c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, volume REAL)")
pt.init(c)
c.execute("INSERT INTO prices VALUES ('SPY','2026-09-30',100,100,100,100,1)")


def genome(tag, hold=60, cap=None):
    g = {"tag": tag, "entry": {"op": "gt"}, "exit": {"op": "lt"}, "risk": {"stop_atr_multiple": 2.0, "max_hold_days": hold}}
    if cap:
        g["risk"]["max_open_positions"] = cap
    return json.dumps(g)


F1 = pt.start(c, cfg, "f1", strategy=genome("f1", cap=2))
F2 = pt.start(c, cfg, "f2", strategy=genome("f2", hold=2))
F3 = pt.start(c, cfg, "f3", strategy=genome("f3"))
F4 = pt.start(c, cfg, "f4", strategy=genome("f4"))
CAP0 = c.execute("SELECT capital_usd FROM paper_runs WHERE run_id=?", (F1,)).fetchone()[0]
state = {"day": None, "px": {}, "cands": {}}


def put(day, t, o, cl):
    c.execute("DELETE FROM prices WHERE ticker=? AND date=?", (t, day))
    c.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,1)", (t, day, o, max(o, cl), min(o, cl), cl))


def market(conn, cfg_):
    return pd.DataFrame({"ticker": list(state["px"]), "date": state["day"], "close": list(state["px"].values()),
                         "dollar_volume_20": 5e7, "atr_14": 5.0, "score": 50.0})


def signals(conn, cfg_, g):
    rows = [{"ticker": t, "close": state["px"][t], "atr_14": 5.0} for t in state["cands"].get(g.get("tag"), [])]
    return pd.DataFrame(rows, columns=["ticker", "close", "atr_14"]), set()


pt._latest_scores = market
pt._genome_signals = signals


def day(d, bars, cands):
    for t, (o, cl) in bars.items():
        put(d, t, o, cl)
    put(d, "SPY", 100, 100)
    state.update(day=d, px={t: cl for t, (o, cl) in bars.items()}, cands=cands)
    pt.step(c, cfg)


def positions(run):
    return {r["ticker"]: dict(r) for r in c.execute("SELECT * FROM paper_positions WHERE run_id=?", (run,))}


def pending(run):
    return {(r["ticker"], r["side"]): dict(r) for r in c.execute("SELECT * FROM paper_pending WHERE run_id=?", (run,))}


def cash(run):
    return c.execute("SELECT cash_usd FROM paper_runs WHERE run_id=?", (run,)).fetchone()[0]


def equity(run, d):
    return dict(c.execute("SELECT * FROM paper_equity WHERE run_id=? AND date=?", (run, d)).fetchone())


# --- day 1: decide only --------------------------------------------------------------------------
day("2026-10-01", {t: (100, 100) for t in ("AAA", "BBB", "CCC", "HHH", "EEE", "NOBAR", "LEG")},
    {"f1": ["AAA", "BBB", "CCC"], "f2": ["HHH"], "f3": ["EEE"], "f4": ["NOBAR"]})
# the transition: a position the OLD engine opened (close fill, no fill_basis) that the new engine will close
c.execute("INSERT INTO paper_positions (run_id, ticker, entry_date, entry_price, shares, stop_price, days_held) "
          "VALUES (?,?,?,?,?,?,0)", (F4, "LEG", "2026-10-01", 100.0, SIZE / 100.0, 50.0))
c.execute("UPDATE paper_runs SET cash_usd = cash_usd - ? WHERE run_id=?", (SIZE, F4))
c.commit()
check("day 1: nothing is bought at the signal close", not positions(F1) and cash(F1) == CAP0)
check("...the cap (2) limits the orders: AAA and BBB wait for the next open", set(pending(F1)) == {("AAA", "BUY"), ("BBB", "BUY")},
      pending(F1))
check("...equity is the cash (no position, nothing debited)", equity(F1, "2026-10-01")["equity_usd"] == CAP0)

# --- day 2: fill at the open -----------------------------------------------------------------------
day("2026-10-02", {"AAA": (102, 104), "BBB": (98, 97), "CCC": (100, 100), "HHH": (100, 101), "EEE": (100, 100),
                   "LEG": (101, 100)}, {})
p = positions(F1)
check("day 2: AAA bought at the OPEN (102), stop 2 x ATR below the fill (92)", p["AAA"]["entry_price"] == 102
      and p["AAA"]["stop_price"] == 92, p.get("AAA"))
check("...the decision date is kept as entry_date; the fill session and basis are recorded",
      (p["AAA"]["entry_date"], p["AAA"]["fill_date"], p["AAA"]["fill_basis"]) == ("2026-10-01", "2026-10-02", "next_open"))
check("...cash is debited at the fill: two positions at the fixed size", abs(cash(F1) - (CAP0 - 2 * SIZE)) < 1e-9)
e2 = equity(F1, "2026-10-02")
check("...marked at the close on the fill basis", abs(e2["positions_usd"] - (SIZE * 104 / 102 + SIZE * 97 / 98)) < 1e-9, e2)
check("...the orders are gone once filled", not pending(F1))

# --- day 3 (10-05): AAA closes below its stop; CCC fires; HHH reaches its holding limit -------------------------
day("2026-10-05", {"AAA": (100, 91), "BBB": (97, 99), "CCC": (100, 100), "HHH": (101, 102), "EEE": (100, 100),
                   "LEG": (45, 40)}, {"f1": ["CCC"]})
check("day 3: the stop is decided on the close, not booked: AAA still held, a SELL waits",
      "AAA" in positions(F1) and pending(F1).get(("AAA", "SELL"), {}).get("reason") == "stop_loss", pending(F1))
check("...the slot the sale frees is refilled at the same open: CCC ordered (cap 2)", ("CCC", "BUY") in pending(F1))
check("...nothing booked yet", c.execute("SELECT COUNT(*) FROM paper_trades").fetchone()[0] == 0)
check("holding limit: decided at the close of entry + max_hold (2 sessions after 10-01)",
      pending(F2).get(("HHH", "SELL"), {}).get("reason") == "horizon_timeout", pending(F2))

# --- day 4 (10-06): AAA gaps down through the stop -------------------------------------------------------
day("2026-10-06", {"AAA": (85, 86), "BBB": (99, 99), "CCC": (101, 103), "HHH": (99, 99), "EEE": (100, 100),
                   "LEG": (37, 38)}, {})
lg = dict(c.execute("SELECT * FROM paper_trades WHERE run_id=? AND ticker='LEG'", (F4,)).fetchone())
check("transition: an old close-fill position exits at the next open (37), its entry basis kept",
      lg["exit_price"] == 37 and lg["entry_price"] == 100 and lg["fill_basis"] == "close"
      and lg["exit_fill_date"] == "2026-10-06", lg)
tr = dict(c.execute("SELECT * FROM paper_trades WHERE run_id=? AND ticker='AAA'", (F1,)).fetchone())
check("day 4: the exit fills at the open and gaps through the stop: 102 -> 85", tr["entry_price"] == 102
      and tr["exit_price"] == 85 and abs(tr["pnl_pct"] - (85 / 102 - 1) * 100) < 1e-9, tr)
check("...decision dates and fill sessions recorded", (tr["entry_date"], tr["exit_date"], tr["fill_date"], tr["exit_fill_date"],
      tr["fill_basis"], tr["exit_reason"]) == ("2026-10-01", "2026-10-05", "2026-10-02", "2026-10-06", "next_open", "stop_loss"), tr)
p = positions(F1)
check("...then CCC is bought at the same open (101)", "AAA" not in p and p["CCC"]["entry_price"] == 101
      and p["CCC"]["fill_date"] == "2026-10-06", p)
check("...cash: the sale's proceeds less costs, then the purchase", abs(cash(F1) - (CAP0 - 2 * SIZE + SIZE + tr["gross_pnl_usd"]
      - tr["costs_usd"] - SIZE)) < 1e-9)
h = dict(c.execute("SELECT * FROM paper_trades WHERE run_id=? AND ticker='HHH'", (F2,)).fetchone())
check("holding limit: filled at the next open (99), held 10-02 .. 10-06 like the simulator's max_hold + 1 bars",
      h["exit_price"] == 99 and h["exit_fill_date"] == "2026-10-06" and h["exit_reason"] == "horizon_timeout", h)

# --- the restated record is the same trade (no second shift), and the overnight gap is not a corporate action ------
r = restate_paper.restate(c)
rs = dict(c.execute("SELECT * FROM paper_trades_restated WHERE run_id=? AND ticker='AAA'", (F1,)).fetchone())
check("restate: the next open after each decision date is the engine's own fill", rs["entry_open_next"] == 102
      and rs["exit_open_next"] == 85 and abs(rs["gross_pct"] - tr["pnl_pct"]) < 1e-9, rs)
check("restate: a 2% overnight gap at entry is not flagged as a corporate action", rs["corporate_action"] == 0, rs)
rl = dict(c.execute("SELECT * FROM paper_trades_restated WHERE run_id=? AND ticker='LEG'", (F4,)).fetchone())
check("restate, mixed row: entry restated to the next open (101), the exit is already the open (37), no false flag "
      "for the 7.5% gap at the exit", rl["entry_open_next"] == 101 and rl["exit_open_next"] == 37
      and rl["corporate_action"] == 0, rl)
df = pd.DataFrame([{"entry_price": 102.0, "exit_price": 85.0, "close_entry": 100.0, "close_exit": 91.0,
                    "open_next_entry": 102.0, "open_next_exit": 85.0, "fill_basis": b} for b in ("next_open", "close")])
flag = fs.corporate_action_flag(df).tolist()
check("CA flag: a next-open row is compared with the fill's open; the same prices on the close basis are flagged",
      flag == [False, True], flag)
split = df.iloc[[0]].assign(open_next_entry=51.0)
check("CA flag: a real adjustment on a next-open row is still flagged", fs.corporate_action_flag(split).tolist() == [True])
mixed = df.iloc[[1]].assign(exit_basis="next_open", close_exit=91.0)
check("CA flag, per leg: a close entry with a next-open exit compares the exit with the open",
      fs.corporate_action_flag(mixed.assign(entry_price=100.0)).tolist() == [False])

# --- a split after a next-open fill re-anchors on the fill's OPEN ------------------------------------------------
# EEE: decided 10-01, bought at the 10-02 open (100, stop 90). A 2-for-1 split back-adjusts its history before 10-07.
for d_ in ("2026-10-01", "2026-10-02", "2026-10-05", "2026-10-06"):
    put(d_, "EEE", 50, 50)
day("2026-10-07", {"BBB": (99, 99), "CCC": (103, 103), "EEE": (51, 52)}, {})
check("split: EEE is not stopped (52 is above the adjusted stop of 45)", "EEE" in positions(F3)
      and ("EEE", "SELL") not in pending(F3), pending(F3))
check("split: marked on the adjusted series from the fill's open: $20 x 52/50", abs(equity(F3, "2026-10-07")["positions_usd"]
      - SIZE * 52 / 50) < 1e-9, equity(F3, "2026-10-07"))

# --- an order whose stock never shows a bar is cancelled after three sessions --------------------------------------
check("no bar: NOBAR's order (10-01) was cancelled once three sessions passed without an open",
      not pending(F4) and not positions(F4), (pending(F4), positions(F4)))

# --- rollback: paper.fills 'close' -------------------------------------------------------------------------
c.execute("INSERT INTO paper_pending (run_id, ticker, side, decided_on, reason, created_at) VALUES (?,?,?,?,?,?)",
          (F1, "ZZZ", "BUY", "2026-10-07", "stray", "x"))
c.commit()
cfg_close = copy.deepcopy(cfg)
cfg_close["paper"]["fills"] = "close"
put("2026-10-08", "BBB", 99, 99)
put("2026-10-08", "CCC", 103, 103)
put("2026-10-08", "SPY", 100, 100)
state.update(day="2026-10-08", px={"BBB": 99.0, "CCC": 103.0}, cands={})
pt.step(c, cfg_close)
check("rollback: the close path drops orders it would never fill", not pending(F1))
check("rollback: next-open positions keep their open anchor (BBB 98, CCC 101): no phantom mark",
      abs(equity(F1, "2026-10-08")["positions_usd"] - (SIZE * 99 / 98 + SIZE * 103 / 101)) < 1e-9, equity(F1, "2026-10-08"))
check("rollback: BBB not stopped by a mis-anchored stop", "BBB" in positions(F1))

print("\n  ALL PASS" if not FAILS else f"\n  FAILED: {FAILS}")
raise SystemExit(1 if FAILS else 0)
