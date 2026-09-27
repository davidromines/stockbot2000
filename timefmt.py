"""
Times shown to the owner, in Pacific time (owner, 2026-09-26: "change the time to
PST"; Stage N11).

Everything is STORED in UTC — database rows, logs, cron — because UTC never
jumps and a stored time must mean one moment. Only what a person reads is
converted, here, to America/Los_Angeles, which is PDT in summer and PST in
winter (the label says which).

    pt("2026-09-28T13:34:27+00:00")   -> "Mon 09-28 06:34 PDT"
    pt_time(...)                      -> "06:34 PDT"
"""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def to_pacific(value) -> datetime | None:
    """A stored time (ISO string or datetime; naive means UTC) as a Pacific datetime."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        d = value
    else:
        s = str(value).strip().replace("Z", "+00:00")
        if len(s) <= 10:
            return None          # a bare date names a session, not a moment: never shift it
        try:
            d = datetime.fromisoformat(s)
        except ValueError:
            return None
    if d.tzinfo is None:
        d = d.replace(tzinfo=timezone.utc)
    return d.astimezone(PACIFIC)


def pt(value, fmt: str = "%a %m-%d %H:%M %Z") -> str:
    """Pacific time for display; a value that is not a time is returned unchanged."""
    d = to_pacific(value)
    if d is None:
        return "n/a" if value in (None, "") else str(value)
    return d.strftime(fmt)


def pt_time(value) -> str:
    return pt(value, "%H:%M %Z")
