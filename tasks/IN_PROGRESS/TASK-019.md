# TASK-019

- component: data
- priority: high
- state: IN_PROGRESS
- branch: ado/task-019
- created: 2026-09-24T03:00:00+00:00
- dependencies: none

## Objective
Create data_providers.py (a provider interface) and finsaber.py (a FINSABER validation-dataset provider and importer), Phase 13 §8-10 and Addendum B §B8/B19.

## Background
FINSABER is an S&P 500 daily price dataset, 2000-2024, including delisted companies, distributed as one CSV (data/price/all_sp500_prices_2000_2024_delisted_include.csv, ~253 MB). It is a SECONDARY VALIDATION dataset: it must never be written into data/market_data.db or replace the primary prices table. It lives in its own SQLite file, data/finsaber.db. The download itself is not part of this task; the importer reads a CSV path it is given.

Expected CSV columns (verify by header, case-insensitive, and fail loudly naming any missing column): date, symbol, open, high, low, close, adjusted_close, volume. Some files name the adjusted column adj_close or "adj close" — accept those as aliases.

The provider interface lets strategies run against either dataset without changing the backtester, and reserves a slot for a future historical INTRADAY provider (B8) that does not exist yet.

## Relevant files
- `data_providers.py`
- `finsaber.py`
- `storage.py`
## Requirements
1. data_providers.py: import runtime first. Define `class DataProvider` with methods `name() -> str`, `daily_bars(tickers: list | None, start: str, end: str) -> pandas.DataFrame` returning columns exactly [ticker, date, open, high, low, close, volume] with date as 'YYYY-MM-DD' strings, `universe(on_date: str) -> list[str]`, and `coverage() -> dict` (keys: name, first_date, last_date, securities, bars).
2. class StockbotProvider(DataProvider)`: wraps an open sqlite3 connection to the primary database; daily_bars reads the `prices` table (columns ticker, date, open, high, low, close, volume); universe returns tickers with a bar on that date.
3. class IntradayProvider(DataProvider)`: abstract placeholder for historical intraday bars with an extra method `intraday_bars(tickers, start, end, interval)`. Its methods raise NotImplementedError with a message saying no historical intraday source is configured. Add `def has_historical_intraday() -> bool` returning False at module level.
4. A registry: `PROVIDERS = {}` and `register(name, factory)` / `get(name, **kw)`.
5. finsaber.py: import runtime first. `DEFAULT_DB = "data/finsaber.db"`. `init(conn)` creates table `finsaber_prices(symbol TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL, adj_close REAL, volume REAL, PRIMARY KEY (symbol, date)) WITHOUT ROWID` and table `finsaber_import(id INTEGER PRIMARY KEY AUTOINCREMENT, source_path TEXT, sha256 TEXT, rows_read INTEGER, rows_written INTEGER, rows_rejected INTEGER, first_date TEXT, last_date TEXT, symbols INTEGER, imported_at TEXT)`.
6. import_csv(conn, path, chunksize=200_000) -> dict`: reads the CSV in chunks with pandas (never the whole file at once), normalises column names, rejects rows with a non-positive close or high < low (counted, not silently dropped), upserts with INSERT OR REPLACE, computes the file's sha256, writes one finsaber_import row, returns a stats dict. Re-importing the same file must not change the row count.
7. class FinsaberProvider(DataProvider)` reading data/finsaber.db (path injectable); daily_bars maps symbol->ticker and uses close (NOT adj_close) for close so it is comparable with the primary table's convention; also expose `adjusted_bars(...)` returning adj_close as close.
8. Register both providers in data_providers.PROVIDERS under "stockbot" and "finsaber" (finsaber.py registers itself on import).
9. CLI for finsaber.py: `--import PATH`, `--db PATH`, `--status` (prints coverage). Refuse with a clear message if PATH does not exist.

## Constraints
1. Create ONLY `data_providers.py` and `finsaber.py`. Modify nothing else.
2. Never open or write data/market_data.db from finsaber.py.
3. No network access; no new dependency.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python -c "import os,tempfile,sqlite3,finsaber,data_providers as dp; d=tempfile.mkdtemp(); p=os.path.join(d,'f.csv'); open(p,'w').write('date,symbol,open,high,low,close,adjusted_close,volume\n2020-01-02,AAA,10,11,9,10.5,10.4,1000\n2020-01-03,AAA,10.5,12,10,11,10.9,1200\n2020-01-03,BBB,5,4,6,5,5,10\n'); c=sqlite3.connect(os.path.join(d,'f.db')); s=finsaber.import_csv(c,p); assert s['rows_written']==2 and s['rows_rejected']==1, s; s2=finsaber.import_csv(c,p); assert c.execute('select count(*) from finsaber_prices').fetchone()[0]==2; fp=finsaber.FinsaberProvider(db_path=os.path.join(d,'f.db')); b=fp.daily_bars(None,'2020-01-01','2020-12-31'); assert list(b.columns)==['ticker','date','open','high','low','close','volume'] and len(b)==2; assert 'finsaber' in dp.PROVIDERS and 'stockbot' in dp.PROVIDERS; assert dp.has_historical_intraday() is False; print('ok')"` prints ok
2. finsaber.py does not contain the string market_data.db.
3. ./run_tests.sh reports ALL PASS.
