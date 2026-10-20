# Stage AD — Making Stockbot2000 profitable: system review and plan

**Entered 2026-10-19. PLAN ONLY — nothing built, nothing changed live** except the owner's separate instruction the same
day to size Runner trades at $5. **Owner decisions H1–H10 answered 2026-10-19 (§8).** Owner: "review the current system in its
entirety … make recommendations and add them to the project plan. Do not action yet."
Inputs: Addendum H (independent reviewer, verbatim in `docs/ADDENDUM_H_ALPHA_RESEARCH_ENGINE.md`), the live ledger
(`slot_trades`, `live_equity`), the funnel of 2026-10-16, the Addendum F audit reports, and the queries recorded in §9.
Roadmap row: Stage AD in `docs/ROADMAP_INTEGRATION.md`.

---

## 1. Bottom line

1. **The machinery works; no edge has been found.** Execution, reconciliation, risk limits and the audit tools are
   sound. The corrected forward test finds 0 of 54 families positive.
2. **The live loss is mostly not a verdict on any strategy.** The live book has been trading something different from
   what was tested, in three ways:

   | # | Tested | What live actually did | Evidence |
   |---|---|---|---|
   | 1 | Hold 21–252 sessions, exit on the strategy's own rule or stop | **Median hold 3 days.** 17 of 23 live exits were forced by slot reassignment (20 releases in 17 trading days) | Reassignment exits: mean **−3.30%**, −3.37% vs SPY over the same days. The strategies' own exits: 5 trades, +3.14% (all in the first week) |
   | 2 | A diversified paper book (up to 20 names) | **One name per slot** | The fund held the slot's name on only 41% of sessions (audit D2). Single-name noise swamps a factor premium measured on a basket |
   | 3 | A ranking meant to pick good strategies | **A ranking that picks volatile stocks.** The score is raw mean return per trade, with no risk adjustment. Higher-volatility names produce larger means for the same quality | 9 of 14 names held live sit in the top quartile of daily volatility, 7 in the top 12%. Live book beta 2.27. Stops at 3 × ATR are 16–33% wide on these names; the three largest losses (−13.5% to −14.5%) all happened inside the stop |

3. **The market did not cause it.** SPY rose about 1% from the first live run (09-24 open 764.07) to 10-15 (771.79). The
   account fell 6.9% over the same period.
4. **What to do, in one line:** stop the churn, make live trade what was tested, size by risk, keep the market's return
   instead of cash, and *then* build the reviewer's evidence engine to decide what deserves capital.

---

## 2. What works — keep it

| Component | Why it is worth keeping |
|---|---|
| Execution path (ExecutionEngine → kill switches → RiskEngine → LiveBroker → Robinhood MCP) | 17 trading days LIVE. Idempotent signals, review-then-place, broker reconciliation every run; no unexplained broker/ledger mismatch on record |
| Risk controls | Kill switch (file, config, Telegram), drawdown tiers 10/20/35%, per-order cap, daily loss caps, fail-closed on unknowns |
| Data platform | 35M bars, point-in-time fundamentals with acceptance times, SUE, Form 4, minute bars for 206 names since 09-17 |
| Honest measurement | Next-open simulator, null surface, survivorship modes, restated paper trades, date-clustered t, Holm/BH/max-T, a pre-registered prospective test |
| Audit discipline | Found real defects in our own code: gross-as-net, same-close paper fills, iid t, the Lab replay, the 10-15 Runner crash |
| Test gate | 165 files. The real-engine Runner test exists because a fake-engine test missed a live failure |

---

## 3. What does not work — evidence and consequence

