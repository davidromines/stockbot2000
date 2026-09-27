# TASK-055

- component: reporting
- priority: medium
- state: TODO
- branch: ado/task-055
- created: 2026-09-27T22:30:00+00:00
- dependencies: none

## Objective
Create digest.py: a short weekly research digest sent to the owner by Telegram — what the research system did this week and what it found — built only from files and tables other stages already write. Plus its regression test.

## Background
The owner reads on a phone, prefers brief structured text, Pacific time, and these rules: the headline money is ONLY the real account's live slot trades (never a sum of paper funds); do not mention fees, spread or costs; results are evidence, never advice. Sources (all may be missing — then that section is omitted, never an error):
- data/funnel.json: keys "as_of", "lab" (dict), "factory" {"steps": [{"from","to","n"}], "rejections": {reason: n}}, "forward" {"funds", "funds_with_marks", "closed_paper_trades"}, "market" {"unseen": {"tested","net_positive","above_random"}, "checks": {check: {"PASS": n, "FAIL": n, "NA": n}}}, "failures": [{"strategy_key","reasons": [..], "near_miss": bool}].
- data/knowledge_factory.json: {"entries", "translated", "translated_yes", "requiring_interpretation", "reproductions", "variants", "lineages"}.
- table strategy_decisions(at TEXT ISO UTC, strategy_key, version, decision, from_state, to_state, reason): transitions this week (at >= now - 7 days) counted by to_state (PAPER = entered paper trading, REJECTED, QUALIFIED).
- table slot_trades(at, mode, slot_id, strategy_key, version, symbol, action 'OPEN'/'CLOSE', quantity, price): LIVE closed trades this week = CLOSE rows in the week paired with the slot's previous OPEN; net = (close price - open price) * quantity.
- table slot_assignments(at, slot_id, action 'ASSIGN'/'RELEASE', strategy_key, version, reason): changes this week.
- table ranking_history(date, strategy_key, version, rank, score): the newest date's top 5 (strategy_key and score) and the strategy names from league_strategies(strategy_key, version, name).
- Sending: import notify inside the function; notify.notify(title, text) sends to Telegram and desktop.
- Time: timefmt.pacific(iso_utc_str) returns a Pacific-time string (import inside functions; fall back to the UTC string if the import fails).

## Relevant files
- `digest.py`
- `tests/regression/test_digest.py`

## Requirements
1. collect(conn, now=None, root=".") -> dict with sections: "live" {closed, net_usd, wins} (this week), "pipeline" {entered_paper, rejected, qualified}, "knowledge" (the json's keys), "funnel" {unseen, checks, near_misses (count of failures with near_miss)}, "slots" [changes: slot_id, action, strategy name or key, reason], "top" [5 of (name, score)]. `now` is a UTC datetime (default now); `root` is where data/ lives. A missing file or table leaves that section None.
2. render(d) -> str: plain text for a phone, at most ~40 lines, sections in this order with short headings: "Real account this week" (closed trades, net $, wins; or "no closed trades"), "Research this week" (entered paper / rejected / qualified), "Knowledge Factory" (translated, reproductions, variants), "Unseen 2023→today" (above random of tested) and "Bear-market check" (pass/fail), "Near misses", "Slot changes", "Top of the ranking". Money as $x.xx with a sign; scores as +x.xx%. Never print the words fee, fees, spread, cost or costs. End with the line "Evidence, not advice."
3. send(conn, now=None, root=".", dry_run=False) -> str: render(collect(...)); unless dry_run, notify.notify("Stockbot2000 weekly research", text); return the text.
4. main(argv=None): --send, --dry-run (print only). Import runtime first; sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60) with from universe import load_config inside main.

## Constraints
1. Create ONLY digest.py and tests/regression/test_digest.py. Modify nothing else.
2. digest.py under 200 lines; test under 150 lines. Standard library only (plus sqlite3/json/datetime).
3. The test uses an in-memory sqlite3 database with the tables above (only the columns listed) and a temporary directory holding data/funnel.json and data/knowledge_factory.json; it replaces notify.notify with a recorder via sys.modules (insert a fake module named notify before calling send).
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does. Plain script, no pytest: check(name, cond, detail="") printing `  PASS  name` / `  FAIL  name`, sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_digest.py exits 0.
2. The test checks: a live CLOSE this week paired with its OPEN gives the right net; a CLOSE from last week is not counted; decisions this week are counted by to_state; slot changes are listed with the strategy name; the top 5 comes from the newest ranking date; missing json files omit their sections without error; the rendered text contains none of fee/fees/spread/cost/costs (case-insensitive) and ends with "Evidence, not advice."; send calls notify once with the text and dry_run does not call it.
3. At least 9 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
