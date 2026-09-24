# Data Dictionary

Generated from the live SQLite schema by `data_dictionary.py`. Do not edit by hand — regenerate with:

```
python data_dictionary.py --counts
```

Tables: 66

## Summary

| Table | Rows | Description |
| --- | --- | --- |
| `allocations` | not counted | capital allocation runs (allocation.py), one row per scheme per run |
| `archive_snapshots` | not counted | one row per Internet Archive capture |
| `benchmarks` | not counted | the null surface cells |
| `claude_fund` | not counted | the discretionary paper fund's positions, each with a written thesis |
| `claude_fund_meta` | not counted | the discretionary fund's capital and status |
| `compute_log` | not counted | per-stage runtime of daily.sh, tagged by compute-priority tier |
| `crypto_benchmarks` | not counted | per-symbol crypto null surface cells |
| `crypto_fund` | not counted | the crypto paper fund |
| `crypto_fund_equity` | not counted | daily marks of the crypto paper fund |
| `crypto_fund_open` | not counted | open grid positions of the crypto paper fund |
| `crypto_fund_trades` | not counted | closed crypto fund trades: gross, fees, net, null |
| `crypto_listings` | not counted | crypto pair listing status, recorded at load time |
| `crypto_prices` | not counted | crypto OHLCV bars, PK (symbol, interval, open_time) |
| `daily_fundamentals` | not counted | fundamentals lagged to the first session they were public |
| `degradation` | not counted | backtest-to-forward degradation per strategy, mean per-trade units |
| `delistings` | not counted | delisted listings with exact dates (Alpha Vantage) |
| `edgar_companies` | not counted | SEC company registry rows behind edgar_filers |
| `edgar_events` | not counted | 8-K item codes as events |
| `edgar_filers` | not counted | point-in-time registry of SEC annual filers, 1993-now |
| `evaluations` | not counted | every scored evaluation; the trial counter is append-only |
| `experiment_registry` | not counted | pre-registered experiments, versioned, hash-checked |
| `experiment_trades` | not counted | trades behind rows in the experiments ledger |
| `experiments` | not counted | the experiment ledger: one row per test, ranked by money |
| `features` | not counted | the 20 technical indicators per (ticker, date) |
| `fills` | not counted | broker fills recorded by the execution engine |
| `freshness_log` | not counted | every freshness-gate verdict, with lag and missing references |
| `fundamentals` | not counted | ~40 derived value/quality metrics per filing |
| `historical_listings` | not counted | Internet Archive replays of the symbol directory |
| `holdout_log` | not counted | sealed-holdout evaluations and refusals; one evaluation per strategy |
| `ingest_state` | not counted | per-ticker backfill progress; makes the load resumable |
| `lab_runs` | not counted | search run metadata |
| `league_state` | not counted | append-only lifecycle transition log; state is derived, never stored |
| `league_strategies` | not counted | strategy identity and immutable versions (definition_hash) |
| `llm_calls` | not counted | ADO delegated model calls: tokens and estimated cost |
| `oos_folds` | not counted | walk-forward fold metadata behind oos_predictions |
| `oos_predictions` | not counted | walk-forward out-of-sample predictions |
| `orders` | not counted | orders built by the execution engine and their state-machine status |
| `pair_fund_equity` | not counted | daily marks of pair funds |
| `pair_funds` | not counted | bull/bear ETF switching funds |
| `paper_equity` | not counted | daily equity marks of paper funds |
| `paper_positions` | not counted | open positions of the paper funds |
| `paper_runs` | not counted | simulated funds; genome stored inline as JSON |
| `paper_trades` | not counted | closed paper trades |
| `picks` | not counted | daily book recommendations and actual fills |
| `prices` | not counted | daily OHLCV bars, PK (ticker, date), 1962 to present |
| `promotion_decisions` | not counted | promotion-policy verdicts per strategy |
| `promotions` | not counted | validation ladder decisions |
| `random_control` | not counted | persistent random-genome control distribution, fingerprinted |
| `risk_events` | not counted | risk-engine rejections and kill-switch events |
| `risk_metrics` | not counted | monthly beta and idiosyncratic volatility |
| `roster_changes` | not counted | live-roster plan and demotion history |
| `scoreboard_snapshots` | not counted | scoreboard output per run, with the formula that produced it |
| `sec_facts` | not counted | raw XBRL facts per filing |
| `sec_filings` | not counted | one row per SEC filing, with accepted time, prevrpt and first_tradeable |
| `signals` | not counted | content-addressed trade signals submitted to execution |
| `strategies` | not counted | evolved genomes |
| `strategy_ancestry` | not counted | origin classification per strategy (seeded / independent) |
| `strategy_library` | not counted | research library: every strategy idea with provenance and evidence |
| `symbols` | not counted | every listing, tagged by security_type, with data_quality flags |
| `synthetic_companies` | not counted | generated delisting price paths for stress tests |
| `system_events` | not counted | system-level events (restarts, mode changes) |
| `trial_ledger` | not counted | append-only cumulative trial counter for multiple-testing correction |
| `value_fund` | not counted | the long-horizon Value Fund |
| `value_fund_equity` | not counted | daily marks of the Value Fund |
| `value_fund_positions` | not counted | open Value Fund positions with thesis and entry score |
| `value_fund_trades` | not counted | closed Value Fund trades |

