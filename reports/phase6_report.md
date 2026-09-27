# STOCKBOT2000 PHASE 6 REPORT

Generated 2026-09-27T18:15:29+00:00 from the database and a test run.

## STATUS

24 of 24 §30 checklist items pass or are superseded. Phase 6 infrastructure is complete.
**No strategy has demonstrated an edge.** Phase 6 was not meant to find one.

## DATA INTEGRITY

- **Truth set:** versions sealed_v1, v1; verified, hashes match, files read-only
- **Point-in-time universe:** 2008-06-30: 22.63% of 3,000 knowable priced; 2016-06-30: 41.57% of 2,490 knowable priced; 2024-06-28: 83.73% of 2,133 knowable priced
- **Delisting coverage:** prices held for 553 of 9,464 delisted listings (5.8%)
- **Fundamental availability:** 400,700 of 400,700 filings carry a first tradeable session (100.0%); 400,700 an acceptance time
- **Freshness:** prices 2026-09-24, features 2026-09-24, daily_fundamentals 2026-09-24

## RESEARCH

- **Trials:** 1,049,975 cumulative (append-only); the best Sharpe noise alone reaches at this count is ~5.27
- **Seed-free search:** both arms run (n=720 each); best fitness seeded 0.124 vs seed-free 0.091; seed-shaped share 13% vs 0%. Caveat: n=1 per arm; fitness differences are not separable from run-to-run variance
- **Multiple-testing accounting:** counter append-only; search mode FROZEN; 11 registered experiment versions

## VALIDATION

- **Holdout:** sealed; 0 strategies have used their one evaluation
- **Firewall:** documented (docs/VALIDATION_FIREWALL.md)
- **Random control:** 0 of 400 random strategies cleared the gate (best Sharpe 1.14, best net $10,980)
- **Matched null:** `baselines.py` per forward fund; `benchmark.py` price x horizon surface in the Lab

## FORWARD TESTING

- **Active funds:** 1424 (paper and pair)
- **Days forward:** since 2026-09-04 (last bar 2026-09-24)
- **Total trades:** 190 closed paper trades

## EXECUTION

- **Simulation:** 9 slot trades recorded
- **Shadow:** 0 slot trades recorded
- **Live:** 9 slot trades recorded  (**armed**: real orders, Robinhood Agentic)

## REGRESSION

- **Tests:** 120 files
- **Pass:** 120
- **Fail:** 0

### §30 checklist

| item | state | evidence |
|---|---|---|
| Seed-free search works | PASS | regression/test_search_hygiene=PASS |
| Seed ancestry tracked | PASS | regression/test_ancestry_and_freshness=PASS |
| Truth set immutable | PASS | regression/test_truth_set=PASS |
| Truth set versioned | PASS | regression/test_truth_set=PASS |
| Truth set hashed | PASS | regression/test_truth_set=PASS |
| Point-in-time universe works | PASS | regression/test_pit_universe=PASS |
| Fundamental availability dates enforced | PASS | regression/test_pit_provenance=PASS, regression/test_lookahead=PASS |
| Data freshness audit works | PASS | regression/test_ancestry_and_freshness=PASS, regression/test_partial_bars=PASS |
| Validation firewall documented | PASS | docs/VALIDATION_FIREWALL.md |
| Sealed holdout inaccessible to research | PASS | regression/test_sealed_holdout=PASS, regression/test_seal_boundary=PASS |
| Experiment registry works | PASS | regression/test_experiment_registry=PASS |
| Experiments can be preregistered | PASS | regression/test_experiment_registry=PASS |
| Registered experiments cannot silently mutate | PASS | regression/test_experiment_registry=PASS |
| Stop sweep works | PASS | regression/test_sweep_and_decay=PASS |
| Forward scoreboard works | PASS | regression/test_scoreboard=PASS |
| Matched-universe null works | PASS | regression/test_baselines=PASS |
| Random control works | PASS | regression/test_random_control=PASS |
| Multiple-testing counter works | PASS | regression/test_multiple_testing=PASS |
| XGBoost calibration metrics work | PASS | regression/test_model_calibration=PASS |
| Signal decay analysis works | PASS | regression/test_sweep_and_decay=PASS |
| Regime analysis works | PASS | regression/test_regimes=PASS |
| TNON regression test works | PASS | regression/test_tnon=PASS |
| Historical measurement bug tests pass | PASS | regression/test_fill_and_pricing=PASS, regression/test_lookahead=PASS, regression/test_data_integrity=PASS, test_fills=PASS |
| Live mode remains disabled | SUPERSEDED | LIVE armed by the owner under Addendum B (B14); §23 no longer applies |

## REMAINING RISKS

- **Survivorship bias** is bounded, not closed: the per-date coverage above is what a backtest can see. Synthetic dead companies (generator v5c) pass the realism test per exit type and are in the ranking's backtests; they remain modelled, not real, prices.
- **Real money is trading strategies with no demonstrated edge.** Most slots hold Rising 200 variants, an entry rule the 14-year stop sweep found loses net in all 30 cells.
- **Forward samples are weeks long.** Nothing clears the scoreboard's 60-mark floor; every forward breakdown (baselines, regimes) is a record, not a verdict.
- **One seed-free comparison (n=1 per arm)** cannot separate seeding from run-to-run variance.
- **Stops are checked on quotes and exited by market order**: gaps through a stop are not protected.

## NEXT RECOMMENDED ENGINEERING PHASE

Not another search. Accrue forward time, keep every fund stepping and backed up, and let the league's sample floors decide. The one purchase that would change the data problem is point-in-time delisted prices (~$270/yr). Do not launch another million-strategy search.

---

Infrastructure working is not success. The goal of Phase 6 was to make Stockbot2000 a research system whose positive result would be substantially harder to dismiss as an artifact.
