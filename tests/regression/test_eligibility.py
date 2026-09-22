"""
REGRESSION: the roster is the top five ELIGIBLE, never the top five by return.

Six of the sixteen paper funds are the same entry rule at different stop widths.
Ranked on return alone the roster fills with six copies of one bet, sized as
though it were six — the concentration of a single position wearing the
appearance of diversification.

Two properties matter most and neither can be exercised on the real arena yet,
because every pair shares too few equity marks. So this builds synthetic funds
long enough to test them:

1. **A correlated duplicate is vetoed even when it scores well.** Exclusion for
   being a duplicate is the rule working, not failing.
2. **An UNKNOWN correlation blocks.** A pair sharing two marks correlates at
   exactly +/-1 by construction; treating thin data as "probably independent" is
   how five copies of one bet reach a roster that believes it holds five.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_eligibility.py
"""
import runtime  # noqa: F401
import datetime as dt
import inspect
import sqlite3
import tempfile

import numpy as np

import eligibility as el
import league as lg
import scoreboard as sb

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


CFG = {"league": {"min_rank_marks": 60, "min_forward_trades": 5,
                  "max_drawdown": 0.25, "max_correlation": 0.7,
                  "min_corr_overlap": 30, "live_roster_size": 5},
       "risk": {"position_size_usd": 20}}

conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE paper_equity (run_id TEXT, date TEXT, equity_usd REAL);
CREATE TABLE pair_fund_equity (name TEXT, date TEXT, equity_usd REAL,
    held TEXT, switches INTEGER);
CREATE TABLE paper_trades (run_id TEXT, net_pnl_usd REAL, costs_usd REAL,
    exit_date TEXT, pnl_pct REAL);
""")
lg.init(conn); sb.init(conn)
d0 = dt.date(2026, 1, 5)
rng = np.random.default_rng(7)

# Three funds: A and its near-duplicate A2, plus an independent B.
base = rng.normal(0.004, 0.01, 90)
noise = rng.normal(0.0, 0.0008, 90)
indep = rng.normal(0.0035, 0.01, 90)
SERIES = {"A": base, "A2": base + noise, "B": indep}

for run, rets in SERIES.items():
    eq = 100.0
    for i, r in enumerate(rets):
        eq *= (1 + r)
        conn.execute("INSERT INTO paper_equity VALUES (?,?,?)",
                     (run, (d0 + dt.timedelta(days=i)).isoformat(), eq))
    for t in range(10):
        conn.execute("INSERT INTO paper_trades VALUES (?,?,?,?,?)",
                     (run, 1.0, 0.1, "2026-02-01", 1.0))
    key = f"paper:{run}"
    lg.register(conn, key, f"Fund {run}", {"family": "t", "entry_rule": run},
                source_kind="paper_runs", source_ref=run)
    lg.transition(conn, key, lg.PAPER, "test")
conn.commit()

# --- correlation measurement ------------------------------------------------
rows, m = el.matrix(conn, CFG)
c_dup, n_dup = el._pair(m, "paper:A", "paper:A2")
c_ind, _ = el._pair(m, "paper:A", "paper:B")
check("a near-duplicate pair correlates near 1", c_dup is not None and c_dup > 0.9,
      str(c_dup))
check("an independent pair does not", c_ind is not None and abs(c_ind) < 0.5,
      str(c_ind))
check("the overlap count is reported", n_dup >= 30, str(n_dup))

thin_a = {"2026-01-05": 0.01, "2026-01-06": -0.02}
thin_b = {"2026-01-05": 0.02, "2026-01-06": -0.04}
val, n = el.correlation(thin_a, thin_b, 30)
check("a 2-mark overlap is UNKNOWN, not +1", val is el.UNKNOWN,
      "two points correlate at exactly +/-1 by construction")
check("the thin pair still reports its overlap size", n == 2)
check("a flat series gives UNKNOWN rather than a divide-by-zero",
      el.correlation({f"d{i}": 0.0 for i in range(40)},
                     {f"d{i}": 0.01 for i in range(40)}, 30) [0] is el.UNKNOWN)

# --- the veto ---------------------------------------------------------------
res = el.propose(conn, CFG)
names = [r["name"] for r in res["roster"]]
check("eligible strategies reach the roster", len(names) >= 1, str(names))
check("the duplicate is NOT on the roster alongside its twin",
      not ("Fund A" in names and "Fund A2" in names),
      f"{names} — two copies of one bet")
check("the duplicate is recorded as VETOED, not silently dropped",
      any(r["name"] in ("Fund A", "Fund A2") for r in res["vetoed"]),
      "a strategy excluded for being a duplicate must say so")
if res["vetoed"]:
    check("the veto names the strategy it duplicates",
          "correlated" in res["vetoed"][0]["veto"].lower(),
          res["vetoed"][0]["veto"])
check("the independent strategy is not vetoed",
      "Fund B" in names, str(names))

# --- unknown correlation must BLOCK ----------------------------------------
strict = {**CFG, "league": {**CFG["league"], "min_corr_overlap": 999}}
res2 = el.propose(conn, strict)
check("when every correlation is UNKNOWN, at most ONE strategy is admitted",
      len(res2["roster"]) <= 1,
      f"{[r['name'] for r in res2['roster']]} — unknown must block, not permit")
check("the block explains that unknown is treated as correlated",
      any("UNKNOWN" in r["veto"] for r in res2["vetoed"]),
      str([r["veto"] for r in res2["vetoed"]][:1]))

# --- eligibility reasons accumulate ----------------------------------------
conn.execute("INSERT INTO paper_equity VALUES ('short','2026-01-05',100)")
conn.execute("INSERT INTO paper_equity VALUES ('short','2026-01-06',90)")
conn.commit()
lg.register(conn, "paper:short", "Fund Short", {"family": "t", "entry_rule": "s"},
            source_kind="paper_runs", source_ref="short")
lg.transition(conn, "paper:short", lg.PAPER, "test")
a = {x["strategy_key"]: x for x in el.assess(conn, CFG)}["paper:short"]
check("a failing strategy reports EVERY reason, not just the first",
      len(a["reasons"]) >= 3, str(a["reasons"]))
check("a losing strategy is ineligible",
      not a["eligible"] and any("not positive" in r for r in a["reasons"]))

# --- the module promotes nothing -------------------------------------------
src = inspect.getsource(el)
check("eligibility never transitions a strategy",
      "transition(" not in src, "item 18: no promotion to live yet")
check("eligibility cannot reach the broker",
      "import execution" not in src and "import broker" not in src)
states_after = {lg.state(conn, f"paper:{r}") for r in ("A", "A2", "B")}
check("no strategy changed state during assessment", states_after == {lg.PAPER})

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
