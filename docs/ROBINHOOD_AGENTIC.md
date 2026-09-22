# Robinhood Agentic Autonomous Trading System — build specification

**Status: PLANNED. Nothing in this document is implemented.** Added to the plan
2026-09-22 at the user's direction, explicitly as a specification only.

Target architecture:

```
 quantitative strategy -> signal -> risk engine -> order validation
   -> Robinhood Trading MCP -> Agentic account -> execution
   -> reconciliation -> performance analysis -> strategy improvement
```

The MCP endpoint is Robinhood's official one,
`https://agent.robinhood.com/mcp/trading`, registered in Claude Code with
`claude mcp add robinhood-trading --transport http <endpoint>`. No unofficial
Robinhood API, and no browser automation where the official MCP can do the job.

---

## Read this before starting: most of this already exists

The specification is written as a greenfield build. **Stockbot2000 is not
greenfield**, and roughly half of the 25 phases describe components that are
already built, tested and running in production. Building
`robinhood_trading_system/` as a fresh tree would fork the project into two
half-systems sharing one database.

The first real engineering decision is therefore **not** "how do we build this"
but "what do we reuse". Mapping, honestly:

| Spec phase | Status here | Module |
|---|---|---|
| 0 Environment audit | **Done** — OS, Python 3.12 venv, git, no Docker, 8.5 GB DB | CLAUDE.md |
| 1 MCP connectivity | **Partly** — read-only Robinhood MCP works today | account/positions/quotes/orders all read |
| 2 Simulation mode | **Done, 21 funds running** | `paper_trading.py`, `pair_funds.py` |
| 3 Signal format | **Partly** — `picks` rows and `orders_today.json` are the de-facto schema | `daily_picks.py`, `orders.py` |
| 4 Risk engine | **Partly** — limits exist but are scattered across `config.yaml` | needs consolidating into one validator |
| 5 Kill switch | **Partly** — `STOP_LAB` halts the search; nothing halts trading | to build |
| 6 Execution engine | **Not built** — this is the actual new work | — |
| 7 Order state machine | **Not built** | — |
| 8 Reconciliation | **Done** for entries | `orders.py --record-fills`, `--reconcile` |
| 9 Database | **Done** — 25 tables, every table already audited | `storage.py` |
| 10 Logging | **Partly** — structured but not JSON, not split by stream | to restructure |
| 11 Strategy plugins | **Done in substance** — 5 screens, genome rules, classifier | `daily_picks.gather()` |
| 12 ML integration | **Done** | `train_model.py`, `walk_forward.py` |
| 13 External data | **Done** — yfinance, SEC EDGAR, Alpha Vantage, Ken French | `storage.py` and friends |
| 14 Backtesting | **Done, and hard-won** | `backtest.py`, `simulator.py` |
| 15 Walk-forward | **Done** — 31 folds, 7.6M OOS predictions | `walk_forward.py` |
| 16 Shadow mode | **Done** — that is what the 21 paper funds are | — |
| 17 Live mode | **Not built** | — |
| 18 Claude role | **Matches current practice** | — |
| 19 Scheduler | **Done** — cron: `daily.sh` 07:00, watchdog every 15 min | `daily.sh`, `lab_watchdog.sh` |
| 20 Recovery | **Partly** — jobs are resumable; no order-state recovery | — |
| 21 Dashboard | **Partly** | `monitor.py`, `fund_report.py` |
| 22 Alerting | **Done** | `notify.py` + Telegram |
| 23 Security | **Done** — secrets in `~/.telegram`, `~/.alphavantage_key`, 0600, never in repo | — |
| 24 Test suite | **Thin** — 2 tests. The real gap. | `tests/` |
| 25 Acceptance test | **Not built** | — |

**Recommendation for when this is implemented:** extend the existing project
rather than create `robinhood_trading_system/`. The genuinely new work is
phases 5, 6, 7, 17, 20, 24 and 25 — the execution path and the tests around it.
Everything else is consolidation of things that already work.

---

## The one hard boundary

The specification asks the system to place orders autonomously through the
authorized MCP, and is explicit that authentication, OAuth, brokerage
permissions and MCP authorization must never be circumvented. That is
compatible with how this project already works.

**The boundary that does not move:** Claude does not itself execute financial
transactions. That is a property of the assistant, not a configuration option,
and it is why the current loop is *system generates -> human places -> system
reconciles*.

What that means concretely for this build:

- Everything up to and including a fully validated, risk-checked, idempotent
  order object can be built and tested. That is the large majority of the work.
- Software placing that order through the user's own authorized MCP connection
  is the user's decision to enable and operate.
- Claude can build it, test it in simulation, review its logs, and explain what
  it did. Claude does not press the button.

