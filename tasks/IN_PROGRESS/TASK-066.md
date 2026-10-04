# TASK-066

- component: knowledge_factory
- priority: medium
- state: IN_PROGRESS
- branch: ado/task-066
- created: 2026-10-04T00:00:00+00:00
- dependencies: none

## Objective
Record the source's claimed result and Stockbot's actual backtest result on `knowledge_reproductions`, so they can be compared side by side (§19 of Addendum E: "source claim and Stockbot result stored apart").

## Background
`knowledge_reproductions` stores one row per translated entry that has been registered as a strategy. It currently has `source_version` / `stockbot_version` (git-hash strings) but no performance metrics. `knowledge_entries.original_claim` holds whatever the original paper claimed (e.g. "12% annual return 2006-2016"). The strategy's actual backtest result lives in `evaluations` (from `factory_pipeline`).

When a knowledge reproduction's backtest completes, we want to write `source_claim_text` (the source's own words, verbatim, ≤200 chars) and `stockbot_net_per_trade` (our backtest's net-per-trade) into `knowledge_reproductions` alongside the existing provenance columns. This closes the §19 requirement and makes the comparison visible in reports.

## Relevant files
- `knowledge_factory.py`
- `knowledge_library.py`
- `tests/regression/test_knowledge_factory.py`
## Requirements
1. **`knowledge_library.init(conn)`**: add the four ALTER TABLE calls above immediately after the `CREATE TABLE IF NOT EXISTS knowledge_reproductions` statement.
2. **`knowledge_factory.init(conn)`**: add the same four ALTER TABLE calls in the same position.
3. **`knowledge_factory.reproduce(conn)`**: when inserting into `knowledge_reproductions`, also populate `source_claim_text` from `r.get("original_claim")`, truncated to 200 characters. The INSERT OR REPLACE currently writes 9 values; add `source_claim_text` as the 10th column and value.
4. **New `knowledge_factory.sync_results(conn)` function**:
5. Query all rows from `knowledge_reproductions` (columns: `entry_id`, `strategy_key`, `version`).
6. For each, look up the latest evaluation in `evaluations` where `strategy_key` matches and `mode = 'as_is'` (the survivorship-corrected backtest used by ranking): `SELECT net_per_trade, n_trades, evaluated_at FROM evaluations WHERE strategy_key=? AND mode='as_is' ORDER BY evaluated_at DESC LIMIT 1`.
7. If a row is found and either `stockbot_net_per_trade IS NULL` or `evaluated_at > stockbot_result_at`, UPDATE `knowledge_reproductions SET stockbot_net_per_trade=?, stockbot_n_trades=?, stockbot_result_at=? WHERE entry_id=?`.
8. If `evaluations` does not exist, return 0 silently.
9. Commit and return the count of rows updated.
10. **`knowledge_factory.run(conn, cfg)`**: call `sync_results(conn)` before returning. Log a single line: `logger.info("knowledge: synced %d reproduction results", n)`.
11. **Tests** in `tests/regression/test_knowledge_factory.py` — add two new checks:
12. source_claim_text populated`: after calling `reproduce(conn)` on a connection that has a translated entry with `original_claim='test claim'`, the `knowledge_reproductions` row has `source_claim_text='test claim'` (truncated at 200 chars).
13. sync_results updates from evaluations`: create an `evaluations` table with one row for the reproduction's strategy_key (`mode='as_is'`, `net_per_trade=0.012`, `n_trades=50`, `evaluated_at='2026-10-01T00:00:00Z'`), call `sync_results(conn)`, assert `stockbot_net_per_trade` is approximately 0.012 and `stockbot_n_trades` is 50.

## Constraints
1. Do not change `factory_pipeline.py`, `ranking.py`, `strategy_objects.py` or any file outside the four listed.
2. The ALTER TABLE calls must be inside try/except so re-running `init()` is always safe.
3. sync_results` must be silent if `evaluations` does not exist (catch `sqlite3.OperationalError`).
4. Do not change the INSERT column order for the existing 9 columns in `reproduce()` — only append `source_claim_text` as the 10th.

## Acceptance criteria
1. ./venv/bin/python tests/regression/test_knowledge_factory.py` exits 0.
2. grep "sync_results" knowledge_factory.py` returns at least three lines (definition, call in run(), docstring or log).
3. ./run_tests.sh` passes.
