"""
Regression test for market_caps.py — the sourced market-cap fallback.

Pinned: the filing cap wins; a quoted cap fills a gap only while fresh; a stale
or absent one stays unknown and the risk engine still rejects it; the LIVE
quote fetches a miss from Robinhood once and records it; a failed fetch fails
closed; an expired sign-in is not swallowed.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
from datetime import date

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import market_caps as mc
import quotes as qt
import risk_engine
import robinhood_mcp as rh
import signals as sg

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def fixture():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, atr_14 REAL, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    c.execute("INSERT INTO fundamentals VALUES ('AAA', '2026-06-01', 5e9)")
    for t in ("AAA", "GEN", "TNY"):
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', 1.0, 5e7)", (t,))
    return c


def fake_call(caps: dict, log: list):
    def call(tool, args):
        log.append((tool, tuple(args.get("symbols") or ())))
        assert tool == "get_equity_fundamentals"
        return {"data": {"results": [{"symbol": s, "market_cap": str(caps[s]), "market_date": date.today().isoformat()}
                                     for s in args["symbols"] if s in caps]}}
    return call


def main():
    today = date(2026, 9, 24)
    c = fixture()
    check("no fallback table yet: unknown, no crash", mc.lookup(c, "GEN", today=today) == (None, None))

    check("filing cap wins", mc.lookup(c, "AAA", today=today) == (5e9, "sec_filing"))
    mc.record(c, "AAA", 1e6, "robinhood", "2026-09-24")
    check("a quoted cap never overrides the filing cap", mc.lookup(c, "AAA", today=today)[1] == "sec_filing")

    mc.record(c, "GEN", 1.45e10, "robinhood", "2026-09-10")
    check("a quoted cap older than max_age_days is unknown",
          mc.lookup(c, "GEN", max_age_days=7, today=today) == (None, None))
    check("the same cap inside the window is used",
          mc.lookup(c, "GEN", max_age_days=30, today=today) == (1.45e10, "robinhood"))
    check("zero / garbage caps are not stored",
          not mc.record(c, "BAD", 0, "yfinance") and not mc.record(c, "BAD", "n/a", "yfinance"))

    # LIVE path: a miss is fetched from Robinhood once, recorded, and passes the floor.
    c = fixture()
    calls = []
    call = fake_call({"GEN": 14536686660.08, "TNY": 3.5e6}, calls)
    f = qt._db_fields(c, "GEN", "robinhood", call=call)
    check("LIVE miss fetched from Robinhood", f["market_cap"] and abs(f["market_cap"] - 14536686660.08) < 1
          and f["market_cap_source"] == "robinhood", f)
    check("recorded append-only with its date and source",
          c.execute("SELECT as_of, source FROM market_cap_quotes WHERE ticker='GEN'").fetchall()
          == [(date.today().isoformat(), "robinhood")])
    n = len(calls)
    qt._db_fields(c, "GEN", "robinhood", call=call)
    check("a recorded cap is not fetched again while fresh", len(calls) == n, calls)

    L = {"min_price": 5.0, "min_dollar_volume": 1e6, "min_market_cap_usd": 1e8}
    eng = risk_engine.RiskEngine(L)
    sig = sg.Signal(symbol="GEN", action="BUY", strategy="t", reason="t", notional_value=20.0)
    q = {"symbol": "GEN", "price": 25.0, "dollar_volume_20": 5e7, "market_cap": 1.45e10}
    check("sourced cap clears the floor", eng._check_tradeability(sig, q) is None)
    tiny = qt._db_fields(c, "TNY", "robinhood", call=call)
    check("a sourced cap below the floor is still rejected",
          "below floor" in (eng._check_tradeability(sig, {**q, "market_cap": tiny["market_cap"]}) or ""))

    # Source returns nothing / raises: stays unknown, risk engine rejects (fail closed).
    def boom(tool, args):
        raise rh.RobinhoodError("down")
    f = qt._db_fields(fixture(), "GEN", "robinhood", call=boom)
    check("failed fetch leaves the cap unknown", f["market_cap"] is None, f)
    check("and the risk engine rejects it",
          "market cap unknown" in (eng._check_tradeability(sig, {**q, "market_cap": None}) or ""))
    f = qt._db_fields(fixture(), "ZZZ", "robinhood", call=fake_call({}, []))
    check("a symbol Robinhood does not return stays unknown", f["market_cap"] is None, f)

    def expired(tool, args):
        raise rh.NeedsLogin("expired")
    try:
        qt._db_fields(fixture(), "GEN", "robinhood", call=expired)
        check("expired sign-in propagates (LIVE halts and alerts)", False)
    except rh.NeedsLogin:
        check("expired sign-in propagates (LIVE halts and alerts)", True)

    # Backfill: batched in one session; a failed batch falls back per chunk.
    names = [f"T{i:02d}" for i in range(23)]
    caps = {n: 1e9 + i for i, n in enumerate(names)}
    sessions = []

    def batch_ok(b):
        sessions.append(len(b))
        return [fake_call(caps, [])(t, a) for t, a in b]
    c = fixture()
    got = mc.fetch_robinhood(c, names, calls=batch_ok)
    check("23 names -> 3 chunks in ONE session", sessions == [3] and len(got) == 23, (sessions, len(got)))

    def batch_bad(b):
        raise rh.RobinhoodError("one chunk broke the batch")
    per = []
    got = mc.fetch_robinhood(fixture(), names, call=fake_call(caps, per), calls=batch_bad)
    check("failed batch retried per chunk, nothing lost", len(per) == 3 and len(got) == 23, (per, len(got)))

    # targets(): liquid, priced, right type, clean, and still without a cap.
    c = fixture()
    c.execute("CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT)")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    rows = [("SPY", "etf", None, 500, 1e10), ("AAA", "common_stock", None, 50, 5e7),
            ("GEN", "common_stock", None, 25, 5e7), ("THIN", "common_stock", None, 25, 1e5),
            ("PENNY", "common_stock", None, 2, 5e7), ("WRT", "warrant", None, 25, 5e7),
            ("TOPS", "common_stock", "price_anomaly", 25, 5e7), ("SH", "etf", None, 30, 5e7)]
    for t, ty, dq, px, dv in rows:
        c.execute("INSERT INTO symbols VALUES (?,?,?)", (t, ty, dq))
        c.execute("INSERT INTO prices VALUES (?, '2026-09-23', ?)", (t, px))
        c.execute("DELETE FROM features WHERE ticker=?", (t,))
        c.execute("INSERT INTO features VALUES (?, '2026-09-23', 1.0, ?)", (t, dv))
    cfg = {"risk": {"min_price": 5.0, "min_dollar_volume": 1e6},
           "market_caps": {"backfill_types": ["common_stock", "etf"]}}
    check("backfill targets: liquid, priced, typed, clean, capless",
          mc.targets(c, cfg) == ["GEN", "SH", "SPY"], mc.targets(c, cfg))

    check("without a source, _db_fields never fetches",
          qt._db_fields(fixture(), "GEN")["market_cap"] is None)

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
