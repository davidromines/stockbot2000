# TASK-031

- component: execution
- priority: high
- state: TODO
- branch: ado/task-031
- created: 2026-09-25T17:20:00+00:00
- dependencies: none

## Objective
Create crypto_live.py (Stage K5 part 1): a thin, defensive client for Robinhood crypto orders, quotes, positions and currency-pair increments, used later by the slot trader; plus its regression test with a fake call function. It places nothing on import and nothing in tests.

## Background
All calls go through a function call(tool, args) -> parsed JSON dict (robinhood_mcp.call in production; a fake in tests). Every tool takes rhs_account_number (a numeric string). Helpers to reuse from robinhood_live (import robinhood_live as rl): rl.find(obj, *keys) returns the first value under any key searching nested dicts/lists; rl.rows(obj, *keys) returns the list under the first matching key (searching nested dicts); rl.num(v) converts to float or None; rl.ref_id(client_order_id) returns a UUIDv5 string. Broker states come from broker.py (import broker as bk): bk.SUBMITTED, bk.PARTIALLY_FILLED, bk.FILLED, bk.CANCELLED, bk.REJECTED, and bk.UNKNOWN if it exists else the string "UNKNOWN". Crypto order states map: queued, confirmed, unconfirmed, pending -> SUBMITTED; partially_filled -> PARTIALLY_FILLED; filled -> FILLED; canceled, cancelled, voided -> CANCELLED; rejected, failed -> REJECTED; anything else -> UNKNOWN. Tool shapes: get_crypto_quotes {"symbols": [...], "rhs_account_number": a} -> {"data": {"results": [{"symbol": "BTCUSD", "bid_price": "83401.74", "ask_price": "84983.68", "mark_price": "84192.71", "updated_at": "2026-09-25T01:00:27.034-04:00"}]}}. get_crypto_positions {"rhs_account_number": a, "cursor"?} -> {"data": {"results": [{"currency": {"code": "BTC"}, "quantity": "0.0002", "quantity_transferable": "0.0002"}], "next": null or cursor}}; the sellable amount is quantity_transferable. get_currency_pairs {"limit": 700} -> {"results": [{"symbol": "BTC-USD", "min_order_size": "0.000001", "min_order_quantity_increment": "0.00000001", "tradability": "tradable"}]}. place_crypto_order {"rhs_account_number", "symbol", "side": "buy"|"sell", "type": "market"|"stop_loss", "dollar_amount"? , "quantity"?, "stop_price"?, "time_in_force": "gtc", "ref_id"} -> a dict containing the order id under "id" or "order_id" (search nested) and a "state". get_crypto_orders {"rhs_account_number", "order_id"} -> {"data": {"results": [{"id", "state", "cumulative_quantity", "average_price", "side", "type"}]}}; with {"state_group": "open"} lists open orders. cancel_crypto_order {"rhs_account_number", "order_id"}. Quote symbols come back unhyphenated: "BTCUSD" -> "BTC-USD".

## Relevant files
- `crypto_live.py`
- `tests/regression/test_crypto_live.py`
## Requirements
1. class CryptoLive(account, call=None, sleep=time.sleep, now=None, poll_seconds=20.0, poll_every=2.0, max_quote_age=120.0); call defaults to robinhood_mcp.call imported lazily inside __init__ only when call is None; now is a function returning an aware UTC datetime (default datetime.now(timezone.utc)); raises ValueError on an empty account.
2. quote(symbol) returns {symbol, bid, ask, mark, price, updated_at, age_s} where price is mark when > 0 else (bid + ask) / 2, or None when the symbol is absent, bid or ask <= 0, ask < bid, updated_at is missing or unparseable, or age_s > max_quote_age.
3. increments() returns {symbol: {"qty_increment": float, "min_qty": float, "tradable": bool}} from get_currency_pairs (cached on the instance after the first call); round_qty(symbol, qty) rounds DOWN to the pair's qty_increment using decimal.Decimal and returns a string, or None if the result is below min_qty or the pair is unknown.
4. positions() returns {"BTC-USD": quantity_transferable float, ...} following the next cursor until it is empty, skipping rows with zero or unreadable quantity.
5. buy(symbol, usd, client_order_id) places a market buy with dollar_amount formatted to 2 decimals, time_in_force "gtc", ref_id rl.ref_id(client_order_id), then polls; sell(symbol, qty, client_order_id) places a market sell with quantity = round_qty(...) and returns {"state": bk.REJECTED, "reason": ...} without calling place when round_qty is None; place_stop(symbol, qty, stop_price, client_order_id) places a sell of type stop_loss with quantity = round_qty(...), stop_price formatted to 2 decimals when >= 1 else 6 significant decimals, time_in_force "gtc", and does NOT poll (returns the state from the placement response mapped); cancel(order_id) calls cancel_crypto_order and returns True unless it raises.
6. _poll(order_id) calls get_crypto_orders with that order_id every poll_every seconds (using the injected sleep) until the mapped state is FILLED, CANCELLED or REJECTED or poll_seconds elapse, and returns {"state", "order_id", "filled_qty", "avg_price"}; a placement response with no readable order id returns state UNKNOWN (never FILLED); an exception raised by call after placement propagates unchanged.
7. open_orders(symbol=None) returns the list of open orders (state_group "open"), filtered by symbol when given, each as {"order_id", "symbol", "side", "type", "state"}.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else.
2. No network in tests: a fake call records every (tool, args) and returns canned responses; sleep is a no-op; never import robinhood_mcp in the test.
3. Keep crypto_live.py under 250 lines and the test under 200 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_crypto_live.py exits 0.
2. The test checks: quote maps BTCUSD to BTC-USD with price = mark; a stale quote (age > max_quote_age) returns None; round_qty rounds 0.123456789 BTC down to 0.12345678 and returns None below min_qty; buy sends dollar_amount "20.00", type market, the ref_id of the client id, and returns FILLED with filled_qty and avg_price after a queued-then-filled poll; a placement without an order id returns UNKNOWN; sell below min_qty places nothing; place_stop sends type stop_loss with gtc and does not poll; positions follows a next cursor across two pages; open_orders filters by symbol.
3. At least 10 lines beginning with `  PASS`.
4. ./run_tests.sh reports ALL PASS.
