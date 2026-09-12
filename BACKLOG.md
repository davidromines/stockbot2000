# Backlog

Ordered roughly by what unblocks the most value next — not a strict
commitment, just a working priority list.

## Survivorship bias — the open data-quality problem

**This is the largest known threat to every backtest number this system will
produce, and it is not fixed.** It is recorded here rather than in a comment
because it needs a decision, not a workaround.

The universe is built from instruments listed *today*. Every company that went
bankrupt or was acquired between 1962 and 2026 is absent, and yfinance does not
serve delisted tickers. A backtest can therefore only ever buy companies that
survived to the present.

Why a simple haircut does not fix it: the bias is not uniform across strategies.
A trend-follower would mostly not have bought companies sliding into bankruptcy,
but *would* have caught the takeover pops that are also missing — biasing it
downward. A mean-reversion strategy buying beaten-down names would have bought
the ones that went to zero — biasing it sharply upward. The Strategy Lab searches
~200k genomes and keeps the winners, so **it will preferentially discover exactly
the strategies whose apparent edge depends on the missing data.** A flat penalty
moves the distribution without touching that selection effect.

- [x] ~~**Research how others solve this.**~~ Done 2026-09-11. Shumway (1997)
  on missing delisting returns; corrections of -30% NYSE/AMEX and -55% Nasdaq.
  Norgate delisted add-on ~$270/yr, Sharadar low hundreds/mo, CRSP institutional.
  Ken French's library is free, CRSP-based and survivorship-free — used for the
  benchmark below.
- [x] ~~**Reconstruct the historical universe from the Internet Archive.**~~
  Partly done 2026-09-11 — `reconstruct_universe.py`, 55 NASDAQ captures,
  2008-2020. **Coverage was 29.5% in 2008.** Still to do: the NYSE half and the
  2020-2026 tail; archive.org rate-limits hard, and the run is resumable.
- [x] ~~**Quantify the bias.**~~ Done 2026-09-11 — `bias_benchmark.py` measures
  **10.4 percentage points a year** against CRSP. Apply this as a haircut to any
  backtest figure until delisted prices exist.
- [ ] **Old item, kept for reference — research how others solve this.** Before spending money, find out what
  practitioners actually do — quant blogs, r/algotrading, QuantConnect and
  Zipline docs on their delisting handling, academic treatment of delisting
  returns (Shumway 1997 is the standard reference on the missing-return bias).
  Specific questions to answer: what do retail algo traders consider the minimum
  acceptable dataset; how much annualised bias do people actually measure; does
  anyone publish a free delisted-ticker list.
- [ ] **Reconstruct the historical universe from the Internet Archive** (free,
  no purchase decision required). The Wayback Machine holds **73 archived
  snapshots of the NASDAQ Trader symbol directory going back to 2008** —
  confirmed available. Fetching those gives a point-in-time record of *which
  tickers existed when*. It does not give their prices, so it cannot remove the
  bias — but it converts an unmeasured bias into a **measured coverage gap**:
  "our 2012 universe covers N% of what actually traded, and here is the list of
  what is missing." That is the difference between a known and an unknown
  unknown, and it makes the buy/don't-buy decision informed rather than a guess.
  Cross-reference with SEC EDGAR filer history, where a company that stops filing
  10-Ks is a strong delisting signal.
- [ ] **Decide on paid point-in-time data.** Norgate (~$60-90/mo, built for
  backtesting, includes delisted securities and point-in-time index
  constituents), Sharadar via Nasdaq Data Link (~$50-150/mo), or CRSP
  (institutional, the gold standard). **Ask any vendor whether they supply
  delisting *returns*, not just prices up to the delisting date** — a bankruptcy's
  real terminal return is often -100%, and a dataset that simply stops at the
  last quoted price leaves the simulator assuming a calm exit, fixing perhaps
  half the problem. Note the awkward economics: $720-1,080/yr against a $100
  account. Suggested middle path is to buy one month, measure the delta on our
  own strategies, then cancel.
- [ ] **Free mitigations, worth doing regardless of the above.** Raise the
  Strategy Lab's `min_liquidity` floor (large-cap delisting rates are a fraction
  of microcap ones); add a delisting stress test that injects terminal -60%/-100%
  events at historically calibrated rates to find which genomes are fragile to
  what we cannot see; and weight paper trading heavily in promotion, since it
  has zero survivorship bias by construction.

---

## Capped deliberately — do not reopen

