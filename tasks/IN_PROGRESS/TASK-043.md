# TASK-043

- component: reporting
- priority: medium
- state: IN_PROGRESS
- branch: ado/task-043
- created: 2026-09-26T08:30:00+00:00
- dependencies: none

## Objective
Create control_center_extra.py: three read-only data views for new Control Center panels — strategy health (N5), published survivorship-free evidence (Stage L), and the Knowledge Factory (Stage O9) — plus its regression test. It only reads the database and returns plain dicts/lists; the page wiring is done separately.

## Background
Tables (a missing table yields an empty view, never an exception): strategy_health(id, at, strategy_key, version, state, reason, metrics) append-only, the latest row per (strategy_key, version) by id is current; league_strategies(strategy_key, version, name, ...) for display names; published_evidence(family, signal, weighting, period, months, mean_long, mean_mkt, mean_excess, tstat_excess, mean_ls, computed_at) where family is either one of our family names (e.g. "value_book") or "jkp:<signal>"; published_signals(source, signal, acronym, authors, year, sample_start, sample_end, op_return, op_tstat, description, direction, cluster, significance); strategy_library(entry_id, name, family, validation_status, status_reason, implementation, ...); knowledge_entries(entry_id, strategy_name, source, translation_state, factory_family, ...) with translation_state values such as 'DATA_UNAVAILABLE', 'SOURCE_DERIVED_VARIANT', 'NEEDS_TEMPLATE' or NULL; knowledge_links(entry_id, strategy_key, version, variant, linked_at). Connection has row_factory sqlite3.Row.

## Relevant files
- `control_center_extra.py`
- `tests/regression/test_control_center_extra.py`
## Requirements
1. health_view(conn) returns {"counts": {state: n}, "flagged": [...]} where flagged lists every strategy whose current state is not HEALTHY as {"strategy_key", "version", "name", "state", "reason", "since"} ("since" = the at of the current row; name from league_strategies or the key), ordered FAILED, DEGRADING, WATCH then by name; counts covers all current states.
2. published_view(conn) returns {"families": [...], "candidates": [...]}: families = for each published_evidence family NOT starting with "jkp:", one dict {"family", "signal", "year", "post_ew_excess", "post_ew_t", "post_vw_excess", "post_vw_t", "pre_ew_excess"} (year from published_signals source 'jkp' for that signal), sorted by post_ew_t descending; candidates = for families starting with "jkp:", the same fields plus "name" (published_signals.description) and "cluster", only where post_ew_t > 3 or post_vw_t > 3, sorted by the larger t descending, at most 20.
3. knowledge_view(conn) returns {"entries": total knowledge_entries, "by_state": {translation_state or "UNTRANSLATED": n}, "linked": number of distinct entry_id in knowledge_links, "library": {validation_status: n} from strategy_library, "published_entries": number of strategy_library rows with entry_id LIKE 'published:%'}.
4. all_views(conn) returns {"health": health_view(conn), "published": published_view(conn), "knowledge": knowledge_view(conn)}.
5. Import runtime first; standard library only (sqlite3). Percentages stay fractions; rendering is not this module's job.

## Constraints
1. Create ONLY control_center_extra.py and tests/regression/test_control_center_extra.py. Modify nothing else.
2. No network; the test uses sqlite3.connect(":memory:") creating only the tables it needs; never opens data/market_data.db.
3. Keep control_center_extra.py under 200 lines and the test under 170 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_control_center_extra.py exits 0.
2. The test checks: health_view takes the LATEST row per strategy (an older FAILED superseded by HEALTHY is not flagged), orders FAILED before WATCH, counts states; published_view excludes jkp: rows from families, includes only t > 3 in candidates, sorts by t; knowledge_view counts states, links and published entries; every view returns an empty-but-valid structure when its tables are missing.
3. At least 9 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
