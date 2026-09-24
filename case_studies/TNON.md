# Case study: TNON, 2026-09-14 to 2026-09-16

Phase 6 §24. One real-money trade, used as a case study. Not evidence that
the strategy is bad, and not evidence that it is good: one trade can show
neither. What it does show is a gap in the data and in the controls, and
that gap is what this document is about.

## What happened

| | |
|---|---|
| source | daily book, `lab_survivor` path (a Strategy Lab survivor genome), rank 1 |
| book date | 2026-09-11 (built from 09-11 data) |
| filled | 2026-09-14, placed by hand: **3 whole shares for $16.62** (~$5.54). Not $20 of fractional shares, as the book assumed |
| stop | $4.8753 (ATR-based) |
| closes | 09-14 $5.56 · 09-15 $5.06 · 09-16 **$3.91**. The stop was breached at the close; the exit is the next session's market order |
| result | about **-29%** on the position. **67% of the Agentic account's whole loss** at the time |

## What the system knew

- Price about $5.54: over the $5 floor.
- 20-day dollar volume **$102M/day**: far over the $1M/day liquidity floor.
- A survivor genome's entry rule had fired.
- Clean price data. Nothing tripped the reverse-split anomaly flags: the
  adjusted price was a normal-looking $5, not a $549-trillion TOPS-style
  artifact.

## What it failed to know

- **Market cap. TNON had none on record.** `fundamentals.market_cap` comes
  only from parsed SEC filings, and TNON's filings were not parsed. It was one
  of ~800 liquid names with no cap.
- The company was about **$3.5M**. It had just done a **1-for-35 reverse
  split** to regain Nasdaq's minimum-bid compliance, then jumped ~70% on a debt
  payoff. The $102M/day was a blow-off: about 29x its whole market cap trading
  every day. That is not liquidity.
- The fill: 3 whole shares, not $20 of fractional. Every value derived from
  the assumed size overstated the position by 20%.

## Why it passed

1. **Price and volume cannot see size.** The floors in force were price and
   dollar volume. Blow-off volume makes a nano-cap look maximally liquid,
   just as serial reverse-splitters look maximally liquid on inflated prices.
2. **There was no size floor on the Lab/classifier path** when the book was
   built on 09-11. It was added on 2026-09-14, the day of the fill.
3. **The obvious size floor would not have caught it.** A plain "reject if
   the cap is below $100M" test waves through a name with *no* cap as
   unmeasured. TNON had no cap.

## Which data field was missing

`fundamentals.market_cap` for TNON, so `quote["market_cap"]` was `None`
everywhere downstream.

## Which control should have rejected it

A size floor that **fails closed**: reject a cap below `min_market_cap_usd`
($100M), and **reject an unknown cap too**. A missing measurement is not an
average one.

## The controls in force now

| path | control | since |
|---|---|---|
| risk engine (every order: SIMULATION, SHADOW, LIVE) | `_check_tradeability`: cap < $100M is rejected, **cap unknown is rejected** | 2026-09-22 |
| daily book, Lab and classifier paths | `daily_picks._size_filter`: same rule, `require_known_market_cap: true` | 2026-09-14 |
| quotes | `market_caps.py`: the filing cap, else a Robinhood or yfinance cap no more than 7 days old, dated and sourced. **Still unknown means still rejected.** | 2026-09-24 |
| fills | `picks.shares` records the filled quantity, never a derived one | 2026-09-14 |

## Does it catch equivalent securities?

Yes, on each route a TNON-like name can take. `tests/regression/test_tnon.py`
covers all of them:

- **TNON exactly** (no cap anywhere, $102M/day, ~$5.54): rejected by the risk
  engine as *market cap unknown*, and dropped by the daily book's size filter.
- **TNON with a sourced cap** (the market-cap fallback returns $3.5M):
  rejected as *below floor*. Before 2026-09-24 this route did not exist; the
  fallback exists to let real large caps through (GEN, NWSA), and it must not
  let nano-caps through with them.
- **Fallback fails or is stale** (no answer, or a cap older than 7 days):
  still unknown, still rejected.
- **The control is not a blanket ban**: an equally liquid name with a known
  $5B cap passes the same checks.

## What this does not fix

- **Overnight gaps.** Stops are checked on quotes, and an exit is a market
  order placed during the session. A gap through the stop is not protected
  against, whatever the size floor does.
- **A name just over the floor.** A $120M company doing $100M/day passes. The
  floor is about size; it is not a detector for pump-like turnover. A
  turnover-to-cap check was considered and not added: it would need a known
  cap, and a known cap under the floor is already rejected.
- **A single trade proves nothing about the strategy.** The Lab genome that
  picked TNON is judged by its forward record and the league's sample floors,
  not by this outcome.
