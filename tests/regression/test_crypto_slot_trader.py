"""
Stage K5/K6: crypto_slot_trader in SIMULATION through the real ExecutionEngine
and RiskEngine. Pinned: inert while allow_crypto is false; a crypto slot buys
the pair its fund holds, with the fund's stop; sells when the fund closes it or
the price reaches the stop; crypto trades never enter slot_trades or the equity
ledger ("slot" prefix); the kill switch flattens. In-memory database only.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import crypto_data
import crypto_fund
import crypto_slot_trader as cst
import slot_trader as st

FAILED = []
LIMITS = {"execution_mode": "SIMULATION", "allow_crypto": True, "allow_fractional_shares": True,
          "crypto": {"min_dollar_volume": 1000.0}, "max_trade_dollars": 25}


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


def fixture(price=100.0):
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    crypto_data.init(c)
    crypto_fund.init(c)
    st.init(c)
    cst.init(c)
    for i in range(25):
        c.execute("INSERT INTO crypto_prices (symbol, open_time, interval, bar_seconds, open, high, low, close, "
                  "volume) VALUES ('BTC-USD', ?, '1d', 86400, ?, ?, ?, ?, 1000)",
                  (i * 86400, price, price, price, price))
    c.execute("INSERT INTO crypto_fund (name, capital_usd, started_ts, interval, strategy, symbols, status, created_at) "
              "VALUES ('f1', 100, 0, '1d', '{\"engine\": \"crypto_trend\"}', '[\"BTC-USD\"]', 'open', 'x')")
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) "
              "VALUES ('2026-09-25T00:00:00', 2, 'ASSIGN', 'crypto:f1', 1, 20.0, 'SIMULATION', 't')")
    c.commit()
    return c


def fund_holds(c, stop=90.0):
    c.execute("DELETE FROM crypto_fund_open")
    c.execute("INSERT INTO crypto_fund_open VALUES ('f1', 'BTC-USD', 86400, ?)",
              (json.dumps({"entry_px": 100.0, "stop": stop}),))
    c.commit()


def set_price(c, px):
    c.execute("UPDATE crypto_prices SET open=?, high=?, low=?, close=? WHERE open_time=24*86400", (px, px, px, px))
    c.commit()


def main():
    cst.refresh = lambda conn, funds: None             # no network, no fund replay in the test

    c = fixture()
    fund_holds(c)
    r = cst.run(c, {}, "SIMULATION", limits={**LIMITS, "allow_crypto": False})
    check("unarmed and flat: does nothing", r and r[0]["status"] == "no_action"
          and not cst.open_positions(c, "SIMULATION"), r)

    r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
    pos = cst.open_positions(c, "SIMULATION")
    check("crypto slot buys the pair its fund holds", 2 in pos and pos[2]["symbol"] == "BTC-USD"
          and any(x["action"] == "BUY" and x["status"] == "filled" for x in r), r)
    check("$20 of BTC at the bar price", 2 in pos and abs(pos[2]["quantity"] - 0.2) < 1e-9, pos.get(2))
    check("position carries the fund's stop", 2 in pos and pos[2]["stop"] == 90.0, pos.get(2))
    check("nothing in the equity slot log", c.execute("SELECT COUNT(*) FROM slot_trades").fetchone()[0] == 0)
    sigs = [x[0] for x in c.execute("SELECT strategy FROM signals")]
    check("signals use the cslot prefix, never slot", sigs and all(s.startswith("cslot") for s in sigs), sigs)

    r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
    check("second run holds (no duplicate buy)", not [x for x in r if x["action"] in ("BUY", "SELL")], r)

    set_price(c, 89.0)
    r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
    check("price at or below the stop sells", any(x["action"] == "SELL" and x["status"] == "filled" for x in r)
          and 2 not in cst.open_positions(c, "SIMULATION"), r)

    c = fixture()
    fund_holds(c, stop=99.0)
    r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
    check("no buy within 2% of the fund's stop", not cst.open_positions(c, "SIMULATION")
          and any("within 2%" in (x.get("reason") or "") for x in r), r)

    c = fixture()
    fund_holds(c)
    cst.run(c, {}, "SIMULATION", limits=LIMITS)
    c.execute("DELETE FROM crypto_fund_open")
    c.commit()
    r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
    check("fund closes its position -> slot sells", any(x["action"] == "SELL" and "strategy exit" in x["reason"]
                                                        for x in r) and not cst.open_positions(c, "SIMULATION"), r)

    c = fixture()
    fund_holds(c)
    cst.run(c, {}, "SIMULATION", limits=LIMITS)
    r = cst.run(c, {}, "SIMULATION", limits={**LIMITS, "allow_crypto": False})
    check("disarmed with a position: it is still managed, no new buys",
          not [x for x in r if x["action"] == "BUY"] and 2 in cst.open_positions(c, "SIMULATION"), r)

    os.environ["TRADING_ENABLED"] = "false"
    try:
        r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
        check("kill switch flattens crypto slots", any(x["action"] == "SELL" and "emergency" in x["reason"]
                                                       for x in r) and not cst.open_positions(c, "SIMULATION"), r)
        check("no buy while the switch is on", not [x for x in r if x["action"] == "BUY"], r)
    finally:
        os.environ.pop("TRADING_ENABLED", None)

    c = fixture()
    fund_holds(c)
    cst.run(c, {}, "SIMULATION", limits=LIMITS)
    c.execute("INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version, capital_usd, mode, reason) "
              "VALUES ('2026-09-25T01:00:00', 2, 'RELEASE', 'crypto:f1', 1, NULL, 'SIMULATION', 't')")
    c.commit()
    r = cst.run(c, {}, "SIMULATION", limits=LIMITS)
    check("released slot's crypto position is sold", any("released" in (x.get("reason") or "") for x in r)
          and not cst.open_positions(c, "SIMULATION"), r)

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
