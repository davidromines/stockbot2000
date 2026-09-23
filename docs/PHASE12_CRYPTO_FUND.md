# PHASE 12 — CRYPTO FUND

Added 2026-09-23 at the user's request, from
`https://x.com/milesdeutscher/status/2102407531771601246`
("How to Build an AI Trading Bot to WIN the Crypto Bull Run").

---

## What the source article proposes

A four-layer architecture:

```text
Claude (brain)  ->  exchange MCP (bridge)  ->  exchange (execution)
                         ^
                    Telegram (control)
```

Plus a "context brain" folder of markdown rules, a `Memory.md` trade ledger, a
learnings file, and a strategy taken from Pine Script, GitHub or TradingView.

## What this project already has, and where it is stronger

| Article | Stockbot2000 |
|---|---|
| A `.md` folder of trading rules | `CLAUDE.md`, versioned, with the reasoning behind each rule |
| `Memory.md` trade ledger | `positions.db` + `picks` + `paper_trades`, queryable |
| "Learnings file" | The measurement-bug record: ten defects, each with what it cost |
| Telegram control | `notify.py`, running since 2026-09-12 |
| Strategy from GitHub/TradingView | `strategy_library.py` — 40 entries, provenance required |
| Exchange MCP execution | `execution.py`, `risk_engine.py`, `killswitch.py`, `broker.py` |
| — | A null surface, sealed holdout, next-open fills, 1.05M trials counted |

**The genuinely new requirement is crypto market data and a crypto fund.**
Everything else in the article exists here in a more rigorous form.

## THE ONE THING THIS PHASE DOES NOT BUILD

**The article's execution layer — an LLM placing orders on an exchange
autonomously — is out of scope and stays out of scope.**

Two independent reasons, either sufficient:

1. **Claude does not execute financial transactions.** This is the standing
   constraint the whole project is built around: the loop is *system generates
   -> human places -> system reconciles*. It is not a training-wheels measure
   to be removed later.

2. **This project's own evidence.** `docs/ROBINHOOD_AGENTIC.md` already records
   the sharpest open question: *autonomous execution of a strategy with no
   demonstrated edge automates the losses, and nothing in this project has yet
   demonstrated one.* Adding a second asset class does not change that; it
   doubles the surface.

The article's own framing makes the risk explicit — it recommends "a completely
separate exchange account just so your funds are sandboxed and your entire
portfolio is not at risk due to an AI error." That is a sensible precaution
against a failure mode the author expects to occur.

## Scope

### 12.1 Crypto market data
- OHLCV for a defined set of pairs, from a public API with no key
  (Binance public klines is what SETS uses and is free).
- Into `market_data.db` under a `crypto_prices` table, NOT `prices` — crypto
  trades 24/7 with no session boundary, and mixing it into a table whose every
  consumer assumes US market sessions would silently corrupt the freshness
  gate, the next-open fill convention and every existing backtest.
- `security_type = 'crypto'` in `symbols`, so `tradeable_types` continues to
  exclude it from the equity screens by default.

### 12.2 The session problem
Crypto has no close and no next open. **The next-open fill convention cannot
be carried over unmodified**, and this must be decided explicitly rather than
inherited:
- a fixed daily boundary (00:00 UTC) treated as the "session", or
- fill at the next bar's open on whatever bar interval is used.

Whichever is chosen, `simulator.py` must be told which convention applies, and
the null surface must be rebuilt on crypto data. **A null computed on equities
is not the null for crypto.**

### 12.3 Crypto paper fund
Modelled on `value_fund.py`: its own tables, its own stepper, its own forward
record, NOT folded into the equity league. Same reasoning as the Value Fund —
a 24/7 instrument ranked on a scoreboard calibrated for equities would be
comparing quantities that are not alike.

### 12.4 Strategies
Enter through `strategy_library.py` as HYPOTHESIS, like everything else. The
SETS grid-DCA genome is already recorded there (`social:sets_machine`).

### 12.5 Order generation
`orders.py`-equivalent: writes a slate a person places. No transmit path.

## Ordering

Data first (12.1, 12.2), then the fund (12.3), then strategies (12.4), then
the slate (12.5). The session-convention decision in 12.2 blocks everything
after it: getting the fill convention wrong is the defect that cost this
project its largest correction, taking the classifier from +$1.63 to -$58.77
gross, and doing it again on a new asset class would be inexcusable.

## What will be true when this phase is done

A crypto paper fund with a forward record, and a daily slate. **Not** an
autonomous trading bot. The fund will hold nothing until it has a strategy
that clears the same gates as everything else, and no strategy in this project
has yet cleared them.
