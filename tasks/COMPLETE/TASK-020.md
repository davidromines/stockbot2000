# TASK-020

- component: data
- priority: high
- state: COMPLETE
- branch: ado/task-020
- created: 2026-09-24T04:00:00+00:00
- dependencies: TASK-019

## Objective
Create dataset_compare.py: the cross-dataset validation layer (Phase 13 §8, §11, §29; step H7) comparing the primary database with the FINSABER validation dataset, running a strategy on both, and assigning survivorship tags.

## Background
data_providers.py defines DataProvider with daily_bars(tickers, start, end) returning a DataFrame with columns [ticker, date, open, high, low, close, volume] (date as 'YYYY-MM-DD' strings), universe(on_date) and coverage(). StockbotProvider(conn) wraps the primary database; finsaber.FinsaberProvider(db_path=...) wraps data/finsaber.db. Discrepancies between datasets must never silently disappear (Addendum B §B19): every comparison is reported, counted and stored.

features.compute_features_for_ticker(df) takes one ticker's OHLCV (columns ticker, date, open, high, low, close, volume) and returns it with all feature columns added (sma_50, sma_200, rsi_14, roc_10, ... dollar_volume_20), or an EMPTY DataFrame if the ticker has fewer than 210 rows. simulator.Panel(df, exit_prices=ex) builds a backtest panel from a frame that has ticker, date, open, close and feature columns, where ex has columns ticker, date, close, open; simulator.simulate(genome, panel, cost_model, position_size_usd, max_entries=None) returns a dict with net_pnl_usd, gross_pnl_usd, costs_usd, n_trades, win_rate, pnl_series (numpy array of per-trade net P&L). costs.CostModel(cfg) builds the cost model from a config dict (an empty dict {} gives defaults).

Survivorship tags (spec §11): SURVIVORSHIP_SAFE, SURVIVORSHIP_ADJUSTED, SURVIVORSHIP_LIMITED, UNKNOWN.

## Relevant files
- `dataset_compare.py`
- `data_providers.py`
- `finsaber.py`
- `features.py`
- `simulator.py`
- `costs.py`
## Requirements
1. Import runtime first. Store nothing in the primary database tables other than the two new tables below; create them with `init(conn)`.
2. compare(primary, secondary, start, end, tickers=None, price_tol=0.01) -> dict` taking two DataProvider objects. Report keys: datasets (names), date_range, securities_primary, securities_secondary, securities_both, only_in_primary (count and up to 50 examples), only_in_secondary (count and up to 50 examples — these are candidate delisted names the primary lacks), bars_primary, bars_secondary, missing_bars_in_primary (dates the secondary has for a common ticker that the primary lacks), missing_bars_in_secondary, duplicate_bars_primary, duplicate_bars_secondary, price_discrepancies (count of common (ticker,date) where abs(close_p/close_s - 1) > price_tol), volume_discrepancies (count where volumes differ by more than 5%), worst_price_discrepancies (up to 20 rows: ticker, date, close_p, close_s, ratio), coverage_by_year ({year: {primary: n_securities, secondary: n_securities, both: n}}), coverage_by_security (up to 200 rows for tickers in both: ticker, bars_primary, bars_secondary, first/last date each). A likely corporate-action mismatch is a ratio near a split factor (2, 3, 4, 5, 10, 1/2, 1/3, ...): count those separately as corporate_action_candidates.
3. provider_panel(provider, tickers, start, end)` -> simulator.Panel or None: fetch bars from 300 calendar days before start through end plus 120 days, compute features per ticker with features.compute_features_for_ticker, keep rows with date between start and end for the panel frame, and pass all fetched bars as exit_prices.
4. cross_validate(primary, secondary, genome, start, end, tickers, cfg=None, size=20.0, max_entries=5000) -> dict`: run the same genome on both providers over the SAME tickers (the intersection of what each provider has) and report: net_primary, net_secondary, return_difference_usd, trades_primary, trades_secondary, trade_count_difference, win_rate_primary, win_rate_secondary, win_rate_difference, max_drawdown_primary, max_drawdown_secondary (max drawdown of the cumulative per-trade net P&L, in dollars), drawdown_difference, sharpe_primary, sharpe_secondary (mean/std of per-trade net P&L times sqrt(trades), 0 if undefined), sharpe_difference, securities_primary, securities_secondary, security_coverage_difference, and data_confidence: 1.0 minus min(1, abs(net_primary - net_secondary) / max(abs(net_primary), abs(net_secondary), 1.0)), rounded to 3 places.
5. survivorship_status(cross: dict | None, haircut_applied: bool = False) -> str`: UNKNOWN if cross is None; SURVIVORSHIP_SAFE if the secondary dataset includes delisted names (cross['secondary_includes_delisted'] is True) and net_secondary > 0 and data_confidence >= 0.5; SURVIVORSHIP_ADJUSTED if haircut_applied is True; otherwise SURVIVORSHIP_LIMITED. cross_validate must set secondary_includes_delisted from `getattr(secondary, "includes_delisted", False)`.
6. init(conn)` creates tables `dataset_comparisons(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, primary_name TEXT, secondary_name TEXT, start TEXT, end TEXT, report TEXT)` and `cross_validations(id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, strategy_key TEXT, version INTEGER, start TEXT, end TEXT, report TEXT, survivorship_status TEXT, data_confidence REAL)`; `store_comparison(conn, report)` and `store_cross_validation(conn, key, version, report, status)` insert JSON reports.
7. CLI: `--compare --start --end` (primary from load_config's database path, secondary FinsaberProvider on data/finsaber.db; if data/finsaber.db does not exist print "FINSABER not imported yet — run finsaber.py --import PATH" and exit 0).

## Constraints
1. Create ONLY `dataset_compare.py`. Modify nothing else.
2. No network access, no new dependency, no pytest.
3. Never write to the primary database's prices, features or fundamentals tables.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python -c "import numpy as np,pandas as pd,sqlite3,dataset_compare as dc
2. ./run_tests.sh reports ALL PASS.
