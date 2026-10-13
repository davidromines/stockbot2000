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

## 2026-10-13 #5 — "How to make money in stocks (full guide)", @SRxTrades on X (link; read in the browser pane)

**What it is.** A Qullamaggie-style momentum-breakout swing system, ending in a
sales pitch for a paid "live swing trading challenge" (not opened). Rules:
1. Market filter: SPY/QQQ above the 8/21/50 EMAs = full size; chop = smaller size.
2. Scan: price > $3, market cap > $300M, volume > 500k, up on the day, ADR > 2%,
   price above 8/21/50 EMAs; sort by volume; keep a 4-5 name focus list.
3. Setup: tight base / pennant, volume drying up, above the averages; prefer daily
   or weekly charts; first or second "staircase" of a hot theme.
4. Entry: break of a repeatedly rejected resistance level on volume (5-15 minute
   entry), or an "undercut and reclaim"; stop at the low of the day.
5. Exit: trim 1/4 at a big resistance level and move the stop to breakeven, 1/4 on a
   close below the 8 EMA, 1/4 below the 21 EMA, the rest below the 50 EMA.
Claims: "made millions", NVDA / SMCI / TSLA / ARM / DELL caught. Unverifiable and
selected winners.

**What we already test, and how it differs.** Our `breakout_52w` (near the 52-week
high + volume ratio, fixed 10-20 day hold, ATR stop) and `volatility_breakout`
(volume surge + positive 10-day move) are NOT this setup. `volatility_contraction`
(low ATR z-score, above the 50-day) is the closest "tight base" analogue. Forward
paper record (whole history, plain iid t, overstated; ~15 sessions of one market):

| family | n | mean net / trade | t |
|---|---:|---:|---:|
| volatility_contraction | 97 | -3.43% | -4.0 |
| breakout_52w | 121 | -4.96% | -7.0 |

So the closest versions we run are negative. The post's distinctive parts are not
tested here: a resistance-level trigger, 8/21/50 EMA features (we have only SMA 50 /
200 and ATR), the trailing-EMA / quarter-trim exit, and market-regime sizing.

**Why parts cannot run as written.** Intraday 5-minute entries with a stop at the
low of the day are day-trade style; the account is limited margin with 3 day trades
per 5 sessions, trades via 5-minute cron and market orders, and slots hold one $20
position with no partial trims. The edge claimed lives largely in that intraday
entry. "Hot theme", "macro tailwind" and "clean structure" are discretionary.

**Evidence we do have on the exit idea.** The registered exit sweep (P2-P3) found
early profit-taking (5-10% targets, 2-3 ATR trails) lowered net per trade; only a
wide +20% target helped, on one strategy. That fits "let winners run" but is not a
test of closing-basis EMA trailing.

**Adopted (attach to Addendum F Phase E; one pre-declared version, no tuned
variants, counted in the trial ledger).**
1. **One Stage O reproduction** of the daily-bar mechanical core: above 21 and 50
   EMA, contraction (ATR z-score) then close above the prior N-day high on volume,
   next-open entry, exit on a close below the 21 EMA. Needs EMA features added to the
   daily panel first.
2. **Exit experiment**: add closing-basis EMA-trail exits to `exit_rules` and run on
   existing slot strategies, same adoption rule as P2 (wins the window and most
   blocks).
3. **Market-trend regime**: report families by "SPY above 21 and 50 EMA" vs not, next
   to the rate/dollar regimes in entry #3. Descriptive only.
Not adopted: the intraday entry, theme / focus-list picking, options leverage, the
paid course.

## 2026-10-13 #6 — "Claude has a Stock Trading Mode: 9 prompts" (@AiWithIqra thread on X)

**What it is.** A 10-post thread (read in the browser pane; X shows each reply only
to its first ~250 characters without logging in, and I did not sign in, so the
tails of the prompts are not read). Claim: Claude has a "Stock Trading Mode" that
can "research and trade literally any stock". The nine prompts are ordinary
equity-research templates: (1) company snapshot, (2) fundamentals table (growth,
margins, EPS, free cash flow, debt, ROE), (3) latest earnings vs guidance, (4)
valuation (P/E, EV/EBITDA, P/S, FCF yield, DCF), (5) score three competitors 1-10,
(6) catalyst and risk map with low/medium/high probabilities, (7) bull / base / bear
cases, (8) technical analysis (trend, support/resistance, 20/50/200-day), (9) a
decision checklist (portfolio size, risk tolerance, maximum loss). The one reply
(a CFA) calls the "mode" nonsense.

**Assessment.** I know of no Claude "Stock Trading Mode"; this is a prompt list
presented as a hidden feature. Claude does not place trades on its own: in this
project orders go through code (signal, risk engine, kill switches, broker), never
through a model. The prompts themselves are reasonable discretionary research
templates and worth nothing as an edge: they produce narrative, and an LLM given
"current financial data" without a data feed can invent figures (prompt 8 correctly
says to use live data only if verified).

