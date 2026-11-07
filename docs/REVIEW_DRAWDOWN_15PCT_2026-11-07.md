# Written review at 15% below the peak — 2026-11-07

**Trigger.** Owner decision H10 (2026-10-19, `docs/STAGE_AD_PROFITABILITY_PLAN.md` §8): at 15% below the peak, a
written review of prediction, execution, turnover and allocation. The rule changes no trading by itself. The
account first closed through the line on Friday 2026-11-06 ($76.24 against a peak of $90.26, −15.5%); the
`STRATEGY_REVIEW` alert went to Telegram on 11-05 and 11-06 (`system_events`, kind `drawdown_tier`).

Figures are to the 11-06 close. The trade ledger reconciles with Robinhood within $0.01 (`reports/ledger_check_2026-11-06.md`).

## 1. Where the account stands

| | Account | SPY |
|---|---:|---:|
| Launch 2026-09-24 | $87.71 | 767.18 |
| Peak (intraday 09-25; best close $89.93) | $90.26 | |
| Close 2026-11-06 | **$76.24** | 735.29 |
| Since launch | **−$11.47 (−13.1%)** | −4.2% |
| 09-24 → 10-19 (before the Stage AD changes) | −$5.61 (−6.4%) | −0.1% |
| 10-19 → 11-06 (after them) | −$5.86 (−7.1%) | −4.1% |
| This week (10-30 → 11-06) | −$7.00 (−8.4%) | −2.7% |

Drawdown tiers: the 10% notice has been on since 11-02; the 15% review is this document. New entries pause automatically
at 20% below the peak ($72.21); everything stops at 35% ($58.67).

## 2. Where the $11.47 went

| Part | Trades | Net | Note |
|---|---:|---:|---|
| Medium-term trades closed before 10-19 | 22 | −$6.73 | 17 sold by slot reassignment (−$9.30, mean −3.30%); 5 by their own exit rule (+$2.56, mean +3.14%) |
| Medium-term trades closed since 10-19 | 2 | −$3.85 | both stops: OVV −8.3% after 16 sessions, CRM −11.0% after 17 |
| Intraday Runners (slots 3 and 5, $5 a trade) | 65 | −$0.25 | stock 39 trades −$0.21; twin-ETF 26 trades −$0.04; 46% winners |
| Open positions: NTLA, OVV, MA | 3 | −$0.61 | |
| Fees and rounding | | −$0.03 | |
| **Total** | | **−$11.47** | |

Before 10-19 the loss was turnover. Since 10-19 it is three single stocks held through a falling market.

## 3. Prediction — do the strategies pick winners?

No, on every forward measure available.

- **The live medium-term trades that ended by their own rule or stop:** 7, mean −0.50%. Too few to mean anything alone.
- **The paper league:** this is where prediction is actually tested, because it holds thousands of trades.
  - The pre-registered prospective test, `forward_families_prospective`, is at 17 of 20 pooled entry dates (20,096 trades). It is interim and decides nothing yet. All eight families are negative net, −0.91% to −6.22% per trade, and all are below SPY over the same days (excess −0.77% to −6.83%). The verdict is due about early December.
  - The funnel (11-06): of 86 families with 20 or more forward trades, 4 have a positive honest mean. The best-sampled of the four is `momentum` at +0.30% (37 entry dates, clustered t +0.3). `lab_search` is −1.03% per trade on 23,906 trades (clustered t −2.3). No family passes.
  - The shadow capital gate: 0 of 1,497 strategies eligible; 0 of the 3 slot holders.
- **The slot holders' own paper records are poor, and the ranking does not see them.** `ranking.evidence_mode: backtest_first` (owner 10-14, kept on 10-19) scores a strategy on its backtest alone; paper results are shown but never scored. The score therefore cannot move:

  | Slot | Strategy | Backtest / trade | Own paper record | Score 10-14 → 11-05 |
  |---:|---|---:|---|---|
  | 1 | Cash Flow, Accruals (quality) | +2.3% | 2 trades, −7.4% | 0.025 → 0.025 |
  | 2 | Valuation of R&D Expenditures | +4.0% | 29 trades, −10.4% | 0.024 → 0.024 |
  | 4 | Earnings Surprise age=10 hold=60 | +1.5% | 21 trades, −4.2% | 0.021 → 0.020 |

  Nothing in today's rules lets a bad forward record release a holder. The monthly review compares scores, scores
  are backtests, and the 20-session freeze plus grandfathering keep holders in place.

## 4. Execution — are the trades carried out as intended?

Yes, with two defects.

- The ledger matches Robinhood to the cent on all 25 days compared. Buys filled +0.02% against the decision-time quote on average (81 orders).
- Stops fired as designed: the first two medium-term stops, both at their computed levels.
- Live quotes: no quote halts since the 10-21 fix.
- One Robinhood error stopped a single run on 11-05; the next run was normal.
- **Defect 1, re-entry after a stop.** OVV was sold on its stop at $61.45 on 11-05 and bought back by the same strategy 6 minutes later at $61.26, with a new, lower stop. The stop realised the loss but kept the exposure. Fix: no re-entry in a stopped name for a set number of sessions.
- **Defect 2, a false halt.** The 5-minute reconciliation can catch a Runner order in flight (10-28, RWM): one false halt, cleared on the next run. Fix: skip a symbol while an order on it is open.