Stated once, here, so the design accommodates it rather than discovering it in
phase 17.

---

## Phases, as specified

Condensed. The full text is preserved in the user's original message; this
records the requirements the build must satisfy.

### Phase 0 — Environment audit
Inspect OS, Python, packages, Node, git, Docker, existing project structure,
databases, environment variables, existing trading code, existing MCP config.
**Do not overwrite existing projects.** Create `README.md`, `ARCHITECTURE.md`,
`CHANGELOG.md`, `.env.example`, `.gitignore`, `requirements.txt`.

### Phase 1 — MCP connectivity
Verify: server reachable, authentication, agentic account visible, account
info, portfolio, buying power, positions, order history, market data tools,
order placement tools. Deliverable: `diagnose_robinhood.py` printing a
structured PASS/FAIL report. If authentication needs manual interaction, stop
at that step only, say exactly what is required, and continue afterwards.

### Phase 2 — Simulation mode
`MODE=SIMULATION` (default) and `MODE=LIVE`. Abstract the broker:

```python
class BrokerInterface:
    def get_account(self): ...
    def get_positions(self): ...
    def get_buying_power(self): ...
    def get_quote(self, symbol): ...
    def place_order(self, order): ...
    def cancel_order(self, order_id): ...
    def get_order(self, order_id): ...
```

Implement `SimulatedBroker` and `RobinhoodBroker` against the same interface.

### Phase 3 — Signal format
A standardized signal object: `signal_id`, `timestamp`, `symbol`, `asset_type`,
`action` (BUY/SELL/HOLD/CLOSE), `quantity`, `notional_value`, `confidence`,
`strategy`, `reason`, `expected_edge`, `expiration`.
**Free-form natural language must never reach the execution engine** — it is
converted to a validated structured signal first.

### Phase 4 — Risk engine
`config/risk.yaml` with max trade dollars, position dollars, position percent,
portfolio exposure, sector exposure, daily loss, drawdown, orders per day,
orders per symbol, open positions, min signal confidence, max slippage, and
flags for fractional/options/crypto/shorting. Every order passes
`risk_engine.validate(signal, portfolio)`. **Impossible to bypass through the
normal workflow.**

### Phase 5 — Kill switches
Software (`TRADING_ENABLED=false`), daily loss, drawdown, error rate, position
reconciliation mismatch, and a manual `KILL_SWITCH` file.
**The system fails CLOSED: if anything is uncertain, do not trade.**

### Phase 6 — Execution engine
Receive validated signal, verify quote, market status, buying power, current
position, duplicate check, final risk check, submit, record order id, monitor,
reconcile, log. **Idempotent** — the same `signal_id` twice must not produce two
trades.

### Phase 7 — Order state machine
`CREATED, VALIDATING, APPROVED, SUBMITTING, SUBMITTED, PARTIALLY_FILLED,
FILLED, CANCEL_REQUESTED, CANCELLED, REJECTED, FAILED, UNKNOWN`.
Never assume success because a request returned. On `UNKNOWN`, **query the
broker before retrying** — never blind-retry.

### Phase 8 — Reconciliation
Compare internal vs Robinhood positions on symbol, quantity, average price,
market value, realized and unrealized P&L, open orders. **Any discrepancy halts
trading** until reconciled. Produce a report.

### Phase 9 — Database
Tables: `signals`, `orders`, `fills`, `positions`, `portfolio_snapshots`,
`risk_events`, `system_events`, `strategy_runs`, `performance_metrics`.
Every trade must answer: which signal, which strategy, what data, which risk
checks, what was submitted, what the broker returned, what filled, what
position resulted.

### Phase 10 — Logging
Structured JSON. Separate application / trade / risk / error / audit streams.
**Never log passwords, tokens, secrets, OAuth credentials or private keys.**

### Phase 11 — Strategy plugins
`class Strategy: def generate_signals(self, market_data): ...` in a
`strategies/` package. The execution engine must not care which strategy
produced a signal.

### Phase 12 — ML integration
Accept XGBoost, LightGBM, CatBoost, Ridge, Bayesian, Monte Carlo and ensembles.
The ML layer outputs probability / expected return / confidence — **it does not
place orders**. The strategy layer converts that into a signal.

### Phase 13 — External data
`class MarketDataProvider` with `get_quote`, `get_historical`, `get_news`.
Vendors pluggable, never hard-coded into a strategy. Keep raw data, features,
model predictions and trade signals clearly separated.

### Phase 14 — Backtesting
Total return, CAGR, Sharpe, Sortino, max drawdown, win rate, profit factor,
average win/loss, expectancy, turnover, trade count, exposure. Transaction costs
and configurable slippage. No look-ahead. Time-series splits, never random.

