"""
Regression tests for crypto_data.py — Phase 12, items 38 and 39.

Every failure mode covered here is SILENT. A Coinbase candle read in Binance's
field order produces bars that look plausible and are wrong on every row; an
in-progress bar stored as if closed is a look-ahead that no downstream check
catches; an impossible bar written to the table only surfaces as a strange
backtest months later. So these tests assert the exact mapping and the exact
rejections rather than "it ran".

No network. `load()` and `_fetch()` are never called — they are the only
functions in the module that touch the wire, and the acceptance criteria for
this task forbid exercising them. Everything tested here is pure or local.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import sqlite3
import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

import crypto_data

PASS = 0
FAIL = 0


def check(name, fn):
    global PASS, FAIL
    try:
        fn()
    except Exception:
        FAIL += 1
        print(f"  FAIL {name}")
        traceback.print_exc()
    else:
        PASS += 1
        print(f"  PASS {name}")


def fresh_conn():
    """
    In-memory database with Row factory, matching what storage.connect gives
    callers. `symbols` is created here because crypto_data.load registers
    tickers there; init() itself only owns crypto_prices.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE symbols (ticker TEXT PRIMARY KEY, "
                 "security_type TEXT)")
    return conn


# A real Coinbase row: [time, low, high, open, close, volume].
# Chosen so that Binance-order reading is detectably different: open != low
# and close != high, and the four values are distinct.
COINBASE_ROW = [1700000000, 99.0, 105.0, 100.0, 104.0, 12.5]


def test_ohlc_field_order():
    o, h, l, c = crypto_data._ohlc(COINBASE_ROW)
    assert (o, h, l, c) == (100.0, 105.0, 99.0, 104.0), (o, h, l, c)


def test_binance_order_would_differ():
    """
    Reading the same row as [time, open, high, low, close] gives
    open=99, high=105, low=100, close=104 — a different bar.

    Whether that wrong bar is also caught by a range check depends entirely on
    the numbers: the swap is visible only when the true low exceeds the true
    open. So the regression pinned here is the mapping itself, not the
    detectability of the error.
    """
    binance = (float(COINBASE_ROW[1]), float(COINBASE_ROW[2]),
               float(COINBASE_ROW[3]), float(COINBASE_ROW[4]))
    correct = crypto_data._ohlc(COINBASE_ROW)
    assert binance != correct


# When is the Binance-order misreading INVISIBLE to a range check?
#
# The swap sets low' = true_open. The check requires low' <= min(open', close'),
# and open' = true_low, so it needs true_open <= true_low. Since true_low <=
# true_open always holds, that is satisfiable ONLY when open == low — a bar
# that opened at its low.
#
# So the range check catches the swap on most bars and is blind to it on
# exactly the bars that opened at their low, which are common. That is the
# case pinned here, and it is why the field mapping needs a regression of its
# own rather than relying on validation to notice.
COINBASE_ROW_SWAP_INVISIBLE = [1700000000, 100.0, 106.0, 100.0, 104.0, 12.5]


def test_binance_order_can_pass_range_check():
    """
    The misreading is not reliably caught by a range check, which is why the
    mapping needs its own regression rather than being covered incidentally.

    Compared as TUPLES, not by passing the same list to _ohlc twice: _ohlc
    reads one fixed field order, so handing it the same row twice necessarily
    returns the same answer and asserts nothing.
    """
    # An ordinary bar: the swap IS caught, so validation helps here.
    ordinary = COINBASE_ROW
    o, h, l, c = (ordinary[1], ordinary[2], ordinary[3], ordinary[4])
    assert not (l <= min(o, c)), "this bar's swap should be detectable"

    # A bar that opened at its low: the swap is invisible.
    row = COINBASE_ROW_SWAP_INVISIBLE
    correct = crypto_data._ohlc(row)
    misread = (row[1], row[2], row[3], row[4])
    o, h, l, c = misread
    assert min(o, h, l, c) > 0
    assert l <= min(o, c) and h >= max(o, c) and h >= l, \
        "a bar opening at its low hides the swap from every range rule"
    # open == low here, so the misread tuple happens to equal the correct one;
    # what matters is that validation cannot distinguish them at all.
    assert crypto_data._valid(row) is True


def test_valid_accepts_well_formed():
    assert crypto_data._valid(COINBASE_ROW) is True


def test_valid_rejects_zero_price():
    row = list(COINBASE_ROW)
    row[3] = 0.0            # open = 0
    assert crypto_data._valid(row) is False


def test_valid_rejects_negative_price():
    row = list(COINBASE_ROW)
    row[1] = -1.0           # low = -1
    assert crypto_data._valid(row) is False


def test_valid_rejects_low_above_open():
    # low=101 > open=100 violates low <= min(open, close).
    row = [1700000000, 101.0, 105.0, 100.0, 104.0, 1.0]
    assert crypto_data._valid(row) is False


def test_valid_rejects_high_below_close():
    # high=103 < close=104 violates high >= max(open, close).
    row = [1700000000, 99.0, 103.0, 100.0, 104.0, 1.0]
    assert crypto_data._valid(row) is False


