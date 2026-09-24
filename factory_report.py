"""Daily Strategy Factory report (Phase 13 §36) and global strategy scoreboard (§17).

Read-only over existing tables. Every money line shows GROSS, COSTS and NET side
by side (Addendum B §B5); benchmarks are informational (§B20). A missing figure
renders as an em dash and the row is kept.
"""
import runtime  # noqa: F401  — must precede numpy/pandas; they read thread limits at import.
import argparse
import json
import sqlite3
import sys
from datetime import datetime, timedelta, timezone

DASH = "\u2014"
FORWARD_STATES = ("PAPER", "QUALIFIED", "LIVE_CANDIDATE", "LIVE", "DEMOTED")
# strategy_metrics phases that measure a forward record. Backtest phases never fill a
# forward row: a forward scoreboard showing backtest profit is the defect this guards.
FORWARD_PHASES = ("paper", "forward", "live")
BACKTESTED_OR_LATER = ("BACKTESTED", "VALIDATED", "PROMISING", "PAPER", "QUALIFIED",
                       "LIVE_CANDIDATE", "LIVE", "DEMOTED")


def _table_exists(conn, name):
    """True if `name` is a table or view in the attached database."""
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type IN ('table','view') AND name=?",
        (name,)).fetchone()
    return row is not None


def _unquote(value):
    """Strip one layer of surrounding double quotes from a JSON-encoded text column."""
    if value is None:
        return None
    if isinstance(value, str) and len(value) >= 2 and value[0] == '"' and value[-1] == '"':
        try:
            return json.loads(value)
        except (ValueError, TypeError):
            return value[1:-1]
    return value


def _num(value):
    """Coerce to float, or None. Non-numeric text is treated as missing, not zero."""
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _latest_metrics(conn, key, version, phases=None):
    """Most recent strategy_metrics row for a strategy, optionally restricted to phases."""
    sql = ("SELECT * FROM strategy_metrics WHERE strategy_key=? AND version=?")
    params = [key, version]
    if phases:
        sql += " AND phase IN (%s)" % ",".join("?" * len(phases))
        params.extend(phases)
    sql += " ORDER BY COALESCE(as_of,'') DESC, id DESC LIMIT 1"
    return conn.execute(sql, params).fetchone()


def _latest_decision(conn, key, version, column):
    """Latest non-null `column` from strategy_decisions for a strategy."""
    row = conn.execute(
        f"SELECT {column} AS v FROM strategy_decisions WHERE strategy_key=? AND version=?"
        f" AND {column} IS NOT NULL ORDER BY COALESCE(at,'') DESC, id DESC LIMIT 1",
        (key, version)).fetchone()
    return row["v"] if row else None


def _current_states(conn):
    """Current lifecycle state per (strategy_key, version): to_state of the largest id."""
    out = {}
    for row in conn.execute("SELECT strategy_key, version, to_state FROM league_state "
                            "ORDER BY id ASC"):
        out[(row["strategy_key"], row["version"])] = row["to_state"]
    return out


def _latest_standings(conn):
    """league_standings rows at the latest as_of."""
    row = conn.execute("SELECT MAX(as_of) AS a FROM league_standings").fetchone()
    if not row or row["a"] is None:
        return []
    return conn.execute("SELECT * FROM league_standings WHERE as_of=? ORDER BY strategy_key, version",
                        (row["a"],)).fetchall()


def _latest_fund_accounting(conn):
    """Latest fund_accounting row per (fund_kind, fund_id) by computed_at."""
    if not _table_exists(conn, "fund_accounting"):
        return []
    rows = conn.execute("SELECT * FROM fund_accounting ORDER BY computed_at ASC, as_of ASC").fetchall()
    latest = {}
    for row in rows:
        latest[(row["fund_kind"], row["fund_id"])] = row
    return list(latest.values())


def _capital_by_strategy(conn):
    """Capital attributed to a strategy key, from fund_accounting labels/ids when present."""
    out = {}
    for row in _latest_fund_accounting(conn):
        cap = _num(row["capital_usd"])
        if cap is None:
            continue
        for candidate in (row["fund_id"], row["label"]):
            if candidate:
                out.setdefault(str(candidate), cap)
    return out


