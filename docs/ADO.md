# AI Development Orchestration (ADO)

Claude architects, specifies and reviews. A cheaper model implements. Git is the
source of truth. `run_tests.sh` is the gate.

**Built and operational 2026-09-22.** One task has been through the full loop.

## The loop

```text
task spec (here)  →  implement (DeepSeek)  →  test (gate)  →  review (here)
                          ↑                                        │
                          └──────── reject + feedback ─────────────┘
                                                                   ↓
                                                          approve → merge
```

## Commands

```bash
python orchestrator.py status
python orchestrator.py new --objective "..." --component data --priority high
python orchestrator.py next-task
python orchestrator.py implement TASK-001
python orchestrator.py test
python orchestrator.py review TASK-001
python orchestrator.py approve TASK-001
python orchestrator.py reject TASK-001 --feedback "..."
python orchestrator.py merge TASK-001
python orchestrator.py usage
```

## Components

| File | Role |
|---|---|
| `llm/provider.py` | Provider abstraction, `DeepSeekProvider`, usage metering. Swap models by adding a class. |
| `ado_task.py` | Task schema, filesystem state machine, context builder. |
| `orchestrator.py` | The CLI and the review loop. |
| `run_tests.sh` | The gate. One command, one exit code. |
| `tasks/{TODO,IN_PROGRESS,REVIEW,COMPLETE}/` | State is the directory a task lives in. |
| `config.yaml` → `ado:` | Provider, model, token cap, rate estimates. |

## Design decisions that are load-bearing

**State is a directory, not a column.** `ls tasks/REVIEW` answers "what needs
attention" with no code running, survives a database rebuild, and git tracks the
whole history free.

**Context is deliberately small.** `build_context()` sends project state,
conventions, the files the task names, and — for database tasks — the schema.
Not the repository, not the conversation. Every token sent is the cost this
arrangement exists to reduce.

**The model may only write files the task names.** Anything else is refused. A
model choosing its own scope is how unrelated changes appear in a diff nobody
asked for.

**Nothing auto-merges.** A passing gate means the known failures did not recur.
Every defect in this project's history passed every test that existed when it
shipped.

**A task without acceptance criteria is refused.** If the criteria are not
checkable the gate cannot function, and review falls back to reading code line
by line — the expensive thing ADO exists to avoid.

**Credentials never enter the loop.** The key lives in `~/.deepseek_key` at
0600, is never logged, never committed, never included in a payload, and is
scrubbed from API error bodies before they are raised.

## What the first real task taught

TASK-001 (`data_audit.py`) took three rounds. Both failures were worth having.

**Round 1 audited the wrong database** — `positions.db`, the trade ledger,
instead of `market_data.db`. It would have run cleanly and produced a confident
report about the wrong data. That is the exact class of defect this project has
spent six weeks removing, and it is the argument against auto-merge in one
example.

**Round 2 used `p.symbol` against a table whose column is `ticker`.** That was a
defect in the *context*, not the implementation: the model was sent a file that
did not yet exist and nothing describing the schema. A model cannot infer a
column name it has never seen. `build_context` now supplies the schema to any
task that looks like it will write SQL.

**The merge step exposed a third gap** — nothing prevented merging a branch
whose task was still `IN_PROGRESS`, and the first run did exactly that because
the merge was a manual git command. `orchestrator.py merge` now refuses
anything not `COMPLETE`.

**Cost:** three rounds, 4 calls, 20,697 prompt tokens, 8,262 completion tokens,
**$0.0147**, 27 seconds of model time.

## What delegates well, and what does not

| Delegate | Keep here |
|---|---|
| Schema and migrations | Anything touching the null, fills or gates |
| CRUD, ETL, report formatting | The validation firewall |
| Test scaffolding from a spec | Point-in-time availability logic |
| Ratio and statement arithmetic | Regression-suite *assertions* |
| Repetitive refactors | Interpreting results |

The division is not by difficulty. It is by **what happens when it is subtly
wrong.** A misformatted report is visible immediately; a benchmark computed on
the wrong fill convention is invisible for weeks and inverts a conclusion.