## `allocations`

capital allocation runs (allocation.py), one row per scheme per run

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `scheme` | TEXT | yes |  |
| `strategy_key` | TEXT | yes |  |
| `dollars` | REAL | yes |  |
| `share` | REAL | yes |  |
| `capital_usd` | REAL | yes |  |
| `note` | TEXT | no |  |

## `archive_snapshots`

one row per Internet Archive capture

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `key` | TEXT | yes | 1 |
| `snapshot_date` | TEXT | yes |  |
| `listings` | INTEGER | yes |  |
| `fetched_at` | TEXT | yes |  |

## `benchmarks`

the null surface cells

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `window_start` | TEXT | yes | 1 |
| `window_end` | TEXT | yes | 2 |
| `horizon_days` | INTEGER | yes | 3 |
| `price_lo` | REAL | yes | 4 |
| `price_hi` | REAL | yes | 5 |
| `min_price` | REAL | yes | 6 |
| `min_dollar_volume` | REAL | yes | 7 |
| `median_price` | REAL | no |  |
| `n_obs` | INTEGER | yes |  |
| `gross_pct` | REAL | yes |  |
| `cost_pct` | REAL | yes |  |
| `net_pct` | REAL | yes |  |
| `computed_at` | TEXT | yes |  |

## `claude_fund`

the discretionary paper fund's positions, each with a written thesis

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `opened_on` | TEXT | yes | 2 |
| `usd` | REAL | yes |  |
| `entry_price` | REAL | yes |  |
| `shares` | REAL | yes |  |
| `stop_price` | REAL | no |  |
| `thesis` | TEXT | yes |  |
| `evidence` | TEXT | no |  |
| `status` | TEXT | yes |  |
| `closed_on` | TEXT | no |  |
| `exit_price` | REAL | no |  |
| `exit_reason` | TEXT | no |  |

## `claude_fund_meta`

the discretionary fund's capital and status

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `key` | TEXT | yes | 1 |
| `value` | TEXT | yes |  |

## `compute_log`

per-stage runtime of daily.sh, tagged by compute-priority tier

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `stage` | TEXT | yes |  |
| `tier` | INTEGER | yes |  |
| `tier_name` | TEXT | yes |  |
| `seconds` | REAL | yes |  |
| `ok` | INTEGER | yes |  |

## `crypto_benchmarks`

per-symbol crypto null surface cells

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `symbol` | TEXT | yes | 1 |
| `interval` | TEXT | yes | 2 |
| `hold_bars` | INTEGER | yes | 3 |
| `mean_pct` | REAL | no |  |
| `median_pct` | REAL | no |  |
| `p25` | REAL | no |  |
| `p75` | REAL | no |  |
| `stdev_pct` | REAL | no |  |
| `n_draws` | INTEGER | no |  |
| `computed_at` | TEXT | yes |  |

## `crypto_fund`

the crypto paper fund

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | no | 1 |
| `capital_usd` | REAL | yes |  |
| `started_ts` | INTEGER | yes |  |
| `interval` | TEXT | yes |  |
| `strategy` | TEXT | yes |  |
| `library_ref` | TEXT | no |  |
| `symbols` | TEXT | yes |  |
| `status` | TEXT | yes |  |
| `last_step` | TEXT | no |  |
| `created_at` | TEXT | yes |  |

## `crypto_fund_equity`

daily marks of the crypto paper fund

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `equity_usd` | REAL | yes |  |
| `realised_usd` | REAL | no |  |
| `unrealised_usd` | REAL | no |  |
| `open_positions` | INTEGER | no |  |

## `crypto_fund_open`

open grid positions of the crypto paper fund

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `symbol` | TEXT | yes | 2 |
| `entry_ts` | INTEGER | yes |  |
| `state` | TEXT | yes |  |

## `crypto_fund_trades`

closed crypto fund trades: gross, fees, net, null

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `symbol` | TEXT | yes | 2 |
| `entry_ts` | INTEGER | yes | 3 |
| `exit_ts` | INTEGER | yes |  |
| `reason` | TEXT | yes |  |
| `levels` | INTEGER | no |  |
| `deployed_usd` | REAL | no |  |
| `gross_usd` | REAL | no |  |
| `fees_usd` | REAL | no |  |
| `net_usd` | REAL | no |  |
| `ret_pct` | REAL | no |  |
| `null_pct` | REAL | no |  |

