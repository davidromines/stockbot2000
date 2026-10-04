# TASK-065

- component: knowledge_extract
- priority: medium
- state: TODO
- branch: ado/task-065
- created: 2026-10-04T00:00:00+00:00
- dependencies: none

## Objective

Extend the genome schema in `knowledge_extract.py` to include two optional stop fields — `take_profit_pct` and `trailing_atr_multiple` — so that knowledge-translated strategies whose source specifies a profit target or trailing stop get those fields encoded in the genome and executed by `stop_plans.from_genome`.

## Background

`knowledge_extract.py` sends a prompt to DeepSeek that defines the genome schema as:
```
A genome is {"entry": NODE, "exit": NODE, "risk": {"stop_atr_multiple": float, "max_hold_days": int}}.
```
Only two risk fields are recognised. `stop_plans.from_genome(genome)` already reads `risk.take_profit_pct` (exit once return ≥ pct) and `risk.trailing_atr_multiple` (trailing stop at high − N×ATR) — they just never appear because the LLM prompt does not mention them and the validation rejects them.

Adding them to the prompt and validation closes the loop: a knowledge entry that says "exit at 15% profit" will produce a genome `risk.take_profit_pct: 15.0` that flows through `stop_plans.from_genome` unchanged. No other file needs changing — `stop_plans.py`, `simulator.py` and the slot trader already handle both fields.

## Relevant files

- `knowledge_extract.py` (prompt string in `_system_prompt()` and `validate_genome()`)
- `tests/regression/test_knowledge_extract.py` (add validation tests)

## Requirements

1. In `_system_prompt()`, replace the genome grammar line:
   ```
   A genome is {"entry": NODE, "exit": NODE, "risk": {"stop_atr_multiple": float, "max_hold_days": int}}.
   stop_atr_multiple must be in 0.5..10; max_hold_days must be in 1..504.
   ```
   with:
   ```
   A genome is {"entry": NODE, "exit": NODE, "risk": {"stop_atr_multiple": float, "max_hold_days": int, "take_profit_pct": float (optional), "trailing_atr_multiple": float (optional)}}.
   stop_atr_multiple must be in 0.5..10; max_hold_days must be in 1..504.
   take_profit_pct (optional): exit when price >= entry × (1 + pct/100); must be in 1.0..500.0.
   trailing_atr_multiple (optional): trailing stop at session-high minus N×ATR; must be in 0.25..10.0.
   Omit take_profit_pct and trailing_atr_multiple when the source does not specify them.
   ```

2. In `validate_genome(g)`, after the existing `stop_atr_multiple` and `max_hold_days` checks, add:
   - If `risk.get("take_profit_pct")` is present and not None: must be a number in 1.0..500.0; append error if not.
   - If `risk.get("trailing_atr_multiple")` is present and not None: must be a number in 0.25..10.0; append error if not.

3. In `tests/regression/test_knowledge_extract.py`, add three new checks to the existing test:
   - `validate_genome({"entry": ..., "exit": ..., "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20, "take_profit_pct": 15.0}})` returns `[]` (no errors).
   - `validate_genome({"entry": ..., "exit": ..., "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20, "trailing_atr_multiple": 3.0}})` returns `[]`.
   - `validate_genome({"entry": ..., "exit": ..., "risk": {"stop_atr_multiple": 2.0, "max_hold_days": 20, "take_profit_pct": 0.5}})` returns a non-empty list (0.5 is below 1.0).
   Use a minimal valid entry/exit node `{"op":"gt","args":[{"col":"rsi_14"},{"const":0.5}]}` for entry and `{"op":"lt","args":[{"col":"close"},{"const":0}]}` for exit.

## Constraints

1. Do not change `stop_plans.py`, `knowledge_factory.py`, `knowledge_library.py` or any other file.
2. Do not alter the test file's existing checks — only append new ones.
3. Create or modify ONLY `knowledge_extract.py` and `tests/regression/test_knowledge_extract.py`.

## Acceptance criteria

1. `./venv/bin/python tests/regression/test_knowledge_extract.py` exits 0.
2. `grep "take_profit_pct" knowledge_extract.py` returns at least two lines (prompt + validation).
3. `./run_tests.sh` passes.
