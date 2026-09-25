"""
Regression test for crypto_costs.py (Stage K1): spread parsing, logging and
the measured half-spread with its two fallbacks. No network; fake quote tool.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import crypto_costs as cc

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def quote(symbol, bid, ask):
    return {"symbol": symbol, "bid_price": bid, "ask_price": ask, "mark_price": "100",
            "routing": "Market Maker Routing", "updated_at": "2026-09-25T01:00:27.034-04:00"}


def resp(rows):
    return {"data": {"results": rows}, "guide": "..."}


def caller(rows, seen=None):
    def call(tool, args):
        if seen is not None:
            seen.append((tool, args))
        return resp(rows)
    return call


def conn():
    c = sqlite3.connect(":memory:")
    cc.init(c)
    return c


def fill(c, symbol_raw, bid, ask, n, day="2026-09-24"):
    for i in range(n):
        cc.log_spreads(c, caller([quote(symbol_raw, bid, ask)]), ["x"], "1",
                       now=f"{day}T{i % 24:02d}:{i // 24:02d}:00Z")


def main():
    p = cc.parse_quotes(resp([quote("BTCUSD", "99", "101")]))
    check("symbol conversion BTCUSD -> BTC-USD", p and p[0]["symbol"] == "BTC-USD", p)
    check("spread_pct for bid 99 ask 101 equals 0.02", p and abs(p[0]["spread_pct"] - 0.02) < 1e-12, p)
    check("zero-bid row skipped", cc.parse_quotes(resp([quote("BTCUSD", "0", "101")])) == [])
    check("ask < bid and non-numeric rows skipped",
          cc.parse_quotes(resp([quote("ETHUSD", "101", "99"), quote("BTCUSD", "abc", "101")])) == [])

    c = conn()
    seen = []
    now = "2026-09-25T12:00:00Z"
    call = caller([quote("BTCUSD", "99", "101"), quote("ETHUSD", "199", "201")], seen)
    n = cc.log_spreads(c, call, ["BTC-USD", "ETH-USD"], "403446024", now=now)
    check("log_spreads inserts 2 rows", n == 2, n)
    check("one quote call, symbols and account passed",
          len(seen) == 1 and seen[0][0] == "get_crypto_quotes"
          and seen[0][1] == {"symbols": ["BTC-USD", "ETH-USD"], "rhs_account_number": "403446024"}, seen)
    check("repeat with the same now inserts 0", cc.log_spreads(c, call, ["BTC-USD"], "1", now=now) == 0)

    c = conn()
    fill(c, "BTCUSD", "99", "101", 12)                      # 2% spread, 12 samples
    hs = cc.half_spread(c, "BTC-USD", now=now)
    check("per-symbol median / 2 with >= min_samples rows", abs(hs - 0.01) < 1e-12, hs)
    hs = cc.half_spread(c, "ETH-USD", now=now)
    check("thin pair falls back to the all-symbol median", abs(hs - 0.01) < 1e-12, hs)
    hs = cc.half_spread(c, "BTC-USD", now="2026-10-30T00:00:00Z")
    check("rows outside the window are ignored -> default", hs == cc.DEFAULTS["default_half_spread"], hs)
    check("empty table -> default_half_spread",
          cc.half_spread(conn(), "BTC-USD", now=now) == cc.DEFAULTS["default_half_spread"])
    check("cfg overrides min_samples",
          abs(cc.half_spread(c, "BTC-USD", cfg={"min_samples": 50, "default_half_spread": 0.02},
                             now=now) - 0.02) < 1e-12)
    r = cc.report(c, now=now)
    check("report: one row per symbol with n and median",
          len(r) == 1 and r[0]["n"] == 12 and abs(r[0]["median_spread_pct"] - 0.02) < 1e-12, r)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
