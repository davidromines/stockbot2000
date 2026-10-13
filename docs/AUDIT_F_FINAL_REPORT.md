# Addendum F — Independent Profitability Audit: final report and handoff (2026-10-13)

Status: phases A to F run; G (fixes) and H (this report) delivered. Everything below is read-only or shadow-only except the items listed under "Changes that touch live trading" (each owner-approved on 2026-10-13 and already merged). No options, crypto, evolutionary-search, capital-limit or risk-engine behaviour was changed without approval.

## The candid answer

**No strategy survives the audit as an established edge.** The seven families the 10-12 dossier called statistically positive are all *unresolved*: the largest has 18 independent entry dates (20 are needed for any label above that), none survives multiple-testing adjustment, the reported t-statistics treated trades from the same few dates as independent, the figures were gross of costs and filled at the signal-day close, and a third of the largest family's trades were a replay of 09-24 created on 09-27. The pool of 18,730 honest forward trades nets −0.45 % per trade. The real account is −$3.59 (−4.1 %) since launch (16 closed trades +$0.37, five open positions −$3.97). Nothing here shows the system loses money by design either: with 16 sessions and one regime, it cannot tell. The only measurement that cannot be inflated by how candidates were found is the pre-registered prospective test, expected to complete around December.

## Acceptance criteria

| | criterion | status | where |
|---|---|---|---|
| A | seven families independently audited, reproduced or discrepancies explained | met | `reports/audit_forward_2026-10-13.md`, `docs/AUDIT_A6_FAMILY_VERDICTS.md` |
| B | statistics account for correlation, multiple testing, sample structure | met | `forward_stats.py` (cluster t, bootstrap, Holm, BH, max-T, effective tests); `reports/audit_selection_2026-10-13.md` |
| C | root causes prioritised by evidence; where candidates are lost | met | `reports/audit_pipeline_2026-10-13.md`, `docs/AUDIT_BC_FINDINGS.md` |
| D | research promise separated from live eligibility, shadow only | met | `capital_gate.py` (0 of 384 eligible), daily stage `[9k1]` |
| E | at least one concrete improvement implemented | met | restatement (`restate_paper.py`), funnel rewrite, drawdown tiers (live), shadow gate, profit report, prospective test registry |
| F | historical-experience approach fairly evaluated | met | `experience_experiment.py`: pre-registered, chronological, costs, baselines; does not meet the bar |
| G | safety architecture intact | met | no change to options, crypto, search, capital limits, risk limits; drawdown tiers added with approval and tests |
| H | candid final report | this document | |

## Deliverables

| # | deliverable | file |
|---|---|---|
| 1 | independent profitability audit | `reports/audit_forward_2026-10-13.md`, `reports/audit_selection_2026-10-13.md`, `docs/AUDIT_A6_FAMILY_VERDICTS.md`, `reports/audit_survivorship_2026-10-13.md`, `reports/audit_execution_2026-10-13.md` |
| 2 | root-cause analysis (ranked) | `reports/audit_pipeline_2026-10-13.md` (B2 table), `docs/AUDIT_BC_FINDINGS.md` |
| 3 | research funnel report | `reports/audit_pipeline_2026-10-13.md`; daily `data/funnel.txt` (rewritten) |
| 4 | ranking and eligibility assessment (shadow) | `reports/audit_ranking_2026-10-13.md`, `reports/capital_gate_2026-10-13.md`, `reports/audit_portfolio_2026-10-13.md` |
| 5 | historical-experience experiment | `reports/experience_experiment_2026-10-13.md`, registry `analog_vs_baseline_2026_10` |
| 6 | implemented fixes | below |
| 7 | updated operational report | `reports/profit_report_2026-10-13.md` (account, current occupants since their own assignment, research kept apart) |
| 8 | handoff | this document, `PROJECT_STATUS.md`, `CLAUDE.md`, `docs/ROADMAP_INTEGRATION.md`, tracker and dossier pages |

## Root causes, ranked (full table with evidence in the pipeline report)

1. Too few independent observations (dates, regimes): decisive. 2. The ranking promotes unproven strategies on counts of correlated trades (median 20 "trades" from one entry date among the top 50; one shared +164 % trade sits in the paper funds of three of five slots). 3. The backtest-to-forward gap (survivorship assumption decides 33 % of verdicts; selection among thousands). 4. Redundant hypotheses (about 175 lineages behind 1,281 non-search strategies; 91 % of documented ideas are title-only). 5. Measurement defects (corrected). 6. Regime and decay (unknown). 7. Costs (not what decides the pool result).