**Map to what we have.** Fundamentals and valuation (2, 4): `value_metrics.py`,
the valuation engine, value score and Value Fund. Earnings (3): `sue_features.py`
and the `earnings_surprise` family. Technicals (8): the 20 indicators and families.
Checklist and max loss (9): `risk_engine.py`, ATR stop plans, the $25 order cap,
daily-loss and drawdown kill switches. Scores 1-10 and probability words (5, 6, 7)
are not calibrated numbers and cannot be backtested.

**Adopted.** None for the system. Reaffirmed rules: no model in the order path;
LLM text becomes a strategy only when it is turned into explicit, pre-declared
mechanical rules and tested like everything else (the `knowledge_extract.py` path
with its verification pass); no scheduled job calls an LLM. For the owner's own
research on individual stocks outside this system, the templates are fine as a
starting point, with every number checked against the filing.

## 2026-10-13 #7 — NQ 3-minute choppy-market dip-buy rules (screenshot, no source or results shown)

**What it is.** Rules only: Nasdaq-100 futures (NQ), 3-minute candles, 9:00-11:00 CT,
long only, one position. Trade only when the Kaufman efficiency ratio of the last 15
closes is <= 0.35 (choppy). One second after each candle closes, rest a buy limit at
close - 1.0 x ATR(14); fill only if price trades one tick THROUGH the limit; cancel
after 9 minutes. Target the middle of the signal candle; stop 1.5 x ATR below the
fill; time stop 15 minutes after the fill; flat at 11:00 CT. Modelled with one tick of
slippage on stops and market exits, and "the losing move assumed first inside each
second". No results, sample size or source are in the image.

**Does not fit as written.** NQ is a futures contract: our broker path has no
futures. Three-minute, two-hour-window trading is day trading: the account is
limited margin with 3 day trades per 5 sessions. Robinhood dollar (fractional)
orders are market orders only; a resting limit order needs whole shares, impossible
at $20 slots in most names. Minute history here is 132,555 bars, 20 names, since
2026-09-17 (about 16 sessions), too short to test an intraday rule.
Five parameters (0.35, 1.0, 1.5, 9 min, 15 min) with no stated derivation look
tuned; without the trial count and out-of-sample result it is a hypothesis, not
evidence.

**Worth keeping: the modelling honesty.** Fill a limit only on a trade THROUGH the
price, assume the adverse move happens first inside a bar, charge slippage on stops
and market exits, cancel unfilled orders. These match this project's stance (next-open
fills, gaps booked, costs in every trade). A search of `intraday.py` shows no
equivalent rule for its same-day SHADOW book; confirm when Addendum F audits D2.

**Adopted (attach to Addendum F).**
1. **Choppiness regime.** There is no efficiency-ratio code in the repo. Add a
   pre-declared 15-day Kaufman efficiency-ratio regime (<= 0.35 choppy) on daily
   bars and report each family by it, next to the rate / dollar / SPY-EMA regimes.
   Our forward-positive families are reversion and pullback types, the kind of
   strategy this regime is meant to favour. Descriptive only, gates nothing.
2. **Limit-entry experiment, research only.** For the reversion families, compare the
   next-open fill with a limit at prior close - k x ATR filled only on a trade-through,
   counting missed trades (adverse selection: fills cluster on falling days). One
   pre-declared k, no sweep.
3. **Intraday simulation rules.** Before any same-day strategy is believed, give
   `intraday.py` the three rules above (trade-through fills, adverse-move-first,
   slippage on stops).
Not adopted: futures, the 3-minute window, live limit orders, the numeric parameters.
If the original post had a backtest, share it; the numbers matter more than the rules.

## 2026-10-13 #8 — "The Deflated Sharpe Ratio: Separating Genuine Skill from Backtest Luck" (one-page explainer, after Bailey & Lopez de Prado 2014)

**What it is.** A two-column summary: with many trials the best Sharpe is inflated
by selection; SE(SR) ~ sqrt((1 + SR^2/2)/T) (Lo 2002); expected maximum of N
skill-less Sharpes ~ sigma * sqrt(2 ln N); the Deflated Sharpe Ratio compares the
observed Sharpe with the luck benchmark SR0 and adjusts for skew and kurtosis; a
three-layer audit: deflated Sharpe, out-of-sample holdout, Monte Carlo reshuffling
of the trade sequence.

**Checked.** Formulas (1), (3) and (4) match the published ones. **One number in the
text is wrong:** "one million zero-edge strategies over a one-year sample: best
Sharpe near 1.7". The formula gives about 4.9 (exact expected maximum 4.87,
sqrt(2 ln N) = 5.26); 1.7 corresponds to only ~4 trials. The correct figure is a
stronger version of the paper's own point. Also unstated: formula (4) needs Sharpe,
skew and kurtosis in the same per-period units as T, and N should be the EFFECTIVE
number of independent trials, not the raw count (ln N grows slowly but the choice of
N moves the bar a lot, below).

