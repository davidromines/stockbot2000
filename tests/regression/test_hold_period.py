"""
hold_period.py + ranking normalisation: a strategy's average hold comes from its own paper
trades first, then a measured simulation, then its rule, then a default; the ranking
scores per 20 sessions held, so a month-long trade no longer outranks a week-long one on
the unit alone. In-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import hold_period as hp
import ranking

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE factory_paper_link (strategy_key TEXT, version INT, run_id TEXT, linked_at TEXT)")
    c.execute("CREATE TABLE paper_trades (run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT)")
    g = {"entry": {"col": "close"}, "risk": {"max_hold_days": 40}}
    check("no evidence: the rule's maximum hold", hp.estimate(c, "fx_a", 1, g) == (40.0, "rule"))
    check("no rule: the default", hp.estimate(c, "pair:x", 1, None) == (hp.DEFAULT_DAYS, "default"))
    check("a rotation rule's 252-day cap is not used as its hold",
          hp.estimate(c, "fx_r", 1, {"rotation": {}, "risk": {"max_hold_days": 252}})[1] == "default")
    hp.record(c, "fx_a", 1, 12.5, "factory backtest")
    check("a measured hold beats the rule", hp.estimate(c, "fx_a", 1, g) == (12.5, "measured (factory backtest)"))
    hp.record(c, "fx_a", 1, 0, "bad")
    check("a zero is not a measurement", hp.estimate(c, "fx_a", 1, g)[0] == 12.5)
    c.execute("INSERT INTO factory_paper_link VALUES ('fx_a', 1, 'run1', 't')")
    c.executemany("INSERT INTO paper_trades VALUES ('run1','T','2026-01-05','2026-01-12')", [()] * 12)
    check("twelve paper trades are too few to set the hold", hp.estimate(c, "fx_a", 1, g)[1].startswith("measured"))
    c.executemany("INSERT INTO paper_trades VALUES ('run1','T','2026-01-05','2026-01-12')", [()] * 20)
    h, src = hp.estimate(c, "fx_a", 1, g)
    check("thirty closed paper trades beat the measurement", src == "paper" and abs(h - 7 * 252 / 365.25) < 1e-9, (h, src))
    s = ranking.settings({})
    check("per 20 sessions: +6% over a 60-session hold is +2%", abs(ranking._per_hold(0.06, 60, s) - 0.02) < 1e-12)
    check("a 20-session hold is unchanged", ranking._per_hold(0.01, 20, s) == 0.01)
    check("a 2-session hold is scaled as 5, not x10", abs(ranking._per_hold(0.01, 2, s) - 0.04) < 1e-12)
    check("disabled -> per trade", ranking._per_hold(0.06, 60, {"normalize_hold_days": None}) == 0.06)
    check("missing score stays missing", ranking._per_hold(None, 60, s) is None)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
