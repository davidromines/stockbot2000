"""
How long a strategy's trades last — so strategies can be compared per day held.

The ranking scored every strategy on net return PER TRADE. A trade held a year and a
trade held a week are not the same unit: ETF rotation (monthly holds) and crypto trend
(30-60 days) looked many times better than 20-60 day stock strategies on that scale
alone. ranking.py now scales every per-trade figure to a common 20-session holding
(`ranking.normalize_hold_days`), using the average holding period estimated here.

Sources, best first (each strategy's estimate names its source):

    paper     its own closed paper trades (>= MIN_TRADES), entry to exit in sessions
    measured  a simulation's average hold (simulator.avg_hold_days) recorded by the
              factory backtest, the unseen-window test, the diversity check, the
              rotation backtest, or crypto_backtests.mean_bars
    rule      the strategy's own maximum hold (risk.max_hold_days) — an upper bound, so
              a strategy that usually exits early is under-credited, never over-credited
    default   DEFAULT_DAYS for a fund with no rule (pair / value funds)
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import datetime as dt
import sqlite3

MIN_TRADES = 30          # fewer paper trades are too noisy to set a strategy's unit of time
DEFAULT_DAYS = 60.0
FLOOR = 1.0
SESSIONS_PER_DAY = 252 / 365.25


def init(conn) -> None:
    conn.execute("""CREATE TABLE IF NOT EXISTS strategy_hold (
        strategy_key TEXT NOT NULL, version INTEGER NOT NULL, avg_hold_days REAL NOT NULL,
        source TEXT NOT NULL, computed_at TEXT NOT NULL, PRIMARY KEY (strategy_key, version))""")
    conn.commit()


def record(conn, key: str, ver: int, days, source: str) -> None:
    """Store a measured average hold (sessions). A zero / missing value is not a measurement."""
    try:
        days = float(days)
    except (TypeError, ValueError):
        return
    if not days or days != days or days <= 0:
        return
    init(conn)
    conn.execute("INSERT OR REPLACE INTO strategy_hold VALUES (?,?,?,?,?)",
                 (key, int(ver), days, source, dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")))


def _paper(conn, key: str, ver: int):
    import leagues
    try:
        ref = leagues.fund_ref(conn, key, ver)
    except sqlite3.Error:
        return None
    if not ref or ref[0] != "paper":
        return None
    try:
        rows = conn.execute("SELECT entry_date, exit_date FROM paper_trades WHERE run_id=?", (ref[1],)).fetchall()
    except sqlite3.Error:
        return None
    if len(rows) < MIN_TRADES:
        return None
    days = [(dt.date.fromisoformat(str(b)[:10]) - dt.date.fromisoformat(str(a)[:10])).days for a, b in rows]
    return max(FLOOR, sum(days) / len(days) * SESSIONS_PER_DAY)


def estimate(conn, key: str, ver: int, genome: dict | None = None) -> tuple:
    """(average hold in sessions, source)."""
    p = _paper(conn, key, ver)
    if p:
        return p, "paper"
    try:
        r = conn.execute("SELECT avg_hold_days, source FROM strategy_hold WHERE strategy_key=? AND version=?",
                         (key, ver)).fetchone()
    except sqlite3.Error:
        r = None
    if r and r[0]:
        return max(FLOOR, float(r[0])), f"measured ({r[1]})"
    if key.startswith("crypto:"):
        try:
            import json
            st = json.loads((conn.execute("SELECT strategy FROM crypto_fund WHERE name=?",
                                          (key.split(":", 1)[1],)).fetchone() or ["{}"])[0])
            row = conn.execute("SELECT mean_bars FROM crypto_backtests WHERE strategy_id=?",
                               (st.get("strategy_id"),)).fetchone()
            if row and row[0]:
                return max(FLOOR, float(row[0]) * SESSIONS_PER_DAY), "measured (crypto_backtests)"
        except Exception:                                    # noqa: BLE001
            pass
    if key.startswith("option:"):
        try:
            import options_lab
            h = options_lab.STRATEGIES.get(key.split(":", 1)[1], {}).get("hold")
            if h:
                return float(h), "rule"
        except Exception:                                    # noqa: BLE001
            pass
    mh = ((genome or {}).get("risk") or {}).get("max_hold_days")
    if mh and "rotation" not in (genome or {}):
        return max(FLOOR, float(mh)), "rule"
    return DEFAULT_DAYS, "default"
