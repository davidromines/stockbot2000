"""
2026-09-28 no-buy morning: (a) a real account's unsettled figure is the broker's own, not
the larger of it and the ledger (the ledger adds a holiday-margin day to every sale);
(b) a cash refusal is account-level, so the entry pass stops trying candidates.
In-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import account_rules as ar
import slot_trader as st

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


c = sqlite3.connect(":memory:")
# The ledger (T+1 + a holiday-margin day) still counted Friday's $70.92 plus today's $18.33.
ar.unsettled_proceeds = lambda conn, today, mode, sd=1, hm=1: 89.25
lim = {"account_type": "cash", "settlement_days": 1, "holiday_margin_days": 1}
ledger = ar.unsettled_proceeds(c, "2026-09-28", "LIVE", 1, 1)
out = ar.annotate(c, {"buying_power": 89.25, "equity": 89.25, "broker_unsettled": 18.33}, lim, "2026-09-28", "LIVE")
check("broker's unsettled figure is used, not the larger ledger figure",
      out["unsettled_proceeds"] == 18.33, (out["unsettled_proceeds"], ledger))
out = ar.annotate(c, {"buying_power": 89.25, "equity": 89.25, "broker_unsettled": None}, lim, "2026-09-28", "LIVE")
check("unreadable broker figure leaves settled cash unknown", "unsettled_proceeds" not in out, out)
out = ar.annotate(c, {"buying_power": 89.25, "equity": 89.25}, lim, "2026-09-28", "SIMULATION")
check("no broker figure (simulation): the ledger", out["unsettled_proceeds"] == ledger, out)
a, why = ar.check_buy({"buying_power": 89.25, "unsettled_proceeds": 18.33}, lim, 20.0)
check("$70.92 settled buys a $20 slot", a == 20.0 and why is None, (a, why))

check("settled-cash refusal is account-level",
      st._account_level(["only $0.00 settled ($89.25 unsettled): buying with unsettled funds risks a good-faith violation"]))
check("market-cap refusal is not", not st._account_level(["market cap $0M below floor $100M"]))

pf = {"buying_power": 89.25, "equity": 89.25, "unsettled_proceeds": 89.25, "day_trades_5d": 0}
lm = {"account_type": "limited_margin"}
a, why = ar.check_buy(pf, lm, 20.0)
check("limited margin: settled-funds rule on by default", why is not None and "settled" in why, (a, why))
a, why = ar.check_buy(pf, {**lm, "limited_margin_settled_funds": False}, 20.0)
check("limited margin: operator switch off -> buying power governs", a == 20.0 and why is None, (a, why))

sys.exit(1 if FAILED else 0)
