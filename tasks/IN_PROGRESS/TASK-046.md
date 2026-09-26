# TASK-046

- component: operations
- priority: high
- state: IN_PROGRESS
- branch: ado/task-046
- created: 2026-09-26T11:00:00+00:00
- dependencies: none

## Objective
Create telegram_bot.py: a Telegram command listener that answers ONLY the owner, from their own chat, with read-only status commands plus a confirmed /kill and /resume of the file kill switch; it never places, changes or cancels an order and never executes message text. Plus its regression test.

## Background
Credentials: notify._telegram_creds() returns {"token", "chat_id", ...} parsed from ~/.telegram (0600), or None; an optional "user_id" line may exist. Owner identity: user_id = creds["user_id"] if present, else int(chat_id) when chat_id > 0 (a private chat's id is the user's id); if neither applies, NO command is authorized (fail closed). An update is authorized only if update["message"]["chat"]["id"] == int(chat_id) AND update["message"]["from"]["id"] == user_id. Telegram getUpdates (GET https://api.telegram.org/bot<TOKEN>/getUpdates?offset=N&timeout=T) returns {"ok": true, "result": [update...]} where each update has "update_id" and "message": {"message_id", "date" (unix seconds), "chat": {"id"}, "from": {"id"}, "text"}. Offsets: after handling (or ignoring) an update, the next offset is update_id + 1, persisted in data/telegram_offset.json so no update is ever handled twice, including unauthorized and stale ones. Stale: a message older than STALE_S = 600 seconds when handled is not executed; the bot replies "ignored: command was N minutes old". The kill switch: killswitch.KILL_FILE (a Path), killswitch.engage(conn, why) creates it, killswitch.release(conn, who) removes it (returns False if absent), killswitch.global_engaged() returns the reason string or None, killswitch.record_event(conn, kind, detail, severity) appends an audit row. Confirmation: "/kill" replies "Reply /kill confirm within 2 minutes to stop all trading and flatten slot positions at the next market-hours run."; "/kill confirm" within CONFIRM_S = 120 seconds of a pending /kill (stored in data/telegram_pending.json with its timestamp) calls killswitch.engage(conn, "telegram /kill by owner at <UTC ISO>") and replies with what happens next; "/resume" and "/resume confirm" likewise call killswitch.release. A confirm with no fresh pending request replies "nothing to confirm". Read-only commands: /help (lists commands), /status (kill switch state, the latest trader_runs row for mode LIVE: at, outcome, positions, cash; open LIVE slot positions from slot_trader.open_positions(conn, "LIVE") as "slot N SYMBOL qty @ price"), /positions (just the positions), /health (strategy health counts from control_center_extra.health_view(conn)["counts"] and the age in minutes of the newest trader_runs row), /report (eod_report.render(eod_report.build(conn, <today UTC>, "LIVE", rank_fn=None))). Any other text (including unknown slash commands) replies "unknown command — /help" and nothing else happens. Every authorized command, and every ignored unauthorized update (without its text), is recorded with killswitch.record_event(conn, "telegram_command" or "telegram_ignored", detail, "info"). Replies are plain text (no parse mode), at most 4000 characters.

## Relevant files
- `telegram_bot.py`
- `tests/regression/test_telegram_bot.py`
## Requirements
1. authorized(update, creds) implements the owner rule above (fail closed on any missing field).
2. handle(conn, update, creds, now=None, reply=None) processes ONE update: returns the reply text it sent (or None when unauthorized — no reply is ever sent to a stranger); `reply` is a callable(text) (default sends to creds chat_id via sendMessage with requests, timeout 20); `now` is a UTC datetime (default now).
3. poll(conn, creds, seconds=55, get_updates=None, reply=None) loops until `seconds` elapse calling get_updates(offset, timeout) (default requests GET with a 25 s long-poll), calls handle for each update in order, and persists the offset after EACH update. Network errors are logged and the loop continues after a short sleep; it never raises.
4. main(argv=None) with --poll [--seconds N]: loads creds (exit 0 with a message when absent), opens the database with sqlite3.connect(load_config()["database"]["market_data_path"], timeout=30) (from universe import load_config), row_factory sqlite3.Row, and polls. Import runtime first.
5. Module docstring states the security model: owner-only, stale commands ignored, confirmations, no order commands, message text is data.

## Constraints
1. Create ONLY telegram_bot.py and tests/regression/test_telegram_bot.py. Modify nothing else.
2. The test never touches the network or ~/.telegram, never creates the real data/KILL_SWITCH: point killswitch.KILL_FILE and the offset/pending file paths (module constants OFFSET_FILE and PENDING_FILE) at a tempfile directory and restore them; use sqlite3.connect(":memory:") with killswitch.init(conn) and a minimal trader_runs / slot_trades schema (or monkeypatch slot_trader.open_positions and control_center_extra.health_view / eod_report functions).
3. Keep telegram_bot.py under 250 lines and the test under 200 lines. Be compact: the response must fit the output limit.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_telegram_bot.py exits 0.
2. The test checks: a stranger's message (different from.id) gets no reply and changes nothing; a message from the owner in a different chat is refused; creds without user_id and a negative chat_id authorize nobody; /kill alone does NOT create the kill file; /kill then /kill confirm within 120 s creates it; /kill confirm after 121 s replies "nothing to confirm" and creates nothing; a stale /kill confirm (message date 11 minutes old) is not executed; /resume confirm removes the file; /status mentions the kill switch state; unknown text replies "unknown command" and executes nothing; poll persists the offset so a re-run skips handled updates.
3. At least 11 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
