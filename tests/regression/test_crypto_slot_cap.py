"""
Stage K cap: however high crypto scores, at most max_crypto_slots (1) slots hold crypto
strategies; stock strategies fill the rest. slots.assess is stubbed; in-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import slots

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def row(key, fam, score):
    return {"strategy_key": key, "version": 1, "family": fam, "score": score, "eligible": True,
            "net_usd": 0.0, "stop_plan": [{"type": "atr", "atr_multiple": 3.0}]}


def main():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT)")
    ranked = [row("crypto:a", "crypto_trend_a", 0.22), row("crypto:b", "crypto_trend_b", 0.20),
              row("crypto:c", "crypto_trend_c", 0.15), row("fx_1", "value_book", 0.03),
              row("fx_2", "profitability", 0.02), row("fx_3", "fcf_to_price", 0.015), row("fx_4", "sue", 0.01)]
    slots.assess = lambda conn, cfg: ranked
    p = slots.plan(c, {})
    keys = [r["strategy_key"] for _, r, _ in p["assign"]] if isinstance(p, dict) and "assign" in p else \
        [a[1]["strategy_key"] for a in p.get("assigns", [])]
    check("five slots filled", len(keys) == 5, keys)
    check("exactly one crypto strategy, the best one", [k for k in keys if k.startswith("crypto:")] == ["crypto:a"], keys)
    check("stocks fill the other four", sum(1 for k in keys if k.startswith("fx_")) == 4, keys)
    check("the cap is a setting", slots.settings({"slots": {"max_crypto_slots": 2}})["max_crypto_slots"] == 2)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
