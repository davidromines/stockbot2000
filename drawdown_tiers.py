"""
Drawdown tiers (owner, 2026-10-13): notice, review, stop.

    notice   `drawdown_notice_percent`  (10)  a Telegram message once a day; nothing else changes
    review   `drawdown_review_percent`  (20)  NEW ENTRIES are refused by the risk engine; exits still go
    stop     `max_drawdown_percent`     (35)  the existing kill switch (killswitch.py), unchanged

Drawdown is measured the way robinhood_live.get_account measures it: from the highest equity ever
recorded in `live_equity`. A tier whose key is absent or 0 is off, so the file can be deployed before
the numbers are chosen. This module only decides and tells; the refusal itself is in risk_engine.py and
the stop is in killswitch.py.
"""
import datetime as dt

OK, NOTICE, REVIEW, HALT = "OK", "NOTICE", "REVIEW", "HALT"


def levels(limits: dict) -> tuple:
    f = lambda k: float(limits.get(k) or 0)
    return f("drawdown_notice_percent"), f("drawdown_review_percent"), f("max_drawdown_percent")


def tier(dd: float, limits: dict) -> str:
    notice, review, halt = levels(limits)
    if halt and dd >= halt:
        return HALT
    if review and dd >= review:
        return REVIEW
    if notice and dd >= notice:
        return NOTICE
    return OK


def entry_pause_reason(dd: float, limits: dict) -> str | None:
    review = float(limits.get("drawdown_review_percent") or 0)
    if review and dd >= review:
        return (f"drawdown {dd:.1f}% is at or past the {review:.0f}% review level: "
                f"new entries are paused, exits still go")
    return None


def current(conn, equity: float | None = None) -> tuple:
    """(equity, peak, drawdown_percent) from live_equity; `equity` overrides the latest mark."""
    peak = conn.execute("SELECT MAX(equity) FROM live_equity").fetchone()[0]
    if equity is None:
        r = conn.execute("SELECT equity FROM live_equity ORDER BY at DESC LIMIT 1").fetchone()
        equity = r[0] if r else None
    if not equity or not peak:
        return equity, peak, 0.0
    peak = max(peak, equity)
    return equity, peak, (peak - equity) / peak * 100


def message(equity: float, peak: float, dd: float, limits: dict) -> tuple:
    notice, review, halt = levels(limits)
    t = tier(dd, limits)
    head = {NOTICE: "Drawdown notice", REVIEW: "Drawdown review level reached"}.get(t, "Drawdown")
    body = (f"Account ${equity:,.2f} is {dd:.1f}% below its ${peak:,.2f} peak. "
            f"Levels: notice {notice:.0f}%, review {review:.0f}%, stop {halt:.0f}%.")
    if t == REVIEW:
        body += " New entries are paused; open positions are still managed and can be sold."
    else:
        body += " No action taken."
    return head, body


def alert_if_new(conn, limits: dict, send, equity: float | None = None, today: str | None = None) -> str | None:
    """Tell the owner once per day per tier (NOTICE and REVIEW). Returns the tier alerted, else None."""
    import killswitch
    eq, peak, dd = current(conn, equity)
    t = tier(dd, limits)
    if t not in (NOTICE, REVIEW):
        return None
    day = today or dt.datetime.now(dt.timezone.utc).date().isoformat()
    killswitch.init(conn)
    key = f"{day}:{t}"
    if conn.execute("SELECT 1 FROM system_events WHERE kind='drawdown_tier' AND detail=?", (key,)).fetchone():
        return None
    killswitch.record_event(conn, "drawdown_tier", key, "warning")
    title, body = message(eq, peak, dd, limits)
    send(f"Stockbot2000 {title}", body)
    return t
