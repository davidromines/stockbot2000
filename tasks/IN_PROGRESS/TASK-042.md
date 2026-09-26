# TASK-042

- component: tests
- priority: high
- state: IN_PROGRESS
- branch: ado/task-042
- created: 2026-09-26T08:00:00+00:00
- dependencies: none

## Objective
Create tests/regression/test_fcf_to_price.py: regression tests for value_metrics.compute's new fcf_to_price metric (free cash flow to price = (operating cash flow - capex) / market cap), pinning that capex is subtracted, that missing inputs give None (never zero), that flows are annualised consistently, and that the old fcf_yield is unchanged.

## Background
value_metrics.compute(cur, prev, market_cap=None, mkt=None) takes cur = {tag: {qtrs: value}} for one filing and returns a dict of metrics. Operating cash flow tags: "NetCashProvidedByUsedInOperatingActivities" (or "...ContinuingOperations"); capex tags: "PaymentsToAcquirePropertyPlantAndEquipment" or "PaymentsToAcquireProductiveAssets" (reported as a positive outflow). qtrs 4 = a full year, qtrs 1 = a quarter. Annualisation (the ann helper): the full-year value if the filing has qtrs 4, else the quarter x 4. fcf_to_price = (ocf_annual - abs(capex_annual)) / market_cap; None when ocf or capex is missing or market_cap is None or <= 0. fcf_yield (legacy name) = ocf_annual / market_cap and must not change. Valuation metrics are computed only when market_cap > 0.

## Relevant files
- `tests/regression/test_fcf_to_price.py`
- `value_metrics.py`
## Requirements
1. Annual filing: ocf {4: 100}, capex {4: 30}, market_cap 1000 -> fcf_to_price 0.07 and fcf_yield 0.10.
2. Quarterly filing: ocf {1: 25}, capex {1: 5}, market_cap 1000 -> fcf_to_price (100 - 20) / 1000 = 0.08.
3. Capex reported negative (e.g. -30) is still subtracted as an outflow: result 0.07 for requirement 1's inputs.
4. Missing capex -> fcf_to_price is None while fcf_yield is still 0.10; missing ocf -> both None.
5. market_cap None and market_cap 0 -> fcf_to_price None.
6. The alternative capex tag PaymentsToAcquireProductiveAssets works the same as the primary tag.
7. Negative free cash flow (ocf 10, capex 50, market cap 1000) -> -0.04 (not clipped to zero).

## Constraints
1. Create ONLY the test file. Do not modify value_metrics.py.
2. No database, no network.
3. Keep the file under 130 lines.
4. Import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed; compare floats with a 1e-12 tolerance.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_fcf_to_price.py exits 0.
2. At least 9 lines beginning with `  PASS`, covering all seven requirements.
3. ./run_tests.sh reports ALL PASS.
