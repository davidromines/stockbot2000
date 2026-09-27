import runtime  # noqa: F401  (thread limits must be set before numpy/pandas import)

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

WEEK = timedelta(days=7)


def _pacific(iso_utc):
    """Pacific rendering is best-effort; a missing helper must not break the digest."""
    if not iso_utc:
        return ""
    try:
        from timefmt import pacific
        return pacific(iso_utc)
    except Exception:
        return iso_utc


def _load_json(root, name):
    path = os.path.join(root, "data", name)
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _table_exists(conn, name):
    try:
        row = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
        ).fetchone()
    except sqlite3.Error:
        return False
    return row is not None


def _rows(conn, sql, params=()):
    """A missing table leaves the section None rather than raising."""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return None


def _week_start(now):
    return (now - WEEK).strftime("%Y-%m-%dT%H:%M:%S")


def _collect_live(conn, start):
    rows = _rows(
        conn,
        "SELECT at, slot_id, symbol, action, quantity, price FROM slot_trades "
        "WHERE mode='LIVE' AND at >= ? ORDER BY at, id",
        (start,),
    )
    if rows is None:
        return None
    # A CLOSE is only a realised trade when the slot's preceding OPEN is known;
    # an unpaired CLOSE is dropped rather than counted at a guessed entry.
    open_by_slot = {}
    closed = 0
    net = 0.0
    wins = 0
    for at, slot_id, symbol, action, quantity, price in rows:
        if action == "OPEN":
            open_by_slot[slot_id] = (symbol, quantity, price)
        elif action == "CLOSE":
            prev = open_by_slot.pop(slot_id, None)
            if prev is None or prev[0] != symbol:
                continue
            _, qty, entry = prev
            if entry is None or price is None or qty is None:
                continue
            pnl = (price - entry) * qty
            closed += 1
            net += pnl
            if pnl > 0:
                wins += 1
    return {"closed": closed, "net_usd": net, "wins": wins}


def _collect_pipeline(conn, start):
    rows = _rows(
        conn,
        "SELECT to_state, COUNT(*) FROM strategy_decisions WHERE at >= ? GROUP BY to_state",
        (start,),
    )
    if rows is None:
        return None
    counts = {state: n for state, n in rows}
    return {
        "entered_paper": counts.get("PAPER", 0),
        "rejected": counts.get("REJECTED", 0),
        "qualified": counts.get("QUALIFIED", 0),
    }


def _collect_slots(conn, start):
    rows = _rows(
        conn,
        "SELECT a.at, a.slot_id, a.action, a.strategy_key, a.version, a.reason, "
        "s.name FROM slot_assignments a "
        "LEFT JOIN league_strategies s "
        "  ON s.strategy_key = a.strategy_key AND s.version = a.version "
        "WHERE a.at >= ? ORDER BY a.at, a.id",
        (start,),
    )
    if rows is None:
        return None
    out = []
    for at, slot_id, action, key, version, reason, name in rows:
        out.append(
            {
                "slot_id": slot_id,
                "action": action,
                "strategy": name or key,
                "reason": reason,
            }
        )
    return out


def _collect_top(conn):
    rows = _rows(conn, "SELECT MAX(date) FROM ranking_history")
    if rows is None or not rows or rows[0][0] is None:
        return None
    newest = rows[0][0]
    rows = _rows(
        conn,
        "SELECT r.strategy_key, r.score, s.name FROM ranking_history r "
        "LEFT JOIN league_strategies s "
        "  ON s.strategy_key = r.strategy_key AND s.version = r.version "
        "WHERE r.date = ? ORDER BY r.rank LIMIT 5",
        (newest,),
    )
    if rows is None:
        return None
    return [(name or key, score) for key, score, name in rows]


def collect(conn, now=None, root="."):
    if now is None:
        now = datetime.now(timezone.utc)
    start = _week_start(now)

    funnel = _load_json(root, "funnel.json")
    knowledge = _load_json(root, "knowledge_factory.json")

    funnel_section = None
    if funnel is not None:
        market = funnel.get("market") or {}
        unseen = market.get("unseen") or {}
        checks = market.get("checks") or {}
        failures = funnel.get("failures") or []
        funnel_section = {
            "unseen": unseen,
            "checks": checks,
            "near_misses": sum(1 for f in failures if f.get("near_miss")),
        }

    return {
        "live": _collect_live(conn, start),
        "pipeline": _collect_pipeline(conn, start),
        "knowledge": knowledge,
        "funnel": funnel_section,
        "slots": _collect_slots(conn, start),
        "top": _collect_top(conn),
    }


def _money(value):
    return "+${:,.2f}".format(value) if value >= 0 else "-${:,.2f}".format(-value)


def _pct(value):
    # Ranking scores are stored as fractions of the trade (0.0223 = +2.23% per trade).
    return "{:+.2f}%".format(value * 100)


def render(d):
    lines = []

    live = d.get("live")
    lines.append("Real account this week")
    if live is None:
        lines.append("  unavailable")
    elif live["closed"] == 0:
        lines.append("  no closed trades")
    else:
        lines.append(
            "  {} closed, net {}, {} wins".format(
                live["closed"], _money(live["net_usd"]), live["wins"]
            )
        )

    pipeline = d.get("pipeline")
    if pipeline is not None:
        lines.append("")
        lines.append("Research this week")
        lines.append(
            "  entered paper {}, rejected {}, qualified {}".format(
                pipeline["entered_paper"], pipeline["rejected"], pipeline["qualified"]
            )
        )

    knowledge = d.get("knowledge")
    if knowledge is not None:
        lines.append("")
        lines.append("Knowledge Factory")
        lines.append(
            "  translated {}, reproductions {}, variants {}".format(
                knowledge.get("translated", 0),
                knowledge.get("reproductions", 0),
                knowledge.get("variants", 0),
            )
        )

    funnel = d.get("funnel")
    if funnel is not None:
        unseen = funnel.get("unseen") or {}
        tested = unseen.get("tested")
        above = unseen.get("above_random")
        if tested is not None:
            lines.append("")
            lines.append("Unseen 2023\u2192today")
            lines.append("  {} of {} above random".format(above, tested))
        checks = funnel.get("checks") or {}
        bear = checks.get("bear_market")
        if bear:
            passed = bear.get("PASS", 0)
            failed = bear.get("FAIL", 0)
            lines.append("")
            lines.append("Bear-market check")
            lines.append("  {} pass / {} fail".format(passed, failed))
        near = funnel.get("near_misses")
        if near:
            lines.append("")
            lines.append("Near misses")
            lines.append("  {}".format(near))

    slots = d.get("slots")
    if slots:
        lines.append("")
        lines.append("Slot changes")
        for s in slots:
            lines.append(
                "  slot {} {} {} ({})".format(
                    s["slot_id"], s["action"], s["strategy"], s["reason"]
                )
            )

    top = d.get("top")
    if top:
        lines.append("")
        lines.append("Top of the ranking")
        for name, score in top:
            lines.append("  {} {}".format(name, _pct(score)))

    lines.append("")
    lines.append("Evidence, not advice.")
    return "\n".join(lines)


def send(conn, now=None, root=".", dry_run=False):
    text = render(collect(conn, now=now, root=root))
    if not dry_run:
        import notify
        notify.notify("Stockbot2000 weekly research", text)
    return text


def main(argv=None):
    parser = argparse.ArgumentParser(description="Weekly research digest")
    parser.add_argument("--send", action="store_true")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    try:
        text = send(conn, dry_run=not args.send or args.dry_run)
    finally:
        conn.close()
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
