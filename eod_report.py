"""End-of-day report (Addendum D §16, Stage N10).

Read-only: every section is derived from tables that other stages wrote. The
report never writes, never reconciles and never repairs — if a number looks
wrong here, the bug is upstream, and a report that silently fixed it would hide
that. Any missing table degrades its section to "no data" rather than raising,
because the owner reads this on a phone at the end of a session and a traceback
is strictly less useful than a partial report.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

from universe import load_config
import timefmt

SLOTS = (1, 2, 3, 4, 5)
STALE_MINUTES = 30
FAILURE_CAP = 20
RANKING_TOP = 10
LINE_WIDTH = 60

HEADINGS = [
    ("account", "ACCOUNT"),
    ("real_account", "REAL ACCOUNT SINCE START"),
    ("pnl", "P&L"),
    ("trades", "TRADES"),
    ("positions", "POSITIONS"),
    ("strategy_performance", "STRATEGY PERFORMANCE"),
    ("ranking", "RANKING"),
    ("replacements", "REPLACEMENTS"),
    ("research", "RESEARCH"),
    ("new_candidates", "NEW CANDIDATES"),
    ("failures", "FAILURES"),
    ("system_health", "SYSTEM HEALTH"),
    ("next_actions", "NEXT ACTIONS"),
]


def _rows(conn, sql, params=()):
    """Run a query, returning [] when the table (or column) does not exist.

    Missing tables are expected: a fresh database, or a stage that has not run
    yet, must not take the whole report down.
    """
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.Error:
        return []


def _one(conn, sql, params=()):
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _money(value):
    return None if value is None else round(float(value), 2)


def _pct(value):
    return None if value is None else round(float(value), 2)


def _today(conn, table, day, mode=None, extra=""):
    """Rows of `table` whose ISO UTC timestamp falls on `day`."""
    sql = "SELECT * FROM %s WHERE substr(at,1,10)=?" % table
    params = [day]
    if mode is not None:
        sql += " AND mode=?"
        params.append(mode)
    sql += extra
    return _rows(conn, sql, tuple(params))


def _open_positions(conn, mode):
    """Latest OPEN per slot with no later CLOSE for that slot.

    Ordering is by (at, id): two rows can share a timestamp, and the id is the
    only total order the table offers.
    """
    rows = _rows(
        conn,
        "SELECT * FROM slot_trades WHERE mode=? ORDER BY at, id",
        (mode,),
    )
    open_by_slot = {}
    for row in rows:
        slot = row["slot_id"]
        if row["action"] == "OPEN":
            open_by_slot[slot] = row
        elif row["action"] == "CLOSE":
            open_by_slot.pop(slot, None)
    return open_by_slot


def _latest_marks(conn, mode):
    marks = {}
    for row in _rows(
        conn,
        "SELECT * FROM slot_marks WHERE mode=? ORDER BY at, id",
        (mode,),
    ):
        marks[row["slot_id"]] = row
    return marks


def _assigned_slots(conn, mode):
    """Latest ASSIGN per slot with no later RELEASE."""
    assigned = {}
    for row in _rows(
        conn,
        # Slot assignments are one roster for every mode (slots.py records them
        # under SIMULATION even while LIVE trades them): never filter by mode.
        "SELECT * FROM slot_assignments ORDER BY at, id",
        (),
    ):
        if row["action"] == "ASSIGN":
            assigned[row["slot_id"]] = row
        elif row["action"] == "RELEASE":
            assigned.pop(row["slot_id"], None)
    return assigned


def _realized_gross(conn, day, mode):
    """Gross realized P&L for today's closes.

    Each CLOSE is matched to the price of that slot's most recent OPEN at or
    before it. This is GROSS: costs are not netted here (see accounting.py).
    """
    rows = _rows(
        conn,
        "SELECT * FROM slot_trades WHERE mode=? AND substr(at,1,10)<=? "
        "ORDER BY at, id",
        (mode, day),
    )
    last_open = {}
    total = 0.0
    n_closed = 0
    for row in rows:
        slot = row["slot_id"]
        if row["action"] == "OPEN":
            last_open[slot] = row
        elif row["action"] == "CLOSE" and row["at"][:10] == day:
            entry = last_open.get(slot)
            if entry is None or entry["price"] is None or row["price"] is None:
                continue
            total += (row["price"] - entry["price"]) * row["quantity"]
            n_closed += 1
    return total, n_closed


def _section_account(conn, day, mode):
    equity_row = _one(
        conn,
        "SELECT * FROM live_equity WHERE session=? ORDER BY at DESC LIMIT 1",
        (day,),
    )
    prev_row = _one(
        conn,
        "SELECT * FROM live_equity WHERE session<? ORDER BY session DESC, at DESC "
        "LIMIT 1",
        (day,),
    )
    run = _one(
        conn,
        "SELECT * FROM trader_runs WHERE mode=? ORDER BY at DESC, id DESC LIMIT 1",
        (mode,),
    )
    equity = equity_row["equity"] if equity_row else None
    prev_equity = prev_row["equity"] if prev_row else None
    return {
        "equity": _money(equity),
        "buying_power": _money(equity_row["buying_power"]) if equity_row else None,
        "cash": _money(run["cash"]) if run else None,
        "unsettled": _money(run["unsettled"]) if run else None,
        "prev_session": prev_row["session"] if prev_row else None,
        "prev_equity": _money(prev_equity),
        "equity_change": _money(equity - prev_equity)
        if equity is not None and prev_equity is not None
        else None,
    }


def _section_pnl(conn, day, mode, account, positions):
    realized, n_closed = _realized_gross(conn, day, mode)
    unrealized = 0.0
    have_unrealized = False
    for pos in positions:
        if pos["mark"] is None or pos["entry_price"] is None:
            continue
        unrealized += (pos["mark"] - pos["entry_price"]) * pos["quantity"]
        have_unrealized = True
    return {
        "realized_gross": _money(realized),
        "closed_trades": n_closed,
        "unrealized_gross": _money(unrealized) if have_unrealized else None,
        "net_equity_change": account["equity_change"],
        "costs": "not separated here (see accounting.py)",
    }


def _section_trades(conn, day, mode):
    out = []
    for row in _today(conn, "slot_trades", day, mode, " ORDER BY at, id"):
        out.append(
            {
                "time": row["at"],
                "slot": row["slot_id"],
                "action": row["action"],
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "price": _money(row["price"]),
                "reason": row["reason"],
            }
        )
    return out


def _section_positions(conn, mode):
    marks = _latest_marks(conn, mode)
    out = []
    for slot in sorted(_open_positions(conn, mode)):
        row = _open_positions(conn, mode)[slot]
        mark_row = marks.get(slot)
        mark = mark_row["price"] if mark_row else None
        stop = mark_row["stop"] if mark_row else None
        entry = row["price"]
        unreal_pct = None
        if mark is not None and entry:
            unreal_pct = (mark - entry) / entry * 100.0
        out.append(
            {
                "slot": slot,
                "symbol": row["symbol"],
                "quantity": row["quantity"],
                "entry_price": _money(entry),
                "mark": _money(mark),
                "stop": _money(stop),
                "unrealized_pct": _pct(unreal_pct),
            }
        )
    return out


def _section_strategy_performance(conn, mode, ranking):
    by_key = {}
    for row in ranking:
        by_key[row.get("strategy_key")] = row
    out = []
    for slot in sorted(_assigned_slots(conn, mode)):
        assign = _assigned_slots(conn, mode)[slot]
        key = assign["strategy_key"]
        rank_row = by_key.get(key)
        if rank_row is None:
            out.append({"slot": slot, "strategy_key": key, "status": "not ranked"})
        else:
            out.append(
                {
                    "slot": slot,
                    "strategy_key": key,
                    "status": "ranked",
                    "score": rank_row.get("score"),
                    "backtest": rank_row.get("backtest"),
                    "forward": rank_row.get("forward"),
                    "forward_trades": rank_row.get("forward_trades"),
                }
            )
    return out


def _section_ranking(ranking):
    out = []
    for row in ranking[:RANKING_TOP]:
        out.append(
            {
                "name": row.get("name"),
                "strategy_key": row.get("strategy_key"),
                "score": row.get("score"),
                "backtest": row.get("backtest"),
                "forward": row.get("forward"),
                "forward_trades": row.get("forward_trades"),
                "passes_gate": row.get("passes_gate"),
                "gate": row.get("gate"),
            }
        )
    return out


def _section_replacements(conn, day, mode):
    out = []
    for row in _today(conn, "slot_assignments", day, None, " ORDER BY at, id"):
        out.append(
            {
                "time": row["at"],
                "slot": row["slot_id"],
                "action": row["action"],
                "strategy_key": row["strategy_key"],
                "version": row["version"],
                "capital_usd": _money(row["capital_usd"]),
                "reason": row["reason"],
            }
        )
    return out


def _section_research(conn, day):
    counts = {}
    for row in _today(conn, "strategy_decisions", day):
        counts[row["decision"]] = counts.get(row["decision"], 0) + 1
    return counts


def _section_new_candidates(conn, day):
    out = []
    for row in _today(conn, "league_state", day, None, " ORDER BY at, id"):
        if row["to_state"] == "PAPER":
            out.append(
                {
                    "time": row["at"],
                    "strategy_key": row["strategy_key"],
                    "version": row["version"],
                    "from_state": row["from_state"],
                    "reason": row["reason"],
                }
            )
    return out


def _section_failures(conn, day, mode):
    rejections = []
    for row in _today(conn, "risk_events", day, None, " ORDER BY at, id"):
        if row["decision"] != "APPROVED":
            rejections.append(
                {
                    "time": row["at"],
                    "symbol": row["symbol"],
                    "decision": row["decision"],
                    "reasons": row["reasons"],
                }
            )
    events = []
    for row in _today(conn, "system_events", day, None, " ORDER BY at, id"):
        if row["severity"] in ("critical", "warning"):
            events.append(
                {
                    "time": row["at"],
                    "kind": row["kind"],
                    "severity": row["severity"],
                    "detail": row["detail"],
                }
            )
    bad_runs = []
    for row in _today(conn, "trader_runs", day, mode, " ORDER BY at, id"):
        if row["outcome"] != "ok":
            bad_runs.append(
                {
                    "time": row["at"],
                    "outcome": row["outcome"],
                    "error": row["error"],
                }
            )
    return {
        "risk_rejections": rejections[:FAILURE_CAP],
        "system_events": events[:FAILURE_CAP],
        "bad_runs": bad_runs[:FAILURE_CAP],
        "n_risk_rejections": len(rejections),
    }


def _section_system_health(conn, now):
    """Latest trader_runs row per mode, and whether it is stale.

    Staleness is measured against `now`, not against the report day: a report
    generated at 20:00 about a run at 09:35 is stale even though both are
    "today".
    """
    modes = [r["mode"] for r in _rows(conn, "SELECT DISTINCT mode FROM trader_runs")]
    out = {}
    for mode in modes:
        row = _one(
            conn,
            "SELECT * FROM trader_runs WHERE mode=? ORDER BY at DESC, id DESC LIMIT 1",
            (mode,),
        )
        if row is None:
            continue
        stale = None
        try:
            at = datetime.strptime(row["at"], "%Y-%m-%dT%H:%M:%S").replace(
                tzinfo=timezone.utc
            )
            stale = (now - at) > timedelta(minutes=STALE_MINUTES)
        except (TypeError, ValueError):
            stale = None
        out[mode] = {
            "at": row["at"],
            "outcome": row["outcome"],
            "reconciled": row["reconciled"],
            "stale": stale,
        }
    return out


def _section_next_actions(conn, mode, failures, system_health):
    actions = []
    assigned = _assigned_slots(conn, mode)
    for slot in SLOTS:
        if slot not in assigned:
            actions.append("slot %d is empty" % slot)
    latest = system_health.get(mode)
    if latest is not None and latest["reconciled"] == 0:
        actions.append("reconciliation failed in the last run")
    if failures["n_risk_rejections"] > 0:
        actions.append("%d risk rejection(s) today" % failures["n_risk_rejections"])
    if latest is not None and latest["stale"]:
        actions.append("trader heartbeat stale")
    if not actions:
        actions.append("none")
    return actions


def _section_real_account(conn, mode):
    """What the system has made in the real account: slot trades only (live_pnl.py).
    Never a sum across paper funds (owner, 2026-09-26)."""
    import live_pnl
    try:
        return live_pnl.render(live_pnl.compute(conn, load_config(), mode))
    except sqlite3.Error:
        return []


def build(conn, day, mode="LIVE", rank_fn=None, now=None):
    """Assemble the twelve sections. Read-only; never raises on missing tables."""
    if now is None:
        now = datetime.now(timezone.utc)
    ranking = list(rank_fn(conn)) if rank_fn is not None else []
    account = _section_account(conn, day, mode)
    positions = _section_positions(conn, mode)
    failures = _section_failures(conn, day, mode)
    system_health = _section_system_health(conn, now)
    return {
        "account": account,
        "real_account": _section_real_account(conn, mode),
        "pnl": _section_pnl(conn, day, mode, account, positions),
        "trades": _section_trades(conn, day, mode),
        "positions": positions,
        "strategy_performance": _section_strategy_performance(conn, mode, ranking),
        "ranking": _section_ranking(ranking),
        "replacements": _section_replacements(conn, day, mode),
        "research": _section_research(conn, day),
        "new_candidates": _section_new_candidates(conn, day),
        "failures": failures,
        "system_health": system_health,
        "next_actions": _section_next_actions(conn, mode, failures, system_health),
    }


def _fmt(value):
    if value is None:
        return "n/a"
    if isinstance(value, float):
        return "%.2f" % value
    return str(value)


def _wrap(text, width=LINE_WIDTH):
    """Wrap to `width` at word boundaries (hard-split only a word longer than a line);
    the owner reads this on a phone."""
    import textwrap
    text = str(text)
    if len(text) <= width:
        return [text]
    return textwrap.wrap(text, width, subsequent_indent="  ", break_long_words=True,
                         break_on_hyphens=False) or [""]


def _emit(lines, text):
    lines.extend(_wrap(text))


def render(report):
    lines = []

    def head(key, title):
        lines.append("")
        lines.append("== %s ==" % title)

    head("account", "ACCOUNT")
    a = report["account"]
    _emit(lines, "equity %s  bp %s" % (_fmt(a["equity"]), _fmt(a["buying_power"])))
    _emit(lines, "cash %s  unsettled %s" % (_fmt(a["cash"]), _fmt(a["unsettled"])))
    _emit(lines, "change vs %s: %s" % (a["prev_session"] or "n/a", _fmt(a["equity_change"])))

    head("real_account", "REAL ACCOUNT SINCE START")
    if not report.get("real_account"):
        _emit(lines, "no data")
    for line in report.get("real_account") or []:
        _emit(lines, line)

    head("pnl", "P&L")
    p = report["pnl"]
    _emit(lines, "realized gross %s (%d closed)" % (_fmt(p["realized_gross"]), p["closed_trades"]))
    _emit(lines, "unrealized gross %s" % _fmt(p["unrealized_gross"]))
    _emit(lines, "net equity change %s" % _fmt(p["net_equity_change"]))
    _emit(lines, "costs %s" % p["costs"])

    head("trades", "TRADES")
    if not report["trades"]:
        _emit(lines, "no data")
    for t in report["trades"]:
        _emit(
            lines,
            "%s s%s %s %s %s @ %s"
            % (timefmt.pt(t["time"]), t["slot"], t["action"], t["symbol"], t["quantity"], _fmt(t["price"])),
        )
        _emit(lines, "  %s" % t["reason"])

    head("positions", "POSITIONS")
    if not report["positions"]:
        _emit(lines, "no data")
    for pos in report["positions"]:
        _emit(
            lines,
            "s%s %s qty %s entry %s mark %s"
            % (pos["slot"], pos["symbol"], pos["quantity"], _fmt(pos["entry_price"]), _fmt(pos["mark"])),
        )
        _emit(lines, "  stop %s  unreal %s%%" % (_fmt(pos["stop"]), _fmt(pos["unrealized_pct"])))

    head("strategy_performance", "STRATEGY PERFORMANCE")
    if not report["strategy_performance"]:
        _emit(lines, "no data")
    for row in report["strategy_performance"]:
        if row["status"] == "not ranked":
            _emit(lines, "s%s %s not ranked" % (row["slot"], row["strategy_key"]))
        else:
            _emit(
                lines,
                "s%s %s score %s" % (row["slot"], row["strategy_key"], _fmt(row["score"])),
            )
            _emit(
                lines,
                "  bt %s fwd %s (%s)"
                % (_fmt(row["backtest"]), _fmt(row["forward"]), _fmt(row["forward_trades"])),
            )

    head("ranking", "RANKING")
    if not report["ranking"]:
        _emit(lines, "no data")
    for i, row in enumerate(report["ranking"], 1):
        _emit(lines, "%d. %s score %s" % (i, row["name"], _fmt(row["score"])))
        _emit(
            lines,
            "  bt %s fwd %s (%s) gate %s"
            % (_fmt(row["backtest"]), _fmt(row["forward"]), _fmt(row["forward_trades"]), row["passes_gate"]),
        )

    head("replacements", "REPLACEMENTS")
    if not report["replacements"]:
        _emit(lines, "no data")
    for r in report["replacements"]:
        _emit(
            lines,
            "%s s%s %s %s v%s" % (timefmt.pt(r["time"]), r["slot"], r["action"], r["strategy_key"], r["version"]),
        )
        _emit(lines, "  %s" % r["reason"])

    head("research", "RESEARCH")
    if not report["research"]:
        _emit(lines, "no data")
    for decision, count in sorted(report["research"].items()):
        _emit(lines, "%s: %d" % (decision, count))

    head("new_candidates", "NEW CANDIDATES")
    if not report["new_candidates"]:
        _emit(lines, "no data")
    for c in report["new_candidates"]:
        _emit(lines, "%s %s v%s -> PAPER" % (timefmt.pt(c["time"]), c["strategy_key"], c["version"]))

    head("failures", "FAILURES")
    f = report["failures"]
    if not (f["risk_rejections"] or f["system_events"] or f["bad_runs"]):
        _emit(lines, "no data")
    for r in f["risk_rejections"]:
        _emit(lines, "risk %s %s %s" % (timefmt.pt(r["time"]), r["symbol"], r["decision"]))
    for e in f["system_events"]:
        _emit(lines, "%s %s %s" % (e["severity"], e["kind"], timefmt.pt(e["time"])))
    for b in f["bad_runs"]:
        _emit(lines, "run %s %s" % (timefmt.pt(b["time"]), b["outcome"]))

    head("system_health", "SYSTEM HEALTH")
    if not report["system_health"]:
        _emit(lines, "no data")
    for mode, h in sorted(report["system_health"].items()):
        _emit(
            lines,
            "%s %s %s recon %s stale %s"
            % (mode, timefmt.pt(h["at"]), h["outcome"], h["reconciled"], h["stale"]),
        )

    head("next_actions", "NEXT ACTIONS")
    for action in report["next_actions"]:
        _emit(lines, "- %s" % action)

    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="End-of-day report")
    parser.add_argument("--day", default=datetime.now(timezone.utc).strftime("%Y-%m-%d"))
    parser.add_argument("--mode", default="LIVE")
    parser.add_argument("--send", action="store_true")
    args = parser.parse_args(argv)

    config = load_config()
    db_path = config["database"]["market_data_path"]
    conn = sqlite3.connect("file:%s?mode=ro" % db_path, uri=True)
    conn.row_factory = sqlite3.Row
    try:
        import ranking

        report = build(conn, args.day, args.mode, rank_fn=lambda c: ranking.rank(c, config))
    finally:
        conn.close()

    text = render(report)
    print(text)

    if args.send:
        try:
            import notify

            notify.notify("Stockbot2000 end of day", text)
        except Exception as exc:  # delivery must never break the report
            print("notify failed: %s" % exc, file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