## `crypto_listings`

crypto pair listing status, recorded at load time

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `symbol` | TEXT | no | 1 |
| `status` | TEXT | yes |  |
| `trading_disabled` | INTEGER | yes |  |
| `first_seen` | TEXT | yes |  |
| `last_seen` | TEXT | yes |  |

## `crypto_prices`

crypto OHLCV bars, PK (symbol, interval, open_time)

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `symbol` | TEXT | yes | 1 |
| `open_time` | INTEGER | yes | 3 |
| `interval` | TEXT | yes | 2 |
| `bar_seconds` | INTEGER | yes |  |
| `open` | REAL | no |  |
| `high` | REAL | no |  |
| `low` | REAL | no |  |
| `close` | REAL | no |  |
| `volume` | REAL | no |  |
| `quote_volume` | REAL | no |  |
| `trades` | INTEGER | no |  |
| `source` | TEXT | no |  |

## `daily_fundamentals`

fundamentals lagged to the first session they were public

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `has_fundamentals` | INTEGER | yes |  |
| `days_since_filing` | INTEGER | no |  |
| `piotroski_f` | REAL | no |  |
| `book_to_market` | REAL | no |  |
| `gross_profitability` | REAL | no |  |
| `chs_distress` | REAL | no |  |
| `asset_growth` | REAL | no |  |
| `accruals` | REAL | no |  |
| `roa` | REAL | no |  |
| `earnings_yield` | REAL | no |  |
| `net_share_issuance` | REAL | no |  |
| `debt_to_equity` | REAL | no |  |
| `cash_to_assets` | REAL | no |  |
| `altman_z` | REAL | no |  |

## `degradation`

backtest-to-forward degradation per strategy, mean per-trade units

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `strategy_key` | TEXT | yes |  |
| `version` | INTEGER | no |  |
| `linked_strategy` | TEXT | no |  |
| `link_method` | TEXT | yes |  |
| `backtest_return` | REAL | no |  |
| `validation_return` | REAL | no |  |
| `paper_return` | REAL | no |  |
| `live_return` | REAL | no |  |
| `paper_vs_backtest` | REAL | no |  |
| `n_marks` | INTEGER | no |  |
| `provisional` | INTEGER | yes |  |
| `note` | TEXT | no |  |

## `delistings`

delisted listings with exact dates (Alpha Vantage)

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `symbol` | TEXT | yes | 1 |
| `name` | TEXT | no |  |
| `exchange` | TEXT | no |  |
| `asset_type` | TEXT | no |  |
| `ipo_date` | TEXT | no |  |
| `delisting_date` | TEXT | yes | 2 |
| `have_prices` | INTEGER | yes |  |
| `source` | TEXT | yes |  |
| `fetched_at` | TEXT | yes |  |

## `edgar_companies`

SEC company registry rows behind edgar_filers

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `cik` | INTEGER | no | 1 |
| `company_name` | TEXT | yes |  |
| `ticker` | TEXT | no |  |
| `first_filed` | TEXT | yes |  |
| `last_filed` | TEXT | yes |  |
| `n_annual` | INTEGER | yes |  |
| `still_filing` | INTEGER | yes |  |

## `edgar_events`

8-K item codes as events

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `adsh` | TEXT | yes | 1 |
| `cik` | INTEGER | yes |  |
| `ticker` | TEXT | no |  |
| `form` | TEXT | yes |  |
| `item` | TEXT | yes | 2 |
| `filed` | TEXT | yes |  |
| `accepted` | TEXT | yes |  |

## `edgar_filers`

point-in-time registry of SEC annual filers, 1993-now

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `cik` | INTEGER | yes | 1 |
| `year` | INTEGER | yes | 2 |
| `quarter` | INTEGER | yes | 3 |
| `company_name` | TEXT | yes |  |
| `form_type` | TEXT | yes | 4 |
| `filed_date` | TEXT | yes |  |

## `evaluations`

every scored evaluation; the trial counter is append-only

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `strategy_id` | TEXT | yes | 1 |
| `window_start` | TEXT | yes | 2 |
| `window_end` | TEXT | no |  |
| `trial_index` | INTEGER | yes |  |
| `fitness` | REAL | yes |  |
| `net_pnl_usd` | REAL | yes |  |
| `gross_pnl_usd` | REAL | no |  |
| `costs_usd` | REAL | no |  |
| `sharpe` | REAL | no |  |
| `max_drawdown` | REAL | no |  |
| `n_trades` | INTEGER | no |  |
| `win_rate` | REAL | no |  |
| `verdict` | TEXT | no |  |
| `excess_pnl_usd` | REAL | no |  |
| `benchmark_pnl_usd` | REAL | no |  |

