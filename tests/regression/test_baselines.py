"""
Regression test for baselines.py (Phase 6 §16).

Pinned: baselines start at the first OPEN after the fund started; the matched
universe is what cleared the floors on the start date (not what is there
today) and keeps a name that stopped trading at its last close; the fund's
figure is the restated accounting net when one exists and says so; the
index-ETF rule is fixed (IWM under the cap line, SPY over it); random
portfolios are the fund's own size; pair funds get SPY, their own index, a
50/50 legs null and random switching.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import baselines as bl
import pair_funds

FAILED = []
CFG = {"costs": {"enabled": False}, "risk": {"min_price": 5.0, "min_dollar_volume": 1e6},
       "universe": {"tradeable_types": ["common_stock"]}}


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def fixture():
    c = sqlite3.connect(":memory:")
    c.execute("CREATE TABLE prices (ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, "
              "volume REAL, source TEXT)")
    c.execute("CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL)")
    c.execute("CREATE TABLE symbols (ticker TEXT, security_type TEXT, data_quality TEXT)")
    c.execute("CREATE TABLE fundamentals (ticker TEXT, filed TEXT, market_cap REAL)")
    days = list(pd.bdate_range("2026-09-01", periods=10).strftime("%Y-%m-%d"))
    # (ticker, type, dv, day0 close, open on day1, close by day) — AAA +10%, BBB -10%,
    # DEAD stops trading on day 5 at -50%, PENNY under $5, THIN illiquid, ETF types.
    spec = {"SPY": ("etf", 1e10, 100, 100, lambda i: 100 + i), "IWM": ("etf", 1e10, 50, 50, lambda i: 50 - i),
            "QQQ": ("etf", 1e10, 10, 10, lambda i: 10 + i), "PSQ": ("etf", 1e8, 10, 10, lambda i: 10 - 0.5 * i),
            "AAA": ("common_stock", 5e7, 20, 20, lambda i: 20 + 2 * i / 9),
            "BBB": ("common_stock", 5e7, 20, 20, lambda i: 20 - 2 * i / 9),
            "DEAD": ("common_stock", 5e7, 20, 20, lambda i: 10),
            "PENNY": ("common_stock", 5e7, 2, 2, lambda i: 4), "THIN": ("common_stock", 1e3, 20, 20, lambda i: 40)}
    for t, (ty, dv, c0, o1, f) in spec.items():
        c.execute("INSERT INTO symbols VALUES (?,?,NULL)", (t, ty))
        for i, d in enumerate(days):
            if t == "DEAD" and i > 5:
                break
            cl = c0 if i == 0 else f(i)
            op = c0 if i == 0 else (o1 if i == 1 else cl)
            c.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,1,'t')", (t, d, op, cl, cl, cl))
            c.execute("INSERT INTO features VALUES (?,?,?)", (t, d, dv))
    c.execute("INSERT INTO fundamentals VALUES ('AAA','2026-01-01',2e9)")
    c.execute("INSERT INTO fundamentals VALUES ('BBB','2026-01-01',5e10)")
    return c, days


def main():
    c, days = fixture()
    check("first session after the start", bl._first_session_after(c, days[0]) == days[1])
    uni = bl.matched_universe(c, CFG, days[0])
    check("matched universe = floors on the START date", uni == ["AAA", "BBB", "DEAD"], uni)
    r = bl.universe_returns(c, uni, days[1], days[-1])
    check("a name that stopped trading keeps its last close", abs(r["DEAD"] - (-0.5)) < 1e-9, r.to_dict())
    check("open(start) -> last close", abs(r["AAA"] - 0.1) < 1e-9 and abs(r["BBB"] + 0.1) < 1e-9, r.to_dict())

    check("index ETF: median cap under $10B -> IWM",
          bl._index_etf(c, CFG, {"tickers": ["AAA", "AAA", "BBB"]}) == "IWM")
    check("... over -> SPY", bl._index_etf(c, CFG, {"tickers": ["BBB"]}) == "SPY")

    c.execute("CREATE TABLE paper_runs (run_id TEXT, name TEXT, strategy TEXT, capital_usd REAL, cash_usd REAL, "
              "started_on TEXT, last_step_on TEXT, status TEXT, created_at TEXT, label TEXT, family TEXT)")
    c.execute("CREATE TABLE paper_equity (run_id TEXT, date TEXT, cash_usd REAL, positions_usd REAL, "
              "equity_usd REAL, open_positions INTEGER)")
    c.execute("CREATE TABLE paper_trades (run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT)")
    c.execute("CREATE TABLE paper_positions (run_id TEXT, ticker TEXT)")
    c.execute("INSERT INTO paper_runs VALUES ('r1','Momo','{}',100,0,?,NULL,'open','x','Momo','momentum')", (days[0],))
    for i, d in enumerate(days):
        c.execute("INSERT INTO paper_equity VALUES ('r1',?,0,0,?,2)", (d, 100 + i))
    c.execute("INSERT INTO paper_trades VALUES ('r1','AAA',?,?)", (days[1], days[3]))
    rows = bl.run(c, CFG)
    f = rows[0]
    check("fund net from the equity curve, labelled as such", f["net"] == 9.0 and "equity curve" in f["net_source"], f)
    check("SPY baseline: open(day1) -> last close", abs(f["spy"] - 100 * (109 / 100 - 1)) < 1e-6, f.get("spy"))
    check("stock fund ETF = IWM (AAA $2B)", f["index_etf_symbol"] == "IWM" and f["index_etf"] < 0, f)
    check("matched null = equal weight of the start-date universe",
          abs(f["matched_null"] - 100 * (0.1 - 0.1 - 0.5) / 3) < 0.01, f.get("matched_null"))
    check("random portfolios are the fund's size (2)", f["random_k"] == 2 and f["random_p5"] <= f["random_p95"], f)
    check("fund percentile reported", 0 <= f["fund_percentile"] <= 100)

    c.execute("CREATE TABLE fund_accounting (as_of TEXT, fund_kind TEXT, fund_id TEXT, net_usd REAL, "
              "accounting_version INTEGER)")
    c.execute("INSERT INTO fund_accounting VALUES (?, 'paper', 'r1', 4.25, 1)", (days[-1],))
    f = bl.run(c, CFG)[0]
    check("restated accounting net wins, and says so", f["net"] == 4.25 and f["net_source"].startswith("accounting"), f)

    pair_funds.init(c)
    c.execute("INSERT INTO pair_funds (name,label,bull,bear,signal,method,param,min_hold,capital_usd,started_on,"
              "status) VALUES ('nasdaq_1x','Nasdaq Switch 1x','QQQ','PSQ','QQQ','roc',2,1,100.0,?,'open')", (days[0],))
    c.execute("INSERT INTO pair_fund_equity VALUES ('nasdaq_1x', ?, 104.0, 'QQQ', 0)", (days[-1],))
    p = [r for r in bl.run(c, CFG) if r["kind"] == "pair"][0]
    check("pair fund: its own index as the ETF", p["index_etf_symbol"] == "QQQ", p)
    q = (19 / 10 - 1)
    s = (5.5 / 10 - 1)
    check("pair fund matched null = 50/50 in the two legs", abs(p["matched_null"] - 100 * (q + s) / 2) < 1e-6, p)
    check("pair fund random switching reported", "random_p50" in p, p)
    print(bl.render(bl.run(c, CFG)))

    print(f"\n  {'ALL PASS' if not FAILED else str(len(FAILED)) + ' FAILED'}")
    return 1 if FAILED else 0


if __name__ == "__main__":
    sys.exit(main())
