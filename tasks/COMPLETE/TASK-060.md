# TASK-060

- component: reporting
- priority: medium
- state: COMPLETE
- branch: ado/task-060
- created: 2026-10-03T00:00:00+00:00
- dependencies: none

## Objective
Append a "DISCOVERY TARGETS" section to the EOD Telegram report showing families that `discovery.weak_spots()` flags. Max 5 lines, only emitted when non-empty.

## Background
`discovery.weak_spots(conn)` returns a `{family: reason}` dict (N7, commit 05e333e). Four signals: near-miss strategies (funnel), weakening slot holder (strategy_health N5), high stop-exit rate (>60% stops, >=3 live trips), high entry slippage (>30 bps, >=4 live fills). The owner gets an EOD Telegram report; surfacing which families deserve fresh strategies closes the loop between live evidence and discovery priority.

The EOD report is built by `_build_report(conn, cfg, day, mode, ranking)` and rendered by `_render_text(report)`. The text renderer emits sections by calling `head()` and printing rows. The DISCOVERY TARGETS section should appear after the existing FAILURES section and only when `discovery.weak_spots(conn)` returns a non-empty dict.

The `head(key, label)` function in `_render_text` is already defined. Each row is printed with two spaces of indentation. `discovery` is already in the project (no new dependency).

## Relevant files
- `eod_report.py`
## Requirements
1. In `_build_report`, call `discovery.weak_spots(conn)` and store the result under key `"discovery_targets"` in the returned report dict. Wrap in try/except so any import or runtime error yields an empty dict (never crash the report).
2. In `_render_text`, after all existing sections, check `report.get("discovery_targets")`. If non-empty, emit a section headed `DISCOVERY TARGETS` with up to 5 lines, each formatted as `  {family}: {reason}`.
3. The section is completely absent (no heading, no blank line) when `discovery_targets` is empty or missing.

## Constraints
1. Do not change the JSON report structure for any key other than the new `"discovery_targets"` addition.
2. Do not change any existing section in `_build_report` or `_render_text`.
3. Create ONLY changes to `eod_report.py`. Modify nothing else.

## Acceptance criteria
1. import eod_report` succeeds (no SyntaxError).
2. In a unit test (add it as a `if __name__ == "__main__"` block or a standalone inline test inside the file): mock `discovery.weak_spots` to return `{"xs_momentum": "stop-exit 75%"}`, call `_render_text` with that in the report, assert `"DISCOVERY TARGETS"` and `"xs_momentum"` appear in the output.
3. Mock `discovery.weak_spots` to return `{}` — assert `"DISCOVERY TARGETS"` does NOT appear.
4. ./run_tests.sh` passes.
