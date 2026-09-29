"""
Owner, 2026-09-28. (1) A strategy predicted to lose (score < slots.min_score) is not
eligible, so a holder is released and a challenger never assigned. (4) A slot whose own
strategy has no buy signal is filled by the reassessment's first stand-in that has one; the
position belongs to the stand-in (its key on the OPEN, its exit rule), and a stand-in
already holding a position is not used twice. SIMULATION through the real engine.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "tests", "regression"))

import paper_trading as pt
import quotes as qt
import ranking
import slot_trader as st
import slots
import stop_plans
import test_slot_trader as base

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


G = {k: {**base.GENOME, "tag": k} for k in ("hold", "sa", "sb")}
slots.genome_for = lambda conn, k, v: G.get(k, base.GENOME)
SIG = {"hold": (["AAA"], set()), "sa": ([], set()), "sb": (["BBB"], set())}
pt._genome_signals = lambda conn, cfg, g: (pd.DataFrame({"ticker": SIG[g["tag"]][0]}), SIG[g["tag"]][1])

# (1) predicted-to-lose gate
ranking.rank = lambda conn, cfg: [
    {"strategy_key": "neg", "version": 1, "passes_gate": True, "gate": "", "score": -0.0069, "family": "f"},
    {"strategy_key": "pos", "version": 1, "passes_gate": True, "gate": "", "score": 0.0177, "family": "g"}]
_fg, _va = stop_plans.from_genome, stop_plans.validate
stop_plans.from_genome = lambda g: [{"type": "atr", "atr_multiple": 2.0}]
stop_plans.validate = lambda plan: (True, [])
c = base.fixture()
rows = {r["strategy_key"]: r for r in slots.assess(c, {})}
check("negative score is not eligible", not rows["neg"]["eligible"]
      and "predicted to lose" in rows["neg"]["reasons"][0], rows["neg"]["reasons"])
check("positive score stays eligible", rows["pos"]["eligible"], rows["pos"]["reasons"])
stop_plans.from_genome, stop_plans.validate = _fg, _va

# (4) stand-in
c = base.fixture()
base.assign(c, 1, "hold")
base.assign(c, 2, "sa")          # slot 2's own strategy has no signal
c.execute("INSERT INTO slot_reviews (at, mode, summary) VALUES ('2026-09-23T00:00:00','SIMULATION',?)",
          (json.dumps({"standins": [["sa", 1], ["sb", 1]]}),))
c.commit()
r = st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
pos = st.open_positions(c, "SIMULATION")
check("slot 1 buys on its own strategy", pos.get(1, {}).get("strategy_key") == "hold", pos.get(1))
check("idle slot 2 filled by the first stand-in with a signal (sb, not sa)",
      pos.get(2, {}).get("strategy_key") == "sb" and pos[2]["symbol"] == "BBB", pos.get(2))
check("the buy names the stand-in", any("stand-in for sa" in (x.get("reason") or "") for x in r), r)
check("holder assignment unchanged", slots.current(c, {})[2]["strategy_key"] == "sa")

# the stop monitor keeps a stand-in's position (09-28: it sold two as "reassigned")
r = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
check("monitor keeps the stand-in position", 2 in st.open_positions(c, "SIMULATION")
      and not [x for x in r if x["action"] == "CLOSE"], r)
# but a genuinely released slot still closes it
base_c = c

# the stand-in's position exits on the stand-in's rule, not the holder's
SIG["sb"] = ([], {"BBB"})
r = st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
check("stand-in position closes on the stand-in's exit rule",
      any(x["action"] == "CLOSE" and x["symbol"] == "BBB" for x in r) and 2 not in st.open_positions(c, "SIMULATION"), r)

# a stand-in already holding a position is not used for a second slot
c = base.fixture()
base.assign(c, 1, "sa")
base.assign(c, 2, "sa")
SIG["sb"] = (["BBB", "AAA"], set())
c.execute("INSERT INTO slot_reviews (at, mode, summary) VALUES ('2026-09-23T00:00:00','SIMULATION',?)",
          (json.dumps({"standins": [["sb", 1]]}),))
c.commit()
st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
pos = st.open_positions(c, "SIMULATION")
check("one stand-in fills at most one slot", len(pos) == 1, pos)
held_slot = next(iter(pos))
c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) "
          "VALUES ('2026-09-23T02:00:00', ?, 'RELEASE', 'sa', 1, NULL, 'SIMULATION', 't')", (held_slot,))
c.commit()
r = st.monitor(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
check("released slot closes its stand-in position", held_slot not in st.open_positions(c, "SIMULATION"), r)

# a stand-in whose only candidate was already bought today is skipped for the next (09-28: JBL)
G["sc"] = {**base.GENOME, "tag": "sc"}
SIG["sa"], SIG["sb"], SIG["sc"] = ([], set()), (["BBB"], set()), (["AAA"], set())
slots.genome_for = lambda conn, k, v: G.get(k, base.GENOME)
c = base.fixture()
base.assign(c, 1, "sa")
c.execute("INSERT INTO slot_reviews (at, mode, summary) VALUES ('2026-09-23T00:00:00','SIMULATION',?)",
          (json.dumps({"standins": [["sb", 1], ["sc", 1]]}),))
c.execute("INSERT INTO orders (client_order_id, signal_id, created_at, session, symbol, side, asset_type, state, mode) "
          "VALUES ('x','x','2026-01-01T00:00:00', ?, 'BBB', 'BUY', 'equity', 'FILLED', 'SIMULATION')", (st._session(c),))
c.commit()
st.trade(c, {}, "SIMULATION", qt.FixedQuotes({"AAA": 50.0, "BBB": 60.0}, conn=c))
pos = st.open_positions(c, "SIMULATION")
check("stand-in with only an already-bought name is skipped for the next",
      pos.get(1, {}).get("strategy_key") == "sc" and pos[1]["symbol"] == "AAA", pos)

# idle rule: a strategy whose entry rule fired on 0 recent sessions is not used (09-28)
import signal_activity as sa
_act, _rf = sa.activity, pt._recent_frame
pt._recent_frame = lambda conn, cfg: pd.DataFrame({"ticker": [], "date": []})
sa.activity = lambda conn, cfg, k, v, df=None, sessions=60: {
    "measurable": True, "active_sessions": 0 if k == "dec" else 12, "last_signal": None}
idle = slots._idle_check(None, {}, {"min_active_sessions": 1, "activity_sessions": 60})
check("idle strategy flagged", "0 of the last 60" in idle({"strategy_key": "dec", "version": 1}))
check("active strategy not flagged", idle({"strategy_key": "live", "version": 1}) == "")
off = slots._idle_check(None, {}, {"min_active_sessions": 0})
check("rule off with min_active_sessions 0", off({"strategy_key": "dec", "version": 1}) == "")
sa.activity = lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom"))
failing = slots._idle_check(None, {}, {"min_active_sessions": 1, "activity_sessions": 60})
check("measurement error fails open", failing({"strategy_key": "x", "version": 1}) == "")
sa.activity, pt._recent_frame = _act, _rf

# stand-in list: one per family, none from a family already in a slot
slots.genome_for = lambda conn, k, v: base.GENOME
c = base.fixture()
base.assign(c, 1, "h1")
rows = [{"strategy_key": k, "version": 1, "eligible": True, "reasons": [], "score": sc, "family": f}
        for k, sc, f in (("h1", 0.03, "es"), ("es2", 0.025, "es"), ("m1", 0.02, "mom"),
                         ("m2", 0.019, "mom"), ("v1", 0.018, "val"))]
slots.assess = lambda conn, cfg: rows
p = slots.plan(c, {"slots": {"count": 1}})
check("stand-ins: one per family, holder's family skipped",
      [k for k, _ in p["standins"]] == ["m1", "v1"], p["standins"])

sys.exit(1 if FAILED else 0)
