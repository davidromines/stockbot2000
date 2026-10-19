# Addendum H — Alpha Research and Validation Engine

**Source:** the independent reviewer, via the owner, 2026-10-19, responding to the 2026-10-19 review dossier
(https://claude.ai/artifact/3YFiMwNxvpXk3ycNVi2PKt, source `docs/artifacts/review_report.html`).
**Status:** entered 2026-10-19, **PLAN ONLY, nothing built, nothing changed live** (owner: "Do not action yet. Just add to
the plan."). Claude's review of the whole system and the staged plan that responds to this addendum are in
`docs/STAGE_AD_PROFITABILITY_PLAN.md` (roadmap Stage AD). Where the two differ, the plan says so and why; the owner decides.

The reviewer's text follows verbatim.

---

tockbot2000: How to make it better at predicting returns and discovering alpha
My recommendation is to change the project's center of gravity from generating and ranking strategies to identifying, validating, and combining repeatable sources of predictive information.
Your dossier describes a substantial engineering achievement: a research factory, a strategy library, historical simulations, forward-testing infrastructure, risk controls, and automated live execution. The problem is that the system has repeatedly produced apparent winners that failed when you corrected the testing methodology.
The latest results are especially important:
- 0 of 54 strategy families qualify as positive under the corrected forward-test criteria.
- The prospective test has reached only 2 of its 20 required independent entry dates. It's too early to draw a conclusion from it.
- The account is down $6.07, or 6.9%, from its initial $87.71.
- The three current medium-term holdings were selected primarily on backtest evidence, with almost no forward trading history of their own.
- The two Intraday Runners are trading without the shadow, holdout, and paper-testing gates originally specified in their plan.
- The research search is frozen, and the system already has 1.05 million-plus recorded evaluations.
Those facts point to a critical distinction:
Stockbot2000 does not primarily need more strategies. It needs a more reliable way to distinguish genuine predictive signals from noise, determine when a signal is likely to work, and prove that it survives trading costs and live execution.
I would preserve the existing infrastructure, keep the evolutionary search frozen for now, and build the next phase around a governed Alpha Research and Validation Engine. This engine would incorporate published academic factors, commercial research where accessible, established quantitative strategies, and new machine-learning models through the same standardized testing process.
The objective is positive net trading returns—not a high backtest score, a high win rate, or beating a benchmark for its own sake. There is no guaranteed way to achieve profitability, and the current evidence does not establish that any strategy in the system has a durable edge.
1. The biggest change: build an evidence-driven alpha engine
I would organize Stockbot2000 around five separate responsibilities:
1. Strategy Library: What strategies and predictive signals have other researchers already documented?
2. Alpha Research: Which of those signals predict future returns in your actual stock universe, at a tradable horizon?
3. Prediction Models: Can we estimate the size, direction, and uncertainty of future returns using those signals?
4. Portfolio and Strategy Selection: Which validated signals deserve capital, given their risks, costs, holding periods, and overlap with existing positions?
5. Live Execution and Feedback: Are the predictions translating into real net profits, and what does the evidence tell us to change?
Your system already has much of the plumbing. The priority is improving the quality of the information flowing through it.
A. Stop treating a strategy as the smallest unit of research
A strategy is usually a bundle of hypotheses. For example, a momentum strategy might combine:
- Past price performance.
- Relative strength versus the market.
- Trading volume.
- Market direction.
- Volatility.
- A breakout condition.
- An entry time.
- A stop-loss rule.
- A holding period.
If the strategy loses money, you don't know which component failed. Perhaps momentum is predictive, but the volume filter adds nothing. Perhaps the entry is good, but the exit gives back the profits. Perhaps the signal works only in strong markets.
Stockbot2000 should test individual signals before testing increasingly complicated combinations of them.
For every signal, the research engine should answer:
Question	What the system should measure
Is there a predictive relationship?	Future returns conditional on the signal
How large is the effect?	Average and median returns, including uncertainty
Is it economically useful?	Returns after realistic transaction costs
When does it work?	Performance across market regimes and conditions
Does it add new information?	Incremental value beyond existing signals
Does it generalize?	Results on genuinely unseen periods
Can we trade it?	Liquidity, spreads, turnover, available capital, and execution
Is it still working?	Prospective results after the strategy is frozen


For example, don't just test whether a stock with strong 15-minute momentum subsequently rises. Test whether 15-minute momentum predicts additional returns after controlling for market direction, volatility, liquidity, time of day, and the stock's recent movement.
That is a much more useful question.
B. Build a signal-level research database
Your Knowledge Strategy Factory already tracks documented strategies and provenance. Extend that concept so that each underlying signal has a permanent record.
Each record should include:
- signal_id: Stable identifier.
- source_id: Original paper, factor library, commercial methodology, or internal hypothesis.
- source_version: Version of the source or methodology.
- economic_hypothesis: Why the signal might predict returns.
- known_publication_date: When the underlying idea became publicly available, if known.
- asset_class and universe: What it applies to.
- required_data: What information is needed and when it becomes available.
- prediction_horizon: For example, 30 minutes, one day, 20 trading days, or 60 trading days.
- direction: Expected positive or negative relationship.
- feature_definition: Exact, reproducible calculation.
- research_trials: All material variants and tests attempted.
- out_of_sample_results: Results not used to design the signal.
- incremental_alpha: Whether it adds predictive value beyond existing signals.
- implementation_constraints: Costs, shorting requirements, minimum capital, and data limitations.
- status: Discovered, replicated, validated, paper-tested, live-tested, rejected, or retired.
The source's published performance must never be copied into Stockbot's results as if Stockbot had reproduced it. Record the original findings separately from your own replication.
This would turn the Knowledge Strategy Factory into an actual research asset, rather than primarily a way to generate more strategies.
2. Incorporate established academic strategies systematically
Your existing library contains 153 JKP factors, published-factor seeds, and hundreds of documented reproductions. That is a strong starting point. I would not begin by adding another thousand factors.
Instead, select a small group of well-documented families, reproduce them faithfully, and determine whether their underlying signals can work in your particular implementation.
Priority 1: Established medium-term equity factors
These are the first families I would investigate.
Family	Hypothesis	Initial Stockbot research
Momentum	Stocks with strong prior performance may continue to outperform over subsequent periods	Cross-sectional momentum; time-series momentum; several lookback periods
Value	Stocks priced cheaply relative to fundamentals may outperform	Free-cash-flow yield, earnings yield, book-to-market, with point-in-time fundamentals
Quality	Profitable, financially sound companies may outperform weaker businesses	Profitability, earnings stability, balance-sheet strength
Earnings surprises	New information about earnings may produce subsequent price drift	Standardized unexpected earnings, surprise magnitude, age of information
Revisions	Changes in earnings expectations may contain information about future returns	Test only if reliable, historically timestamped analyst-estimate data is available
Reversal	Recent underperformance may predict a rebound under certain conditions	Separate short-horizon reversal from medium-term reversal
Low risk	Lower-risk securities may deliver attractive risk-adjusted performance	Volatility, downside risk, and beta; account for leverage and implementation constraints
Investment and cash flow	Corporate investment and cash-flow characteristics may contain information about future returns	Asset growth, free cash flow, accruals, and related documented factors


These are research candidates, not claims that the strategies will be profitable in your account.
For instance, AQR publishes research and downloadable datasets covering quality, momentum, value, and related factors. Its Quality Minus Junk research documents a quality factor based on profitability, growth, safety, and payout. That provides a concrete external reference for your existing quality research, although its published long/short factor returns are not directly achievable by your current long-only, approximately $20-per-slot implementation. AQR Capital Management
Similarly, the Fama–French-style value and momentum portfolio constructions documented in the academic literature provide reproducible definitions against which your implementations can be compared. Springer
Priority 2: Reproduce before innovating
For each chosen family, run three distinct experiments.
Experiment A — Faithful replication
Reproduce the published methodology as closely as your available data permits.
Don't optimize parameters to make it perform better in your database. Document deviations from the original methodology.
Experiment B — Implementation replication
Apply the same economic signal to Stockbot's actual constraints:
- Long-only positions.
- Fractional shares, where supported.
- Available buying power.
- Actual transaction costs.
- Realistic entry and exit prices.
- Point-in-time information.
- Your actual holding periods.
This tells you whether the original concept remains useful in your implementation.
Experiment C — Incremental improvement
Only after A and B are complete should you test variants such as alternative holding periods, market-regime filters, signal combinations, or machine-learning models.
Keep the faithful replication immutable. Every variation must have its own experiment ID and trial history.
This distinction matters because a documented strategy can be legitimate in its original context but unsuitable for your capital size, trading constraints, or implementation.
Priority 3: Incorporate the research behind the strategy, not just its name
Consider earnings-surprise momentum.
Rather than adding a strategy called earnings_surprise_60d, build and test its components:
1. Standardized earnings surprise.
2. Time since the announcement.
3. Price response around the announcement.
4. Relative strength following the announcement.
5. Trading volume around the event.
6. Market and industry-adjusted returns.
7. Liquidity and estimated trading costs.
Then test whether each component predicts returns independently and whether combining them improves genuinely unseen results.
Your dossier already shows a promising reason to investigate this area: the current forward-test table contains an earnings-related family, and the existing Knowledge Strategy Factory has documented reproductions. But its limited forward evidence does not yet justify treating it as an established edge.
The goal is to find out whether a signal has predictive value—not to produce the best possible combination of indicators in hindsight.
A critical warning about academic research
Published results are not proof that a strategy will work in your implementation. Research can fail to replicate, become crowded, or lose its economic advantage after costs.
Harvey, Liu, and Zhu explain why conventional statistical significance thresholds are insufficient when researchers have tested many potential factors; their analysis argues for a substantially higher significance hurdle for newly discovered factors. National Bureau of Economic Research
Novy-Marx similarly demonstrates that combining multiple signals can create substantial backtest-overfitting bias, even when individual signals are not genuinely predictive. National Bureau of Economic Research
This is especially relevant to Stockbot because your system has already accumulated more than one million recorded evaluations.
The number of strategies discovered is not a measure of progress. The number of independently validated predictive relationships is.
3. Incorporate commercial quantitative systems intelligently
There are three different things that people mean by a commercial trading system. Stockbot should approach each differently.
A. Commercial research and factor libraries
These provide documented methodologies, research, data, and sometimes portfolio construction techniques.
Examples worth evaluating include:
Source	Potential use	Limitation
AQR Research and Data Library	Reference factor definitions and published return series for value, momentum, quality, and related research	Some implementations are long/short, require unavailable data, or use horizons that do not match Stockbot
Kenneth French Data Library	Standardized academic factor portfolios and benchmarks	Primarily a research benchmark; its portfolio returns do not automatically translate into an executable Stockbot strategy
Andrea Frazzini's Data Library	Reference material and links to published factor datasets	Must check the licensing, methodology, and suitability of each dataset
QuantConnect LEAN	Independent reference implementation for event-driven backtesting and execution modeling	It is an engine, not an alpha source or a guarantee of profitable strategies


AQR's data library includes daily and monthly datasets for several established factors. That makes it useful for independent comparison, rather than forcing Stockbot to judge every result using its own internally generated benchmarks. AQR Capital Management
The priority should be to use external research to challenge Stockbot's conclusions, not to import published returns as evidence that your own strategy works.
B. Open-source trading systems and strategy implementations
These can help you find established methods and expose weaknesses in your own implementation.
One candidate is QuantConnect LEAN, an open-source engine for research, backtesting, and live trading. It supports modular data feeds, transaction processing, portfolio management, and configurable brokerage and fee models. QuantConnect
I would not replace your existing trading infrastructure with LEAN as the first step. You have already built a substantial amount of custom infrastructure, and a migration would introduce risk without proving that your predictions improve.
Instead:
1. Select one or two representative strategies.
2. Reproduce their historical results in Stockbot.
3. Independently implement the same rules in LEAN.
4. Compare signals, entry timestamps, fills, costs, corporate actions, and portfolio returns.
5. Investigate every material discrepancy.
This is an independent validation exercise, not a contest to see which engine reports the highest return.
If your simulator consistently disagrees with a mature independent engine, that is useful information. If the engines agree but the strategy loses money, the problem is more likely the signal or its economic implementation than the simulator alone.
C. Commercial data and execution products
These are different from strategy libraries. They provide information or execution capabilities that your system may not currently have.
Potential areas include:
- Point-in-time analyst estimates and estimate revisions.
- Historically timestamped earnings-call transcripts.
- Corporate events and filings.
- Historical bid/ask quotes.
- Intraday trades and quotes.
- Historical news with publication timestamps.
- More reliable delisted-security and corporate-action data.
I would not purchase all of these at once.
Your system currently uses free price data and a synthetic reconstruction for dead companies. Its documented problems include corporate-action distortion in paper trades and a synthetic survivorship model that was tuned on the same real failures used to evaluate it.
Those limitations make it difficult to determine whether an apparently predictive signal is real.
Before purchasing a data product, define a specific hypothesis:
What information does this dataset provide, when does it become available, and what test will establish whether it adds predictive value beyond the data we already have?

Then establish the historical coverage, timestamp quality, licensing, point-in-time availability, and cost before committing to a subscription.
A paid data source is justified when it removes a specific limitation in the research or execution process—not simply because it is more sophisticated.
4. Make Stockbot better at predicting returns
This is the second major change. Stockbot should stop thinking primarily in terms of selecting the best strategy and start estimating the future returns associated with individual opportunities.
I would build a multi-horizon prediction layer that serves the strategy library and portfolio manager.
A. Predict returns, not just whether a stock goes up
Suppose the system is considering buying a stock.
A basic classifier might estimate:
Probability the stock closes higher tomorrow: 56%.

That sounds useful, but it is incomplete. A 56% chance of gaining 0.2% is not necessarily attractive if the expected loss on the other 44% of outcomes is large and the round-trip costs are substantial.
Instead, the model should estimate:
- Probability of a positive return.
- Expected gross return.
- Expected net return after estimated trading costs.
- Return distribution or prediction interval.
- Probability of a sufficiently large loss.
- Expected return relative to an appropriate benchmark.
- Uncertainty in the estimate.
For a long-only strategy, the decision should be based on whether the expected net return is sufficiently attractive relative to the risk and uncertainty.
For example, a hypothetical prediction might look like this:
Output	Hypothetical estimate
Probability of a positive 5-day return	57%
Expected gross return	+0.80%
Estimated round-trip costs	−0.25%
Expected net return	+0.55%
Estimated downside risk	−2.0%
Confidence	Low


These are illustrative numbers, not actual Stockbot predictions.
Even this opportunity would need further evaluation: the expected return might be too uncertain, the downside too large, or the estimate insufficiently reliable to justify a trade.
The system must be able to decide that no trade is better than a weak trade.
B. Build separate models for different holding periods
Don't train one model to predict everything.
I would establish three distinct prediction tracks.
Track	Target	Primary research
Intraday	Net return over approximately 15, 30, and 60 minutes	Momentum, reversal, volume, market direction, volatility, time of day, and execution costs
Short-term	Net return over approximately 1–10 trading days	Earnings surprises, price momentum, short-term reversal, event effects, and market conditions
Medium-term	Net return over approximately 20–60 trading days	Value, quality, earnings trends, revisions where available, momentum, and financial characteristics


Each track needs its own labels, cost assumptions, evaluation methods, and validation periods.
A feature can be predictive at one horizon and useless at another. A stock that rebounds over the next 30 minutes might still be a poor investment over the next 30 days.
This is also why I would not combine the two Intraday Runners with the medium-term strategies in a single leaderboard.
C. Establish a simple prediction-model ladder
Do not begin with a large neural network or a complicated reinforcement-learning system.
Build models in increasing order of complexity:
1. Baseline: Market return, historical average, and simple rule-based forecasts.
2. Linear models: Ridge regression and logistic regression.
3. Tree models: LightGBM or CatBoost, if the existing environment supports them.
4. Regime-aware models: Models that account for volatility, market direction, liquidity, and event conditions.
5. Ensembles: Combine genuinely complementary models, using weights learned only from training data.
6. More complex models: Consider only if simpler models have demonstrated stable predictive value and the complex model adds out-of-sample improvement.
The important question is not which model is most advanced. It is which model produces the most reliable incremental net-return predictions on data it has not seen.
For each model, preserve a simple baseline and compare performance on identical dates, securities, labels, and cost assumptions.
If CatBoost performs no better than Ridge regression on the untouched evaluation set, use Ridge regression. Simpler models are easier to diagnose and less likely to hide overfitting.
D. Use machine learning to discover interactions—not to manufacture them
Your existing XGBoost and analog-forecasting work can become more useful if it is given a specific role.
For example, the model might discover that earnings surprises are more predictive when:
- The surprise is large relative to historical earnings variability.
- The stock has not already made a large price adjustment.
- The broader market is not experiencing a sharp selloff.
- Liquidity is sufficient to enter without excessive costs.
Those interactions could be valuable, but they must be tested against simpler alternatives.
For every proposed interaction, compare:
1. The original signal alone.
2. The new condition alone.
3. The combined signal.
4. The combined signal against a simple baseline.
5. The combined signal on an untouched period.
The model should also be allowed to report that a relationship is unstable or not predictive.
I would not let a model continuously retrain on its newest wins and losses and immediately change live behavior. First record predictions, freeze model versions, measure calibration and performance, and promote changes through a controlled process.
E. Add market-regime detection
This is a particularly useful area to investigate because the system currently compares strategies across very different conditions.
Possible regime features include:
- Broad-market trend.
- Realized volatility.
- Volatility relative to its recent history.
- Market breadth.
- Cross-sectional dispersion.
- Correlation between stocks.
- Sector leadership.
- Volume and liquidity conditions.
- Market drawdowns.
The first implementation should use transparent, measurable features rather than an elaborate regime-classification model.
Then ask:
Does the signal predict future returns consistently across these conditions, or is its apparent performance concentrated in one environment?

For instance, a momentum signal might perform differently during strong market trends and sharp reversals. A value signal might have a different return distribution from a short-term breakout signal.
However, regime detection must not become another mechanism for finding profitable-looking subsets in hindsight. Regimes must be defined using information available at the time of the decision, and the conditions must be evaluated prospectively.
5. The most important new capability: test incremental alpha
This is where I think Stockbot2000 can make the largest research improvement.
A strategy can produce positive returns without providing any unique predictive information.
For example, a strategy that buys stocks with strong recent performance might appear profitable during a rising market. But if the market itself accounts for the returns, the strategy may not be adding anything useful.
Your research engine needs to distinguish three different results:
1. Positive raw returns: The strategy made money in the tested period.
2. Positive returns after costs: The strategy survived estimated implementation costs.
3. Incremental predictive value: The strategy provides information beyond the existing signals and appropriate market benchmarks.
The third is the critical question for an alpha research engine.
A. Use a common prediction target
For medium-term equity research, define a standardized target such as:
\[
y_{i,t,h}
=
R_{i,t\rightarrow t+h}
-
R_{\text{benchmark},t\rightarrow t+h}
\]
Here:
- \(i\) is the stock.
- \(t\) is the decision time.
- \(h\) is the forecast horizon.
- \(R\) is the return measured using the specified, consistent execution convention.
This is a benchmark-relative return target, not a guarantee of true risk-adjusted alpha. It helps separate a stock's performance from the market's general movement.
For actual trading decisions, Stockbot must also evaluate expected net dollar returns after costs. A benchmark-relative signal is a research tool, not a substitute for the actual portfolio's profit and loss.
For intraday strategies, use separate intraday labels and appropriate benchmarks. Do not apply daily factor-testing assumptions indiscriminately to minute-level trading.
B. Test each signal against a baseline model
Suppose the current model uses:
- Momentum.
- Value.
- Quality.
- Earnings surprise.
- Volatility.
Now introduce a new published factor.
Run the baseline model and the augmented model on identical out-of-sample observations.
Measure whether the new factor improves:
- Prediction error.
- Rank ordering of future returns.
- Calibration.
- Expected net returns under the same portfolio and cost assumptions.
- Drawdown or downside risk.
- Stability across dates and market regimes.
A factor that improves a statistical metric but does not improve portfolio outcomes may not be useful for trading.
Conversely, a factor might be useful in reducing losses or avoiding bad trades, even if it does not materially increase average returns.
C. Measure feature importance correctly
I would add four complementary analyses:
1. Standalone predictive value
How predictive is the feature by itself?
2. Conditional predictive value
Does it remain predictive after accounting for existing features?
3. Ablation test
Does model performance deteriorate when the feature is removed?
4. Stability test
Does the feature retain its effect across different periods, market conditions, and reasonable cost assumptions?
Feature importance from a single fitted model is not sufficient. Correlated features can divide or distort apparent importance, and a model can assign importance to relationships that will not generalize.
D. Add a signal-dependence map
Stockbot already uses a correlation constraint for strategy selection. Extend the concept to the research layer.
For each pair of signals, estimate:
- Feature correlation.
- Correlation of their prediction errors.
- Correlation of their realized strategy returns.
- Incremental performance when combined.
- Whether they depend on the same market conditions.
Two strategies with different names may essentially be the same bet. Conversely, two individually modest signals may complement one another if their errors differ.
The objective is not to maximize the number of signals in the library. It is to identify a smaller set of signals that contribute distinct, reliable information.
E. Establish a formal promotion ladder
Every signal or model should pass through the same stages:
1. Registered hypothesis: The economic rationale and test are recorded before evaluation.
2. Exploratory research: Develop the feature and understand its behavior.
3. Replication: Reproduce the source methodology where applicable.
4. Out-of-sample validation: Evaluate on data not used for feature selection or parameter tuning.
5. Prospective shadow: Record live predictions without trading.
6. Paper trading: Test the complete strategy and execution assumptions.
7. Micro-live: Permit a tightly limited real-money test only after the required evidence and explicit approval.
8. Production: Allocate capital only if the strategy continues to meet its requirements.
Failed experiments remain in the research ledger. They should not be silently deleted, renamed, or restarted with a fresh trial count.
The existing prospective test should continue under its registered rules. Do not change its criteria because the interim results are disappointing.
6. Fix the strategy-selection problem before adding more strategies
Your change to backtest_first is understandable. The previous ranking method blended backtests and paper results, but the paper results were contaminated by same-close fills and gross returns presented as net.
The corrected evidence suggests that the previous paper-ranking method was unreliable.
However, replacing a flawed ranking method with a backtest-only ranking method does not solve the underlying problem.
Your dossier reports a rank correlation of +0.21 between backtest scores and subsequent returns, compared with +0.03 for the former blended score. That is evidence worth investigating, but it does not establish that selecting the highest backtest scores produces profitable live trades.
My recommendation: use evidence-gated ranking
Separate eligibility from ranking.
Stage 1: Eligibility
A strategy must pass the following gates:
- Valid implementation and data integrity.
- Realistic fills and costs.
- Survivorship and corporate-action checks appropriate to the strategy.
- Out-of-sample testing.
- Minimum evidence requirements appropriate to its horizon.
- No unresolved critical execution or accounting defects.
Stage 2: Ranking
Rank eligible strategies using a combination of:
1. Out-of-sample expected net return.
2. Uncertainty in the return estimate.
3. Stability across time periods and regimes.
4. Downside risk and drawdown.
5. Turnover and implementation costs.
6. Incremental predictive value.
7. Correlation with the existing portfolio.
8. Forward evidence, when enough independent observations exist.
A strategy with a spectacular backtest and almost no forward evidence should not automatically outrank a more modest strategy with stronger independent validation.
At the same time, a strategy should not be rejected merely because it has had a few bad trades. Forward evidence needs sufficient sample size, appropriate uncertainty estimates, and consideration of the strategy's expected holding period.
What should happen while the prospective test is incomplete?
Your prospective test has only 2 of the required 20 independent entry dates. Continue collecting the registered evidence without changing the criteria.
I would not treat the current top-ranked backtests as validated winners in the meantime. Preserve the existing research and compare candidates in shadow or paper mode.
If you continue allocating real money according to backtest_first, explicitly treat that as a risk-bearing experiment rather than an established alpha strategy.
I would also avoid rotating positions simply because a newly discovered backtest ranks slightly higher. With an account this small, turnover and the losses realized during forced reassignment can be material.
7. Reconsider the two Intraday Runners
The two Runners are an interesting experiment, but their current evidence does not support a claim of positive expected returns.
The stock Runner has one reported live trade, which lost $0.09. The twin-ETF Runner has only five replay sessions, with a 30-minute average return of −0.04%. Neither result is sufficient to determine whether either strategy has an edge.
The more important finding is that the project's own earlier same-day paper set lost approximately 0.05% per trade after costs.
My recommendation for the stock Runner
Return it to SHADOW while it collects a sufficiently broad prospective sample.
Record every qualifying signal, including those that could not be traded because of insufficient buying power. Evaluate those signals separately from actual executions.
This is important because the limited capital available for two Runners makes the traded sample highly selective. If the system only takes the first signal it can afford, the realized trades may not represent the overall signal population.
Track at least:
- All qualifying signals.
- Signals refused because of insufficient buying power.
- Predicted return and confidence at entry.
- Returns at 15, 30, and 60 minutes.
- Realistic executable entry and exit prices.
- Gross and net returns.
- Spread and slippage estimates.
- Stop-trigger price versus actual exit fill.
- Market direction and volatility.
- Time of day.
- Whether the entry conditions still predict returns after controlling for market movement.
Do not fit the entry thresholds repeatedly to the shadow data and then count those same observations as validation evidence.
My recommendation for the twin-ETF Runner
I would put this strategy in SHADOW immediately.
The underlying idea is testable: short-horizon index momentum might predict continuation, and inverse ETFs allow a long-only account to express a bearish directional view. But the five-session replay does not establish a useful edge.
There is also a crucial distinction between the underlying index's direction and the return of the selected ETF. Leveraged and inverse ETFs have product-specific behavior, and their trading costs and intraday price paths must be modeled directly.
I would test these hypotheses separately:
1. Does 15-minute index momentum predict the next 15 minutes?
2. Does it predict the next 30 minutes?
3. Does it predict the next 60 minutes?
4. Does it work better when market volatility is high or low?
5. Does it add predictive value beyond the index's current direction and recent volatility?
6. Does the signal survive actual entry and exit costs?
7. Does the inverse ETF behave as expected under the proposed entry and exit rules?
Compare the directional strategy against simple controls: no trade, always bullish, and a simple market-trend rule.
Do not assume the strategy is profitable just because it can switch between bullish and bearish positions.
Why I recommend SHADOW instead of using live trading to discover the answer
Your original plan required shadow evidence, an untouched holdout, and a paper trial before live deployment. Those gates were waived.
I would restore them. The account is already below its initial equity, the two Runners do not have demonstrated positive expectancy, and the available capital is too limited to generate a large, balanced sample of live trades quickly.
You can still learn a great deal from prospective shadow data without paying real-money trading costs.
A live trial becomes more defensible only after the strategy demonstrates a credible net-return edge under frozen rules and realistic execution assumptions. Even then, live trading should begin at a limited scale, with explicit stop conditions.
8. Improve the research data before purchasing more data
Your database is substantial, but the dossier identifies several unresolved data-quality issues.
These deserve attention because a more sophisticated model can make better use of good data—but can also exploit defects in bad data.
I would prioritize the following.
First: fix known defects that can distort measured returns
Corporate actions in paper trades
The dossier identifies a case in which an entry price remained at the traded price while subsequent prices were back-adjusted. This produced apparent losses around a spin-off.
Measure the scope of the issue, correct the accounting convention, and restate affected results without overwriting the originals.
End-of-bar paper fills
The paper engine still uses the close that generated the signal for entries and exits, whereas the simulator uses next-open fills.
This must be resolved. Otherwise, the strategy-ranking system compares results generated under different execution assumptions.
For intraday strategies, next-open daily-bar logic alone is not sufficient. Use the appropriate intraday bar or quote data, account for the time at which the signal becomes available, and model subsequent execution.
Historical universe integrity
The synthetic dead-company reconstruction is a useful research tool, but the dossier acknowledges that its configurations were tuned on the same failures used to evaluate it.
Keep that caveat visible. Compare strategies under the different survivorship assumptions already implemented, and avoid treating the synthetic reconstruction as independent evidence.
If the ranking changes substantially depending on the dead-company assumption, the strategy should be classified as sensitive to unresolved data uncertainty.
Second: improve the data that can actually change decisions
I would evaluate data purchases in this order:
1. Corporate actions and historical universe integrity: Resolve accounting and survivorship distortions.
2. Intraday execution data: Obtain sufficiently accurate historical quotes or other suitable data to estimate spread, slippage, and executable prices.
3. Point-in-time earnings expectations: Only if you decide to prioritize earnings revisions and estimate-based strategies.
4. Timestamped news or alternative data: Only after identifying a specific hypothesis that existing data cannot test.
For every candidate dataset, run a value-of-information experiment: compare the model with and without the new data using identical out-of-sample periods.
Do not buy data simply because a commercial provider markets it as predictive.
9. Put strategies with different holding periods on a common decision framework
You asked in the dossier how to compare strategies holding positions for five days, 60 days, or different option horizons.
The answer is not to compare raw return percentages directly.
A 1% return in one day is not equivalent to a 1% return over 60 days. Nor is a 1% return on an unleveraged stock equivalent to a 1% return on a leveraged ETF or an option.
Use a standardized evaluation framework, while retaining horizon-specific performance measures.
For each strategy, report:
Measure	Why it matters
Expected net return per trade	Measures the expected payoff under the specified implementation
Expected net return per unit of capital-day	Helps compare capital tied up for different periods
Annualized return, where appropriate	Provides a common long-horizon reference
Maximum drawdown	Measures peak-to-trough capital loss
Downside risk	Captures adverse outcomes not described by average returns
Turnover	Identifies strategies that consume returns through frequent trading
Capital utilization	Shows whether the strategy leaves capital idle
Correlation with existing strategies	Helps distinguish diversification from duplicate exposure
Evidence quality	Separates a promising hypothesis from a validated strategy
Robustness to costs	Tests whether the edge survives plausible execution deterioration


For very short holding periods, capital-day return and annualized estimates can be misleading because they magnify small estimates and ignore capacity constraints. They should be secondary measures, not the sole ranking criterion.
Likewise, Sharpe ratios should not be compared mechanically across strategies with different horizons, overlapping positions, or return autocorrelation.
The ultimate comparison should be the contribution each strategy makes to the portfolio's expected net returns, risk, and drawdown—not which strategy has the largest historical percentage return.
10. The implementation roadmap I would use
I would not start another large roadmap with dozens of loosely connected features. I would make the next phase a bounded project with concrete deliverables.
Phase A — Restore research integrity
Objective: Make sure Stockbot measures strategy performance consistently.
Tasks:
- Fix and quantify the corporate-action issue in paper trades.
- Correct the paper engine's same-close fill convention.
- Reconcile the live account equity and trade ledger to the cent.
- Audit the live and paper cost models.
- Ensure all Runner signals and minute bars are included in backups.
- Verify that the existing prospective-test criteria remain frozen.
- Produce a consolidated data-integrity report.
Acceptance criteria: The same strategy, data, execution assumptions, and dates produce consistent accounting across the simulator, paper engine, and reporting layer.
No new strategy families should be introduced during this phase.
Phase B — Build the Alpha Research Registry
Objective: Turn the existing Knowledge Strategy Factory into a reproducible signal-research system.
Tasks:
- Add standardized signal metadata and provenance.
- Inventory the 153 JKP factors and existing published-strategy reproductions.
- Select a small set of documented factor families.
- Separate faithful replication from Stockbot-specific variations.
- Record every material experiment and its relationship to prior experiments.
- Add an explicit multiple-testing policy.
- Prevent exploratory results from being presented as independent validation.
Acceptance criteria: The system can trace every promoted signal to its source, exact definition, experiments, rejected variants, and untouched evaluation results.
Phase C — Build the Incremental Alpha Test Bench
Objective: Determine whether individual signals add predictive information.
Tasks:
- Standardize prediction targets by horizon.
- Test standalone and conditional predictive relationships.
- Compare linear baselines with the existing machine-learning models.
- Measure out-of-sample prediction error and calibration.
- Evaluate feature ablations and incremental predictive value.
- Report performance by market regime, date, sector, and liquidity where sample sizes permit.
- Add dependence-aware statistical evaluation and sensitivity to costs.
Acceptance criteria: Every tested signal has a report showing whether it adds predictive value beyond the baseline, whether the result survives costs, and how uncertain the estimate is.
Phase D — Build the Prediction Service
Objective: Produce actionable, uncertainty-aware return forecasts.
Tasks:
- Establish separate intraday, short-term, and medium-term models.
- Estimate expected net returns and downside distributions.
- Compare Ridge/logistic baselines with the existing tree models.
- Keep model versions immutable once used for prospective testing.
- Log predictions before the outcomes occur.
- Track calibration and model drift.
- Make abstention—choosing not to trade—a first-class decision.
Acceptance criteria: The system produces timestamped, reproducible forecasts and can demonstrate whether those forecasts improve decisions on data not used to fit the models.
Phase E — Rebuild Capital Allocation Around Evidence
Objective: Stop weakly supported strategies from automatically taking capital from other candidates.
Tasks:
- Separate eligibility from ranking.
- Add minimum evidence and data-quality gates.
- Evaluate strategies on expected net returns, downside risk, capital usage, and incremental value.
- Incorporate forward evidence when sufficient independent observations exist.
- Prevent unnecessary forced liquidation solely due to small ranking changes.
- Restore the Intraday Runners' SHADOW gates.
- Keep options and other unvalidated execution paths inert.
Acceptance criteria: Every live capital assignment has a recorded eligibility decision, evidence summary, risk assessment, and explicit authorization where required.
Phase F — External Benchmark and Independent Replication
Objective: Check that Stockbot's research is not merely validating itself.
Tasks:
- Select representative strategies and reproduce them independently in LEAN or another suitable framework.
- Compare signal timestamps, corporate actions, fills, costs, and performance.
- Benchmark academic factor implementations against published reference data.
- Investigate discrepancies instead of selecting the engine with the best reported results.
Acceptance criteria: The independent replication results and unresolved differences are documented, with no material unexplained accounting or execution discrepancies.
11. What I would do with the existing $100 account
I would separate the research budget from the real-money trading budget.
The real-money account should not be used as the primary mechanism for discovering whether an unproven strategy has an edge. At the current account size, a few bad trades can materially change the balance, while the limited buying power makes the live sample small and uneven.
My immediate recommendations are:
1. Put both Intraday Runners in SHADOW.
2. Do not enable options trading.
3. Do not increase capital allocated to a strategy simply because its backtest ranks first.
4. Keep the prospective test unchanged.
5. Correct the known accounting and execution discrepancies before trusting any new ranking.
6. Continue research and paper testing without expanding the number of strategy families.
7. Require a new evidence review before any strategy is promoted to live trading.
The existing drawdown tiers remain useful as emergency safeguards, but they are not a substitute for strategy validation. A daily loss limit can constrain damage without making a losing strategy profitable.
I would also add a portfolio-level review trigger tied to both absolute losses and the reliability of the strategy evidence. The review should examine whether the account's losses are coming from poor predictions, poor execution, excessive turnover, or incorrect strategy allocation.
12. The concrete next step: a governed Alpha Research and Validation Engine
Here is the implementation brief I would give Claude.
The aim is not to rewrite Stockbot2000. It is to build on the architecture you already have, using your existing research registry, data, accounting, simulator, forward-testing tools, and risk engine.
Claude implementation brief
Project: Stockbot2000 — Alpha Research and Validation Engine
Objective
Improve Stockbot2000's ability to predict future returns and discover genuine, incremental alpha by incorporating documented academic strategies, published quantitative factors, open-source implementations, and selected commercial research or data sources.
The objective is to improve expected net trading returns after realistic costs. Strategy count, backtest score, win rate, and model complexity are not success criteria on their own.
Starting conditions
Use the 2026-10-19 independent-review dossier as the baseline.
The existing architecture, including the Knowledge Strategy Factory, strategy registry, simulator, survivorship framework, forward-test funnel, prospective test, execution engine, and risk engine, must be preserved unless a demonstrated defect requires a change.
Do not begin by adding a large collection of strategies or unfreezing evolutionary search.
Workstream 1 — Integrity and accounting
1. Audit the corporate-action issue in paper trades and quantify affected records.
2. Resolve the paper engine's same-close fill inconsistency.
3. Reconcile live equity, positions, cash, and trade ledgers.
4. Verify cost calculations and execution assumptions.
5. Include Runner signals, minute bars, and heartbeat data in backups.
6. Preserve original records and store corrections as versioned restatements.
7. Add regression tests for each corrected defect.
Workstream 2 — Research registry
1. Inventory the existing published factors, knowledge reproductions, and internal strategy families.
2. Establish stable signal identifiers, source provenance, exact definitions, horizons, and data requirements.
3. Distinguish faithful published-strategy replication from modified variants.
4. Record all material research trials and rejected variants.
5. Define a multiple-testing policy that accounts for the number of hypotheses examined and the dependence between signals.
6. Prevent results from the exploratory sample from being presented as independent validation.
Workstream 3 — Academic and commercial research integration
1. Begin with a small set of documented momentum, value, quality, earnings-surprise, reversal, and low-risk hypotheses.
2. Use authoritative published methodologies and reference datasets where available.
3. Evaluate each source's methodology, timestamp quality, historical coverage, licensing, cost, and implementation requirements.
4. Reproduce the source methodology as faithfully as the available data permits.
5. Then evaluate Stockbot-specific implementations separately.
6. Add commercial datasets only when a defined experiment shows why the existing data is insufficient.
7. Do not import published performance figures as if they were Stockbot results.
Workstream 4 — Incremental alpha evaluation
1. Standardize return targets for intraday, short-term, and medium-term horizons.
2. Establish simple benchmark models.
3. Measure standalone and conditional predictive value for each signal.
4. Run ablation tests and measure incremental out-of-sample improvement.
5. Evaluate dependence between signals and the diversity of their prediction errors.
6. Report uncertainty, transaction costs, drawdown, turnover, capital utilization, and performance stability.
7. Use only point-in-time information and prevent future-data leakage.
8. Preserve untouched evaluation periods and the existing prospective test.
Workstream 5 — Prediction models
1. Benchmark simple rules and linear models before introducing more complex machine learning.
2. Evaluate the existing XGBoost and analog models against the same baselines and observations.
3. Produce expected net returns, positive-return probabilities, downside estimates, and uncertainty measures.
4. Separate models by holding period.
5. Log predictions before outcomes occur.
6. Version models and prevent unvalidated changes from affecting live decisions.
7. Allow the model to abstain when its expected net return is insufficient or its estimate is unreliable.
Workstream 6 — Evidence-gated allocation
1. Separate strategy eligibility from strategy ranking.
2. Do not rank strategies on backtest scores alone.
3. Include out-of-sample performance, forward evidence, uncertainty, downside risk, implementation costs, and incremental predictive value.
4. Avoid forced rotation based solely on small ranking differences.
5. Return both Intraday Runners to SHADOW until the evidence gates have been satisfied.
6. Keep options trading disabled.
7. Do not change live capital allocation automatically as a side effect of research or model training.
8. Preserve the owner's explicit authority over LIVE deployment.
Engineering requirements
- Inspect the actual repository before designing or modifying modules.
- Reuse existing modules wherever practical.
- Identify dependencies and expected changes before implementation.
- Use bounded, reviewable tasks with explicit file paths.
- Add regression tests for new behavior and corrected defects.
- Run the full existing test suite after each logical milestone.
- Preserve append-only records and existing research provenance.
- Do not commit with failing tests.
- Do not modify the registered prospective-test criteria.
- Do not introduce a paid data dependency without explicit approval.
- Do not arm new live strategies as part of this project.
- Every milestone must produce working code, tests, and a report—not merely a plan.
Required deliverables
1. Repository audit and prioritized defect report.
2. Signal and strategy inventory with provenance.
3. Reproducible academic-strategy benchmark report.
4. Incremental-alpha evaluation framework.
5. Baseline-versus-advanced-model comparison.
6. Prediction and uncertainty reporting.
7. Evidence-gated strategy-selection design.
8. Automated regression tests and a reproducible evaluation command.
9. Final report distinguishing demonstrated findings, unresolved hypotheses, and failed experiments.
10. A prioritized list of the next research experiments based on the evidence—not on which ideas appear most exciting.
Completion standard
The phase is complete when Stockbot can demonstrate, reproducibly, which signals add predictive information beyond its baseline, whether that information survives realistic costs and untouched evaluation, and how the evidence affects strategy eligibility.
The phase is not complete merely because additional strategies, indicators, or models have been implemented.
My final recommendation
I would make three decisions now.
First, stop expanding the strategy count. You already have enough candidates. Concentrate on replication, incremental predictive value, and out-of-sample validation.
Second, build the Alpha Research and Validation Engine before adding more sophisticated prediction models. It will give your existing XGBoost, analog forecasts, published factors, and knowledge-based strategies a consistent way to prove their value.
Third, separate research success from trading permission. A model can be useful without being ready to trade real money. Stockbot should earn the right to allocate capital through evidence, not through its position in a backtest leaderboard.
The most important principle is this:
Do not ask Stockbot to find the strategy that made the most money in the past. Ask it to find information that improves future-return predictions, demonstrate that the improvement is real, and trade only when the expected net benefit justifies the risk.
That is the direction I would take to give Stockbot2000 its best chance of becoming a genuinely useful quantitative trading system.
