# Addendum G — Intraday Momentum Runner (entered 2026-10-14; NOT BUILT)

> **Context.** Received from the owner 2026-10-14, together with a closing recommendation from the owner's independent
> reviewer ("7. My final recommendation"). Reproduced **as written** below the line. Nothing in the text between the two
> horizontal rules has been edited. The implementation plan that responds to it is `docs/INTRADAY_RUNNER_PLAN.md`; the
> plan, not this document, records Claude's findings, assumptions and objections.
>
> **Owner instructions that came with it (2026-10-14):** ask questions; enter the prompt in the project plan as written;
> review it and think hard about how to implement it in the current systems; build it into **TWO of the existing five live
> slots**; produce a detailed plan for the independent reviewer **before** any implementation.
>
> **Owner answers to Claude's questions (2026-10-14):**
> 1. *Day trades.* The owner states that Robinhood no longer has the 3-day-trade / $25,000 pattern-day-trader limit: FINRA's
>    new intraday margin standards replaced the PDT rule, and Robinhood implemented the change on 2026-06-04 (no
>    rolling-5-day limit, no $25k minimum for day trading, existing PDT flags removed from margin accounts; margin accounts
>    are now monitored against intraday margin requirements). **Claude has not independently verified this and our own risk
>    engine still enforces the old rule** (`account_rules.py`, 3 day trades per 5 sessions on a margin-type account); the
>    plan treats verification against the broker, and then an owner-approved change to `account_rules.py`, as a blocker
>    before any live intraday activity.
> 2. *Intraday data.* Free only to start: our own collector (widened), no paid source yet.
> 3. *Slots.* "What strategy is currently allocated to each slot" — the choice of the two slots is to be made from the
>    current allocation (plan section 6 does this and gives a recommendation, to be confirmed by the shadow allocation report).
> 4. *Polling.* Yes: a resident service during market hours is allowed.
>
> **Related decision of the same day, not part of this addendum but material to it:** slot selection was switched to
> `ranking.evidence_mode: backtest_first` (owner instruction "the live slots must be the best performing ideas"). The
> reviewer's closing note below cautions that those backtest-chosen assignments are not suitable for day trading and that
> the Runner must have its own logic and evaluation. The plan keeps the two systems separate.

---

Claude Implementation Prompt: StockBot2000 — Intraday Momentum Runner
Project: `davidromines/stockbot2000`
Objective: Build a dedicated, automated intraday trading strategy that identifies stocks with the strongest probability of continuing upward, enters promising moves, uses protective and trailing stops, and exits when momentum fails.
This is a strategic change in the purpose of StockBot's active trading slots.
The current system has invested heavily in historical research, backtesting, and strategy ranking. However, the live account is losing money, and the system has been holding stocks for days while they decline.
I do not want another round of general research, a new dashboard without trading logic, or a minor modification to the existing backtest-ranked strategies.
I want you to implement an actual intraday trading strategy designed to capture short-term upward price movements and cut losses quickly.
The objective is positive realized net P&L over time. Do not assume the strategy will be profitable merely because it has been implemented.
Phase 1 — Inspect the existing implementation
Before coding, inspect the current repository and determine how the existing components work.
Review at least:

* `ranking.py`
* `slot_trader.py`
* `risk_engine.py`
* `execution.py`
* `costs.py`
* `config.yaml`
* `config/risk.yaml`
* The market-data ingestion and quote interfaces
* The position and order ledgers
* The existing trailing-stop and ATR-stop implementations
* The paper-trading engine
* The backtest and fill simulator
* The live trading scheduler
* The current `backtest_first` ranking configuration

Trace the entire path from candidate selection through order placement, stop management, exit, and P&L reconciliation.
Do not assume that a feature exists simply because it appears in a roadmap or report. Verify its actual implementation.
Reuse the existing architecture. Do not create a separate broker, risk engine, position ledger, or execution system.
Phase 2 — Implement an intraday stock scanner
Create a new, clearly named strategy module, such as `intraday_momentum.py`, following the project's existing conventions.
The scanner should evaluate a liquid universe of eligible US-listed equities during market hours.
Implement candidate scoring using available, valid data for:

1. Relative strength versus the broader market.
2. Short-term price momentum.
3. Volume acceleration relative to the time of day.
4. Breakouts above established intraday resistance.
5. Short-term trend confirmation, including VWAP where data supports it.
6. Volatility and the stock's typical intraday range.
7. Bid/ask spread, liquidity, and expected execution costs.
8. Market-wide conditions that may affect the probability of successful long trades.

