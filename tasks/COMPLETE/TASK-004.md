# TASK-004

- component: value
- priority: high
- state: COMPLETE
- branch: ado/task-004
- created: 2026-09-22T22:18:45+00:00
- dependencies: none

## Objective
Restrict Value Fund candidates to common stock in value_fund.py. The fund currently proposes buying corporate notes, preferred shares and warrants.

## Background
The first Value Fund review preview proposed buying ATLCZ, BANFP and ANNAW in
its top six. Checked against `symbols.security_type` those are a corporate
note, a preferred share and a warrant — not companies. The fund would have
held three instruments whose fundamentals belong to an issuer they are not a
claim on in the way a share is.

`value_fund.candidates()` pools the top decile of every industry from
`value_score.score_division`, and nothing anywhere in that path filters to
common stock. The rest of the project does filter: `universe.tradeable_types`
in config names the permitted types, and the scanner and Lab paths apply it.
This path was built later and missed it.

The rule this project already follows is that an UNKNOWN is never treated as
acceptable. A ticker absent from `symbols`, or present with a NULL
`security_type`, must be excluded rather than assumed to be common stock.

## Relevant files
- `value_fund.py`
## Requirements
1. Add a module-level function `is_common_stock(conn, ticker)` returning True
2. Give it a docstring saying that an unknown security type is excluded rather
3. In `candidates()`, exclude any scored company that is not common stock,
4. Do not change `BUY_PERCENTILE`, `SELL_PERCENTILE`, `MAX_POSITIONS`,
5. Do not change `review()`, `mark()`, `status()` or `render()`.
6. Keep `candidates()` returning the same shape it returns now: a list of the
7. Query `symbols` once per candidate at most. Do not issue a query per

## Constraints
1. Modify ONLY `value_fund.py`. Do not touch `value_score.py`,
2. Do not add a dependency.
3. Do not change the database schema.
4. Do not add a config option. `common_stock` is the literal value used in

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python -c "import value_fund, storage; from universe
2. ./run_tests.sh` reports ALL PASS with 31 files.
3. git status --short` shows exactly one modified file, `value_fund.py`.
