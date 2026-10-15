# Intraday Momentum Runner: implementation plan for independent review

Prepared 2026-10-14 in response to `docs/ADDENDUM_G_INTRADAY_MOMENTUM_RUNNER.md` (the owner's prompt, entered verbatim).
**Status: PLAN ONLY. Nothing has been built, scheduled or armed.** The owner asked for the plan to go to the independent
reviewer before any implementation; every item below is *planned* unless marked *verified* (checked in the repository or
the database on 2026-10-14).

## Revision 2 (2026-10-15): independent review incorporated

The reviewer's comments are in `docs/INTRADAY_RUNNER_REVIEW_1.md` (verbatim). They approve the direction and ask for targeted changes, not a redesign. **Where this section differs from sections 0-10 below, this section governs.** Still plan only: nothing is built, scheduled or armed.

### R2.1 Disposition of every requested change

| # | reviewer request | disposition | where |
|---|---|---|---|
| 1 | resolve the validation timeline | accepted: 60 shadow + 20 untouched holdout + 20 paper; overlap rules stated | R2.3 |
| 2 | broker / account-rule verification before live | **accepted as a pre-live checklist; whether it is a hard gate is the owner's decision** (owner has instructed that the day-trade guard not be a blocker) | R2.2, decision D1 |
| 3 | quote quality and exit reliability as hard gates | accepted | R2.4 |
| 4 | simulator timing rules explicit | accepted | R2.5 |
| 5 | risk accounting: intended vs realised, unrealised, cooldown | accepted | R2.7 |
| 6 | net-edge sensitivity report | accepted | R2.8 |
| 7 | keep current holders during SHADOW/PAPER; owner approves any live reallocation | accepted (it was already the plan) | R2.9 |
| 8 | review `backtest_first` separately | accepted as a separate workstream; the owner set it live on 2026-10-14 and keeps that decision | R2.9, decision D2 |
| 9 | every stage produces a concrete deliverable | accepted | R2.11 |
| 10 | LIVE disabled by default | accepted (unchanged) | R2.4 |
| Q1-Q8 | answers to the plan's questions | adopted as the decisions of record | R2.12 |

### R2.2 Day-trade guard and account rules (conflict surfaced, not hidden)

The owner instructed on 2026-10-14 that the guard be removed and not be treated as a blocker; it is off (`enforce_day_trade_limit: false`, reversible). The reviewer cautions that removing a check on an unverified belief is not sound and asks for verification before LIVE. Both are recorded. **Proposed resolution, owner to decide (D1):** the guard stays off as instructed, and the following read-only checklist is completed and reported before the first LIVE order; it is recommended as a gate, but it is the owner's call whether it blocks.

P1. Read Robinhood's official documentation for this account type and record what it says on day trades, minimum equity, intraday margin, settlement and good-faith rules. P2. Read the account's displayed restrictions through the read-only account tools. P3. Keep software safety controls (our limits) separate from regulatory or broker restrictions in code and in the report. P4. Test, with a simulated broker, that a rejected order or an account restriction stops new intraday entries after the configured number of failures and raises an alert.

### R2.3 Timeline (corrected)

Three separate evidence requirements; assumptions: owner approves the collector job by 2026-10-16, collection starts Monday 2026-10-19, US market holidays observed (Thanksgiving, Christmas, New Year's Day, MLK Day, Presidents' Day).

| stage | length | calendar (approx.) | can overlap with |
|---|---|---|---|
| SHADOW assessment (initial research result) | 60 sessions | 2026-10-19 to 2027-01-13 | build milestones M2-M6 run during it |
| Untouched prospective holdout (rule frozen first) | 20 sessions | 2027-01-14 to 2027-02-11 | paper trading, operations only |
| PAPER with slot constraints | 20 sessions | strict sequence: 2027-02-12 to 2027-03-12; overlapped: concurrent with the holdout | the holdout, **only if** the paper results are not counted as statistical evidence (they share the market's realisation) and the service is ready by 2027-01-14 |
| Validation decision (M7) | | strict: about 2027-03-15 (~100 sessions); overlapped: about 2027-02-12 (~80 sessions) | |

An **initial research result** (after the 60 shadow sessions) is not a validation decision: only the holdout plus the operational paper record, evaluated against pre-registered criteria, can produce a continue / revise / stop decision. None of the three periods is shortened.

### R2.4 Hard gates for LIVE (all must hold; LIVE stays disabled by default and is never armed automatically)

G1. **Quote capability verified:** `get_equity_quotes` (or the chosen source) returns usable bid, ask and timestamps for equities, shown in a probe report; if not, SHADOW continues on conservative assumptions but no strategy is reported as passed on last-trade prices. G2. **Execution costs measured:** decision-price to fill difference, spread, slippage and rejected orders, with conservative estimates while samples are small. G3. **Historical data verified:** timestamps, missing bars, split adjustment and universe membership shown free of look-ahead and survivorship effects. G4. **Monitoring cadence proven:** measured quote latency, API response time and throttling under the intended load before 15-30 seconds is adopted. G5. **Exit reliability tested:** restart-and-reconciliation test passes (mandatory before any LIVE order), failed-exit escalation tested, service-health rule tested. G6. **Pre-live account-rule checklist (R2.2)** per decision D1. G7. **Pre-registered SHADOW, holdout and paper criteria met (R2.3, R2.8).** G8. **Owner's explicit approval** after the reallocation report (R2.9), `allow_intraday: true` and `intraday.stage: LIVE` set by the owner.

### R2.5 Simulator specification (explicit)

* **Event order inside a bar is unknown; the rule is conservative and fixed:** for a long position the bar's adverse extreme (low) is assumed to occur before its favourable extreme (high), unless the bar data establishes the order.
* **The entry bar's pre-entry high never moves the trailing stop.** The highest eligible price starts at the first price observable after the fill; bar highs count only for bars that begin after the fill time. A test pins this.
* **Latency:** signal observed at bar close `t`; order submitted at `t + L_submit`; fill at the first executable price at or after `t + L_submit + L_fill` (parameters measured in M1, conservative defaults until then: decision-to-fill delay of at least one full bar of data).
* **Prices:** entries fill at the ask side (quote when available, else last price plus half the modelled spread), exits at the bid side; slippage and fees applied; a stop trigger fills at the next executable price, never at the trigger, and a gap through the stop fills at the gap price.
* **Triggers and executions are stored separately** (`trigger_price`, `exec_price`, `trigger_time`, `exec_time`) and every report states returns on execution prices; the worked example (entry $100, high $103, 1 % trail, trigger $101.97) is reported as trigger 1.97 % and an actual execution-based return, which may differ (e.g. 1.90 % or 1.50 %).
* **Capital:** overlapping positions consume capital; rejected, delayed and partial orders are modelled with the rates measured in M1 and tested at higher rates.

### R2.6 Exit reliability (additions)

* **Service-health rule:** if reliable monitoring (fresh quotes for every open position and a successful heartbeat) cannot be restored within 30 seconds, new entries halt and an alert is raised; if it cannot be restored within 90 seconds, the position is exited at market through the engine; the kill switch overrides all of it.
* **Failed-exit escalation:** retry with the same idempotent ref_id after reconciling outstanding orders; never submit a second sell for an unconfirmed first; after the configured number of failures, escalate to the emergency flatten path and alert the owner by Telegram; an exit is never assumed to have succeeded without a confirmed fill or a reconciled flat position.
* **Broker-side protection investigation (M1 deliverable):** test, read-only and in review mode, whether a supported order type can protect a position independently of our service, including whole-share positions for lower-priced stocks; the finding goes into the M1 report; nothing is assumed to work with fractional-dollar positions.
* **Time handling:** forced flattening and all session logic use the US market calendar and America/New_York time, never a fixed UTC hour. The earlier "cron safety sweep at 19:50 UTC" is replaced by a sweep that runs at both 19:45 and 20:45 UTC and acts only when New York time is 15:45-15:55 on a trading day, with a daylight-saving test across both transitions and an early-close (13:00 ET) test.
* **Mandatory before any LIVE order:** a successful restart-and-reconciliation test with an open position.

### R2.7 Risk accounting (definitions)

* **`intraday_max_loss_per_trade_dollars` ($0.50 proposed) is intended stop risk**: it bounds the stop distance at entry. Reports show intended stop risk and **actual realised loss** side by side, with the excess (gap and slippage) reported as its own statistic.
* **Daily loss limit counts realised plus unrealised intraday P&L** ($2 proposed): crossing it halts new intraday entries and triggers exits of open intraday positions; in addition the existing account-level limits ($15 / 15 % daily, drawdown tiers 10 / 20 / 35 %) stay authoritative and are not weakened.
* **Re-entry:** after a stop-out the symbol is locked for the session (and the slot cools down for the configured minutes); a re-entry requires a new independently valid signal that also clears a higher threshold; every blocked and every allowed re-entry is logged and tested.

### R2.8 Pass criteria and net-edge reporting (clearer, not easier)

SHADOW and holdout reports state **signals and independent trading dates side by side**; uncertainty is a date-block bootstrap (observations on the same day are dependent); the configuration is frozen before the holdout; every configuration tried is in the experiment ledger; every control is reported (random entries with the same exits, simple momentum, no-trade, and the reversal counterpart), not only the winner. **Minimum economically meaningful net edge (proposal, reviewer to confirm):** mean net return per trade of at least 0.10 % at the measured round-trip cost, and still greater than zero at 2x the measured cost, with the date-block lower bound above zero; no threshold is lowered for the small account. Every report also shows net expectancy per trade, total net P&L, maximum drawdown, and the sensitivity to higher-than-measured costs; a strategy profitable only under optimistic execution has not passed.

### R2.9 Slots and backtest-first

* The five current holders stay through SHADOW and PAPER; no slot is reserved or reassigned for the Runner until LIVE. Slots 3 and 5 remain the recommendation, to be re-decided from the allocation on the day.
* **Before LIVE:** a reallocation report shows the proposed slot changes, current holdings, realised and unrealised P&L and the evidence behind each replacement; **selling existing positions to make room needs the owner's explicit approval.**
* **`backtest_first` review (separate workstream, own deliverable `reports/backtest_first_review.md`, not part of the Runner):** the owner set it live on 2026-10-14 and it stays unless the owner changes it. The review will compare, over the sessions since 2026-10-14, the forward results of the backtest-first holders with the previous allocation, the pool and random picks, restate the earlier finding that backtests ranked later returns weakly (rank correlation about +0.2 with 3 weeks of data), and propose pre-declared criteria under which the owner might revert (decision D2). The Runner does not depend on it and does not use `ranking.py`.

### R2.10 Goals and the entry-condition breakdown

Goal A (a working, safe intraday engine) is an engineering deliverable; Goal B (an intraday strategy that makes money net of costs, shown prospectively) is an empirical result. Passing A says nothing about B. The evaluation report breaks net performance down **by entry condition** and attributes it to **entry selection, exit management or both**: high-volume breakouts vs ordinary short-term momentum; relative strength vs the market; how extended entries are at detection; whether stops cut losers without cutting winners early; profitability after higher costs; and whether profits come from many dates or a few exceptional sessions.

### R2.11 Milestones, with acceptance and a concrete deliverable each

| # | work | acceptance | deliverable |
|---|---|---|---|
| M0 | finalise plan | review comments incorporated; scope and gates approved by the owner | this revised plan |
| M1 | data foundation | collector reliable; quote capability, latency, throttling and broker-side protection verified and reported; data-quality report clean | collector job, `intraday_universe`, M1 report |
| M2 | stops and simulator | stop, fill, gap, cost and failure tests pass; the R2.5 specification encoded and tested | `intraday_stops.py`, `intraday_sim.py`, stop test suite |
| M3 | scanner and SHADOW | signals and rejection reasons logged; no-look-ahead (truncation) tests pass | `intraday_momentum.py`, signal log |
| M4 | evaluation | walk-forward report with controls, all attempted configurations, net results, uncertainty, entry-condition breakdown | `intraday_eval.py`, first report (exploratory until 60 sessions) |
| M5 | integration | existing trading behaviour intact; new risk controls and slot isolation pass regression tests | branch, tests, shadow allocation report, **owner merge** |
| M6 | service and PAPER | service survives restart, handles failures safely, completes the required paper period | `intraday_runner.py`, systemd unit, paper report |
| M7 | validation decision | pre-registered criteria decide continue / revise / stop | decision report |
| M8 | LIVE-micro | a separate explicit owner decision after reviewing the evidence and the G1-G8 checklist | owner |

### R2.12 Reviewer answers adopted as decisions of record

Q1 keep the pass criteria, defined more clearly (R2.8). Q2 SHADOW logs every qualifying signal, kept separate from paper/live trades, with same-day correlation handled by date-based statistics. Q3 reversal is tracked as a control. Q4 the risk limits are starting values, now with the R2.7 definitions. Q5 free one-minute data for research; not sufficient for live approval by itself; no paid source until a specific limitation is identified. Q6 15-30 s polling only after G4. Q7 holders keep their slots during SHADOW/PAPER; fresh allocation review before LIVE. Q8 `backtest_first` is not treated as validated; reviewed separately (R2.9).

### R2.13 Decisions needed from the owner

D1. Is the pre-live account-rule checklist (R2.2) a hard gate for LIVE (reviewer and Claude recommend yes) or informational (owner's earlier instruction)? D2. Keep `backtest_first` on while its separate review is produced (current state), or switch back to `blend` until then? D3. Approve M1 (the daily collector job, the quote and latency probes) so collection can start; every session not collected now is unrecoverable and moves every date in R2.3. D4. Approve the minimum net edge in R2.8.

## 0. Summary

| | |
|---|---|
| What | A dedicated intraday long-only momentum strategy, with its own scanner, entry model, stops and exits, running in **two of the five live slots** once it has earned it |
| What it is not | A re-ranking of the medium-term strategies, a dashboard, or another research programme |
| First milestone | Working scanner + explicit entry/exit model + realistic simulator + SHADOW and paper report (no live orders) |
| Honest prior | Low. The existing same-day SHADOW set (288 trades, 6 rules, 12 sessions) nets **−0.05 % per trade**; its three momentum-type rules are negative (−0.31 %, −0.17 %, −0.14 %), the two reversion rules slightly positive on small samples. Retail intraday momentum rarely survives costs. The plan is built so that a negative result is found quickly and cheaply |
| Money at stake | Two slots x $20-25 = at most ~$50 deployed. A good strategy would make cents a day; the value of running it is **evidence**, not profit. Scaling is a later, separate owner decision |
| Earliest honest verdict | An initial research result about 60 sessions after the widened collector starts (about 2027-01-13 if collection starts 2026-10-19); the validation decision needs the holdout and paper period as well (about 80-100 sessions, R2.3). Free 1-minute history is ~1 week, ours is 18 sessions for 20 names, so no credible backtest can exist sooner. The plan says so rather than substituting a flattering short backtest |
| Gates before any live use | (1) the pre-registered SHADOW and paper criteria; (2) the owner's explicit approval to arm. **The day-trade guard is not a blocker:** on 2026-10-14 the owner removed it (`enforce_day_trade_limit: false` in `config/risk.yaml`, switch added to `account_rules.py`) |

## 1. Owner answers and assumptions

1. **Day trades.** Owner states Robinhood dropped the 3-per-5-days / $25k pattern-day-trader limit on 2026-06-04 (FINRA intraday margin standards) and, on the same day (2026-10-14), instructed that our guard be removed. Done: `account_rules.py` now honours `enforce_day_trade_limit`, and `config/risk.yaml` sets it to `false` (the day-trade count is still recorded; `true` restores the old behaviour). Claude has not independently confirmed the broker's current rule; the broker remains the final authority and will reject anything it does not allow, which the order-failure handling in section 3.6 covers. See 3.8.
2. **Data.** Free only to start: widen our own 1-minute collector. No paid source, no new account, no credentials.
3. **Slots.** Choose the two slots from the current allocation; recommendation in section 6.
4. **Polling.** A resident service during market hours is allowed.

## 2. What the repository actually does today (Phase 1 inspection)

All *verified* on 2026-10-14 by reading code and querying the database.

| area | finding | consequence for the Runner |
|---|---|---|
| Selection to order | `ranking.py` scores strategies; `slots.py` assigns five slots; `slot_trader.py` (cron, LIVE at minutes 4-59/5, 13:00-20:59 UTC) evaluates daily-bar signals, then `ExecutionEngine` -> `RiskEngine` -> `LiveBroker` (review, place, confirm; ref_id idempotency) | Reuse `ExecutionEngine`, `RiskEngine`, `LiveBroker`, the kill switch and reconciliation unchanged |
| Cadence | One pass per 5 minutes; `monitor()` reads one quote per open position per pass | Too coarse for a 1 % trailing stop; needs a resident loop (approved) |
| Quotes | `RobinhoodQuotes.get` returns `last_trade_price` only (no bid/ask), staleness limit **300 s**; `LiveQuotes` (yfinance 1-minute, delayed) limit 900 s | Intraday needs bid/ask (to be probed), a 15-20 s freshness limit, batch quotes. The crypto path already reads bid/ask from `get_crypto_quotes`; whether `get_equity_quotes` returns them is **unverified** |
| Orders | Dollar-amount orders are market-only and regular-hours-only; stops cannot rest at the broker for fractional dollar orders (project mandate) | Stops are software-monitored and exit as market orders, with slippage and gap risk. A whole-share route (price <= ~$25) might allow broker-resting stops: **unverified**, a probe item |
| Stops | `stop_plans.py` has fixed %, ATR, volatility, `trailing_pct` (0.5-50 %) and `trailing_atr` with `high_since_entry`, but built for daily ATR and 5-minute polling | Reuse the plan/validate vocabulary; add a 1-minute-ATR and a monotone trailing-state implementation |
| Costs | `costs.py`: spread estimated from daily dollar-volume tiers, slippage 0.05 % per side; "we hold no quote data" | Not good enough for 5-30 minute trades; needs a measured spread model |
| Risk limits | `config/risk.yaml`: $25 per order and symbol, 10 orders a day, 2 per symbol per day (one round trip per symbol), $15 / 15 % daily loss, drawdown tiers 10/20/35 %, min price $5, `allow_*` switches | Intraday limits go in `risk.yaml` and `risk_engine.py` (a strategy edit must not widen a risk limit); new `allow_intraday` switch, default false |
| Day-trade guard | `account_rules.py` blocked the 4th buy in 5 sessions on margin-type accounts | Removed by the owner 2026-10-14 (switch `enforce_day_trade_limit: false`); not a blocker |
| Same-day engine | `intraday.py` is SHADOW-only by design (B8): 6 rules, `intraday_signals` 41,697 rows, `intraday_trades` 288 closed shadow trades over 12 sessions | Reuse its feature vocabulary (vwap, pct_from_open, ret_15m, range) and its results as the first baseline |
| Intraday history | `minute_bars`: **20 tickers, 140,352 bars, 18 sessions** (2026-09-17 to 10-12), raw/unadjusted, collected after the close | Far too thin to validate anything; the collector must widen now because every missing day is unrecoverable |
| Paper/backtest | Daily-bar engines (`simulator.py` next-open fills; `paper_trading.py` daily). No intraday simulator | A minute-bar event simulator is new code |
| Ledgers | `slot_trades` (LIVE/SHADOW/SIMULATION rows with slot, strategy key, price, ATR, stop plan, reason), `orders`, `slot_marks`, `live_equity` | Intraday trades use the same tables with strategy key `intraday:momentum_runner` so reconciliation and the account P&L keep working |
| Medium-term loop | `slot_trader.trade()` buys the most liquid candidate for a slot and holds until a daily exit/stop; "slot released" sells at the open | Intraday slots must be invisible to this path (section 3.1) or intraday positions would be treated as multi-day holdings, the failure the owner described |
| Current selection | `ranking.evidence_mode: backtest_first` set in `config.yaml` 2026-10-14 (uncommitted at time of writing) | Independent of the Runner; see section 6 and section 9 |

## 3. Design

### 3.1 Architecture and slot integration

New code is a thin layer over existing parts: one scanner/decision module, one stop module, one event simulator, one service loop. **No second broker, risk engine, position ledger or execution path.**

* **Reserved slots.** `config.yaml: slots.intraday_slots: []` (empty = feature off). Slots listed there are excluded from the ranking-based assignment in `slots.plan` (so the medium-term machinery sees `count - len(intraday_slots)` slots) and are held by the strategy key `intraday:momentum_runner` v1. `slot_trader.trade()` and `monitor()` skip any slot whose holder key starts with `intraday:`, except the emergency flatten and an end-of-session safety sweep (3.6), which cover every open position.
* **Stage gate.** `intraday.stage: OFF | SHADOW | PAPER | LIVE`. Until LIVE, the reserved slots keep their current medium-term holders; the Runner trades only in the `intraday_*` shadow/paper tables. LIVE additionally requires `allow_intraday: true` in `config/risk.yaml` (owner) and the owner's explicit approval.
* **Service.** `intraday_runner.py --serve` as a systemd user unit during market hours (flock-guarded single instance): scan the universe every N seconds while a slot is flat; poll only open positions every 15-30 s; every loop checks the kill switch, data freshness and reconciliation state; writes a heartbeat to `trader_runs`.
* **Execution.** Entries and exits are `Signal`s through `ExecutionEngine.execute(...)` (so the risk engine, duplicate check, idempotent ref_id, order state machine and reconcile all apply), recorded with the existing `_record_trade`.
* **Accounting.** A new fund kind `intraday` in `accounting.py` / league so the Runner has a stable identity, versioned definition and its own forward record, never merged with other slots' P&L.

### 3.2 Data

| item | plan |
|---|---|
| Universe | Top ~200 US common stocks by 20-day dollar volume (>= $50M/day), price >= $5, market cap >= $2B; frozen list stored per date (`intraday_universe`) so tests are point-in-time; refreshed weekly |
| Collector | Widen `minute_bars.py` from 20 to ~200 tickers, daily after the close from the free 1-minute source (about 5-7 sessions of backfill on the first run); log gaps and bad bars; raw bars as now |
| Live snapshots | During SHADOW/PAPER the service stores bid/ask/last for the universe at a modest cadence (batch quote calls, rate budget) to build a **measured** spread model; first a one-off probe of what `get_equity_quotes` returns for bid/ask |
| Quality | Per-session coverage and gap report; sessions failing it are excluded from tests, not patched |
| Depth | 18 sessions now. Verdict windows: >= 40 sessions exploratory walk-forward, >= 60 first verdict, then a 20-session untouched prospective holdout. A paid history source is a later option: price, coverage and licence reported first, owner buys |

### 3.3 Scanner and features (module `intraday_momentum.py`, features in `intraday_features.py`)

Features at decision time `t` (1-minute bars, nothing after `t`):

1. relative strength vs SPY and vs the sector ETF over 5/15/30 minutes; 2. short-term return and its acceleration; 3. volume vs the same time-of-day median (20-session profile, built from the collector); 4. distance above the opening range high / prior N-bar high (breakout with a volume condition); 5. position vs VWAP and VWAP slope, higher-low structure; 6. realised 1-minute volatility and range used so far relative to the stock's typical daily range (extension); 7. estimated spread and cost, liquidity; 8. market state: SPY trend and realised volatility, breadth of the universe up vs down.

Hard filters (reject with a logged reason): spread or cost above a cap, extension above a cap, below VWAP or trend level, adverse reversal in the last bars, expected net move below the cost floor, stale or missing data, entry window (no entries in the first N minutes after the open or the last M before the close), a stop-out cooldown.

### 3.4 Entry model

* **v0 (pre-declared, transparent):** fixed-sign, z-scored feature score; thresholds set once from the exploratory window and written to the experiment registry before the verdict window is looked at.
* **v1 (only if data supports it):** expected net return and probability of a favourable move per horizon estimated from the empirical conditional distribution of forward 5/15/30-minute outcomes in score bins (walk-forward, no future rows), including the **actual stop policy simulated on the bars** so expected adverse movement and reward/risk are measured, not assumed.
* Output per candidate: expected gross and net return, P(favourable), expected adverse excursion, reward/risk, spread/liquidity penalty, freshness, confidence, accept/reject reason.
* Ranking: expected net return divided by expected downside (risk-adjusted net opportunity). **No quota:** zero, one or two entries a day is a valid outcome.
* **Multiplicity:** the entire search space is fixed in advance (<= 12 configurations: 3 horizons x 2 score thresholds x 2 stop modes), every configuration tried is added to a trial ledger, and the chosen one is reported with a max-T / Holm adjustment across all of them, never as the maximum of the grid.
* **Controls reported beside every result:** random entries at the same times with the same exits and holding limits; a simple momentum baseline (top short-term return, no other conditions); no-trade (zero). Also reported: the reversal counterpart, because the existing shadow set suggests the sign may be opposite on this universe; if reversal beats momentum the reviewer should know, even though the product is momentum.

### 3.5 Stops and exits (`intraday_stops.py`, pure functions)

* State per position: entry price, highest eligible price since entry (bar highs only after the entry time), trailing stop = `highest * (1 - pct)` (or `highest - k * ATR1m`), **monotone non-decreasing**, plus the initial stop (percentage or ATR) and the maximum-loss-per-trade cap.
* Stop modes compared honestly: percentage (grid 0.5-2 %), 1-minute-ATR multiple, and a fixed-time-stop variant. No single stop is assumed right; the sensitivity table is part of the report.
* Exit reasons: initial stop, trailing stop, momentum deterioration (price below VWAP with falling slope for M bars, or relative strength turning negative), thesis failure (breakout level lost), maximum holding time, end-of-session flatten (default 15:45 ET, hard sweep 15:55 ET), account-level risk (kill switch, daily loss, drawdown tier).
* Intraday means flat by the close. No automatic carry-over after a failed signal; any overnight policy would be a separate, explicitly configured and tested policy (none planned).
* Fill honesty: in simulation, within a bar the adverse extreme is assumed first; a gap through the stop fills at the open or the next available price, never at the stop; the stop price is reported as a trigger, not an execution price.

### 3.6 Failure handling

| failure | handling |
|---|---|
| stale or missing quote | no new entries; open positions: if no good quote for 30 s, attempt exit at market; at 90 s alert; kill-switch path available |
| data outage / API throttle (HTTP 429) | per-loop call budget; back off; single-symbol fallback; never loop faster than the budget; log every throttle |
| gap through stop / fast decline between polls | exit at the next available quote; gap loss recorded as its own statistic |
| rejected exit | retry with backoff, then escalate to the emergency flatten path and alert; never silently hold |
| partial fill | track remaining quantity in the ledger; the manager keeps managing the remainder with the same stop state |
| restart with open position | state persisted on every update (`intraday_state`); on start, reconcile with the broker, rebuild the highest price from stored minute bars since entry, resume |
| duplicate instance / duplicate order | flock + deterministic ref_id (existing idempotency) |
| near/after close | flatten at 15:45 ET; a New-York-time safety sweep (R2.6, daylight-saving safe) closes any `intraday:` position still open; alert if it ever fires |
| reconciliation mismatch | existing behaviour: halt trading, alert |

### 3.7 Risk limits (new keys in `config/risk.yaml`, enforced in `risk_engine.py`, entries only; branch + owner merge)

`allow_intraday` (false), `intraday_max_position_dollars`, `intraday_max_loss_per_trade_dollars` (bounds the stop distance), `intraday_max_daily_realized_loss_dollars`, `intraday_max_entries_per_session`, `intraday_max_simultaneous`, `intraday_max_correlated_positions`, `intraday_max_quote_age_seconds`, `intraday_max_order_failures`. Existing limits stay authoritative and are not weakened: $25 per order, 10 orders and 2 per symbol per day, $15 daily loss, drawdown tiers, kill switch. Starting values are set conservatively in the plan review (proposal: $20 position, $0.50 loss per trade, $2 intraday daily loss, 3 entries, 2 simultaneous).

### 3.8 The day-trade rule: removed by the owner (2026-10-14)

1. **Done:** the 3-per-5-sessions guard is switched off by the owner's instruction: `account_rules.check_buy` skips it when `enforce_day_trade_limit` is false (set false in `config/risk.yaml`); a regression test pins the switch, the default-true behaviour and that the settled-funds rule and every other risk limit are untouched.
2. **What stays:** any rule the broker itself applies. If Robinhood's intraday margin requirement or a restriction rejects an order, the order fails and is handled as any rejected order (no retry loop, recorded, reconciled, intraday entries halted after the configured number of failures). The first live-micro sessions log every broker rejection reason so a hidden requirement shows up immediately.
3. **Not a blocker.** It is no longer listed as a gate. (The reviewer may still want a one-line confirmation of the broker's current rule in their notes.)

### 3.9 Evaluation and success criteria (pre-registered in `experiment_registry` before the verdict window)

* **SHADOW** (all qualifying signals logged each day with modelled fills including spread and slippage, not constrained by slots, so evidence accrues faster than two slots could trade): after >= 60 sessions and >= 300 signals on >= 40 dates, pass requires mean net per signal > 0 with a date-block bootstrap lower bound > 0, above the random-entry control by more than the cost, above the simple momentum baseline, with the configuration chosen after the multiplicity adjustment.
* **Prospective holdout:** the next 20 sessions, rule frozen, one look.
* **PAPER with slot constraints** (two slots, capital, entry cap, cooldowns, rejected and partial orders): >= 20 sessions, same criteria plus realised stop statistics.
* **LIVE-micro:** only after the owner's explicit approval; two slots, $20 each, the new limits; judged by the same net-of-cost criteria.
* **Kill criteria:** SHADOW 60-session mean net <= 0, or lower bound below a stated floor, or the control beats the strategy: stop, write up, release the two slots back to the medium-term machinery. The reviewer is asked to confirm these thresholds.
* **Reported for every configuration:** win rate, mean and median net per trade, gross P&L, costs, net P&L, maximum adverse and favourable excursion, average holding time, stop-trigger frequency, gap-through-stop losses, maximum drawdown, trades and independent trading dates.

## 4. Test plan

* **Stop suite** (`tests/regression/test_intraday_stops.py`, deterministic bars and a fake broker): steady rise; sharp rise then retrace; immediate fall after entry; rise then gap below the trailing stop; oscillation around the stop; delayed quote updates; broker rejects the exit; partial fill leaves a position; restart with an open position; open near the close. Plus the monotonic property (the trailing stop never decreases) and the worked example (enter $100, high $103, 1 % trail: stop $101.97).
* Scanner/feature tests: no future bars used (truncation test: features at `t` identical when bars after `t` are removed), time-of-day volume profile correct, filters reject for the logged reason.
* Simulator tests: adverse-first within a bar, gap fills, spread and slippage applied, overlapping positions consume capital, partial and rejected orders.
* Integration: reserved slots invisible to `slot_trader`; emergency flatten covers intraday positions; reconcile with the ledger; risk-engine entry limits.
* Full regression suite before any deployment proposal.

## 5. Delivery plan (milestones with gates)

| # | milestone | contents | gate |
|---|---|---|---|
| M0 | Plan review | this document, reviewer feedback, owner approval | approval |
| M1 | Data foundation | widen collector to ~200 names (scheduled job, owner-approved), universe table, coverage report, equity bid/ask probe, spread snapshot logger | collector running, coverage report clean |
| M2 | Stops and simulator | `intraday_stops.py`, `intraday_sim.py`, cost model from measured spreads, the stop test suite | all stop tests pass |
| M3 | Scanner and entry model v0 | `intraday_momentum.py`, features, candidate log with reasons, SHADOW signal logger with controls | signals logging daily; truncation test passes |
| M4 | Evaluation harness | walk-forward and controls report (`intraday_eval.py`), trial ledger, registry spec | report runs on the data available (exploratory only until 40-60 sessions) |
| M5 | Slot integration (shadow) | reserved-slot config, `slot_trader` skip logic, risk-limit keys on a branch, shadow allocation report | branch tests pass; **owner merge** |
| M6 | Service + paper | `intraday_runner.py --serve`, systemd unit, paper trading with slot constraints | 20 paper sessions, no unreconciled state |
| M7 | Verdict | pre-registered SHADOW/holdout/paper criteria | continue / stop |
| M8 | LIVE-micro | only on the owner's explicit approval after M7 | owner |

New files (planned): `intraday_momentum.py`, `intraday_features.py`, `intraday_stops.py`, `intraday_sim.py`, `intraday_runner.py`, `intraday_eval.py`, `intraday_universe.py`, tests for each, a systemd unit template, `docs/INTRADAY_RUNNER_REPORT.md`. Modified (planned): `minute_bars.py` (universe), `quotes.py` (batch/bid-ask, freshness), `slots.py` and `slot_trader.py` (reserved slots), `risk_engine.py` and `config/risk.yaml` (limits), `accounting.py` (fund kind), `backup.py` (new tables), `daily.sh` (collector/reports), `config.yaml`. New tables (planned, all append-only and in the backup): `intraday_universe`, `intraday_candidates`, `intraday_state`, `intraday_events`, `intraday_experiments`.

## 6. Which two slots

The owner asked that the choice follow the current allocation. After the 07:00 UTC reassessment on 2026-10-14 (if `backtest_first` stays on) the slot backtest evidence is expected to be: R&D valuation +4.05 %, cash-flow/accruals quality +2.34 %, earnings-surprise (hold 60) +1.52 %, price-and-earnings momentum +1.39 %, and the kept uptrend-pullback (INTC) +0.46 %. Three observations: the intraday Runner should displace the weakest, most short-horizon holders; the stocks selected by the backtest-first rule are medium-term (hold 40-60 sessions) and are the ones the owner wants to keep as the value/quality leg; and slot ids are stable labels, not rankings.

**Recommendation: reserve slots 3 and 5** (the lowest backtest evidence after the reassessment: uptrend-pullback and the momentum reproduction), keep slots 1, 2 and 4 on the backtest-first medium-term strategies. This is a recommendation, not a decision: the shadow allocation report (M5) will list, for the actual allocation on the day, which positions would be retained, exited or replaced and why, and the owner confirms the two slots then. If the owner prefers the prompt's "four short-horizon slots, one medium-term" structure, the config supports any number of reserved slots; the owner asked for two.

## 7. Honest expectations and risks

* **Prior:** unfavourable. The only intraday evidence we hold is 288 shadow trades; momentum-type rules were negative. Daily-bar strategies in this project produced positive-looking backtests and negative forward results; intraday adds higher turnover against every cost.
* **Cost wall:** with $20 positions the dollar P&L of a 1 % move is $0.20. A round trip's spread, slippage and market-order fill noise must be small against the expected 5-30 minute move. Live fills so far: +0.03 % mean adverse versus the decision quote (28 orders, worst 0.26 %), +0.39 % / +0.45 % adverse versus the session open on entries/exits with standard errors of 0.60 / 0.33: too few to settle the cost model; M1 builds the measured one.
* **Stops are triggers, not guarantees:** software stops exit by market order; gaps and fast drops fill below the stop.
* **Statistical power:** two slots produce at most a few trades a day; the SHADOW design (log every qualifying signal) is how evidence is gathered at a useful rate. Signals on the same day are correlated, so the sample is the number of dates.
* **Cannot be bought out of:** history. The honest first verdict is ~60 sessions away.
* **Scope risk:** the reviewer asked that this not become a sprawling research project. The plan is deliberately bounded: one strategy, <= 12 configurations, fixed evaluation, explicit kill criteria.
* **Live-code risk:** changes to `slots.py`, `slot_trader.py`, `risk_engine.py`, `account_rules.py` are live-path edits; per project practice they go on a worktree branch with tests and the owner merges.

## 8. Items that need the owner

1. Approval of this plan after the reviewer's comments.
2. The scheduled collector widening (daily job) and the resident service (systemd user unit).
3. Merging the live-path branch (reserved slots, risk limits, `account_rules.py`).
4. The two slots, confirmed from the shadow allocation report.
5. `allow_intraday: true`, `intraday.stage: LIVE`, and any change to capital: never automatic.

## 9. Interaction with the other open changes

* **Backtest-first selection** (`ranking.evidence_mode`, `config.yaml`, 2026-10-14) applies to the medium-term slots only. The reviewer's note that those assignments rest on backtests despite the audit finding no established edge is a fair concern about that change, not about the Runner; the Runner does not use `ranking.py`. The reviewer is asked to comment on whether the backtest-first switch should stay while the intraday work proceeds. It also means the 07:00 UTC reassessment will sell WDC, CRS, AMD and FDX at the next open and buy four new positions.
* **Audit conclusions** (`docs/AUDIT_F_FINAL_REPORT.md`) apply: nothing here is evidence of an edge until the pre-registered criteria are met.

## 10. Questions for the reviewer (answered 2026-10-15; the answers are adopted in R2.12)

1. Is the pre-registered pass rule (>= 60 sessions, >= 300 signals on >= 40 dates, date-block lower bound > 0, beats random and momentum controls after a max-T adjustment across <= 12 configurations) strong enough, or too strict for a two-slot, $20-per-position experiment?
2. Is logging **every** qualifying signal in SHADOW (not just what two slots could trade) a sound way to gather evidence, given the correlation of same-day signals?
3. Should the reversal counterpart be tracked as a control, given the existing shadow evidence that reversion rules did better than continuation rules?
4. Are the kill criteria and the proposed risk limits ($20 position, $0.50 loss per trade, $2 intraday daily loss, 3 entries, 2 simultaneous) appropriate?
5. Is 1-minute free-source history, collected from now, an acceptable basis for a verdict in ~60 sessions, or should a paid source be evaluated in parallel?
6. Is a resident polling service at 15-30 s acceptable given the earlier throttling (HTTP 429), or should the plan be limited to the 5-minute cron cadence?
7. Is reserving slots 3 and 5 reasonable, and should the medium-term machinery lose two slots while the Runner is only in SHADOW/PAPER (my plan: it does not; the slots stay with their medium-term holders until the Runner reaches LIVE)?
8. Does the reviewer agree the backtest-first switch should remain in place during this work?
