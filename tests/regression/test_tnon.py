"""
REGRESSION: the TNON trade (Phase 6 §24, case_studies/TNON.md).

TNON: ~$5.54, $102M/day of blow-off volume, a ~$3.5M company with NO market
cap on record. It passed the price and liquidity floors and lost ~29%. This
pins every route an equivalent security could take today:

  1. exactly TNON (no cap anywhere)       risk engine: unknown -> rejected
                                          daily book size filter: dropped
  2. the fallback finds its cap ($3.5M)   rejected below the floor
  3. the fallback fails or is stale       still unknown -> still rejected
  4. not a blanket ban                    the same liquidity with a $5B cap passes

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import daily_picks
import market_caps
import quotes as qt
import robinhood_mcp as rh
from risk_engine import RiskEngine, load_limits
from signals import Signal

FAILED = []
TNON_PX, TNON_DV, TNON_CAP = 5.54, 102_000_000.0, 3.5e6


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def db():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    for t in ("TNON", "BIGCO"):
        c.execute("INSERT INTO features VALUES (?, '2026-09-11', 0.5, ?)", (t, TNON_DV))
    c.execute("INSERT INTO fundamentals VALUES ('BIGCO', '2026-06-30', 5e9)")
    return c


def rh_returns(caps):
    def call(tool, args):
        return {"data": {"results": [{"symbol": s, "market_cap": str(caps[s]), "market_date": date.today().isoformat()}
                                     for s in args["symbols"] if s in caps]}}
    return call


def main():
    L = load_limits()
    eng = RiskEngine(L)
    floor = float(L["min_market_cap_usd"])
    check("the floor in force is at least $100M", floor >= 100e6, floor)
    portfolio = {"equity": 100.0, "cash": 100.0, "positions": {}, "daily_pnl": 0.0, "drawdown_percent": 0.0}
    sig = Signal(symbol="TNON", action="BUY", strategy="lab_survivor", reason="entry", notional_value=20.0)

    def verdict(q):
        return eng._check_tradeability(sig, q)

    # 1. exactly TNON: the price and liquidity floors pass, the cap is unknown.
    c = db()
    f = qt._db_fields(c, "TNON")
    q = {"symbol": "TNON", "price": TNON_PX, **f}
    check("TNON clears price and liquidity (why it got through)",
          TNON_PX >= float(L["min_price"]) and f["dollar_volume_20"] >= float(L["min_dollar_volume"]))
    check("1. no cap on record -> rejected as unknown", "market cap unknown" in (verdict(q) or ""), verdict(q))
    r = eng.validate(sig, portfolio, q, {})
    check("   ... and validate() refuses the order", not r.approved, r.reasons)

    cfg = {"risk": {"min_market_cap_usd": floor, "require_known_market_cap": True}}
    kept = daily_picks._size_filter(c, cfg, [{"ticker": "TNON"}, {"ticker": "BIGCO"}])
    check("1. daily book size filter drops TNON, keeps a $5B name",
          [k["ticker"] for k in kept] == ["BIGCO"], kept)

    # 2. the fallback finds its real cap: rejected below the floor.
    c = db()
    f = qt._db_fields(c, "TNON", "robinhood", call=rh_returns({"TNON": TNON_CAP}))
    check("2. fallback supplies the $3.5M cap, sourced", f["market_cap"] == TNON_CAP
          and f["market_cap_source"] == "robinhood", f)
    v = verdict({"symbol": "TNON", "price": TNON_PX, **f})
    check("   ... and it is rejected below the floor", "below floor" in (v or ""), v)

    # 3. the fallback fails, returns nothing, or is stale: still unknown.
    def down(tool, args):
        raise rh.RobinhoodError("unavailable")
    for why, call in (("fails", down), ("returns nothing", rh_returns({}))):
        f = qt._db_fields(db(), "TNON", "robinhood", call=call)
        check(f"3. fallback {why} -> still unknown -> rejected",
              f["market_cap"] is None and "market cap unknown" in (verdict({"price": TNON_PX, **f}) or ""), f)
    c = db()
    market_caps.record(c, "TNON", 5e9, "robinhood", (date.today() - timedelta(days=30)).isoformat())
    f = qt._db_fields(c, "TNON")
    check("3. a cap older than the window is not used (even a flattering one)", f["market_cap"] is None, f)

    # 4. not a blanket ban.
    c = db()
    f = qt._db_fields(c, "BIGCO")
    q = {"symbol": "BIGCO", "price": TNON_PX, **f}
    check("4. same price and liquidity with a known $5B cap passes", verdict(q) is None, verdict(q))

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
