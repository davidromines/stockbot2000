FILE: tests/regression/test_crypto_fund.py
```python
"""
Regression tests for the crypto paper fund, its order slate, the crypto broker
adapters and the crypto risk floors. Phase 12, items 40 and 42.

WHAT THESE TESTS ARE FOR
------------------------
Every property below fails SILENTLY. A fund that replays the past and calls it
forward, a step that double-books a trade, a fee charged once per position
instead of once per fill, an equity floor applied to a pair — none of these
raise. They produce a number that looks like a result. This project's history is
measurement bugs that ran fine and computed the wrong thing, so each property
gets a test that would have caught the version of it that already happened.

IN MEMORY ONLY
--------------
Every test builds its own `sqlite3.connect(":memory:")` and inserts bars by
hand. The real database is never opened: a regression suite that reads live
state reports on the state, not on the code, and would pass or fail depending
on what was ingested that morning.

Run: PYTHONPATH=. venv/bin/python tests/regression/test_crypto_fund.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import sqlite3
import sys
import traceback
from datetime import datetime, timezone

import numpy as np

import broker
import crypto_data as cd
import crypto_fund as cf
import crypto_grid as cg
import crypto_orders as co
import risk_engine as re_
import signals as sg

RESULTS = []


def check(name: str, cond: bool, detail: str = "") -> None:
    RESULTS.append((name, bool(cond), detail))
    print(f"  {'PASS' if cond else 'FAIL'}  {name}" + (f"  — {detail}" if detail else ""))


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

HOUR = cd.INTERVAL_SECONDS["1h"]
# A fixed epoch so every fixture is reproducible. 2024-01-01T00:00:00Z.
T0 = 1704067200


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cd.init(conn)
    return conn


def _insert_bars(conn, symbol: str, closes, interval: str = "1h",
                 start: int = T0, high_extra: float = 0.0,
                 low_extra: float = 0.0) -> None:
    """
    Insert one bar per close. open == previous close (or the first close), so a
    fill at the next bar's open is a known number rather than a coincidence.
    """
    prev = closes[0]
    for i, c in enumerate(closes):
        o = prev
        hi = max(o, c) * (1 + high_extra)
        lo = min(o, c) * (1 - low_extra)
        conn.execute(
            "INSERT INTO crypto_prices (symbol, open_time, interval, bar_seconds,"
            " open, high, low, close, volume, quote_volume, trades)"
            " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (symbol, start + i * HOUR, interval, HOUR, o, hi, lo, c,
             1000.0, 1000.0 * c, 10))
        prev = c
    conn.commit()


def _listing(conn, symbol: str, status: str = "online",
             disabled: int = 0) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO crypto_listings (symbol, status, trading_disabled,"
        " first_seen, last_seen) VALUES (?,?,?,?,?)",
        (symbol, status, disabled, "2024-01-01", "2024-01-02"))
    conn.commit()


def _dip_then_rally(n: int = 120) -> list:
    """
    A series that triggers a grid entry and then a take-profit: flat, a drop
    below the entry reference, then a recovery above the average fill.
    """
    closes = [100.0] * 30
    closes += [100.0 - 0.5 * k for k in range(1, 11)]     # down to 95.0
    closes += [95.0 + 0.5 * k for k in range(1, 21)]      # back to 105.0
    closes += [105.0] * (n - len(closes))
    return closes[:n]


def _fund_conn(symbol: str = "BTCUSDT", closes=None, started_ts: int | None = None,
               genome: dict | None = None):
    """A db with one pair, a listing, bars, and an opened fund."""
    conn = _conn()
    closes = closes if closes is not None else _dip_then_rally()
    _insert_bars(conn, symbol, closes)
    _listing(conn, symbol)
    cf.open_fund(conn, 100.0, genome=genome, started_ts=started_ts)
    return conn, symbol, closes


# ---------------------------------------------------------------------------
# Property 1 — one engine
# ---------------------------------------------------------------------------

def test_one_engine():
    """
    The fund's closed trades must be exactly what `simulate()` produces when
    called directly with the same start index and `close_at_end=False`. If the
    fund ever grows its own copy of the strategy, this is the test that fails.
    """
    conn, sym, closes = _fund_conn()
    f = cf._fund(conn)
    g = json.loads(f["strategy"])
    cf.step(conn)

    rows = conn.execute(
        "SELECT entry_ts, exit_ts, reason, levels, ret_pct FROM crypto_fund_trades"
        " WHERE name=? AND symbol=? ORDER BY entry_ts", (cf.FUND, sym)).fetchall()

    b = cg._bars(conn, sym, "1h")
    ts = np.array([r[0] for r in conn.execute(
        "SELECT open_time FROM crypto_prices WHERE symbol=? AND interval=?"
        " ORDER BY open_time", (sym, "1h"))], dtype="int64")
    start_i = int(np.searchsorted(ts, f["started_ts"]))
    direct = cg.simulate(b["open"], b["high"], b["low"], b["close"], g,
                         start_i=start_i, close_at_end=False)

    check("one engine: fund recorded at least one closed trade",
          len(rows) > 0, f"{len(rows)} trade(s)")
    check("one engine: trade count matches simulate()",
          len(rows) == len(direct["trades"]),
          f"fund {len(rows)} vs simulate {len(direct['trades'])}")

    same = True
    detail = ""
    for row, t in zip(rows, direct["trades"]):
        if (int(row["entry_ts"]) != int(ts[t["entry_i"]])
                or int(row["exit_ts"]) != int(ts[t["exit_i"]])
                or row["reason"] != t["reason"]
                or abs(row["ret_pct"] - t["ret_pct"]) > 1e-9):
            same = False
            detail = (f"fund ({row['entry_ts']},{row['exit_ts']},{row['reason']},"
                      f"{row['ret_pct']:.6f}) vs simulate "
                      f"({ts[t['entry_i']]},{ts[t['exit_i']]},{t['reason']},"
                      f"{t['ret_pct']:.6f})")
            break
    check("one engine: every trade matches simulate() bar-for-bar", same, detail)

    # The fund must not close a trade the engine left running.
    check("one engine: an unfinished grid is held OPEN, not closed at the last bar",
          direct["open"] is not None or len(rows) == len(direct["trades"]),
          "open grid present" if direct["open"] else "no open grid in this fixture")


def test_open_grid_is_not_booked():
    """
    A grid still running off the end of the data must appear in
    `crypto_fund_open` and NOT in `crypto_fund_trades`. Booking it would record
    a fill that never happened.
    """
    # A monotone decline never reaches take-profit and never stops out within
    # the fixture, so the grid is still open at the last bar.
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    closed = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                          (cf.FUND,)).fetchone()[0]
    opens = conn.execute("SELECT COUNT(*) FROM crypto_fund_open WHERE name=?",
                         (cf.FUND,)).fetchone()[0]
    check("open grid: an unfinished grid is recorded as open", opens == 1,
          f"{opens} open row(s)")
    check("open grid: an unfinished grid is not booked as a closed trade",
          closed == 0, f"{closed} closed trade(s)")


# ---------------------------------------------------------------------------
# Property 2 — forward only
# ---------------------------------------------------------------------------

def test_forward_only():
    """
    A separate db whose bars all predate the fund's start. The entry rule is
    satisfied in that history, so a fund that replayed the past would book a
    trade; a forward-only fund books nothing.
    """
    closes = _dip_then_rally()
    conn = _conn()
    _insert_bars(conn, "BTCUSDT", closes)
    _listing(conn, "BTCUSDT")
    # Start AFTER the last bar: every bar is history the lookback may read and
    # none may signal.
    last_open = T0 + (len(closes) - 1) * HOUR
    cf.open_fund(conn, 100.0, started_ts=last_open + HOUR)
    cf.step(conn)
    n = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                     (cf.FUND,)).fetchone()[0]
    check("forward only: no trade is entered from bars before the fund opened",
          n == 0, f"{n} trade(s) booked from pre-fund history")

    # And the same fixture with the fund opened at the first bar DOES trade, so
    # the test above is not passing because the fixture never triggers.
    conn2 = _conn()
    _insert_bars(conn2, "BTCUSDT", closes)
    _listing(conn2, "BTCUSDT")
    cf.open_fund(conn2, 100.0, started_ts=T0)
    cf.step(conn2)
    n2 = conn2.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                       (cf.FUND,)).fetchone()[0]
    check("forward only: the same fixture does trade when the fund predates it",
          n2 > 0, f"{n2} trade(s)")

    # Every recorded entry must be at or after the fund's start.
    f = cf._fund(conn2)
    bad = conn2.execute(
        "SELECT COUNT(*) FROM crypto_fund_trades WHERE name=? AND entry_ts < ?",
        (cf.FUND, f["started_ts"])).fetchone()[0]
    check("forward only: no recorded entry predates started_ts", bad == 0,
          f"{bad} early entry(ies)")


def test_open_fund_starts_after_newest_closed_bar():
    """
    `open_fund` with no explicit start must begin at the bar AFTER the newest
    closed one, so the first signal is the next bar to close.
    """
    conn = _conn()
    closes = _dip_then_rally()
    _insert_bars(conn, "BTCUSDT", closes)
    _listing(conn, "BTCUSDT")
    r = cf.open_fund(conn, 100.0)
    newest = T0 + (len(closes) - 1) * HOUR
    check("open_fund: start is the bar after the newest closed bar",
          r["started_ts"] == newest + HOUR,
          f"started_ts {r['started_ts']} vs {newest + HOUR}")


# ---------------------------------------------------------------------------
# Property 3 — idempotent step
# ---------------------------------------------------------------------------

def test_step_is_idempotent():
    conn, sym, _ = _fund_conn()
    cf.step(conn)
    first = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                         (cf.FUND,)).fetchone()[0]
    r2 = cf.step(conn)
    second = conn.execute("SELECT COUNT(*) FROM crypto_fund_trades WHERE name=?",
                          (cf.FUND,)).fetchone()[0]
    check("idempotent: the first step records trades", first > 0, f"{first}")
    check("idempotent: a second step records no new trades",
          r2.get("new_trades", -1) == 0, f"new_trades={r2.get('new_trades')}")
    check("idempotent: the trade count is unchanged after a second step",
          first == second, f"{first} then {second}")

    # The open-grid table is rebuilt each step, so it must not accumulate.
    opens = conn.execute("SELECT COUNT(*) FROM crypto_fund_open WHERE name=?",
                         (cf.FUND,)).fetchone()[0]
    check("idempotent: open grids do not accumulate across steps", opens <= 1,
          f"{opens} open row(s)")


# ---------------------------------------------------------------------------
# mark()
# ---------------------------------------------------------------------------

def test_mark():
    conn, sym, _ = _fund_conn()
    cf.step(conn)
    r1 = cf.mark(conn, "2024-03-01")
    r2 = cf.mark(conn, "2024-03-01")     # same date, must replace not duplicate
    r3 = cf.mark(conn, "2024-03-02")
    n = conn.execute("SELECT COUNT(*) FROM crypto_fund_equity WHERE name=?",
                     (cf.FUND,)).fetchone()[0]
    check("mark: one row per date", n == 2, f"{n} row(s) for 2 dates")
    check("mark: re-marking the same date replaces rather than duplicates",
          r1["equity"] == r2["equity"], f"{r1['equity']} vs {r2['equity']}")

    f = cf._fund(conn)
    realised = conn.execute("SELECT COALESCE(SUM(net_usd),0) FROM crypto_fund_trades"
                            " WHERE name=?", (cf.FUND,)).fetchone()[0]
    row = conn.execute("SELECT equity_usd, realised_usd, unrealised_usd"
                       " FROM crypto_fund_equity WHERE name=? AND date=?",
                       (cf.FUND, "2024-03-02")).fetchone()
    check("mark: equity equals capital + realised + unrealised",
          abs(row["equity_usd"] - (f["capital_usd"] + row["realised_usd"]
                                   + row["unrealised_usd"])) < 1e-6,
          f"{row['equity_usd']:.4f} vs {f['capital_usd'] + row['realised_usd'] + row['unrealised_usd']:.4f}")
    check("mark: realised equals the sum of closed net_usd",
          abs(row["realised_usd"] - realised) < 1e-6,
          f"{row['realised_usd']:.4f} vs {realised:.4f}")
    check("mark: the second date is recorded", r3["date"] == "2024-03-02")


def test_mark_charges_entry_fees_on_open_grids():
    """
    An open grid's unrealised P&L must be charged the entry fees already paid,
    so it never looks better than it is before its exit fee.
    """
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    cf.mark(conn, "2024-03-01")
    row = conn.execute("SELECT unrealised_usd FROM crypto_fund_equity WHERE name=?",
                       (cf.FUND,)).fetchone()
    st = json.loads(conn.execute("SELECT state FROM crypto_fund_open WHERE name=?",
                                 (cf.FUND,)).fetchone()[0])
    naive = st["qty"] * st["last_close"] - st["deployed_usd"]
    check("mark: an open grid's unrealised P&L is charged its entry fees",
          row["unrealised_usd"] < naive,
          f"{row['unrealised_usd']:.6f} vs naive {naive:.6f}")
    check("mark: the entry fee charged is the taker fee on deployed capital",
          abs((naive - row["unrealised_usd"]) - st["deployed_usd"] * cg.TAKER_FEE) < 1e-9,
          f"{naive - row['unrealised_usd']:.8f} vs {st['deployed_usd'] * cg.TAKER_FEE:.8f}")


# ---------------------------------------------------------------------------
# Property 4 — fees on each fill's own notional
# ---------------------------------------------------------------------------

def test_crypto_broker_fee_per_fill():
    b = broker.CryptoSimulatedBroker(conn=None, cash=100.0,
                                     quotes={"BTCUSDT": {"symbol": "BTCUSDT",
                                                         "price": 100.0}})
    o = broker.Order(signal_id="sig-1", symbol="BTCUSDT", side="BUY",
                     notional=10.0, asset_type="crypto")
    b.place_order(o)
    check("crypto broker: a $10 buy fills", o.state == broker.FILLED, o.state)
    check("crypto broker: a $10 buy costs exactly $0.06 in fees",
          abs(b.fees_paid - 0.06) < 1e-9, f"fees_paid={b.fees_paid:.8f}")
    check("crypto broker: cash is reduced by notional plus fee",
          abs(b.cash - (100.0 - 10.0 - 0.06)) < 1e-9, f"cash={b.cash:.6f}")

    # A second fill pays its own fee; the fee is not charged once per position.
    o2 = broker.Order(signal_id="sig-2", symbol="BTCUSDT", side="BUY",
                      notional=10.0, asset_type="crypto")
    b.place_order(o2)
    check("crypto broker: a second $10 buy pays its own $0.06",
          abs(b.fees_paid - 0.12) < 1e-9, f"fees_paid={b.fees_paid:.8f}")

    # A SELL pays the fee on the exit notional too.
    before = b.fees_paid
    o3 = broker.Order(signal_id="sig-3", symbol="BTCUSDT", side="SELL",
                      quantity=0.1, asset_type="crypto")
    b.place_order(o3)
    check("crypto broker: an exit pays the fee on its own notional",
          abs((b.fees_paid - before) - 0.006 * 0.1 * 100.0) < 1e-9,
          f"exit fee {b.fees_paid - before:.8f}")


def test_crypto_broker_quote_reads_crypto_prices():
    """
    The crypto quote must read `crypto_prices`, never the equity `prices`
    table — every consumer of that table assumes US sessions.
    """
    conn = _conn()
    _insert_bars(conn, "BTCUSDT", [100.0, 101.0, 102.0])
    b = broker.CryptoSimulatedBroker(conn=conn, cash=100.0)
    q = b.get_quote("BTCUSDT")
    check("crypto broker: the quote comes from crypto_prices",
          q is not None and abs(q["price"] - 102.0) < 1e-9,
          f"price={q['price'] if q else None}")
    check("crypto broker: the quote carries turnover for the risk engine",
          q is not None and q.get("dollar_volume_20") is not None,
          f"dollar_volume_20={q.get('dollar_volume_20') if q else None}")


def test_coinbase_adapter_does_not_transmit():
    """
    `CoinbaseBroker.place_order` builds the specification and leaves it in
    UNKNOWN. No module on this project transmits an order; a test that let this
    adapter reach a terminal state would be testing a different system.
    """
    b = broker.CoinbaseBroker()
    o = broker.Order(signal_id="sig-cb", symbol="BTCUSDT", side="BUY",
                     notional=10.0, asset_type="crypto")
    b.place_order(o)
    check("coinbase adapter: place_order leaves the order in UNKNOWN",
          o.state == broker.UNKNOWN, o.state)
    check("coinbase adapter: the order is not in a terminal state",
          o.state not in broker.TERMINAL, o.state)
    check("coinbase adapter: the note says transmission is an operator step",
          "operator step" in (o.note or ""), o.note)

    # Reads are injected, never imported. An unwired read must raise rather
    # than silently return nothing.
    raised = False
    try:
        b.get_account()
    except NotImplementedError:
        raised = True
    check("coinbase adapter: an unwired read raises rather than returning None",
          raised)


# ---------------------------------------------------------------------------
# Property 5 — crypto floors
# ---------------------------------------------------------------------------

def _crypto_limits(allow_crypto: bool = True) -> dict:
    return {
        "allow_crypto": allow_crypto,
        "allow_options": False,
        "allow_shorting": False,
        "min_price": 5.0,                 # an equity floor that must NOT apply
        "min_market_cap_usd": 1e9,        # an equity floor that must NOT apply
        "min_dollar_volume": 1e6,
        "max_trade_dollars": 100.0,
        "max_position_dollars": 100.0,
        "max_position_percent": 100.0,
        "max_open_positions": 10,
        "allow_fractional_shares": True,
        "crypto": {"min_dollar_volume": 5e6},
    }


def _crypto_sig(action: str = "BUY", notional: float = 10.0) -> sg.Signal:
    return sg.Signal(symbol="BTCUSDT", action=action, strategy="crypto_grid:test",
                     reason="test", asset_type="crypto", session="2024-03-01",
                     notional_value=notional)


def _portfolio() -> dict:
    return {"equity": 100.0, "buying_power": 100.0, "positions": {},
            "daily_pnl": 0.0}


def test_crypto_floors():
    eng = re_.RiskEngine(limits=_crypto_limits(True))
    q = {"symbol": "BTCUSDT", "price": 0.26, "dollar_volume_20": 1e9,
         "market_cap": None}
    r = eng.validate(_crypto_sig(), _portfolio(), q, {})
    check("crypto floors: a $0.26 quote with $1e9 turnover is APPROVED",
          r.approved, "; ".join(r.reasons))

    # The equity floors would reject this quote on both price and market cap.
    # If either leaks into the crypto path, this test fails.
    check("crypto floors: the equity min_price floor is not applied",
          not any("below floor" in x and "price" in x for x in r.reasons),
          "; ".join(r.reasons))
    check("crypto floors: the equity min_market_cap floor is not applied",
          not any("market cap" in x for x in r.reasons), "; ".join(r.reasons))

    eng_off = re_.RiskEngine(limits=_crypto_limits(False))
    r_off = eng_off.validate(_crypto_sig(), _portfolio(), q, {})
    check("crypto floors: allow_crypto False rejects every crypto signal",
          not r_off.approved, "; ".join(r_off.reasons))
    check("crypto floors: the rejection names crypto",
          any("crypto" in x for x in r_off.reasons), "; ".join(r_off.reasons))

    q_none = {"symbol": "BTCUSDT", "price": 0.26, "dollar_volume_20": None,
              "market_cap": None}
    r_none = eng.validate(_crypto_sig(), _portfolio(), q_none, {})
    check("crypto floors: unknown turnover is rejected", not r_none.approved,
          "; ".join(r_none.reasons))
    check("crypto floors: the unknown-turnover rejection says 'liquidity unknown'",
          any("liquidity unknown" in x for x in r_none.reasons),
          "; ".join(r_none.reasons))

    q_thin = {"symbol": "BTCUSDT", "price": 0.26, "dollar_volume_20": 1e6,
              "market_cap": None}
    r_thin = eng.validate(_crypto_sig(), _portfolio(), q_thin, {})
    check("crypto floors: turnover below the 5e6 crypto floor is rejected",
          not r_thin.approved, "; ".join(r_thin.reasons))
    check("crypto floors: the thin-turnover rejection names the crypto floor",
          any("crypto floor" in x for x in r_thin.reasons),
          "; ".join(r_thin.reasons))

    # An equity signal with the same quote must still hit the equity floors —
    # otherwise the crypto branch has replaced the equity one rather than
    # sitting beside it.
    eq = sg.Signal(symbol="XYZ", action="BUY", strategy="test", reason="test",
                   asset_type="equity", session="2024-03-01", notional_value=10.0)
    r_eq = eng.validate(eq, _portfolio(), q, {})
    check("crypto floors: an equity signal still hits the equity floors",
          not r_eq.approved, "; ".join(r_eq.reasons))


# ---------------------------------------------------------------------------
# crypto_orders
# ---------------------------------------------------------------------------

def test_orders_candidates_from_open_grid():
    """
    An open grid produces its resting orders at the prices `simulate()` would
    use: the next level, the take-profit and the stop.
    """
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    cands = co.candidates(conn)
    kinds = {c["kind"] for c in cands}
    check("orders: an open grid produces candidates", len(cands) > 0,
          f"{len(cands)} candidate(s)")
    check("orders: the next grid level is offered", "grid level 2" in kinds,
          ", ".join(sorted(kinds)))
    check("orders: a take-profit is offered", "take-profit" in kinds,
          ", ".join(sorted(kinds)))
    check("orders: a stop is offered", "stop" in kinds, ", ".join(sorted(kinds)))

    f = cf._fund(conn)
    g = json.loads(f["strategy"])
    st = json.loads(conn.execute("SELECT state FROM crypto_fund_open WHERE name=?",
                                 (cf.FUND,)).fetchone()[0])
    base = st["fills"][0][0]
    lvl = base * (1 - g["spacing"] * len(st["fills"]))
    got = [c for c in cands if c["kind"] == "grid level 2"]
    check("orders: the next level price matches the engine's own formula",
          got and abs(got[0]["limit_price"] - lvl) < 1e-9,
          f"{got[0]['limit_price'] if got else None} vs {lvl}")


def test_orders_candidates_forward_only():
    """
    A pair with no open grid whose latest closed bar meets the entry rule
    produces a BUY — but only if that bar closed after the fund opened.
    """
    closes = [100.0] * 30 + [100.0 - 0.5 * k for k in range(1, 11)]
    conn = _conn()
    _insert_bars(conn, "BTCUSDT", closes)
    _listing(conn, "BTCUSDT")
    last_open = T0 + (len(closes) - 1) * HOUR
    cf.open_fund(conn, 100.0, started_ts=last_open + HOUR)
    cands = co.candidates(conn)
    check("orders: no entry is offered from a bar that closed before the fund",
          not any(c["kind"] == "grid entry" for c in cands),
          f"{len(cands)} candidate(s)")

    conn2 = _conn()
    _insert_bars(conn2, "BTCUSDT", closes)
    _listing(conn2, "BTCUSDT")
    cf.open_fund(conn2, 100.0, started_ts=T0)
    cands2 = co.candidates(conn2)
    check("orders: an entry IS offered when the bar closed after the fund",
          any(c["kind"] == "grid entry" for c in cands2),
          f"{len(cands2)} candidate(s)")


def test_orders_route_halted_when_not_stepped():
    """
    A fund not stepped today is a stale book, and the kill switch exists to
    halt on exactly that. `route()` must report halted=True and approve
    nothing.
    """
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    # Backdate last_step so the fund is not reconciled for today.
    conn.execute("UPDATE crypto_fund SET last_step=? WHERE name=?",
                 ("2020-01-01T00:00:00+00:00", cf.FUND))
    conn.commit()
    cands = co.candidates(conn)
    r = co.route(conn, cands)
    check("orders: route() halts when the fund was not stepped today",
          r["halted"] is True, f"halted={r['halted']}")
    check("orders: no order is approved while halted",
          all(not o["approved"] for o in r["orders"]),
          f"{sum(1 for o in r['orders'] if o['approved'])} approved")
    check("orders: every order carries a verdict, approved or not",
          all("approved" in o and "why" in o for o in r["orders"]),
          f"{len(r['orders'])} order(s)")


def test_orders_route_stepped_today_is_not_halted_by_staleness():
    """
    The complement of the test above: a fund stepped today must not be halted
    for staleness. Without this, a `reconciled` flag hardcoded to False would
    pass the previous test and halt every run forever.
    """
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    today = datetime.now(timezone.utc).date().isoformat()
    last = cf._fund(conn)["last_step"]
    check("orders: step() stamps last_step with today's date",
          last[:10] == today, last)
    r = co.route(conn, co.candidates(conn))
    check("orders: a fund stepped today is not halted for staleness",
          r["halted"] is False, f"halted={r['halted']}")


def test_orders_route_uses_buying_power_not_cash():
    """
    The portfolio handed to the risk engine must carry `buying_power`. The
    first version passed `cash`, the sizer read `buying_power`, every order was
    sized to $0.00 and rejected as too small — a wrong key that looked like a
    limit. This test pins the key.
    """
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    r = co.route(conn, co.candidates(conn))
    sized = [o for o in r["orders"] if o["approved"]]
    check("orders: at least one order is approved on a healthy fund",
          len(sized) > 0,
          f"{len(r['orders'])} candidate(s), {len(sized)} approved")
    check("orders: an approved order is sized above the $1 minimum",
          all((o.get("notional") or 0) >= 1.0 or (o.get("quantity") or 0) > 0
              for o in sized),
          "; ".join(f"{o['symbol']} {o.get('notional')}" for o in sized))


def test_orders_write_outputs():
    """The slate is written for a person and for reconciliation."""
    import tempfile
    from pathlib import Path
    closes = [100.0] * 30 + [100.0 - 0.2 * k for k in range(1, 21)]
    conn, sym, _ = _fund_conn(closes=closes)
    cf.step(conn)
    r = co.route(conn, co.candidates(conn))
    with tempfile.TemporaryDirectory() as d:
        txt = Path(d) / "crypto_slate.txt"
        js = Path(d) / "crypto_slate.json"
        co.SLATE_TXT, co.SLATE_JSON = txt, js
        try:
            co.write(r)
            check("orders: the text slate is written", txt.exists())
            check("orders: the json slate is written", js.exists())
            check("orders: the json slate round-trips",
                  json.loads(js.read_text())["session"] == r["session"])
        finally:
            co.SLATE_TXT, co.SLATE_JSON = co.SLATE_TXT, co.SLATE_JSON


# ---------------------------------------------------------------------------
# status / render
# ---------------------------------------------------------------------------

def test_status_and_render():
    conn = _conn()
    s = cf.status(conn)
    check("status: an unopened fund reports exists=False", s["exists"]