### Phase 15 — Walk-forward
Train -> validate -> trade simulation -> roll forward -> retrain, reported
per period.

### Phase 16 — Shadow mode
`MODE=SHADOW`: real data, real signals, real risk calculations, **no orders**.
Record "would have bought/sold" and track hypothetical performance. Run long
enough to establish signals, order construction, risk controls, reconciliation,
duplicate protection, logging and restart recovery all work.

### Phase 17 — Live mode
Requires explicit `MODE=LIVE`, never the default. Print a loud warning banner,
then account, buying power, positions, risk limits, daily loss limit, max trade
size and mode — and verify them before the first order.

### Phase 18 — Claude's role
Supervisory: inspect performance, analyse logs, find anomalies, propose
improvements, review backtests, investigate events, explain trades.
**Claude must not silently modify** risk limits, kill switches, credentials,
authentication, live mode or max trade size.

### Phase 19 — Automation
A real scheduler (APScheduler / Celery / cron), not an LLM conversation.
Jobs: market-open init, data refresh, signal generation, portfolio monitoring,
risk monitoring, reconciliation, order monitoring, end-of-day reconciliation,
performance reporting.

### Phase 20 — Recovery
Survive process crash, restart, network outage, MCP disconnect, broker timeout,
duplicate signals, stale data, partial fills, unknown order status, database
interruption. On restart: connect, fetch account, positions and open orders,
reconcile, identify unresolved orders, restore state, **then** resume.
Never assume the previous process finished an order.

### Phase 21 — Dashboard
System status, mode, broker and MCP connection, buying power, portfolio value,
today's and total P&L, drawdown, open positions and orders, recent signals and
trades, risk events, kill-switch status. Plus **"why did the system trade?"**
per position: strategy, signal, confidence, expected edge, risk approval,
entry, current price, P&L, exit condition.

### Phase 22 — Alerting
Trade executed, trade rejected, risk limit triggered, kill switch activated,
MCP disconnected, broker unavailable, position mismatch, large loss, unexpected
position, system failure. Provider modular.

### Phase 23 — Security
`.env`, environment secrets, secrets excluded from git, least privilege, secure
file permissions, audit logs, no credentials in source. `.env.example` holds
placeholders only. **Never paste a secret into a source file.**

### Phase 24 — Tests
Unit: risk engine, position sizing, signal validation, order construction,
duplicate detection, P&L, drawdown.
Integration: MCP, broker interface, database, reconciliation, order lifecycle.
Failure: network timeout, duplicate order, unknown status, partial fill, MCP
disconnect, database failure, stale quote, risk breach.
End-to-end: signal -> risk -> simulated order -> fill -> position -> P&L ->
reconciliation.

### Phase 25 — Acceptance test
A 26-item checklist run automatically. **No item marked PASS without being
actually tested**, and LIVE mode must remain disabled.

---

## Working rules the spec imposes

- **INSPECT -> DESIGN -> IMPLEMENT -> TEST -> FIX -> DOCUMENT -> VERIFY -> NEXT.**
  Create real files, run real tests, fix real errors. No theoretical code dumps.
- **Maintain `PROJECT_STATUS.md`** after every phase: current phase, completed
  tasks, failed tests, known issues, next tasks, files created and modified.
  Read it plus `ARCHITECTURE.md` and `README.md` at the start of each session.
- **Do not get stuck.** On failure report PROBLEM / CAUSE / WHAT CAN BE DONE NOW
  / REQUIRED USER ACTION / NEXT AUTOMATED STEP, then continue with everything
  not blocked.
- **No fake completion.** Never claim tested, connected, working, deployed or
  executed without verification. Label anything unverified **UNVERIFIED**.
- **Token efficiency.** Do not restate the architecture or re-argue the premise.

---

## Open questions to settle before implementation starts

1. **Extend Stockbot2000, or build `robinhood_trading_system/` separately?**
   The spec says the latter; the audit above argues for the former. Two systems
   against one 8.5 GB database is a real risk.
2. **Which account?** The Agentic account currently holds ~$89 of real money and
   five positions placed by hand. Does this system take that account over, or
   get a separate one?
3. **Does the $100 mandate cap still hold?** It bounds every sizing decision in
   the existing project, and phase 4's limits have to be written against a
   number.
4. **What does it trade?** The existing evidence says the classifier is gross
   negative under honest fills and every screen loses to SPY. Autonomous
   execution of a strategy with no demonstrated edge automates the losses. The
   21 paper funds exist to answer this, and phase 16 shadow mode is the same
   question asked again.
5. **Options and crypto** are in scope per the spec's flags but have no
   strategy, no backtest and no data in this project.
