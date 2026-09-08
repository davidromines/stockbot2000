# Strategy Lab — Design Specification

An evolutionary search engine that invents trading strategies, scores them on 20
years of market history, keeps what works, and promotes only survivors to real money.

Decisions locked 2026-09-08.

---

## How it works

Generate a large population of trading strategies with **random settings** —
indicator weights, entry thresholds, stop distances, holding periods. Run each
against historical data as if it had been trading live. Score on money made
*relative to risk taken*. Best scorers survive, get mutated into variations, get
tested again. Bad ones die.

Repeat for thousands of generations and the population drifts toward settings that
actually worked. Every strategy ever tried — parents, settings, results — is
recorded, so the full family tree is inspectable and any branch can be revived.

**A strategy scoring well is not a reason to fund it.** Winners must clear a sealed
slice of history they have never seen, then trade on paper against live market data,
before any real dollars are involved. That gauntlet is the point of the design.

---

## The genome

Each candidate strategy is one setting of every gene below.

| Gene | Controls | Range |
|---|---|---|
| `indicator_weights` | Contribution of each of ~25 indicators to a stock's score | −1.0 … 1.0 each |
| `entry_threshold` | How high a score must be before buying | 0.50 … 0.95 |
| `stop_atr_multiple` | Stop distance in multiples of the stock's own volatility | 0.5 … 5.0 |
| `take_profit_pct` | Optional fixed profit target | none, 3% … 40% |
| `max_hold_days` | Forced exit after N days regardless of signal | 2 … 60 |
| `max_open_positions` | Portfolio concentration limit | 3 … 30 |
| `position_sizing` | Equal-weight / volatility-scaled / score-weighted | 3 modes |
| `sector_cap` | Max share of portfolio in any one sector | 15% … 100% |
| `min_liquidity` | Dollar-volume floor for tradeable names | $1M … $50M/day |
| `regime_filter` | Stand down when the broad market trends down | on/off + threshold |

This is deliberately a **tuning** space rather than open-ended rule synthesis. It
reuses the existing scoring pipeline, evaluates fast enough to test hundreds of
thousands of candidates per night, and keeps every result interpretable — you can
read a winning genome and understand what it does.

---

## Reward function

```
# per walk-forward window
window_score = sharpe(daily_returns_net_of_costs)
             × (1 − max_drawdown)                  # drawdown penalty
             × sqrt(n_trades / (n_trades + 30))    # small-sample shrinkage

# final fitness across all windows
fitness = mean(window_scores) − 0.5 × stdev(window_scores)
```

Each term blocks a specific failure mode:

- **Sharpe, not profit.** Returns divided by their own volatility. A strategy that
  doubles money via wild swings scores worse than one grinding out steadier gains.
  Costs and slippage are deducted *before* this is computed, so high-turnover
  strategies pay for their turnover.
- **Drawdown penalty.** A strategy that went 60% underwater keeps only 40% of its
  score. Deep drawdowns are what make people abandon a system mid-run.
- **Small-sample shrinkage.** A strategy with 4 trades and a perfect record is luck.
  Shrinkage pulls low-trade-count scores toward zero.
- **Consistency across time.** Subtracting the standard deviation across windows
  penalizes strategies that made all their money in one lucky year.

---

## Anti-overfitting protocol

| Period | Role |
|---|---|
| 2006 – 2019 | **Search.** Walk-forward. The population evolves here and only here. |
| 2020 – 2022 | **Validation.** Finalist selection. Covers the COVID crash and 2022 bear market. |
| 2023 – present | **Sealed.** Opened once per strategy, at the funding decision. |
| Forward | **Paper trading** on data that did not exist at design time. |

Two safeguards on top of the split:

**Trial-count correction.** Testing 200,000 strategies inflates the winner's Sharpe
purely by how many were tried. The ledger records the exact trial count so a
deflated Sharpe ratio can be computed for any finalist.

**The sealed period is genuinely sealed.** Not used for scoring, ranking, early
stopping, or "just checking." Each strategy may be evaluated against it exactly
once. Every peek costs statistical validity, and there is no way to un-peek.

