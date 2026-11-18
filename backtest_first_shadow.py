"""
SHADOW: which five strategies would hold the slots if backtest evidence led and paper results only checked?

Eligible: passes the ranking gate, positive in the worst-case survivorship mode (zero), positive on the unseen
2023-today window where one exists, and has a backtest at all (Lab-search funds have none).  Ranked by the prior the
ranking already uses (unseen-window result, else the survivorship backtest), per 20 sessions held.  One per family,
0.7 correlation veto.  Reads only; changes nothing.

    ./run_bounded.sh ./venv/bin/python backtest_first_shadow.py
"""
import runtime  # noqa: F401
import sqlite3
import numpy as np
import pandas as pd
import ranking
import strategy_diversity as sd
import slots
from universe import load_config

cfg = load_config()
conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
conn.row_factory = sqlite3.Row
rows = ranking.rank(conn, cfg)
s = ranking.settings(cfg)
cur = {(h["strategy_key"], h["version"]): sl for sl, h in slots.current(conn, cfg).items() if h}
out = []
for r in rows:
    if r["from_search"] or r["backtest"] is None or not r["passes_gate"]:
        continue
    prior = r["holdout"] if r["holdout"] is not None else r["backtest"]
    if r["worst_case"] is None or r["worst_case"] <= 0 or prior is None or prior <= 0:
        continue
    r["prior20"] = ranking._per_hold(prior, r["hold_days"], s)
    out.append(r)
out.sort(key=lambda r: -r["prior20"])
chosen = []
for r in out:
    if any(c["family"] == r["family"] for c in chosen):
        continue
    if any((sd.lookup(conn, (r["strategy_key"], r["version"]), (c["strategy_key"], c["version"])) or 0) > 0.7 for c in chosen):
        continue
    chosen.append(r)
    if len(chosen) == 5:
        break
def pct(x): return "n/a" if x is None else f"{x*100:+.2f}"
L = ["# Shadow: backtest-first slot selection (nothing changed)", "",
     f"{len(out)} strategies are eligible (gate passed, worst case positive, unseen window positive where tested, a backtest exists).", "",
     "## Would hold the slots", "", "| # | strategy | family | backtest % | unseen 2023+ % | worst case % | per 20 sessions % | forward trades | forward (ranking basis) % |", "|---:|---|---|---:|---:|---:|---:|---:|---:|"]
for i, r in enumerate(chosen, 1):
    L.append(f"| {i} | {r['name'][:46]} | {r['family']} | {pct(r['backtest'])} | {pct(r['holdout'])} | {pct(r['worst_case'])} | {pct(r['prior20'])} | {r['forward_trades']} | {pct(r['forward'])} |")
L += ["", "## Holding the slots now", "", "| slot | strategy | family | backtest % | unseen % | worst case % | forward trades |", "|---:|---|---|---:|---:|---:|---:|"]
byk = {(r["strategy_key"], r["version"]): r for r in rows}
for (k, v), sl in sorted(cur.items(), key=lambda x: x[1]):
    r = byk.get((k, v))
    if r:
        L.append(f"| {sl} | {r['name'][:46]} | {r['family']} | {pct(r['backtest'])} | {pct(r['holdout'])} | {pct(r['worst_case'])} | {r['forward_trades']} |")
open("reports/backtest_first_shadow.md", "w").write("\n".join(L) + "\n")
print("\n".join(L))
