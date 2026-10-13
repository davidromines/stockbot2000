# Addendum F, Phases B and C: findings and decisions for the owner (2026-10-13)

Read-only and shadow. Nothing in `slots.py`, `risk_engine.py` or `slot_trader.py` changed or reads these results.
Full tables: `reports/audit_pipeline_2026-10-13.md` (B1/B2), `reports/audit_ranking_2026-10-13.md` (B3),
`reports/capital_gate_2026-10-13.md` (C1), `reports/audit_portfolio_2026-10-13.md` (C2/C3). Code: `audit_pipeline.py`,
`audit_ranking.py`, `capital_gate.py`, `audit_portfolio.py`; 22 checks in `tests/regression/test_audit_phase_bc.py`.

## B1/B2: where candidates are lost, and why no edge is established

| stage | strategies | families |
|---|---:|---:|
| documented hypotheses | 4,158 | |
| strategy identities | 2,233 | 99 |
| backtested (latest generator) | 1,163 | 82 |
| positive net, survivors only / with dead companies / worst case | 1,092 / 1,005 / 642 | 77 / 72 / 60 |
| positive on the unseen 2023-today window | 205 of 337 tested | 46 |
| forward chain: strategies with a paper fund | 2,191 | 94 |
| >= 20 honest forward trades / and positive / and >= 20 own entry dates | 168 / 82 / **0** | 24 / 12 / 0 |
| ever in a real slot | 18 | |
| real account, closed trades | 16 trades, 12 winners, +$0.37 net on $286 deployed | |

Pool of all 18,730 honest forward trades: gross −0.27 %, costs 0.18 %, net −0.45 % per trade. Ranked causes (a judgement, evidence in the report):
(1) too few independent observations, decisive; (2) the ranking promotes unproven strategies on counts of correlated trades;
(3) the backtest-to-forward gap; (4) redundant hypotheses; (5) measurement defects, now corrected; (6) regime and decay, unknown;
(7) costs, not what decides the pool result.

## B3: the ranking formula

- **Structure matches the documented blend** (10 x prior + n x forward) / (10 + n), scaled by 20 / max(hold, 5), for 80 % of strategies. **Deviations from the documentation:**
  21 % of rows use the 2023-today unseen-window result as the prior, not the 2016-19 backtest stored in `ranking_history.backtest`; 41 % are Lab-search funds whose prior is zero.
- **`n` counts open positions.** Among the 50 best-scored strategies on each date the median `n` is 20, from **one** independent entry date (a research-mode fund opens 20 positions at once).
- **The stored score is a weak predictor of what happened next:** mean rank correlation with later honest returns +0.03, against +0.21 for the backtest alone, +0.15 for the unscaled blend and +0.29 for an
  empirical-Bayes estimate counting dates; top quintile predicted +1.62 % realised −0.42 %, middle quintile +0.35 %. Ten snapshots, 1 to 11 sessions of outcome each: indicative, not proof.
- **One trade chose three of the five slots' paper funds.** KOD entered 2026-09-24 returned +163.85 % net and sits in exactly three funds: the paper funds of slots 1, 2 and 5. Without it those funds
  average +6.0 %, +3.8 % and no trades. The live positions are different stocks (WDC, CRS, AMD, INTC, FDX); the *selection* of the strategy was driven by one shared outlier. Slots 3 and 4 (factory
  strategies) have honest means of +0.21 % (39 trades) and −0.74 % (96 trades).
- **Churn:** 13 slot releases in 13 trading days, 6 by ranking swaps justified by claimed advantages of +0.5 to +7.2 %/trade from holders with 3 to 7 sessions.
- The 20-session scaling is rank-identical to per-trade return (Spearman 1.00): most holds are shorter than its 5-session floor, so it is a constant multiplier there.

## C1: shadow capital-eligibility gate (13 criteria, UNKNOWN blocks)

0 of 384 strategies assessed are eligible; 0 of the 5 slot holders. C4 (20 own independent dates) and C13 (completed prospective test) block everyone; 196 fail provenance (> 25 % retroactive replay);
only 31 pass the worst-case survivorship check. Thresholds are configuration (`capital_gate:` in `config.yaml`, defaults in code) and were fixed before the run. Daily stage `[9k1]` records each day's verdict in `capital_gate_shadow`.

## C2/C3: comparability and the portfolio

- Per holding session keeps 4 of the per-trade top 10; per fund session (idle cash counted) keeps 3. The intervals around every top fund cross zero; several have a single entry date.
- **The five live positions are not five independent bets:** WDC, INTC and AMD (beta 2.9 to 3.2, pairwise correlation 0.45 to 0.57) plus CRS (1.55) and FDX (0.90). Equal-weight beta to SPY **2.27**,
  average pairwise correlation +0.31, diversification ratio 1.41 against 2.24 for five independent equal-risk bets. Strategy-level correlations of the five holders 0.25 to 0.57. At that beta a 10 % market fall
  is a ~23 % account fall, and the 35 % kill switch corresponds to a market fall of roughly 15 %; the account is −4.1 % since launch while SPY gained +1.5 % from 09-24 to 10-09, so
  it has underperformed even its own beta (a short, noisy window).
- **Shadow selection:** the current top-five rule and a date-counting alternative are indistinguishable from the pool (−0.10 %, −0.17 %, pool −0.05 % per trade over 10 snapshots). Neither is shown to select better than chance on this record.

## Decisions for the owner (nothing has been changed)

| # | decision | recommendation |
|---|---|---|
| 1 | Show the gate verdict beside each slot in the daily image / report (option A in the gate report) | yes: information only, no change to trading |
| 2 | Enforce do-no-harm criteria only (data integrity, provenance, cost stress, worst-case survivorship, drawdown) | wait two weeks of shadow data, then decide |
| 3 | Replace the ranking estimate (count dates, winsorise outliers, shrink) | not yet: shadow evidence is too short; revisit after the prospective test |
| 4 | Add a beta / concentration limit to slot selection (e.g. no more than two slots above beta 2.5, or an account-beta cap) | worth deciding: it is the one finding that bears directly on the −4 % result; a live-allocation change, so the owner's call, with a worktree branch and 3-way tests |
| 5 | Treat a trade contributing more than half of a fund's total return as non-evidence in the ranking | consider with 3 |