Treat these as testable features, not guaranteed sources of profitability.
The system must not buy a stock solely because it has risen sharply. It must assess whether the move is likely to continue and whether the remaining potential reward justifies the downside risk and transaction costs.
Avoid buying stocks that are:

* Illiquid or excessively wide-spread.
* Already extended far beyond their normal intraday range without supporting evidence.
* Falling below important trend levels.
* Experiencing an adverse momentum reversal.
* Likely to produce an expected move too small to cover costs.
* Subject to unreliable or stale market data.

Use only information available at the actual decision timestamp.
Phase 3 — Build an explicit entry model
The entry model must evaluate the probability and expected magnitude of continued upward movement over short horizons.
Evaluate candidate prediction horizons such as 5, 15, and 30 minutes.
Determine which features, thresholds, and horizons are supported by the available data. Do not arbitrarily select whichever configuration produces the highest historical return without accounting for the number of configurations tested.
For each candidate, calculate or estimate:

* Expected gross return.
* Expected net return after realistic execution costs.
* Probability of a favorable move.
* Expected adverse movement.
* Risk/reward characteristics.
* Liquidity and spread penalties.
* Signal freshness and confidence.
* Reasons for accepting or rejecting the candidate.

The strategy should rank candidates by expected risk-adjusted net opportunity.
Do not rank candidates by historical backtest return alone.
Do not require five trades simply because the account has five slots. If only one stock qualifies, only one should be eligible for entry.
Phase 4 — Implement protective and trailing stops
Implement a configurable initial stop and a trailing stop.
The trailing stop must use the highest observed eligible price since entry and must never move downward.
For a percentage-based trailing stop:
`trailing_stop = highest_price_since_entry * (1 - trailing_stop_pct)`
For example, if the stock enters at $100, reaches $103, and then reverses by 1%, the stop should be approximately $101.97. Subject to actual execution, that could preserve a gain of about 1.97% before costs.
Support configurable stop modes so the system can compare percentage-based stops with volatility-aware alternatives such as ATR-based stops.
Do not assume that a 1% stop is universally appropriate. A stop that is too tight can repeatedly exit normal market noise; one that is too wide can expose the account to excessive losses.
Determine suitable candidate parameters through honest testing.
The stop system must also handle:

* Price gaps through the stop.
* Fast declines between quote updates.
* Stale or missing quotes.
* Market-data outages.
* Partial fills and rejected orders.
* Rejected or unavailable protective orders.
* Restarting the service while positions remain open.
* Market close and overnight exposure.
* Idempotent order submission and broker reconciliation.

Never report a stop price as though it guarantees the execution price.
Use the existing execution and risk-management layers. Do not bypass them.
Phase 5 — Add explicit exit rules
The strategy must not continue holding a stock indefinitely simply because its original backtest ranked well.
Support exits triggered by:

1. Initial protective stop.
2. Trailing stop.
3. Confirmed deterioration in momentum.
4. Failure of the entry thesis.
5. Maximum holding time.
6. End-of-session policy.
7. Account-level risk controls.

The strategy must explicitly distinguish between an intraday trade and a medium-term investment.
An intraday position should not automatically become a multiday investment after its signal fails.
Default to closing intraday positions before the end of the trading session unless an explicitly configured and tested policy allows otherwise.
Phase 6 — Establish realistic intraday data and testing
The existing database primarily contains daily bars. Determine what historical intraday data is actually available, its coverage, its quality, and its limitations.
Build or extend the data interface required for intraday strategy development.
Evaluate suitable historical intraday data sources and their licensing, access costs, and coverage before adding a dependency.
Use realistic intraday execution assumptions:

* Entries occur only after the signal is observable.
* Fills cannot use prices that were unavailable at the decision time.
* Bid/ask spreads and slippage are modeled.
* Stop orders can experience gaps and unfavorable fills.
* Overlapping positions consume capital.
* Rejected, delayed, and partial orders are accounted for.
* Costs are deducted from reported net P&L.

Do not use daily high/low information to claim that the system would have entered before a price rise and exited before a decline unless the underlying intraday sequence supports that conclusion.
Test chronologically, using walk-forward validation and a prospective holdout.
Account for the many strategies and parameter combinations that the project has already tested. Avoid presenting a result selected from thousands of trials as though it were an independent confirmation.
Compare results against reasonable controls, including random entries with comparable holding periods, a simple momentum baseline, and a no-trade baseline.
Phase 7 — Test the stop-loss and trailing-stop policy
Create a dedicated test suite for stop behavior.
Include the following scenarios:

