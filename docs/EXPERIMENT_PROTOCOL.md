# Experiment protocol

Phase 6 §11-§12, §29. How an experiment is run here, from question to
recorded result. The mechanism is `experiment_registry.py`; this document is
the procedure around it.

**The problem it prevents: researcher degrees of freedom.** Every choice made
after seeing a result (which metric, which window, which holding period,
whether to re-run) turns a test into a search that reports itself as a test.
This project has done it: momentum+pullback was reported as a finding and
withdrawn within the hour once its ancestry was checked.

---

## The lifecycle

```text
DRAFT -> REGISTERED -> RUNNING -> COMPLETE
   \          \           \
    +----------+-----------+--> REJECTED   (with a reason; kept, never deleted)
```

| state | what may change |
|---|---|
| DRAFT | anything |
| REGISTERED | nothing locked. `update()` refuses; a change is a NEW VERSION |
| RUNNING | nothing locked; results not yet attached |
| COMPLETE | nothing. Terminal: a completed experiment is history |
| REJECTED | nothing. Abandoned experiments stay (the file-drawer rule) |

## The locked fields

Fixed at registration and hashed (`spec_hash`). The hash is checked again
before any result is attached:

| field | write down |
|---|---|
| `hypothesis` | what is claimed, and **what result would count as it failing** |
| `primary_metric` | the one number that decides it. Net P&L in dollars unless there is a reason |
| `universe` | who may be traded, with the floors (price, liquidity, market cap) |
| `entry_rule` / `exit_rule` | exactly, including stops |
| `holding_period` | fixed, or the rule that ends a hold |
| `cost_assumptions` | the cost model and its settings |
| `evaluation_period` | dates. **Never the sealed holdout** unless this is its one use |
| `data_version` | which database state / truth set |
| `stopping_rule` | when it ends: a date, a trade count, a budget. Not "when it looks good" |
| `sample_size` | the trades or sessions needed before the primary metric is read |
| `holdout_policy` | what is held out and when it may be opened (once, ever) |

Notes and free text may change. The experiment may not.

## Procedure

1. **Write the question as a hypothesis that can fail.** "Tight stops beat wide
   stops on rising_200, net, 2006-2019, in a majority of hold lengths" can
   fail. "Explore stop widths" cannot. The registry refuses an empty
   hypothesis.
2. **Fill every locked field before looking at any result** that bears on the
   question, including a quick backtest "just to check it runs".
3. **Declare the trial budget** if it generates strategies. Trials count against
   the append-only counter (`multiple_testing.py`), and `factory.py` refuses a
   generation run without a registered experiment, `seed_mode: NONE`, a
   budget, an acknowledged freeze and ancestry recording.
4. **Register.** From here a change to any locked field is a new version, and
   the registry shows both versions side by side.
5. **Run.** Where there are arms (seeded vs seed-free, A vs B), **run every
   arm and report every arm**. There is no code path that reports only the
   better one (`experiments/seed_free_search/run.py`).
6. **Attach results and a conclusion.** State the primary metric first, gross,
   costs and net side by side, against the null and the baselines it
   registered.
7. **Attach counter-evidence as an artifact** (hash, timestamp, path), not a
   footnote. The stop-width sweep is attached this way to the six rising_200
   decisions.
8. **A result that looks promising is a hypothesis for the next registered
   experiment, not a parameter to adopt.** No threshold, horizon or band is
   picked from the experiment that measured it.

## Worked example: `stop_width` (COMPLETE, 2026-09-24)

| | |
|---|---|
| observation | 11 forward days on 6 funds: same rising_200 entry, tight stops positive, wide stops negative |
| design | a sweep, not a search: entry fixed, stop width x hold varied, over the registered 2006-2019 grid, every entry rule given to it. The output is a shape that holds or does not, not a champion |
| result | **refuted.** rising_200 loses net and trails the null in all 30 stop x hold cells, and tight stops did worse than wide, for all four entry rules tested |
| consequence | the six rising_200 funds are classified PROMISING / INSUFFICIENT EVIDENCE, with the sweep attached as counter-evidence |

## Commands

```bash
./venv/bin/python experiment_registry.py --list
./venv/bin/python experiment_registry.py --show <experiment_id>
./venv/bin/python experiments.py            # the ledger of results, ranked by money
```

## What this does not protect against

- **An honest question asked of biased data.** Registration does not fix
  survivorship bias; `pit_universe.py`, the universe loader's modes and the
  matched-universe baseline bound it.
- **Many registered experiments on one dataset.** Each is honest, but together
  they are multiple testing. They count against the trial counter, and the
  deflated-Sharpe correction uses that count.
