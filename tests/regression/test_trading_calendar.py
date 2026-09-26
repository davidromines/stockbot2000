"""Regression tests for the rule-derived NYSE trading calendar (TASK-034)."""
import runtime  # noqa: F401

import datetime as dt
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

import trading_calendar as tc  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def d(s):
    return dt.date.fromisoformat(s)


def main():
    check("holidays(2024) exact",
          tc.holidays(2024) == [d("2024-01-01"), d("2024-01-15"), d("2024-02-19"),
                                d("2024-03-29"), d("2024-05-27"), d("2024-06-19"),
                                d("2024-07-04"), d("2024-09-02"), d("2024-11-28"),
                                d("2024-12-25")],
          str(tc.holidays(2024)))

    check("2021-07-05 observed Independence Day", d("2021-07-05") in tc.holidays(2021))
    check("2022-12-26 observed Christmas", d("2022-12-26") in tc.holidays(2022))
    check("2023-01-02 observed New Year", d("2023-01-02") in tc.holidays(2023))

    # Jan 1 2022 is a Saturday and New Year has no Friday observance.
    check("2021-12-31 is a session", tc.is_session("2021-12-31"))
    check("2022-01-01 not a session", not tc.is_session("2022-01-01"))

    check("2012-10-29 (Sandy) not a session", not tc.is_session("2012-10-29"))
    check("2001-09-11 not a session", not tc.is_session("2001-09-11"))
    check("Good Friday 2019-04-19", d("2019-04-19") in tc.holidays(2019))
    check("Good Friday 2024-03-29", d("2024-03-29") in tc.holidays(2024))

    check("MLK absent before 1998", d("1997-01-20") not in tc.holidays(1997))
    check("Juneteenth absent before 2022", d("2021-06-19") not in tc.holidays(2021))

    check("next_session skips weekend", tc.next_session("2024-01-05") == d("2024-01-08"))
    check("prev_session skips weekend", tc.prev_session("2024-01-08") == d("2024-01-05"))
    check("next_session skips holiday", tc.next_session("2024-01-12") == d("2024-01-16"))
    check("prev_session skips holiday", tc.prev_session("2024-01-16") == d("2024-01-12"))

    n = len(tc.sessions("2024-01-01", "2024-12-31"))
    check("2024 session count == 252", n == 252, f"got {n}")

    dates = [d("2024-01-01") + dt.timedelta(days=i) for i in range(31)]
    df = tc.calendar_columns(dates)
    check("calendar_columns length", len(df) == 31, str(len(df)))
    check("calendar_columns columns",
          list(df.columns) == ["cal_month", "cal_dom", "cal_tdom", "cal_tdom_rev",
                               "cal_pre_holiday", "cal_post_holiday"],
          str(list(df.columns)))

    row = {x.isoformat(): df.iloc[i] for i, x in enumerate(dates)}
    check("2024-01-02 cal_tdom == 1", row["2024-01-02"]["cal_tdom"] == 1,
          str(row["2024-01-02"]["cal_tdom"]))
    check("2024-01-31 cal_tdom_rev == 1", row["2024-01-31"]["cal_tdom_rev"] == 1,
          str(row["2024-01-31"]["cal_tdom_rev"]))
    check("2024-01-12 cal_pre_holiday == 1", row["2024-01-12"]["cal_pre_holiday"] == 1,
          str(row["2024-01-12"]["cal_pre_holiday"]))
    check("2024-01-16 cal_post_holiday == 1", row["2024-01-16"]["cal_post_holiday"] == 1,
          str(row["2024-01-16"]["cal_post_holiday"]))
    check("2024-01-19 cal_pre_holiday == 0", row["2024-01-19"]["cal_pre_holiday"] == 0,
          str(row["2024-01-19"]["cal_pre_holiday"]))
    check("2024-01-13 (Sat) cal_tdom == 0", row["2024-01-13"]["cal_tdom"] == 0,
          str(row["2024-01-13"]["cal_tdom"]))
    check("2024-01-15 (MLK) cal_tdom == 0", row["2024-01-15"]["cal_tdom"] == 0,
          str(row["2024-01-15"]["cal_tdom"]))
    check("2024-01-31 cal_tdom == 21", row["2024-01-31"]["cal_tdom"] == 21,
          str(row["2024-01-31"]["cal_tdom"]))

    # ISO strings and datetimes must give the same answer as dates.
    mixed = tc.calendar_columns(["2024-01-12", dt.datetime(2024, 1, 16, 15, 30)])
    check("string/datetime inputs agree",
          mixed.iloc[0]["cal_pre_holiday"] == 1 and mixed.iloc[1]["cal_post_holiday"] == 1,
          str(mixed.values.tolist()))

    # A repeated date must be computed once and reused (cache identity).
    check("per-date cache is shared",
          tc._columns_for(d("2024-01-12")) is tc._columns_for(d("2024-01-12")))

    if FAILED:
        print(f"\n{len(FAILED)} FAILED")
        sys.exit(1)
    print("\nALL PASS")


if __name__ == "__main__":
    main()
