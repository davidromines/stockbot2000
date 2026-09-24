# stockbot2000 — v1 (real-first, will get better)

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

Outside the daily cycle, feeding the historical store:

```
universe.py --record → symbols table + data/symbol_snapshots/  (who was listed, when)
backfill.py          → data/market_data.db                     (20yr OHLCV, resumable)
storage.py           → owns that database's schema and writes
```

**`daily.sh` is the real daily job** and has been on cron at 07:00 UTC on
weekdays since 2026-09-12. Each stage is independently runnable and
idempotent; a failing stage does not abort the ones after it.

```
[1/10]  Symbol directory      who is listed today — a missed day loses that
                              day's delistings PERMANENTLY, so it runs first
[2/10]  Price top-up          backfill.py --top-up
[3/10]  Features              the 20 indicators
[3b/10] Fundamental projection daily_fundamentals
[3c/10] Market-cap fallback  market_caps.py --backfill: Robinhood caps for
                              liquid names the filings miss (dated, sourced)
[4/10]  Freshness gate        fails the run if any derived table is behind
[5/10]  Paper trading         advance the simulated funds one day
[6/10]  Daily book            best candidate from every system + sell signals
[7/10]  Pair funds            mark the bull/bear switching funds
[8/10]  Fund report           one status line per fund
[9/10]  Research integrity
[9b/10] Accounting            authoritative gross / costs / net per fund
[9c-9h] Strategy Factory      library sync, templates, discovery plan,
                              pipeline (budget 12, ~20 min, ~4.3 GB),
                              league standings, data/factory_report.txt
[9i/10] Slot reassessment     slots.py --apply (SIMULATION): the five slots
[10/10] Backup
```

**The trading engine runs separately** (Addendum A): `./services.sh --install`
adds one cron line that runs `slot_trader.py --auto` every 5 minutes during
US market hours — the entry pass once per session, the stop monitor after —
in SIMULATION. LIVE is refused until `config/risk.yaml` says
`execution_mode: LIVE`, which is the account owner's step. `slots.py
--leaderboard` shows every forward strategy ranked on net P&L and why each is
or is not eligible for a slot.

**Survivorship stress data** (Addendum C) lives in `data/universe/`, never in
`prices`: `universe_layer_a.py --build`, `universe_cohorts.py --build`,
`universe_synthetic.py --build`, `universe_validate.py --run`; backtests read
it through `universe_loader.load_backtest_data(conn, start, end, mode)`.

On success the order slate and fund report go to Telegram; on failure an ALERT
goes instead, naming the symbol-directory step specifically.

`run_pipeline.sh` is the older single-run chain and is superseded by `daily.sh`.
Training and backtesting are still run manually, not on cron.

## Historical data store

`data/market_data.db` (~8.5 GB) holds **35.4M daily bars across 13,121
instruments back to 1962**, plus 33.8M feature rows, the SEC fundamentals, the
delisting registry, the Lab's genomes and every forward record. The daily
pipeline reads it directly — the old Parquet path is gone.

**Freshness has a trap in it.** The top-up used to ask "which tickers are behind
`MAX(date)` in `prices`" — the same table it exists to advance — which is
circular and left the whole universe a session behind every day while reporting
success. It now asks the data source directly for the last *completed* session.
See CLAUDE.md before changing anything about staleness.

```bash
python universe.py --record          # refresh the symbol registry + snapshots
python backfill.py --limit 20        # prove the loop on 20 tickers first
nohup python backfill.py &           # full run — hours, survives SSH drops
python backfill.py --status          # progress, any time
python backfill.py --retry-failed    # another pass at failures
```

**The backfill is resumable.** Kill it and re-run: `ingest_state` tracks progress
per ticker and commits once per batch, so an interruption loses at most one batch.
Never start it over from scratch — just run it again.

Universe source is `config.yaml` -> `universe.source`:

| Source | Tickers | Use |
|---|---|---|
| `sp500` | 18 (Wikipedia 403s, falls back) | smoke test |
| `all_us` | ~6,172 from the NASDAQ Trader directory | production backfill |
| `custom` | whatever's in your file | ad hoc |

### Two databases, on purpose

- `data/market_data.db` — market history. Large, regenerable, rebuilt by re-running
  the backfill. Owned by `storage.py`, which is the only module that writes SQL to it.
- `data/positions.db` — the trade ledger. Small, irreplaceable, owned by
  `position_tracking.py`. This is the record of what the system actually did.

### A limitation worth knowing

yfinance does not serve delisted companies, so this data covers only firms still
listed today. Every bankruptcy and acquisition of the last 20 years is missing,
which makes any backtest run against it look better than reality. This is a known,
accepted trade-off — not something the code can correct for. `universe.py --record`
snapshots the symbol directory daily so that *going forward* we can tell when a
ticker leaves the listings, but the missing history stays missing until a
point-in-time data source is bought.

## One-time setup

```bash
cd ~/stockbot2000
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
# 0 7 * * 1-5 /home/stockpicker/stockbot2000/run_pipeline.sh >> logs/pipeline.log 2>&1
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

## The funds

`fund_report.py` rebuilds this every morning and sends it to Telegram.

| | What |
|---|---|
| **Agentic account** | The only real money. ~$89, five positions, traded by the daily book with a human placing the orders. |
| **16 paper funds** | Simulated, stepped daily. Named for what they trade — `MACD Pullback`, `Rising 200 · Stop 3.3`, `Crash Buyer 5d`. |
| **5 pair funds** | Bull/bear ETF switching (S&P 1x/2x, Nasdaq, Russell, Energy), $100 each, opened 2026-09-15. |
| **Claude Fund** | Discretionary, unfunded, paper-tracked. Currently holds nothing. |

Three other Robinhood accounts are reported for completeness and are **not
touched by this system**.

**No figure here is a forecast.** The honest state of the evidence: the
classifier is gross negative under next-open fills, ETF switching loses to
buy-and-hold on every index pair, and every one of the five crash-buying paper
funds is negative. The one live lead is that the same momentum rule is positive
with tight stops and negative with wide ones, on eleven days of forward data.
See CLAUDE.md for the full record, including six searches that produced six
measurement artifacts.
