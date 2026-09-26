"""Stage N5: operational health of a strategy from its forward paper record.

The state is a comparison of what a strategy is doing now against what its own
backtest promised. It is deliberately not a performance score: a strategy can
be HEALTHY while losing money if its backtest also lost money, and FAILED while
profitable if it breached its league drawdown limit.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from universe import load_config

DEFAULTS = {
    "window": 20,
    "min_watch": 5,
    "min_degrading": 10,
    "min_failed": 20,
    "degrading_fraction": 0.5,
    "dd_watch": 0.5,
    "dd_degrading": 0.75,
    "freq_drop": 0.5,
}

DEFAULT_DD_LIMIT = 15.0  # percent; used when the league has no configured limit

SCHEMA = """
CREATE TABLE IF NOT EXISTS strategy_health (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    at           TEXT NOT NULL,
    strategy_key TEXT NOT NULL,
    version      INTEGER NOT NULL,
    state        TEXT NOT NULL,
    reason       TEXT NOT NULL,
    metrics      TEXT
)
"""


def init(conn):
    conn.execute(SCHEMA)
    conn.commit()


def _now(now=None):
    if now is None:
        return datetime.now(timezone.utc).isoformat()
    if isinstance(now, datetime):
        return now.isoformat()
    return str(now)


def run_id_for(conn, key, version):
    """Map a strategy key to the paper run that measures it, or None.

    Only two key families are measured here. Everything else (pair:, value:,
    crypto:) has no forward paper record in this schema, and returning a
    guessed run id would silently attribute another fund's trades to it.
    """
    if key is None:
        return None
    if key.startswith("paper:"):
        return key.split(":", 1)[1] or None
    if key.startswith("fx_"):
        row = conn.execute(
            "SELECT run_id FROM factory_paper_link WHERE strategy_key=? AND version=?",
            (key, version),
        ).fetchone()
        return row["run_id"] if row else None
    return None


def _closed_trades(conn, run_id):
    rows = conn.execute(
        "SELECT ticker, entry_date, exit_date, entry_price, shares, net_pnl_usd "
        "FROM paper_trades WHERE run_id=? AND exit_date IS NOT NULL "
        "ORDER BY exit_date, ticker",
        (run_id,),
    ).fetchall()
    out = []
    for r in rows:
        shares = r["shares"]
        entry = r["entry_price"]
        net = r["net_pnl_usd"]
        if shares in (None, 0) or entry in (None, 0) or net is None:
            # A trade whose per-trade return cannot be computed is dropped
            # rather than counted as zero: zero would bias the rolling mean
            # toward "no degradation".
            continue
        out.append({"exit_date": r["exit_date"], "ret": net / (shares * entry)})
    return out


def _max_drawdown_pct(conn, run_id):
    rows = conn.execute(
        "SELECT date, equity_usd FROM paper_equity WHERE run_id=? ORDER BY date",
        (run_id,),
    ).fetchall()
    peak = None
    worst = 0.0
    for r in rows:
        eq = r["equity_usd"]
        if eq is None:
            continue
        if peak is None or eq > peak:
            peak = eq
        if peak and peak > 0:
            dd = (peak - eq) / peak * 100.0
            if dd > worst:
                worst = dd
    return worst if peak is not None else None


def _count_window(trades, start, end):
    n = 0
    for t in trades:
        d = t["exit_date"]
        if d is None:
            continue
        if start <= d < end:
            n += 1
    return n


def metrics(conn, run_id):
    """Forward-record metrics for one paper run. None where not computable."""
    out = {
        "n": 0,
        "roll": None,
        "allt": None,
        "win_rate_roll": None,
        "dd": None,
        "recent_60d": None,
        "prior_60d": None,
    }
    if run_id is None:
        return out
    trades = _closed_trades(conn, run_id)
    n = len(trades)
    out["n"] = n
    if n:
        out["allt"] = sum(t["ret"] for t in trades) / n
    out["dd"] = _max_drawdown_pct(conn, run_id)
    if n:
        last_exit = max(t["exit_date"] for t in trades)
        try:
            end = datetime.strptime(last_exit, "%Y-%m-%d").date()
        except (TypeError, ValueError):
            end = None
        if end is not None:
            recent_start = (end - timedelta(days=59)).isoformat()
            prior_start = (end - timedelta(days=119)).isoformat()
            out["recent_60d"] = _count_window(trades, recent_start, last_exit + "\uffff")
            out["prior_60d"] = _count_window(trades, prior_start, recent_start)
    return out


def _roll_metrics(conn, run_id, window):
    """Rolling mean and win rate over the last `window` closed trades."""
    trades = _closed_trades(conn, run_id)
    if not trades:
        return None, None
    tail = trades[-window:] if window and window > 0 else trades
    roll = sum(t["ret"] for t in tail) / len(tail)
    wins = sum(1 for t in tail if t["ret"] > 0)
    return roll, wins / len(tail)


def classify(m, bt, lim, s):
    """Return (state, reason). First matching rule wins, in the order below."""
    n = m.get("n") or 0
    roll = m.get("roll")
    allt = m.get("allt")
    dd = m.get("dd")
    lim = lim if lim is not None else DEFAULT_DD_LIMIT

    if dd is not None and lim and dd >= lim:
        return "FAILED", "drawdown %.2f%% >= league limit %.2f%%" % (dd, lim)
    if n >= s["min_failed"] and roll is not None and allt is not None and roll < 0 and allt < 0:
        return "FAILED", "n=%d rolling %.4f%% and all-time %.4f%% both negative" % (
            n, roll * 100, allt * 100)

    if dd is not None and lim and dd >= s["dd_degrading"] * lim:
        return "DEGRADING", "drawdown %.2f%% >= %.2f%% of league limit %.2f%%" % (
            dd, s["dd_degrading"] * 100, lim)
    if n >= s["min_degrading"] and bt is not None and roll is not None and roll < s["degrading_fraction"] * bt:
        return "DEGRADING", "n=%d rolling %.4f%% < %.2f x backtest %.4f%%" % (
            n, roll * 100, s["degrading_fraction"], bt * 100)

    if dd is not None and lim and dd >= s["dd_watch"] * lim:
        return "WATCH", "drawdown %.2f%% >= %.2f%% of league limit %.2f%%" % (
            dd, s["dd_watch"] * 100, lim)
    if n >= s["min_watch"] and bt is not None and roll is not None and roll < bt:
        return "WATCH", "n=%d rolling %.4f%% < backtest %.4f%%" % (n, roll * 100, bt * 100)
    recent = m.get("recent_60d")
    prior = m.get("prior_60d")
    if (n >= 2 * s["window"] and recent is not None and prior is not None
            and recent < s["freq_drop"] * prior):
        return "WATCH", "trade frequency fell: %d in last 60d vs %d prior" % (recent, prior)

    if n < s["min_watch"]:
        return "HEALTHY", "insufficient evidence (n < min_watch)"
    return "HEALTHY", "within expectations"


def _settings(cfg):
    s = dict(DEFAULTS)
    s.update((cfg or {}).get("strategy_health") or {})
    return s


def _dd_limit(cfg, league):
    leagues = (cfg or {}).get("leagues") or {}
    entry = leagues.get(league) or {}
    lim = entry.get("max_drawdown_pct")
    return DEFAULT_DD_LIMIT if lim is None else lim


def evaluate(conn, cfg, rank_rows, now=None):
    s = _settings(cfg)
    results = []
    for row in rank_rows or []:
        key = row.get("strategy_key")
        version = row.get("version")
        run_id = run_id_for(conn, key, version)
        if run_id is None:
            results.append({
                "strategy_key": key, "version": version, "name": row.get("name"),
                "state": "HEALTHY",
                "reason": "not measured (no paper trades table for this fund kind)",
                "metrics": None,
            })
            continue
        m = metrics(conn, run_id)
        roll, win_rate = _roll_metrics(conn, run_id, s["window"])
        m["roll"] = roll
        m["win_rate_roll"] = win_rate
        bt = row.get("backtest")
        lim = _dd_limit(cfg, row.get("league"))
        state, reason = classify(m, bt, lim, s)
        results.append({
            "strategy_key": key, "version": version, "name": row.get("name"),
            "state": state, "reason": reason, "metrics": m,
        })
    return results


def record(conn, results, now=None):
    at = _now(now)
    written = 0
    for r in results:
        key = r.get("strategy_key")
        version = r.get("version")
        state = r.get("state")
        prev = conn.execute(
            "SELECT state FROM strategy_health WHERE strategy_key=? AND version=? "
            "ORDER BY id DESC LIMIT 1",
            (key, version),
        ).fetchone()
        if prev is not None and prev["state"] == state:
            continue
        conn.execute(
            "INSERT INTO strategy_health (at, strategy_key, version, state, reason, metrics) "
            "VALUES (?,?,?,?,?,?)",
            (at, key, version, state, r.get("reason"),
             json.dumps(r.get("metrics"), sort_keys=True) if r.get("metrics") is not None else None),
        )
        written += 1
    conn.commit()
    return written


def latest(conn):
    out = {}
    rows = conn.execute(
        "SELECT strategy_key, version, state, reason, at FROM strategy_health ORDER BY id"
    ).fetchall()
    for r in rows:
        out[(r["strategy_key"], r["version"])] = (r["state"], r["reason"], r["at"])
    return out


def _connect():
    conn = sqlite3.connect(load_config()["database"]["market_data_path"])
    conn.row_factory = sqlite3.Row
    return conn


def main(argv=None):
    ap = argparse.ArgumentParser(description="Strategy health (Stage N5)")
    ap.add_argument("--run", action="store_true", help="evaluate and record")
    ap.add_argument("--report", action="store_true", help="print current health")
    args = ap.parse_args(argv)

    conn = _connect()
    try:
        init(conn)
        if args.run:
            from ranking import rank
            cfg = load_config()
            rows = rank(conn, cfg)
            results = evaluate(conn, cfg, rows)
            n = record(conn, results)
            print("recorded %d state change(s) across %d strategies" % (n, len(results)))
        if args.report:
            cfg = load_config()
            from ranking import rank
            rows = rank(conn, cfg)
            results = evaluate(conn, cfg, rows)
            for r in results:
                m = r.get("metrics") or {}
                bt = None
                for row in rows:
                    if row.get("strategy_key") == r["strategy_key"] and row.get("version") == r["version"]:
                        bt = row.get("backtest")
                        break
                def pct(v):
                    return "n/a" if v is None else "%.2f%%" % (v * 100)
                print("%-10s %-28s n=%-4s roll=%-9s bt=%-9s dd=%s" % (
                    r["state"], (r.get("name") or r.get("strategy_key") or "")[:28],
                    m.get("n", 0), pct(m.get("roll")), pct(bt),
                    "n/a" if m.get("dd") is None else "%.2f%%" % m["dd"]))
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
