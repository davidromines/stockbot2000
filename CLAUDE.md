# Stockbot2000

Automated swing-trading system: scores US equities on technical indicators, sizes and
stops positions by ATR, and evolves its own trading strategies against 20 years of
market history before any real capital is committed.

> **Product definition — Addendum A, 2026-09-24** (`docs/ADDENDUM_A_AUTONOMOUS_5_SLOT.md`). Stockbot2000 is an
> autonomous trading system that continuously discovers, tests, ranks and
> paper-trades strategies, automatically selects the five best currently
> eligible ones, allocates ~$20 to each of five slots, and executes and manages
> their trades through Robinhood — replacing weaker strategies with stronger
> ones automatically. The objective is positive trading P&L, not beating SPY.
> Where anything below conflicts with this, the addendum wins. **Approved and
> authorized for construction by Addendum B, 2026-09-24**
> (`docs/ADDENDUM_B_FINAL_BUILD_DIRECTIVE.md`). The affected rules are flagged
> in "Trading mandate"; real-money activation remains the user's step (B14).

Renamed several times: `betbot9000` -> `trend-scanner` -> `stockpicker2000` ->
**`stockbot2000`** (current, as of 2026-09-08). Older commits, the VM hostname
and the Linux user still say `stockpicker` — that is expected, not a leftover to
clean up. Do not confuse this with the separate `betbot` project (college football
betting), which is a different system entirely.

---

## Current state — READ THIS FIRST

### LIVE TRADING IS ON — since 2026-09-24 15:39 UTC (read this first)

The owner armed LIVE (`config/risk.yaml` `execution_mode: LIVE`). The slot
trader places REAL orders in the Robinhood Agentic account **403446024**
(type `limited_margin`) every 5 minutes, 13:00-20:59 UTC weekdays, via cron
(`slot_trader.py --auto --mode LIVE`, log `logs/slot_trader_live.log`).

First live run (15:39-15:40 UTC): BUY SNDK $20 (0.011318 @ 1767.07), DELL $20
(0.03759 @ 532.05), MRNA $20 (0.107927 @ 185.31), TWST $8.45 (0.048951 @
172.62 — the settled cash left). Slot 5 (MACD Pullback) refused every pick:
GEN and NWSA unknown market cap, then no settled cash ($19.26 of the owner's
manual ACT sale settles 2026-09-25). Account before: $87.71.

How it is wired, in one breath: ranking.py scores every strategy (owner's
process, 2026-09-24: backtest -> rank -> paper -> move continuously; score =
expected net return per trade, starting at the backtest and shifting to the
paper record with each trade; a losing backtest is out) -> slots.py fills the
five slots with the top five TRADEABLE strategies on day one (no evidence
floor, no lifecycle state; up to 4 per family) -> slot_trader.py -> ExecutionEngine -> kill switches -> RiskEngine
(account rules: PDT limit AND settled funds for limited_margin) ->
robinhood_live.LiveBroker (review -> place -> confirm, ref_id idempotency)
-> robinhood_mcp.py (MCP 2.x client, agent.robinhood.com/mcp/trading, OAuth
token at ~/.config/stockbot2000/robinhood_oauth.json, mode 600).

**Controls the owner has:**
- Stop everything and flatten slot positions: `touch data/KILL_SWITCH`
  (delete it to resume). Stop new trades but keep positions:
  `execution_mode: SIMULATION`.
- Sign-in expired -> trading halts and alerts; fix: `./venv/bin/python
  robinhood_mcp.py --login` (owner, desktop browser + Robinhood app).
- Every live fill and every halt sends a Telegram/desktop alert.

**What is NOT true, so no one overclaims:** no strategy has demonstrated an
edge. Four of five slots are Rising 200 stop variants — one entry rule, which
the 14-year sweep found loses net — on 9 sessions of forward evidence. The
acceptance checklist (`acceptance.py`) was 25/26 at arming: the SHADOW record
had 1 of 10 sessions. The owner armed anyway; that is their call and is
recorded here, not relitigated.

**Permission mode:** LIVE wiring was blocked under Claude Code auto mode; the
owner switched the session to manual approval to finish it. Expect the same
in a new session for anything touching orders.

### SESSION HANDOFF — 2026-09-24 (start here in a new session)

**What the user wants now:** build Phase 13 (Strategy Factory, research engine)
then Addendum A (autonomous 5-slot trading engine), as ordered by Addendum B
(`docs/ADDENDUM_B_FINAL_BUILD_DIRECTIVE.md`, "BUILD NOW", don't stop to ask
between steps). Delegate what is reasonable to DeepSeek via ADO to save Claude
tokens. The user dislikes: deviating from the written plan's order,
re-litigating automation caveats, stale trackers, and results reported without
gross / costs / net side by side.

**Build status — Phase 13 (Stage H in `docs/ROADMAP_INTEGRATION.md`)**

| step | state | where |
|---|---|---|
| H1 audit | done | `docs/PHASE13_ARCHITECTURE_MAP.md` |
| H2 accounting | done | `accounting.py` (liquidation basis, `fund_accounting` table, reconciliation); paper-engine fixes in `paper_trading.py` |
| H3 object model + lifecycle + factory | done | §14 states added to `league.py`; `strategy_objects.py`; `strategy_factory.py` (40 families, 229 objects) |
| H4 research library | done | `library_bridge.py`, `research_queue.py` (27 of 40 entries -> 244 linked objects) |
| H5 fundamental factory | done | fundamental families in `strategy_factory.py`; `storage.attach_fundamentals()` |
| H6 FINSABER / providers | done; **all three files downloaded 2026-09-24** (user yes) | CSV -> `data/finsaber.db` `finsaber_prices` (4.74M bars, 1,017 symbols); pickles via `finsaber_pkl.py` (streaming, restricted) -> `finsaber_pkl_prices` / `finsaber_news` / `finsaber_filings`. The S&P pickle is **27.3 GB**, not the README's 11 GB |
| H7 cross-dataset validation | done, run 2000-2024 | `dataset_compare.py` — compares **daily returns** (99.5-99.8% agree within 0.5pp per year; 2000 is 98.0%). Price LEVELS differ by a per-ticker adjustment anchor and are not a data error |
| H8 leagues | done | `leagues.py`, `leagues:` + `league_families:` in config |
| H9 discovery | done | `discovery.py` (priority, budgets, failure_log, recycling) |
| H10 robustness | done | `robustness.py` |
| H11-H13 pipeline | done | `factory_pipeline.py`; first run: 2 value+quality strategies reached PAPER, 2 momentum+volume rejected out of sample |
| H14 report + scoreboard | done (TASK-021 merged 2026-09-24) | `factory_report.py` — forward rows never fall back to backtest metrics |
| H15 end-to-end test | done | `tests/e2e/e2e_factory.py` — real data in a temp DB, never production; run under `run_bounded.sh`. Found 5 defects, all fixed |
| daily.sh wiring | done (`[9c]-[9h]`) | pipeline budget 12: ~20 min, 4.3 GB peak |
| unit tests for H3-H13 | done (TASK-022..026, DeepSeek) | strategy_objects, discovery, leagues, robustness, factory_pipeline; gate is 50 files, all passing |

**Addendum A (Stage I): I1-I14 BUILT 2026-09-24 in SIMULATION and SHADOW.**
All five slots are CASH today: 0 of 33 forward strategies are eligible (every
one is short of the 20-session / 10-trade floor). LIVE is refused everywhere
until `config/risk.yaml` `execution_mode: LIVE` — the user's step (B14) — and
even then `RobinhoodBroker.place_order` only builds the spec; transmission is
an operator step. Modules: `slots.py`, `stop_plans.py`, `slot_trader.py`,
`quotes.py`, `account_rules.py`, `intraday.py`, `services.sh`, plus additions
to `killswitch.py`, `broker.py`, `execution.py`, `risk_engine.py`. The trader
runs from cron every 5 min, 13:00-20:59 UTC weekdays (`./services.sh`).

**Defects found and fixed while building it — worth knowing:**
- Approved exits carried NO size (risk_engine returned before sizing), so
  every simulated sell filled 0 shares. Exits now size from the held quantity.
- Order ids and daily throttles were shared across modes: a SHADOW run of a
  SIMULATION decision was suppressed as a duplicate, and SIMULATION orders
  used up the SHADOW/LIVE order cap. Now per mode.
- `paper_runs.label/family/last_review` were created by hand in production
  and by no code; `fund_accounting` only by the daily stage. A fresh database
  broke enrolment. Both now created in `init`.

**Addendum C (Stage J): Stages 1-5 BUILT 2026-09-24 on the RECOMMENDED answers**
to the eight questions (the user said build every roadmap item; each answer
is a config value under `universe_reconstruction:` — change them there).
`universe_layer_a.py` (Layer A, 1996-2024), `universe_cohorts.py`,
`universe_synthetic.py` (v3), `universe_loader.py` (five modes),
`universe_validate.py`. Store: `data/universe/` only, never `prices`.
**The generator FAILS the discriminability gate (AUC 0.768, merger-only
0.737, vs < 0.60; v1 0.987)**. Synthetic rows were for retests and stress
bounds only — **until the owner's ruling of 2026-09-24: the ranking now scores
on backtests WITH them** (`survivorship_backtest.py`, next step 9). Sensitivity, 12-1 momentum 2009-2024: 23.3% CAGR on our data,
18.9% with synthetic dead companies, 13.2% if every unpriced death was a total
loss. Synthetic share of the priced universe peaks at 52% (2016).

**Ticker reuse trap (fixed in Layer A):** matching a dead company by ticker
attaches it to whoever holds the ticker TODAY and credits it with the
successor's prices. 426 of 676 "real dead" companies were impostors. Any
ticker match must agree with the company's own dates; a record owns a
ticker's prices only if they end near its own end. Real dead sample: 158. Synthetic deaths
concentrate after 2008 because listing evidence starts there; the 1996-2007
hole is mostly EDGAR-only filers, excluded by default.

**FINSABER had 99 symbols alternating between two price levels** (CBE:
$170 / $0.005). Flagged in `finsaber_quality`, excluded by the provider and
loader. It had added 15 points a year to a momentum backtest.

**Waiting on the user**

1. ~~Account type~~ — Robinhood reports **limited_margin** (not cash); both the
   PDT limit and the settled-funds rule are enforced.
2. ~~FINSABER~~ — all imported; filings are NOT point-in-time (use
   sec_filings.first_tradeable); headlines unverified.
3. ~~Addendum C answers~~ — built on the recommended answers; change any in
   `config.yaml` `universe_reconstruction:` and rebuild.
4. ~~FinanceDatabase~~ — **owner said yes 2026-09-24; loader built, NOT YET
   FETCHED** (this cloud session cannot reach it). On the VM:
   `./venv/bin/python finance_database.py --fetch --import`, then rebuild
   Layer A (`universe_layer_a.py --build`). Rows attach only on ticker AND
   name; sector stays in `fd_sector`, never merged into SIC divisions.

**Also done 2026-09-24 (late session)**

- `backup.py` now covers 38 tables, up from 18. The League and Phase 13 decision
  logs (`league_state`, `strategy_decisions`, `fund_accounting`,
  `experiment_registry`, ...) and the value/crypto funds had been **outside
  the backup since 09-22**. If you add an append-only table, add it to
  `backup.GROUPS["forward"]`.
- Roadmap page republished (version 13): Phase 13 at 14 of 15, decisions
  resolved. Source `docs/artifacts/roadmap_page.html`.
- The 09-23 daily run ended "WITH FAILURES": freshness gate, SPY/QQQ/IWM
  missing the newest bar. That was the partial-bar incident, already fixed.
- **The user is on Pacific time.** Cron 07:00 UTC is midnight PDT (11 PM PST
  in winter); the market opens 06:30 PT. The user asked about 05:30 PT; the
  advice was to keep 07:00 UTC because a run now takes ~65 min and closes are
  final either way. Offered 10:00 UTC (03:00 PDT) if they want it later.
- `finsaber_pkl.py` import of the 27.3 GB S&P pickle: **run after the daily
  job finishes** — `./run_bounded.sh ./venv/bin/python finsaber_pkl.py
  --import data/finsaber/stock_data_sp500_2000_2024_v2.pkl`. Resumable.

**Next steps, in order (next session)**

1. **Watch the live account first.** `tail -50 logs/slot_trader_live.log`;
   `./venv/bin/python slot_trader.py --status --mode LIVE`; check the alerts.
   Verify slot 5 fills on 2026-09-25 once the $19.26 settles, and that stop
   exits SELL only the slot's shares.
2. ~~**Market-cap gaps block real picks**~~ — **done 2026-09-24**
   (`market_caps.py`). The filing cap still wins; else a Robinhood (LIVE
   quotes, daily `[3c]` backfill) or yfinance cap no older than 7 days, stored
   dated and sourced in `market_cap_quotes`. Still unknown -> still rejected.
   GEN $14.5B and NWSA $15.9B per Robinhood. ETFs quote AUM and meet the same
   $100M floor. **Deploy: `git pull` on the VM**; the first `[3c]` run fills
   the gap, and a LIVE quote fetches any miss on its own.