## Implemented fixes and tools

| change | kind | live effect |
|---|---|---|
| `restate_paper.py` + `paper_trades_restated` (daily `[9k0]`) | honest next-open restatement beside the unchanged originals | none |
| `funnel.py` `forward_families`, `eight_questions` | gross/net/honest, clustered t, 20-date rule; hard-coded conclusions replaced | none |
| `forward_stats.py` | shared statistics | none |
| `drawdown_tiers.py`, `risk_engine.py`, `slot_trader.py`, `config/risk.yaml` | notice 10 %, new entries paused 20 %, stop 35 % unchanged | **yes, owner-approved, merged 2026-10-13** |
| `capital_gate.py`, daily `[9k1]`, `capital_gate_shadow` | shadow gate | none (nothing reads it) |
| `prospective_eval.py`, registry `forward_families_prospective` | locked prospective test | none |
| `hypothesis_scorecard.py`, `audit_*.py`, `profit_report.py`, `experience_experiment.py` | reports/experiments | none |

Verified defects and status: same-close paper fills and gross-labelled "net" (restated, funnel corrected); funnel hard-coded conclusions (replaced); corporate-action phantom losses, e.g. CTVA (flagged in the restatement, excluded from funnel statistics); duplicate trades across funds (deduplicated in the audit statistics). Not changed: the ranking basis and estimator (owner decisions, below). Unresolved: stop behaviour live (no stop has fired), whether the modelled round-trip cost matches live (35 fills, inconclusive).

## Decisions waiting for the owner (all would change, or inform, live behaviour)

1. Show the shadow-gate verdict beside each slot in the daily report (information only). 2. Enforce do-no-harm criteria (data integrity, provenance, cost stress, worst-case survivorship, drawdown) after two weeks of shadow data. 3. Replace the ranking estimate (count dates, winsorise outliers, shrink) after the prospective test. 4. A beta / concentration limit for slot selection: the five live positions have an equal-weight beta of 2.27 to SPY. 5. Treat a trade that supplies more than half of a fund's return as non-evidence in the ranking. Also open: arming `daily_snapshot.py` in cron after the owner approves its design; `allow_options`, `allow_crypto`, `search.mode`, `published_prior` remain the owner's.

## Commands to reproduce

```bash
./venv/bin/python audit_forward.py --reported          # A1-A3
./venv/bin/python audit_selection.py                   # A4-A5
./venv/bin/python prospective_eval.py                  # A6 progress (INTERIM until ~December)
./run_bounded.sh ./venv/bin/python audit_pipeline.py   # B1-B2
./run_bounded.sh ./venv/bin/python audit_ranking.py    # B3
./run_bounded.sh ./venv/bin/python capital_gate.py     # C1 (also daily [9k1])
./run_bounded.sh ./venv/bin/python audit_portfolio.py  # C2-C3
./run_bounded.sh ./venv/bin/python audit_survivorship.py && ./run_bounded.sh ./venv/bin/python audit_execution.py   # D
./run_bounded.sh ./venv/bin/python hypothesis_scorecard.py   # E1-E2
./run_bounded.sh ./venv/bin/python experience_experiment.py  # E3 (already COMPLETE in the registry; re-render only)
./run_bounded.sh ./venv/bin/python profit_report.py          # F / H7
./run_tests.sh                                               # all regression tests
```

## Database changes (all append-only, all in `backup.py`)

`paper_trades_restated` (from the earlier restatement), `capital_gate_shadow`, `hypothesis_scorecard`, and experiment-registry rows `forward_families_prospective` v1 (REGISTERED) and `analog_vs_baseline_2026_10` v1 (COMPLETE).

## Scheduled jobs

Daily `[9k0]` restate and `[9k1]` capital gate are in `daily.sh`. Nothing else was added to cron. To arm `daily_snapshot.py`: drop `--send` from the `eod_report.py` cron line and add `12 21 * * 1-5 cd ~/stockbot2000 && ./venv/bin/python daily_snapshot.py --mode LIVE --send >> logs/daily_snapshot.log 2>&1` after approving its look.

## What would change these conclusions

A family passing the prospective test (20 independent entry dates, max-T adjusted p <= 0.05, bootstrap lower bound above zero) would earn "promising", not "proven". A period with a different market regime and the same families still positive would strengthen it. A completed month of live trading with the account still below its start would not by itself refute anything (16 sessions, five positions).