| # | Problem | Evidence | Consequence |
|---|---|---|---|
| P1 | **Churn.** Daily reassessment replaces holders on small score differences of very uncertain estimates | `min_advantage_score` 0.002 (0.2% per trade) against estimates whose standard error is several percent; `min_hold_sessions` 3; replacements justified by "+8.09%/trade vs +0.91%" from a few Lab paper trades; ~10 rule changes in 17 sessions (generator v5c, family cap, idle rule, owner replacements ×2, backtest_first, Runner reservations ×3), each one rotating live capital | Strategies never reach their designed holding period, so live evidence says nothing about them. Each rotation realises noise and pays the price impact of a round trip |
| P2 | **Volatility-seeking selection** | Score = mean net return per trade (per 20 sessions held), no risk term. `survivorship_backtests` stores no per-trade dispersion, so the ranking could not risk-adjust even if asked. Live names at the 76th–98th volatility percentile | A book with beta ~2 and very wide dollar risk per position. The low-volatility literature says the most volatile decile has historically had *lower* average returns, so this tilt likely costs return as well as adding risk |
| P3 | **Position size ignores risk** | Every slot is $20 regardless of volatility. A 2%-ATR name risks ~$1.20 at its 3-ATR stop; a 7%-ATR name risks ~$4.20 | One volatile name dominates the account's P&L. Stops are too far away to act as risk control |
| P4 | **Slot ≠ paper portfolio** | Paper funds run 20 positions in research mode; a slot buys the single top candidate | At typical stock correlations a single name has about 3× the variance of a 20-name basket; the paper record cannot predict the slot |
| P5 | **Fill conventions differ across layers** | Simulator next-open; paper engine signal-day close (Addendum F V1, still unfixed in the engine); live at the open, +0.39% / +0.45% adverse vs the open (audit D2); medium-term entries fill in the first 6 minutes of the session | Rankings mix incompatible bases; live pays the widest spreads of the day |
| P6 | **Live evidence is statistically useless for ranking** | Restated paper trades: per-trade SD 8.6%. To show +1% per trade at t = 2 needs ~300 independent trades; at designed holds the live book closes ~4 trades a month | Years of live trading per verdict. Live P&L can verify *execution*, never *edge*. "Replace weaker with stronger automatically" must run on population evidence, not live P&L |
| P7 | **Runners are cash-starved and untested** | ~$21 of buying power for two Runners; 21 qualifying signals, 1 traded. The logged signals (2 sessions): mean +0.10% at 30 min (+0.07% vs SPY), SD 0.75% | Live trading yields about one observation a day; shadow would yield ~10 a day at zero cost |
| P8 | **Closed-trade selection bias in forward records** | Closed restated paper trades have a median hold of 4 days even for 60-day strategies: the trades that have closed are mostly early exits | Family means from closed trades alone are biased (usually downward for medium-term strategies). Evaluate entry cohorts on marked equity, as the prospective test does |
| P9 | **Open integrity items** | Corporate actions (CTVA −84% phantom losses), ledger vs equity off by $0.24, Runner tables not in backup, sign-in outage 10-01 to 10-05 left positions unmonitored for 4 days | Measured returns still carry known distortions; one more outage could leave stops unwatched |
| P10 | **Too many moving targets** | Rules that select live capital changed roughly every two sessions | No rule has been in place long enough to be judged. This is the classic way small accounts lose: switching approach after every drawdown |

---

## 4. Goals against the system

**Goal (Addendum A, owner):** positive net trading P&L; five automatically selected strategies at ~$20 each, executed
through Robinhood, with weaker strategies replaced by stronger ones automatically.

| Goal element | Fit today | What has to change |
|---|---|---|
| Autonomous execution | **Met** | — |
| Five slots, ~$20 each | Met mechanically | Each slot should hold a small *basket* sized by risk, not one name at $20 (AD2, AD3) |
| "Best" strategies | Not met: "best" means highest raw mean, which means most volatile | Risk-adjusted, uncertainty-aware score (AD3, AD6) |
| Replace weaker with stronger automatically | Over-active: replaces on noise | Replacement only on hard-gate failure, or a challenger better by more than its uncertainty plus the switching cost, at a fixed monthly review (AD0, AD6) |
| Positive P&L | Not met: −6.9% in a flat market | Stop the self-inflicted losses (P1–P5) first; alpha second |

**The size of the prize, honestly.** At $82, a genuine edge of 0.5% a month is about $0.40 a month, while the current
book's 17-day swing is several dollars. So the account is a test harness: what matters is the *process* having positive
expectancy, proven on populations of trades, before capital is added. Two things follow:

- **The most reliable positive expectancy a long-only account has is the market's return.** A strategy should earn its
  capital by beating what that capital would earn in a broad index fund, and idle capital should not default to cash
  (decision H3). This is a hurdle and a parking place, not a change of objective: the objective stays positive P&L.
- **The fastest P&L improvement available is removing the self-inflicted losses** (churn, volatility tilt,
  open-auction fills, single-name concentration). None of these needs a new signal.

---

## 5. Response to the reviewer (Addendum H)

**Agreed and adopted** (mapped to stages in §6):

- Signal-level research before strategy bundles; a signal registry with provenance; faithful → implementation →
  variant experiments (AD4).