## `experiment_registry`

pre-registered experiments, versioned, hash-checked

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `experiment_id` | TEXT | yes | 1 |
| `version` | INTEGER | yes | 2 |
| `status` | TEXT | yes |  |
| `hypothesis` | TEXT | yes |  |
| `researcher` | TEXT | yes |  |
| `created_at` | TEXT | yes |  |
| `registered_at` | TEXT | no |  |
| `completed_at` | TEXT | no |  |
| `spec` | TEXT | yes |  |
| `spec_hash` | TEXT | yes |  |
| `results` | TEXT | no |  |
| `conclusion` | TEXT | no |  |
| `supersedes` | INTEGER | no |  |

## `experiment_trades`

trades behind rows in the experiments ledger

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `experiment_id` | TEXT | yes | 1 |
| `ticker` | TEXT | yes | 2 |
| `entry_date` | TEXT | yes | 3 |
| `exit_date` | TEXT | no |  |
| `entry_price` | REAL | no |  |
| `exit_price` | REAL | no |  |
| `shares` | REAL | no |  |
| `gross_pnl_usd` | REAL | no |  |
| `costs_usd` | REAL | no |  |
| `net_pnl_usd` | REAL | no |  |
| `pnl_pct` | REAL | no |  |
| `exit_reason` | TEXT | no |  |

## `experiments`

the experiment ledger: one row per test, ranked by money

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | TEXT | yes | 1 |
| `name` | TEXT | yes |  |
| `kind` | TEXT | yes |  |
| `config` | TEXT | yes |  |
| `period_start` | TEXT | no |  |
| `period_end` | TEXT | no |  |
| `n_trades` | INTEGER | yes |  |
| `capital_usd` | REAL | no |  |
| `net_pnl_usd` | REAL | no |  |
| `net_pnl_pct` | REAL | no |  |
| `gross_pnl_usd` | REAL | no |  |
| `costs_usd` | REAL | no |  |
| `win_rate_pct` | REAL | no |  |
| `max_drawdown_pct` | REAL | no |  |
| `avg_days_held` | REAL | no |  |
| `notes` | TEXT | no |  |
| `created_at` | TEXT | yes |  |

## `features`

the 20 technical indicators per (ticker, date)

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `sma_50` | REAL | no |  |
| `sma_200` | REAL | no |  |
| `rsi_14` | REAL | no |  |
| `roc_10` | REAL | no |  |
| `adx_14` | REAL | no |  |
| `macd` | REAL | no |  |
| `macd_signal` | REAL | no |  |
| `macd_hist` | REAL | no |  |
| `bb_pct` | REAL | no |  |
| `vol_ratio` | REAL | no |  |
| `price_above_sma50` | REAL | no |  |
| `price_above_sma200` | REAL | no |  |
| `golden_cross` | REAL | no |  |
| `atr_14` | REAL | no |  |
| `stoch_k` | REAL | no |  |
| `stoch_d` | REAL | no |  |
| `obv_rising` | REAL | no |  |
| `cci_20` | REAL | no |  |
| `willr_14` | REAL | no |  |
| `chaikin_osc` | REAL | no |  |
| `dollar_volume_20` | REAL | no |  |
| `pct_of_52w_high` | REAL | no |  |
| `pct_off_52w_low` | REAL | no |  |
| `drawdown_200` | REAL | no |  |
| `log_dollar_volume` | REAL | no |  |

## `fills`

broker fills recorded by the execution engine

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `client_order_id` | TEXT | yes |  |
| `at` | TEXT | yes |  |
| `quantity` | REAL | yes |  |
| `price` | REAL | yes |  |
| `state` | TEXT | yes |  |

## `freshness_log`

every freshness-gate verdict, with lag and missing references

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `checked_at` | TEXT | yes | 1 |
| `expected_latest_date` | TEXT | no |  |
| `actual_latest_date` | TEXT | no |  |
| `lag_days` | INTEGER | no |  |
| `lag_sessions` | INTEGER | no |  |
| `missing_symbols` | INTEGER | yes |  |
| `ok` | INTEGER | yes |  |
| `reason` | TEXT | yes |  |

## `fundamentals`