## 5. Turnover — is the system trading too much?

No longer.

- **Before 10-19:** 17 of 24 medium-term exits were forced by slot reassignment, with a median hold of about 4 sessions against designed holds of 21–252.
- **Since 10-19:** zero forced exits. Both medium-term exits were stops after 16–17 sessions. The first monthly review (11-02) released nothing.
- **The Runners** trade about 4 round trips a session at $5. Their cost is small, but so is any possible gain.

The churn fix did what it was designed to do.

## 6. Allocation — is the money spread sensibly?

No. Single-name risk is the main open problem.

- **One stock per slot.** Each slot is $20, about 26% of the account, so three single stocks carry the overnight risk.
- **Most of the loss is stock-specific.** Regressing the 31 daily account returns on SPY gives a beta of 0.81 (correlation 0.56). The market explains about 3.3 points of the roughly 13.6-point summed daily loss; the other ~10.3 points come from the stocks themselves. The daily excess return is −0.33% (t ≈ −1.5), so a negative edge is not established either.
- **The book beta cap (1.3) did not bind.** The book's beta is 0.75, but the cap measures market exposure only:
  - NTLA has a beta of 2.1 and about 95% a year of stock-specific volatility.
  - OVV (oil) has a beta of −0.35 and fell 15% in the week.
- **Stops are wide.** 3× ATR stops sit 16–33% below entry (10-19 finding), so one slot can lose $3–6 before its stop fires. The stop-width experiment favours wider stops, not tighter.
- **The fix exists but is not live.** Basket slots (4 names, inverse-volatility weights) still run in SIMULATION only, with first basket entries on 11-05/06. There is nothing to compare against yet.

**Is this luck?** Partly, possibly. At this account's daily volatility (1.53%), a strategy with zero edge has about
an 8% chance of a 15% drawdown within 31 sessions (bootstrap of the account's own de-meaned daily returns). So the
drawdown is unlucky under zero edge, but not extreme. The live account is too small and too short to tell no edge
from a small negative one. The paper league can tell them apart, and it reads negative.

## 7. Conclusions

1. **The machinery works:** fills, ledger, stops, reconciliation, alerts and the churn fix all behave as designed.
2. **There is no edge:** the forward evidence, now 17 of 20 prospective dates, is negative against both zero and SPY.
3. **The live loss since 10-19 is single-name risk** in a falling market, on holders whose own paper records were negative and which the ranking cannot see.

## 8. Options for the owner

No trading change follows from this review unless the owner chooses one.

| Option | What changes | For | Against |
|---|---|---|---|
| A. Continue unchanged | nothing until the December verdicts | rules set in advance stay set | the evidence already reads negative; same single-name exposure |
| **B. Reduce risk, keep running (recommended)** | (1) re-entry cooldown after a stop; (2) skip symbols with an order in flight in reconciliation; (3) basket slots LIVE when the freeze ends (~11-16); (4) at each monthly review, release a holder whose own paper record has ≥20 trades and is net negative | keeps live evidence coming at lower single-name risk; (1) and (2) are defect fixes | (3) and (4) are rule changes the owner must approve; $5 basket legs cost more relative to size |
| C. Medium-term slots to SIMULATION | no new medium-term live buys; held positions exit by their own rules | protects capital while the paper league decides | no live medium-term evidence (paper still accrues) |
| D. All live trading to SIMULATION | as C, plus the Runners stop | most capital protected | the live machinery stops being exercised |

**Recommendation.**
- Take B now: items (1) and (2) outside market hours, and (3) and (4) on the owner's approval.
- Pre-register a fallback to C. If `forward_families_prospective` fails at its verdict (about early December), the medium-term slots move to SIMULATION until a strategy passes the capital gate.
- Apply the same rule to the Runners: if `intraday_runner_v0_prospective` fails (interim: stock −0.106% per signal, t −1.84; twin −0.10%, t −1.45), they move to SHADOW.

The account exists to prove a simple profit before more capital is added (owner, 10-19). Nothing so far is that proof.

## 9. Questions for the independent reviewer

1. Is the reading "machinery works, no edge" fair, or is there a measurement in the paper league that could make it look worse than it is? Two candidates: the long-only exposure through an October–November decline, and the interim marks on open positions.
2. Should forward evidence count in slot selection, either as a release rule (option B4) or a return to blending, given the 10-14 move to `backtest_first`?
3. Is the 20% automatic entry pause still the right next tier, or should the review tier itself pause medium-term entries?
4. Given the paper league's result, is any further strategy research worth doing on this data without paid delisted data, or is the better use of the system as a forward-evidence engine with live capital parked?
