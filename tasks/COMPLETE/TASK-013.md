# TASK-013

- component: crypto
- priority: high
- state: COMPLETE
- branch: ado/task-013
- created: 2026-09-23T06:50:22+00:00
- dependencies: none

## Objective
Create tests/regression/test_crypto_data.py covering crypto_data.py, following the style of the existing files in tests/regression/.

## Background
Phase 12 items 38 and 39. `crypto_data.py` loads crypto OHLCV from Coinbase
into its own `crypto_prices` table.

Three things must not regress, each because the failure is silent rather than
loud:

1. **The OHLC field order.** A Coinbase candle is
   `[time, low, high, open, close, volume]` — low and high come BEFORE open and
   close. Binance's is `[time, open, high, low, close, ...]`. Reading Coinbase
   rows in Binance's order swaps low with open and high with close on EVERY
   row, and the result still passes a naive "is high the biggest number" check.
   `_ohlc(k)` owns this mapping.

2. **The in-progress bar is excluded.** The newest candle is the bar currently
   forming. Storing it puts a partial close in the table, which is a
   look-ahead — the same reason the equity loader skips today's bar.

3. **Impossible bars are rejected at write time.** `_valid` requires all four
   prices positive and `low <= min(open, close)`, `high >= max(open, close)`,
   `high >= low`. The equity loader learned this from yfinance returning
   negative adjusted prices.

## Relevant files
- `tests/regression/test_crypto_data.py`
- `crypto_data.py`
## Requirements
1. Import `runtime` as the very first import, before pandas or numpy.
2. Use an in-memory sqlite3 database with `conn.row_factory = sqlite3.Row`.
3. **Make NO network calls.** Do not call `load()` or `_fetch()`. Test the pure
4. Follow the existing style in `tests/regression/`: module docstring naming
5. Test `_ohlc` returns open, high, low, close in THAT order from a Coinbase
6. Test that reading that same row in Binance order would give a DIFFERENT
7. Test `_valid` accepts a well-formed candle.
8. Test `_valid` rejects: a zero price, a negative price, a candle whose low
9. Test `_valid` returns False rather than raising on a malformed row: a short
10. Test `INTERVAL_SECONDS` maps "1h" to 3600 and "1d" to 86400, and that
11. Test `init(conn)` creates `crypto_prices` with a primary key over
12. Test that `bar_seconds` is stored on the row, since a consumer must never
13. Test `coverage()` returns one entry per symbol with a bar count, using

## Constraints
1. Create ONLY `tests/regression/test_crypto_data.py`. Modify nothing else.
2. NO network access of any kind. No new dependency. Standard library only.
3. Do not use pytest.
4. Do not open the real database.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_data.py` exits 0
2. It prints at least 14 lines beginning with `  PASS`.
3. The test file contains no call to `crypto_data.load` or `crypto_data._fetch`.
4. ./run_tests.sh` reports ALL PASS with 35 files.
