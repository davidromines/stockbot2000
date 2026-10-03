# TASK-059

- component: infrastructure
- priority: high
- state: COMPLETE
- branch: ado/task-059
- created: 2026-10-03T00:00:00+00:00
- dependencies: none

## Objective
Add a `[3c2]` step to `daily.sh` that refreshes the Robinhood OAuth token once per day, so the token does not expire between sessions. Wire it via `robinhood_mcp.py --refresh --quiet`.

## Background
The Robinhood token expired on 2026-10-01 and halted LIVE trading (token from 09-24 was never refreshed; file mtime unchanged). The `--refresh` flag was added in commit e0066d0 and refreshes the token when it has aged past 1/4 of its stated lifetime. It currently only fires during an active trading session. A proactive daily refresh before the trading window starts prevents the silent expiry that killed LIVE.

`daily.sh` already has a `[3c]` step (`market_caps.py --backfill`) at line ~116. The new `[3c2]` step runs immediately after `[3c]`. It must be a no-op when the token file is missing (sign-in has never been done) and must not block the rest of the pipeline on failure.

The `run` helper in `daily.sh` logs and times each step; every existing step uses it. Steps that should not abort the pipeline on failure use `|| true` after the run call.

`robinhood_mcp.py --refresh` already performs the refresh and logs output. Add `--quiet` so it suppresses stdout when nothing was done (token still fresh or file missing). Errors are still printed.

Token file path: `~/.config/stockbot2000/robinhood_oauth.json`.

## Relevant files
- `daily.sh`
- `robinhood_mcp.py`
## Requirements
1. Add `--quiet` flag to `robinhood_mcp.py --refresh` that suppresses stdout output when no refresh was performed (token still fresh or file absent). Errors are still printed to stderr.
2. Add `[3c2/10] Robinhood token refresh` to `daily.sh` immediately after the `[3c]` step (market_caps.py line), calling `$PY robinhood_mcp.py --refresh --quiet`. The step must not abort the pipeline on failure (append `|| true` to the `run` call).
3. When the token file does not exist at `~/.config/stockbot2000/robinhood_oauth.json`, exit 0 with no output.

## Constraints
1. Do not change any other step in `daily.sh`.
2. Do not change the token refresh logic itself — only add `--quiet` flag output suppression.
3. Create ONLY changes to `daily.sh` and `robinhood_mcp.py`. Modify nothing else.

## Acceptance criteria
1. grep -n "3c2" daily.sh` prints one line containing `robinhood_mcp.py --refresh --quiet`.
2. ./venv/bin/python robinhood_mcp.py --refresh --quiet` exits 0 and prints nothing to stdout when the token file is absent.
3. Running `./run_tests.sh` still passes (no regressions).
