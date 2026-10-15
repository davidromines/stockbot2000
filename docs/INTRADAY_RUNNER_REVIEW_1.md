# Independent review 1 of the Intraday Momentum Runner plan (received 2026-10-15)

Reproduced as written by the owner's independent reviewer. Claude's disposition of every point is in `docs/INTRADAY_RUNNER_PLAN.md`, section "Revision 2".

---

Independent review: Intraday Momentum Runner
I've reviewed the plan. My overall recommendation is approve the direction, but make several changes before committing to implementation.
The plan has a lot going for it: it treats the Intraday Momentum Runner as a separate strategy, recognizes that your existing momentum tests have been negative, accounts for trading costs, includes explicit stop and exit logic, and requires evidence before allowing the strategy to trade live. It also directly addresses the failure you've been seeing: positions getting bought and then held while they lose money instead of being managed as short-term trades.
However, I see a few important weaknesses. Some could waste weeks collecting data without answering the right question; others could cause the system to miss its own exits or allocate capital based on misleading backtest results.
My recommendation is to keep the core architecture, tighten the safety and evaluation rules, and then commit to a bounded implementation—not commit to live trading.
1. What I would keep
These are strong design decisions that I would not change.
- A separate intraday strategy. It should not be mixed into the existing medium-term strategy-ranking logic.
- Explicit holding-period and end-of-day exits. Intraday positions should not quietly become multiday holdings.
- A monotonic trailing stop. Once the stop moves upward, it must never move downward.
- Realistic execution assumptions. A stop trigger is not a guaranteed fill price, especially during a fast decline.
- A dedicated shadow simulator. Record signals even when the live portfolio cannot take every trade.
- Pre-registered evaluation and comparison strategies. The system must not keep changing thresholds until it finds an attractive historical result.
- A separate live activation gate. Building the strategy must not automatically enable it to trade real money.
The plan explicitly includes these features and a useful suite of failure-handling tests.
One expectation needs to stay clear throughout the project: the goal is to discover a profitable strategy, not to assume the strategy will be profitable because we've built a sophisticated trading system. The implementation should make it easier to find and exploit a genuine edge if one exists, while stopping quickly if the evidence says otherwise.
2. The changes I would require before committing
A. Do not disable a trading restriction without confirming the actual account rules
Priority: Critical
The plan says the day-trade guard has been disabled because the owner believes Robinhood changed its rules in June 2026. It also acknowledges that Claude has not independently confirmed the broker's current requirements.
I would not treat the account's ability to place an order as proof that every planned trading pattern is permitted or free of restrictions.
Before live activation, require Claude to:
1. Verify the current rules for this specific Robinhood account type using Robinhood's official documentation and the account's displayed restrictions.
2. Confirm applicable buying-power, settlement, and intraday trading requirements.
3. Keep the software's safety controls separate from regulatory or broker restrictions.
4. Test that an account restriction or rejected order stops new entries appropriately.
Important distinction: I'm not saying the old day-trading restriction definitely still applies. I'm saying the plan itself identifies this as unverified, so we should close that gap before live trading.
The day-trade guard being configurable is sensible. Removing a safety check based on an unverified assumption is not.
B. Resolve the timeline inconsistency
Priority: High
The plan describes an initial verdict after approximately 60 sessions, followed by an untouched 20-session prospective holdout and at least 20 paper-trading sessions.
Those are three separate evidence requirements:
- 60 sessions of shadow evaluation.
- 20 subsequent sessions of prospective validation.
- At least 20 sessions of paper trading.
If they must happen sequentially, the complete process requires approximately 100 trading sessions, not 60. Some activities could overlap, but only if their data and evaluation rules remain genuinely independent.
I recommend keeping the 60-session shadow requirement, the untouched 20-session holdout, and the 20-session paper requirement. Do not shorten them just to get the strategy into production sooner.
Have Claude correct the milestone dates and state explicitly which stages can overlap. Also distinguish an initial research result from a completed validation decision.
C. Make market-data quality a hard gate for live trading
Priority: Critical
The current database contains 18 sessions of one-minute bars for only 20 tickers. The plan proposes expanding that to approximately 200 stocks using free data and gathering live bid/ask observations to estimate actual spreads.
That's a reasonable starting point for research. It is not yet enough to justify live trading.
I would require three specific conditions:
1. Live quote verification: Confirm that the selected quote source actually returns usable bid, ask, and timestamps for equities. Do not assume that it does.
2. Execution-cost verification: Measure the difference between decision prices and actual fills, including spread, slippage, and rejected orders. Keep estimates conservative when samples are small.
3. Historical-data verification: Confirm that timestamps, missing bars, split adjustments, and universe membership cannot introduce look-ahead or survivorship bias into the evaluation.
If reliable bid/ask data is unavailable, the system can still conduct shadow research with conservative assumptions. But it should not quietly substitute a last-trade price for a reliable executable price and then claim a strategy has passed.
I would not purchase a paid data source yet. First prove that the free collection process works and identify the specific data limitation that a paid source would solve. The plan's proposed data-quality report and measured-spread model are appropriate first steps.
D. Tighten the protection against a failed exit
Priority: Critical
The design relies on software-monitored stops because the existing fractional-dollar order path does not support resting broker-side stops. It proposes checking open positions every 15–30 seconds.
That creates an important limitation: a trailing stop does not protect the account while the service is unable to detect a decline or submit an exit.
For example, suppose the system buys at $100 and the trailing stop rises to $101.97 after the price reaches $103. If the price drops rapidly through the stop between checks, the eventual sale may be below $101.97. If the service crashes or the broker rejects the sell order, the exposure could last longer still.
The proposed failure handling is a good start, but I would add these requirements:
- Prove the monitoring cadence: Measure actual quote latency, API response times, and throttling under the intended workload before deciding that 15–30 seconds is viable.
- Set an explicit service-health rule: If reliable monitoring cannot be restored, halt new entries and raise an alert.
- Define a failed-exit escalation procedure: Retry safely, reconcile outstanding orders, and alert the owner. Never create duplicate sell orders or assume an exit succeeded without confirmation.
- Test broker-side protection: Investigate whether a supported order type can provide protection independently of the local service. Do not assume it works with fractional-dollar positions.
- Test forced flattening across daylight-saving changes: Use the US market calendar and Eastern Time, not a fixed UTC time that silently changes its relationship to the market close.
The plan already calls for a resident service, state persistence, duplicate protection, and exit-failure tests. Keep those requirements.
I would also make a successful restart-and-reconciliation test mandatory before any live order is permitted.
E. Define exactly how a trade is simulated
Priority: High
The plan says the simulator will assume the adverse price extreme occurs first within a bar, and that a gap through a stop must be filled at the next available price rather than at the stop price. Those are good conservative rules.
However, the implementation needs to be precise about what happens when an entry and a potential stop or trailing-stop update occur within the same one-minute candle.
Suppose the strategy enters during a candle whose high occurred before the entry. The system must not use that earlier high to move the trailing stop upward. A candle's high and low alone do not reveal the order of every price movement inside it.
Require Claude to:
- Prevent the entry candle's pre-entry high from influencing the trailing stop.
- Apply consistent, conservative assumptions wherever the bar data cannot establish event order.
- Model the delay between observing a signal, submitting an order, and receiving a fill.
- Apply realistic entry and exit prices, spread, slippage, and fees where applicable.
- Track trigger price separately from actual execution price.
The existing stop-test list is strong; these rules should be part of the simulator's explicit specification, not left to implementation interpretation.
F. Don't let a positive backtest automatically displace existing strategies
Priority: High
The plan recommends eventually reserving two of the five slots for the Intraday Momentum Runner, while leaving the existing medium-term allocation in place during shadow and paper testing. It also identifies backtest_first as a separate, unresolved change.
I agree with keeping the existing holders in place while the new strategy is only in shadow or paper mode.
I do not recommend treating backtest performance alone as sufficient evidence to decide which existing live holdings should be removed. Your earlier audits already raised the concern that historical performance has not reliably translated into forward performance.
My recommendation:
- Continue the Intraday Runner work independently.
- Keep the current allocation during SHADOW and PAPER.
- Before live activation, produce a report showing the proposed slot changes, current holdings, realized and unrealized P&L, and the evidence supporting each replacement.
- Require your explicit approval before selling existing positions to make room for the Runner.
- Reassess backtest_first separately rather than assuming it is validated because this new project is progressing.
The new strategy should have to earn its place; it should not inherit credibility from the sophistication of its implementation.
G. Make the statistical pass criteria clearer, not easier
Priority: High
The plan proposes at least 60 sessions, at least 300 signals across at least 40 dates, a date-block bootstrap lower bound above zero, and performance better than random-entry and simple-momentum controls, with an adjustment for testing multiple configurations.
That is a sound direction. The important detail is that 300 signals are not necessarily 300 independent observations. Many stocks can move together on the same day, and repeated signals in one market regime may provide less evidence than the raw trade count suggests.
I would retain the date-based evaluation and require Claude to:
- Report both signal counts and the number of independent trading dates.
- Calculate uncertainty using a method that respects dependence between observations on the same day.
- Freeze the configuration before the untouched holdout.
- Include all tried configurations in the experiment ledger.
- Report the results for every control, not just the winning strategy.
- Define a minimum economically meaningful net edge that is larger than plausible uncertainty in execution costs.
I would not lower the pass threshold to accommodate the small account. A $20 position makes the dollar returns small; it does not make weak evidence more reliable.
One refinement: require the report to show net expectancy per trade, total net P&L, drawdown, and sensitivity to higher-than-measured trading costs. A strategy that is profitable only under optimistic execution assumptions has not passed.
3. Answers to the plan's eight review questions
Here are my decisions on the questions Claude explicitly asked.
#	Question	My recommendation	Reason
1	Are the statistical pass criteria too strict?	Keep them, with clearer definitions.	A positive result should survive costs, uncertainty, and comparison against controls. A small account is not a reason to weaken the evidence.
2	Should SHADOW log every qualifying signal, not just two slots' trades?	Yes.	This gathers evidence faster. Keep simulated signals separate from actual paper/live trades, and account for same-day correlation in the statistics.
3	Should reversal be tracked as a control?	Yes.	Existing shadow results reportedly favor some reversion rules over momentum rules. Measuring reversal alongside momentum can reveal whether the underlying assumption is wrong.
4	Are the proposed risk limits appropriate?	Reasonable starting limits, subject to clarification and testing.	They limit exposure, but the system must account for gaps, costs, and failed exits.
5	Is free one-minute data acceptable?	Yes for initial research; not automatically sufficient for live approval.	First establish data quality and reliable execution-cost estimates. Reconsider paid history only if a specific limitation prevents valid testing.
6	Is a 15–30-second polling service acceptable?	Only after testing it under realistic load.	The plan identifies prior HTTP 429 throttling and unverified equity bid/ask support. A faster loop is not useful if the data source cannot support it reliably.
7	Are slots 3 and 5 reasonable, and should existing strategies keep them during SHADOW/PAPER?	Keep existing holders during SHADOW/PAPER. Require a fresh allocation review before LIVE.	The slot numbers are implementation labels, not evidence of which strategies deserve capital.
8	Should backtest_first remain enabled?	Do not treat it as validated. Review it separately before any further live reallocation.	The audit history raises concerns about relying on historical performance alone. The Runner should not distract from that separate risk.


