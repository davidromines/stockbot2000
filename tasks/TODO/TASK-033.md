# TASK-033

- component: data
- priority: medium
- state: TODO
- branch: ado/task-033
- created: 2026-09-25T16:30:00+00:00
- dependencies: none

## Objective
Create item5.py (Stage M2b): a pure parser that extracts quarterly high/low stock prices from the text of a 10-K "Item 5 — Market for Registrant's Common Equity" section, plus its regression test against nine real hand-labelled filings.

## Background
Dead companies have no price history in free data, but their 10-Ks report the high and low price for every quarter of the last two fiscal years. These become real price anchors for synthetic paths, so a WRONG number is far worse than a missing one: the parser must prefer returning nothing for a table it cannot read confidently. Input is plain text already stripped of HTML (tokens separated by spaces/newlines; "$" may be its own token). Prices are decimal tokens like 127.10, $14.80, 0.96 (integers are never prices: they are years, days, counts). Dividend columns (small numbers such as 0.0125, 0.13, 0.420, or an em dash) may appear before or after the High/Low columns. Real layouts, condensed (each is a fixture in tests/fixtures/item5/):
A) year header then quarter rows: "High Low Fiscal Year 2008 First Quarter $ 127.10 $ 95.33 Second Quarter $ 140.50 $ 122.20 ... Fiscal Year 2009 First Quarter ..." (also "2016 Fourth quarter $ 8.40 $ 4.90 $ — Third quarter 7.03 4.84 — ..." with a trailing dividend column, and "Cash Dividend High Low 2017 First Quarter $0.420 $59.03 $51.50" with a LEADING dividend column, and "2009 Fourth Quarter ended December 31, 2009 $ 5.57 $ 3.79").
B) years as column groups: "2014 2013 High Low High Low First Quarter $ 15.17 $ 10.06 $ 19.67 $ 11.35 Second Quarter ..." and "2011 2010 High Low Cash Dividends Declared High Low Cash Dividends Declared Quarter Ended: December 31 $ 24.80 $ 14.70 $ 0.0125 $ 30.71 $ 26.52 $ 0.0125 September 30 34.29 22.85 0.0125 26.51 20.00 0.0125 ...".
C) quarters as columns: "Fourth Quarter Third Quarter Second Quarter First Quarter High Low High Low High Low High Low Fiscal Year 2016 $ 9.26 $ 8.81 $ 9.34 $ 7.10 $ 8.94 $ 6.31 $ 12.43 $ 6.83 Fiscal Year 2015 ...".
D) dated rows: "Quarter Ended: High Low Dividends Declared December 31, 2018 $ 2.83 $ 2.01 $ — September 30, 2018 $ 3.49 $ 1.78 $ — ...".
Quarter labels: First/Second/Third/Fourth (any case, optional "Fiscal"), 1st/2nd/3rd/4th, Q1..Q4, or a month name (with or without a day and year). A month m maps to fiscal quarter ((m - fye_month - 1) % 12) // 3 + 1, and a dated row's fiscal year is its calendar year if m <= fye_month else year + 1. High must be >= low and both > 0. tests/fixtures/item5/expected.json maps each fixture file name to {"fye_month": int, "rows": [{"year", "quarter", "high", "low"}]}.

## Relevant files
- `item5.py`
- `tests/regression/test_item5.py`
- `tests/fixtures/item5/expected.json`
## Requirements
1. parse(text, fye_month=12) returns a list of dicts {"year": int, "quarter": int 1-4, "high": float, "low": float}, deduplicated on (year, quarter), in any order.
2. It handles layouts A, B, C and D from the Background, including dividend columns before or after the prices, by reading the column header order (the words High, Low and Dividend(s) and any years) that precedes the first quarter label.
3. It returns [] rather than guessing when a table's structure is ambiguous, when a row has a number of prices that does not match the header, or when any parsed high < low.
4. locate(text) returns the substring from the LAST occurrence of "market for (the) registrant" / "market for (the) company" (case-insensitive) that is followed within 4,000 characters by at least six decimal prices and the word High, up to 4,000 characters long; or "" when none qualifies.
5. quarter_end(year, quarter, fye_month) returns the ISO date (last day of the month) on which that fiscal quarter ends, e.g. (2016, 4, 8) -> "2016-08-31" and (2009, 1, 12) -> "2009-03-31".
6. Import runtime first; standard library only (re, calendar, json).

## Constraints
1. Create ONLY item5.py and tests/regression/test_item5.py. Do not modify expected.json or the fixtures.
2. No network, no database.
3. Keep item5.py under 280 lines and the test under 120 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does; read every tests/fixtures/item5/*.txt with its expected rows from expected.json.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_item5.py exits 0.
2. For EVERY fixture, every parsed row matches an expected row exactly (year, quarter, and high/low within 0.005): no wrong numbers anywhere (precision 100%).
3. At least 7 of the 9 fixtures are parsed completely (all expected rows found), each checked as its own PASS line.
4. quarter_end examples from Requirement 5 are checked, and parse returns [] for a text with no price table.
5. ./run_tests.sh reports ALL PASS.
