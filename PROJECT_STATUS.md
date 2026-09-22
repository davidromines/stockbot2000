# PROJECT_STATUS

Read this, `CLAUDE.md` and `docs/ROBINHOOD_AGENTIC.md` at the start of a session.
Updated 2026-09-22.

## Current phase

**Agentic execution system — merged into Stockbot2000, core built.**
The decision on open question 1 was made: extend this project, do not fork a
separate `robinhood_trading_system/` tree. Two systems against one 8.5 GB
database was the risk being avoided.

## Completed this phase

| Phase | Module | Tests |
|---|---|---|
| 3 Signal schema | `signals.py` | in `test_risk_engine.py` |
| 4 Risk engine | `risk_engine.py`, `config/risk.yaml` | `test_risk_engine.py` — 27 |
| 5 Kill switches | `killswitch.py` | `test_killswitch.py` — 14 |
| 2 Broker abstraction | `broker.py` | `test_execution.py` |
| 7 Order state machine | `broker.py` | `test_execution.py` |
| 6 Execution engine | `execution.py` | `test_execution.py` — 26 |
| 9 Database | `orders`, `fills`, `signals`, `risk_events`, `system_events` | — |
| 10 Structured logging | JSON events in `execution.py` | — |
| 16 Shadow mode | `execution.py`, `run_execution.py` | `test_execution.py` |
| — Runner | `run_execution.py` | run against the live book |

**Test suite: 5 files, all passing.** `test_fills`, `test_sell_alert`,
`test_risk_engine`, `test_killswitch`, `test_execution`.

## Design decisions worth not relitigating

- **`signal_id` is content-addressed** over strategy, symbol, action and
  session — not a timestamp or a uuid. The same decision regenerated after a
  crash hashes identically, so a retry cannot become a second trade.
- **Orders are sized by the risk engine, never by the signal.** An oversized
  signal is capped, not obeyed.
- **Everything fails closed.** Missing quote, unknown liquidity, unknown market
  cap, unreadable portfolio, reconciliation that never ran: all halt or reject.
- **UNKNOWN is resolved by asking the broker**, never by resubmitting.
- **Exits are never size-limited.** A limit that can block a sale traps capital
  in a losing position.
- **`config/risk.yaml` is separate from `config.yaml`** so a strategy edit can
  never widen a risk limit.

## Not built

| Phase | Why |
|---|---|
| 17 LIVE mode | No wired transmit path. `run_execution.py --mode LIVE` refuses explicitly rather than pretending. |
| 8 Full reconciliation service | Entry reconciliation exists (`orders.py --record-fills`); the scheduled comparison loop does not. |
| 20 Order-state recovery on restart | The engine is idempotent, but there is no startup sweep for unresolved orders. |
| 21 Dashboard | `monitor.py` and `fund_report.py` cover part of it; "why did the system trade?" per position does not exist yet. |
| 25 Acceptance test | The 26-item checklist is not automated. |

## Known issues

- `conv_deep_value` and `conv_quality_value` paper runs stalled since
  2026-09-11 — their `strategy` field holds `{"conviction": "..."}` rather than
  a genome. `_conviction_step` exists to handle it; still not advancing.
- **Re-score of the 304 Lab survivors never completed.** 284 of them were
  produced before the next-open fill fix and remain unverified. The job was
  killed mid-run; the lab loop currently holds the CPU.
- `stop_sweep.py` is built and has never been run, for the same reason.

## Next direction — Phase 6, planned 2026-09-22

**`docs/PHASE6_RESEARCH_INTEGRITY.md` is the new plan and supersedes the "Next"
list below as the project's direction.** It is a specification only; nothing has
been actioned. All existing systems integrate into it.

It reverses several current behaviours — continuous search becomes frozen by
default, seeding becomes opt-in with full ancestry tracking, and compute
priority puts strategy search last. Read it before resuming any work.

## Previously identified next steps (superseded as direction, still accurate as facts)

1. Run the re-score and the stop sweep when the CPU frees up.
2. Continue the search for a profitable strategy — the standing goal. Nothing
   in this project has demonstrated an edge: the classifier is gross negative
   under honest fills, every conviction screen loses to SPY, and ETF switching
   loses to buy-and-hold on every index pair.
3. The live lead is stop width: identical entry rule, tight stops positive and
   wide stops negative across six paper funds, on 11 days of forward data.
