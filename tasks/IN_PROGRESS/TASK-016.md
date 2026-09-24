# TASK-016

- component: docs
- priority: high
- state: IN_PROGRESS
- branch: ado/task-016
- created: 2026-09-23T17:30:00+00:00
- dependencies: none

## Objective
Create data_dictionary.py, which generates docs/DATA_DICTIONARY.md from the live SQLite schema (Phase 6 section 29).

## Background
Phase 6 section 29 requires a DATA_DICTIONARY.md. Hand-written schema
documentation goes stale the day a column is added, so the dictionary is
GENERATED from `sqlite_master` and `PRAGMA table_info`, and regenerated on
demand. Descriptions for known tables come from a dict in the module; a table
with no description is listed as "undocumented" rather than omitted, so a new
table is visible as a gap instead of invisible.

Table descriptions to include in a module-level dict `DESCRIPTIONS`
(table -> one line):
prices: daily OHLCV bars, PK (ticker, date), 1962 to present
features: the 20 technical indicators per (ticker, date)
symbols: every listing, tagged by security_type, with data_quality flags
ingest_state: per-ticker backfill progress; makes the load resumable
risk_metrics: monthly beta and idiosyncratic volatility
sec_filings: one row per SEC filing, with accepted time, prevrpt and first_tradeable
sec_facts: raw XBRL facts per filing
fundamentals: ~40 derived value/quality metrics per filing
daily_fundamentals: fundamentals lagged to the first session they were public
edgar_filers: point-in-time registry of SEC annual filers, 1993-now
edgar_events: 8-K item codes as events
delistings: delisted listings with exact dates (Alpha Vantage)
historical_listings: Internet Archive replays of the symbol directory
archive_snapshots: one row per Internet Archive capture
strategies: evolved genomes
evaluations: every scored evaluation; the trial counter is append-only
promotions: validation ladder decisions
lab_runs: search run metadata
benchmarks: the null surface cells
oos_predictions: walk-forward out-of-sample predictions
paper_runs: simulated funds; genome stored inline as JSON
paper_equity: daily equity marks of paper funds
paper_trades: closed paper trades
pair_funds: bull/bear ETF switching funds
pair_fund_equity: daily marks of pair funds
picks: daily book recommendations and actual fills
experiment_registry: pre-registered experiments, versioned, hash-checked
value_fund: the long-horizon Value Fund
crypto_prices: crypto OHLCV bars, PK (symbol, interval, open_time)
crypto_fund: the crypto paper fund

## Relevant files
- `data_dictionary.py`
- `storage.py`
- `universe.py`
## Requirements
1. Import `runtime` first (the project rule), then argparse, sqlite3, pathlib.
2. Provide `describe(conn) -> list[dict]`, one dict per table: name, description (or None), columns (list of dicts: name, type, notnull, pk), without_rowid (bool, from the CREATE sql).
3. Provide `render(tables, counts: dict | None) -> str` producing markdown: a title, a generated-on line, a summary table of all tables, then one section per table with a column table.
4. Tables are listed alphabetically. Skip sqlite_ internal tables.
5. Row counts are OPTIONAL via `--counts` because COUNT(*) over 35M rows is slow; without it the count column says "not counted".
6. A table missing from DESCRIPTIONS renders its description as `**undocumented**`.
7. CLI: `python data_dictionary.py [--db PATH] [--out docs/DATA_DICTIONARY.md] [--counts]`; the default db comes from `load_config()["database"]["market_data_path"]` in universe.py.
8. Open the database READ-ONLY with a `file:...?mode=ro` URI. The generator must never write to it.

## Constraints
1. Create ONLY `data_dictionary.py`. Modify nothing else.
2. No new dependency.
3. Do not generate docs/DATA_DICTIONARY.md yourself; the reviewer runs the script.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python -c "import sqlite3,data_dictionary as d; c=sqlite3.connect(':memory:'); c.execute('CREATE TABLE prices (ticker TEXT, date TEXT, PRIMARY KEY (ticker,date)) WITHOUT ROWID'); c.execute('CREATE TABLE zz_new (x INTEGER)'); t=d.describe(c); s=d.render(t, None); assert 'undocumented' in s and 'prices' in s and t[0]['without_rowid'] is True; print('ok')"` prints ok
2. The file contains `mode=ro`.
3. ./run_tests.sh` reports ALL PASS.