~40 derived value/quality metrics per filing

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `adsh` | TEXT | yes | 3 |
| `filed` | TEXT | yes | 2 |
| `period` | TEXT | no |  |
| `form` | TEXT | no |  |
| `market_cap` | REAL | no |  |
| `book_to_market` | REAL | no |  |
| `earnings_yield` | REAL | no |  |
| `sales_to_price` | REAL | no |  |
| `fcf_yield` | REAL | no |  |
| `ebit_to_ev` | REAL | no |  |
| `ev_to_ebitda` | REAL | no |  |
| `ev_to_sales` | REAL | no |  |
| `roa` | REAL | no |  |
| `roe` | REAL | no |  |
| `roic` | REAL | no |  |
| `gross_profitability` | REAL | no |  |
| `gross_margin` | REAL | no |  |
| `operating_margin` | REAL | no |  |
| `net_margin` | REAL | no |  |
| `cash_roa` | REAL | no |  |
| `accruals` | REAL | no |  |
| `net_operating_assets` | REAL | no |  |
| `earnings_quality` | REAL | no |  |
| `asset_growth` | REAL | no |  |
| `revenue_growth` | REAL | no |  |
| `earnings_growth` | REAL | no |  |
| `book_growth` | REAL | no |  |
| `net_share_issuance` | REAL | no |  |
| `debt_to_equity` | REAL | no |  |
| `debt_to_ebitda` | REAL | no |  |
| `current_ratio` | REAL | no |  |
| `quick_ratio` | REAL | no |  |
| `interest_coverage` | REAL | no |  |
| `cash_to_assets` | REAL | no |  |
| `asset_turnover` | REAL | no |  |
| `inventory_turnover` | REAL | no |  |
| `ebitda` | REAL | no |  |
| `piotroski_f` | REAL | no |  |
| `altman_z` | REAL | no |  |
| `ohlson_o` | REAL | no |  |
| `chs_distress` | REAL | no |  |

## `historical_listings`

Internet Archive replays of the symbol directory

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `snapshot_date` | TEXT | yes | 1 |
| `ticker` | TEXT | yes | 2 |
| `name` | TEXT | no |  |
| `security_type` | TEXT | no |  |
| `exchange` | TEXT | no |  |

## `holdout_log`

sealed-holdout evaluations and refusals; one evaluation per strategy

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `strategy_id` | TEXT | yes | 1 |
| `attempt` | INTEGER | yes | 2 |
| `at` | TEXT | yes |  |
| `truth_version` | TEXT | no |  |
| `permitted` | INTEGER | yes |  |
| `reason` | TEXT | yes |  |
| `results` | TEXT | no |  |

## `ingest_state`

per-ticker backfill progress; makes the load resumable

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `first_date` | TEXT | no |  |
| `last_date` | TEXT | no |  |
| `row_count` | INTEGER | yes |  |
| `status` | TEXT | yes |  |
| `attempts` | INTEGER | yes |  |
| `last_error` | TEXT | no |  |
| `updated_at` | TEXT | yes |  |

## `lab_runs`

search run metadata

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `run_id` | TEXT | yes | 1 |
| `started_at` | TEXT | yes |  |
| `finished_at` | TEXT | no |  |
| `generations` | INTEGER | no |  |
| `population` | INTEGER | no |  |
| `evaluated` | INTEGER | yes |  |
| `window_start` | TEXT | no |  |
| `window_end` | TEXT | no |  |
| `config` | TEXT | no |  |
| `notes` | TEXT | no |  |

## `league_state`

append-only lifecycle transition log; state is derived, never stored

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `strategy_key` | TEXT | yes |  |
| `version` | INTEGER | yes |  |
| `at` | TEXT | yes |  |
| `from_state` | TEXT | no |  |
| `to_state` | TEXT | yes |  |
| `reason` | TEXT | yes |  |
| `actor` | TEXT | no |  |

## `league_strategies`

strategy identity and immutable versions (definition_hash)

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `strategy_key` | TEXT | yes | 1 |
| `version` | INTEGER | yes | 2 |
| `name` | TEXT | yes |  |
| `family` | TEXT | no |  |
| `author` | TEXT | no |  |
| `created_at` | TEXT | yes |  |
| `parent_key` | TEXT | no |  |
| `ancestry` | TEXT | no |  |
| `hypothesis` | TEXT | no |  |
| `universe` | TEXT | no |  |
| `entry_rule` | TEXT | no |  |
| `exit_rule` | TEXT | no |  |
| `position_sizing` | TEXT | no |  |
| `holding_period` | TEXT | no |  |
| `required_data` | TEXT | no |  |
| `parameters` | TEXT | no |  |
| `definition_hash` | TEXT | yes |  |
| `source_kind` | TEXT | no |  |
| `source_ref` | TEXT | no |  |
| `supersedes` | INTEGER | no |  |

## `llm_calls`

ADO delegated model calls: tokens and estimated cost

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `task_id` | TEXT | no |  |
| `purpose` | TEXT | yes |  |
| `provider` | TEXT | yes |  |
| `model` | TEXT | yes |  |
| `prompt_tokens` | INTEGER | yes |  |
| `completion_tokens` | INTEGER | yes |  |
| `cost_usd` | REAL | yes |  |
| `latency_s` | REAL | yes |  |
| `ok` | INTEGER | yes |  |

## `oos_folds`