def _confidence(tier):
    t = (tier or "").upper()
    if t == "ESTABLISHED":
        return "established"
    if t == "ELIGIBLE":
        return "eligible"
    return "insufficient"


def scoreboard(conn):
    """One row per strategy with a forward record, plus every VALIDATED/PROMISING strategy."""
    states = _current_states(conn)
    standings = _latest_standings(conn)
    capitals = _capital_by_strategy(conn)

    rows = {}
    for st in standings:
        key, version = st["strategy_key"], st["version"]
        rows[(key, version)] = {"strategy": key, "version": version, "league": _unquote(st["league"]),
                                "evidence": "forward", "tier": st["tier"],
                                "gross_usd": _num(st["gross_usd"]), "costs_usd": _num(st["costs_usd"]),
                                "net_usd": _num(st["net_usd"]), "paper_days": st["sessions"],
                                "max_drawdown_pct": _num(st["max_drawdown_pct"]),
                                "trades": st["closed_trades"]}

    for (key, version), state in states.items():
        if state in ("VALIDATED", "PROMISING") and (key, version) not in rows:
            rows[(key, version)] = {"strategy": key, "version": version, "league": None,
                                    "evidence": "backtest", "tier": None}

    out = []
    for (key, version), base in rows.items():
        meta = conn.execute("SELECT * FROM strategy_meta WHERE strategy_key=? AND version=?",
                            (key, version)).fetchone()
        if base.get("evidence") == "forward":
            metrics = _latest_metrics(conn, key, version, FORWARD_PHASES)
        else:
            metrics = (_latest_metrics(conn, key, version, ("validation",))
                       or _latest_metrics(conn, key, version))
        capital = capitals.get(str(key))
        net = base.get("net_usd")
        if net is None and metrics is not None:
            net = _num(metrics["net_usd"])
        return_pct = None
        if net is not None and capital:
            return_pct = net / capital * 100.0
        if return_pct is None and metrics is not None:
            return_pct = _num(metrics["return_pct"])
        out.append({
            "strategy": key,
            "version": version,
            "league": base.get("league") or _unquote(meta["league"]) if meta else base.get("league"),
            "status": states.get((key, version), DASH),
            "classification": _latest_decision(conn, key, version, "classification") or DASH,
            "gross_usd": base.get("gross_usd") if base.get("gross_usd") is not None
                        else (_num(metrics["gross_usd"]) if metrics else None),
            "costs_usd": base.get("costs_usd") if base.get("costs_usd") is not None
                         else (_num(metrics["costs_usd"]) if metrics else None),
            "net_usd": net,
            "return_pct": return_pct,
            "max_drawdown_pct": base.get("max_drawdown_pct") if base.get("max_drawdown_pct") is not None
                                else (_num(metrics["max_drawdown_pct"]) if metrics else None),
            "sharpe": _num(metrics["sharpe"]) if metrics else None,
            "sortino": _num(metrics["sortino"]) if metrics else None,
            "win_rate": _num(metrics["win_rate"]) if metrics else None,
            "profit_factor": _num(metrics["profit_factor"]) if metrics else None,
            "trades": base.get("trades") if base.get("trades") is not None
                      else (metrics["trades"] if metrics else None),
            "turnover": _num(metrics["turnover"]) if metrics else None,
            "paper_days": base.get("paper_days"),
            "benchmark": _num(metrics["excess_vs_null_usd"]) if metrics else None,
            "benchmark_label": "informational",
            "correlation": _num(metrics["correlation"]) if metrics else None,
            "data_quality": (metrics["data_quality_status"] if metrics and metrics["data_quality_status"]
                             else DASH),
            # A forward record is traded point-in-time, so it carries no survivorship bias.
            "survivorship": ("forward" if base.get("evidence") == "forward"
                             else metrics["survivorship_status"] if metrics and metrics["survivorship_status"]
                             else "UNKNOWN"),
            "confidence": _confidence(base.get("tier")),
            "evidence": base.get("evidence", "backtest"),
            "tier": base.get("tier") or DASH,
        })

    out.sort(key=lambda r: (0 if r["evidence"] == "forward" else 1,
                            -(r["net_usd"] if r["net_usd"] is not None else float("-inf"))))
    return out


