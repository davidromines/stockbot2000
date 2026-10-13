"""
Drawdown tiers (owner, 2026-10-13): notice at 10%, review at 20% (new entries refused, exits still go),
stop at 35% (the existing kill switch). Synthetic numbers, in-memory database, no network.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import drawdown_tiers as dtier
from risk_engine import RiskEngine, load_limits
from signals import Signal

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


LIM = {"drawdown_notice_percent": 10.0, "drawdown_review_percent": 20.0, "max_drawdown_percent": 35.0}


def sig(action="BUY", **kw):
    base = dict(symbol="AAPL", action=action, strategy="t", reason="t", notional_value=20.0, confidence=0.8,
                session="2026-10-13")
    base.update(kw)
    return Signal(**base)


def main():
    # --- tiers
    check("below the notice level is OK", dtier.tier(9.9, LIM) == dtier.OK)
    check("at 10% is NOTICE", dtier.tier(10.0, LIM) == dtier.NOTICE)
    check("at 20% is REVIEW", dtier.tier(20.0, LIM) == dtier.REVIEW)
    check("at 35% is HALT (the existing kill switch level)", dtier.tier(35.0, LIM) == dtier.HALT)
    check("a missing key turns that tier off", dtier.tier(50.0, {"drawdown_notice_percent": 10.0}) == dtier.NOTICE)
    check("no keys at all: everything OK", dtier.tier(80.0, {}) == dtier.OK)
    check("entries are paused at 20%", dtier.entry_pause_reason(20.0, LIM) is not None)
    check("entries are not paused at 19.9%", dtier.entry_pause_reason(19.9, LIM) is None)
    check("no review key: entries never paused by this module", dtier.entry_pause_reason(60.0, {}) is None)

    # --- risk engine: entries refused at the review level, exits not
    limits = {**load_limits(), "account_type": "cash", "limited_margin_settled_funds": True, **LIM}
    eng = RiskEngine(limits)
    quote = {"price": 50.0, "dollar_volume_20": 20_000_000.0, "market_cap": 5e9}
    held = {"AAPL": {"quantity": 0.4, "value": 20.0}}

    def pf(dd, positions=None):
        return {"equity": 100.0, "buying_power": 100.0, "unsettled_proceeds": 0.0, "day_trades_5d": 0, "daily_pnl": 0.0,
                "drawdown_percent": dd, "positions": positions or {}}

    r = eng.validate(sig("BUY"), pf(5.0), quote)
    check("an entry at 5% drawdown is approved", r.approved, r.reasons if hasattr(r, "reasons") else r)
    r = eng.validate(sig("BUY"), pf(25.0), quote)
    check("an entry at 25% drawdown is refused for the review level",
          (not r.approved) and any("review level" in x for x in r.reasons), r.reasons)
    r = eng.validate(sig("CLOSE", notional_value=None, quantity=0.4), pf(25.0, held), quote)
    check("an exit at 25% drawdown is still approved", r.approved, r.reasons)

    # --- the alert: once per day per tier
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE live_equity (at TEXT, session TEXT, equity REAL, buying_power REAL)")
    for i, e in enumerate([90.0, 100.0, 95.0, 88.0]):
        c.execute("INSERT INTO live_equity VALUES (?,?,?,?)", (f"2026-10-0{i + 1}T15:00:00", f"2026-10-0{i + 1}", e, 0.0))
    sent = []
    send = lambda title, body: sent.append((title, body))
    eq, peak, dd = dtier.current(c)
    check("drawdown is measured from the highest equity ever recorded", abs(dd - 12.0) < 1e-9 and peak == 100.0, (eq, peak, dd))
    check("a 12% drawdown alerts NOTICE", dtier.alert_if_new(c, LIM, send, today="2026-10-13") == dtier.NOTICE and len(sent) == 1)
    check("the same tier on the same day does not alert again", dtier.alert_if_new(c, LIM, send, today="2026-10-13") is None and len(sent) == 1)
    check("the notice says what was and was not done", "No action taken" in sent[0][1] and "$100.00 peak" in sent[0][1], sent[0])
    check("the next day it alerts again", dtier.alert_if_new(c, LIM, send, today="2026-10-14") == dtier.NOTICE and len(sent) == 2)
    check("going deeper alerts REVIEW the same day",
          dtier.alert_if_new(c, LIM, send, equity=75.0, today="2026-10-14") == dtier.REVIEW and len(sent) == 3)
    check("the review message says entries are paused", "entries are paused" in sent[-1][1], sent[-1])
    check("an account above the notice level alerts nothing", dtier.alert_if_new(c, LIM, send, equity=99.0, today="2026-10-20") is None and len(sent) == 3)

    # --- the shipped config
    shipped = load_limits()
    check("the shipped risk.yaml sets the notice and review levels",
          shipped.get("drawdown_notice_percent") == 10.0 and shipped.get("drawdown_review_percent") == 20.0, shipped)
    check("...and leaves the 35% stop unchanged", shipped.get("max_drawdown_percent") == 35.0)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
