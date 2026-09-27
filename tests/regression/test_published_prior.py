"""
Stage L4 (ranking.published_factor): a family's post-publication t shrinks its backtest
(t/3, capped 1, floored 0); no evidence leaves it whole; the switch is off by default.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import ranking

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE published_evidence (family TEXT, signal TEXT, weighting TEXT, period TEXT, "
              "tstat_excess REAL)")
    c.executemany("INSERT INTO published_evidence VALUES (?,?,?,?,?)",
                  [("value_book", "be_me", "ew", "post", 3.2), ("profitability", "gp_at", "ew", "post", 0.46),
                   ("liquidity_premium", "ami", "ew", "post", -0.3), ("value_book", "be_me", "ew", "pre", 9.0)])
    check("t >= 3 keeps the backtest whole", ranking.published_factor(c, "value_book") == (1.0, 3.2))
    f, t = ranking.published_factor(c, "profitability")
    check("weak post-publication evidence shrinks it", abs(f - 0.46 / 3) < 1e-9 and t == 0.46, (f, t))
    check("a factor gone after publication zeroes it", ranking.published_factor(c, "liquidity_premium")[0] == 0.0)
    check("no published evidence leaves it whole", ranking.published_factor(c, "rsi_reversion") == (1.0, None))
    check("off by default", ranking.DEFAULTS["published_prior"] is False)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