- [x] **Search capacity.** Four searches, four scoreboard artifacts. Capped at
  50 x 300 per run on 2026-09-12; see CLAUDE.md. The constraint is data, not
  compute. Add paper-trading calendar time instead.

## External data sources — closing the survivorship gap

Sources supplied 2026-09-12. Read each, tested each, results below.

- [x] **SEC EDGAR quarterly indexes — WORKING, free, no account, back to 1993.**
  `edgar_registry.py`. 136 quarters, 4.0 GB, 303,383 annual filings, **38,876
  distinct companies of which 31,752 (82%) stopped filing.** Reaches fifteen
  years further back than the Internet Archive reconstruction (2008) and so
  covers the financial crisis, which sits inside the search window.
  Gives the *universe*, not prices.

- [x] **Alpha Vantage LISTING_STATUS — WORKING with the user's free key.**
  `delistings.py`. One request returns the whole registry: **9,464 delisted
  listings, 7,480 common stock, of which we hold prices for 418 (5.6%).**
  7,062 companies a backtest here can never buy, each with an exact delisting
  date. Independently corroborates the Archive figure of 9,029.
  **Thin before 2009** — 4 delistings recorded for 2008 — so it does not cover
  the crisis. Use EDGAR for that era.

- [ ] **Stooq — blocked to automation, needs a human browser.** Every endpoint,
  including the documented CSV API, sits behind a proof-of-work bot check. Not
  bypassed deliberately. User downloading `d_us_txt.zip` manually; unknown
  whether delisted tickers are included, which is the only question that matters.

- [ ] **FirstRateData — the actual fix, and it costs money.** 16,302 tickers
  including **7,000+ delisted** back to 2000, which matches the size of our hole
  almost exactly. Free samples are two weeks only. This is the cheapest thing
  that would close the price half of the problem.

- [x] **CRSP zips — CONTAIN NO DATA.** Both copies identical; they hold WRDS
  reader scripts for `CRSP_StkDlySecurityData.dat`, a file only a subscriber
  has. Closed.

- [x] **Shiller — index-level only.** Monthly S&P Composite, dividends, earnings
  and CPI since 1871. A good long-run benchmark; contains no individual
  companies and therefore cannot touch survivorship bias. Closed.

- [x] **hfdatalibrary zip — 0 bytes**, a failed download matching the supplied
  `error.txt` ("Access denied"). Closed.

- [ ] **Next: use the registry instead of the average.** `bias_exposure.py`
  currently proxies risk by drawdown. With real delisting dates it can ask the
  exact question — what share of a strategy's entries were in names that
  actually disappeared within N days — and the flat 10.4-point haircut can be
  retired for anything after 2009.

## Near-term

- [ ] **Seed the search with known strategies.** The search currently starts from
  random genomes every time, which wastes most of generation zero rediscovering
  that `macd_hist > 0.4` is not a strategy. Research documented approaches —
  momentum, mean reversion, moving-average crossovers, RSI extremes, Bollinger
  reversion, breakout, dual momentum, turtle rules — encode each as a genome, and
  seed the initial population with them alongside random ones.

  Two benefits beyond speed. Each seed gets a **baseline P&L of its own**, so the
  ledger gains a row for "textbook momentum" against which everything else is
  compared. And mutation starts from structures that already make sense rather
  than from noise, so the lineage becomes interpretable — "this began as a moving
  average crossover and evolved a volume filter" is a far more trustworthy story
  than "this appeared at generation 23".

  Caveat to hold onto: a published strategy that still worked would not be
  published. Expect the seeds to lose money after costs, exactly as our baseline
  does. Their value is as reference points, not as candidates.

