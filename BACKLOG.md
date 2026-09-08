# Backlog

Ordered roughly by what unblocks the most value next — not a strict
commitment, just a working priority list.

## Near-term
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