- Incremental-alpha tests against a baseline on identical rows; ablations; a dependence map; a multiple-testing
  policy (AD4).
- A model ladder starting from linear baselines; per-horizon models; predictions logged before outcomes; abstention
  as a first-class decision (AD5).
- Eligibility separated from ranking; no rotation on small ranking differences (AD0, AD6).
- Runners to SHADOW, with every qualifying signal evaluated including the unaffordable ones (AD7).
- Integrity first: corporate actions, paper-engine fills, ledger to the cent, backups (AD1).
- No new families, search stays frozen, options and crypto stay off, the prospective test stays untouched, no data
  purchase without a value-of-information test.

**Where this plan adds to or differs from the reviewer:**

| Topic | Reviewer | This plan, and why |
|---|---|---|
| What caused the live loss | Weak evidence behind the selections | Agree, but the numbers show **implementation** dominated: churn, volatility tilt, single names. Fixing these (AD2, AD3) is cheap and comes at the same priority as integrity |
| Ranking while the engine is built | Don't rank on backtests alone | Agree for the end state (AD6). In the interim `backtest_first` stays for *eligibility* (it is the better-calibrated score we have: rank correlation +0.21 against +0.03), but it must stop driving daily replacement (AD0) |
| Idle capital | Not addressed | Default sleeve in a broad index ETF, sold when a strategy needs the cash (H3) |
| Position construction | Capital utilisation as a metric | Basket slots and risk-budget sizing (AD2, AD3): the single biggest variance reduction available |
| LEAN replication | Phase F | Lower priority. First compare our implementations of momentum and value against the JKP series **already imported** (`published_signals`); install LEAN only if a discrepancy cannot be explained. LEAN on this 4-vCPU/11.7 GB VM is a large install for a check we can mostly do with data we hold |
| Runners in SHADOW | Wait for prospective shadow data | Agree, and **replay now** with free history: yfinance serves 5-minute bars for ~60 days and hourly bars for ~730 days. The twin-ETF idea has a published, testable form (market intraday momentum, Gao, Han, Li and Zhou 2018: the first half-hour's return predicting the last half-hour's); an hourly version of it can be tested over ~500 sessions today |
| The XGBoost classifier | Benchmark against baselines | Also test it as a **market-timing dial**: `signal_decay.py` found its skill is across dates (good days vs bad days), not across stocks within a date. That is a different use (how much to invest), worth one pre-registered test |

---

## 6. The plan — Stage AD

Priorities: **P0** now (owner decisions, config or very small code), **P1** next two weeks, **P2** following month,
**P3** after evidence.

### AD0 — Stop the bleeding (P0, owner decisions, mostly config)

| Item | Change | Mechanism |
|---|---|---|
| AD0.1 | **No daily replacement.** Holders keep their slot until their own stop, time limit or exit rule, or a hard-gate failure (data defect, newly losing worst-case backtest). Reassessment at a monthly review | Config now: `slots.min_hold_sessions` = a large value, `max_replacements_per_day` 0 outside the monthly review; code later (AD2.3) |
| AD0.2 | **Grandfather holders on rule changes.** A change to ranking or eligibility rules applies to new assignments only | Code (AD2.3); until then, by discipline: no rule change releases a holder |
| AD0.3 | **Runners to SHADOW** (both), or the stock Runner at $5 as an execution probe (fills against quotes) with the twin in SHADOW | `intraday.stage`, `intraday_twin.stage` |
| AD0.4 | **Change freeze on live selection rules** for 20 sessions, safety fixes excepted, so one rule set accumulates evidence | Discipline; recorded in CLAUDE.md |
| AD0.5 | Keep `backtest_first` for eligibility; do not use it to rotate | Follows from AD0.1 |

### AD1 — Integrity (P1; reviewer Phase A)

1. **Paper engine to next-open fills** as its own versioned convention (Addendum F V1), originals kept. Restated and
   live bases then agree.
2. **Corporate actions.** Store raw (unadjusted) closes and split/dividend events beside the adjusted series; compute
   every paper and live return on one consistent basis; restate affected trades beside the originals; count them.
3. **Ledger to the cent.** Reconcile `live_pnl` with `live_equity` using Robinhood's realised-P&L and dividend records;
   explain the $0.24.
