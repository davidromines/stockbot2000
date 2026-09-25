# Stage M — research: realistic dead companies

2026-09-25. Owner: "I want to narrow down our survivorship and improve our
database. I want the backtesting to be reliable and useful ... dont just build
M. research it." This is the research, the diagnosis of generator v4 against
it, what real data exists, and the design it leads to. Numbers below were read
from the papers themselves (PDFs in the session scratchpad), or measured on
this project's data today.

## 1. What a backtest actually needs from a dead company

A strategy never "holds the universe"; it buys what passes its filters
(`min_price` $5, `min_dollar_volume` $1M, its rule) and later sells. A dead
company changes a backtest only if, at some date, it was **tradeable and
signalled**. So the generator must get four things right, in order of how much
money they move:

1. **Which companies died, when, and how** — exit type (buyout / failure /
   SPAC liquidation / going private / exchange move), by exchange, era and size.
2. **The path while the company was still tradeable** — the decline into
   failure, or the run-up into a buyout — because that is what a strategy
   buys into and holds.
3. **The terminal step** — the delisting return for the shares still held.
4. **How many** — the death rate per year, so the universe is not too clean
   or too dirty in aggregate.

Everything after delisting (OTC trading) matters only as the price a holder
can get out at; our backtests exit at delisting.

## 2. v4, diagnosed