def _window_start(days):
    """ISO timestamp `days` before now; the report window is [start, now]."""
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def _count(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    return row[0] if row and row[0] is not None else 0


def daily_report(conn, days=1):
    """Sectioned daily report over the trailing `days` window."""
    start = _window_start(days)
    states = _current_states(conn)

    # Every new strategy (or version) enters the lifecycle log at DISCOVERED.
    new_strategies = _count(conn, "SELECT COUNT(*) FROM league_state WHERE to_state='DISCOVERED' "
                                  "AND at >= ?", (start,)) if _table_exists(conn, "league_state") else 0
    recycled = set()
    if _table_exists(conn, "strategy_meta"):
        for row in conn.execute("SELECT strategy_key, version FROM strategy_meta WHERE source='recycle'"):
            recycled.add((row["strategy_key"], row["version"]))
    new_variants = 0
    for table in ("strategy_decisions", "strategy_metrics"):
        if not _table_exists(conn, table):
            continue
        for row in conn.execute(f"SELECT DISTINCT strategy_key, version FROM {table}"):
            if (row["strategy_key"], row["version"]) in recycled:
                new_variants += 1
    new_sources = _count(conn, "SELECT COUNT(*) FROM research_queue WHERE created_at >= ? "
                               "AND source IN ('library','human')", (start,)) if _table_exists(conn, "research_queue") else 0

    completed = _count(conn, "SELECT COUNT(DISTINCT strategy_key) FROM strategy_metrics "
                             "WHERE phase='backtest' AND COALESCE(as_of, recorded_at) >= ?",
                       (start,)) if _table_exists(conn, "strategy_metrics") else 0
    promising = [k for k, s in states.items() if s in ("PROMISING", "VALIDATED")]
    failed = []
    if _table_exists(conn, "failure_log"):
        for row in conn.execute("SELECT strategy_key, version, stage, reason FROM failure_log "
                                "WHERE at >= ? ORDER BY at DESC", (start,)):
            failed.append({"strategy": row["strategy_key"], "version": row["version"],
                           "stage": row["stage"], "reason": row["reason"]})

    new_enrolments = []
    if _table_exists(conn, "league_state"):
        new_enrolments = [(r["strategy_key"], r["version"]) for r in conn.execute(
            "SELECT DISTINCT strategy_key, version FROM league_state WHERE to_state='PAPER' AND at >= ?",
            (start,))]
    leagues = {}
    for st in _latest_standings(conn):
        name = _unquote(st["league"]) or DASH
        entry = leagues.setdefault(name, {"count": 0, "best_net": None, "worst_net": None})
        entry["count"] += 1
        net = _num(st["net_usd"])
        if net is not None:
            entry["best_net"] = net if entry["best_net"] is None else max(entry["best_net"], net)
            entry["worst_net"] = net if entry["worst_net"] is None else min(entry["worst_net"], net)
    promotions = [k for k, s in states.items() if s in ("QUALIFIED", "LIVE_CANDIDATE")]
    demotions = [k for k, s in states.items() if s == "DEMOTED"]

    candidates = [k for k, s in states.items() if s in ("LIVE_CANDIDATE", "LIVE")]
    live = {"candidates": candidates}
    if not _table_exists(conn, "slots"):
        live["note"] = "slot engine not yet built"

    totals = {}
    recon_counts = {}
    for row in _latest_fund_accounting(conn):
        for kind in (row["fund_kind"], "ALL"):
            entry = totals.setdefault(kind, {"gross": 0.0, "costs": 0.0, "net": 0.0})
            entry["gross"] += _num(row["gross_usd"]) or 0.0
            entry["costs"] += _num(row["costs_usd"]) or 0.0
            entry["net"] += _num(row["net_usd"]) or 0.0
        status = row["recon_status"] or "UNKNOWN"
        recon_counts[status] = recon_counts.get(status, 0) + 1

    if _table_exists(conn, "dataset_comparisons"):
        row = conn.execute("SELECT COUNT(*) AS n, MAX(at) AS last FROM dataset_comparisons").fetchone()
        finsaber = {"summary": f"{row['n']} comparison(s), latest {row['last'] or DASH}"} if row["n"] else \
                   {"summary": "FINSABER comparison: not run yet"}
    else:
        finsaber = {"summary": "FINSABER comparison: not run yet"}
    data_problems = _count(conn, "SELECT COUNT(*) FROM strategy_decisions WHERE decision='DATA_PROBLEM' "
                                 "AND at >= ?", (start,)) if _table_exists(conn, "strategy_decisions") else 0

    explored = set()
    if _table_exists(conn, "strategy_decisions"):
        for row in conn.execute("SELECT DISTINCT strategy_key, version FROM strategy_decisions "
                                "WHERE to_state IN (%s)" % ",".join("?" * len(BACKTESTED_OR_LATER)),
                                BACKTESTED_OR_LATER):
            meta = conn.execute("SELECT family FROM strategy_meta WHERE strategy_key=? AND version=?",
                                (row["strategy_key"], row["version"])).fetchone()
            if meta and meta["family"]:
                explored.add(_unquote(meta["family"]))
    all_families = set()
    if _table_exists(conn, "strategy_meta"):
        for row in conn.execute("SELECT DISTINCT family FROM strategy_meta WHERE family IS NOT NULL"):
            all_families.add(_unquote(row["family"]))
    queue_by_source, queue_by_status = {}, {}
    if _table_exists(conn, "research_queue"):
        for row in conn.execute("SELECT source, COUNT(*) AS n FROM research_queue GROUP BY source"):
            queue_by_source[row["source"] or DASH] = row["n"]
        for row in conn.execute("SELECT status, COUNT(*) AS n FROM research_queue GROUP BY status"):
            queue_by_status[row["status"] or DASH] = row["n"]
    diversity = 0
    if _table_exists(conn, "strategy_decisions"):
        fams = set()
        for row in conn.execute("SELECT DISTINCT strategy_key, version FROM strategy_decisions "
                                "WHERE at >= ? AND to_state IN (%s)"
                                % ",".join("?" * len(BACKTESTED_OR_LATER)),
                                [start] + list(BACKTESTED_OR_LATER)):
            meta = conn.execute("SELECT family FROM strategy_meta WHERE strategy_key=? AND version=?",
                                (row["strategy_key"], row["version"])).fetchone()
            if meta and meta["family"]:
                fams.add(_unquote(meta["family"]))
        diversity = len(fams)

    return {
        "discovery": {"new_strategies": new_strategies, "new_variants": new_variants,
                      "new_research_sources": new_sources},
        "backtesting": {"completed": completed, "promising": promising, "failed": failed},
        "paper": {"new_enrolments": new_enrolments, "leagues": leagues,
                  "promotions": promotions, "demotions": demotions},
        "live": live,
        "accounting": {"totals": totals, "recon_status": recon_counts},
        "data": {"finsaber": finsaber, "data_problem_decisions": data_problems},
        "research": {"families_explored": sorted(explored),
                     "families_never_tested": sorted(all_families - explored),
                     "queue_by_source": queue_by_source, "queue_by_status": queue_by_status,
                     "diversity": diversity},
    }


def _money(value):
    """Signed money with two decimals, or an em dash when the figure is missing."""
    if value is None:
        return DASH
    return f"{value:+,.2f}"


def _pct(value):
    """Percentage to two decimals, or an em dash when the figure is missing."""
    return DASH if value is None else f"{value:.2f}"


def _cell(value, width):
    text = DASH if value is None else str(value)
    return text[:width].ljust(width)


def render(scoreboard_rows, report):
    """Plain-text report for a terminal and for Telegram."""
    lines = ["STRATEGY FACTORY REPORT", "=" * 24, ""]
    lines.append("SCOREBOARD (GROSS / COSTS / NET; tier shown, never rank by raw return alone)")
    header = (f"{'strategy':<28} {'league':<10} {'status':<14} {'tier':<20} "
              f"{'gross':>12} {'costs':>10} {'net':>12} {'trades':>7} {'days':>6} "
              f"{'maxDD%':>8} {'survivorship':<12}")
    lines.append(header)
    lines.append("-" * len(header))
    if not scoreboard_rows:
        lines.append("none")
    for row in scoreboard_rows:
        lines.append(
            f"{_cell(row['strategy'], 28)} {_cell(row['league'], 10)} {_cell(row['status'], 14)} "
            f"{_cell(row['tier'], 20)} {_money(row['gross_usd']):>12} {_money(row['costs_usd']):>10} "
            f"{_money(row['net_usd']):>12} {_cell(row['trades'], 7)} {_cell(row['paper_days'], 6)} "
            f"{_pct(row['max_drawdown_pct']):>8} {_cell(row['survivorship'], 12)}")
    lines.append("")

    disc = report["discovery"]
    lines.append("DISCOVERY")
    lines.append(f"  new strategies: {disc['new_strategies']}  new variants: {disc['new_variants']}  "
                 f"new research sources: {disc['new_research_sources']}")
    bt = report["backtesting"]
    lines.append("BACKTESTING")
    lines.append(f"  completed: {bt['completed']}  promising: {len(bt['promising'])}  failed: {len(bt['failed'])}")
    for item in bt["failed"]:
        lines.append(f"    {item['strategy']} v{item['version']}: {item['stage']} — {item['reason']}")
    paper = report["paper"]
    lines.append("PAPER")
    lines.append(f"  new enrolments: {len(paper['new_enrolments'])}  promotions: {len(paper['promotions'])}  "
                 f"demotions: {len(paper['demotions'])}")
    if not paper["leagues"]:
        lines.append("  leagues: none")
    for name, entry in sorted(paper["leagues"].items()):
        lines.append(f"    {name}: count {entry['count']}  best {_money(entry['best_net'])}  "
                     f"worst {_money(entry['worst_net'])}")
    live = report["live"]
    lines.append("LIVE")
    lines.append(f"  candidates: {len(live['candidates'])}")
    if live.get("note"):
        lines.append(f"  note: {live['note']}")
    acc = report["accounting"]
    lines.append("ACCOUNTING (GROSS / COSTS / NET)")
    if not acc["totals"]:
        lines.append("  none")
    for kind, entry in sorted(acc["totals"].items()):
        lines.append(f"  {kind}: gross {_money(entry['gross'])}  costs {_money(entry['costs'])}  "
                     f"net {_money(entry['net'])}")
    lines.append(f"  recon: {acc['recon_status'] or 'none'}")
    data = report["data"]
    lines.append("DATA")
    lines.append(f"  {data['finsaber']['summary']}")
    lines.append(f"  data_problem decisions: {data['data_problem_decisions']}")
    res = report["research"]
    lines.append("RESEARCH")
    lines.append(f"  families explored: {len(res['families_explored'])}  "
                 f"never tested: {len(res['families_never_tested'])}  diversity: {res['diversity']}")
    lines.append(f"  queue by source: {res['queue_by_source'] or 'none'}")
    lines.append(f"  queue by status: {res['queue_by_status'] or 'none'}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Daily Strategy Factory report.")
    parser.add_argument("--days", type=int, default=1)
    parser.add_argument("--out", default="data/factory_report.txt")
    parser.add_argument("--json", default="data/factory_report.json")
    parser.add_argument("--db", default=None)
    args = parser.parse_args(argv)

    path = args.db
    if path is None:
        import universe
        path = universe.load_config()["database"]["market_data_path"]

    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = scoreboard(conn)
        report = daily_report(conn, days=args.days)
    finally:
        conn.close()

    text = render(rows, report)
    import os
    for target in (args.out, args.json):
        directory = os.path.dirname(target)
        if directory:
            os.makedirs(directory, exist_ok=True)
    with open(args.out, "w") as f:
        f.write(text + "\n")
    with open(args.json, "w") as f:
        json.dump({"scoreboard": rows, "report": report}, f, indent=2, default=str)
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