4. **Backups** cover `intraday_runner_signals`, `intraday_heartbeat`, `intraday_state`, `minute_bars`.
5. **Forward evaluation by entry cohort on marked equity** (P8), not closed trades only, in the funnel and ranking.
6. **Sign-in watchdog**: alert 48 h before the Robinhood token's expiry and on the first failed refresh.
7. **Real-schema integration test for every live path** (the 10-15 lesson): every module that touches the engine
   gets a test against real tables and the real engine with a simulated broker.

*Acceptance:* the same strategy, data and dates give the same trades and P&L in the simulator, the paper engine and the
report; the integrity report lists every remaining known distortion with its size.

### AD2 — Make live trade what was tested (P1)

1. **Basket slots.** A medium-term slot holds its strategy's top *k* candidates (proposal: k = 4, about $5 each; the
   broker's $1 fractional minimum to be verified), rebalanced only on the strategy's own schedule. The paper fund that
   scores the strategy runs the same *k*, so paper and slot are the same portfolio.
2. **Honour the designed holding period.** Minimum hold = the strategy's hold, unless its stop or exit rule fires.
3. **Replacement rule in code** (AD0.1, AD0.2): monthly review, hard-gate releases only between reviews,
   grandfathering, and a challenger margin of switching cost plus one standard error of the score difference.
4. **Fill parity**: one convention for research, paper and live (next open, or one fixed post-open time).
5. **Entry-timing experiment** (pre-registered): medium-term entries at the open vs at about 10:00 ET, alternating
   sessions, judged on the price obtained against the decision-time quote (`orders.quote_price`, merged with N6) and
   the paper twin. Adopt the better time only if the difference exceeds its uncertainty.
6. **Default sleeve** (if H3 approved): unassigned and Runner-shadow capital in a broad index ETF, sold first when a
   strategy needs cash; reported separately as market exposure, never as a strategy result.

*Acceptance:* for every live slot, the paper twin and the slot hold the same names (± rounding) on ≥ 95% of sessions;
no release outside the review except a logged hard-gate failure.

### AD3 — Risk: size by risk, rank by risk-adjusted return (P1)

1. **Risk-budget sizing**: position dollars = risk budget ÷ stop distance, capped at the slot's capital. Proposal:
   about 0.75% of equity per position (~$0.60 today). A 2%-ATR name at a 3-ATR stop gets ~$10; a 7%-ATR name ~$3. Any
   remainder goes to the default sleeve.
2. **Store per-trade dispersion** in `survivorship_backtests` (and the holdout and paper summaries) so a risk-adjusted
   score is possible.
3. **Risk-adjusted ranking**: score = expected net return per unit of risk (per 20 sessions held), or mean minus a
   variance penalty. Shadow-compare against the current score for 20 sessions before LIVE.
4. **Book limits**: equal-weight beta cap (proposal 1.3) and at most one name above the 90th volatility percentile.
5. **Earnings-date rule, tested not assumed**: backtest whether non-earnings strategies should skip entries within N
   sessions before a scheduled report; adopt only if it helps after costs.
6. **Stop review from data**: MAE/MFE (worst and best excursion) per family from restated trades, to set stop multiples
   that fit each holding period. Research only; live stops change only through AD6's evidence gate.

*Acceptance:* each live position's dollar risk at the stop is within ±25% of the budget; book beta and volatility
limits are enforced and logged.

### AD4 — Alpha Research and Validation Engine (P2; reviewer Phases B and C)

Built mostly from existing parts: `knowledge_library` tables (provenance), `signal_decay.py` (decile spreads by
horizon), `forward_stats.py` (clustered t, Holm/BH, max-T), `composite.py` (IC weights), `walk_forward.py` and
`oos_predictions`, `analog_eval.py`, `published_signals` (JKP).

1. **Signal registry**: extend the knowledge tables with `signal_id`, definition hash, horizon, direction, required
   data and availability time, status ladder, and the trial count per signal. Published results stored apart from
   our replications.
2. **First set: at most 12 signals in 6 families**: 12-1 and 9-1 momentum; FCF/price, earnings yield, book-to-market;
   gross profitability; SUE plus days since the report; 1-week reversal; 60-day low volatility. Faithful (JKP
   definitions) → implementation (long-only top-k basket, next-open, costs) → variants, each with its own
   experiment id.
3. **Bench**: per-date Spearman IC and top-k long-only excess vs SPY, net, at 5/20/60 sessions; date-clustered
   uncertainty; incremental value of each signal over a ridge baseline on identical rows; ablations; a dependence map
   of signal and error correlations.
4. **Multiple-testing policy**: every signal × horizon × variant counted in the registry; Holm/BH at family level;
   promotion needs prospective confirmation, not an in-sample t.
