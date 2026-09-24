FILE: factory_report.py
```python
"""
Daily Strategy Factory report (Phase 13 §36) and the global strategy scoreboard
(§17).

Read-only over the existing tables. Nothing here writes, and nothing here
computes a new performance figure — every number is lifted from a table that
some other stage already populated. That is deliberate: a report that derives
its own returns is a second, silently-diverging implementation of the
accounting, and this project's history is measurement bugs that ran fine.

Two conventions worth stating because they are easy to get wrong:

- Money is always shown GROSS / COSTS / NET side by side (Addendum B §B5). A
  net figure alone hides whether an edge survived costs, which is the only
  question that matters here.
- A missing figure prints as an em dash and the row stays. Dropping rows with
  absent data would make the report look cleaner and be wrong.
"""
import runtime  # noqa: F401  — must precede numpy/pandas; they read thread
                #   limits once at import time.
import argparse
import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

import yaml

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("factory_report")

DASH = "\u2014"

# States that mean "this strategy has a forward record worth showing even if it
# never reached the league standings".
FORWARD_STATES = {"VALIDATED", "PROMISING"}

# States that count as having been backtested at least once, for the research
# section's "families explored".
BACKTESTED_STATES = {
    "BACKTESTED", "VALIDATED", "PROMISING", "PAPER", "QUALIFIED",
    "LIVE_CANDIDATE", "LIVE", "DEMOTED", "REJECTED",
}


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------
# connection helpers
# --------------------------------------------------------------------------

def connect_readonly(path: str) -> sqlite3.Connection:
    """
    Open the database read-only.

    mode=ro is not decoration: it makes an accidental write raise instead of
    succeeding, which is the only thing standing between a reporting bug and a
    corrupted research database.
    """
    uri = f"file:{path}?mode=ro"
    conn = sqlite3.connect(uri, uri=True)
    conn.row_factory = sqlite3.Row
    return conn


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    if not _table_exists(conn, table):
        return set()
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})")}


def _rows(conn: sqlite3.Connection, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
    """Run a query, returning [] if the table it needs does not exist."""
    try:
        return conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError as e:
        log.debug(f"query skipped ({e}): {sql}")
        return []


def _one(conn: sqlite3.Connection, sql: str, params: tuple = ()):
    rows = _rows(conn, sql, params)
    return rows[0] if rows else None


def _unquote(value):
    """
    Text columns in this schema sometimes hold JSON-encoded strings, so `family`
    may arrive as `value_quality` or as `"value_quality"`. Strip the surrounding
    quotes when present; leave anything else alone.
    """
    if value is None:
        return None
    if isinstance(value, str):
        s = value.strip()
        if len(s) >= 2 and s[0] == '"' and s[-1] == '"':
            try:
                return json.loads(s)
            except (ValueError, TypeError):
                return s.strip('"')
        return s
    return value


def _num(value):
    """Coerce to float, or None. Empty strings and junk become None, not 0.0 —
    a missing figure and a zero figure are different facts."""
    if value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value)
    try:
        return float(str(value).strip())
    except (ValueError, TypeError):
        return None


def _money(value) -> str:
    n = _num(value)
    if n is None:
        return DASH
    return f"{n:+,.2f}"


def _pct(value) -> str:
    n = _num(value)
    if n is None:
        return DASH
    return f"{n:+.2f}"


def _int(value) -> str:
    n = _num(value)
    if n is None:
        return DASH
    return f"{int(n)}"


def _window_start(days: int) -> str:
    """
    ISO timestamp for the start of the reporting window.

    The window is measured in calendar days back from now, in UTC, because every
    `at` in this schema is written as an ISO timestamp and string comparison is
    how they are filtered. Using local time here would silently shift the window
    by the box's offset.
    """
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


# --------------------------------------------------------------------------
# scoreboard (§17)
# --------------------------------------------------------------------------

def _latest_standings(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    if not _table_exists(conn, "league_standings"):
        return []
    latest = _one(conn, "SELECT MAX(as_of) AS a FROM league_standings")
    if not latest or latest["a"] is None:
        return []
    return _rows(conn, "SELECT * FROM league_standings WHERE as_of=?", (latest["a"],))


def _current_states(conn: sqlite3.Connection) -> dict[tuple, str]:
    """
    Current state of each (strategy_key, version): the to_state of the row with
    the largest id. Ordering by `at` would be wrong — two transitions can share
    a timestamp, and id is the only total order the table guarantees.
    """
    if not _table_exists(conn, "league_state"):
        return {}
    rows = _rows(conn, """
        SELECT strategy_key, version, to_state
        FROM league_state ls
        WHERE ls.id = (
            SELECT MAX(id) FROM league_state x
            WHERE x.strategy_key = ls.strategy_key AND x.version = ls.version
        )
    """)
    return {(r["strategy_key"], r["version"]): r["to_state"] for r in rows}


def _latest_decision(conn: sqlite3.Connection, key: str, version: int) -> sqlite3.Row | None:
    return _one(conn, """
        SELECT * FROM strategy_decisions
        WHERE strategy_key=? AND version=?
        ORDER BY at DESC, id DESC LIMIT 1
    """, (key, version))


def _latest_metrics(conn: sqlite3.Connection, key: str, version: int,
                    phases: tuple[str, ...] | None = None) -> sqlite3.Row | None:
    """
    Most recent metrics row for a strategy.

    `as_of` is the observation date and is the right sort key; `recorded_at` is
    when the row was written and can be later than the data it describes.
    """
    if phases:
        placeholders = ",".join("?" for _ in phases)
        return _one(conn, f"""
            SELECT * FROM strategy_metrics
            WHERE strategy_key=? AND version=? AND phase IN ({placeholders})
            ORDER BY as_of DESC, id DESC LIMIT 1
        """, (key, version, *phases))
    return _one(conn, """
        SELECT * FROM strategy_metrics
        WHERE strategy_key=? AND version=?
        ORDER BY as_of DESC, id DESC LIMIT 1
    """, (key, version))


def _latest_fund_capital(conn: sqlite3.Connection, key: str, version: int) -> float | None:
    """
    Capital for a strategy's fund, used to turn a net dollar figure into a
    percentage. fund_id is matched on the strategy key; if no fund exists the
    caller falls back to the metrics row's own return_pct.
    """
    if not _table_exists(conn, "fund_accounting"):
        return None
    row = _one(conn, """
        SELECT capital_usd FROM fund_accounting
        WHERE fund_id=?
        ORDER BY computed_at DESC LIMIT 1
    """, (key,))
    if row is None:
        return None
    return _num(row["capital_usd"])


def _confidence(tier: str | None) -> str:
    t = (tier or "").upper()
    if t == "ESTABLISHED":
        return "established"
    if t == "ELIGIBLE":
        return "eligible"
    return "insufficient"


def scoreboard(conn: sqlite3.Connection) -> list[dict]:
    """
    One row per strategy with a forward record, plus every strategy currently
    VALIDATED or PROMISING.

    Forward-record rows take their money from league_standings — that is the
    measured record. Backtest-only rows take theirs from the latest validation
    metrics and are labelled evidence "backtest", so a reader can never mistake
    a backtest for a forward result.
    """
    states = _current_states(conn)
    standings = _latest_standings(conn)

    meta: dict[tuple, sqlite3.Row] = {}
    if _table_exists(conn, "strategy_meta"):
        for r in _rows(conn, "SELECT * FROM strategy_meta"):
            meta[(r["strategy_key"], r["version"])] = r

    rows: list[dict] = []
    seen: set[tuple] = set()

    for st in standings:
        key, version = st["strategy_key"], st["version"]
        seen.add((key, version))
        m = meta.get((key, version))
        dec = _latest_decision(conn, key, version)
        met = _latest_metrics(conn, key, version)

        net = _num(st["net_usd"])
        capital = _latest_fund_capital(conn, key, version)
        if capital:
            return_pct = net / capital * 100.0 if net is not None else None
        else:
            return_pct = _num(met["return_pct"]) if met is not None else None

        rows.append({
            "strategy": key,
            "version": version,
            "league": _unquote(st["league"]) or (_unquote(m["league"]) if m is not None else None) or DASH,
            "status": states.get((key, version), DASH),
            "classification": _unquote(dec["classification"]) if dec is not None else DASH,
            "gross_usd": _num(st["gross_usd"]),
            "costs_usd": _num(st["costs_usd"]),
            "net_usd": net,
            "return_pct": return_pct,
            "max_drawdown_pct": _num(st["max_drawdown_pct"]),
            "sharpe": _num(met["sharpe"]) if met is not None else None,
            "sortino": _num(met["sortino"]) if met is not None else None,
            "win_rate": _num(met["win_rate"]) if met is not None else None,
            "profit_factor": _num(met["profit_factor"]) if met is not None else None,
            "trades": _num(st["closed_trades"]),
            "turnover": _num(met["turnover"]) if met is not None else None,
            "paper_days": _num(st["sessions"]),
            "benchmark": _num(met["excess_vs_null_usd"]) if met is not None else None,
            "benchmark_label": "informational",
            "correlation": _num(met["correlation"]) if met is not None else None,
            "data_quality": (met["data_quality_status"] if met is not None
                             and met["data_quality_status"] else DASH),
            "survivorship": (met["survivorship_status"] if met is not None
                             and met["survivorship_status"] else "UNKNOWN"),
            "tier": st["tier"] or DASH,
            "confidence": _confidence(st["tier"]),
            "evidence": "forward",
        })

    # Strategies with no forward record but a live state worth surfacing.
    for (key, version), state in states.items():
        if (key, version) in seen:
            continue
        if state not in FORWARD_STATES:
            continue
        m = meta.get((key, version))
        dec = _latest_decision(conn, key, version)
        met = _latest_metrics(conn, key, version, phases=("validation", "robustness", "backtest"))
        net = _num(met["net_usd"]) if met is not None else None
        capital = _latest_fund_capital(conn, key, version)
        if capital:
            return_pct = net / capital * 100.0 if net is not None else None
        else:
            return_pct = _num(met["return_pct"]) if met is not None else None

        rows.append({
            "strategy": key,
            "version": version,
            "league": _unquote(m["league"]) if m is not None else DASH,
            "status": state,
            "classification": _unquote(dec["classification"]) if dec is not None else DASH,
            "gross_usd": _num(met["gross_usd"]) if met is not None else None,
            "costs_usd": _num(met["costs_usd"]) if met is not None else None,
            "net_usd": net,
            "return_pct": return_pct,
            "max_drawdown_pct": _num(met["max_drawdown_pct"]) if met is not None else None,
            "sharpe": _num(met["sharpe"]) if met is not None else None,
            "sortino": _num(met["sortino"]) if met is not None else None,
            "win_rate": _num(met["win_rate"]) if met is not None else None,
            "profit_factor": _num(met["profit_factor"]) if met is not None else None,
            "trades": _num(met["trades"]) if met is not None else None,
            "turnover": _num(met["turnover"]) if met is not None else None,
            "paper_days": None,
            "benchmark": _num(met["excess_vs_null_usd"]) if met is not None else None,
            "benchmark_label": "informational",
            "correlation": _num(met["correlation"]) if met is not None else None,
            "data_quality": (met["data_quality_status"] if met is not None
                             and met["data_quality_status"] else DASH),
            "survivorship": (met["survivorship_status"] if met is not None
                             and met["survivorship_status"] else "UNKNOWN"),
            "tier": DASH,
            "confidence": "insufficient",
            "evidence": "backtest",
        })

    # Forward first, then net descending. Never by raw return: a strategy with a
    # large return on a tiny capital base outranks a real one otherwise, which is
    # exactly the artifact this project keeps finding.
    rows.sort(key=lambda r: (0 if r["evidence"] == "forward" else 1,
                             -(r["net_usd"] if r["net_usd"] is not None else float("-inf"))))
    return rows


# --------------------------------------------------------------------------
# daily report (§36)
# --------------------------------------------------------------------------

def _discovery(conn: sqlite3.Connection, since: str) -> dict:
    new_strategies = 0
    if _table_exists(conn, "strategy_meta"):
        row = _one(conn, "SELECT COUNT(*) AS n FROM strategy_meta WHERE created_at >= ?", (since,))
        new_strategies = row["n"] if row else 0

    # A "variant" is a strategy whose meta says it came from recycling. The
    # source column is the only place that provenance is recorded.
    new_variants = 0
    if _table_exists(conn, "strategy_meta"):
        row = _one(conn, """
            SELECT COUNT(DISTINCT strategy_key) AS n FROM strategy_meta
            WHERE source = 'recycle' AND created_at >= ?
        """, (since,))
        new_variants = row["n"] if row else 0

    new_sources = 0
    if _table_exists(conn, "research_queue"):
        row = _one(conn, """
            SELECT COUNT(*) AS n FROM research_queue
            WHERE created_at >= ? AND source IN ('library', 'human')
        """, (since,))
        new_sources = row["n"] if row else 0

    return {
        "new_strategies": new_strategies,
        "new_variants": new_variants,
        "new_research_sources": new_sources,
    }


def _backtesting(conn: sqlite3.Connection, since: str) -> dict:
    completed = 0
    if _table_exists(conn, "strategy_metrics"):
        row = _one(conn, """
            SELECT COUNT(DISTINCT strategy_key || ':' || version) AS n
            FROM strategy_metrics WHERE phase='backtest' AND as_of >= ?
        """, (since,))
        completed = row["n"] if row else 0

    promising = 0
    failed: list[dict] = []
    if _table_exists(conn, "league_state"):
        row = _one(conn, """
            SELECT COUNT(DISTINCT strategy_key || ':' || version) AS n
            FROM league_state WHERE to_state IN ('PROMISING','VALIDATED') AND at >= ?
        """, (since,))
        promising = row["n"] if row else 0

        rejected = _rows(conn, """
            SELECT strategy_key, version FROM league_state
            WHERE to_state='REJECTED' AND at >= ?
        """, (since,))
        for r in rejected:
            fl = _one(conn, """
                SELECT stage, reason FROM failure_log
                WHERE strategy_key=? AND version=?
                ORDER BY at DESC, id DESC LIMIT 1
            """, (r["strategy_key"], r["version"]))
            failed.append({
                "strategy": r["strategy_key"],
                "version": r["version"],
                "stage": fl["stage"] if fl is not None else DASH,
                "reason": fl["reason"] if fl is not None else DASH,
            })

    return {"completed": completed, "promising": promising, "failed": failed}


def _paper(conn: sqlite3.Connection, since: str) -> dict:
    new_enrolments = 0
    promotions = 0
    demotions = 0
    if _table_exists(conn, "league_state"):
        row = _one(conn, "SELECT COUNT(*) AS n FROM league_state WHERE to_state='PAPER' AND at >= ?", (since,))
        new_enrolments = row["n"] if row else 0
        row = _one(conn, """
            SELECT COUNT(*) AS n FROM league_state
            WHERE to_state IN ('QUALIFIED','LIVE_CANDIDATE') AND at >= ?
        """, (since,))
        promotions = row["n"] if row else 0
        row = _one(conn, "SELECT COUNT(*) AS n FROM league_state WHERE to_state='DEMOTED' AND at >= ?", (since,))
        demotions = row["n"] if row else 0

    leagues: list[dict] = []
    for st in _latest_standings(conn):
        pass
    if _table_exists(conn, "league_standings"):
        latest = _one(conn, "SELECT MAX(as_of) AS a FROM league_standings")
        if latest and latest["a"] is not None:
            for r in _rows(conn, """
                SELECT league, COUNT(*) AS n, MAX(net_usd) AS best, MIN(net_usd) AS worst
                FROM league_standings WHERE as_of=? GROUP BY league ORDER BY league
            """, (latest["a"],)):
                leagues.append({
                    "league": _unquote(r["league"]) or DASH,
                    "count": r["n"],
                    "best_net": _num(r["best"]),
                    "worst_net": _num(r["worst"]),
                })

    return {
        "new_enrolments": new_enrolments,
        "leagues": leagues,
        "promotions": promotions,
        "demotions": demotions,
    }


def _live(conn: sqlite3.Connection) -> dict:
    candidates = 0
    if _table_exists(conn, "league_state"):
        row = _one(conn, """
            SELECT COUNT(*) AS n FROM league_state ls
            WHERE ls.id = (
                SELECT MAX(id) FROM league_state x
                WHERE x.strategy_key = ls.strategy_key AND x.version = ls.version
            ) AND ls.to_state IN ('LIVE_CANDIDATE','LIVE')
        """)
        candidates = row["n"] if row else 0

    out = {"candidates": candidates}
    if not _table_exists(conn, "slots"):
        out["note"] = "slot engine not yet built"
    return out


def _accounting(conn: sqlite3.Connection) -> dict:
    """
    Latest accounting row per (fund_kind, fund_id), summed by kind and overall.

    Latest computed_at, not latest as_of: a restatement is a new row for the same
    as_of, and the restated figure is the one that is true.
    """
    totals: dict[str, dict] = {}
    recon_counts: dict[str, int] = {}

    if _table_exists(conn, "fund_accounting"):
        rows = _rows(conn, """
            SELECT fa.* FROM fund_accounting fa
            WHERE fa.computed_at = (
                SELECT MAX(computed_at) FROM fund_accounting x
                WHERE x.fund_kind = fa.fund_kind AND x.fund_id = fa.fund_id
            )
        """)
        for r in rows:
            kind = r["fund_kind"] or DASH
            bucket = totals.setdefault(kind, {"gross_usd": 0.0, "costs_usd": 0.0, "net_usd": 0.0, "funds": 0})
            bucket["gross_usd"] += _num(r["gross_usd"]) or 0.0
            bucket["costs_usd"] += _num(r["costs_usd"]) or 0.0
            bucket["net_usd"] += _num(r["net_usd"]) or 0.0
            bucket["funds"] += 1
            status = r["recon_status"] or "UNKNOWN"
            recon_counts[status] = recon_counts.get(status, 0) + 1

    overall = {"gross_usd": 0.0, "costs_usd": 0.0, "net_usd": 0.0, "funds": 0}
    for bucket in totals.values():
        for k in ("gross_usd", "costs_usd", "net_usd", "funds"):
            overall[k] += bucket[k]

    return {"by_kind": totals, "all": overall, "recon_status": recon_counts}


def _data(conn: sqlite3.Connection, since: str) -> dict:
    finsaber = "FINSABER comparison: not run yet"
    if _table_exists(conn, "dataset_comparisons"):
        row = _one(conn, "SELECT * FROM dataset_comparisons ORDER BY at DESC, id DESC LIMIT 1")
        if row is not None:
            finsaber = (f"FINSABER comparison: {row['primary_name']} vs "
                        f"{row['secondary_name']} ({row['start']} to {row['end']})")

    problems = 0
    if _table_exists(conn, "strategy_decisions"):
        row = _one(conn, """
            SELECT COUNT(*) AS n FROM strategy_decisions
            WHERE decision='data_problem' AND at >= ?
        """, (since,))
        problems = row["n"] if row else 0

    return {"finsaber": finsaber, "data_problem": problems}


def _research(conn: sqlite3.Connection, since: str) -> dict:
    explored: set[str] = set()
    if _table_exists(conn, "strategy_decisions"):
        placeholders = ",".join("?" for _ in BACKTESTED_STATES)
        for r in _rows(conn, f"""
            SELECT DISTINCT family FROM strategy_decisions
            WHERE to_state IN ({placeholders}) AND family IS NOT NULL
        """, tuple(BACKTESTED_STATES)):
            fam = _unquote(r["family"])
            if fam:
                explored.add(fam)

    known: set[str] = set()
    if _table_exists(conn, "strategy_meta"):
        for r in _rows(conn, "SELECT DISTINCT family FROM strategy_meta WHERE family IS NOT NULL"):
            fam = _unquote(r["family"])
            if fam:
                known.add(fam)
    if _table_exists(conn, "research_queue"):
        for r in _rows(conn, "SELECT DISTINCT family FROM research_queue WHERE family IS NOT NULL"):
            fam = _unquote(r["family"])
            if fam:
                known.add(fam)

    never_tested = sorted(known - explored)

    by_source: dict[str, int] = {}
    by_status: dict[str, int] = {}
    if _table_exists(conn, "research_queue"):
        for r in _rows(conn, "SELECT source, COUNT(*) AS n FROM research_queue GROUP BY source"):
            by_source[r["source"] or DASH] = r["n"]
        for r in _rows(conn, "SELECT status, COUNT(*) AS n FROM research_queue GROUP BY status"):
            by_status[r["status"] or DASH] = r["n"]

    diversity = 0
    if _table_exists(conn, "strategy_decisions"):
        placeholders = ",".join("?" for _ in BACKTESTED_STATES)
        row = _one(conn, f"""
            SELECT COUNT(DISTINCT family) AS n FROM strategy_decisions
            WHERE to_state IN ({placeholders}) AND at >= ? AND family IS NOT NULL
        """, (*BACKTESTED_STATES, since))
        diversity = row["n"] if row else 0

    return {
        "families_explored": sorted(explored),
        "families_never_tested": never_tested,
        "queue_by_source": by_source,
        "queue_by_status": by_status,
        "diversity": diversity,
    }


def daily_report(conn: sqlite3.Connection, days: int = 1) -> dict:
    since = _window_start(days)
    return {
        "discovery": _discovery(conn, since),
        "backtesting": _backtesting(conn, since),
        "paper": _paper(conn, since),
        "live": _live(conn),
        "accounting": _accounting(conn),
        "data": _data(conn, since),
        "research": _research(conn, since),
    }


# --------------------------------------------------------------------------
# render
# --------------------------------------------------------------------------

def _clip(text, width: int) -> str:
    s = DASH if text is None else str(text)
    if len(s) > width:
        return s[: width - 1] + "\u2026"
    return s


def render(scoreboard_rows: list[dict], report: dict) -> str:
    """
    Plain text: fixed-width so it survives a terminal and a Telegram code block
    without reflowing.
    """
    lines: list[str] = []
    lines.append("STRATEGY FACTORY REPORT")
    lines.append("=" * 100)
    lines.append("")

    lines.append("SCOREBOARD")
    lines.append("-" * 100)
    header = (f"{'strategy':<28} {'league':<12} {'status':<16} {'tier':<20} "
              f"{'gross':>12} {'costs':>12} {'net':>12} {'trades':>7} {'days':>6} "
              f"{'maxDD%':>8} {'survivorship':<14}")
    lines.append(header)
    lines.append("-" * len(header))
    if not scoreboard_rows:
        lines.append("(none)")
    for r in scoreboard_rows:
        lines.append(
            f"{_clip(r['strategy'], 28):<28} "
            f"{_clip(r['league'], 12):<12} "
            f"{_clip(r['status'], 16):<16} "
            f"{_clip(r['tier'], 20):<20} "
            f"{_money(r['gross_usd']):>12} "
            f"{_money(r['costs_usd']):>12} "
            f"{_money(r['net_usd']):>12} "
            f"{_int(r['trades']):>7} "
            f"{_int(r['paper_days']):>6} "
            f"{_pct(r['max_drawdown_pct']):>8} "
            f"{_clip(r['survivorship'], 14):<14}"
        )
    lines.append("")
    lines.append("GROSS / COSTS / NET are shown side by side (Addendum B §B5).")
    lines.append("Benchmark figures are informational (§B20) and are not a gate.")
    lines.append("")

    def section(title: str):
        lines.append(title.upper())
        lines.append("-" * 100)

    d = report.get("discovery", {})
    section("discovery")
    lines.append(f"  new strategies:        {d.get('new_strategies', 0)}")
    lines.append(f"  new variants:          {d.get('new_variants', 0)}")
    lines.append(f"  new research sources:  {d.get('new_research_sources', 0)}")
    lines.append("")

    b = report.get("backtesting", {})
    section("backtesting")
    lines.append(f"  completed:  {b.get('completed', 0)}")
    lines.append(f"  promising:  {b.get('promising', 0)}")
    failed = b.get("failed", [])
    lines.append(f"  failed:     {len(failed)}")
    for f in failed:
        lines.append(f"    {f['strategy']} v{f['version']}: {f['stage']} {DASH} {f['reason']}")
    lines.append("")

    p = report.get("paper", {})
    section("paper")
    lines.append(f"  new enrolments: {p.get('new_enrolments', 0)}")
    lines.append(f"  promotions:     {p.get('promotions', 0)}")
    lines.append(f"  demotions:      {p.get('demotions', 0)}")
    leagues = p.get("leagues", [])
    if not leagues:
        lines.append("  leagues: none")
    for lg in leagues:
        lines.append(f"  league {lg['league']}: {lg['count']} strategies, "
                     f"best {_money(lg['best_net'])}, worst {_money(lg['worst_net'])}")
    lines.append("")

    lv = report.get("live", {})
    section("live")
    lines.append(f"  candidates: {lv.get('candidates', 0)}")
    if lv.get("note"):
        lines.append(f"  note: {lv['note']}")
    lines.append("")

    a = report.get("accounting", {})
    section("accounting")
    lines.append(f"  {'fund_kind':<16} {'funds':>6} {'gross':>14} {'costs':>14} {'net':>14}")
    for kind, bucket in sorted(a.get("by_kind", {}).items()):
        lines.append(f"  {_clip(kind, 16):<16} {bucket['funds']:>6} "
                     f"{_money(bucket['gross_usd']):>14} {_money(bucket['costs_usd']):>14} "
                     f"{_money(bucket['net_usd']):>14}")
    allb = a.get("all", {"funds": 0, "gross_usd": 0.0, "costs_usd": 0.0, "net_usd": 0.0})
    lines.append(f"  {'ALL':<16} {allb['funds']:>6} "
                 f"{_money(allb['gross_usd']):>14} {_money(allb['costs_usd']):>14} "
                 f"{_money(allb['net_usd']):>14}")
    recon = a.get("recon_status", {})
    if recon:
        lines.append("  reconciliation: " + ", ".join(f"{k} {v}" for k, v in sorted(recon.items())))
    else:
        lines.append("  reconciliation: none")
    lines.append("")

    dt = report.get("data", {})
    section("data")
    lines.append(f"  {dt.get('finsaber', DASH)}")
    lines.append(f"  data_problem decisions: {dt.get('data_problem', 0)}")
    lines.append("")

    rs = report.get("research", {})
    section("research")
    explored = rs.get("families_explored", [])
    never = rs.get("families_never_tested", [])
    lines.append(f"  families explored:     {len(explored)}"
                 + (f" ({', '.join(explored)})" if explored else ""))
    lines.append(f"  families never tested: {len(never)}"
                 + (f" ({', '.join(never)})" if never else ""))
    lines.append(f"  diversity (backtested in window): {rs.get('diversity', 0)}")
    by_source = rs.get("queue_by_source", {})
    by_status = rs.get("queue_by_status", {})
    lines.append("  queue by source: " + (", ".join(f"{k} {v}" for k, v in sorted(by_source.items())) or "none"))
    lines.append("  queue by status: " + (", ".join(f"{k} {v}" for k, v in sorted(by_status.items())) or "none"))
    lines.append("")

    return "\n".join(lines)


# --------------------------------------------------------------------------
# CLI
# --------------------------------------------------------------------------

def main() -> None:
    parser = argparse.ArgumentParser(description="Daily Strategy Factory report.")
    parser.add_argument("--days", type=int, default=1, help="reporting window in days")
    parser.add_argument("--out", default="data/factory_report.txt", help="text output path")
    parser.add_argument("--json", default="data/factory_report.json", help