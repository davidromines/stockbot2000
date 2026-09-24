# Phase 13 architecture map (step H1)

Audit of 2026-09-24: which existing module owns each concept the Phase 13 and
Addendum A specs name, verified against the code. Rule from spec §3: extend,
never rewrite a working component.

| concept | owner today | what Phase 13 / Addendum A adds |
|---|---|---|
| Strategy identity / versions | `league.py` — `league_strategies`, `definition_hash`, append-only `league_state` | `strategy_objects.py`: §13 metadata + metric snapshots keyed on (strategy_key, version); §14 states added to `league.ALLOWED` |
| Strategy rules | `genome.py` — `{entry, exit, risk:{stop_atr_multiple, max_hold_days}}`; ops gt/lt/crosses/and/or/not/rank/lag/delta/pct_change/zscore | `strategy_factory.py` emits genomes from family templates |
| Features | `train_model.FEATURE_COLS` (24) in `features` | unchanged |
| Fundamentals (PIT) | `daily_fundamentals` (12 metrics, lagged to first tradeable session); `statements.py` per filing | fundamental templates read `daily_fundamentals` columns joined onto the panel; FCF/ROIC/dividend families flagged `DATA_PROBLEM` until projected daily |
| Backtest | `simulator.py` (next-open fills, unfiltered exits), `costs.py`, `benchmark.py` | `factory_pipeline.backtest()` wraps it, bounded windows |
| Validation | `promote.py`, `evaluate_holdout.py`, `random_control.py`, `multiple_testing.py` | pipeline gate: net-positive, minimum trades, window consistency; null/benchmark informational (B20) |
| Robustness | `stress_test.py` (delisting), `bias_exposure.py` | `robustness.py` (§28) |
| Paper trading | `paper_trading.py` (genome or `"model"` or conviction), `pair_funds.py`, `value_fund.py`, `crypto_fund.py` | automatic enrolment of factory strategies as `paper_runs` rows |
| Accounting | per-engine: paper costs at exit only; pair funds skip the opening cost; Value Fund charges none | `accounting.py`: one liquidation-basis model, restated alongside originals |
| League / ranking | `scoreboard.py` (single league, 60 marks), `degradation.py`, `eligibility.py` | `leagues.py`: nine leagues, per-league horizons |
| Research library | `strategy_library.py` (40 entries), `factory.py` (governed evolution; frozen) | `library_bridge.py`: §7 fields, entries → strategy objects |
| Data | `storage.py`, `backfill.py`, `pit_universe.py`, `delistings.py`, `crypto_data.py` | `data_providers.py` interface; `finsaber.py` provider; `dataset_compare.py` |
| Promotion / allocation | `promotion_policy.py`, `allocation.py`, `roster.py` | family-concentration limit; slot engine supersedes `roster` for live |
| Live execution | `signals.py`, `risk_engine.py`, `killswitch.py`, `broker.py` (`RobinhoodBroker`, state machine), `execution.py`, `live_pipeline.py`, `run_execution.py` | LIVE transmit via injected transport, confirmation, retry, restart recovery, reconciliation; stop plans mandatory |
| Monitoring | `check_exits.py` (daily) | `position_monitor.py` (intraday, quote-provider interface) |
| Reporting | `fund_report.py`, `notify.py`, `build_dashboard.py` | `factory_report.py`, `leaderboard.py`, slot report |
| Scheduling | `daily.sh` (cron 07:00 UTC), `run_bounded.sh` | `services.sh`: always-on services under memory caps |

**Constraints discovered in the audit**

- `evolve.py` stays frozen (B16); factory templates are a separate path.
- `daily_fundamentals` lacks FCF, ROIC, dividend and buyback-yield columns;
  `net_share_issuance` stands in for buybacks (negative issuance).
- The price database is daily bars only; intraday history does not exist
  (B8) — intraday strategies stay paper/shadow.
- Heavy jobs must run through `run_bounded.sh` (see CLAUDE.md).