def test_valid_rejects_high_below_low():
    # high=98 < low=99 violates high >= low.
    row = [1700000000, 99.0, 98.0, 100.0, 104.0, 1.0]
    assert crypto_data._valid(row) is False


def test_valid_returns_false_on_short_row():
    assert crypto_data._valid([1700000000, 99.0]) is False


def test_valid_returns_false_on_non_numeric():
    row = [1700000000, "x", 105.0, 100.0, 104.0, 1.0]
    assert crypto_data._valid(row) is False


def test_interval_seconds():
    assert crypto_data.INTERVAL_SECONDS["1h"] == 3600
    assert crypto_data.INTERVAL_SECONDS["1d"] == 86400
    # Every declared interval must be a positive whole number of seconds.
    for name, secs in crypto_data.INTERVAL_SECONDS.items():
        assert isinstance(secs, int) and secs > 0, (name, secs)


def test_init_creates_table_with_pk():
    conn = fresh_conn()
    crypto_data.init(conn)
    cols = {r["name"]: r for r in conn.execute(
        "PRAGMA table_info(crypto_prices)")}
    assert set(cols) >= {"symbol", "open_time", "interval", "bar_seconds",
                         "open", "high", "low", "close", "volume",
                         "quote_volume", "trades", "source"}
    # PRAGMA table_info returns rows in table order and its `pk` column is the
    # 1-based position within the key, so the key order must be recovered by
    # sorting on `pk` rather than by filtering on truthiness.
    rows = [r for r in conn.execute("PRAGMA table_info(crypto_prices)")
            if r["pk"]]
    pk = [r["name"] for r in sorted(rows, key=lambda r: r["pk"])]
    assert pk == ["symbol", "interval", "open_time"], pk
    conn.close()


def test_bar_seconds_stored_on_row():
    conn = fresh_conn()
    crypto_data.init(conn)
    conn.execute(
        "INSERT INTO crypto_prices (symbol, open_time, interval, bar_seconds, "
        "open, high, low, close, volume, quote_volume, trades, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        ("BTC-USD", 1700000000, "1h", 3600, 100.0, 105.0, 99.0, 104.0,
         12.5, 0.0, 0, "coinbase"))
    conn.commit()
    row = conn.execute(
        "SELECT bar_seconds FROM crypto_prices WHERE symbol=? AND interval=?",
        ("BTC-USD", "1h")).fetchone()
    assert row["bar_seconds"] == 3600
    conn.close()


def test_coverage_one_entry_per_symbol():
    conn = fresh_conn()
    crypto_data.init(conn)
    rows = [
        ("BTC-USD", 1700000000, "1h", 3600, 100.0, 105.0, 99.0, 104.0,
         1.0, 0.0, 0, "coinbase"),
        ("BTC-USD", 1700003600, "1h", 3600, 104.0, 106.0, 103.0, 105.0,
         1.0, 0.0, 0, "coinbase"),
        ("ETH-USD", 1700000000, "1h", 3600, 10.0, 11.0, 9.5, 10.5,
         1.0, 0.0, 0, "coinbase"),
    ]
    conn.executemany(
        "INSERT INTO crypto_prices (symbol, open_time, interval, bar_seconds, "
        "open, high, low, close, volume, quote_volume, trades, source) "
        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    cov = crypto_data.coverage(conn, "1h")
    assert len(cov) == 2, cov
    by_sym = {r["symbol"]: r for r in cov}
    assert by_sym["BTC-USD"]["bars"] == 2
    assert by_sym["ETH-USD"]["bars"] == 1
    assert by_sym["BTC-USD"]["first"] == 1700000000
    assert by_sym["BTC-USD"]["last"] == 1700003600
    conn.close()


def main():
    print("\n  CRYPTO DATA REGRESSION")
    print("  " + "-" * 62)
    check("_ohlc maps Coinbase order to (open, high, low, close)",
          test_ohlc_field_order)
    check("reading the row in Binance order gives a different bar",
          test_binance_order_would_differ)
    check("a Binance-order misreading can still pass the range check",
          test_binance_order_can_pass_range_check)
    check("_valid accepts a well-formed candle", test_valid_accepts_well_formed)
    check("_valid rejects a zero price", test_valid_rejects_zero_price)
    check("_valid rejects a negative price", test_valid_rejects_negative_price)
    check("_valid rejects low above open", test_valid_rejects_low_above_open)
    check("_valid rejects high below close", test_valid_rejects_high_below_close)
    check("_valid rejects high below low", test_valid_rejects_high_below_low)
    check("_valid returns False on a short row", test_valid_returns_false_on_short_row)
    check("_valid returns False on a non-numeric field",
          test_valid_returns_false_on_non_numeric)
    check("INTERVAL_SECONDS maps 1h->3600 and 1d->86400", test_interval_seconds)
    check("init creates crypto_prices with PK (symbol, interval, open_time)",
          test_init_creates_table_with_pk)
    check("bar_seconds is stored on the row", test_bar_seconds_stored_on_row)
    check("coverage returns one entry per symbol with a bar count",
          test_coverage_one_entry_per_symbol)
    print("  " + "-" * 62)
    print(f"  {PASS} passed, {FAIL} failed\n")
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
