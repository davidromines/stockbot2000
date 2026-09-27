"""
The strategy journal and leaderboard movement (Addendum D N3/N4, owner 2026-09-27).

Nothing here is a new record of what happened: every event already sits in an
append-only table. The journal assembles them per strategy, oldest first:

    registered      league_strategies (each version, with its definition)
    state           league_state (DISCOVERED -> ... -> PAPER, REJECTED, RETIRED)
    decision        strategy_decisions (promotions, rejections, data problems, why)
    slot            slot_assignments (assigned to / released from a slot, and why)
    trade           slot_trades (every SIMULATION / SHADOW / LIVE slot trade)
    paper           the forward fund's latest accounting (trades, dollars)
    rank            ranking_history (the one new table: a daily snapshot of the
                    ranking, so a strategy's movement can be seen at all)

    ./venv/bin/python journal.py --snapshot            # daily: record today's ranking
    ./venv/bin/python journal.py --movement            # biggest risers and fallers
    ./venv/bin/python journal.py --show fx_value_book_b87d80aeb1
    ./venv/bin/python journal.py --search "value book"
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import sqlite3
import sys


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS ranking_history (
            date TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL, rank INTEGER NOT NULL,
            score REAL, backtest REAL, forward REAL, forward_trades INTEGER, passes_gate INTEGER, state TEXT,
            PRIMARY KEY (date, strategy_key, version))""")
    conn.commit()


def _q(conn, sql, params=()) -> list:
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []


def snapshot(conn, cfg: dict, rows: list | None = None) -> int:
    """Record today's ranking (the newest price session). Idempotent per date."""
    import ranking
    init(conn)
    rows = rows if rows is not None else ranking.rank(conn, cfg)
    day = conn.execute("SELECT MAX(date) FROM prices WHERE ticker='SPY'").fetchone()[0]
    conn.execute("DELETE FROM ranking_history WHERE date=?", (day,))
    conn.executemany("INSERT INTO ranking_history VALUES (?,?,?,?,?,?,?,?,?,?)",
                     [(day, r["strategy_key"], r["version"], i, r.get("score"), r.get("backtest"), r.get("forward"),
                       r.get("forward_trades"), int(bool(r.get("passes_gate"))), r.get("state"))
                      for i, r in enumerate(rows, 1)])
    conn.commit()
    return len(rows)


def movement(conn, top: int = 25) -> dict:
    """The newest snapshot against the one before: rank change for the top, plus arrivals and exits."""
    init(conn)
    dates = [r[0] for r in _q(conn, "SELECT DISTINCT date FROM ranking_history ORDER BY date DESC LIMIT 2")]
    if not dates:
        return {"date": None, "previous": None, "top": [], "new": [], "gone": []}
    cur = {(k, v): (rk, sc) for k, v, rk, sc in _q(conn, "SELECT strategy_key, version, rank, score FROM "
                                                          "ranking_history WHERE date=?", (dates[0],))}
    prev = {(k, v): rk for k, v, rk in _q(conn, "SELECT strategy_key, version, rank FROM ranking_history "
                                                "WHERE date=?", (dates[1],))} if len(dates) > 1 else {}
    names = {(k, v): n for k, v, n in _q(conn, "SELECT strategy_key, version, name FROM league_strategies")}
    top_rows = sorted(cur.items(), key=lambda x: x[1][0])[:top]
    out = [{"strategy_key": k, "version": v, "name": names.get((k, v), k), "rank": rk, "score": sc,
            "change": (prev[(k, v)] - rk) if (k, v) in prev else None} for (k, v), (rk, sc) in top_rows]
    top_keys = {(r["strategy_key"], r["version"]) for r in out}
    new = [names.get(k, k[0]) for k in cur if prev and k not in prev and k in top_keys]
    gone = [names.get(k, k[0]) for k, rk in prev.items() if rk <= top and k not in cur]
    return {"date": dates[0], "previous": dates[1] if len(dates) > 1 else None, "top": out, "new": new, "gone": gone}


def search(conn, text: str, limit: int = 20) -> list:
    like = f"%{text.lower()}%"
    return [{"strategy_key": k, "version": v, "name": n, "family": f} for k, v, n, f in _q(
        conn, "SELECT strategy_key, version, name, family FROM league_strategies WHERE lower(name) LIKE ? OR "
              "lower(strategy_key) LIKE ? OR lower(family) LIKE ? ORDER BY strategy_key, version DESC LIMIT ?",
        (like, like, like, limit))]


