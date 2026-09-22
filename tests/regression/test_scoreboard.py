"""
REGRESSION: the scoreboard refuses to rank a sample that cannot support a rank.

The 21 migrated funds hold a median of 7 equity marks. A Sharpe from 7
observations is noise with a decimal point, and a leaderboard that prints one
invites precisely the decision the league exists to prevent — promoting whoever
got lucky in their first fortnight.

Also pinned: the scoring formula is pluggable and every snapshot records which
formula produced it, because Phase 7 asks for the architecture to TEST formulas
rather than for the final weighting. Changing the weighting must write new
history, never rewrite old.

Run:  PYTHONPATH=. venv/bin/python tests/regression/test_scoreboard.py
"""
import runtime  # noqa: F401
import inspect
import sqlite3
import tempfile

import numpy as np

import league as lg
import scoreboard as sb

fails = []


def check(name, cond, detail=""):
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail and not cond else ""))
    if not cond:
        fails.append(name)


conn = sqlite3.connect(tempfile.mktemp(suffix=".db"))
conn.row_factory = sqlite3.Row
conn.executescript("""
CREATE TABLE paper_equity (run_id TEXT, date TEXT, equity_usd REAL);
CREATE TABLE pair_fund_equity (name TEXT, date TEXT, equity_usd REAL,
    held TEXT, switches INTEGER);
CREATE TABLE paper_trades (run_id TEXT, net_pnl_usd REAL, costs_usd REAL);
""")
lg.init(conn); sb.init(conn)

CFG = {"league": {"min_rank_marks": 60}}
FLOOR = sb.min_marks(CFG)
check("the ranking floor comes from config", FLOOR == 60)

# A thin fund (7 marks, like the real ones) and a long one (80 marks).
import datetime as dt
d0 = dt.date(2026, 1, 5)


def add_paper(run_id, n, drift):
    eq = 100.0
    for i in range(n):
        eq *= (1 + drift)
        conn.execute("INSERT INTO paper_equity VALUES (?,?,?)",
                     (run_id, (d0 + dt.timedelta(days=i)).isoformat(), eq))


add_paper("thin", 7, 0.01)
add_paper("long", 80, 0.001)
add_paper("flat", 80, 0.0)
conn.execute("INSERT INTO pair_fund_equity VALUES ('pair','2026-01-05',100,'SPY',0)")
conn.execute("INSERT INTO pair_fund_equity VALUES ('pair','2026-01-06',101,'SPY',2)")
conn.commit()

for key, ref, kind in [("paper:thin", "thin", "paper_runs"),
                       ("paper:long", "long", "paper_runs"),
                       ("paper:flat", "flat", "paper_runs"),
                       ("pair:pair", "pair", "pair_funds")]:
    lg.register(conn, key, key, {"family": "t", "entry_rule": ref},
                source_kind=kind, source_ref=ref)
    lg.transition(conn, key, lg.PAPER, "test")

# --- refusal ----------------------------------------------------------------
m_thin = sb.metrics(conn, "paper:thin", "paper_runs", "thin")
ok, why = sb.rankable(m_thin, FLOOR)
check("a 7-mark strategy is NOT rankable", not ok, why)
check("the refusal says how many more marks are needed", "60" in why and "7" in why, why)

m_long = sb.metrics(conn, "paper:long", "paper_runs", "long")
check("an 80-mark strategy IS rankable", sb.rankable(m_long, FLOOR)[0])

m_flat = sb.metrics(conn, "paper:flat", "paper_runs", "flat")
check("a strategy with a flat curve is NOT rankable",
      not sb.rankable(m_flat, FLOOR)[0],
      "zero volatility makes every ratio meaningless or infinite")

rows = sb.build(conn, CFG, "risk_adjusted")
ranked = [r for r in rows if r["rankable"]]
check("only the sufficient sample is ranked",
      [r["strategy_key"] for r in ranked] == ["paper:long"],
      str([r["strategy_key"] for r in ranked]))
check("unranked strategies still appear with their record",
      any(r["strategy_key"] == "paper:thin" and r["metrics"]["n_marks"] == 7
          for r in rows),
      "a thin strategy keeps accruing a record, it just gets no number")
check("an unranked strategy has NO score", all(
      r["score"] is None for r in rows if not r["rankable"]),
      "a score on a thin sample is the whole failure mode")

# --- metrics are right ------------------------------------------------------
# 80 marks span 79 steps: the generator compounds once before the first mark.
check("cumulative return is measured against the FIRST mark",
      abs(m_long["cumulative_return"] - (1.001 ** 79 - 1)) < 1e-6,
      f"{m_long['cumulative_return']}")
check("a steadily rising curve has no drawdown",
      m_long["max_drawdown"] == 0.0)

eq = np.array([100.0, 120.0, 60.0, 90.0])
check("drawdown is measured peak-to-trough, not first-to-last",
      abs(sb._drawdown(eq) - 0.5) < 1e-9, str(sb._drawdown(eq)))

# --- pair funds must not be scored as having lost trades they never made ----
m_pair = sb.metrics(conn, "pair:pair", "pair_funds", "pair")
check("a pair fund's win rate is ABSENT, not zero", m_pair["win_rate"] is None,
      "zero would rank it as having lost every trade it never made")
check("a pair fund reports switches as its trade count", m_pair["n_trades"] == 2)

# --- formulas are pluggable and recorded ------------------------------------
check("more than one formula is registered", len(sb.FORMULAS) >= 3)
check("a control formula exists", "sharpe_only" in sb.FORMULAS,
      "a considered formula that cannot beat raw Sharpe adds nothing")
try:
    sb.build(conn, CFG, "not_a_formula")
    check("an unknown formula is refused", False)
except SystemExit as e:
    check("an unknown formula is refused", "unknown formula" in str(e))

scores = {name: sb.build(conn, CFG, name)[0] for name in sb.FORMULAS}
check("switching formula changes the score",
      len({r["score"] for r in scores.values() if r["score"] is not None}) > 1
      or all(r["score"] is None for r in scores.values()))

n = sb.snapshot(conn, CFG, "risk_adjusted")
n2 = sb.snapshot(conn, CFG, "sharpe_only")
check("each snapshot records every strategy", n == n2 == len(rows))
formulas = {r[0] for r in conn.execute(
    "SELECT DISTINCT formula FROM scoreboard_snapshots")}
check("every snapshot records WHICH formula produced it",
      formulas == {"risk_adjusted", "sharpe_only"}, str(formulas))
total = conn.execute("SELECT COUNT(*) FROM scoreboard_snapshots").fetchone()[0]
check("snapshots accumulate rather than replace", total == n + n2,
      "a rank is never revised; a new formula writes new history")

src = inspect.getsource(sb)
check("the scoreboard never UPDATEs or DELETEs a snapshot",
      "UPDATE " not in src.upper() and "DELETE FROM" not in src.upper())
import re
queried = set(re.findall(r"FROM\s+([a-z_]+)", src))
forward_only = {"paper_equity", "pair_fund_equity", "paper_trades",
                "scoreboard_snapshots"}
check("the scoreboard queries ONLY forward tables",
      queried <= forward_only,
      f"also reads {sorted(queried - forward_only)} — a backtest figure on a "
      f"forward scoreboard would be read as forward")

print()
print(f"  RESULT: {'PASS' if not fails else 'FAIL — ' + ', '.join(fails)}")
raise SystemExit(0 if not fails else 1)