walk-forward fold metadata behind oos_predictions

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `fold` | TEXT | yes | 1 |
| `train_start` | TEXT | yes |  |
| `train_end` | TEXT | yes |  |
| `test_start` | TEXT | yes |  |
| `test_end` | TEXT | yes |  |
| `n` | INTEGER | yes |  |
| `auc` | REAL | no |  |
| `computed_at` | TEXT | yes |  |

## `oos_predictions`

walk-forward out-of-sample predictions

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `fold` | TEXT | yes |  |
| `score` | REAL | yes |  |
| `label` | INTEGER | yes |  |

## `orders`

orders built by the execution engine and their state-machine status

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `client_order_id` | TEXT | yes | 1 |
| `signal_id` | TEXT | yes |  |
| `created_at` | TEXT | yes |  |
| `session` | TEXT | yes |  |
| `symbol` | TEXT | yes |  |
| `side` | TEXT | yes |  |
| `asset_type` | TEXT | yes |  |
| `notional` | REAL | no |  |
| `quantity` | REAL | no |  |
| `state` | TEXT | yes |  |
| `broker_order_id` | TEXT | no |  |
| `filled_quantity` | REAL | yes |  |
| `avg_fill_price` | REAL | no |  |
| `mode` | TEXT | yes |  |
| `note` | TEXT | no |  |

## `pair_fund_equity`

daily marks of pair funds

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `equity_usd` | REAL | yes |  |
| `held` | TEXT | no |  |
| `switches` | INTEGER | yes |  |

## `pair_funds`

bull/bear ETF switching funds

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `label` | TEXT | yes |  |
| `bull` | TEXT | yes |  |
| `bear` | TEXT | yes |  |
| `signal` | TEXT | yes |  |
| `method` | TEXT | yes |  |
| `param` | INTEGER | yes |  |
| `min_hold` | INTEGER | yes |  |
| `capital_usd` | REAL | yes |  |
| `started_on` | TEXT | yes |  |
| `status` | TEXT | yes |  |
| `search_note` | TEXT | no |  |

## `paper_equity`

daily equity marks of paper funds

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `run_id` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `cash_usd` | REAL | yes |  |
| `positions_usd` | REAL | yes |  |
| `equity_usd` | REAL | yes |  |
| `open_positions` | INTEGER | yes |  |

## `paper_positions`

open positions of the paper funds

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `run_id` | TEXT | yes | 1 |
| `ticker` | TEXT | yes | 2 |
| `entry_date` | TEXT | yes |  |
| `entry_price` | REAL | yes |  |
| `shares` | REAL | yes |  |
| `stop_price` | REAL | no |  |
| `days_held` | INTEGER | yes |  |

## `paper_runs`

simulated funds; genome stored inline as JSON

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `run_id` | TEXT | yes | 1 |
| `name` | TEXT | yes |  |
| `strategy` | TEXT | yes |  |
| `capital_usd` | REAL | yes |  |
| `cash_usd` | REAL | yes |  |
| `started_on` | TEXT | yes |  |
| `last_step_on` | TEXT | no |  |
| `status` | TEXT | yes |  |
| `created_at` | TEXT | yes |  |
| `last_review` | TEXT | no |  |
| `label` | TEXT | no |  |
| `family` | TEXT | no |  |

## `paper_trades`

closed paper trades

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `run_id` | TEXT | yes | 1 |
| `ticker` | TEXT | yes | 2 |
| `entry_date` | TEXT | yes | 3 |
| `exit_date` | TEXT | yes |  |
| `entry_price` | REAL | no |  |
| `exit_price` | REAL | no |  |
| `shares` | REAL | no |  |
| `gross_pnl_usd` | REAL | no |  |
| `costs_usd` | REAL | no |  |
| `net_pnl_usd` | REAL | no |  |
| `pnl_pct` | REAL | no |  |
| `exit_reason` | TEXT | no |  |

## `picks`

daily book recommendations and actual fills

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `pick_date` | TEXT | yes | 1 |
| `ticker` | TEXT | yes | 2 |
| `source` | TEXT | yes | 3 |
| `rank` | INTEGER | no |  |
| `price` | REAL | yes |  |
| `stop_price` | REAL | no |  |
| `hold_days` | INTEGER | no |  |
| `rationale` | TEXT | no |  |
| `status` | TEXT | yes |  |
| `exit_date` | TEXT | no |  |
| `exit_price` | REAL | no |  |
| `exit_reason` | TEXT | no |  |
| `entry_date` | TEXT | no |  |
| `shares` | REAL | no |  |

## `prices`

daily OHLCV bars, PK (ticker, date), 1962 to present

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `open` | REAL | no |  |
| `high` | REAL | no |  |
| `low` | REAL | no |  |
| `close` | REAL | no |  |
| `volume` | INTEGER | no |  |
| `source` | TEXT | yes |  |

## `promotion_decisions`