5. **Two cheap, decisive tests first**:
   - *Low-volatility screen*: does excluding the top volatility decile improve the currently eligible strategies' net
     per trade in the survivorship backtest? (Directly tests P2.)
   - *Classifier as timing dial*: does the cross-sectional mean of the walk-forward probability predict SPY's next
     20-session return? (Pre-registered; one look.)

*Acceptance:* every tested signal has a one-page report: standalone and incremental value, net of costs,
uncertainty, by regime where samples allow, and a status.

### AD5 — Prediction service (P2; reviewer Phase D)

Per-horizon models (1, 5, 20, 60 sessions) on excess return vs SPY, next-open to next-open, net. Ladder: historical
mean → ridge → XGBoost (existing) → regime terms. Outputs: expected net return, P(> 0), lower decile, uncertainty.
Append-only prediction log written before outcomes; frozen versions; abstention when expected net return is below
the switching cost or uncertainty too wide.

*Acceptance:* forecasts timestamped and reproducible; calibration tracked; a demonstrated improvement over the ridge
baseline on untouched dates, or the simpler model is used.

### AD6 — Evidence-gated allocation (P2–P3; reviewer Phase E)

1. **Eligibility** (gates): data integrity, honest fills, survivorship-sensitivity flag, out-of-sample pass, minimum
   evidence by horizon, no open defect.
2. **Ranking**: a posterior estimate of net excess return per unit of risk with a **skeptical prior centred on zero**,
   which is what 0 of 54 says. Backtests enter as weak evidence, weighted by their measured predictive power
   (ρ ≈ 0.2); forward evidence enters by independent entry dates, not trade counts; minus the expected switching cost.
3. **Replacement** only at the monthly review and only if the challenger's posterior beats the holder's by more than
   the switching cost with high probability.
4. **Shadow first**: the new selector runs beside the live one for 20 sessions (extend `capital_gate.py`, already in
   shadow).
5. If nothing is eligible, the slot holds the default sleeve, never a weak strategy.

*Acceptance:* every live assignment carries an eligibility record, an evidence summary, a risk summary and the
approval where required.

### AD7 — Intraday track (P1 for replays, P3 for any live)

1. **Stock Runner, historical replay now** on yfinance 5-minute bars (~60 days, ~200 names), with the v0 rule
   approximated at 5-minute resolution and the approximation stated.
2. **Twin-ETF, faithful replication now**: market intraday momentum (first half-hour return → last half-hour return,
   on 30-minute bars, ~60 days) and its hourly approximation (first hour → last hour, hourly bars, ~730 days) for SPY,
   QQQ and IWM, then the bull/inverse-leg implementation. Controls: no trade,
   always long, random direction.
3. **Prospective SHADOW** for both v0 rules, logging every qualifying signal including unaffordable ones, with
   matched controls (same name at a random time; SPY).
4. **Pre-registered decision** after ≥ 30 sessions and ≥ 300 signals: net 30-minute excess vs SPY above cost with
   date-clustered t ≥ 2 → paper, then micro-live with stop conditions; mean ≤ 0 → retire v0; otherwise continue.
   Thresholds never tuned on the shadow sample that judges them.

### AD8 — External benchmarks (P2; reviewer Phase F, re-ordered)

1. Rebuild JKP `ret_12_1` and `be_me` long-leg decile monthly returns with our pipeline (2010–2024); correlate with the
   JKP series in `published_signals`; target ≥ 0.9 for a faithful replication; investigate every gap.
2. LEAN only if a gap stays unexplained.

### AD9 — Reporting that answers "is it working?" (P1)

1. **Per-trade counterfactual**: each live trade beside what the same dollars would have done in SPY over the same
   days, in the daily report and dossier.
2. **Two ledgers**: signal quality judged on paper/shadow populations; execution judged live as the gap between the
   live trade and its paper twin.
3. **Evidence meter**: per strategy, independent dates so far against those needed for a verdict.
4. **Portfolio review trigger** (reviewer §11): at the 10% notice tier, or after 20 sessions behind the
   default-sleeve counterfactual by more than its uncertainty, a written review: prediction, execution, turnover or
   allocation?

---

## 7. Order, dependencies and timing

