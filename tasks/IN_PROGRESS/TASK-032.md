# TASK-032

- component: execution
- priority: high
- state: IN_PROGRESS
- branch: ado/task-032
- created: 2026-09-25T18:00:00+00:00
- dependencies: TASK-031

## Objective
Create crypto_broker.py (Stage K5 part 2): CryptoBroker, a subclass of robinhood_live.LiveBroker that trades crypto through crypto_live.CryptoLive behind the existing broker.BrokerInterface, so crypto orders go through the same ExecutionEngine and RiskEngine as equities; plus its regression test with fakes.

## Background
robinhood_live.LiveBroker(conn, account_number, call=None, calls=None, provider=None, poll_seconds=20.0) implements get_account (portfolio equity, buying power, unsettled funds), get_positions, get_quote, place_order, get_order, cancel_order for EQUITIES. broker.Order has signal_id, symbol, side ("BUY"/"SELL"), notional, quantity, asset_type, client_order_id, broker_order_id, state, filled_quantity, avg_fill_price, note, and order.to(state, note) enforces broker.ALLOWED transitions (CREATED -> ... ; place_order receives an APPROVED order and must move it APPROVED -> SUBMITTING -> SUBMITTED -> PARTIALLY_FILLED/FILLED/CANCELLED/REJECTED, or SUBMITTING -> REJECTED, or SUBMITTING -> UNKNOWN on a transport failure after sending). broker.TERMINAL is the set of final states. crypto_live.CryptoLive(account, call=..., sleep=..., now=..., poll_seconds=...) provides quote(symbol) -> {symbol, bid, ask, mark, price, updated_at, age_s} or None; positions() -> {"BTC-USD": qty}; buy(symbol, usd, client_order_id) and sell(symbol, qty, client_order_id) -> {"state", "order_id", "filled_qty", "avg_price"} (state is a broker state, UNKNOWN when the order id is unreadable) or {"state": REJECTED, "reason"}; place_stop(symbol, qty, stop_price, client_order_id) -> {"state", "order_id"}; cancel(order_id) -> bool; open_orders(symbol=None) -> [{"order_id", "symbol", "side", "type", "state"}]. The risk engine needs quote["price"] > 0 and, for crypto, quote["dollar_volume_20"] (unknown means rejected): compute it from crypto_prices (symbol, open_time, interval, close, volume) as the mean of close * volume over the latest 20 bars with interval '1d' (None if fewer than 5 bars). robinhood_mcp.RobinhoodError is the broker's own refusal (a rejection); any other exception raised while placing is a transport failure after sending (UNKNOWN), never a fill.

## Relevant files
- `crypto_broker.py`
- `tests/regression/test_crypto_broker.py`
- `robinhood_live.py`
- `crypto_live.py`
- `broker.py`
## Requirements
1. class CryptoBroker(robinhood_live.LiveBroker) with __init__(self, conn, account_number, call=None, client=None, poll_seconds=20.0); client defaults to crypto_live.CryptoLive(account_number, call=call or robinhood_mcp.call imported lazily, poll_seconds=poll_seconds); pass call through to LiveBroker so get_account still reads the portfolio.
2. get_quote(symbol) returns the client quote plus "dollar_volume_20" from crypto_prices as in Background plus "source": "robinhood_crypto", or None when the client returns None.
3. get_positions() returns {symbol: {"quantity", "entry", "price", "value"}} from client.positions(), with price from get_quote (falling back to 0.0 when no quote) and entry 0.0 (Robinhood crypto cost basis is not read here).
4. place_order(order) refuses (order.to(REJECTED, note)) any order whose asset_type is not "crypto"; BUY needs order.notional > 0 and calls client.buy; SELL needs order.quantity > 0 and calls client.sell; it moves APPROVED -> SUBMITTING before the call, then SUBMITTED and the final state from the client result, setting broker_order_id, filled_quantity and avg_fill_price; a RobinhoodError raised by the client moves SUBMITTING -> REJECTED; any other exception moves SUBMITTING -> UNKNOWN; a client result with state REJECTED moves SUBMITTING -> REJECTED with its reason; a client result with state UNKNOWN moves SUBMITTING -> UNKNOWN.
5. place_stop(symbol, quantity, stop_price, client_order_id) delegates to client.place_stop and returns its result; cancel_order(order_id) delegates to client.cancel; get_order(order_id) returns {"state", "filled_quantity", "avg_fill_price", "broker_order_id"} using client._poll with poll_seconds 0 semantics is NOT required: call get_crypto_orders through the client's call function directly and map state with crypto_live._map_state.
6. open_stops(symbol=None) returns the client's open orders whose type is "stop_loss".

## Constraints
1. Create ONLY crypto_broker.py and tests/regression/test_crypto_broker.py. Do not modify robinhood_live.py, crypto_live.py or broker.py (they are given for reference).
2. No network in tests: build CryptoBroker with a fake client object (methods returning canned results) and a fake call for LiveBroker; use sqlite3.connect(":memory:") with crypto_data.init(conn) and a few 1d bars; never import robinhood_mcp in the test.
3. Keep crypto_broker.py under 200 lines and the test under 200 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_broker.py exits 0.
2. The test checks: an equity order is REJECTED without calling the client; a BUY fills to FILLED with broker_order_id, filled_quantity and avg_fill_price from the client; a client REJECTED result ends REJECTED; a client UNKNOWN result ends UNKNOWN; a RuntimeError raised by the client ends UNKNOWN (never FILLED); get_quote carries dollar_volume_20 from the bars and returns None when the client has no quote; get_positions values a position at the quote price; place_stop delegates.
3. At least 9 lines beginning with `  PASS`.
4. ./run_tests.sh reports ALL PASS.
