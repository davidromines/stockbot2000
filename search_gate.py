"""
When the evolutionary search may start a run (owner, 2026-09-26: restart the
search seed-free, winners to paper only, on a small budget outside market hours).

lab_loop.sh asks this before every iteration. Answers, one line on stdout:

    RUN <generations> <population> <paper_per_run>   start one now
    WAIT <reason>                                   sleep and ask again
    STOP <reason>                                   frozen: exit the loop

Rules (config search:):
    mode FROZEN                    -> STOP; lifting it is the owner's edit
    runs_per_day                   -> at most this many runs started per UTC day
    blocked windows (UTC)          -> the daily job (weekdays 06:45-08:45) and the
                                      market (weekdays 12:30-21:30), so the search
                                      never competes with either for CPU or memory
    run_hours                      -> a run starts only if it can finish (this many
                                      hours) before the next blocked window
Read-only apart from nothing: the day's count comes from lab_runs.

    ./venv/bin/python search_gate.py
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import datetime as dt
import sqlite3
import sys

DEFAULTS = {"runs_per_day": 1, "generations": 50, "population": 300, "paper_per_run": 3, "run_hours": 4.0,
            "blocked_utc": [["06:45", "08:45"], ["12:30", "21:30"]]}


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **((cfg.get("search") or {}).get("schedule") or {})}


def _blocks(now: dt.datetime, s: dict, days: int = 3) -> list:
    """Blocked (start, end) datetimes from today through `days` ahead; weekdays only."""
    out = []
    for d in range(-1, days + 1):
        day = (now + dt.timedelta(days=d)).date()
        if day.weekday() >= 5:
            continue
        for a, b in s["blocked_utc"]:
            ha, ma = map(int, a.split(":"))
            hb, mb = map(int, b.split(":"))
            out.append((dt.datetime.combine(day, dt.time(ha, ma), tzinfo=dt.timezone.utc),
                        dt.datetime.combine(day, dt.time(hb, mb), tzinfo=dt.timezone.utc)))
    return sorted(out)


def decide(cfg: dict, now: dt.datetime, runs_today: int) -> str:
    srch = cfg.get("search") or {}
    if str(srch.get("mode", "FROZEN")).upper() != "ACTIVE":
        return "STOP search.mode is FROZEN (set search.mode: ACTIVE in config.yaml to run)"
    s = settings(cfg)
    if runs_today >= int(s["runs_per_day"]):
        return f"WAIT daily budget used ({runs_today} of {s['runs_per_day']} runs today, UTC)"
    for a, b in _blocks(now, s):
        if a <= now < b:
            return f"WAIT blocked until {b:%a %H:%M} UTC (daily job or market hours)"
    nxt = next((a for a, _ in _blocks(now, s) if a > now), None)
    if nxt is not None and (nxt - now) < dt.timedelta(hours=float(s["run_hours"])):
        return f"WAIT a run would not finish before {nxt:%a %H:%M} UTC"
    return f"RUN {int(s['generations'])} {int(s['population'])} {int(s['paper_per_run'])}"


def runs_today(conn, now: dt.datetime) -> int:
    try:
        r = conn.execute("SELECT COUNT(*) FROM lab_runs WHERE substr(started_at,1,10)=?",
                         (now.strftime("%Y-%m-%d"),)).fetchone()
        return int(r[0]) if r else 0
    except sqlite3.Error:
        return 0


def main() -> int:
    from universe import load_config
    cfg = load_config()
    now = dt.datetime.now(dt.timezone.utc)
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True, timeout=60)
    print(decide(cfg, now, runs_today(conn, now)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