---

## Promotion ladder

Counts illustrative of one weekly cycle.

| # | Stage | Survivors |
|---|---|---|
| 01 | Population search (2006-2019 walk-forward) | ~200k/night |
| 02 | Survivor shortlist (deduplicated) | ~200 |
| 03 | Validation window (2020-2022) | ~10 |
| 04 | Sealed holdout, deflated Sharpe applied | ~2-3 |
| 05 | Live paper trading | 1-2 |
| 06 | Funded, small fixed stake + kill rule | funded |

Most candidates dying at stage 03 is the system working correctly, not a failure.

---

## Idea ledger schema

```
strategies    — id, parent_id, generation, genome (JSON), created_at, status
evaluations   — strategy_id, window_start, window_end, sharpe, return,
                max_drawdown, n_trades, fitness, trial_index
promotions    — strategy_id, stage, decision, evidence, decided_at
live_trades   — strategy_id, ticker, entry/exit price + date, pnl, exit_reason
```

Full trade-by-trade ledgers are kept only for shortlisted strategies — storing every
fill for 200k nightly candidates would balloon the database for no benefit. Everything
else keeps summary metrics, which suffices since the genome fully determines behavior
and any strategy can be re-run from it.

---

## Modules to build

| Module | Role |
|---|---|
| `genome.py` | Search space definition, mutation and crossover operators |
| `simulator.py` | Vectorized backtest with costs, slippage, liquidity filters. The hot inner loop. |
| `reward.py` | Trade ledger → fitness score |
| `evolve.py` | Population loop and parallel worker pool |
| `ledger.py` | SQLite persistence for strategies, lineage, evaluations, promotions |
| `promote.py` | Enforces the ladder, including the once-only rule on the sealed period |
| `lab_dashboard.py` | HTML leaderboard and lineage views |

---

## Compute plan

Sized for 4 vCPU / 12 GB on Arena, overnight while the other VM is quiet.

The search must not touch the full 40M-row database on every evaluation. The
simulator preloads a compact `float32` matrix covering the liquid tradeable subset
(~1,500 tickers after liquidity filters) into **shared memory**, so all four workers
read one copy rather than each holding their own. Winners are re-validated against
the full universe before promotion.

| Metric | Value |
|---|---|
| Shared search matrix in RAM | ~900 MB |
| Parallel evaluation workers | 4 |
| Strategies evaluated per 8h night | ~200k |
| Ledger growth | ~5 GB/year |

Scheduling constraints: the search and the Ollama LLM report must not run
simultaneously (together they exceed 12 GB). Since 4 vCPUs fully commits the host
alongside the other VM, pick the overnight window against that VM's actual quiet hours.

---

## Risks

**Survivorship bias is a data problem, not a config flag.** yfinance largely does not
serve delisted companies. A universe built from currently-listed tickers silently
excludes every bankruptcy and acquisition, which flatters every backtest run against
it. Fixing this needs point-in-time data with dead tickers included (~$50-100/month).
The alternative is accepting a known-but-unmeasured optimistic bias. **Unresolved
decision.**

**The search will find noise, reliably and convincingly.** Not a flaw in the
implementation — it is what large searches over noisy data do. 200,000 random
strategies tested against the same history will produce dozens with beautiful equity
curves that mean nothing. The validation ladder catches most, but "most" is not "all."

**Market regimes change.** A strategy validated on 2006-2022 is fit to a world with
particular interest rates, liquidity conditions and market structure. Weekly
re-search keeps the population adapting but cannot anticipate a regime that has not
happened yet.

**Slippage estimates are estimates.** Since the search actively hunts for edge, it
gravitates toward strategies whose profitability is sensitive to exactly this
assumption. Test finalists under deliberately pessimistic cost assumptions before funding.

**Paper trading is not live trading.** Paper fills are frictionless in ways real
orders are not. Better than any backtest, but the step to funded is still a step
into new information.

---

*This document describes a system design, not investment advice. No backtested or
simulated result is a prediction of future returns.*