| | v4 today | what is true | source |
|---|---|---|---|
| exit reason known | **81 of 8,141** (1%); the rest drawn 40/55/5 performance/merger/other | the filings say, per company (tested: ANLY — SC TO-T tender offer, 25-NSE delisting date, 15-12B) | SEC EDGAR submissions |
| exit mix | one prior for every exchange and era | NYSE/AMEX 1962-93: 58% merger, 27% performance. Nasdaq 1972-95: performance **49%**, merger 27%, moved-up 18% | Shumway 1997 T.I; Shumway & Warther 1999 T.I |
| performance delisting return | N(−55%, 15%) Nasdaq, N(−30%, 15%) other | NYSE/AMEX: mean −29.9%, median −31.3%, **sd 48.9%**, **~11% become worthless (−100%)**, max +316% | Shumway 1997 T.V |
| | | Nasdaq: −55% effective, incl. lost liquidity; performance delisting rate 5.6%/yr vs NYSE/AMEX 1.2%; 2.95%/**month** in the smallest 5% | Shumway & Warther 1999 |
| | | 1999-2002 Nasdaq delistings that kept trading OTC: about −19% on delisting; volatility ×3, spreads ×3, volume −⅔ after | Harris, Panchapagesan & Werner 2008 |
| surprise | not modelled | about ⅔ of performance delists are surprises (halt, then gone); pre-announced ones lose ~14% at announcement | Shumway 1997 T.II, T.IV |
| failure path | lower tail of **buyout** donors' final years | distressed stocks: individual annual vol ~**94%**, skew ~**+2.5**, excess return ~−16%/yr, low price per share, small size | Campbell, Hilscher & Szilagyi 2008 T.6 |
| buyout path | one real buyout final year (v4) — passes the gate, AUC 0.48 | runup +13.3% over the 42 sessions before the bid; markup +15.8% to delisting (successful), within ~126 sessions | Schwert 1996 T.2 |
| SPACs | treated as operating companies: market beta, dead-company volatility | blank-check shells trade near the $10 trust with almost no volatility and liquidate at trust + interest; ~32% of 2020-22 SPACs liquidated | SPAC industry data (Boardroom Alpha, SPACInsider, AQR 2024) |
| blank-check shells in the synthetic set | ~1,100+ names ("... Acquisition Corp"), peaking 2022-23 | | measured |
| start price | random draw from real first closes | 10-K Item 5 reports **quarterly high/low prices**, cover page reports public float and share count — real price anchors for dead companies | SEC filings (tested: ANLY, 8 quarters per 10-K) |
| coverage before 2007 | almost none (Alpha Vantage's list starts ~2007) | the 2008 crisis and 2000-02 bust are inside the search window | measured: 1 synthetic death before 2007 |
| identity | 50% of synthetic companies have no CIK, so no filing can be linked | | measured |
| realism gate | AUC 0.593 overall (passes, barely); merger-only 0.484 | failures are not graded on their own | validation_v4.json |

**The core problem in one line:** v4 is good at buyouts and guesses
everything else. Failures are the case that hurts a backtest most and the
case it knows least about, because a bankrupt company's price history
disappears from free data.

## 3. Real data: what exists, what was tested

| source | result of testing today | use |
|---|---|---|
| **SEC EDGAR submissions + filings** (free) | works. Per company: form types and dates (SC TO-T / DEFM14A / 8-K 2.01 = acquired; 8-K 1.03 = bankruptcy; 8-K 3.01 = delisting notice; Form 25 / 25-NSE = delisting date; 15-12B/G = deregistration), 10-K Item 5 quarterly high/low prices, cover-page exchange, public float, shares outstanding, tender/merger price per share | **exit reason, dates, and price anchors** for every dead company with a CIK |
| **our own price database** | 1,312 real distress episodes (common stock, below $2 and >85% off its 52-week high); 78 of them died, 1,234 survived. 170 are from 2008-09 | **real decline paths** for synthetic failures — the decline is real whichever way the company ended |
| FINSABER S&P pickle (27.3 GB, on disk) | not imported yet | real paths for dead S&P 500 members |
| Yahoo "Q" tickers (bankruptcy OTC continuation) | **dead end**: 0 of 9 tested (LEHMQ, WAMUQ, GMGMQ, HTZGQ, JCPNQ, SHLDQ, BBBYQ, SIVBQ, RADCQ) | not used |
| Stooq | blocked behind a JavaScript bot check | not used — getting around bot checks is not done here |
| Kaggle "Quandl WIKI prices" | free, ~3,000 US companies incl. some delisted, to 2018; needs the owner's Kaggle account | owner's step, optional |
| Norgate / FirstRateData / EODHD / Sharadar (paid, ~$270-600/yr) | complete delisted histories | the only complete fix (M-paid, owner's call) |

## 4. Design — generator v5: anchored, evidence-first, per exit type

Principle: **use every real fact first; synthesize only between facts; tag
which is which.**

**A. Evidence layer (real).** For every dead company: link the CIK (name +
date match against EDGAR where the ticker route fails, with the ticker-reuse
check), then harvest from its filings: exit type and evidence form, delisting
date (Form 25), last 10-K date, exchange from the cover page, public float and
shares, quarterly high/low prices from every 10-K, deal price per share for
buyouts. Every field keeps its source form and accession number.

**B. Exit type.** Filing evidence where present. Where absent, a prior by
exchange × era × SPAC flag from the literature tables above, then recalibrated
on the companies whose exit the filings do reveal. SPAC shells are their own
type.

**C. Paths per exit type.**
- *Buyout* — v4's real final-year donor (it passes), ending at the filed deal
  price where known.
- *Failure* — three phases: (1) the decline, copied from a real distress
  episode in our own database matched on start price, size and era; (2) the
  delisting return drawn from Shumway's empirical distribution — a ~11% mass
  at −100% and a wide body (sd ~49%) centred at −30% NYSE/AMEX, −55% Nasdaq
  (effective, incl. liquidity), with ⅔ surprise gaps and ⅓ announced (−14% at
  notice); (3) no trading after delisting.
- *SPAC* — near-flat around $10 with tiny volatility, liquidating at trust +
  interest.
- *Other* (going private, exchange move, voluntary) — near-zero terminal step.

**D. Anchoring.** Where 10-K quarterly high/low ranges exist, a path is
constrained to pass through them (donor residuals rescaled piecewise between
anchors), so the synthetic price level and range match the real one quarter by
quarter. The unanchored remainder is tagged as such.

**E. The missing years.** Companies that filed 10-Ks naming an exchange on the
cover page (Section 12(b)) are listed companies — real listing evidence for
the EDGAR-only filers v4 excludes. That closes much of the 1996-2007 hole with
evidence rather than assumption.

## 5. Validation — four tests, the last two new

1. **Discriminability** (existing gate), now **per exit type** — a buyout pass
   can no longer hide an unrealistic failure.
2. **Moments vs literature** — failure-path volatility and skew vs CHS;
   delisting-return distribution vs Shumway; runup/markup vs Schwert.
3. **Twin test** (what matters for backtests): take real dead companies we DO
   hold prices for, hide their prices, generate synthetic twins from their
   filing evidence alone, run the same strategies on real and twin, and
   compare trade-level returns. Synthetic data is useful exactly to the extent
   the twin earns what the real company earned.
4. **Aggregate calibration** — the equal-weighted return of (real + synthetic)
   small caps per year against the CRSP-based Ken French series, which
   includes the dead (`bias_benchmark.py` measures the gap today at ~10
   points/year as an upper bound).

## 6. Build order (replaces M2-M4 in the roadmap; M1 done 09-25)

| step | what | where |
|---:|---|---|
| M2 | SEC evidence harvester: CIK linking, exit type, delisting date, Item 5 anchors, cover exchange/float, deal price | VM (network, ~10 req/s) |
| M3 | Distress donor library from our own database (1,312 episodes), phase-aligned | VM |
| M4 | Generator v5 (sections 4B-4E) | VM |
| M5 | Validation: per-type discriminability, moments, twin test, French calibration | VM |
| M6 | FINSABER S&P pickle as a further real-path source | VM, long |
| M7 | Paid delisted prices — owner's call | owner |

## Sources

- Shumway, T. (1997), *The Delisting Bias in CRSP Data*, Journal of Finance 52(1).
- Shumway, T. & Warther, V. (1999), *The Delisting Bias in CRSP's Nasdaq Data and Its Implications for the Size Effect*, Journal of Finance 54(6).
- Harris, J., Panchapagesan, V. & Werner, I. (2008), *Off but Not Gone: A Study of Nasdaq Delistings*, Fisher College WP 2008-03-005.
- Campbell, J., Hilscher, J. & Szilagyi, J. (2008), *In Search of Distress Risk*, Journal of Finance 63(6) (NBER w12362).
- Schwert, G.W. (1996), *Markup Pricing in Mergers and Acquisitions*, Journal of Financial Economics 41.
- Beaver, W., McNichols, M. & Price, R. (2007), *Delisting Returns and Their Effect on Accounting-Based Market Anomalies*, Journal of Accounting and Economics 43 (the −30% imputation convention).
- SPAC liquidation data: AQR (2024) *Are SPACs Still Alive?*; SPACInsider 2023 review; Boardroom Alpha SPAC statistics.
