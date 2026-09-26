# TASK-040

- component: research
- priority: high
- state: IN_PROGRESS
- branch: ado/task-040
- created: 2026-09-26T07:00:00+00:00
- dependencies: TASK-039

## Objective
Create published_library.py (Stage L2): for all 153 JKP factors, attach the original paper (citation, publication year, in-sample period, original t-stat), compute the post-publication long-leg evidence, flag adoption candidates at t > 3, and enter each factor into the Research Library as a HYPOTHESIS; plus its regression test.

## Background
published_signals.py (already built) provides: init(conn); tables published_signals(source, signal, acronym, authors, year, sample_start, sample_end, op_return, op_tstat, description, direction), published_returns(source, signal, leg, weighting, date, ret, n) with legs 'pf1','pf2','pf3','ls','mkt' (source 'jkp'; the market series is signal 'mkt' leg 'mkt' weighting 'vw_cap'), published_evidence(family, signal, weighting, period, months, mean_long, mean_mkt, mean_excess, tstat_excess, mean_ls, computed_at); and helpers _series(conn, signal, leg, weighting) -> {date: ret}, _period_of(date, sample_end, pub_year) -> 'pre'|'post'|'gap', _stats(excess_list, ls_list) -> (mean_excess, tstat, mean_ls). Reuse them (import published_signals as ps); do not reimplement the arithmetic. data/jkp/factor_details.csv (first row is the header) has columns including abr_jkp, name_new, cite (e.g. "Foster Olsen and Shevlin (1984)" or "Chan Jegadeesh and Lakonishok (1996) 1972/1"), "in-sample period" (e.g. "1974 - 1981"), t-stat, direction, significance; rows with an empty abr_jkp are skipped; if an abr_jkp appears twice, the first row wins. data/jkp/cluster_labels.csv has characteristic, cluster. Publication year = the first 4-digit number in parentheses in cite, else the first 4-digit number 1900-2030 in cite. Sample end = the last 4-digit number in "in-sample period". The long leg is pf3 if the published_signals direction is +1 else pf1 (as in published_signals.evidence). strategy_library.upsert(conn, entry) requires entry_id, name, family, original_hypothesis, known_biases, limitations, validation_status (strategy_library.HYPOTHESIS); family must be in strategy_library.FAMILIES = ("value", "quality", "momentum", "fundamental_momentum", "value_momentum", "value_quality", "defensive", "event_driven", "technical", "machine_learning"). CLUSTER_TO_FAMILY: Value -> value; Size -> value; Quality -> quality; Profitability -> quality; Accruals -> quality; Investment -> quality; Debt Issuance -> quality; Low Leverage -> defensive; Low Risk -> defensive; Momentum -> momentum; Profit Growth -> fundamental_momentum; Seasonality -> technical; Short-Term Reversal -> technical. Adoption bar (Harvey, Liu and Zhu 2016): post-publication long-leg excess t-stat > 3 in either weighting ('ew' or 'vw_cap').

## Relevant files
- `published_library.py`
- `tests/regression/test_published_library.py`
- `published_signals.py`
## Requirements
1. read_details(path="data/jkp/factor_details.csv", clusters="data/jkp/cluster_labels.csv") returns {abr_jkp: {"name", "cite", "year", "sample_end", "tstat", "significance", "cluster"}} per the Background parsing rules (numbers as int/float or None).
2. attach(conn, details) adds columns cluster TEXT and significance INTEGER to published_signals when missing (ALTER TABLE, idempotent) and updates every source 'jkp' row whose signal is in details: authors = cite, year, sample_end, description = name, op_tstat = tstat, cluster, significance. Returns the number of rows updated.
3. evidence_all(conn) computes, for EVERY source 'jkp' signal with a year and sample_end, for weightings ('ew', 'vw_cap') and periods ('pre', 'post', 'all'), the same quantities as published_signals.evidence, and INSERT OR REPLACEs them into published_evidence with family = "jkp:" + signal; returns the rows.
4. candidates(conn) returns the list of {signal, name, cluster, year, post_ew_excess, post_ew_t, post_vw_excess, post_vw_t, adopt} for every jkp signal with post-period evidence, where adopt is True when either post t-stat > 3; sorted by the larger post t-stat descending.
5. to_library(conn) upserts one strategy_library entry per candidate: entry_id "published:jkp:" + signal; name = the factor name; family via CLUSTER_TO_FAMILY (default "technical"); source "JKP Global Factor Data (Jensen, Kelly & Pedersen 2023)"; publication = cite; original_hypothesis = "<name>: <high|low> values predict higher returns (<cite>)" using the direction; original_period = in-sample period text "<sample_start?>-<sample_end>" or str(sample_end); original_universe "US common stock (CRSP incl. delisted), tercile portfolios"; original_metrics = {"t_stat": op_tstat, "significance": significance}; known_biases = "Portfolio evidence: monthly-rebalanced tercile portfolios of all US stocks incl. microcaps; a single $20 slot position is not the portfolio. Returns decay after publication (McLean & Pontiff 2016); only the post-publication period counts."; limitations = "Long-leg excess over the market, before trading costs; our data may not compute this characteristic; not tested on our data."; results = {"post_ew_excess", "post_ew_t", "post_vw_excess", "post_vw_t", "adopt"}; validation_status HYPOTHESIS; status_reason = "published; post-publication long-leg excess <ew>%/mo (t <t>) ew, <vw>%/mo (t <t>) vw; adopt candidate: <yes|no>". Returns the number of entries written.
6. main(argv=None) with --run (read_details, attach, evidence_all, to_library) and --report (print candidates with adopt first: signal, cluster, year, post ew %/mo and t, post vw %/mo and t, ADOPT flag). Connect with sqlite3.connect(load_config()["database"]["market_data_path"]) (from universe import load_config). Import runtime first.

## Constraints
1. Create ONLY published_library.py and tests/regression/test_published_library.py. Do not modify published_signals.py (given for reference).
2. The test uses sqlite3.connect(":memory:"), calls ps.init and strategy_library.init, inserts a few published_signals / published_returns rows directly, writes tiny factor_details.csv / cluster_labels.csv in a tempfile directory, and never opens data/market_data.db or the real downloads.
3. Keep published_library.py under 240 lines and the test under 180 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_published_library.py exits 0.
2. The test checks: cite "Foster Olsen and Shevlin (1984)" -> year 1984; "Chan Jegadeesh and Lakonishok (1996) 1972/1" -> 1996; "1974 - 1981" -> sample_end 1981; attach is idempotent (run twice, no error, same values); evidence_all writes rows with family "jkp:<signal>" and the pre/post split follows year and sample_end; a factor with post t above 3 is adopt True and one below is False; to_library writes an entry with validation_status HYPOTHESIS, entry_id "published:jkp:<signal>", and a family from CLUSTER_TO_FAMILY.
3. At least 9 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
