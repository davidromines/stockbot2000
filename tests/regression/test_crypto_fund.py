"""
Regression tests for the crypto paper fund (Phase 12 items 40, 42).

Five silent-failure properties: one engine, forward-only signalling, idempotent
step, per-fill fees, and the crypto risk floors. Everything runs against an
in-memory sqlite database built by hand; the real database is never opened.

Property 2 (forward only) is exercised on a SEPARATE database whose fund opens
after the bars have already fallen, so a pre-start entry would be visible if the
start index were ignored.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import broker as bk
import crypto_data as cd
import crypto_fund as cf
import crypto_grid as cg
import crypto_orders as co
import risk_engine as re_
import signals as sg

PASS = FAIL = 0
FAILURES = []


def check(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  PASS  {name}")
    else:
        FAIL += 1
        FAILURES.append(name)
        print(f"  FAIL  {name}  {detail}")


def _bars(conn, symbol, n=400, start=1_600_000_000, interval="1h"):
    """A dip then a recovery, so the grid entry rule fires and take-profit hits."""
    step = cd.INTERVAL_SECONDS[interval]
    rows = []
    px = 100.0
    for i in range(n):
        # A sustained decline over the first third guarantees the close falls
        # entry_drop below the prior-lookback mean; the recovery then lifts the
        # high above the average fill so a take-profit can print.
        px = 100.0 * (1.0 - 0.30 * min(i, n // 3) / (n // 3)) if i < n // 3 else \
            70.0 * (1.0 + 0.60 * (i - n // 3) / (n - n // 3))
        o = px * 0.999
        h = px * 1.02
        lo = px * 0.97
        rows.append((symbol, start + i * step, interval, step, o, h, lo, px,
                     1000.0, 100000.0, 10))
    conn.executemany(
        "INSERT OR REPLACE INTO crypto_prices (symbol, open_time, interval, "
        "bar_seconds, open, high, low, close, volume, quote_volume, trades) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?)", rows)


def fixture(started_ts=None, symbols=("BTCUSDT", "ETHUSDT")):
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cd.init(conn)
    for s in symbols:
        _bars(conn, s)
        conn.execute("INSERT OR REPLACE INTO crypto_listings (symbol, status, "
                     "trading_disabled, first_seen, last_seen) VALUES (?,?,?,?,?)",
                     (s, "online", 0, "2020-01-01", "2026-01-01"))
    conn.commit()
    cf.open_fund(conn, 100.0, started_ts=started_ts)
    return conn


def test_engine_and_forward():
    # Open at the FIRST bar so the fund may trade the whole series. Opened with
    # the default start — after all the data — it correctly records nothing,
    # because forward-only means history before the fund existed never trades.
    conn = fixture(started_ts=1_600_000_000)
    f = cf._fund(conn)
    g = json.loads(f["strategy"])
    syms = json.loads(f["symbols"])
    cf.step(conn)
    recorded = conn.execute(
        "SELECT symbol, entry_ts, exit_ts, reason, levels, ret_pct "
        "FROM crypto_fund_trades WHERE name=? ORDER BY symbol, entry_ts",
        (cf.FUND,)).fetchall()
    check("step records closed trades", len(recorded) > 0, f"{len(recorded)}")

    # Property 1: the fund's trades ARE simulate()'s trades, same engine.
    direct = []
    for s in syms:
        b = cg._bars(conn, s, f["interval"])
        res = cg.simulate(b["open"], b["high"], b["low"], b["close"], g,
                          start_i=0, close_at_end=False)
        for t in res["trades"]:
            direct.append((s, t["reason"], t["levels"], round(t["ret_pct"], 9)))
    got = [(r["symbol"], r["reason"], r["levels"], round(r["ret_pct"], 9))
           for r in recorded]
    check("one engine: fund trades match simulate()", got == direct,
          f"{len(got)} vs {len(direct)}")

    # Property 3: idempotent — a second step adds nothing.
    n1 = len(recorded)
    cf.step(conn)
    n2 = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                      (cf.FUND,)).fetchone()[0]
    check("step is idempotent", n1 == n2, f"{n1} -> {n2}")

    # Property 2: no recorded entry predates the fund's start.
    early = [r for r in recorded if r["entry_ts"] < f["started_ts"]]
    check("no entry before started_ts", not early, f"{len(early)} early")

    # Property 7: mark() writes one row per date, equity = capital + realised + unreal.
    cf.mark(conn, "2026-09-23")
    cf.mark(conn, "2026-09-23")
    rows = conn.execute("SELECT date, equity_usd, realised_usd, unrealised_usd "
                        "FROM crypto_fund_equity WHERE name=?", (cf.FUND,)).fetchall()
    check("mark writes one row per date", len(rows) == 1, f"{len(rows)}")
    r = rows[0]
    check("mark equity = capital + realised + unrealised",
          abs(r["equity_usd"] - (f["capital_usd"] + r["realised_usd"]
                                 + r["unrealised_usd"])) < 1e-6,
          f"{r['equity_usd']}")
    conn.close()


def test_forward_only_separate_db():
    # Open the fund AFTER the bars have already fallen and recovered: the dip
    # that would have triggered an entry is history, not a signal.
    conn = fixture(started_ts=1_600_000_000 + 399 * cd.INTERVAL_SECONDS["1h"])
    cf.step(conn)
    f = cf._fund(conn)
    n = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                     (cf.FUND,)).fetchone()[0]
    check("forward-only: no trades from pre-start bars", n == 0, f"{n}")
    check("forward-only: started_ts honoured", f["started_ts"] > 1_600_000_000)
    conn.close()


def test_brokers():
    # Property 4: fee is CRYPTO_TAKER_FEE x each fill's own notional.
    b = bk.CryptoSimulatedBroker(conn=None, cash=100.0,
                                 quotes={"BTCUSDT": {"symbol": "BTCUSDT",
                                                     "price": 100.0}})
    o = bk.Order(signal_id="s1", symbol="BTCUSDT", side="BUY", notional=10.0)
    o.to(bk.VALIDATING); o.to(bk.APPROVED)
    b.place_order(o)
    check("crypto broker fills the order", o.state == bk.FILLED, o.state)
    check("crypto broker charges 0.60% of notional",
          abs(b.fees_paid - 0.06) < 1e-9, f"{b.fees_paid}")
    check("crypto broker debits cash + fee",
          abs(b.cash - (100.0 - 10.0 - 0.06)) < 1e-9, f"{b.cash}")

    # Requirement 9: the live adapter never transmits.
    cb = bk.CoinbaseBroker()
    o2 = bk.Order(signal_id="s2", symbol="BTCUSDT", side="BUY", notional=10.0)
    # An order reaches a broker only after risk approval; the state machine
    # refuses CREATED -> SUBMITTING, and that refusal is correct behaviour.
    o2.to(bk.VALIDATING); o2.to(bk.APPROVED)
    cb.place_order(o2)
    check("CoinbaseBroker leaves order UNKNOWN", o2.state == bk.UNKNOWN, o2.state)
    check("CoinbaseBroker does not fill", o2.filled_quantity == 0.0)


def test_crypto_risk_floors():
    limits = {"allow_crypto": True, "allow_shorting": False,
              "min_price": 5.0, "min_market_cap_usd": 1e9,
              "crypto": {"min_dollar_volume": 5e6}}
    eng = re_.RiskEngine(limits=limits)
    port = {"equity": 100.0, "buying_power": 100.0, "positions": {},
            "daily_pnl": 0.0}
    q = {"symbol": "BTCUSDT", "price": 0.26, "dollar_volume_20": 1e9,
         "market_cap": None}
    sig = sg.Signal(symbol="BTCUSDT", action="BUY", strategy="t", reason="r",
                    asset_type="crypto", session="2026-09-23", notional_value=10.0)
    check("crypto skips equity price/cap floors",
          eng.validate(sig, port, q, {}).approved)

    off = re_.RiskEngine(limits={**limits, "allow_crypto": False})
    check("allow_crypto False rejects",
          not off.validate(sig, port, q, {}).approved)

    qn = {**q, "dollar_volume_20": None}
    rn = eng.validate(sig, port, qn, {})
    check("unknown turnover rejected",
          not rn.approved and any("liquidity unknown" in x for x in rn.reasons),
          str(rn.reasons))

    ql = {**q, "dollar_volume_20": 1e6}
    check("turnover below crypto floor rejected",
          not eng.validate(sig, port, ql, {}).approved)


def test_route_halted_when_not_stepped():
    conn = fixture()
    # The fund exists but was never stepped this session, so its book is stale
    # and the kill switch must halt the slate.
    r = co.route(conn, [])
    check("route halts on an unstepped fund", r["halted"] is True, str(r["halted"]))
    check("route reports a session", bool(r["session"]))
    conn.close()


def main():
    for fn in (test_engine_and_forward, test_forward_only_separate_db,
               test_brokers, test_crypto_risk_floors,
               test_route_halted_when_not_stepped):
        print(f"\n{fn.__name__}")
        fn()
    print(f"\n  {PASS} passed, {FAIL} failed")
    if FAILURES:
        print("  failures: " + ", ".join(FAILURES))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