3. ~~**Diversity: ETF switch funds in slots**~~ — **done 2026-09-24.** A
   `pair:` holder's slot buys `pair_funds.next_leg()` (the fund's own replay,
   min_hold included; refuses if a leg lacks the newest bar), sells the old leg
   when the fund switches, and carries a stop the fund's record does NOT have:
   entry - 3 x ATR (`slots.pair_risk`). Families split by index (owner,
   2026-09-24): `pair_sp500` (1x and 2x together), `pair_nasdaq`,
   `pair_russell`, `pair_energy`. On a switch in LIVE the new leg waits for the
   sale to settle (limited_margin, T+1); ERY's AUM ($42.6M) is under the $100M
   floor, so Energy's bear leg is refused. Whether a pair fund takes a slot is
   the ranking's call (ranking.py), like every other strategy.
   **Value Fund in slots (owner's option C, 2026-09-24):** a `value:` holder's
   slot buys the fund's highest `score_at_entry` current holding
   (`value_fund.ranked_holdings`; the next one if another slot has it), $20,
   with a 3 x ATR stop the fund itself does not use (`slots.value_risk`), and
   sells when the fund drops the stock at a review. Ranked on the fund's
   paper record sized at capital / holdings.
4. ~~Robinhood sessions~~ — **done 2026-09-24.** `robinhood_mcp.session()`
   keeps ONE MCP session open for a whole LIVE slot_trader run (background
   thread); every `rh.call`/`rh.calls` inside uses it. A session that dies or a
   call stuck > 120 s falls back to per-call sessions for the rest of the run;
   errors reach callers unchanged (an order failing in transport is still
   UNKNOWN). The log line `robinhood: N call(s) in one session` shows it working.
5. Addendum C: **generator v4 written 2026-09-24, NOT YET BUILT OR SCORED.**
   v3 failed the gate (AUC 0.768) on final-year shape: real skew 1.17 vs 0.20,
   kurtosis 16.5 vs 4.2, drawdown -22% vs -34%, last-60 +2.5% vs -2.6% — the
   acquisition shape (jump, then quiet). v4 gives clean exits a real donor's
   whole final year on their own market dates; failures keep v3 (no real
   failing year exists to copy, so the gate cannot judge them — expect the
   all-reasons AUC to stay above the merger-only one). On the VM:
   `./run_bounded.sh ./venv/bin/python universe_synthetic.py --build` then
   `universe_validate.py --run` (writes `validation_v4.json`). The loader uses
   v4 once it exists.
6. **Crypto earns a slot — Stage K, PLANNED 2026-09-24** (`docs/ROADMAP_INTEGRATION.md`).
   Robinhood's crypto spread measured ~1.9% round trip (BTC/ETH/SOL/XRP/LINK,
   one after-hours snapshot) against the 1.2% the backtests assume, so
   grid-DCA (+2% take-profit) cannot pass. Order: K1 Robinhood cost model ->
   K2 daily history to ~2016 -> K3 low-turnover strategies (trend, BTC/cash)
   -> K4 crypto backtest into ranking.py (a losing one is OUT; today it is
   ranked from a neutral 0) -> K5 crypto orders in slot_trader -> K6 hourly
   24/7 crypto cron -> K7 owner sets `allow_crypto: true`. The Agentic account
   has a linked crypto account.
7. **Profit exits (owner, 2026-09-24: "when will profits be taken?").**
   Until now live slots sold only on the ATR stop, the time limit or the
   strategy's exit rule. **Fixed:** `stop_plans.from_genome` had dropped
   `risk.take_profit_pct`, which the backtest and paper engine both apply, so
   live traded a different strategy than was tested; now carried (checked
   after the stop), and positions bought earlier get it from their strategy
   version. **Built, NOT YET RUN:** `exit_sweep.py` (experiment `exit_rules`):
   take-profit none/5/10/20% x trailing stop none/2/3 ATR on each slot
   strategy, 2006-2019. Adoptable only if it beats the strategy as it is over
   the window AND in most two-year blocks. On the VM:
   `./run_bounded.sh ./venv/bin/python exit_sweep.py --run`. An adoptable
   cell becomes a new strategy version; the ranking re-scores it.
8. **Published signals — Stage L, PLANNED 2026-09-24** (`docs/ROADMAP_INTEGRATION.md`).
   The owner asked for a big strategy database like trader.dev's 797k; that
   is a backtest leaderboard, so not used. Instead: Open Source Asset Pricing
   (212 published predictors, decile returns on CRSP — **dead companies
   included**, the only survivorship-free long history available here) plus
   Global Factor Data (93 countries) as a cross-check. L1 import (VM; both
   sites blocked from the cloud session) -> L2 library entries, post-
   publication evidence only -> L3 rebuild the price/SEC-computable signals
   as factory templates -> L4 owner decides whether the published return
   becomes the ranking prior. Adopt only at t > 3.
