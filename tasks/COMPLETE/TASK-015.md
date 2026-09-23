# TASK-015

- component: tests
- priority: high
- state: COMPLETE
- branch: ado/task-015
- created: 2026-09-23T15:48:49+00:00
- dependencies: none

## Objective
Create tests/regression/test_crypto_fund.py covering crypto_fund.py, crypto_orders.py, the crypto broker adapters in broker.py, and the crypto floors in risk_engine.py.

## Background
Phase 12 items 40 and 42. Five properties must not regress; each failure is
silent rather than loud.

1. **One engine.** `crypto_fund.step()` produces trades by calling
   `crypto_grid.simulate()`, the same function the backtest uses. Replaying
   the fund from the very first bar must produce the same closed trades as
   `simulate()` called directly with `close_at_end=False`.
2. **Forward only.** Only bars whose open_time is at or after the fund's
   `started_ts` may signal an entry. A trade entered before the fund existed
   would make the "forward" record a backtest relabelled.
3. **Idempotent step.** Calling `step()` twice records the same closed trades
   once — they are keyed by (name, symbol, entry_ts).
4. **Fees on each fill's own notional.** `CryptoSimulatedBroker` charges
   `CRYPTO_TAKER_FEE` x notional per fill: a $10 buy costs exactly $0.06.
5. **Crypto floors.** For asset_type "crypto", `RiskEngine` skips the equity
   `min_price` and `min_market_cap_usd` floors and applies
   `L["crypto"]["min_dollar_volume"]`. Unknown turnover is still a rejection.
   `allow_crypto: false` rejects every crypto signal.

## Relevant files
- `tests/regression/test_crypto_fund.py`
- `crypto_fund.py`
- `crypto_orders.py`
- `crypto_grid.py`
- `broker.py`
- `risk_engine.py`
## Requirements
1. Import `runtime` first. Use an in-memory sqlite3 db with
2. Existing style: module docstring, `check(name, cond, detail)` helper
3. Build fixtures by hand: call `crypto_data.init(conn)`, then insert a
4. Open the fund with `crypto_fund.open_fund(conn, 100.0, started_ts=...)
5. Test property 2 using a SEPARATE in-memory db: open with `started_ts` at
6. Test property 3: call `step()` twice and assert the trade count is
7. Test `mark()` writes one row per date and that equity equals
8. Test property 4 with `broker.CryptoSimulatedBroker(conn=None, cash=100.0,
9. Test `CoinbaseBroker().place_order(order)` leaves the order in state
10. Test property 5 by constructing `risk_engine.RiskEngine(limits={...})
11. a $0.26 quote with turnover 1e9 is APPROVED when allow_crypto is True
12. the same with allow_crypto False is rejected;
13. turnover None is rejected with "liquidity unknown" in a reason;
14. turnover 1e6 (below the 5e6 crypto floor) is rejected.
15. Test that `crypto_orders.route()` returns `halted=True` when the fund's

## Constraints
1. Create ONLY `tests/regression/test_crypto_fund.py`. Modify nothing else.
2. No network, no new dependency, no pytest, do not open the real database.
3. If a property cannot be exercised in memory, test what can and say so in

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_fund.py
2. At least 16 lines beginning with `  PASS`.
3. The file contains no reference to `market_data.db`.
4. ./run_tests.sh` reports ALL PASS with 36 files.