promotion-policy verdicts per strategy

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `strategy_key` | TEXT | no |  |
| `version` | INTEGER | no |  |
| `decision` | TEXT | yes |  |
| `readiness_ok` | INTEGER | yes |  |
| `eligible_ok` | INTEGER | yes |  |
| `blockers` | TEXT | yes |  |
| `evidence` | TEXT | no |  |
| `actor` | TEXT | no |  |

## `promotions`

validation ladder decisions

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `strategy_id` | TEXT | yes | 1 |
| `stage` | TEXT | yes | 2 |
| `decision` | TEXT | yes |  |
| `evidence` | TEXT | no |  |
| `decided_at` | TEXT | yes |  |

## `random_control`

persistent random-genome control distribution, fingerprinted

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `fingerprint` | TEXT | yes |  |
| `window` | TEXT | yes |  |
| `genome` | TEXT | no |  |
| `n_trades` | INTEGER | no |  |
| `n_signals` | INTEGER | no |  |
| `entries_capped` | INTEGER | no |  |
| `net_pnl_usd` | REAL | no |  |
| `excess_pnl_usd` | REAL | no |  |
| `sharpe` | REAL | no |  |
| `max_drawdown` | REAL | no |  |
| `win_rate` | REAL | no |  |
| `turnover` | REAL | no |  |
| `passed_gate` | INTEGER | yes |  |

## `risk_events`

risk-engine rejections and kill-switch events

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `signal_id` | TEXT | no |  |
| `symbol` | TEXT | no |  |
| `decision` | TEXT | yes |  |
| `reasons` | TEXT | yes |  |

## `risk_metrics`

monthly beta and idiosyncratic volatility

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `beta` | REAL | no |  |
| `ivol` | REAL | no |  |

## `roster_changes`

live-roster plan and demotion history

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `strategy_key` | TEXT | yes |  |
| `action` | TEXT | yes |  |
| `reason` | TEXT | yes |  |
| `dollars` | REAL | no |  |
| `applied` | INTEGER | yes |  |

## `scoreboard_snapshots`

scoreboard output per run, with the formula that produced it

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `formula` | TEXT | yes |  |
| `strategy_key` | TEXT | yes |  |
| `version` | INTEGER | no |  |
| `rank` | INTEGER | no |  |
| `score` | REAL | no |  |
| `rankable` | INTEGER | yes |  |
| `n_marks` | INTEGER | no |  |
| `metrics` | TEXT | yes |  |

## `sec_facts`

raw XBRL facts per filing

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `adsh` | TEXT | yes | 1 |
| `tag` | TEXT | yes | 2 |
| `ddate` | TEXT | yes | 3 |
| `qtrs` | INTEGER | yes | 4 |
| `value` | REAL | yes |  |

## `sec_filings`

one row per SEC filing, with accepted time, prevrpt and first_tradeable

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `adsh` | TEXT | yes | 1 |
| `cik` | INTEGER | yes |  |
| `name` | TEXT | no |  |
| `sic` | TEXT | no |  |
| `form` | TEXT | yes |  |
| `period` | TEXT | no |  |
| `fy` | TEXT | no |  |
| `fp` | TEXT | no |  |
| `filed` | TEXT | yes |  |
| `ticker` | TEXT | no |  |
| `accepted` | TEXT | no |  |
| `prevrpt` | INTEGER | no |  |
| `detail` | INTEGER | no |  |
| `first_tradeable` | TEXT | no |  |
| `ticker_raw` | TEXT | no |  |

## `signals`

content-addressed trade signals submitted to execution

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `signal_id` | TEXT | yes | 1 |
| `created_at` | TEXT | yes |  |
| `session` | TEXT | yes |  |
| `symbol` | TEXT | yes |  |
| `asset_type` | TEXT | yes |  |
| `action` | TEXT | yes |  |
| `quantity` | REAL | no |  |
| `notional_value` | REAL | no |  |
| `confidence` | REAL | yes |  |
| `expected_edge` | REAL | yes |  |
| `strategy` | TEXT | yes |  |
| `reason` | TEXT | yes |  |
| `expiration` | TEXT | no |  |
| `payload` | TEXT | yes |  |

## `strategies`

evolved genomes

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | TEXT | yes | 1 |
| `parent_id` | TEXT | no |  |
| `run_id` | TEXT | yes |  |
| `generation` | INTEGER | yes |  |
| `origin` | TEXT | yes |  |
| `genome` | TEXT | yes |  |
| `complexity` | INTEGER | yes |  |
| `entry_desc` | TEXT | no |  |
| `exit_desc` | TEXT | no |  |
| `status` | TEXT | yes |  |
| `created_at` | TEXT | yes |  |

## `strategy_ancestry`

