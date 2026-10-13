# Ideas log

External ideas the owner shares for review. Each entry: what it is, what we take,
what we do not, and why. Nothing here changes live trading. Adopted items are
tracked in the plan they attach to (currently Addendum F, Stage AB).

## 2026-10-13 #1 — "24/7 autonomous crypto trading agent" prompt (screenshot)

**What it is.** A social-media prompt for a 24/7 crypto agent: an LLM "brain" does
research and code; a fast "reflex" model (a product called Jev) scores every
candle from an order-book snapshot in ~81 ms; hard risk limits live in code; the
system rewrites its own decision schema every night; a build harness (AgentKit,
agenkit.xyz) is to be installed into Claude Code. Promotional. The products and
latency claims are unverified; no site was opened and nothing was installed.

**Does not fit this system.**
- Order-book / millisecond trading. We trade US equities on daily bars through
  market orders, and crypto is gated off with a measured ~1.9% round-trip spread,
  which kills any high-frequency edge. We have no order-book feed.
- Nightly self-rewrite and auto-ship of the live decision logic. That is the loop
  that produced this project's measurement artifacts (selection on the same data,
  1.05M-trial search, now frozen), and live changes need owner approval.
- An LLM in the live order path emitting "calibrated probabilities". No evidence
  they are calibrated; our policy keeps LLMs out of execution.
- Fractional-Kelly sizing. It needs a trustworthy edge estimate; we have none yet,
  and overestimated edge makes Kelly overbet. Stock slots stay fixed $20.
- Narrative / tokenomics "asymmetric setups". Untestable and bias-prone.

**Already how we work (confirms the design).** Hard limits in code and outside the
model (`risk_engine.py`, `killswitch.py`, `config/risk.yaml`); brain/reflex split
(research factory vs execution layer); typed signal schema (`signals.py`); "survive
over looking profitable" is the project's standing caution.

**Adopted, attached to Addendum F.**
1. **Calibration of the ranking itself** (Phase B3/F): compare each strategy's
   predicted per-20-session return with what it later realised, as reliability
   bins plus a Brier-style score, not only a mean. Parts exist
   (`degradation.py`, `live_feedback.py`, `model_calibration.py`); extend, do not
   rebuild.
2. **A mandatory "WHAT COULD BE WRONG" section** in every audit report and weekly
   digest, listing the strongest argument against the headline finding.
3. **Nightly review stays measure-only**: read fills and misses, report; never
   rewrite live logic automatically.

## 2026-10-13 #2 — Quantpedia strategy encyclopedia + "test it" recipe (social post)

**What it is.** Pick a published strategy from Quantpedia (free tier), have an AI
build and backtest it, re-run only on data after publication, re-run on a market
the paper never touched (crypto pairs), verify on TradingView, incubate 1-3
months. Claims 1,368 strategies run in 2 hours, 277 passed.

