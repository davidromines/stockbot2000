12 of 14 pass. Both failures are bugs in the TEST, not in crypto_data.py.

FAILURE 1 — "Binance-order reading ... passes range check"

With COINBASE_ROW = [1700000000, 99.0, 105.0, 100.0, 104.0, 12.5], the
Binance-order reading is open=99, high=105, low=100, close=104. Your second
assertion is:

    assert bl <= min(bo, bc)          # 100 <= min(99, 104) = 99

which is False. So with THESE numbers the swap IS caught by a range check, and
the test asserts it is not.

That is a real and useful observation, but it is not what the test should pin.
Whether the swap happens to be detectable depends entirely on the numbers: it
is caught when the true low exceeds the true open, and missed otherwise. The
regression worth guarding is simply that _ohlc does not read the row in
Binance order.

Delete the second assertion and the "passes range check" clause from the check
name. Keep `assert binance != correct`. Rename the check to something like
"reading the row in Binance order gives a different bar".

If you want to keep the stronger point, add a SECOND row where the swap is
genuinely invisible — one where low < open and high > close both hold after
swapping — and assert _valid() returns True for that wrong reading. That
demonstrates the danger honestly. Optional; the rename alone is enough.

FAILURE 2 — "init creates crypto_prices with PK"

PRAGMA table_info returns rows in TABLE order, and its `pk` column is the
1-based position within the primary key, not a boolean. Your comprehension
filters on truthiness and therefore returns PK columns in table declaration
order — symbol, open_time, interval — while you assert the PK order,
symbol, interval, open_time.

Sort by the pk index instead:

    rows = [r for r in conn.execute("PRAGMA table_info(crypto_prices)") if r["pk"]]
    pk = [r["name"] for r in sorted(rows, key=lambda r: r["pk"])]
    assert pk == ["symbol", "interval", "open_time"], pk

Change only those two tests. Everything else in the file is correct.