**What we already have, and the gap.** `promote.py` implements the deflated Sharpe
(Euler constant, expected maximum) and applies it at the Lab ladder's sealed-holdout
stage; `multiple_testing.py` keeps the trial counter, an `effective(total, unique)`
count and `noise_max_sharpe`. A search finds NO deflation or multiple-testing use in
`funnel.py`, `ranking.py`, `slots.py`, `factory_pipeline.py` or `strategy_health.py`.
So the forward-positive families, the ranking and the live slots are not deflated at
all; this is exactly the Addendum F A4 question and the answer is "not connected".

**Why it matters for the seven families (noise-only expected maximum of N independent
standard-normal t-stats; 95% = the level the max exceeds 5% of the time):**

| N (independent tests) | expected max | 95% threshold |
|---:|---:|---:|
| 88 (families) | 2.49 | 3.25 |
| 170 (honest simulator shapes) | 2.71 | 3.43 |
| 1,405 (specs) | 3.35 | 3.97 |
| 127,652 (unique Lab structures) | 4.44 | 4.93 |
| 1,000,000 (raw trials) | 4.87 | 5.32 |

Reported t: kf_mean_reversion 2.9, bollinger_reversion 3.2, st_momentum_1d 3.4,
st_uptrend_pullback 3.7, momentum 4.8, kf_seasonality 7.1, lab_search 17.2. Even with
the generous N = 88, two to three of the seven fall inside the luck range; with
N = 1,405 the first four do. This is BEFORE correcting the iid-trade standard error,
which makes every t smaller. The `lab_search` family alone drew from ~127k unique
structures, so its relevant bar is ~4.4-4.9; 17.2 clears it only if the dependence
correction leaves it above that. Indicative, not a verdict: N is uncertain and the
families are not independent.

**Adopted (Addendum F A3/A4/B3).**
1. **Deflation column in the funnel and ranking reports** (not a gate): each family's
   t and each strategy's per-trade score beside the noise-maximum for the stated N,
   shown for three N values so the sensitivity is visible.
2. **Effective N** from `multiple_testing.effective`, documented, never the raw trial
   count.
3. **Units**: deflate on per-period (daily portfolio) return series, with skew and
   kurtosis from the same series; do not mix per-trade means with annualised Sharpe
   (the project already hit this trap in `degradation.py`).
4. **Monte Carlo layer**: block-bootstrap / reshuffle each family's trade sequence for
   fragility of the equity curve, as the paper's layer (iii).
5. Heavy tails first: the skew and kurtosis terms are meaningless while corporate-action
   artefacts (entry #4, CTVA) sit in the data; clean those before computing DSR.

## 2026-10-13 #9 — "LEAPS are the best way to grow a small account" (social post, lead-magnet)

**What it is.** A claim that buying one LEAPS call (12+ months, leveraged exposure to
100 shares, defined maximum loss, no margin, no weeklies) is the best route for a
small account; results quoted: IREN +500%, HOOD +300%, NVDA +200%, META +59% in
under five months. The actual entry and strike / expiry rules are withheld behind
"comment LEAP for my cheat sheet" (not engaged). Nothing testable is stated.

**Assessment.**
- The quoted results are four large winners of a strong period, chosen after the fact;
  no losses, trade counts or total P&L are shown. A LEAPS gain is the underlying's
  move times leverage, less time value; leverage amplifies a stock bet in both
  directions and creates no edge of its own.
- "Defined maximum loss" means up to 100% of the premium; the post itself says
  mis-timed LEAPs "bleed to zero".

**Hard limits here.**
- **No LEAP data.** `option_quotes` has 6.9M rows, 702 symbols, 2020-01-06 to
  2026-10-09, but the longest expiry in it is 77 days; zero rows are 330+ days out.
  No LEAPS strategy could be backtested; all nine option strategies use 7-60 day
  windows.
- **Contract size vs account.** One NVDA or META LEAPS call costs thousands of
  dollars. The account is ~$86, the options paper stake is $100 a trade, and
  `books.py` already rejects a contract costing more than `max_contract_cost_usd`
  ($100). Only sub-$1.00 premiums fit: deep out-of-the-money lottery tickets, the
  opposite of the post's description.
- Owner rule (09-27): long single-contract options only is allowed in principle; real
  orders stay off (`allow_options: false`, no option level, no strategy proven).
- Our short-dated option paper strategies lose (-1% to -27% per trade over
  2020-2026), consistent with the research on buying options.

**Adopted.** Nothing now. One ordering rule for Addendum F: leverage via options is
considered only AFTER the underlying stock signal has an audited edge, then tested as
"same signal, stock vs LEAPS stock-replacement", which needs a LEAPS-length data
source first (add to the data wish-list; the current DoltHub pull stops at 77 days).