These answers preserve the plan's basic design while tightening its evidence and operational requirements. The slot-allocation and backtest-first questions are explicitly identified as separate from the Runner's strategy logic in the document.
A closer look at the proposed risk limits
The proposed starting limits are:
- $20 maximum position.
- $0.50 maximum intended loss per trade.
- $2 maximum intraday realized loss.
- Three entries per session.
- Two simultaneous positions.
Those are sensible experimental limits, but I would make three things explicit before implementation.
First, define what the $0.50 loss limit actually means. A stop can be placed to target that loss, but a market order cannot guarantee that the final loss stays below $0.50. The configuration and reports should distinguish intended stop risk from actual realized loss.
Second, define whether the daily loss limit includes unrealized losses. My preference is to have both a realized-loss limit and an account-level exposure/drawdown safeguard. Otherwise, a losing open position could remain exposed even after the day's realized loss reaches its limit.
Third, prevent repeated re-entry from circumventing risk controls. A strategy must not repeatedly buy the same stock after being stopped out simply because a new signal appears. The proposed cooldown is useful, but it should be tested and logged.
Keep the existing risk limits authoritative. The plan already says the strategy must not weaken them.
4. One important product decision: what counts as success?
I want to distinguish two goals that can otherwise become confused.
Goal A: Build a working intraday trading engine.
It scans stocks, calculates signals, submits orders through the existing execution path, manages trailing stops, closes positions, and recovers safely from failures.
Goal B: Build an intraday strategy that actually makes money.
It selects entries whose subsequent price movements are favorable enough to cover spreads, slippage, and other trading costs. It also demonstrates that result prospectively rather than just in a historical simulation.
Goal A is an engineering deliverable. Goal B is an empirical result that the engineering work must help establish.
The plan appropriately recognizes that the existing momentum evidence is unfavorable: its reported 288 shadow trades averaged −0.05% per trade, with the three momentum-type rules negative.
That makes the scanner's entry quality especially important. A trailing stop can manage a position after entry, but it cannot turn a consistently poor entry signal into a profitable strategy by itself.
I would therefore add one requirement to the evaluation report:
Break down results by entry condition and explain which conditions contribute to, or detract from, net performance. Show whether the strategy's advantage comes from entry selection, exit management, or both.

