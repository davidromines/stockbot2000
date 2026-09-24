# Architecture

Stockbot2000 ingests daily price bars and point-in-time fundamentals, derives
features from both, and runs steppers that advance simulated and paper funds one
session at a time. Those steppers write a forward record — equity curves, trades,
marks — that a research layer reads to rank strategies, measure degradation, and
decide promotion. The end of the chain is the slot trader (`slot_trader.py`),
which since 2026-09-24 places real orders in the Robinhood Agentic account
through the execution engine, risk engine and kill switches. The older
morning slate for a human (`orders.py`) still exists beside it.

## Daily pipeline

Each arrow is a real dependency: the stage on the right reads what the stage on
the left wrote. Running them out of order produces stale or missing inputs, not
an error.

```
universe.py --record          symbol directory, stamps delistings
  -> backfill.py --top-up     price bars
  -> build_features.py        20 indicators
  -> fundamental_features.py  filings lagged to availability
  -> freshness.py             FAILS the run if any of the above is stale
  -> paper_trading.py         the 16 paper funds step one day
  -> pair_funds.py            the 5 ETF switching funds
  -> value_fund.py            the Value Fund marks to market
  -> daily_picks.py           the daily book
  -> orders.py                the morning slate a human places
  -> [human places orders]
  -> orders.py --record-fills reconciliation
```

| Stage | Produces |
|---|---|
| `universe.py --record` | `historical_listings`, `delistings` — who was tradeable, when |
| `backfill.py --top-up` | `prices` rows for the current session |
| `build_features.py` | `features` — 20 indicators per ticker-date |
| `fundamental_features.py` | `daily_fundamentals`, lagged to filing availability |
| `freshness.py` | `freshness_log`; non-zero exit if any input is stale |
| `paper_trading.py` | `paper_runs`, `paper_equity`, `paper_positions`, `paper_trades` |
| `pair_funds.py` | `pair_funds`, `pair_fund_equity` |
| `value_fund.py` | Value Fund marks |
| `daily_picks.py` | `picks` |
| `orders.py` | `orders` in state `proposed` |
| `orders.py --record-fills` | `fills`, order state transitions |

## Research layer

Reads the forward record. Never writes to it.

| Module | Decides |
|---|---|
| `league.py` | Strategy identity, immutable versioning, the 10-state lifecycle |
| `scoreboard.py` | Ranks strategies — and refuses to, below 60 equity marks |
| `degradation.py` | Backtest vs forward return, per trade |
| `eligibility.py` | Correlation, and the top-five-eligible rule |
| `promotion_policy.py` | RETIRED 2026-09-24 — replaced by `ranking.py` + `slots.py` |
| `allocation.py` | RETIRED 2026-09-24 |
| `roster.py` | RETIRED 2026-09-24 |
| `live_pipeline.py` | RETIRED 2026-09-24 |
| `ranking.py` | The one ranking: backtest first, paper evidence takes over |
| `slots.py` | Which strategies hold the five slots. Places no order |

## Execution layer (Addendum A)

The only path from a decision to a broker. Run from cron every 5 minutes in
market hours.

```
slots.py (who holds each slot)
  -> slot_trader.py --auto        entry pass once per session, stop monitor after
  -> execution.py                 duplicate check, record
  -> killswitch.py                global + per-strategy switches
  -> risk_engine.py               floors (price, liquidity, market cap: unknown
                                  rejected), sizing, loss limits, PDT and
                                  settled funds (account_rules.py)
  -> robinhood_live.LiveBroker    review -> place -> confirm, ref_id idempotent
  -> robinhood_mcp.py             Robinhood Trading MCP (OAuth, owner signs in)
```

Quotes come from Robinhood in LIVE (`robinhood_live.RobinhoodQuotes`), with
liquidity from `features` and market cap from the filings, else
`market_caps.py`. A pair-fund slot trades the ETF `pair_funds.next_leg()`
names.

## Data layer

| Module | Owns |
|---|---|
| `storage.py` | `market_data.db`; the only module writing SQL to it |
| `statements.py` | The three financial statements, point-in-time |
| `valuation.py` | Multiples, industry-aware |
| `intrinsic.py` | DCF and four other methods, with mandatory sensitivity |
| `value_score.py` | Nine dimensions, ranked within industry |
| `pit_facts.py` | "What was knowable on this date" |

## Boundaries

1. Nothing in the research layer imports `broker` or `execution`. Only the
   execution side does: `slot_trader.py`, `run_execution.py`,
   `crypto_orders.py`, `robinhood_live.py` and `acceptance.py`. The league
   must not be able to place an order, so the import graph is the enforcement
   rather than a reviewer's attention.
2. `storage.py` is the only module that writes SQL to `market_data.db`. One
   writer means one place where a schema change or a bad transaction can
   corrupt the store.
3. The forward record tables (`paper_runs`, `paper_equity`, `paper_trades`,
   `pair_funds`, `value_fund_*`) are written only by their own stepper. The
   league migration reads them and never writes, so a ranking run cannot
   rewrite the history it is ranking.

## Storage

Two databases, deliberately separate:

- `data/market_data.db` (~9 GB) — prices, features, fundamentals, filings,
  the forward record. Everything the pipeline reads.
- `data/positions.db` — the trade ledger.

They are separate so that a corrupt or locked market-data store cannot take the
trade ledger with it, and so the ledger can be backed up on its own.

## Where to look when a number is wrong

| Symptom | Look at |
|---|---|
| A price or bar looks wrong | `backfill.py`, then `storage.py` |
| A feature value looks wrong | `build_features.py` |
| A fundamental looks wrong, or is dated wrong | `statements.py`, `pit_facts.py` |
| A ranking or eligibility call looks wrong | `scoreboard.py`, `eligibility.py` |
