# TASK-041

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-041
- created: 2026-09-26T07:30:00+00:00
- dependencies: TASK-040

## Objective
Create factory_families_l.py (Stage L3): register strategy families rebuilt from published signals that survived publication (JKP post-publication t > 3), exactly as specified, and record which published signal each existing or new family encodes; plus its regression test.

## Background
Same registration mechanism as factory_families_o.py (given for reference): import strategy_factory as sf and call sf.family(name, league, rationale, grid, build, data=("features",), available=True, missing=None, combo=False) at import time; helpers sf.col, sf.k, sf.gt, sf.lt, sf.and_, sf.rank, sf.pct, sf.G(entry, exit_=None, stop, hold). Define lag(a, n) = {"op": "lag", "args": [a], "n": int(n)} locally. The panel has a daily `close` column. JKP momentum is formation over t-12..t-1 months skipping the most recent month, rebalanced monthly: in trading days, 12-1 = the 231-session return ending 21 sessions ago = lag(pct(col("close"), 231), 21); 9-1 = lag(pct(col("close"), 168), 21). NEW FAMILIES, name / league / grid / entry / exit / stop / hold:
1. momentum_12_1 / momentum / {"q": [0.8, 0.9], "stop": [3.0, 4.0]} / sf.gt(sf.rank(lag(sf.pct(sf.col("close"), 231), 21)), sf.k(p["q"])) / none / p["stop"] / 21.
2. momentum_9_1 / momentum / {"q": [0.8, 0.9], "stop": [3.0, 4.0]} / sf.gt(sf.rank(lag(sf.pct(sf.col("close"), 168), 21)), sf.k(p["q"])) / none / p["stop"] / 21.
3. fcf_to_price / fundamental / {"q": [0.8]} / sf.gt(sf.rank(sf.col("fcf_to_price")), sf.k(p["q"])) / none / 3.0 / 60; data ("features", "daily_fundamentals", "free cash flow"), available=False, missing="free cash flow (operating cash flow minus capex) is not on the daily panel; value_metrics.fcf_yield is operating cash flow / market cap (JKP ocf_me), not free cash flow".
4. earnings_surprise / event / {"q": [0.8]} / sf.gt(sf.rank(sf.col("sue")), sf.k(p["q"])) / none / 3.0 / 60; data ("features", "quarterly EPS"), available=False, missing="standardized unexpected earnings is computed by pead.py per filing but not projected onto the daily panel".
Rationales name the paper and the survivorship-free post-publication evidence, e.g. momentum_12_1: "Jegadeesh & Titman (1993) 12-1 month momentum; JKP post-publication long-tercile excess +0.45%/month (t 3.25, 1994-2025, dead companies included)"; momentum_9_1: "9-1 month momentum; JKP post-publication +0.48%/month (t 3.43)"; fcf_to_price: "Free cash flow to price (Lakonishok, Shleifer & Vishny 1994); JKP post-publication +0.52%/month (t 4.43)"; earnings_surprise: "Standardized earnings surprise (Foster, Olsen & Shevlin 1984); JKP post-publication +0.35%/month (t 3.43)". PUBLISHED maps family name -> list of Research Library entry ids it encodes: momentum_12_1 -> ["published:jkp:ret_12_1"]; momentum_9_1 -> ["published:jkp:ret_9_1"]; fcf_to_price -> ["published:jkp:fcf_me"]; earnings_surprise -> ["published:jkp:niq_su"]; and the EXISTING families: quality_piotroski -> ["published:jkp:f_score"]; earnings_yield -> ["published:jkp:ni_me"]; buyback -> ["published:jkp:eqnetis_at", "published:jkp:chcsho_12m"]; value_book -> ["published:jkp:be_me"]; profitability -> ["published:jkp:gp_at"]; low_investment -> ["published:jkp:at_gr1"]; low_accruals -> ["published:jkp:oaccruals_at"]; liquidity_premium -> ["published:jkp:ami_126d"]; seasonality_12m -> ["published:jkp:seas_1_1an"].

## Relevant files
- `factory_families_l.py`
- `tests/regression/test_factory_families_l.py`
- `factory_families_o.py`
## Requirements
1. factory_families_l.py registers exactly the four families above via sf.family with the given league, grid, entry, exit (none = sf.G's default), stop, hold, data/available/missing, and rationale.
2. It defines lag(a, n), NEW_FAMILIES (the four names in order) and PUBLISHED (as above).
3. link_library(conn) sets the `implementation` field of each strategy_library row whose entry_id is in PUBLISHED to "factory family <name>" (UPDATE ... WHERE entry_id=?; a missing entry is skipped) and returns the number of rows updated; it creates nothing.
4. Importing the module twice does not duplicate or change sf.F. A module docstring states: Stage L3, rebuilt from published signals that survived publication, templates not search (the freeze boundary applies).

## Constraints
1. Create ONLY factory_families_l.py and tests/regression/test_factory_families_l.py. Do not modify strategy_factory.py or factory_families_o.py (given for reference).
2. No network; the test uses sqlite3.connect(":memory:") with strategy_library.init(conn) for link_library and never opens data/market_data.db.
3. Keep factory_families_l.py under 150 lines and the test under 130 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does; import strategy_factory, then factory_families_l.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_factory_families_l.py exits 0.
2. The test checks: all four names in strategy_factory.F; momentum_12_1's entry contains an op "lag" with n 21 wrapping op "pct_change" with n 231 and max_hold_days 21; momentum_9_1 uses 168; fcf_to_price and earnings_surprise have data_available False with a non-empty missing reason; momentum families are available; PUBLISHED covers every NEW_FAMILIES name; link_library updates a seeded entry's implementation and skips a missing one; the strings "import evolve" and "import seeds" are absent from the module.
3. At least 8 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