| When | Stages | Depends on |
|---|---|---|
| This week | AD0 (owner decisions H1–H5) | — |
| Weeks 1–2 | AD1, AD2, AD3 code on a worktree branch; AD7.1/AD7.2 replays; AD9.1 | AD0. Live-path changes merged outside market hours with owner approval, after 5 sessions in SHADOW |
| Weeks 2–6 | AD4 (bench, first 12 signals, two cheap tests), AD8.1 | AD1 (consistent fills and corporate actions) |
| Weeks 4–8 | AD5; AD6 in shadow | AD4 |
| ~December | Prospective test result (unchanged rules); AD6 decides allocation | AD6 shadow record |

**Capital:** no added capital until AD6 makes something eligible on population evidence; then size up per evidence,
not per hope.

---

## 8. Decisions for the owner

| # | Decision | Recommendation | **Owner's answer (2026-10-19)** |
|---|---|---|---|
| H1 | Runners: SHADOW both / stock Runner at $5 as an execution probe / keep LIVE | SHADOW both, plus the replays; a $5 probe only if fill data is wanted | **Both stay LIVE at $5 a trade** (was $20; done, commit 3b40aa1). The replays (AD7.1–7.2) and the logging of every qualifying signal still apply; the pre-registered AD7.4 rule decides paper/retire |
| H2 | Daily replacement off; grandfather holders; monthly review | Yes | **Monthly review.** Between reviews a slot is released only on a hard-gate failure; rule changes apply to new assignments only |
| H3 | Idle capital (empty slots, Runner slots in SHADOW) in a broad index ETF (SPY or VTI) | Yes | **No: idle cash stays in cash.** AD2.6 dropped; an empty or ineligible slot holds cash. SPY stays the reporting benchmark (AD9.1) |
| H4 | 20-session freeze on live selection rules | Yes | **Yes, 20 sessions** (safety fixes allowed). Starts when AD0/AD2.3 take effect |
| H5 | Keep `backtest_first` as the eligibility rule until AD6 | Yes, without daily rotation | **Yes** |
| H6 | Basket slots (k = 4) | Yes, after verifying the broker's minimum order size | **Yes: 4 stocks × ~$5 per medium-term slot**; the paper fund runs the same 4 |
| H7 | Risk sizing and a book limit | Yes; the numbers are the owner's | **H7a: inverse-volatility weights within each slot's basket** (full $20 invested, equal risk per name). **H7b: risk-adjusted ranking plus a book beta cap of 1.3** |
| H8 | LEAN | Defer until the JKP comparison shows an unexplained gap | **Published data first**; LEAN only if a gap stays unexplained |
| H9 | Data purchases | None now; only through a value-of-information test | **Nothing now** |
| H10 | Drawdown at which the whole approach is reviewed, not just paused | Owner to state | **15% from the peak (~$76.70 against $90.26)**: a written review of prediction, execution, turnover and allocation; separate from the automatic 10/20/35% tiers |

**Plan changes from these answers:** AD0.3 (Runners) is replaced by H1: LIVE at $5. AD2.6 (default sleeve) is
dropped; §4's index-fund point stands as the *benchmark* only. AD3.1 becomes inverse-volatility weighting inside each
slot's basket rather than a per-position risk budget with idle remainder. AD3.4 beta cap = 1.3. AD9.4's review trigger
is 15% from the peak (plus the 20-session underperformance test).

## 9. What not to do

Unfreeze the evolutionary search; add strategy families; arm options or crypto; buy data without a defined test;
add capital; change the prospective test; put an LLM in the decision path; tune Runner thresholds on the shadow
sample and count it as validation; change live selection rules after a bad week.

## 10. Risks of this plan

- **Fewer live trades for a while.** SHADOW Runners and no churn mean less activity. That is the point: activity has
  been the loss.
- **The default sleeve carries market risk.** In a bear market it loses. Today's book already carries about twice the
  market's beta, so this lowers risk.
- **A skeptical allocator may leave slots in the index for months.** If nothing clears the evidence bar, that is the
  honest outcome, and it costs nothing relative to trading a non-edge.
- **Basket slots raise the order count** (about 4 per slot rebalance) against `max_orders_per_day` 20; monthly
  rebalancing keeps it well inside.

---

## Appendix — queries behind the numbers (2026-10-19, read-only)

- Live trades: `slot_trades` (mode LIVE) paired OPEN→CLOSE: 23 closes; exit reasons 17 "slot released or reassigned",
  5 "strategy exit signal", 1 intraday trailing stop. SPY counterfactual from `prices` (entry-day open to exit-day
  close).
