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
stop_plans.from_genome = lambda g: [{"type": "atr", "atr_multiple": 2.0}]
stop_plans.validate = lambda plan: (True, [])
c = base.fixture()
rows = {r["strategy_key"]: r for r in slots.assess(c, {})}
check("negative score is not eligible", not rows["neg"]["eligible"]
      and "predicted to lose" in rows["neg"]["reasons"][0], rows["neg"]["reasons"])
check("positive score stays eligible", rows["pos"]["eligible"], rows["pos"]["reasons"])

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

sys.exit(1 if FAILED else 0)
