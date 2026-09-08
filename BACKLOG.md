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

- [ ] **Research how others solve this.** Before spending money, find out what
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

## Near-term
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
