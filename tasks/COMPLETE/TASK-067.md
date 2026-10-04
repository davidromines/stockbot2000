# TASK-067

- component: general
- priority: normal
- state: IN_PROGRESS
- branch: ado/task-067
- created: 
- dependencies: none

## Objective
Stage O10 — Import JKP/OSAP published factors as knowledge library entries
## Constraints
1. Never call `published_library.evidence_all()` or `published_library.candidates()
2. Do NOT touch `knowledge_factory.py`.
3. Do NOT touch `ranking.py`, `slots.py`, or any live-trading path.
4. Do NOT add a new test file; extend `tests/regression/test_knowledge_factory.py`.
5. No new dependency.
6. The function must be idempotent (re-running produces the same result, returns 0

## Acceptance criteria
1. grep "import_published_factors" knowledge_library.py` returns at least 2 lines
2. grep "published_factors" knowledge_library.py` returns at least 2 lines
3. grep "9c1" daily.sh` returns exactly 1 line
4. grep "published_factors" daily.sh` returns at least 1 line
5. python -m pytest tests/regression/test_knowledge_factory.py -x -q` exits 0