For example, the report should help answer:
- Do high-volume breakouts outperform ordinary short-term momentum?
- Does relative strength versus the market improve results?
- Are entries too extended by the time the scanner detects them?
- Do the stops cut losing trades without consistently cutting winners too early?
- Does the strategy remain profitable after costs are increased?
- Are profits spread across many dates or concentrated in a few exceptional sessions?
That is how we learn something actionable instead of merely receiving a report that says a strategy passed or failed.
What about your example of buying at $100 and trailing the stop?
The plan's test example is correct mathematically:
- Entry: $100.
- Highest eligible price: $103.
- Trailing-stop distance: 1%.
- Trailing-stop trigger: $103 × 0.99 = $101.97.
But the strategy's profitability must be evaluated using the actual exit fill, not the $101.97 trigger.
If it sells at $101.90, the gross gain is $1.90 per share, or 1.90% before costs. If it sells at $101.50, the gross gain is 1.50%. Both outcomes differ from the nominal 1.97% trigger-based return.
And with a $20 position, a 1% price move represents roughly $0.20 before costs. The plan correctly recognizes that small-dollar positions make execution costs particularly important.
5. Recommended changes to the plan before approval
I would ask Claude to revise the plan with these specific changes:
1. Resolve the validation timeline. Distinguish the initial 60-session shadow assessment from the subsequent holdout and paper-trading requirements.
2. Add a broker/account-rule verification gate before any live activation, including confirmation of the actual account type and applicable trading restrictions.
3. Make live quote quality and exit reliability hard gates. Do not permit LIVE if equity bid/ask availability, data freshness, order handling, or reconciliation is unverified.
4. Strengthen simulator timing rules. Explicitly prevent pre-entry prices from influencing trailing stops and model signal-to-fill latency conservatively.
5. Clarify risk accounting. Define intended versus realized stop losses, treatment of unrealized losses, and re-entry cooldown behavior.
6. Require a net-edge sensitivity report. Show results after measured costs and under more conservative cost assumptions.
7. Keep existing strategies in their slots during SHADOW and PAPER. Require your approval for any subsequent live reallocation.
8. Review backtest_first separately. Do not treat backtest results alone as proof that a live strategy should receive capital.
9. Make every stage produce a concrete deliverable. Code, tests, configuration, and reports—not merely another proposal or investigation.
10. Keep LIVE disabled by default. Neither completion of the code nor a positive exploratory backtest should automatically arm the strategy.
These are targeted changes, not a request to redesign the entire project.
6. The implementation sequence I would approve
The plan's milestones are generally well structured. I would preserve their order, with these acceptance gates:
Stage	Work	Acceptance condition
M0	Finalize plan	Review comments incorporated; scope and gates approved.
M1	Data foundation	Collector runs reliably; quote capabilities and data coverage are verified and reported.
M2	Stops and simulator	Stop, fill, gap, cost, and failure tests pass.
M3	Scanner and SHADOW	Signals and rejection reasons are logged; no-look-ahead tests pass.
M4	Evaluation	Walk-forward report includes controls, all attempted configurations, net results, and uncertainty.
M5	Integration	Existing trading behavior remains intact; new risk controls and slot isolation pass regression tests.
M6	Service and PAPER	Resident service survives restart, handles failures safely, and completes the required paper-trading period.
M7	Validation decision	Pre-registered criteria determine whether to continue, revise, or stop.
M8	LIVE-micro	Requires a separate, explicit decision from you after reviewing the evidence.


This keeps the scope bounded and prevents the engineering work from becoming an endless research project. It also prevents the opposite failure: rushing into live trading before the execution and evidence are trustworthy. The original plan already lays out these milestones and reserves live activation for a later owner decision.
Final recommendation
I would approve this plan in principle, subject to the revisions above.
The architecture is sensible, the plan is honest about the weak existing evidence, and the proposed strategy directly addresses your desire for active short-term trading rather than accidentally holding losing positions for days.
The two issues I would not compromise on are:
- Reliable, tested exit handling. A trailing-stop formula is not enough if the service or broker cannot execute the exit reliably.
- Evidence of positive net performance. We must not confuse a completed implementation or a positive backtest with a demonstrated trading edge.
I would also keep the account-rule verification and the independent review of backtest_first on the pre-live checklist.
My suggested next step: Have Claude incorporate these review comments into the existing plan, without starting implementation yet. Review the revised version once, then commit to the bounded implementation milestones. That gives you a concrete build path without prematurely authorizing live trading.
The goal is to stop debating the architecture once the requirements are clear and start building—and then let disciplined testing determine whether the Runner deserves real capital.

---