origin classification per strategy (seeded / independent)

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `strategy_id` | TEXT | yes | 1 |
| `seed_origin` | TEXT | yes |  |
| `seed_name` | TEXT | no |  |
| `evidence` | TEXT | yes |  |
| `generation` | INTEGER | no |  |
| `parent_ids` | TEXT | no |  |
| `classified_at` | TEXT | yes |  |

## `strategy_library`

research library: every strategy idea with provenance and evidence

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `entry_id` | TEXT | no | 1 |
| `name` | TEXT | yes |  |
| `family` | TEXT | yes |  |
| `original_author` | TEXT | no |  |
| `source` | TEXT | no |  |
| `publication` | TEXT | no |  |
| `original_hypothesis` | TEXT | yes |  |
| `original_universe` | TEXT | no |  |
| `original_period` | TEXT | no |  |
| `original_metrics` | TEXT | no |  |
| `required_data` | TEXT | no |  |
| `interpretation` | TEXT | no |  |
| `implementation` | TEXT | no |  |
| `known_biases` | TEXT | yes |  |
| `faithfulness` | TEXT | no |  |
| `limitations` | TEXT | yes |  |
| `results` | TEXT | no |  |
| `validation_status` | TEXT | yes |  |
| `status_reason` | TEXT | no |  |
| `measured_at` | TEXT | no |  |
| `created_at` | TEXT | yes |  |

## `symbols`

every listing, tagged by security_type, with data_quality flags

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `ticker` | TEXT | yes | 1 |
| `name` | TEXT | no |  |
| `exchange` | TEXT | no |  |
| `first_seen` | TEXT | yes |  |
| `last_seen` | TEXT | yes |  |
| `is_active` | INTEGER | yes |  |
| `security_type` | TEXT | no |  |
| `data_quality` | TEXT | no |  |

## `synthetic_companies`

generated delisting price paths for stress tests

`WITHOUT ROWID`

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `symbol` | TEXT | yes | 1 |
| `member` | INTEGER | yes | 2 |
| `archetype` | TEXT | yes |  |
| `seed` | INTEGER | yes |  |
| `start_date` | TEXT | yes |  |
| `end_date` | TEXT | yes |  |
| `n_days` | INTEGER | yes |  |
| `start_price` | REAL | yes |  |
| `exchange` | TEXT | no |  |

## `system_events`

system-level events (restarts, mode changes)

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `at` | TEXT | yes |  |
| `kind` | TEXT | yes |  |
| `detail` | TEXT | yes |  |
| `severity` | TEXT | yes |  |

## `trial_ledger`

append-only cumulative trial counter for multiple-testing correction

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `at` | TEXT | yes | 1 |
| `evaluations` | INTEGER | yes |  |
| `promotions` | INTEGER | yes |  |
| `backtests` | INTEGER | yes |  |
| `sweeps` | INTEGER | yes |  |
| `total_trials` | INTEGER | yes |  |
| `unique_structures` | INTEGER | no |  |
| `note` | TEXT | no |  |

## `value_fund`

the long-horizon Value Fund

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | no | 1 |
| `capital_usd` | REAL | yes |  |
| `cash_usd` | REAL | yes |  |
| `started_on` | TEXT | yes |  |
| `last_review` | TEXT | no |  |
| `last_mark` | TEXT | no |  |
| `weighting` | TEXT | yes |  |
| `status` | TEXT | yes |  |
| `created_at` | TEXT | yes |  |

## `value_fund_equity`

daily marks of the Value Fund

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `date` | TEXT | yes | 2 |
| `cash_usd` | REAL | no |  |
| `positions_usd` | REAL | no |  |
| `equity_usd` | REAL | no |  |
| `n_positions` | INTEGER | no |  |

## `value_fund_positions`

open Value Fund positions with thesis and entry score

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `name` | TEXT | yes | 1 |
| `ticker` | TEXT | yes | 2 |
| `opened_on` | TEXT | yes |  |
| `entry_price` | REAL | yes |  |
| `shares` | REAL | yes |  |
| `industry` | TEXT | no |  |
| `thesis` | TEXT | yes |  |
| `score_at_entry` | REAL | no |  |

## `value_fund_trades`

closed Value Fund trades

| Column | Type | Not null | PK |
| --- | --- | --- | --- |
| `id` | INTEGER | no | 1 |
| `name` | TEXT | yes |  |
| `ticker` | TEXT | yes |  |
| `opened_on` | TEXT | no |  |
| `closed_on` | TEXT | no |  |
| `entry_price` | REAL | no |  |
| `exit_price` | REAL | no |  |
| `shares` | REAL | no |  |
| `net_pnl_usd` | REAL | no |  |
| `pnl_pct` | REAL | no |  |
| `exit_reason` | TEXT | yes |  |
| `thesis` | TEXT | no |  |
| `score_at_entry` | REAL | no |  |
| `score_at_exit` | REAL | no |  |