9. **Backtests include the dead companies — BUILT 2026-09-24, NOT YET RUN**
   (owner: "use the synthetic data, why are you not using the systems we
   built?"). Until now the synthetic paths had no indicators and no consumer
   but a report, and `ranking.py` — which fills the live slots — had NO
   survivorship correction at all (the drawdown gate lived only on the retired
   promotion ladder). `survivorship_backtest.py` runs every ranked strategy on
   the factory window in exclude / as_is / zero; ranking scores and gates on
   **as_is**, shows **zero** as the worst case, and applies the drawdown
   exposure gate (`survivorship.max_drawdown_exposure`). Assumptions: synthetic
   volume unknown (liquidity at the floor, volume indicators NaN), no
   fundamentals, generator fails its realism gate. Nightly `daily.sh [9f2]`;
   first run on the VM: `./run_bounded.sh ./venv/bin/python
   survivorship_backtest.py --run`, then `ranking.py` to see who drops out.
10. **Realistic dead companies — Stage M, PLANNED 2026-09-24.** The donors
   are nearly all buyouts; failures have no real final year to copy. M1 build
   + score v4 -> M2 real failure paths (bankruptcy `ticker+Q` OTC series via
   yfinance for 8-K 1.03 companies; FINSABER pickle; label our own delisted
   names by 8-K item) -> M3 v5 copies real failure final years -> M4 realism
   gate per exit type -> M5 paid delisted data (owner's call).

**Findings from this session that change numbers elsewhere**

- **Restated P&L (accounting v1):** 23 simulated funds net **-$49.59** (gross
  -$41.19, costs -$8.40), not the -$4.52 the engines' own curves implied. The
  paper engine had marked positions with no bar at ENTRY price and, in 11
  funds, let a repeated step overwrite held positions (cash drift). Both fixed;
  originals kept, restatements alongside. The user-supplied figures are kept as
  `reports/pnl_snapshot_2026-09-24_supplied.json`, marked superseded.
- **Stop-width lead refuted** (experiment `stop_width`, COMPLETE): rising_200
  loses net in all 30 stop x hold cells, 2006-2019; tight stops did no better.
  Rising 200 funds are classified PROMISING / INSUFFICIENT EVIDENCE (§19).
- **Signal decay** (`signal_decay.py`): within a date, the classifier's top
  decile does not beat the bottom at any horizon; the pooled spread is timing
  across dates, not stock selection.
- **Fundamentals were on two scales**: `value_metrics.py` mixed a 10-Q's
  quarterly flow with a 10-K's annual flow, so ROA / earnings yield jumped ~4x
  after every 10-K. Now annualised; `fundamentals` and `daily_fundamentals`
  rebuilt 2026-09-24. Conviction screens used the broken scale before that.
- **Partial bars**: an intraday top-up stored 41 in-progress bars;
  `backfill.completed_bars()` now drops anything dated today (New York time),
  and the freshness gate fails on data newer than the market.
- Phase 07 (costs, next-open fills, gap-through-stop) closed and re-measured:
  classifier gross -$82.54 under next-open fills.

**Governance rulings from the user (2026-09-24)** — all six Phase 13 defaults
confirmed. Load-bearing: counter-evidence is attached as a first-class
artifact (hash + timestamp + path), never a footnote — the stop_width sweep is
attached that way to the six rising_200 decisions; restatements live beside
originals with `accounting_version`, never over them; templates are a
separate governed path and `tests/regression/test_freeze_boundary.py` fails
if factory output can reach evolve.py; H13 connects to the execution layer,
never extends it.

**Gotchas that cost time this session**

- **`run_bounded.sh` fails under cron** — `systemd-run --user` needs a user
  bus and Linger=no. `daily.sh` has a `bounded` helper that falls back to a
  plain run there. **Do not edit `daily.sh` near 07:00 UTC**: bash reads the
  script as it runs.

- **Run heavy jobs with `./run_bounded.sh`** (6 GB cap, own systemd scope).
  An OOM inside Claude's scope killed the desktop app three times.
- **ADO `implement` checks out the task branch in this working tree.** Commit
  or stash before, `git checkout main` after. `./ado_ship.sh TASK-nnn` runs
  review -> approve -> merge with the gate each time (under the memory cap).
- **Never `git commit -a`** — it sweeps in daily-run outputs
  (`backups/forward.sql.gz`, `reports/*`, `data/*.txt`). Add paths explicitly.
- **DeepSeek output cap is 8,000 tokens**: ask for files under ~300 lines or
  split the task, or the response truncates and nothing is written.
- `league.versions()` and most league helpers need `conn.row_factory =
  sqlite3.Row`.
- Task specs: requirement items must be single lines (the task parser keeps
  only the first line of a numbered item).

**Commands**

```bash
./run_bounded.sh ./venv/bin/python accounting.py --report
./run_bounded.sh ./venv/bin/python leagues.py --standings
./run_bounded.sh ./venv/bin/python factory_pipeline.py --run --budget 4
./venv/bin/python discovery.py --status
./venv/bin/python strategy_factory.py --list
./venv/bin/python orchestrator.py status
./ado_ship.sh TASK-021
./run_tests.sh
```

**The market database is built and complete** (2026-09-08): 35.4M price bars across
13,121 instruments back to 1962, plus 33.8M feature rows. Details under Storage
model. Phases 01-05 are done; phase 06 is at 90%.

**The Parquet migration is DONE — this section said otherwise until
2026-09-22.** `daily.sh` runs entirely off `market_data.db`: `backfill.py
--top-up`, `build_features.py`, `fundamental_features.py`, and every consumer
downstream. 35,557,344 price bars across 13,214 tickers, current to 2026-09-21.
`features.py` and `data_pull.py` still contain Parquet code but **neither is in
the daily path**.

That stale line sat at the top of this file for two weeks naming a finished job
as the single most important gap, which is worse than saying nothing: a reader
starting here concluded the project's stated priority was being skipped. **If
you finish something named in this section, edit this section in the same
commit.**

**The real current gap** is that none of it has produced an edge. Phases 6-9
built the machinery to measure honestly; every measurement so far says the same
thing. See "The Strategy League" and "The Research Library" below.

**Data freshness: `daily.sh` runs at 07:00 on weekdays via cron** (installed
2026-09-12). It records the symbol directory, tops up prices, rebuilds features
and steps paper trading. Check `logs/daily.log` before trusting any score.

**Step 1 is the survivorship-critical one.** Recording the listing directory is
what stamps a ticker inactive on the day it disappears. The backwards bias
cannot be fixed — 5 tickers stopped trading in the whole 2006-2019 window
against 9,029 the Internet Archive says existed — but from 2026-09-12 forward
the record is point-in-time, and **a missed day loses that day's delistings
permanently.** If the VM is down for a week, that week is gone.

**`backfill.py` needs `--top-up` for daily use.** Plain `backfill.py` resumes an
*interrupted initial load*; it does not fetch new bars for tickers already
marked `done`, which after the historical load is all of them. That made a daily
re-run a silent no-op: on 2026-09-12 the database held bars to 2026-09-04 for
12,750 tickers and a full pipeline run advanced 28. Earlier wording here called
the loader "incremental", which was true of resumability and false of top-up.

---

### Smoke test — passed 2026-09-08

**The smoke test passed on 2026-09-08.** Every stage ran end to end on the
18-ticker fallback universe, on Python 3.12 with no code changes required.

| Stage | Result |
|---|---|
| `universe.py` | 18 tickers (Wikipedia 403 -> fallback, as expected) |
| `data_pull.py` | 13,140 rows / 18 tickers -> `ohlcv_history.parquet` |
| `features.py` | 20 indicators for 18 tickers -> `features_latest.parquet` |
| `train_model.py` | 9,558 labeled rows, 21.9% positive, test AUC 0.764 |
| `score.py` | 18 scored; top score 41.7 (TSLA) |
| `position_tracking.py` | ledger initialized |
| `check_exits.py` | ran clean (no open positions) |
| `backtest.py` | ran; **result is invalid, see below** |
| `llm_report.py` | ran in fallback mode — Ollama is not installed on this VM |

### Walk-forward result — 2026-09-11

**The edge is stable.** 31 rolling retrains, 2011-2026, each trained on the prior
5 years and predicting the next 6 months. 7,597,510 out-of-sample predictions.

| | |
|---|---|
| AUC mean / min / max | 0.629 / 0.582 / 0.670 |
| Folds above 0.5 | **31 of 31** |
| Pooled AUC | 0.633 |
| Top-decile hit rate | **37.8%** vs 24.5% base (1.54x lift) |

This is the first evidence in the project that the signal persists rather than
being an artifact of where the data was cut. Run it with `walk_forward.py --run`;
it is resumable by fold, and `--report` prints the table.

Mild decay: folds before 2019 average 0.642, folds from 2020 average 0.611.
Consistent with alpha decay or regime change — still positive throughout.

**What this does not establish.** The measurement sits on survivorship-biased
data, so part of the lift may be survivors recovering rather than skill. AUC 0.63
is real but weak. **The 0.43% per-trade return quoted here was an artifact of
close fills and a 10-position config, and is superseded** — under next-bar fills
the same model is gross NEGATIVE. See "Fills happen on the NEXT bar" below. A
stable ranking is not the same as a profitable strategy, and this is the case
that proves it.

### Do not trust the backtest number

`backtest.py --threshold 70` reports a **97.9% win rate over 47 trades**. This is
not a result, it is look-ahead leakage. `train_model.py` splits with
`train_test_split(..., stratify=y)` — a *random shuffled* split over time-ordered
rows — so the model is trained on the same history the backtest then evaluates,
including days after each simulated trade. Any figure from `backtest.py` is
meaningless until the walk-forward split in `BACKLOG.md` is implemented. Do not
quote this number, tune against it, or treat it as even an optimistic upper bound.

### What the smoke test did *not* exercise

- **No entry path.** Top score was 41.7 against a threshold of 70, so zero
  candidates qualified and no order was ever proposed. The buy flow is still
  unproven end to end.
- **No exit path.** The ledger is empty, so `check_exits.py` short-circuited.
- **No real LLM report.** Ollama is absent; reasons are generic placeholder text.

~~Immediate next steps (as of 2026-09-11)~~ — **all but one are done; kept
only to show what was superseded.**

| was | now |
|---|---|
| 1. Repoint the pipeline off Parquet | **done** — `daily.sh` is all SQLite |
| 2. Fix the leaking train/test split | **done** — `walk_forward.py`, 31 folds |
| 3. Top up prices | **done, and automated** — cron at 07:00 weekdays |
| 4. Survivorship-bias research | **done** — measured per date, `pit_universe.py` |
| 5. Install Ollama | still open, still optional |

The work is now tracked in `docs/ROADMAP_INTEGRATION.md`, which carries a status
table per stage. **That file is the roadmap; this list is history.**

---

## Environment gotchas — these have already cost time

- **Python 3.14 is too new for parts of this stack.** `pandas_ta` pins
  `numba==0.61.2`, which refuses to build on 3.14. `pandas_ta` has been **removed
  entirely**; all indicators are hand-rolled in plain pandas/numpy inside
  `features.py`. Do not reintroduce `pandas_ta`. **This VM also ships Python 3.14
  as the system Python** (Ubuntu 26.04) — 3.12 is installed alongside it from the
  deadsnakes PPA. Always build the venv with `python3.12`, never bare `python3`.
- **`requirements.txt` had `pandas-ta` still pinned** long after the code stopped
  importing it. Removed 2026-09-08. `pyyaml`, `yfinance` and `pyarrow` — previously
  flagged as missing — are all present and pinned. Requirements installed
  cleanly end to end on Python 3.12 on 2026-09-08. Versions are floors only
  (`>=`), so the working set — pandas 3.0.5, numpy 2.5.3, xgboost 3.4.1 — is not
  recorded anywhere; see `BACKLOG.md`.
- **Indicator count is 20, not 25.** `FEATURE_COLS` in `train_model.py` lists 20,
  and all 20 are verified present in `features.py` output. `README.md` and
  `docs/STRATEGY_LAB.md` both say "~25" in places — the genome's `indicator_weights`
  space is sized off that wrong number and should be built against 20.
- **Wikipedia S&P 500 scrape returns HTTP 403.** Still true, and `universe.source:
  sp500` still falls back to 18 hardcoded tickers — that is the smoke-test path and
  is left alone deliberately. Production uses `universe.source: all_us`, built from
  the NASDAQ Trader symbol directory, which does not scrape and does not 403.
- **yfinance returns negative prices for some tickers.** `auto_adjust=True`
  back-adjusts for splits and dividends; where the cumulative adjustment exceeds
  the original price the result goes negative, which also inverts high/low.
  Found on 8 tickers during the 20-year pull, and the guard has run over the full 13,121-instrument load since. `storage.is_valid_ohlcv()` now rejects these at
  write time — do not remove that guard, and do not "fix" impossible bars by
  taking absolute values. The adjusted series for those tickers is simply wrong.
- **yfinance produces impossible prices for serial reverse-splitters.** TOPS
  carries a maximum adjusted close of **$549 trillion per share**; 425,964 rows
  across 333 tickers sit above $10,000. These passed every filter — `min_price`
  is a floor, and `dollar_volume_20` is close x volume, so inflated tickers looked
  maximally *liquid*. `storage.flag_price_anomalies()` marks them via
  `symbols.data_quality` (120 tickers) and every type-scoped query excludes them.
  The rule is absolute price **and** range, never range alone: Berkshire A really
  trades near $800k and Monster Beverage really is up 15,352x.
- **yfinance does not serve delisted tickers.** This is a real correctness problem
  for backtesting — see the survivorship-bias item under Open Decisions.
- Long backfills must be run under `nohup`/`tmux`/`screen`. SSH sessions to this
  box have dropped mid-run before.
- **Start every heavy job from a Claude session with `./run_bounded.sh`.** A job
  launched from Claude — even under `setsid nohup` — stays inside the Claude
  desktop app's systemd scope, and when the kernel OOM-kills it, systemd stops
  the whole scope, **desktop included**. That crashed Claude three times on
  2026-09-23, each from one ~9.5 GB Python job. `run_bounded.sh` gives the job
  its own scope capped at `compute.max_memory_gb` (6 GB): over the ceiling it
  dies alone with exit 137. A 137 means the job must load less, not that the
  cap should rise — the desktop, browser and Claude need the other ~5 GB.

---

## Trading mandate and hard constraints

These came out of the original design conversation and are **not** derivable from
the code. They bound everything else.

> **Addendum A (2026-09-24, approved by Addendum B) revises four of these.** Kept below unedited as the record of what applied until then.
>
> | rule below | under Addendum A |
> |---|---|
> | Orders are placed by a person | the system places, monitors and exits orders automatically through the central risk and execution layer; humans handle only configuration, funding, account authorization, maintenance and emergency shutdown (§24) |
> | Swing trading only, never intraday | intraday, day trading, swing and longer holds are all permitted (§3); the risk engine must enforce the pattern-day-trader / settled-cash rules that apply to the account type — see Stage I decision 2 |
> | Top 10 by score each day (`top_n`) | the live slot allocation engine fills up to five slots with distinct eligible strategies and leaves a slot in cash rather than fill it with a losing strategy (§11–13) |
> | Stops checked about once a day | a position monitor checks stops continuously during market hours; risk exits override strategy signals (§16–17) |
>
> Unchanged: the $100 cap and ~$20 x 5 sizing (now configurable, §14); the
> user owns the outcome; Robinhood's dollar-order mechanics below.

- **The account is capped at $100.** That is the entire downside. Sizing is
  **$20 x 5 concentrated positions** (`config.yaml`, changed 2026-09-14 from
  $10 x 10). Do not propose sizing that assumes a larger account.
- **Orders are placed by a person, and the pipeline is built around that.**
  Not as a training-wheels measure: Claude does not execute financial
  transactions, so the loop is *system generates -> human places -> system
  reconciles*. `orders.py` writes an exact slate to `data/orders_today.txt` and
  `.json` each morning; a person places them; the next run reads the real
  account and records actual fills. Nothing needs to be reported back by hand.

  Two consequences worth knowing rather than rediscovering:

  **Sells are always listed before buys.** A fully deployed $100 account has no
  spare cash, so a buy placed before its matching sell is rejected for
  insufficient funds.

  **A `picks` row is `recommended` until the position is confirmed in the
  account, then `open`.** Marking a proposal as held on the day it is proposed
  makes the order generator see a full book and refuse to buy the very names it
  just recommended.
- **The user owns the outcome.** This is a data-gathering and scoring tool. It does
  not give investment advice, and no backtest figure is a forecast.
- **Swing trading, days to weeks — never intraday.** Not a style preference: US
  pattern-day-trader rules require $25k equity to day-trade without restriction, so
  a $100 account cannot day-trade. Any change toward intraday breaks this.
- **Selection: the top 10 by score each day** (`risk.selection_mode: top_n`),
  subject to tradeability floors of `min_price` $5 and `min_dollar_volume` $1M/day.

  The old rule was "score >= 70". **It was unreachable and always selected
  nothing.** The score is a calibrated probability of a ~27%-base-rate event, so
  it rarely exceeds 50 — the highest in 183k out-of-sample rows was 66. Threshold
  and score were on different scales. Changed 2026-09-11 with the user's
  agreement. Do not reinstate an absolute cutoff without first checking it
  against the score distribution.

### Robinhood order mechanics — these shape the design

Dollar-based fractional orders are supported (to 6 decimal places), which is what
makes a $100 account workable at all. But:

- **Dollar-amount orders are market orders only.** No limit or stop order can carry
  a dollar amount.
- **They execute only during regular hours**, 09:30-16:00 ET.

The consequence matters: **stop-losses cannot rest at the broker.** `stop_loss.py`
computes a level, `check_exits.py` compares it against a daily quote, and the exit
is then placed as an approved market order. So a stop is checked roughly once a day,
not continuously — **overnight and intraday gaps below the stop are not protected
against.** Any future work on exits should start from this limitation rather than
assume a broker-side stop exists.

### Claude's role in the daily loop

> Superseded by Addendum A (approved by Addendum B): routine selection and ordering become
> automatic, with no per-trade approval step (§2, §24).

Claude reads exactly two files — `data/scoresheet.json` and `data/exits_needed.json`
— and nothing else. Not the raw data, features, or model. For entries it filters to
the top candidates by score, checks tradability and fractional eligibility,
checks the open-position count against the cap, presents the list for approval, and on approval places $10
market orders. Fill prices are reported back so the ledger can be written
server-side; Claude has no direct database access.

---

## Architecture

Grouped by what each module is for. Everything reads `config.yaml`; nothing
hardcodes paths, thresholds or model parameters.

### Core plumbing
| File | Role |
|---|---|
| `universe.py` | Ticker list (`sp500` / `all_us` / `custom`). Also owns `load_config()`, imported everywhere. |
| `runtime.py` | CPU thread caps and nice level. **Must be imported before numpy/pandas/xgboost.** |
| `storage.py` | Owns `market_data.db` — schema, upserts, ingest state. Only module writing SQL to it. |
| `costs.py` | Commission, spread by liquidity tier, slippage, SEC/FINRA fees. One cost model so backtest and paper agree. |
| `notify.py` | Telegram + desktop delivery. Formats the slate for a phone; red/green emoji because Telegram has no text colour. |
| `monitor.py` | Live process//job dashboard served on the VM. |

### Data acquisition
| File | Role |
|---|---|
| `backfill.py` | Resumable OHLCV loader. `--top-up` for daily use. Owns `last_market_session()`. |
| `data_pull.py` | yfinance fetch helpers. |
| `build_features.py` | Computes the 20 indicators across all history into `features`. |
| `features.py` | The 20 indicators per (ticker, date). No third-party TA lib. |
| `sec_fundamentals.py` | Pulls SEC company facts into `sec_filings` / `sec_facts`. |
| `value_metrics.py` | Derives ~40 value/quality metrics per filing, including point-in-time `market_cap`. |
| `fundamental_features.py` | Lags filings into `daily_fundamentals` so screens never see a filing before it existed. |
| `edgar_registry.py` | Point-in-time registry of every SEC annual filer, 1993-now. The only source reaching before 2008. |
| `edgar_events.py` | 8-K item codes as an event taxonomy. |
| `delistings.py` | The delisting registry. Reads its API key from `~/.alphavantage_key`, never the repo. |

### Survivorship bias
| File | Role |
|---|---|
| `reconstruct_universe.py` | Replays Internet Archive captures of the symbol directory. |
| `bias_benchmark.py` | Quantifies the bias in %/year against Ken French's CRSP-based series. |
| `bias_exposure.py` | Scores a strategy's dependence on deeply drawn-down names; gates the sealed stage. |
| `synthetic_delistings.py` | Generates delisting price paths from researched patterns. |
| `synthetic_validate.py` | Checks synthetic paths against the real delistings we do hold. |
| `retest_synthetic.py` | Re-scores strategies against panels augmented with synthetic failures. |
| `stress_test.py` | Bounds how much a result depends on the missing companies. |
| `mc_1m.py` | The million-path Monte Carlo over delisting families. |

### The Strategy Lab
| File | Role |
|---|---|
| `genome.py` | The searchable rule representation, plus `shape()`, `value_range()`, `is_degenerate()`. |
| `simulator.py` | Vectorised scorer. **Fills at the next open**; exits priced off the unfiltered series. |
| `reward.py` | Fitness. Risk-adjusted, cost-net, scored against the null surface. |
| `benchmark.py` | The null: a surface over entry price x holding period. `--compare-fills` measures fill conventions. |
| `control.py` | Runs random genomes through the real gates. The ladder's false-positive rate. |
| `evolve.py` | The population loop. |
| `ledger.py` | Strategies, evaluations, promotions, lab_runs. |
| `promote.py` | Six-stage ladder; the sealed holdout is enforced in code. |
| `rescore.py` | Re-scores past survivors after a benchmark change. |
| `seeds.py` | 20 published strategies as a sanity baseline. |
| `paper_trading.py` | Advances open paper runs one day. The only unbiased measurement here. |

### Fundamental and conviction screens
| File | Role |
|---|---|
| `conviction.py` | The screens (Piotroski, Magic Formula, ValProf, Buffett, deep value). Ranks **within size buckets**. |
| `conviction_walkforward.py` | 15 rolling 2-year windows against SPY. |
| `buffett.py` | QMJ-style quality score, and the Buffett's-Alpha reproduction. |
| `pead.py` | Post-earnings announcement drift / SUE. |

### Bull/bear ETF switching
| File | Role |
|---|---|
| `paired_etf.py` | The original pre-registered ERX/ERY test. Run once, **closed FAIL**. |
| `erx_momentum.py` | Momentum method grid + `run_switch()` + the random-switch null. |
| `pair_momentum.py` | The same across every pair and leverage level, with buy-and-hold as a second benchmark. |
| `pair_funds.py` | The five live switching funds. Searches, opens and steps them. |

### Order execution (built 2026-09-22)
| File | Role |
|---|---|
| `signals.py` | The only shape execution accepts. `signal_id` is content-addressed, which is what makes retries idempotent. |
| `risk_engine.py` | What is ALLOWED, separate from what a strategy wants. Fails closed on any unknown. |
| `config/risk.yaml` | Execution limits. Deliberately NOT `config.yaml`, so a strategy edit cannot widen a risk limit. |
| `killswitch.py` | Six switches. `data/KILL_SWITCH` stops everything with no code running. |
| `broker.py` | `BrokerInterface`, `SimulatedBroker`, `RobinhoodBroker`, and the order state machine. |
| `execution.py` | The only path from signal to broker. Duplicate check, risk, build, submit, resolve, record. |
| `run_execution.py` | Turns the daily book into signals and runs them. SIMULATION by default; LIVE refuses. |

### The Strategy League (built 2026-09-22)
| File | Role |
|---|---|
| `league.py` | Strategy identity, immutable versioning, the 10-state lifecycle. Append-only; contains no `UPDATE`. |
| `migrate_league.py` | Brought the 21 forward funds in. **Moves no data** — points at the existing tables. |
| `scoreboard.py` | The persistent leaderboard. Its main job is **refusing to rank** a sample that cannot support a rank. |
| `degradation.py` | backtest -> forward, in mean per-trade terms. How predictive are our own backtests? |
| `eligibility.py` | Correlation, and the top-five-ELIGIBLE rule. **Promotes nothing.** |

### Point-in-time fundamentals (built 2026-09-22)
| File | Role |
|---|---|
| `pit_backfill.py` | Recovered `accepted` / `prevrpt` / `detail` for all 400,700 filings from the cached zips. |
| `pit_facts.py` | "What was knowable as of this exact date?" Resolves the first tradeable session per filing. |
| `industry.py` | SIC -> division and major group, **point-in-time**. A peer-grouping heuristic, never a feature. |
| `fix_ticker_map.py` | Repaired 181 issuers mapped to a preferred or warrant series. |

### Financial statements (built 2026-09-22)
| File | Role |
|---|---|
| `statements.py` | The three statements per filing, point-in-time. **"not reported" is never zero.** |

### The Research Library (built 2026-09-22)
| File | Role |
|---|---|
| `strategy_library.py` | Every strategy idea with provenance. `known_biases` and `limitations` are **required** fields. |
| `factory.py` | Governed generation. Five gates before a genome is drawn. **Cannot unfreeze itself.** |

### Phase 13 — the Strategy Factory (built 2026-09-24)
| File | Role |
|---|---|
| `accounting.py` | **The authoritative P&L.** Liquidation basis for every fund; restated beside the original curves, never over them. |
| `strategy_objects.py` | §13 metadata, metric snapshots and §37 decisions around the league identity. |
| `strategy_factory.py` | 40 families as economic hypotheses with fixed small grids. Templates, not search. |
| `research_queue.py` / `library_bridge.py` | The research queue; library entries -> linked strategy objects. |
| `discovery.py` | What to test next: priority, budgets, failure records, recycling as new versions. |
| `robustness.py` | §28 collapse tests and pre-defined SPY regimes. |
| `factory_pipeline.py` | DISCOVERED -> ... -> PAPER -> QUALIFIED -> LIVE_CANDIDATE. Backtests admit, only forward evidence qualifies. |
| `leagues.py` | Nine leagues, tiers per B11, evidence from accounting. |
| `data_providers.py` / `finsaber.py` / `dataset_compare.py` | Provider interface, the FINSABER validation store, cross-dataset checks and survivorship tags. |
| `signal_decay.py` | §20: decile spread by horizon, t-stat across dates. |
| `phase6_report.py` | Phase 6 §31: the final report and §30 checklist, built from the database and a test run. |
| `baselines.py` | Phase 6 §16: each forward fund vs cash, SPY, its index ETF, the matched-universe null and same-size random portfolios. |
| `regimes.py` | Phase 6 §21: predefined regimes (SPY bull/bear, vol, crisis + 3-month T-bill high/low at a fixed 2.0%), the `rates` table, and forward P&L by regime. |
| `model_calibration.py` | Phase 6 §19: ranking skill, calibration (Brier, log loss, ECE), economic value and net return by fixed confidence band — four questions, answered separately. |
| `data_dictionary.py` / `changelog.py` | Generate `docs/DATA_DICTIONARY.md` and `CHANGELOG.md`. |
| `run_bounded.sh` / `ado_ship.sh` | Memory-capped job launcher; ADO review-approve-merge helper. |
| `finsaber_pkl.py` | Streams FINSABER's pickles (27.3 GB) without loading them; a restricted pickle VM — only `datetime.date` may be built. |

### Addendum A — the trading engine (built 2026-09-24, SIMULATION/SHADOW)
| File | Role |
|---|---|
| `ranking.py` | The single ranking: score = (k x backtest + n x paper) / (k + n) in net return per trade; losing backtest out; DEMOTED stays in the pool. What slots.py fills from. |
| `slots.py` | Pair funds (`pair:`) trade the ETF their fund holds, via `pair_funds.next_leg()`, with a `slots.pair_risk` ATR stop. The Value Fund (`value:`) trades its top-ranked holding with a `slots.value_risk` stop and sells when the fund sells. Five slots filled from ranking.py's top five tradeable strategies; family cap; controlled replacement on score; the leaderboard. Places no order. |
| `stop_plans.py` | Mandatory stop plans; valid only with a price stop; tightest wins; risk outranks strategy. Carries the genome's take-profit (an exit, never a stop). |
| `survivorship_backtest.py` | Every ranked strategy backtested with the synthetic dead companies (exclude / as_is / zero); ranking.py scores and gates on as_is. |
| `exit_sweep.py` | Registered `exit_rules` experiment: take-profit x trailing stop against each slot strategy as it is. |
| `slot_trader.py` | Trades the slots through ExecutionEngine; `--auto` from cron; emergency policy; restart-safe via the orders ledger. |
| `quotes.py` | Live 1-minute quotes with a staleness refusal; the historical-intraday interface (not provided). |
| `market_caps.py` | Sourced market-cap fallback (Robinhood / yfinance, dated, <= 7 days) for names the filings miss. Never an assumed cap. |
| `account_rules.py` | Cash account: settled funds only (T+1 + 1 day margin). Margin: PDT entry stop. |
| `intraday.py` | Intraday signal engine, SHADOW only (B8). |
| `services.sh` | Installs the trader's cron line. |

### Addendum C — survivorship-bias-free universe (built 2026-09-24, retest-only)
| File | Role |
|---|---|
| `finance_database.py` | FinanceDatabase: sector / identifiers / delisted flag, no dates; attaches on ticker AND name only. |
| `universe_layer_a.py` | Which companies existed, 1996-2024, per-field provenance. |
| `universe_cohorts.py` | Real dead-company statistics by cohort; states its own clean-exit bias. |
| `universe_synthetic.py` | Tagged synthetic paths (v3, joint donor draws) for 7,618 unpriced dead companies. |
| `universe_loader.py` | `load_backtest_data(..., mode)` — exclude / real_only / as_is / zero / optimistic. |
| `universe_validate.py` | Discriminability gate, provenance checks, five-mode sensitivity. |

### The daily loop and reporting
| File | Role |
|---|---|
| `train_model.py` | Trains the XGBoost classifier. Owns `FEATURE_COLS`. |
| `walk_forward.py` | 31 rolling retrains; the out-of-sample prediction series. |
| `score.py` | Ranks the universe, writes the scoresheet. |
| `stop_loss.py` | ATR-based stop levels. |
| `position_tracking.py` | SQLite trade ledger. |
| `backtest.py` | Portfolio simulation over the scoring strategy. `--fill` switches convention. |
| `check_exits.py` | Evaluates open positions against stop/exit rules. |
| `daily_picks.py` | **The daily book** — best candidate from every system, sell signals, the size floor. |
| `orders.py` | The morning slate, `--record-fills`, and reconciliation. |
| `claude_fund.py` | The discretionary fund: positions chosen by judgement, not by the screens. |
| `fund_report.py` | One status line per fund across everything. |
| `experiments.py` | The experiment ledger CLI. |
| `llm_report.py` | Narrative report via local Ollama (absent on this VM). |
| `daily.sh` | Orchestrates the 7 daily stages. |
| `lab_loop.sh` | Overnight search loop. |
| `run_pipeline.sh` | The older single-run pipeline. |

Config lives in `config.yaml`. Nothing should hardcode paths, thresholds, or
model parameters — read them from config.

### Storage model

Two stores, different purposes.

**Market data** — `data/market_data.db` (SQLite), ~8.5 GB. Every table below
lives here.

*Prices and indicators*
| Table | What it holds |
|---|---|
| `prices` | 35.4M OHLCV bars, 13,121 instruments, 1962 to present. PK (ticker, date). |
| `features` | 33.8M rows of the 20 indicators. 31.5M fully non-null — the trainable set. |
| `symbols` | 13,182 listings tagged by `security_type`, with `data_quality` flags. |
| `ingest_state` | Per-ticker backfill progress. What makes the long load resumable. |
| `risk_metrics` | Monthly beta and idiosyncratic volatility. |

*Fundamentals*
| Table | What it holds |
|---|---|
| `sec_filings` / `sec_facts` | Raw SEC company facts. |
| `fundamentals` | ~40 derived metrics per filing, including point-in-time `market_cap`. |
| `daily_fundamentals` | Those metrics lagged to the day they became public. Screens read this, never `fundamentals`. |
| `edgar_filers` / `edgar_companies` / `edgar_events` | Point-in-time filer registry and 8-K events. |

*Survivorship*
| Table | What it holds |
|---|---|
| `delistings` | 9,464 delisted listings with exact dates. 7,480 common stock; we hold prices for 418. |
| `historical_listings` / `archive_snapshots` | Internet Archive replays of the symbol directory. |
| `synthetic_companies` | Generated delisting paths. |

*The Lab*
| Table | What it holds |
|---|---|
| `strategies` / `evaluations` / `promotions` / `lab_runs` | Genomes, scores, ladder decisions, run metadata. |
| `benchmarks` | The null surface: 360 cells over window x horizon x price band. |
| `oos_predictions` / `oos_folds` | 7.6M walk-forward out-of-sample predictions. |

*Forward records — the part that matters*
| Table | What it holds |
|---|---|
| `paper_runs` / `paper_equity` / `paper_positions` / `paper_trades` | The 16 simulated funds. `label` and `family` name them. |
| `pair_funds` / `pair_fund_equity` | The 5 bull/bear ETF switching funds. |
| `picks` | The daily book's recommendations, and the **actual fills** — `price`, `shares`, `entry_date`. |
| `claude_fund` / `claude_fund_meta` | The discretionary fund. Every position carries a written thesis. |
| `experiments` / `experiment_trades` | The experiment ledger. One row per test, ranked by money. |

**`paper_runs` stores each genome inline as JSON** rather than referencing
`strategies.id`. That denormalisation is why every forward test survived a
corruption that cost 5,767 strategy rows. Keep it.

**Trade ledger** — `data/positions.db` (SQLite). Stays separate. The "what did
the system actually do" record.

---

## The funds — what actually exists, 2026-09-17

Nothing here is estimated. `fund_report.py` rebuilds all of it daily.

**Real money.** One account, `••••6024` ("Agentic"), ~$89. Traded by the daily
book via a human placing the orders. The other three Robinhood accounts — Main
~$12.3k, Roth ~$1.9k, Robinhood-Managed ~$787 — are **not touched by this
system** and are reported only so one total exists.

**Paper funds, 16 open.** Named by what they trade, because opaque ids hid two
things worth seeing: 16 runs are about 5 distinct ideas, and whole families win
or lose together.

| Family | n | Average | Note |
|---|---:|---:|---|
| momentum | 8 | -2.40% | contains every winner |
| model | 1 | -4.90% | the XGBoost classifier |
| crash buyers | 5 | **-8.62%** | **every single one negative** |
| conviction | 2 | -2.71% | stalled 09-11 to 09-22, now running |

**The clearest lead this project has produced**: the same entry rule
(`pct_change(sma_200,3) > 0.02`) flips sign on stop width alone.

| Stop | Result |
|---|---:|
| 2.5 / 2.6 / 3.3 | +0.55% / +0.34% / **+1.72%** |
| 4.98 (x3) | -0.78% / -3.95% / **-8.30%** |

Tight stops win, wide stops lose, identical entry.

**REFUTED by the pre-registered sweep, 2026-09-24** (`stop_sweep.py`,
experiment `stop_width`, 2006-2019). Over fourteen years the `rising_200` entry
loses money net and trails the null in **all 30** stop x hold cells, and tight
stops do worse than wide ones — for all four entry rules tested. The forward
split below is 12 sessions in a market where this rule happened to work. Best of all 16 is
`MACD Pullback` at +2.00% — MACD in the top 30% but RSI still under 40.
**This is 11 days of forward data.** It is a lead, not a result.

**Pair funds, 5 open** (2026-09-15). Bull/bear ETF switching, $100 each.
See "Long/inverse switching" below.

**Claude Fund** — discretionary, unfunded, paper-tracked. Holds nothing. It
exists because the daily book *cannot* hold nothing: `top_n` always returns a
top N, so it fills five slots every morning whether or not five good ideas
exist. A fund that can decline to trade is a different instrument.

**The conviction funds were stalled for a reason nobody had checked — fixed
2026-09-22.** `conv_deep_value` and `conv_quality_value` sat frozen from
2026-09-11. The diagnosis recorded here was that their `strategy` field holds
`{"conviction": "deep_value"}` rather than a genome, so the stepper could not
advance them. **That was wrong.** `paper_trading._conviction_of` and
`_conviction_step` handle that shape correctly and log the real reason: *no
fundamental panel this week*.

`daily_fundamentals` stopped on 2026-09-11 and nothing rebuilt it. It is
derived from filings rather than bars, so the price top-up never touched it,
and `daily.sh` had no stage that did. Prices and features advanced every
morning; fundamentals did not, for eleven days.

**The freshness gate did not catch it because it only looked at `prices`.**
Every conviction screen in the daily book was reading eleven-day-old
fundamentals while the pipeline reported success — the same silent-staleness
failure as the 2026-09-15 bug, in a table the gate did not watch.

Both fixed: `daily.sh` gained a `[3b/10] Fundamental projection` stage, and
`freshness.check_derived()` now measures `features` and `daily_fundamentals`
against `prices` and fails the run when either falls behind. A missing table
fails too — a check that passes when its subject is absent is not a check.

**The general lesson, now costing this project a fourth bug: a freshness gate
protects only the tables it names.**

Both funds stepped on 2026-09-22 and are running: 10 positions each, **-2.60%
(quality_value)** and **-2.81% (deep_value)** since 2026-09-11.

**Their equity curves have an eleven-day hole and it was left there.** The
positions were chosen on 09-11 and the return across the gap is real, but the
daily path between the two marks does not exist and was not manufactured. Those
days were never stepped; writing them in afterwards would turn a gap in the
forward record into fabricated forward record, which is the one thing this
project's only unbiased measurement cannot survive.

## The Strategy League — built 2026-09-22, and it ranks nothing

Phase 7 Stage B. All 21 forward funds (16 paper + 5 pair) are registered with a
stable identity, an immutable version history and a lifecycle state. The
scoreboard, degradation tracker and eligibility rules run nightly from
`daily.sh`.

**Every one of them currently reports the same thing: not enough data.**

| | |
|---|---|
| ranked by the scoreboard | **0 of 21** |
| eligible for a live roster | **0 of 21** |
| measurable correlation pairs | **0 of 210** |
| degradation verdicts | **0** — 11 pairings, all provisional |

That is the correct answer, not a configuration problem. The funds hold a
**median of 7 equity marks** against a floor of 60, and a Sharpe from 7
observations is noise with a decimal point. **Do not lower `min_rank_marks` to
make the leaderboard populate** — a leaderboard of whoever got lucky in their
first fortnight is precisely the decision this league exists to prevent.

Four design rules that are load-bearing rather than stylistic:

1. **Identity splits from version.** `strategy_key` is who a strategy is;
   `version` is what it was. `definition_hash` covers entry, exit, sizing,
   holding period and parameters — and deliberately excludes labels, so a
   rename cannot fork a forward record and a rule edit cannot inherit one.
2. **State is derived from an append-only log, never stored in a column.** A
   column is something a person can set. For the record that would justify
   allocating capital, that difference is the point. `league.py` contains no
   `UPDATE` at all.
3. **The migration moved no data.** `paper_runs`, `paper_equity`,
   `paper_trades`, `pair_funds` and `pair_fund_equity` are never written by it;
   the league points at them. Nothing is copied, so nothing can be copied
   wrongly. Re-running it is a no-op.
4. **Unknown blocks.** An unmeasurable correlation is treated as correlated,
   not as independent — the same fail-closed rule as unknown market cap and
   unknown liquidity. Admitting unmeasured pairs is how five copies of one bet
   reach a roster that believes it holds five, and six of the sixteen paper
   funds really are one entry rule at different stop widths.

**The scoring formula is deliberately undecided.** Phase 7 asks for the
architecture to *test* formulas, so they are registered in `scoreboard.FORMULAS`
and every snapshot records which one produced it. `sharpe_only` exists as a
control: a considered formula that cannot beat ranking on raw Sharpe is not
adding anything.

**Nothing promotes anything to live.** Item 18 is explicit, and the tests assert
that `eligibility.py` performs no lifecycle transition and imports neither
`execution` nor `broker`.

### A units trap worth remembering — degradation, 2026-09-22

The first version of `degradation.py` divided the Lab's `net_pnl_usd` by a
fund's $100 capital. But that P&L is the sum across up to 20,000 independent
$20 trades over fourteen years, while a forward return compounds one $100 book
over weeks. It produced backtest figures of **3,428% to 26,065%** against
forward figures of a few percent, with every "survived" ratio near zero — a
table that read as a devastating finding about backtest reliability and was
purely a unit error. The docstring warning against exactly that trap was already
written above the line that walked into it.

Both sides are now **mean return per trade**, the only quantity a backtest and a
forward record both actually have.

## The Research Library — built 2026-09-22, nothing in it is SUPPORTED

Phase 8 Stage C. 35 entries covering every idea this project has implemented or
intends to test.

| status | n | meaning |
|---|---:|---|
| REFUTED | 16 | measured here, failed, and the encoding was faithful |
| INCONCLUSIVE | 5 | **our encoding** failed; the publication was never tested |
| HYPOTHESIS | 14 | recorded, not yet measured here |
| **SUPPORTED** | **0** | nothing has cleared a forward test |

**A citation is provenance, not a result.** Everything enters at HYPOTHESIS
whatever its pedigree. Novy-Marx is a reason to test gross profitability on this
data, not a reason to believe the answer first.

**Evidence is computed from the database at import, never typed in.** That is
how a retracted result outlives its retraction — this project has already had a
finding survive an hour past its own refutation because it was written down
somewhere else.

### "0 of 20 beat the null" — the precise version

The loose phrasing in this file is worth pinning down. Measured at import:

| | |
|---|---:|
| seed evaluations showing **positive excess over the null** | **40.3%** |
| seed evaluations **clearing the promotion gate** | **0%** |

Both are true and only the second means anything. The gate sits at the 95th
percentile of what random strategies achieve, so beating the null by a little is
what noise does too. The library stores both so the loose statement cannot be
mistaken for the strict one.

### A refuted ENCODING is not a refuted publication

Five of the twenty seeds say outright they are not the rule as published —
*"an adaptation, not the strategy"*, *"a z-score break and an N-day-high break
are not the same event"*, *"roc_10 is far shorter"* against Jegadeesh & Titman's
3-12 month formation. Their encodings failed here; the publications were never
run.

`strategy_library.NOT_FAITHFUL` names those five, and **only a FAITHFUL encoding
may be marked REFUTED**. The rest are INCONCLUSIVE with the deviation stated.
"Jegadeesh & Titman: REFUTED" is a far larger claim than anything measured here,
and it is the version someone would remember.

### Governed generation — the gates exist, the freeze stands

`factory.py` requires **all five** before a single genome is drawn:

1. A **registered experiment** — what is being tested and what would count as it
   failing, written before any result exists.
2. **`seed_mode: NONE`** — no hand-written rules, no descendants.
3. A **declared trial budget**, priced against the append-only ledger.
4. The **freeze explicitly acknowledged** in the experiment spec.
5. **Ancestry recording**, not switchable here.

Blockers accumulate rather than short-circuit, so governance reads as a
description of a legitimate run rather than a queue of obstacles to clear one at
a time.

**It cannot unfreeze itself.** `authorize()` reports whether a run *would* be
permitted. Flipping `search.mode` to ACTIVE is a human edit to `config.yaml`,
deliberately outside this code — a governor that can lift its own restriction is
not a governor. **Search remains FROZEN and every run is refused today.**

## 212 large caps were invisible to the fundamental screens — fixed 2026-09-22

**`sec_filings.ticker` pointed at a preferred or warrant series for 212
issuers.** The list is a who's-who: J P Morgan as `JPM-PM`, Wells Fargo as
`WFC-PZ`, AT&T as `T-PC`, Ford as `F-PD`, MetLife as `MET-PF`, Goldman as
`GS-PD`, Simon Property as `SPG-PJ`.

The consequence was not cosmetic. The conviction screens need price **and**
fundamentals under one ticker:

| | JPM | JPM-PM |
|---|---:|---:|
| price bars | 11,723 | 1,295 |
| fundamental rows | **0** | 69 |

So the screens were not ranking JPMorgan poorly. **They could not see it.**

**This is a second, independent cause of "the daily book never recommends an
S&P 500 name."** The 2026-09-14 investigation found value ranks were size ranks
in disguise and fixed that. This sat underneath it the whole time, and mostly
hit financials — the division with 1,374 tickers and the market's largest
issuers.

Repaired by `fix_ticker_map.py`, deliberately narrowly: a remap happens only
when the base ticker exists in `symbols` as common stock **and** the dashed one
does not. 260 of 305 qualify; **45 are left alone**, because `BRK-A` and `BRK-B`
are both real common stock and mapping either to `BRK` would invent a security
that does not trade. A wrong mapping attaches one company's financials to
another company's prices and nothing downstream would ever notice. Originals are
kept in `ticker_raw`.

After rebuilding `value_metrics` and `fundamental_features`: `daily_fundamentals`
grew by 456,638 rows, and **111 of the repaired issuers now appear in the
conviction panel with a median market cap of $8.0B against the panel median of
$3.2B.**

## A filed DATE is not an acceptance TIME — 2026-09-22

The SEC stamps `filed` using a **17:30 cutoff, not the 16:00 close**:

| accepted in hour | filings | share carrying the SAME filed date |
|---:|---:|---:|
| 16:00-16:59 | 139,593 | **100%** |
| 17:00-17:59 | 61,067 | 88.4% |
| 18:00+ | ~27,000 | ~1% |

So roughly **193,600 filings — 48% of the corpus — carry a date on which they
were not tradeable.** All 400,700 now store `accepted` to the minute, plus
`prevrpt` (superseded by a later amendment; the form string cannot tell you
this, since an amended 10-K is still form "10-K").

**The existing two-day lag turned out to be conservative, not leaky.** Measured
against the session the pipeline effectively uses, 2 of 20,000 filings are
optimistic and both are SEC data defects — an acceptance stamp a month and a
year after its own filed date. **Nothing was rewired to the tighter rule**: a
conservative error costs signal, an optimistic one costs the truth of every
number downstream.

`sec_fundamentals.py` now stores all of this at load time, so a future fetch
cannot reintroduce the gap.

### Two false alarms in one session, from the same mistake

Both came from a check that did not replicate a step the real code performs:

1. Comparing which value a daily row was *closest* to, to detect amendment
   look-ahead — but a 10-Q filed between a 10-K and its 10-K/A supplies a
   different number entirely. Reported 23% look-ahead; the truth, tested against
   the mechanism, was **429 of 429 correct**.
2. Comparing `first_tradeable` against raw `filed + LAG_DAYS` — but
   `merge_asof` snaps to the next **session**. Reported 3,996 of 20,000 as
   look-ahead; the true figure was **2**.

**A verification that skips a step the pipeline performs will invent a bug.**
Both checks now do the snap, and say why in the code.

## The statement engine, and what it cannot see — 2026-09-22

`statements.py` exposes revenue, margins, balance sheet, cash flow and returns
per filing, point-in-time via `first_tradeable`. 16 SEC tags were added and the
70 cached quarters re-parsed: **`sec_facts` went from 19.0M to 23.5M.**

**Coverage is uneven, and that is a data fact rather than a bug.** Across 400
companies:

| field | coverage |
|---|---:|
| assets / equity / book value | ~98% |
| net income | 93% |
| revenue | 75% |
| EBITDA | 58% |
| **debt** | **38%** |

**Debt at 38% is the binding constraint on the valuation engine.** Many filers
never tag `LongTermDebtNoncurrent` or `ShortTermBorrowings`, so every EV-based
multiple — EV/EBITDA, EV/EBIT, EV/Sales — is computable for a minority of the
universe. Treating missing debt as zero would report those companies as
unlevered with an artificially low enterprise value: **the most flattering
possible error**, applied precisely to the companies we know least about.

### Two rules in this engine

**Absence is never zero.** A company that did not disclose R&D is not one that
spent nothing on it. Every figure is a number or `None`, and any ratio with a
missing input is `None`. The one deliberate default is at `_net_debt`: absent
short-term borrowings count as zero, safe *only* because it makes leverage look
better, so a company failing a leverage test fails on debt we can actually see.
**Missing cash is not defaulted**, because that would invent leverage.

**Capex is subtracted.** It is reported as a positive outflow; adding it to
operating cash flow turns the most capital-hungry companies into the database's
best free-cash-flow generators — a ranking that looks plausible and is exactly
inverted.

### INSERT OR REPLACE wiped two repairs — fixed at source

Re-parsing the zips **reverted every ticker repair and erased
`first_tradeable`**, because `INSERT OR REPLACE` deletes the whole row and
reinserts it. JPMorgan went back to `JPM-PM` within one reload.

`sec_fundamentals.py` now UPSERTs and will not overwrite `ticker` where
`ticker_raw` records a repair. **If you add a column to `sec_filings` that is
owned by another module, add it to that exclusion too** — a loader that
refreshes a row must not silently own every column in it.

## Conventions

### How to communicate

- **Be brief.** Default to fewer words. Include what is needed to act or decide,
  and stop. No preamble, no restating the question, no summarising work the user
  just watched happen. Length is not thoroughness.
- **Prefer structure over prose.** Bullets, tables, short lists, diagrams and
  charts wherever they carry the information better than paragraphs. Numbers
  belong in tables; comparisons belong side by side; sequences belong in
  ordered lists.
- These two work together: structure is what makes brevity possible. A table of
  six figures replaces a paragraph nobody finishes reading.
- Brevity does not mean omitting bad news. Caveats, risks and failures stay —
  state them in one line instead of three.


- **Commit on every change. No exceptions.** This is the project's primary rule and
  it overrides any instinct to batch work up. Every edit — code, config, docs,
  a one-line typo fix — gets its own commit before moving to the next thing. The
  git log is the project's change record; if a change isn't committed, it didn't
  happen. Do not wait to be asked, do not finish a session with a dirty tree, and
  do not roll unrelated changes into one commit.
- Update `README.md` in the same commit whenever a change affects setup, usage,
  schema, or pipeline shape. See `GIT_WORKFLOW.md` for message conventions.
- Config over hardcoding, always.
- Pipeline stages must be independently runnable and idempotent — rerunning a
  stage should update state, not duplicate or corrupt it.
- Long-running jobs must be resumable. Assume any run can be interrupted.
- Never introduce a dependency without adding it to `requirements.txt` in the
  same change.

---

## Scale targets

- Universe: **13,155 listings** from the NASDAQ Trader directory across NASDAQ,
  NYSE, NYSE American, NYSE Arca, Cboe BZX and IEX — every instrument type, each
  tagged. `universe.tradeable_types` keeps the scanner on common stock; the
  database deliberately holds the whole market.
- History: **full available depth**, 1962 to present.
- **Measured** database size: 8.5 GB (73 GB free). The original 14-19 GB estimate
  turned out to be in the right range only by accident — it assumed 20 years for
  6-8k common stocks, and the real shape is 60+ years for 13k instruments.
- Beware the earlier universe count of 6,169 "common stocks": **822 of those were
  not common stock** (closed-end funds, corporate notes, preferred, units). Fixed
  by `security_type` tagging on 2026-09-08.

### Host — migration completed 2026-09-08

Now running on the "Arena" VM. Hostname is `stockpicker2000` and the Linux user is
`stockpicker` — both predate the rename to Stockbot2000 and were left alone; only
the project is renamed. Repo at `~/stockbot2000`. Ubuntu 26.04 LTS.

Measured: **4 vCPU (1 socket) / 11.7 GB RAM / 194 GB disk** (165 GB free).

The disk was resized 2026-09-11 — the volume group had ~98 GB unclaimed, so `/`
was 97 GB against a 200 GB device. `lvextend -l +100%FREE` plus `resize2fs`
recovered it. Worth re-checking after any VM reconfiguration.

RAM is 11.7 GB, not the 12 GB planned. The Strategy Lab compute plan is sized
against the measured figure — see `docs/STRATEGY_LAB.md`.

**CPU is capped deliberately.** `runtime.py` holds OpenBLAS, OpenMP and XGBoost to
`compute.max_threads` (3 of 4 cores) and batch jobs call `be_nice()`. It must be
the *first* import in any entry point: those libraries read their thread counts
once at load time, so setting the variables after numpy is imported does nothing,
silently. Do not reorder those imports.

The old host (`betbot9000`) is not reachable from this VM. Code arrived by
manual file transfer, so **there is no git history before this point.**

CPU is fully committed across both VMs, so heavy jobs (historical backfill, model
training, strategy search) need an off-peak window. The strategy search and the
Ollama LLM step must not run concurrently — together they exceed 12 GB.

---

## AI Development Orchestration — BUILT 2026-09-22

Claude architects, specifies and reviews; a cheaper model implements; git is the
source of truth; `run_tests.sh` is the gate. Full documentation in `docs/ADO.md`.

```bash
python orchestrator.py next-task | implement TASK-nnn | test | review | approve | merge
```

Four rules that are load-bearing rather than stylistic:

1. **Nothing auto-merges.** A passing gate means known failures did not recur.
   Every defect in this project's history passed every test that existed when it
   shipped.
2. **A task without checkable acceptance criteria is refused**, because an
   ungated task has to be reviewed line by line, which is the cost being avoided.
3. **The model may only write files its task names.** Anything else is refused.
4. **Context is small and deliberate** — project state, conventions, named
   files, and the schema for database tasks. Never the repository, never the
   conversation.

First task cost **$0.0147** across three rounds. The two rejections are recorded
in `docs/ADO.md` because both were instructive: one audited the wrong database
entirely, and one was a context defect on my side rather than a model error.

---

## THE PROJECT DIRECTION — Phases 6-13

**A full revamp of the project's planning. All existing systems integrate into
this direction.** Phases 6-12 are built (stage tables in
`docs/ROADMAP_INTEGRATION.md`). **Phase 13 and Addendum A are BUILDING from
2026-09-24 under Addendum B** (`docs/ADDENDUM_B_FINAL_BUILD_DIRECTIVE.md`),
which resolves their open decisions — see the table at the end of
`ROADMAP_INTEGRATION.md`.

| Phase | | Spec |
|---|---|---|
| 6 | Research Integrity & Independent Validation | `docs/PHASE6_RESEARCH_INTEGRITY.md` |
| 7 | Continuous Strategy Laboratory & Paper Trading League | `docs/PHASES_7_11_STRATEGY_LEAGUE.md` |
| 8 | Continuous Strategy Discovery & Real-World Strategy Library | same |
| 9 | Fundamental Value Intelligence Engine | same |
| 10 | Live Capital Allocation & Strategy Promotion | same |
| 11 | Continuous Research Loop | same |
| 12 | Crypto Fund | `docs/PHASE12_CRYPTO_FUND.md` |
| 13 | Strategy Factory 2.0 + Data Integrity + Continuous Discovery | `docs/PHASE13_STRATEGY_FACTORY.md` |
| A | Autonomous 5-slot trading system | `docs/ADDENDUM_A_AUTONOMOUS_5_SLOT.md` |
| B | Final build directive | `docs/ADDENDUM_B_FINAL_BUILD_DIRECTIVE.md` |
| C | Survivorship-bias-free universe reconstruction (revision 2) — PLANNED; build only after the user confirms the staged plan and answers the questions in Stage J | `docs/ADDENDUM_C_SYNTHETIC_DELISTING.md` |

Integration analysis — dependencies, module reuse, gaps, schema, risks, ordering
— in `docs/ROADMAP_INTEGRATION.md`.

**What changes, in one line:** Stockbot2000 stops being a system that searches
for a good backtest and becomes a research laboratory where strategies compete
continuously, are graded on a permanent scoreboard, and receive capital only
through promotion — with a separate Fundamental Value Engine feeding a distinct
long-term Value Fund.

Four things that reverse current behaviour, listed so they are seen before
anything is touched:

1. **Search freezes by default** (`SEARCH_MODE=FROZEN`). The watchdog must not
   restart a deliberately frozen search — a direct reversal of the watchdog
   installed 2026-09-19.
2. **Seeding becomes explicit and traceable** (`seed_mode: NONE`). No
   hand-written rules, no descendants of seeded strategies, ancestry recorded
   per strategy.
3. **Compute priority inverts**: data integrity first, strategy search last.
4. **Nothing is ever overwritten.** Strategy versions, scores, ranks and
   retirement records are immutable; a modified strategy becomes a new version.

**The central architectural rule of the new direction:** the live roster is the
top five *eligible* strategies after risk and correlation constraints — never
the five highest raw returns. Raw profitability alone would fill all five slots
with copies of the same trade. Beating SPY is a reference point, not a promotion
requirement.

**Three layers that must not be collapsed:** Research Factory creates and tests
ideas; Strategy League paper-trades and ranks them; Capital Deployment allocates
only to strategies that pass promotion and risk. The league must not be able to
call the broker.

---

## Phase 6: Research integrity & independent validation — BUILT 2026-09-22/24

**The new project direction.** Specification reproduced verbatim in
`docs/PHASE6_RESEARCH_INTEGRITY.md`; roadmap phase 15. **Built**: Stage A in
`docs/ROADMAP_INTEGRATION.md`, finished 2026-09-24 with baselines (§16),
calibration (§19), rate regimes (§21), `case_studies/TNON.md` (§24),
`docs/RESEARCH_METHODOLOGY.md` + `docs/EXPERIMENT_PROTOCOL.md` (§29) and
`phase6_report.py` (§31). **The §31 report has not been run yet** — it needs
the VM's database: `./run_bounded.sh ./venv/bin/python phase6_report.py`.

All existing systems integrate into this direction. Its premise is the project's
own record: the system has repeatedly produced apparent edges that were later
proven to be measurement artifacts, so the phase is about making it harder for
Stockbot2000 to fool itself rather than about finding another strategy.

Default assumption it imposes: **NO EDGE UNTIL PROVEN OTHERWISE.**

Items that reverse current behaviour, and so matter before touching anything:

- **`SEARCH_MODE=FROZEN`.** Continuous evolutionary search stops by default. The
  watchdog keeps monitoring but must NOT restart a deliberately frozen search.
  The stated reason is the multiple-testing burden of 1.03M trials, not a belief
  about momentum.
- **`seed_mode: NONE`** means no human-provided strategies, no hand-written
  rules, and no descendants of seeded strategies. Every strategy carries an
  ancestry record and a seed-derived strategy is never classed as an independent
  discovery.
- **Compute priority is inverted**: data integrity, forward testing, regression
  tests, independent validation, backtesting, and strategy search LAST.
- **Forward strategies are frozen on entry** and never modified retrospectively.

---

## Robinhood Agentic execution — core BUILT 2026-09-22

Specification in `docs/ROBINHOOD_AGENTIC.md`; status in `PROJECT_STATUS.md`;
roadmap phase 14. **Merged into this project, not forked into a separate tree** —
two systems against one 8.5 GB database was the risk being avoided.

Built and tested: signal schema, risk engine, six kill switches, broker
abstraction, order state machine, execution engine, shadow mode, and the runner.
**67 tests across 5 files, all passing.**

Built since (Addendum A, 2026-09-24): scheduled reconciliation (every
slot_trader run compares the slot log with the broker and halts on any
difference), order-state recovery on restart (LedgerSimulatedBroker rebuilds
from the orders ledger), and a per-trade reason on every slot trade. **Still
not built: the LIVE transmit path** (RobinhoodBroker builds the spec only;
transmission is the operator's) and the automated acceptance checklist.

Connects the strategy engine to the Agentic account via Robinhood's official
Trading MCP, with a deterministic execution pipeline — signal, risk engine,
order validation, execution, order state machine, reconciliation — and the LLM
as a supervisory layer outside that path.

Three things to know before touching it:

1. **Around half the 25 specified phases already exist here.** The spec is
   written greenfield; this project is not. Building a separate
   `robinhood_trading_system/` tree would fork the project into two half-systems
   sharing one 8.5 GB database. The spec document carries a phase-by-phase audit
   of what to reuse.
2. **The new work is narrow**: kill switches, the execution engine, the order
   state machine, live mode, order-state recovery, and a real test suite. Two
   tests exist today, which is the honest gap.
3. **Claude does not execute financial transactions.** Everything up to a fully
   validated, risk-checked, idempotent order object can be built and tested;
   placing it through the user's authorized MCP is the user's to enable and
   operate. Recorded in the spec so phase 17 does not discover it.

Five open questions are listed at the end of that document. The sharpest:
autonomous execution of a strategy with no demonstrated edge automates the
losses, and nothing in this project has yet demonstrated one.

---

## Planned: the Strategy Lab

A major scope addition, fully specced in `docs/STRATEGY_LAB.md`. Summary:

An evolutionary search engine that generates random strategy configurations,
scores them against history on a risk-adjusted reward, keeps and mutates the
winners, and promotes survivors through a validation gauntlet before any real
money is involved.

Key design points (do not silently change these — they were deliberate):

- **Reward is risk-adjusted, not raw profit.** Raw P&L maximization reliably
  discovers strategies that make enormous concentrated bets.
- **The action space is open-ended rule synthesis** as of 2026-09-11, changed
  from parameter tuning with the user's explicit agreement. The search composes
  entry and exit rules from primitives and operators; risk parameters stay as
  tuned genes. Reversed because parameter tuning can only re-tune an idea that
  already loses money after costs, and because net-of-cost fitness now exists to
  make open search survivable. Complexity is penalised so trees cannot grow until
  they memorise history.
- **Score against the null, never against zero.** Buying at random and holding
  five days was profitable in every window this project tests on, because the
  market rose. Scoring against zero rewards being long in a bull market, not
  selection — it let 57% of random strategies pass validation. `benchmark.py`
  computes what chance earns per window; fitness and every gate measure excess
  over it. **Re-run `control.py --calibrate` after any change to fitness, the
  simulator or the gates.** A gate never tested against noise is an assumption.
- **The null is a surface over price and holding period, not a number.** Both
  dimensions were loopholes while flat, and the search found each immediately.
  Holding period: the null is +0.07% at 5 days and +2.1% at 45, so a fixed
  5-day null paid a long-holding strategy 30x for drift it did not earn.
  **Price: the null runs from +25.2% at $5-6 to -0.5% at $100+ over a 45-day
  hold** (2020-22), so a market-wide null handed anything that bought cheap
  stocks an enormous unearned excess. Each trade is charged the null of its own
  entry price, interpolated in log price between band centres — see the next
  item for what that cost. Bands are configured in `config.yaml` under
  `benchmark.price_band_edges`, deliberately fine below $20 where nearly all the
  variation sits.
- **Net P&L in dollars is the headline metric.** Not AUC, not win rate, not
  Sharpe. Those are diagnostics of *why*; money is the test of *whether*. Report
  it first, everywhere.
- **The sealed holdout period is sealed.** Each strategy may be evaluated
  against it exactly once, ever. No peeking for early stopping, ranking, or
  "just checking."
- **Trial count is recorded** so a deflated Sharpe ratio can be computed. Testing
  200k strategies inflates the winner's apparent skill; the correction matters.

New modules to build: `genome.py`, `simulator.py`, `reward.py`, `evolve.py`,
`ledger.py`, `promote.py`, `lab_dashboard.py`.

---

## Open decisions — do not assume answers

1. **Survivorship bias — now ENUMERATED, not just estimated (2026-09-12).**

   **Every backtest figure is still roughly 10 points a year optimistic**, but
   the hole is now a list rather than an average.

   - `delistings.py` holds the Alpha Vantage registry: **9,464 delisted
     listings, 7,480 of them common stock, and we hold prices for 418 (5.6%).
     7,062 companies a backtest here can never buy**, each with an exact
     delisting date. That independently corroborates the Internet Archive
     figure of 9,029 by a completely unrelated method.
   - **Thin before 2009** — the registry records 4 delistings for all of 2008 —
     so it does *not* cover the financial crisis, which sits inside the
     2006-2019 search window. Use EDGAR for that era.
   - `edgar_registry.py` builds a point-in-time company registry from the SEC
     quarterly indexes, **1993 to now**: 303,383 annual filings, 38,876
     distinct companies, **31,752 (82%) that stopped filing**. Coverage of
     10-K filers by our price data runs **14% in 1998, 26% in 2007, 50% in
     2019, 77% in 2025** — improving toward the present, which is the signature
     of survivorship bias rather than of better collection.
   - `bias_benchmark.py` still gives the headline 10.4 points/year against Ken
     French's CRSP-based series. Treat it as an upper bound; it also contains
     composition differences.
   - **Prices for the dead remain unavailable from any free source.**
     FirstRateData sells 16,302 tickers including 7,000+ delisted back to 2000,
     which matches the size of our hole almost exactly, and is the cheapest
     thing that would close it. CRSP via WRDS is the academic standard and free
     with a university affiliation.

   **A trap worth remembering.** Measuring the 418 delisted names we *do* hold
   suggests delisting is nearly harmless: median drawdown 20%, mean final-60-day
   return **+1.3%**. That is wrong, and the reason is the whole problem in
   miniature — those 418 are the delistings that survived the survivorship
   filter, because a clean acquisition keeps its price history and a bankruptcy
   does not. Never calibrate the failure case on that sample.

   **Drawdown as a proxy for death is real but weak.** 15% of all rows sit more
   than 30% below their 200-day high; 38% of rows at actual delisting do. A 2.5x
   enrichment. `bias_exposure.py` is an ordering, not a probability.

2. **Survivorship-bias data source — interim decision made, still needs work.**
   yfinance omits delisted companies, so the universe excludes every bankruptcy and
   acquisition since 1962. Decided 2026-09-08: collect now and accept the bias, with
   `source` recorded per row and the symbol directory snapshotted daily so the gap
   stops widening. **That is an interim position, not a fix.** A flat haircut cannot
   correct it either, because the bias is not uniform across strategies and the Lab
   preferentially discovers the ones that exploit it. Full reasoning and a costed
   research path — free Internet Archive reconstruction first, paid point-in-time
   data second — are the first section of `BACKLOG.md`.
3. **Arena provisioning** — confirm 100 GB datastore availability and identify
   the other VM's quiet hours for the overnight search window.
4. **Paper-trading duration and funding stake** — no concrete rule agreed yet.
   Note this sits awkwardly against the $100 account cap: the Strategy Lab's
   promotion ladder ends in "funded, small fixed stake", but the mandate above
   caps total exposure at $100. Either the cap rises when the Lab goes live, or
   the funded stake comes out of the same $100. Undecided.

---

## The price-filter result — 2026-09-12

**The Strategy Lab's first 66 "validation survivors" were an artifact of the
benchmark, and all 66 have been voided.** This is the clearest example so far of
the standing caution below, and worth reading before trusting any Lab output.

The search's best answers collapsed to five rule structures, 58 of them the same
idea with a different constant:

| Count | Rule shape |
|---:|---|
| 33 | `sma_200 < N` |
| 25 | `lag(sma_200, N) < N` |
| 8 | everything else |

The top five were `sma_200 < 7.05 / 7.83 / 8.27 / 8.59 / 8.59` — **"buy stocks
whose 200-day average price is under about $8."** A price filter, not a strategy.
They appeared at generations 2-5, barely evolved.

They scored well because they were benchmarked against the whole market while
trading only its cheapest corner. Re-scored against the null of the stocks they
actually bought (`rescore.py`), **0 of the top 25 still clear the gate**:

| | was | now |
|---|---|---|
| `sma_200 < 7.05` net P&L | +$26,166 | +$26,166 |
| its excess over the null | large | **-$585** |
| null charged (45d, ~$6.70 entry) | +2.46% | **+13.38%** |
| fitness | 0.387 | 0.000 |

Three things to take from it:

1. **Net P&L alone cannot tell you anything.** That strategy really did make
   $26k in the simulator. Every dollar of it was the benchmark.
2. **Cheap stocks are where survivorship bias is worst**, since the sub-$8 names
   that went to zero are absent from this database entirely. Bucketing does not
   fix that — it stops the search being *paid* for finding it.
3. **Fixing it in two stages was necessary.** Hard price bands alone were not
   enough: the search immediately moved to the bottom of the cheapest band
   (`sma_200 < 6.81`, entering at a median $6.64 against a band median of $7.59)
   and collected the within-band gradient instead. Interpolating across price,
   and extrapolating below the cheapest band rather than clamping, closed it.

`control.py` still rejects 60 of 60 random strategies after the change.

---

## The search converged on its own seed — 2026-09-22

**A result I reported as the project's most interesting finding, and then had to
retract within the hour.** It is the cleanest example of the standing caution
below, and the procedure that caught it is worth keeping.

After 1,022,905 cumulative trials the Lab produced **455 validation survivors
across 435 distinct structures** — the monoculture problem was genuinely fixed.
Reading what they *said* rather than how they were shaped:

| | |
|---|---:|
| contain a relative-strength `rank()` | 97% |
| contain an RSI oversold term | 81% |
| **contain both — momentum + pullback** | **85%** |
| **are crash buyers** | **0%** |

That looked like independent convergence, and it matched the best paper fund
(`MACD Pullback`, +2.00%) exactly. Two processes agreeing.

**They were not independent.** `seeds.py` contains a hand-written strategy,
`momentum_pullback`, whose entry is
`rank(roc_10) > 0.7 and price_above_sma200 > 0.5 and rsi_14 < 40`. `lab_loop.sh`
runs `evolve.py --seeds`, so that rule is injected into the population **every
iteration**. Of 455 survivors, **231 carry the literal constant 40** — not 39.8,
not 41.2, exactly 40. That is inheritance. And `MACD Pullback` is itself a
mutated descendant of the same seed, so the "corroboration" shared an ancestor.

The seed's own comment, written months earlier and then ignored:
*"The most 'designed' rule here, and so the most suspect."*

**What survives the retraction**, and it is much smaller:

- **Zero crash buyers out of 455 is real.** It is an absence, not a selection,
  and nothing seeds it. The exit-pricing and next-open-fill fixes killed that
  artifact for good.
- **~224 survivors use a LEARNED oversold threshold** (33.7, 32.9, 34.2) rather
  than the inherited 40. Evolution re-deriving something in that region without
  the constant handed to it is weak evidence for the shape.
- 48% carry a relative-strength `rank()` term at a threshold no seed supplies.

**What caught it**: `consensus.py` requires a term to appear in a MAJORITY of
survivors and writes the hypothesis to disk before scoring. Only one term
cleared the bar, and its interquartile range was `[40.0, 40.0]` — every survivor
using an identical constant is the signature of descent, not discovery. A lower
inclusion bar would have assembled a five-term rule and made it look like a
finding.

**The open question this leaves.** Re-run the search with seeds DISABLED and
compare. If momentum+pullback still dominates without the seed in the
population, it is real; if it evaporates, a week of results was our own
handwriting read back. `evolve.py` already takes `--seeds` as a flag, so the
work is tagging which runs were seeded and running both.

**The rule that generalises: when survivors agree on an exact constant, look for
where that constant came from before calling it a discovery.**

---

## Survivorship bias, measured per date — 2026-09-22

`pit_universe.py` answers "which securities could an investor have known about
on this date" from the 114 Internet Archive directory snapshots, and compares
that against what this database can actually price.

| date | knowable | priced | blind | coverage |
|---|---:|---:|---:|---:|
| 2008-06-30 | 3,000 | 679 | 2,321 | **22.6%** |
| 2012-06-29 | 2,487 | 831 | 1,656 | 33.4% |
| 2016-06-30 | 2,490 | 1,035 | 1,455 | 41.6% |
| 2020-06-30 | 2,568 | 1,436 | 1,132 | 55.9% |
| 2024-06-28 | 2,133 | 1,786 | 347 | **83.7%** |

**A backtest on 2008 data was looking at 22.6% of the real universe.** The
monotonic climb toward the present is the signature of the bias itself:
companies that survived keep their price history, companies that died do not.

This supersedes the ~10.4 points/year figure as the primary statement of the
problem. That number was an aggregate inferred against an external benchmark;
this is a direct per-date count of what was there against what we can see.

**`symbols.first_seen` is NOT a listing date.** It records when our own daily
snapshots first saw a ticker and ranges 2026-09-08 to 2026-09-21. The first
version of the point-in-time universe read it and returned zero knowable
securities for every historical date — an empty universe rather than an error,
which is the worst way for a data source to be wrong. The historical record
lives in `historical_listings`.

**Snapshots are sparse** — 114 over eighteen years — so a date between them uses
the most recent prior snapshot and `snapshot_lag_days` is reported with every
answer. A universe from a 144-day-old snapshot is a weaker claim than one from a
6-day-old snapshot, and callers are told which they have.

---

## The trial counter is append-only — 2026-09-22

```text
The cumulative trial count is append-only and is never reset, including when
strategies are archived or retired.
```

**Deleting records does not delete the contamination.** 1,037,005 evaluations
have already happened. Removing the rows would not un-run the searches; it would
destroy the denominator the deflated-Sharpe correction depends on, and the next
survivor would appear to have cleared a bar of one trial when it actually
cleared a bar of a million.

That is the file-drawer problem. Discarding failed experiments is not a fix for
multiple testing, it is multiple testing with the evidence removed.

So: **label, never delete.** The 284 survivors scored by the buggy simulator and
the 231 carrying the seed constant `40` are marked, not removed. Any future
rebuild or migration must carry the cumulative count forward, and a rebuilt
database starting from zero is a regression that a test should catch.

**What does start fresh is the SEARCH, not the records** — a seed-free run,
tagged, compared against the seeded distribution. Clean population, preserved
accounting.

---

## Search capacity is capped deliberately — 2026-09-12

**Do not add generations, population, or nightly evaluation budget.** The
`docs/STRATEGY_LAB.md` figure of 200,000 evaluations a night is obsolete and
should not be chased.

Four searches have now run. Every one found its result in the scoreboard rather
than in the market, and each fix revealed the next:

| Search | What it "found" | What it actually was |
|---|---|---|
| 1 | `sma_200 < 8` | a price filter, benchmarked against the whole market |
| 2 | one rule, 199 of 200 shortlist slots | monoculture; dedup compared text, not structure |
| 3 | 60 "distinct" entry rules | one rule with 60 dead branches; bloat as mutation armour |
| 4 | `pct_change(sma_200, 20) < -0.1` | buy the crash — 85% of entries in names this data has almost none of the failures for |

More search does not help because the binding constraint is not search. It is
that **5 tickers stopped trading in the whole 2006-2019 window against 9,029
companies the Internet Archive says existed.** A larger search over the same
data finds the same holes faster.

What to add instead, in order: forward paper-trading time (the only unbiased
measurement, and it accrues only in calendar time), then exposure diagnostics
like `bias_exposure.py`, then — if money is ever available — point-in-time
delisted prices at roughly $270/yr, which closes this permanently.

---

## Never version the database or its write-ahead log — 2026-09-12

`data/*.db`, `*.db-wal` and `*.db-shm` are gitignored, and must stay that way.

A tracked `-wal` is not just a large file in the repo. **`git checkout` rewrites
it underneath an open connection**, which is exactly how `market_data.db` was
corrupted: `git add -A` had swept the WAL in, and switching to a branch dropped a
stale write-ahead log onto a live 10 GB database.

Recovery worked by rebuilding into a fresh file, not repairing in place — `DROP
TABLE` cannot run on a corrupt table, because freeing its pages means walking the
tree that is broken. Prices, features, the Internet Archive snapshots, promotions
and every paper-trading run came through intact; `strategies` lost 6.3% and
`evaluations` 0.05%.

**Design note worth keeping:** `paper_runs` stores each strategy's genome inline
as JSON rather than referencing `strategies.id`. That denormalisation is why
every forward test survived a corruption that cost 5,767 strategy rows. Keep it.

---

## Long/inverse ETF switching — 2026-09-17. The mechanism works; it still loses.

**Hold whichever of a bull/bear ETF pair is rising.** The logic is sound and the
evidence supports the first half of it: switching beats the random-switch null
on every index pair tested.

| Pair | Switching | Buy & hold | vs null |
|---|---:|---:|---|
| S&P 1x (SPY/SH) | **+6.82%** | +13.27% | beats |
| S&P 2x (SSO/SDS) | **+10.63%** | +23.26% | beats |
| S&P 3x (SPXL/SPXS) | **+12.15%** | +31.69% | beats |
| Nasdaq 2x (QLD/QID) | **+12.50%** | +32.11% | beats |
| Energy 2x (ERX/ERY) | +2.29% | **-8.21%** | loses |

*(2010-2019, best method per pair, costs charged per switch, fills at next open.)*

**Three findings, in order of importance:**

1. **It loses to doing nothing.** SPY buy-and-hold made 13.27%/yr against
   switching's 6.82%. **`benchmark.py`'s random null was never enough here** —
   a strategy can beat coin-flipping comfortably and still be worse than sitting
   still, and in a rising market that is the common case. `pair_momentum.py`
   now carries buy-and-hold as a second, mandatory benchmark.

2. **It loses in the crash too, which kills the "it's insurance" defence.**
   Across 2020-2022 — COVID crash *and* the 2022 bear, precisely where going
   inverse should pay — S&P switching returned **-4.14% against buy-and-hold's
   +7.72%**. The mechanism is a V-shaped crash: a 120-day signal flips you into
   the inverse leg *after* the bottom, just in time for the recovery. Switching
   is insurance that pays out after the fire.

3. **Decay scales with leverage, as predicted.** Share of buy-and-hold captured:
   **51% at 1x, 46% at 2x, 38% at 3x.** A 2x daily-rebalanced fund loses money
   in a choppy market even when the index ends flat, so both legs bleed and
   every whipsaw is punished twice.

**Energy is the exception and it is not trustworthy.** Switching beat holding
ERX by 10 points in the bull window and 39 points through the crash — then
returned **-37.39%/yr since 2023** against buy-and-hold's +22.08%. Two wins and
a catastrophe is variance. The parameters were chosen on 2010-2019 and did not
generalise.

**Do not re-litigate ERX/ERY from scratch.** It has now been tested twice by
unrelated methods: `paired_etf.py` ran one pre-registered rule and closed FAIL;
`erx_momentum.py` searched 130 variants across five method families and every
one lost money on 2008-2019, the best at -2.2%/yr.

**The five funds were opened anyway**, at the user's explicit instruction and
with the above stated. That is a defensible call rather than a concession: the
forward record is the only measurement in this project with no survivorship bias
and no look-ahead, and a strategy nobody runs produces no evidence at all.

---

## Staleness was measured against the table being updated — fixed 2026-09-15

**The daily top-up asked "which tickers are behind `MAX(date)` in `prices`" —
the same table it exists to advance.** Circular. Level the universe at date D
and nothing is behind anything, so nothing is fetched and the database stops at
D permanently.

It never quite froze only because stragglers existed: a few tickers behind D got
fetched, their fetch returned bars past D, the max moved, and *the next morning*
everyone else finally looked stale. Measured on 2026-09-15: **12,769 tickers at
2026-09-11 against a max of 2026-09-14, SPY and AAPL among them, with 81 tickers
on the newest bar.** Features followed — 9,965 rows at 09-11 against 2 at 09-14.

So the scorer, the daily book and every paper run were working **a full session
behind, every single day, by construction** — and the pipeline reported success
throughout.

`backfill.last_market_session()` now asks the data source directly for the newest
**completed** session from a liquid ETF, and `stale_tickers` takes that as
`as_of`. Today's bar is excluded deliberately: asked during market hours the
source returns an in-progress bar, and treating it as the last session would
store 13,000 partial bars as closes.

**The general lesson, which has now cost this project three separate bugs:
never derive a freshness reference from the thing whose freshness is in
question.**

---

## A size floor, because price and volume cannot see size — 2026-09-14

The Lab and classifier paths bought **TNON**: a ~$3.5M company that had just
done a 1-for-35 reverse split to regain Nasdaq bid compliance, spiked ~70% on a
debt payoff, and cleared the $1M/day liquidity floor with **$102M/day of blowoff
volume**. It closed -29% four sessions later and was 67% of the Agentic
account's entire loss. A $3.5M company doing $100M/day is not liquidity.

**The obvious fix does not work.** TNON has no market cap in this database at
all, so "reject if below the floor" waves it through as *unmeasured*. An unknown
cap is therefore rejected too — the same rule `buffett.quality_score` already
applies to its own components: a missing measurement is not an average one.

Cost: of 3,042 names clearing the existing floors, 2,224 have a known cap and
**2,183 survive a $100M floor**. The 818 unknowns are not junk (median price
$30.74), they are issuers whose filings are unparsed here.

Scoped to the Lab and classifier paths only. The conviction screens rank within
size buckets already and require the fundamentals this derives from.

---

## Two functions shared one SQL line — 2026-09-15

Adding `include_open` to `load_training_frame` used a string replace on
`sql = (f"SELECT f.ticker, f.date, p.close, {cols} "`. **That exact line appears
in two functions.** `load_latest_features` got the `price_cols` reference too,
has no such variable, and raised `NameError` at runtime — killing the
paper-trading step and the classifier source in the daily book.

Same family as the `_load_panel` two-branch bug, inverted: that time one of two
was fixed, this time one of two was broken. **Edit near-identical SQL one
function at a time, and grep for the line before replacing it.**

---

## Fills happen on the NEXT bar — 2026-09-15. This one answers the project's question.

**Both engines bought at the close of the bar whose close produced the signal.**
Entry rules read `sma_200`, `rsi_14`, `close`; the simulator and the backtest
then filled at that same close, a price nobody can obtain until the session is
over. Exits had it too, which quietly made stops perfect: a stop detected at a
close was filled at that close, so the exit was booked at the very price that
breached it. CLAUDE.md has said for months that overnight gaps are unprotected
while the simulator assumed the opposite.

Fixed in `simulator.py`, `benchmark.py` (the null must match, or the comparison
is rigged — the second time that asymmetry has had to be closed) and
`backtest.py`. Signals fill at the next open; exits trigger on a close and fill
on the following open. `tests/test_fills.py` pins the semantics: one synthetic
trade goes from -$11.76 to **-$51.46** once the stop is allowed to gap.

### The measurement, controlled

Same model, same window (2022-07-20 -> 2026-09-11), same $20 x 5 config. **Only
the fill convention differs** — that is what `--fill close` exists for:

| | close fills | next-open fills |
|---|---:|---:|
| trades | 1,054 | 1,053 |
| **gross P&L** | **+$1.63** | **-$58.77** |
| gross per trade | +0.008% | **-0.279%** |
| trading costs | -$104.35 | -$104.29 |
| survivorship haircut | -$38.31 | -$38.27 |
| **net P&L** | **-$141.03** | **-$201.33** |
| win rate | 41.4% | 40.9% |

**The look-ahead was worth 0.287 points per trade.** Not the 0.7 estimated from
the older `baseline_top10` row — that comparison was contaminated, see below.

### Two findings, not one

1. **The signal does not survive costs, because there is no signal to survive
   them.** Gross is *negative* under honest fills. The strategy loses money
   before it pays a cent of spread. The question "does the edge survive costs"
   is answered, but not the way it was posed.

2. **The 0.43%/trade figure does not reproduce at 5 positions even WITH the
   look-ahead.** `baseline_top10` (2026-09-11) ran $10 x 10 and recorded gross
   +$90.31 over 2,109 trades = +0.428%/trade. The same model at $20 x 5 with the
   same close fills yields +0.008%/trade. **The top 5 names perform worse than
   the top 10** — a model whose ranking is not monotonic at its own top decile
   is evidence against the ranking being real, independent of fills.

**AUC 0.63 is not contradicted.** The classifier does rank better than chance;
31 of 31 walk-forward folds said so. It does not rank well enough to pay for
acting on it. Ranking skill and tradeable edge are different quantities and this
is the distance between them.

**Do not quote a per-trade return without stating its fill convention and
position count.** Both move it by more than the entire claimed edge.

---

## Size and liquidity in the fundamental screens — 2026-09-14

Two separate problems, found by asking why the daily book never recommends an
S&P 500 name. Neither was exclusion: large caps are in the universe and lose on
rank.

**1. The liquidity floor was missing from the conviction path.** `_load_panel`
filtered on `min_price` alone, so `min_dollar_volume` — the $1M/day floor the
scanner has enforced since the penny-stock result — never applied to any
fundamental screen. Only the classifier and Lab paths had it. It put **MXC at
the top of the daily book, agreed on by two systems, at $890k/day and a $15M
market cap**. Fixed; panel 2,674 -> 2,349 names. **If you add another screen,
apply both floors.**

**2. Value ranks were size ranks in disguise.** Measured on our own panel:

| metric | Spearman vs log market cap |
|---|---:|
| **book_to_market** | **-0.352** |
| earnings_yield | +0.185 |
| gross_profitability | -0.029 |
| beta | -0.026 |

B/M and EBIT/EV carry market cap in the denominator, and large companies hold
most of their worth in brand and goodwill no balance sheet records. So ranking
on B/M sorts toward small before it sorts toward cheap. Every value pick the
book made was in the bottom half by size, three of five in the bottom quartile,
from a universe whose median company is $3.1B.

**The tilt is not wrong in general and was not removed.** The size premium is
real and these screens are meant to lean small. It is wrong on *this* data:
microcaps are where the 7,062 missing delisted companies concentrate, so the
small-cap leg is the least trustworthy thing these screens do.

`conviction._rank(s, d)` now ranks within the row's size bucket. Two details
that are load-bearing:

- **Buckets are assigned within each review date, never pooled across dates.**
  The market roughly quadrupled over the backtest window, so pooled buckets
  would be a calendar variable — a company of unchanged real size would drift
  from "small" to "large" by doing nothing, and the late years would be almost
  entirely top-bucket.
- **Market cap is point-in-time.** `value_metrics._market_cap` multiplies shares
  taken *from the filing* by the price *on the filing date*. Never substitute a
  current share count: dilution is exactly what distressed companies do between
  then and now.

`buffett` was already the least affected screen — its quality and low-beta legs
pull against the value leg, and its top-10 median sat at the panel median while
the two pure value screens sat in the bottom quintile. The z-scores inside
`buffett.quality_score` are deliberately left global; their inputs correlate
-0.03 with size, so there is nothing to neutralise, and per-bucket z-scores
would thin each group until they stop meaning anything.

`daily_picks` takes at most one name per bucket, because neutral ranks still
permit three names from one corner on the days that corner holds the top
percentiles.

**Re-measured, and it helped.** `conviction_walkforward --all`, 15 rolling
2-year windows against SPY over the same dates:

| screen | was | now |
|---|---|---|
| deep_value | 6/15, -1.5% | **7/15, +0.8%** |
| quality_value | 4/15, -4.2% | **6/15, -3.6%** |
| buffett | 6/15 | 6/15, -3.7% |

Two of the three screens the book uses improved, none got worse. That is weak
evidence the small-cap tilt was costing these screens rather than paying them —
consistent with the tilt leaning on exactly the part of the sample where our
missing delistings concentrate.

**Do not read deep_value's +0.8% as an edge.** Its *median* window is -0.5%, so
a few windows carry the mean; the 15 windows overlap heavily and are nowhere
near independent; and 7 of 15 is a coin. The three screens the book does not
use remain poor — magic_formula 1/15, conservative 2/15, piotroski_value 3/15.

---

## The exit-pricing bug — 2026-09-12. Read this before trusting any old number.

**71% of the Lab's reported profit was a defect in its own simulator.**

`simulator.Panel` built its forward-price matrix by shifting within the
*filtered* panel. Tradeability floors decide what may be **bought**; they were
also deciding what an open position could be **sold** for. When a holding fell
below the $5 floor its rows left the frame, the forward price became NaN, and the
exit was booked at "the last price we have" — the last bar *above* the floor. A
company falling from $6 to $0.20 exited near $5.50 and its collapse never
happened.

Measured on the search's best strategy, 2006-2019:

| | filtered exits | true exits |
|---|---:|---:|
| net P&L | +26,065 | **+7,575** |
| mean trade return | 13.46% | **4.22%** |
| median trade return | 3.54% | **0.26%** |
| win rate | 60.7% | **49.2%** |

11.9% of its 20,000 trades had a truncated forward series; those returned -0.02%
against +15.29% for the rest.

**`benchmark.py` had the identical bug**, so the null was inflated the same way.
Both are fixed via `storage.load_exit_prices()`, and every `simulator.Panel`
construction in the project now passes unfiltered closes. **If you add another,
pass them.**

Three consequences worth holding on to:

1. **The crash-buying artifact was mostly this, not survivorship bias.** The
   search kept discovering "buy falling stocks" because the simulator refused to
   let falling stocks finish falling.
2. **The price gradient was partly this too.** The null for $5-6 names at a
   45-day hold fell from +6.19% to +3.85% once exits were priced honestly, so
   roughly half of "cheap stocks earn more" was truncation rather than a market
   fact.
3. **Noise lost its edge as well.** Random genomes beating the null fell from
   45% to 15%.

The same defect was found and fixed once before in the daily pipeline — see the
`storage.price_series` note. The Lab kept it for months. **A filter that decides
what you may buy must never decide what you may sell.**

---

## A standing caution

This system searches a large space of strategies against fixed historical data.
That process reliably produces strategies with excellent backtests that are pure
noise, and it gets worse the harder the search works. The validation ladder exists
specifically to catch these. Treat every backtest figure as an optimistic upper
bound, never as a forecast, and never weaken the validation protocol to make
results look better.
