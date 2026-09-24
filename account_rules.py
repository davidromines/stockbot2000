"""
Account-rule guard. Addendum A §3, Addendum B §B12; build step I12.

The Robinhood Agentic account is a CASH account (user, 2026-09-24), set as
`account_type` in config/risk.yaml. The two account types break in different
ways, and the guard enforces the one that applies:

CASH — settled funds only
    Sale proceeds settle T+1. Buying with unsettled proceeds and then selling
    that purchase before the proceeds settle is a good-faith violation; three
    in twelve months restricts the account for 90 days. The guard prevents the
    first half: a BUY may use only SETTLED cash, so no purchase is ever funded
    by unsettled money and no violation can follow. Pattern-day-trader rules
    do not apply to cash accounts.

MARGIN — pattern day trader
    Four or more day trades in five business days with equity under $25,000
    restricts the account. A day trade is a buy and a sell of one symbol in
    one session. Blocking the exit would trap capital in a losing position (the
    risk engine never size-limits a sale), so the guard blocks the ENTRY instead:
    at three day trades in the window, new buys stop until the window rolls.

Both figures are computed from the execution engine's own `orders` table, in
the same mode as the engine (SIMULATION fills never count against LIVE), so the
guard works identically in simulation, shadow and live.

Settlement dates count weekdays only. Market holidays make real settlement a
day LATER than this computes, which would make the guard optimistic by a day
around a holiday — so a sale is held unsettled for one extra weekday
(`holiday_margin_days`, default 1). A day of idle cash costs nothing; a
violation costs the account.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
from datetime import date, timedelta

FILLED = ("FILLED", "PARTIALLY_FILLED")
PDT_EQUITY = 25_000.0
PDT_MAX_DAY_TRADES = 3


def add_weekdays(d: date, n: int) -> date:
    while n > 0:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def weekdays_back(d: date, n: int) -> date:
    while n > 0:
        d -= timedelta(days=1)
        if d.weekday() < 5:
            n -= 1
    return d


def unsettled_proceeds(conn, today: str, mode: str, settlement_days: int = 1,
                       holiday_margin_days: int = 1) -> float:
    """Dollars from filled sells that have not settled as of `today` (YYYY-MM-DD)."""
    t = date.fromisoformat(today)
    look_from = weekdays_back(t, settlement_days + holiday_margin_days + 2).isoformat()
    total = 0.0
    for session, qty, px in conn.execute(
            "SELECT session, filled_quantity, avg_fill_price FROM orders WHERE side='SELL' "
            "AND mode=? AND state IN (?,?) AND session >= ? AND filled_quantity > 0",
            (mode, *FILLED, look_from)):
        settles = add_weekdays(date.fromisoformat(session[:10]), settlement_days + holiday_margin_days)
        if settles > t:
            total += float(qty or 0) * float(px or 0)
    return round(total, 2)


def day_trades(conn, today: str, mode: str, window: int = 5) -> int:
    """Day trades (same-session filled buy and sell of one symbol) in the last `window` weekdays."""
    start = weekdays_back(date.fromisoformat(today), window - 1).isoformat()
    rows = conn.execute(
        "SELECT session, symbol FROM orders WHERE mode=? AND state IN (?,?) AND filled_quantity > 0 "
        "AND session >= ? GROUP BY session, symbol HAVING SUM(side='BUY') > 0 AND SUM(side='SELL') > 0",
        (mode, *FILLED, start)).fetchall()
    return len(rows)


def annotate(conn, portfolio: dict | None, limits: dict, today: str, mode: str) -> dict | None:
    """Add the account-rule figures the risk engine checks. None stays None (fail closed upstream)."""
    if portfolio is None:
        return None
    kind = str(limits.get("account_type", "cash")).lower()
    out = dict(portfolio)
    out["account_type"] = kind
    if kind == "cash":
        ledger = unsettled_proceeds(
            conn, today, mode, int(limits.get("settlement_days", 1)),
            int(limits.get("holiday_margin_days", 1)))
        if "broker_unsettled" in portfolio:
            # A real account: sales made outside this system (a manual sell in
            # the app) settle too. Take the larger figure; if the broker's
            # cannot be read, leave settled cash unknown so buys are refused.
            b = portfolio["broker_unsettled"]
            if b is not None:
                out["unsettled_proceeds"] = max(ledger, float(b))
        else:
            out["unsettled_proceeds"] = ledger
    else:
        out["day_trades_5d"] = day_trades(conn, today, mode)
    return out


def check_buy(portfolio: dict, limits: dict, want: float) -> tuple:
    """
    (allowed_notional, reason). Called by the risk engine for BUYs only.

    Fails closed: a cash account whose unsettled figure is missing cannot be
    checked, so nothing is bought.
    """
    kind = str(limits.get("account_type", "cash")).lower()
    cash = float(portfolio.get("buying_power") or 0)
    if kind == "cash":
        if "unsettled_proceeds" not in portfolio:
            return 0.0, "settled cash unknown — cash-account buy refused rather than assumed"
        settled = max(0.0, cash - float(portfolio["unsettled_proceeds"]))
        if want > settled:
            return settled, (None if settled >= 1.0 else
                             f"only ${settled:,.2f} settled (${portfolio['unsettled_proceeds']:,.2f} "
                             f"unsettled): buying with unsettled funds risks a good-faith violation")
        return want, None
    if kind == "margin":
        eq = float(portfolio.get("equity") or 0)
        n = portfolio.get("day_trades_5d")
        if n is None:
            return 0.0, "day-trade count unknown — margin-account buy refused rather than assumed"
        if eq < PDT_EQUITY and n >= PDT_MAX_DAY_TRADES:
            return 0.0, (f"{n} day trades in 5 sessions with equity ${eq:,.0f} < $25,000: "
                         f"a same-day exit would breach the pattern-day-trader rule")
        return want, None
    return 0.0, f"unknown account_type {kind!r}"
