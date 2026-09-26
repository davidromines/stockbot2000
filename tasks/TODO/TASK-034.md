# TASK-034

- component: data
- priority: high
- state: TODO
- branch: ado/task-034
- created: 2026-09-26T02:00:00+00:00
- dependencies: none

## Objective
Create trading_calendar.py (Stage O): the NYSE trading calendar from rules (no network, no data), and calendar columns for calendar-anomaly strategies, plus its regression test.

## Background
Calendar strategies (turn of the month, pre-holiday, payday, January) need to know, on a given session, how many sessions remain in the month and whether the next session follows a holiday. That must come from the exchange calendar, never from the data's own future dates, so a live run on today's bar computes the same value as a backtest. NYSE full-day holidays by rule: New Year's Day (Jan 1; if Saturday, NOT observed on Fri Dec 31; if Sunday, observed Monday Jan 2), Martin Luther King Jr. Day (3rd Monday of January, from 1998), Washington's Birthday (3rd Monday of February), Good Friday (Friday before Easter Sunday; compute Easter with the anonymous Gregorian algorithm), Memorial Day (last Monday of May), Juneteenth (June 19, from 2022), Independence Day (July 4), Labor Day (1st Monday of September), Thanksgiving (4th Thursday of November), Christmas (Dec 25). For July 4, June 19 and Dec 25: Saturday -> observed Friday before, Sunday -> observed Monday after. One-off closures: 2001-09-11, 2001-09-12, 2001-09-13, 2001-09-14, 2004-06-11, 2007-01-02, 2012-10-29, 2012-10-30, 2018-12-05, 2025-01-09. Sessions are weekdays that are not holidays or closures. Supported range 1990-01-01 to 2040-12-31.

## Relevant files
- `trading_calendar.py`
- `tests/regression/test_trading_calendar.py`
## Requirements
1. holidays(year) returns the sorted list of datetime.date full-day holidays and one-off closures in that year, per the Background rules.
2. is_session(d) for a date or ISO string; sessions(start, end) returns the list of session dates (datetime.date) in [start, end] inclusive; next_session(d) and prev_session(d) return the adjacent session.
3. calendar_columns(dates) takes an iterable of dates (datetime, date, or ISO strings; non-sessions allowed) and returns a pandas DataFrame indexed like the input position with integer columns: cal_month (1-12), cal_dom (calendar day of month), cal_tdom (1-based index of the session within its month; 0 for a non-session), cal_tdom_rev (1 on the month's LAST session, 2 on the one before, ...; 0 for a non-session), cal_pre_holiday (1 if the date is a session and the next session is more than one weekday later, i.e. a holiday or closure falls between; ordinary weekends do not count), cal_post_holiday (1 if the date is a session and the previous session is more than one weekday earlier).
4. calendar_columns must compute per unique date once (cache by date) so a 30-million-row panel is fast; module-level lru_cache on the per-date function is acceptable.
5. Import runtime first; standard library plus pandas only.

## Constraints
1. Create ONLY the two files this task names. Modify nothing else.
2. No network, no database, no new dependency.
3. Keep trading_calendar.py under 200 lines and the test under 160 lines.
4. Test file: import runtime first, then put the repo root on sys.path as tests/regression/test_accounting.py does.
5. Plain script, no pytest: a check(name, cond, detail="") helper printing `  PASS  name` or `  FAIL  name`, then sys.exit(1) if any failed.

## Acceptance criteria
1. PYTHONPATH=. venv/bin/python tests/regression/test_trading_calendar.py exits 0.
2. The test checks holidays(2024) equals exactly [2024-01-01, 2024-01-15, 2024-02-19, 2024-03-29, 2024-05-27, 2024-06-19, 2024-07-04, 2024-09-02, 2024-11-28, 2024-12-25]; 2021-07-05 and 2022-12-26 and 2023-01-02 are holidays (observed); 2022-01-01 is a Saturday with no Friday observance so 2021-12-31 is a session; 2012-10-29 and 2001-09-11 are not sessions; Good Friday 2019-04-19 is a holiday.
3. The test checks calendar_columns on 2024-01-02..2024-01-31: 2024-01-02 has cal_tdom 1, 2024-01-31 has cal_tdom_rev 1, 2024-01-12 has cal_pre_holiday 1 (MLK on the 15th), 2024-01-16 has cal_post_holiday 1, 2024-01-19 (a Friday before a normal weekend) has cal_pre_holiday 0, and 2024-01-13 (a Saturday) has cal_tdom 0.
4. sessions(2024-01-01, 2024-12-31) has 252 dates.
5. At least 12 lines beginning with `  PASS`; ./run_tests.sh reports ALL PASS.
