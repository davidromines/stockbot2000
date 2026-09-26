"""NYSE trading calendar from rules (Stage O).

Derived from exchange rules rather than from the price data's own dates, so a
live run on today's bar computes the same calendar columns as a backtest. The
data's future dates are not available at decision time; the calendar is.
"""
import runtime  # noqa: F401  (thread limits must be set before pandas import)

import datetime as _dt
from functools import lru_cache

import pandas as pd

MIN_YEAR = 1990
MAX_YEAR = 2040

# Full-day closures that no rule generates. Kept as data because they are
# historical accidents, not recurring observances.
ONE_OFF_CLOSURES = frozenset({
    _dt.date(1994, 4, 27),                        # Nixon funeral
    _dt.date(2001, 9, 11), _dt.date(2001, 9, 12),
    _dt.date(2001, 9, 13), _dt.date(2001, 9, 14),
    _dt.date(2004, 6, 11),   # Reagan funeral
    _dt.date(2007, 1, 2),    # Ford funeral
    _dt.date(2012, 10, 29), _dt.date(2012, 10, 30),  # Hurricane Sandy
    _dt.date(2018, 12, 5),   # Bush funeral
    _dt.date(2025, 1, 9),    # Carter funeral
})


def _easter(year):
    """Anonymous Gregorian algorithm (Meeus/Jones/Butcher)."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month, day = divmod(h + l - 7 * m + 114, 31)
    return _dt.date(year, month, day + 1)


def _nth_weekday(year, month, weekday, n):
    """n-th `weekday` (Mon=0) of the month; n=-1 means the last one."""
    if n > 0:
        first = _dt.date(year, month, 1)
        offset = (weekday - first.weekday()) % 7
        return first + _dt.timedelta(days=offset + 7 * (n - 1))
    last = _dt.date(year, month + 1, 1) - _dt.timedelta(days=1) if month < 12 \
        else _dt.date(year, 12, 31)
    offset = (last.weekday() - weekday) % 7
    return last - _dt.timedelta(days=offset)


def _observed(d):
    """Saturday -> Friday before, Sunday -> Monday after."""
    if d.weekday() == 5:
        return d - _dt.timedelta(days=1)
    if d.weekday() == 6:
        return d + _dt.timedelta(days=1)
    return d


@lru_cache(maxsize=None)
def holidays(year):
    """Sorted full-day holidays and one-off closures falling in `year`."""
    out = set()

    # New Year's Day is the one holiday with no Friday observance: a Saturday
    # Jan 1 is simply not observed, so Dec 31 of the prior year stays a session.
    ny = _dt.date(year, 1, 1)
    if ny.weekday() != 5:
        out.add(_observed(ny))

    if year >= 1998:
        out.add(_nth_weekday(year, 1, 0, 3))          # MLK
    out.add(_nth_weekday(year, 2, 0, 3))              # Washington's Birthday
    out.add(_easter(year) - _dt.timedelta(days=2))    # Good Friday
    out.add(_nth_weekday(year, 5, 0, -1))             # Memorial Day
    if year >= 2022:
        out.add(_observed(_dt.date(year, 6, 19)))     # Juneteenth
    out.add(_observed(_dt.date(year, 7, 4)))          # Independence Day
    out.add(_nth_weekday(year, 9, 0, 1))              # Labor Day
    out.add(_nth_weekday(year, 11, 3, 4))             # Thanksgiving
    out.add(_observed(_dt.date(year, 12, 25)))        # Christmas

    out.update(d for d in ONE_OFF_CLOSURES if d.year == year)
    return sorted(out)


@lru_cache(maxsize=None)
def _holiday_set(year):
    return frozenset(holidays(year))


def _as_date(d):
    if isinstance(d, _dt.datetime):
        return d.date()
    if isinstance(d, _dt.date):
        return d
    return _dt.date.fromisoformat(str(d)[:10])


@lru_cache(maxsize=None)
def is_session(d):
    d = _as_date(d)
    if d.weekday() >= 5:
        return False
    return d not in _holiday_set(d.year)


def sessions(start, end):
    """Session dates in [start, end] inclusive."""
    start, end = _as_date(start), _as_date(end)
    out = []
    d = start
    step = _dt.timedelta(days=1)
    while d <= end:
        if is_session(d):
            out.append(d)
        d += step
    return out


def next_session(d):
    d = _as_date(d) + _dt.timedelta(days=1)
    while not is_session(d):
        d += _dt.timedelta(days=1)
    return d


def prev_session(d):
    d = _as_date(d) - _dt.timedelta(days=1)
    while not is_session(d):
        d -= _dt.timedelta(days=1)
    return d


def _weekdays_between(a, b) -> int:
    """Weekdays strictly between two dates: 0 across an ordinary weekend, >= 1 across a holiday."""
    n, d = 0, a + _dt.timedelta(days=1)
    while d < b:
        n += d.weekday() < 5
        d += _dt.timedelta(days=1)
    return n


@lru_cache(maxsize=None)
def _columns_for(d):
    """Per-date calendar columns. Cached: a panel repeats dates heavily."""
    if not is_session(d):
        return (d.month, d.day, 0, 0, 0, 0)

    month_sessions = sessions(d.replace(day=1),
                              _dt.date(d.year, d.month, 28) + _dt.timedelta(days=4))
    month_sessions = [s for s in month_sessions if s.month == d.month]
    tdom = month_sessions.index(d) + 1
    tdom_rev = len(month_sessions) - tdom + 1

    # A gap of more than one weekday means a holiday or closure intervened;
    # an ordinary weekend is exactly one weekday of gap and does not count.
    nxt, prv = next_session(d), prev_session(d)
    pre = 1 if _weekdays_between(d, nxt) else 0
    post = 1 if _weekdays_between(prv, d) else 0
    return (d.month, d.day, tdom, tdom_rev, pre, post)


_COLUMNS = ["cal_month", "cal_dom", "cal_tdom", "cal_tdom_rev",
            "cal_pre_holiday", "cal_post_holiday"]


def calendar_columns(dates):
    """Calendar columns for `dates`, indexed positionally like the input."""
    rows = [_columns_for(_as_date(d)) for d in dates]
    return pd.DataFrame(rows, columns=_COLUMNS, dtype="int64")