* Stock rises steadily.
* Stock rises sharply and then retraces.
* Stock falls immediately after entry.
* Stock rises and then gaps below the trailing stop.
* Stock oscillates around the stop.
* Quote updates are delayed.
* The broker rejects an exit.
* A partial fill leaves an open position.
* The service restarts while the position is open.
* A position remains open near the session close.

For each tested configuration, report:

* Win rate.
* Average and median net return per trade.
* Gross P&L.
* Trading costs.
* Net P&L.
* Maximum adverse excursion.
* Maximum favorable excursion.
* Average holding time.
* Stop-trigger frequency.
* Gap-through-stop losses.
* Maximum drawdown.
* Number of trades and independent trading dates.

Do not optimize the stop using only the best historical configuration. Evaluate sensitivity to parameter changes and different market regimes.
Phase 8 — Integrate with the five-slot portfolio
Integrate the new strategy with the existing slot architecture.
The intended portfolio structure is:

* Four slots available for short-horizon strategies, including the new intraday momentum strategy.
* One slot available for the existing medium-term value/quality strategy.

These are intended roles, not a requirement to fill every slot.
Allow a slot to remain in cash when no strategy meets its eligibility criteria.
Do not let the medium-term value strategy determine the intraday scanner's candidate ranking.
Do not let the intraday strategy inherit a multiday holding period from an existing strategy.
Prevent duplicate positions, correlated overexposure, and repeated entries into a stock that has just been stopped out unless a new, independently valid signal appears.
Before changing existing live assignments, produce a shadow allocation report showing which positions would be retained, exited, or replaced and why.
Phase 9 — Protect the live account
The live account has limited capital and has already experienced losses.
Do not enable the new strategy for live trading automatically.
Build and validate it through the existing simulation and paper-trading infrastructure first.
Implement explicit, configurable limits for:

* Maximum position size.
* Maximum loss per trade.
* Maximum daily realized loss.
* Maximum portfolio drawdown.
* Maximum simultaneous positions.
* Maximum entries per session.
* Maximum exposure to correlated positions.
* Data freshness.
* Order failures and reconciliation discrepancies.

Verify the actual broker account restrictions and settled-funds rules before enabling frequent intraday round trips. Do not assume the account can execute unlimited same-day trades.
The existing live execution path, kill switch, broker reconciliation, and risk controls must remain authoritative.
Do not place live orders, change live capital allocation, or arm the new strategy without my explicit approval.
Do not disable existing risk controls to make the strategy appear more active.
Phase 10 — Produce an actionable implementation report
Do not stop after writing a proposal.
Implement the new strategy, tests, configuration, and reporting using the existing project architecture.
The final report must identify:

1. Files created and modified.
2. The actual intraday data available and any remaining data gaps.
3. How candidate stocks are scored.
4. How entry and exit signals work.
5. How trailing stops are maintained.
6. How the implementation handles broker and data failures.
7. The results of historical and paper evaluations.
8. How results compare with simple baseline strategies.
9. Whether the evidence supports continuing development.
10. The remaining blockers before live activation.

Clearly distinguish completed functionality from planned functionality.
Run the relevant tests and report their actual results. Run the full regression suite before proposing deployment.
Do not make unsupported claims that the system is profitable.
The definition of success is not that the code runs or that a backtest looks good. Success means the system can identify intraday opportunities, execute the intended trading logic reliably, and demonstrate credible positive net performance in prospective testing.
7. My final recommendation
I would pursue this approach, but I would make one change to the way we evaluate success.
Don't judge the new system by whether it buys stocks that are already up. Judge it by whether it can identify opportunities before the move, exit losing trades as intended, and retain enough of its winners to produce positive net results.
That is the actual challenge.
And I would not let Claude turn this into another sprawling research project. The first milestone should be a working intraday scanner, a clearly defined entry and exit model, realistic historical testing, and a paper-trading report. Everything else comes after we have evidence that this approach has potential.
One final issue needs particular attention: the latest dossier describes the live selection change as relying on historical backtest performance, even though the audit found no established trading edge. I would not assume those new assignments are suitable for day trading. The Intraday Momentum Runner should have its own strategy logic and evaluation criteria, separate from the medium-term backtest-ranked strategies.
That is how I would turn your idea into a concrete, testable trading system rather than another stock picker that buys and waits.

---
