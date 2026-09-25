"""
Stage K4: a crypto trend fund ranks on its crypto_backtests row, the grid fund
keeps its neutral start, and no crypto strategy is slot-eligible while
config/risk.yaml allow_crypto is false. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import crypto_backtest as cb
import crypto_fund
import ranking
import slots

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def main():
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    crypto_fund.init(c)
    cb.init(c)
    g = {"family": "trend_sma", "n": 200, "stop_atr": 3.0, "universe": "all"}
    sid = cb.strategy_id(g)
    c.execute("INSERT INTO crypto_backtests (strategy_id, genome, trades, net_per_trade) VALUES (?,?,?,?)",
              (sid, json.dumps(g), 50, 0.031))
    c.execute("INSERT INTO crypto_fund (name, capital_usd, started_ts, interval, strategy, symbols, status, "
              "created_at) VALUES ('t1', 100, 0, '1d', ?, '[\"BTC-USD\",\"ETH-USD\"]', 'open', 'x')",
              (json.dumps({"engine": "crypto_trend", "genome": g, "strategy_id": sid}),))
    c.execute("INSERT INTO crypto_fund (name, capital_usd, started_ts, interval, strategy, symbols, status, "
              "created_at) VALUES ('grid', 100, 0, '1h', '{\"levels\": 3}', '[\"BTC-USD\"]', 'open', 'x')")
    c.commit()
    bt = ranking.backtest_per_trade(c, {}, "crypto:t1", 1)
    check("trend fund ranks on its crypto backtest", bt is not None and abs(bt - 0.031) < 1e-12, bt)
    check("grid fund has no backtest (neutral start)", ranking.backtest_per_trade(c, {}, "crypto:grid", 1) is None)
    check("unknown crypto fund has no backtest", ranking.backtest_per_trade(c, {}, "crypto:nope", 1) is None)

    import risk_engine
    real = risk_engine.load_limits
    try:
        risk_engine.load_limits = lambda *a, **k: {"allow_crypto": False}
        check("allow_crypto false -> not armed", slots._crypto_armed() is False)
        risk_engine.load_limits = lambda *a, **k: {"allow_crypto": True}
        check("allow_crypto true -> armed", slots._crypto_armed() is True)

        def boom(*a, **k):
            raise RuntimeError("unreadable")
        risk_engine.load_limits = boom
        check("unreadable limits fail closed", slots._crypto_armed() is False)

        risk_engine.load_limits = lambda *a, **k: {"allow_crypto": False}
        ranking.rank = lambda conn, cfg: [{"strategy_key": "crypto:t1", "version": 1, "name": "t1", "score": 0.03,
                                           "passes_gate": True, "gate": "ok", "forward_trades": 0}]
        slots.genome_for = lambda conn, k, v: {"risk": {"stop_atr_multiple": 3.0}}
        slots._latest_session = lambda conn: None
        out = slots.assess(c, {})
        check("crypto strategy not slot-eligible while unarmed",
              out and not out[0]["eligible"] and any("allow_crypto" in r for r in out[0]["reasons"]), out)
    finally:
        risk_engine.load_limits = real

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