**Already how we work.** Steps 1, 3, 4 and 6 are Stage O (Knowledge Factory:
reproduce first, then declared variants), Stage L (post-publication evidence only,
adopt at t > 3), Stage AA (Chan's Kalman pairs: fail after publication) and paper
incubation before any slot. Quantpedia is already a rule-description source for a
few curated entries (calendar effects, payday anomaly: all rejected net); it is not
bulk-ingested.

**Red flags.**
- "277 of 1,368 passed" (20%) is a multiple-testing warning, not a result. Here 94%
  of 1.05M search trials were net positive in backtests and none showed a durable
  edge; the pass rate says the bar is low.
- Step 5 (try 3 crypto pairs) is a new search over many markets; "a rule works on a
  coin nobody applied it to" needs the trial count charged. Crypto here also costs
  ~1.9% round trip, and buy-and-hold beat every crypto trend variant.
- TradingView verification is redundant: our simulator already fills at the next
  open, includes costs and models dead companies.
- tradingkit.com plugin: unverified third-party tooling; not installed.
- Quantpedia's paid library and terms: bulk copying may be restricted. Check terms
  before any scripted ingestion; the free tier is for reading.

**Adopted (attach to Addendum F, Phase E1/E2).**
1. **Out-of-universe replication as a prior, counted honestly**: when a documented
   strategy passes after-publication, one pre-declared replication on a different
   market or period counts as extra evidence, and every market tried is added to
   the trial ledger.
2. **Record each strategy's publication year** in `knowledge_library` so the
   after-publication window is computed, not typed (partly exists in Stage L).
3. **Pass-rate sanity line in reports**: show the share of tested strategies that
   pass beside the share a random-rule control passes (`random_control.py`).

## 2026-10-13 #3 — "Rising yields + rising dollar: plan for the worst case" (social post)

**What it is.** A macro-fear post. Claims: 10Y yield and dollar both rising; a -57%
crash followed a similar setup; "something underneath" is the trigger (private-credit
withdrawal gates, record auto-loan and office-CMBS delinquencies, 16-year-high
corporate bankruptcies, a narrow S&P held up by a few mega-caps, six small bank
failures in 2026). Advice: raise cash gradually, hold short Treasuries or the 10Y,
watch the mega-cap leaders (NVDA, AAPL, MSFT) for a breakdown, avoid junk / zombie
companies, favour quality over momentum, do not short the top, write a plan for
-10/-20/-30% before it happens. **All figures in the post are its own claims and are
unverified here.** The framing ("most important post you'll ever see",
"multi-millionaire") is promotional; one remembered crash is one path.

**Not for this system.** Personal portfolio advice (cash, Treasuries, buying the 10Y)
is not something this project decides or Claude advises on: the system trades $20
slots in one account and touches none of the owner's other accounts. Narrative
"triggers" cannot be tested. "Raise cash when leaders crack" is market timing; the
project's own regime test (bear-market entry rule, 2006-2026) found entries below the
200-day average did better, not worse.

**Useful as testable questions (all read-only, nothing live).**
1. **Rate and dollar regimes.** `regimes.py` has SPY, volatility, crisis and a fixed
   T-bill rate regime but no yield-trend or dollar-trend regime. Add pre-declared
   10Y-trend and dollar-trend regimes from free FRED series and report forward and
   backtest results per regime. Descriptive only: few independent episodes, so it
   gates nothing. (Addendum F Phase F.)
2. **Credit-event survivability.** Show each live slot holder and the seven positive
   families under the existing worst-case survivorship mode (`zero`: every death
   -100%) beside the as-is score, since the post's thesis is more failures.
   (Addendum F Phase D1.)
3. **Drawdown playbook + stress replay.** Write down what the system does at SPY
   -10/-20/-30% (ATR stops, no shorts, daily-loss and drawdown kill switches, idle
   slots stay cash) and replay the five slots through 2008, 2020 and 2022 with the
   existing windows. (Phase G.)
4. **Mega-cap leadership breakdown** as ONE pre-declared hypothesis in the knowledge
   library (HYPOTHESIS, no parameter variants), tested like any other. Low priority.

**Already in place.** No shorts; quality and low-debt factors in the factory
(profitability, Piotroski, debt reduction); $100M market-cap and $1M/day liquidity
floors that exclude most zombie micro-caps; kill switches at $15 / 15% daily loss and
35% drawdown.

## 2026-10-13 #4 — "Technical analysis taxonomy: price breaks come before indicators" (social post)

**What it is.** A tour of technical-analysis schools (Dow, candlesticks, chart forms
such as necklines and head-and-shoulders, Elliott, Wyckoff, Gann, "chip" cost
clustering, indicator schools). Claim: price itself (a neckline or prior-high break
on volume) is the fastest signal, KDJ/RSI crosses next, MACD slowest; indicators
confirm, they do not time. The author left technicals for news and fund-flow
direction.

**What this tests, and what we already have.** "Breakout on volume" is already
several paper-tracked families (`breakout_52w`: near 52-week high + volume ratio,
`volatility_breakout`, `kf_breakout`, `momentum_volume`; Donchian seeds). Forward
paper record, whole history, plain trade-level t (iid, so overstated):

| family | n | mean net / trade | t |
|---|---:|---:|---:|
| breakout_52w | 121 | -4.96% | -7.0 |
| volatility_breakout | 345 | -4.82% | -8.1 |
| kf_breakout | 183 | -4.20% | -18.9 |
| momentum_volume | 207 | -4.02% | -9.4 |

The "fastest signal" is the most negative group in the forward record. Speed of
confirmation is a latency claim, not an edge claim: arriving earlier at a crowded
entry costs more, not less. The families that are positive forward are pullback /
reversal / momentum, the opposite of chasing a break. (Subject to Addendum F audit.)

**Not adopted.** Necklines, head-and-shoulders, Elliott, Wyckoff and Gann have no
agreed mechanical definition, so each backtest hides many choices (researcher
degrees of freedom). Only a single pre-declared mechanical definition would be
admitted, as one hypothesis with no tuned variants. Candlestick patterns likewise.

**Possible, low priority.**
1. "Chip" cost clustering (volume-at-price, share of volume traded below the current
   price): computable from daily OHLCV as ONE pre-declared hypothesis in the
   knowledge library; the exact definition must be written before any result.
2. Fund flows (ETF share-count changes) as a Stage O data candidate; needs a
   point-in-time free source first. News is not usable yet: headline dates in the
   FINSABER set are unverified.

**Data-integrity leads found while checking (for Addendum F Phase A2 / D2; nothing
changed).**
1. **Corporate actions booked as losses.** Four paper trades in `CTVA` (four funds)
   show entry 78.5-79.5 and exit 12.57 within a week, about -84%. The prices table
   now holds a back-adjusted series (11.7 on 09-28), so an unadjusted entry price was
   compared with a post-event exit price. Likely a spin-off; the true loss is near
   zero. Any split or spin-off during a hold can do this. Check how many paper trades
   span a corporate action and how they move family means.
2. **Duplicate observations.** The same ticker/date trade appears once per fund (KOD
   +170% 09-24 to 09-28 appears three times in `lab_search` alone). This is the
   effective-n problem the audit already names, now with a concrete example.
3. **Recompute mismatch.** A plain recompute from `paper_trades` over all history
   gives momentum +2.04% (t 4.2, n 416) and st_uptrend_pullback +0.36% (t 1.5, n 627)
   against the funnel's +2.69% and +1.13%. The cut (window, dedupe, definition) is
   unknown. This is exactly the A1 reproduction step; unresolved.