- Releases: `slot_assignments` 20 RELEASE rows 09-28 → 10-17 (3 for the Runners).
- Volatility percentiles: ATR(14)/close on 2026-10-15 among 3,031 common stocks ≥ $5 and ≥ $1M/day (median 3.25%);
  measured on 10-15, not at each entry date.
- Stop widths: 3 × ATR at entry ÷ entry price from `slot_trades.stop_plan` / `atr`.
- Runner signals: `intraday_runner_signals` (21) against `minute_bars` (New York time), entry at the next bar's open.
- Per-trade dispersion: `paper_trades_restated` net_pct, SD 8.59%, median hold 4 days.

---

## 11. Build log (owner: "go ahead and build", 2026-10-19; "go", 2026-10-20)

| Item | State | Where | Result / note |
|---|---|---|---|
| AD0 H1 Runners at $5 | **LIVE** | config.yaml | 5 trades on 10-19 (1 on 10-16); no signal refused for cash |
| AD0/AD2.3 monthly review, hard/soft releases, grandfathering | **LIVE** | slots.py, config `slots.review` | first review 2026-11-02; margin = switching cost + 1 SE |
| AD1.3 ledger to the cent | **daily [9k7]** | ledger_check.py | 12 days match Robinhood's realised P&L; account gap +$0.02 (the $0.23 was mark timing) |
| AD1.4 backups | done | backup.py | Runner tables, restated trades, alpha registry, allocator, timing, forecasts |
| AD1.5 open positions in the funnel | done | funnel.py | `open` and `+open` columns |
| AD1.6 sign-in watchdog | **fixed** | robinhood_mcp.py | could never fire before (stamp erased by refresh; missing notify function) |
| AD1 integrity report | done | integrity_report.py | one page; corporate-action text corrected 10-20 |
| Item 4 corporate actions | **LIVE in the paper engine** | paper_trading.adjusted_entry, `_exit_values`, `_mark_value` | open positions re-anchored to the adjusted series (entry, stop, take-profit); 1,472 of 34,098 open positions affected, no stop verdict changed. Extended 10-20 to the rotation and conviction steps. Restated record was already right (both legs on one series) |
| LIVE splits | **LIVE (trader, from the 10-20 13:00 UTC run)** | slot_trader.split_adjust | broker/ledger a clean split ratio AND yfinance confirms -> zero-P&L CLOSE + restated OPEN (qty x k, price and ATR / k, remaining time limit, reason kept); unconfirmed left to reconciliation. Reports, ranking, attribution, feedback, digest and discovery treat it as one continuing position, not a trade |
| AD2.1 basket slots | SIMULATION (shadow) | slot_trader.py, config `slots.basket` | LIVE after the freeze; reports now basket-aware (item 1) |
| AD2.5 entry-timing experiment | built, OFF | slot_trader.entry_wait | switch on after the freeze |
| AD3.2 dispersion | done | survivorship_backtest.py (+ `--refill`) | 4,188 rows of the current build carry it |
| AD3.3 risk-adjusted order | shadow | ranking.risk_terms, `slots.score_mode: raw` | flip after 20 sessions of shadow |
| AD3.4 beta cap 1.3 | **LIVE** | slot_trader.beta_block | refuses a purchase only |
| AD3.5 earnings | studied; **backtest registered** | earnings_study.py, risk_sweep.py | 1.64x dispersion, no reward -> `earnings_skip_v1` registered 10-20 (skip within 5 sessions of a report; covered ticker-years; predicted-date check) |
| AD3.6 stops | studied; **backtest registered** | stop_study.py, risk_sweep.py | `stop_width_slots_v1` registered 10-20 (ATR 1.5-6, paired by trade, t >= 2.58 and most years); 23 strategies frozen |
| AD4 alpha bench v1 (one look) | done | alpha_bench.py | 0 validated, 8 replicated; volatility screen helps momentum/reversal baskets |
| AD4 timing dial v1 (one look) | **PASS** | alpha_bench.py | corr +0.355, NW t +6.45, 94% of folds; no fold-boundary leakage (purged) |
| Timing dial, prospective | **shadow daily [9k5]** | timing_shadow.py | `market_timing_dial_shadow_v1`: 120 sessions, corr > 0 and NW t >= 2 (~April 2027) |
| AD5 prediction service | **shadow daily [9k6]** | predict_service.py | ridge kept at 5/20/60 (val IC +0.04/+0.06/+0.09); XGBoost negative within a date |
| AD6 allocator | **shadow daily [9k2]** | allocator.py | overlap 1 of 3; no swap beats the switching cost |
| AD7 Runner replays | done | intraday_replay.py | stock -0.11%/signal (t -3.3), twin -0.14%; MIM absent; prospective rule registered 10-19 23:45 UTC |
| AD8 JKP check | done | external_benchmark.py | spread corr 0.86 (momentum), 0.73 (value): partial |
| AD9 attribution + evidence in the daily report | **LIVE (Telegram)** | live_attribution.py, eod_report `VS THE MARKET / EVIDENCE` | account vs SPY today and since start; test progress |
| Item 1 basket-aware reports | done | live_pnl, eod_report, control_center(_extra), telegram_bot, daily_snapshot | pre-existing defect fixed: Control Center `max_hold_days` was inside a comment |
| Item 3 next-open fills in the paper engine | **built; first daily step 2026-10-21** | paper_trading._step_next_open, `paper_pending`, config `paper.fills` | decide on the close, fill at the next open (sells first, gaps through stops; buys sized at the open); decision dates kept, so restate/audits/prospective test price the same fill (no second shift); corporate-action flag per leg; held stocks below the purchase floors are stopped on their real close (they were not, before); `paper.fills: close` rolls back. Rehearsed on a copy of the database before the merge |
| accounting v2 | built | accounting.py, paper_trading.as_recorded | open paper positions valued on the adjusted series (v1 booked splits/dividends as open P&L); Kalman positions anchor on the open they paid |

