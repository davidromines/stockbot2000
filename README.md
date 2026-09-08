# stockpicker2000 — v1 (real-first, will get better)

Mirrors the football-prediction system's shape: local server pulls data and
does the heavy compute (yfinance + XGBoost + local LLM), Claude only reads
the final scoresheet and handles the Robinhood side.

**This project is fully separate from `betbot9000`** — own folder, own
GitHub repo. See `GIT_WORKFLOW.md` for setup and commit conventions
(short version: every code change gets a commit + a README update).

## Pipeline

```
data_pull.py       → data/ohlcv_history.parquet   (2yrs daily OHLCV, S&P 500)
features.py        → data/features_latest.parquet (technical indicators, 20 features)
train_model.py      → models/xgb_uptrend.json      (run occasionally, NOT daily)
score.py            → data/raw_scores.json          (XGBoost probability per ticker)
llm_report.py        → data/scoresheet.json          (local LLM's plain-English scoresheet)
check_exits.py       → data/exits_needed.json        (open positions that hit their stop-loss)
backtest.py          → prints strategy performance summary (run manually, not in cron)
position_tracking.py  → data/positions.db             (SQLite: all entries/exits, for backtesting + review)
```

`run_pipeline.sh` chains data pull → features → score → LLM report → exit
check, in that order. Intended for cron, pre-market. Training and
backtesting are run manually/separately, not on the daily cron.

## One-time setup

```bash
cd ~/stockpicker2000
python3.12 -m venv venv   # NOT bare python3 — system python is 3.14
source venv/bin/activate
pip install -r requirements.txt

# 1. Pull ~2 years of history + build features
python data_pull.py
python features.py

# 2. Train the initial model (need enough history first — see note below)
python train_model.py

# 3. Initialize the position-tracking database
python position_tracking.py

# 4. Set up cron for the daily scan (edit crontab -e)
# 0 7 * * 1-5 /home/stockpicker/stockpicker2000/run_pipeline.sh >> logs/pipeline.log 2>&1
```

**Note on training data**: `train_model.py` needs enough history for the
5-day-forward labels to exist — i.e., don't train until `data_pull.py` has
pulled the full 730-day lookback at least once. Retrain periodically
(weekly/monthly) as more labeled history accumulates; don't retrain in the
daily pipeline.

## Local LLM

`llm_report.py` assumes Ollama running locally (`http://localhost:11434`)
with whatever model you've got loaded (default config: `llama3.1:8b`).
Edit `config.yaml` → `llm:` if you're running something else or an
OpenAI-compatible endpoint instead — `call_ollama()` in `llm_report.py` is
the only place that needs adjusting for a different backend.

**Important**: the LLM does NOT set the score. `score.py` (XGBoost) is the
source of truth for the number. The LLM only writes the one-line "reason"
column. This is deliberate — keeps the ranking machine-generated and
reproducible, and keeps the LLM from silently drifting the numbers.

## Scoresheet schema (the handoff to Claude)

```json
[
  {
    "ticker": "AAPL",
    "score": 82.4,
    "reason": "Price above both moving averages with rising MACD histogram and strong volume confirmation."
  }
]
```

## Risk management

- **Account cap: $100 total.** $10 x 10 positions spends exactly that. The cap is
  the point — total downside is bounded at $100 by design, not by luck.
- **Every order is human-approved**, entries and exits alike. The system proposes;
  a person authorizes.
- **Swing trading only** (days-weeks). Intraday is ruled out: pattern-day-trader
  rules require $25k equity.
- **Stops are not resting broker orders.** Robinhood dollar-amount orders are
  market-only and regular-hours-only, so `check_exits.py` evaluates stops once a day
  and the exit goes in as an approved market order. A gap through the stop
  overnight is not protected against.
- **Position sizing**: `$10` per position (dollar-based, fractional),
  configurable in `config.yaml` → `risk.position_size_usd`.
- **Max holdings**: 10 concurrent open positions, `risk.max_open_positions`.
- **Stop-loss**: ATR-based by default (`stop_loss.py`) — stop price =
  entry price − 2× the stock's own 14-day ATR at entry, so volatile stocks
  get proportionally more room than quiet ones. Switch to a flat
  percentage via `risk.stop_loss_type: fixed_pct` if you'd rather.
- **Position tracking**: every entry/exit is written to `data/positions.db`
  (SQLite, see `position_tracking.py`) — this is what makes backtesting and
  "how are we actually doing" reviews possible.

## Backtesting

```bash
python backtest.py --threshold 70
```

Simulates the score ≥ threshold → enter, stop-loss/horizon → exit strategy
over your pulled history and prints win rate, avg P&L, and stop-out rate.
**Caveat**: the model is currently trained on the same history it's
backtested against, so treat results as a check of the strategy *logic*,
not a genuine out-of-sample performance estimate — see `BACKLOG.md`.

## Handoff to Claude

Each day, two files matter for the handoff:

- `data/scoresheet.json` — new candidates to consider buying
- `data/exits_needed.json` — open positions that hit their stop-loss

Upload whichever is relevant into your chat with Claude. For entries,
Claude will:

1. Filter to `score >= 70`
2. Check each candidate's tradability + fractional-share eligibility on
   Robinhood, and current open-position count against the 10-position cap
3. Present the filtered, verified list for your approval
4. On approval, place `$10` market orders and log the entry (tell Claude
   the resulting fill price/position id so it can be recorded — position
   DB writes happen server-side, Claude doesn't have direct DB access)

For exits, Claude will confirm the stop-loss trigger against a live quote
and place the sell order on your approval.

Claude does not read the raw data, features, or model — only the two
handoff files. This keeps token usage low and keeps the interpretation
work on your local model, per the design goal.

## Known v1 rough edges (fix in the "make it good" pass)

See `BACKLOG.md` for the full list — top of mind: no strict train/test
time split yet (backtest isn't truly out-of-sample), no fee/slippage
modeling in the backtest, and yfinance is unofficial/free with no SLA.
