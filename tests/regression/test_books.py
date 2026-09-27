"""books.py: the capital books read together; every inconsistency that would make a
book trade differently from its numbers is reported."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import books

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


CFG = {"capital": {"stocks_usd": 100}, "slots": {"count": 5, "capital_per_slot": 20},
       "options": {"stake_usd": 100, "live": {"capital_usd": 1000, "per_trade_usd": 100, "max_open": 10}}}
LIM = {"max_trade_dollars": 25, "max_position_dollars": 25, "max_open_positions": 5,
       "max_daily_loss_dollars": 15, "max_drawdown_percent": 35, "allow_options": False}


def main():
    b = books.books(CFG, LIM)
    check("today's settings are consistent", books.problems(b) == [], books.problems(b))
    check("options not armed", b["options"]["armed"] is False)
    grown = {**CFG, "slots": {"count": 5, "capital_per_slot": 200}, "capital": {"stocks_usd": 1000}}
    p = books.problems(books.books(grown, LIM))
    check("scaling slots without the per-order limit is caught", any("per-order limit" in x for x in p), p)
    over = {**CFG, "slots": {"count": 6, "capital_per_slot": 20}}
    p = books.problems(books.books(over, LIM))
    check("more slots than capital or open positions is caught",
          any("more than the $100.00 book" in x for x in p) and any("open positions" in x for x in p), p)
    opt = {**CFG, "options": {"stake_usd": 50, "live": {"capital_usd": 500, "per_trade_usd": 100, "max_open": 10}}}
    p = books.problems(books.books(opt, LIM))
    check("options: over-committed book and paper/live size mismatch are caught",
          any("options: 10 x" in x for x in p) and any("different size" in x for x in p), p)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