- [x] **Paired-ETF switching experiment (ERX/ERY) — CLOSED, FAILED, 2026-09-12.**

  The idea: hold ERX when the signal says energy rises, switch to ERY when it says
  energy falls. Never both at once. Structurally sound, and it solved a real
  constraint — ERY gives a cash-only, long-only account a bear position it
  otherwise cannot take. Run with `paired_etf.py`; the pass/fail rule was written
  into `verdict()` before the numbers were seen.

  4,475 days, 2008-11-19 to 2026-09-04, costs charged on every switch:

  | strategy | CAGR | max DD | switches | $100 becomes |
  |---|---|---|---|---|
  | buy & hold ERX | -5.4% | 100% | — | — |
  | buy & hold ERY | -40.2% | 100% | — | — |
  | **random switching (the null)** | **-24.6%** | — | — | (95th pct -6.3%) |
  | MACD (best signal) | **-11.1%** | 99% | 354 | $12.44 |
  | sma_50 | -18.8% | 99% | 334 | $2.48 |
  | momentum_20 | -22.4% | 99% | 430 | $1.09 |
  | rsi_14 | -27.4% | 100% | 528 | $0.34 |
  | dual_sma | -33.9% | 100% | 216 | $0.06 |

  **Verdict on the four pre-registered conditions:**

  | # | Condition | Result |
  |---|---|---|
  | 1 | Positive CAGR after costs | **FAIL** — -11.1% |
  | 2 | Beats the random-switch null | **FAIL** — -11.1% vs -6.3% (95th pct) |
  | 3 | Survives 2020-2022 validation | PASS — +93.9% vs null +87.7% |
  | 4 | Under 5% of random signals pass | PASS — 3% |

  Failing either of the first two closes it, and both failed. **The best signal
  tested loses money faster than switching at random.** Condition 3 passing is
  not a reprieve: 2020-2022 is the oil crash and the energy boom that followed,
  the single most favourable regime a trend signal on this pair could be handed,
  and even there it beat the null by only 6 points.

  Why it fails is structural, not a matter of finding a better signal. Both legs
  are 2x leveraged and both decay; you are always holding a decaying asset, and
  every switch pays a round trip. The switching idea was sound — the instruments
  are not. **Do not reopen without a non-decaying pair.**

- [ ] **Move the entry threshold into `config.yaml`** — the `70` cutoff currently
  lives in the Claude-side workflow and as a `--threshold` CLI arg on
  `backtest.py`. Nothing else in the system hardcodes a tunable, and the Strategy
  Lab treats `entry_threshold` as a gene, so it needs a config home first.
- [ ] **Take-profit is dead code.** `stop_loss.check_take_profit_triggered()` is
  implemented and `config.yaml` exposes `risk.take_profit_pct`, but
  `check_exits.py` only ever calls `check_stop_triggered()`. Either wire it in or
  drop it — right now setting the config key silently does nothing.
- [ ] **Gap risk on stops is unmitigated.** Stops are checked once daily against a
  quote, and dollar-amount orders can't rest at the broker. A stock that gaps
  through its stop overnight exits at whatever the next approved market order
  fills at. Worth at least measuring in the backtest before it matters live.
- [ ] **Reconcile the indicator count.** Code has 20 (`FEATURE_COLS`); `README.md`
  and `docs/STRATEGY_LAB.md` say ~25 in places. The genome's `indicator_weights`
  space must be built against the real number.
- [ ] **Telegram bot** — daily push notification with:
  - The day's scorecard (top N candidates + scores + reasons from `scoresheet.json`)
  - Currently open positions and their unrealized P&L
  - Any stop-losses triggered overnight
  - Requires: a Telegram bot token (via @BotFather), `python-telegram-bot`
    library, and a small script that reads `data/scoresheet.json` +
    `positions.db` and formats a message. Runs at the end of `run_pipeline.sh`.
- [ ] **Proper walk-forward train/test split** in `train_model.py` — right
  now training uses all history; `backtest.py` results are a logic sanity
  check, not a true out-of-sample estimate. Fix: train on data through date
  X, backtest only on dates after X.
- [ ] **Exit logic beyond stop-loss** — currently only stop-loss and
  horizon-timeout exits exist. Consider: exit early if score decays below
  a lower threshold (e.g. drops below 50) even if stop-loss hasn't hit.
- [ ] **Slippage/fee modeling** in `backtest.py` — currently assumes fills
  at exact close price with no cost, which overstates returns.

## Medium-term
- [ ] Feature importance report after each `train_model.py` run (which
  indicators are actually driving the score — useful sanity check before
  trusting the LLM's "reason" text).
- [ ] Data provider redundancy — yfinance has no SLA; consider a fallback
  source (or a paid provider) if data pulls start failing regularly.
- [ ] Position sizing beyond fixed $10 — e.g. scale by score confidence,
  once there's enough backtest history to justify it.
- [ ] Portfolio-level correlation check — avoid ending up with 10 positions
  that are all the same sector/highly correlated.

## Later / exploratory
- [ ] Sentiment/news feature — free headline sources (e.g. RSS feeds) fed
  through the local LLM as an additional feature input to XGBoost, not just
  the post-hoc "reason" text.
- [ ] Web dashboard (even a static one) as an alternative to Telegram for
  reviewing scorecards and position history.