def timeline(conn, key: str) -> dict:
    """Every recorded event for one strategy (all versions), oldest first."""
    init(conn)
    ev = []
    for v, at, name, fam, src in _q(conn, "SELECT version, created_at, name, family, source_kind FROM "
                                          "league_strategies WHERE strategy_key=?", (key,)):
        ev.append({"at": at, "kind": "registered", "version": v, "text": f"{name} ({fam}; from {src})"})
    for v, at, fr, to, why, actor in _q(conn, "SELECT version, at, from_state, to_state, reason, actor FROM "
                                             "league_state WHERE strategy_key=?", (key,)):
        ev.append({"at": at, "kind": "state", "version": v, "text": f"{fr or '—'} -> {to}: {why}"})
    for v, at, d, why in _q(conn, "SELECT version, at, decision, reason FROM strategy_decisions WHERE strategy_key=?",
                            (key,)):
        ev.append({"at": at, "kind": "decision", "version": v, "text": f"{d}: {why}"})
    for v, at, slot, act, mode, why in _q(conn, "SELECT version, at, slot_id, action, mode, reason FROM "
                                                "slot_assignments WHERE strategy_key=?", (key,)):
        ev.append({"at": at, "kind": "slot", "version": v, "text": f"slot {slot} {act}: {why}"})
    for v, at, mode, sym, act, q, px, why in _q(conn, "SELECT version, at, mode, symbol, action, quantity, price, "
                                                      "reason FROM slot_trades WHERE strategy_key=?", (key,)):
        ev.append({"at": at, "kind": f"trade {mode}", "version": v,
                   "text": f"{act} {sym} {q} @ {px}: {why}"})
    ev.sort(key=lambda e: str(e["at"]))
    ranks = [{"date": d, "version": v, "rank": rk, "score": sc} for d, v, rk, sc in _q(
        conn, "SELECT date, version, rank, score FROM ranking_history WHERE strategy_key=? ORDER BY date", (key,))]
    paper = None
    try:
        import leagues
        vers = [r[0] for r in _q(conn, "SELECT version FROM league_strategies WHERE strategy_key=? ORDER BY version "
                                       "DESC LIMIT 1", (key,))]
        if vers:
            e = leagues.evidence(conn, key, vers[0])
            if e.get("has_forward_record"):
                paper = {k: e.get(k) for k in ("fund_kind", "fund_id", "sessions", "closed_trades", "net_usd",
                                               "max_drawdown_pct", "as_of")}
    except Exception:                                        # noqa: BLE001 — a view never raises
        paper = None
    name = next((r[0] for r in _q(conn, "SELECT name FROM league_strategies WHERE strategy_key=? ORDER BY version "
                                        "DESC LIMIT 1", (key,))), key)
    return {"strategy_key": key, "name": name, "events": ev, "ranks": ranks, "paper": paper}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--snapshot", action="store_true")
    ap.add_argument("--movement", action="store_true")
    ap.add_argument("--show", metavar="KEY")
    ap.add_argument("--search", metavar="TEXT")
    a = ap.parse_args(argv)
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    conn.row_factory = sqlite3.Row
    init(conn)
    if a.snapshot:
        print(f"{snapshot(conn, cfg)} strategies recorded")
    if a.movement:
        m = movement(conn)
        print(f"ranking {m['date']} vs {m['previous']}")
        for r in m["top"]:
            ch = "new" if r["change"] is None else f"{r['change']:+d}"
            print(f"  {r['rank']:>3} {ch:>5}  {str(r['name'])[:44]:<44} {r['score'] or 0:+.2%}")
    if a.search:
        for r in search(conn, a.search):
            print(f"  {r['strategy_key']} v{r['version']}  {r['name']}")
    if a.show:
        t = timeline(conn, a.show)
        print(f"{t['name']}  ({a.show})")
        if t["paper"]:
            print(f"  paper: {json.dumps(t['paper'], default=str)}")
        for e in t["events"]:
            print(f"  {str(e['at'])[:19]}  v{e['version']}  {e['kind']:<16} {e['text'][:110]}")
        if t["ranks"]:
            print("  rank: " + ", ".join(f"{r['date']} #{r['rank']}" for r in t["ranks"][-10:]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