### Item 3 — next-open fills inside the paper engine: BUILT 2026-10-20 (branch `paper/next-open-fills`; design kept below)

Why not tonight: about twenty modules read `paper_trades` / `paper_positions`, and several (restate_paper, audit_forward,
audit_execution, prospective_eval's open marks) shift entries to the next open themselves. Converting the engine without
changing them would shift those trades twice and alter inputs to a locked experiment.

Design, in the order it must land (one branch, outside market hours, full suite, a dry run on a database copy):
1. `paper_pending` table (run_id, ticker, side, decided_on, reason, stop rule inputs). A step on day D decides on the
   close of D and writes pending orders; the next step fills them at the open of the first session after D (entries
   sized at that open; exits booked at that open, gaps included); an order with no open for 3 sessions is cancelled.
   Cash is debited at the fill, not at the decision (accounting stays on a liquidation basis).
2. Keep `entry_date` / `exit_date` as the DECISION dates and add `fill_basis` ('close' | 'next_open') and `fill_date`
   columns. Downstream code that keys on decision dates (funnel, the locked prospective test, audit dates) is then
   unchanged.
3. `restate_paper`: rows with fill_basis 'next_open' are copied as they are (no second shift); rows with 'close' are
   restated as today.
4. `audit_forward`, `audit_execution`, `prospective_eval` (open marks): skip their own next-open shift for
   'next_open' rows.
5. Equity and marks unchanged (close of D); a position pending exit is still marked until it fills.
6. Conviction, rotation and Kalman steps keep their own conventions (documented).
Acceptance: the same strategy and dates give the same trades in the simulator, the paper engine and the restated record.

### Still open after this build
- Run `risk_sweep.py --run` (after a daily run, bounded), then `--report --write`; either result is recorded, and a
  passing one is a candidate for a paper variant, not a live change.
- Found by the item 3 rehearsal (2026-10-20): the close-fill engine never stopped a held stock below the $5 purchase
  floor and booked it at its ENTRY after 4 holding periods — 35 closed trades at 0.00% whose true move was -15% to
  -96% (mean -38%; the restated record already has the real figures), and 701 open positions in 63 such names
  (median -44%) waiting to be booked the same way. Fixed in the next-open path; the 10-21/10-22 runs book the sales.
  The original rows stay as recorded (restatements beside originals); accounting still reads their 0.00% — a v3 that
  takes closed-trade P&L from the restated record is the follow-up.
- Kalman trades record FILL dates (they buy at the session's open), so the restatement prices them one session late
  (2 trades, none flagged). Small; fix in kalman_pair (record the decision date) when that family is touched.
- (Closed 10-20: re-anchoring now covers the rotation and conviction steps; `paper_trading.close()` books no exits, so
  there is nothing to re-anchor. The LIVE split handler is built; see the table.)
- After the 20-session freeze (~2026-11-16): baskets in LIVE, risk-adjusted order, entry-timing experiment, allocator
  from shadow to deciding — each an owner decision on its shadow record.
