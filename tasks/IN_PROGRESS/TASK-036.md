# TASK-036

- component: tests
- priority: high
- state: IN_PROGRESS
- branch: ado/task-036
- created: 2026-09-26T04:30:00+00:00
- dependencies: none

## Objective
Create tests/regression/test_live_paths.py (Addendum D N2): regression tests for five live-trading paths that are coded but untested — stale quote, quote outside market hours, partial fill recorded at the filled quantity, rejected buy writes no OPEN, and a failed stop sell keeps the position.

## Background
robinhood_live.RobinhoodQuotes(conn, call=fake, max_age_seconds=300).get(symbol) calls call("get_equity_quotes", {"symbols": [symbol]}) whose response shape is {"data": {"results": [{"quote": {"symbol": "AAA", "last_trade_price": "50.00", "venue_last_trade_time": "<ISO UTC time>"}}]}}; it returns None when the quote is older than max_age_seconds or when quotes.market_open() is False, else a dict with price. quotes.market_open(now=None) uses the current time; in the test, replace robinhood_live.qt.market_open (the module attribute the quote class calls) with a lambda returning True or False, and restore it afterwards. It also calls quotes._db_fields(conn, symbol, "robinhood", call=...) for liquidity fields: in the test replace robinhood_live.qt._db_fields with a lambda returning {"dollar_volume_20": 5e7, "market_cap": 5e9}. slot_trader._record_trade(conn, mode, slot, holder, symbol, action, res, reason, plan=None, atr=None) writes a slot_trades row ONLY when res["status"] is "filled" or "partially_filled" and res["order"].filled_quantity > 0, using order.filled_quantity as quantity and order.avg_fill_price as price; otherwise it writes nothing and returns False. slot_trader.open_positions(conn, mode) returns {slot_id: position} from OPEN rows not followed by a CLOSE. broker.Order(signal_id, symbol, side, notional=None, quantity=None) has fields state, filled_quantity, avg_fill_price. slot_trader.init(conn) creates the tables on an in-memory database. slot_trader._exit(conn, engine, mode, slot, pos, reason, reconciled, results) executes a SELL through engine.execute(signal, reconciled=...) and then calls _record_trade with the result; use a fake engine object with attribute session = "2026-09-25" and a method execute(sig, reconciled=None) that returns a canned result dict {"status": ..., "signal_id": sig.signal_id, "order": order, "reasons": [...]}. A position dict for _exit needs keys symbol, quantity, strategy_key, version (build it from open_positions after recording an OPEN). The holder dict for _record_trade has strategy_key and version.

## Relevant files
- `tests/regression/test_live_paths.py`
- `robinhood_live.py`
- `slot_trader.py`
- `broker.py`
## Requirements
1. Stale quote: with market_open patched True, a quote whose venue_last_trade_time is 10 minutes old returns None, and one 30 seconds old returns a price of 50.0.
2. Outside hours: with market_open patched False, a fresh quote returns None.
3. Partial fill: an OPEN recorded from a result with status "partially_filled", an order of notional 20 with filled_quantity 0.25 and avg_fill_price 40.0 creates one slot_trades row with quantity 0.25 and price 40.0, and open_positions shows that quantity.
4. Rejected buy: a result with status "rejected" and an order with filled_quantity 0 writes no slot_trades row and open_positions stays empty.
5. Failed stop sell: after an OPEN of 0.5 shares, calling _exit with a fake engine whose execute returns status "failed" (filled_quantity 0) leaves the position open with quantity 0.5 and appends a result entry with status "failed"; a second _exit whose engine returns "filled" with filled_quantity 0.5 closes it.

## Constraints
1. Create ONLY tests/regression/test_live_paths.py. Do not modify robinhood_live.py, slot_trader.py or broker.py (given for reference).
2. No network, never import robinhood_mcp directly, never open data/market_data.db; use sqlite3.connect(":memory:") with row_factory sqlite3.Row.
3. Keep the file under 200 lines. Restore every patched attribute in a finally block.
4. Import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_live_paths.py exits 0.
2. At least 9 lines beginning with `  PASS`, covering all five requirements.
3. The test file does not contain the string market_data.db.
4. ./run_tests.sh reports ALL PASS.
