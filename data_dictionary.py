"""
Generates docs/DATA_DICTIONARY.md from the live SQLite schema.

Hand-written schema documentation goes stale the day a column is added, so this
reads `sqlite_master` and `PRAGMA table_info` and renders what is actually there.
Descriptions come from DESCRIPTIONS below; a table with no entry is rendered as
**undocumented** rather than omitted, so a new table shows up as a visible gap
instead of an invisible one.

The database is opened READ-ONLY. A documentation generator that can write to
the database it documents is one bug away from being a migration tool.
"""
import runtime  # noqa: F401  — must precede numpy/pandas. Both modules
                #   have a __main__ block, so they are entry points too.
import argparse
import sqlite3
from pathlib import Path

# One line per table. Tables absent from this dict are reported as undocumented
# on purpose — see the module docstring.
DESCRIPTIONS = {
    "prices": "daily OHLCV bars, PK (ticker, date), 1962 to present",
    "features": "the 20 technical indicators per (ticker, date)",
    "symbols": "every listing, tagged by security_type, with data_quality flags",
    "ingest_state": "per-ticker backfill progress; makes the load resumable",
    "risk_metrics": "monthly beta and idiosyncratic volatility",
    "sec_filings": "one row per SEC filing, with accepted time, prevrpt and first_tradeable",
    "sec_facts": "raw XBRL facts per filing",
    "fundamentals": "~40 derived value/quality metrics per filing",
    "daily_fundamentals": "fundamentals lagged to the first session they were public",
    "edgar_filers": "point-in-time registry of SEC annual filers, 1993-now",
    "edgar_events": "8-K item codes as events",
    "delistings": "delisted listings with exact dates (Alpha Vantage)",
    "historical_listings": "Internet Archive replays of the symbol directory",
    "archive_snapshots": "one row per Internet Archive capture",
    "strategies": "evolved genomes",
    "evaluations": "every scored evaluation; the trial counter is append-only",
    "promotions": "validation ladder decisions",
    "lab_runs": "search run metadata",
    "benchmarks": "the null surface cells",
    "oos_predictions": "walk-forward out-of-sample predictions",
    "paper_runs": "simulated funds; genome stored inline as JSON",
    "paper_equity": "daily equity marks of paper funds",
    "paper_trades": "closed paper trades",
    "pair_funds": "bull/bear ETF switching funds",
    "pair_fund_equity": "daily marks of pair funds",
    "picks": "daily book recommendations and actual fills",
    "experiment_registry": "pre-registered experiments, versioned, hash-checked",
    "value_fund": "the long-horizon Value Fund",
    "crypto_prices": "crypto OHLCV bars, PK (symbol, interval, open_time)",
    "crypto_fund": "the crypto paper fund",
    "allocations": "capital allocation runs (allocation.py), one row per scheme per run",
    "claude_fund": "the discretionary paper fund's positions, each with a written thesis",
    "claude_fund_meta": "the discretionary fund's capital and status",
    "compute_log": "per-stage runtime of daily.sh, tagged by compute-priority tier",
    "crypto_benchmarks": "per-symbol crypto null surface cells",
    "crypto_fund_equity": "daily marks of the crypto paper fund",
    "crypto_fund_open": "open grid positions of the crypto paper fund",
    "crypto_fund_trades": "closed crypto fund trades: gross, fees, net, null",
    "crypto_listings": "crypto pair listing status, recorded at load time",
    "degradation": "backtest-to-forward degradation per strategy, mean per-trade units",
    "edgar_companies": "SEC company registry rows behind edgar_filers",
    "experiment_trades": "trades behind rows in the experiments ledger",
    "experiments": "the experiment ledger: one row per test, ranked by money",
    "fills": "broker fills recorded by the execution engine",
    "freshness_log": "every freshness-gate verdict, with lag and missing references",
    "holdout_log": "sealed-holdout evaluations and refusals; one evaluation per strategy",
    "league_state": "append-only lifecycle transition log; state is derived, never stored",
    "league_strategies": "strategy identity and immutable versions (definition_hash)",
    "llm_calls": "ADO delegated model calls: tokens and estimated cost",
    "oos_folds": "walk-forward fold metadata behind oos_predictions",
    "orders": "orders built by the execution engine and their state-machine status",
    "paper_positions": "open positions of the paper funds",
    "promotion_decisions": "promotion-policy verdicts per strategy",
    "random_control": "persistent random-genome control distribution, fingerprinted",
    "risk_events": "risk-engine rejections and kill-switch events",
    "roster_changes": "live-roster plan and demotion history",
    "scoreboard_snapshots": "scoreboard output per run, with the formula that produced it",
    "signals": "content-addressed trade signals submitted to execution",
    "strategy_ancestry": "origin classification per strategy (seeded / independent)",
    "strategy_library": "research library: every strategy idea with provenance and evidence",
    "synthetic_companies": "generated delisting price paths for stress tests",
    "system_events": "system-level events (restarts, mode changes)",
    "trial_ledger": "append-only cumulative trial counter for multiple-testing correction",
    "value_fund_equity": "daily marks of the Value Fund",
    "value_fund_positions": "open Value Fund positions with thesis and entry score",
    "value_fund_trades": "closed Value Fund trades",
}


def describe(conn: sqlite3.Connection) -> list[dict]:
    """
    One dict per user table, alphabetically by name.

    `sqlite_%` tables are excluded: they are SQLite's own bookkeeping (the
    sequence table behind AUTOINCREMENT, the WAL index) and documenting them
    would imply they are part of the schema anyone should reason about.

    `without_rowid` is read from the CREATE statement rather than inferred. It
    cannot be recovered from `PRAGMA table_info`, and it is not cosmetic: a
    WITHOUT ROWID table has no hidden rowid, so any query relying on one fails
    outright.
    """
    rows = conn.execute(
        "SELECT name, sql FROM sqlite_master "
        "WHERE type = 'table' AND name NOT LIKE 'sqlite_%' "
        "ORDER BY name"
    ).fetchall()

    tables = []
    for name, sql in rows:
        cols = conn.execute(f'PRAGMA table_info("{name}")').fetchall()
        tables.append({
            "name": name,
            "description": DESCRIPTIONS.get(name),
            "columns": [
                {
                    "name": c[1],
                    "type": c[2] or "",
                    "notnull": bool(c[3]),
                    "pk": int(c[5]),
                }
                for c in cols
            ],
            # `sql` is NULL for some internal tables; treat that as not-WITHOUT-ROWID.
            "without_rowid": bool(sql) and "WITHOUT ROWID" in sql.upper(),
        })
    return tables


def _escape(text: str) -> str:
    """Pipe is the markdown cell separator, so it cannot appear raw in a cell."""
    return str(text).replace("|", "\\|")


def render(tables: list[dict], counts: dict | None = None) -> str:
    """
    Render the dictionary as markdown.

    `counts` is optional and keyed by table name. COUNT(*) on `prices` is a full
    scan of ~35M rows, so the caller opts in with --counts rather than paying for
    it on every regeneration. A table absent from `counts` reads "not counted",
    which is deliberately distinct from a count of zero.
    """
    lines = [
        "# Data Dictionary",
        "",
        "Generated from the live SQLite schema by `data_dictionary.py`. "
        "Do not edit by hand — regenerate with:",
        "",
        "```",
        "python data_dictionary.py --counts",
        "```",
        "",
        f"Tables: {len(tables)}",
        "",
        "## Summary",
        "",
        "| Table | Rows | Description |",
        "| --- | --- | --- |",
    ]

    for t in tables:
        if counts is None or t["name"] not in counts:
            n = "not counted"
        else:
            n = f"{counts[t['name']]:,}"
        desc = t["description"] or "**undocumented**"
        lines.append(f"| `{_escape(t['name'])}` | {n} | {_escape(desc)} |")

    for t in tables:
        desc = t["description"] or "**undocumented**"
        lines += ["", f"## `{t['name']}`", "", desc, ""]
        if t["without_rowid"]:
            lines += ["`WITHOUT ROWID`", ""]
        lines += [
            "| Column | Type | Not null | PK |",
            "| --- | --- | --- | --- |",
        ]
        for c in t["columns"]:
            lines.append(
                f"| `{_escape(c['name'])}` | {_escape(c['type'] or '—')} | "
                f"{'yes' if c['notnull'] else 'no'} | "
                f"{c['pk'] if c['pk'] else ''} |"
            )

    return "\n".join(lines) + "\n"


def row_counts(conn: sqlite3.Connection, tables: list[dict]) -> dict:
    """COUNT(*) per table. Slow on the large tables — only run when asked."""
    return {
        t["name"]: conn.execute(f'SELECT COUNT(*) FROM "{t["name"]}"').fetchone()[0]
        for t in tables
    }


def connect_readonly(db_path: str) -> sqlite3.Connection:
    """
    Open the database read-only via URI.

    `mode=ro` is enforced by SQLite itself, not by convention: a stray write
    raises rather than silently mutating the database this script exists to
    describe. `uri=True` is required for the query string to be parsed at all —
    without it the whole string is treated as a filename.
    """
    path = Path(db_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"No database at {path}")
    return sqlite3.connect(f"file:{path}?mode=ro", uri=True)


def main() -> None:
    from universe import load_config

    parser = argparse.ArgumentParser(description="Generate the data dictionary from the live schema.")
    parser.add_argument("--db", default=None, help="Path to the SQLite database.")
    parser.add_argument("--out", default="docs/DATA_DICTIONARY.md", help="Output markdown path.")
    parser.add_argument("--counts", action="store_true",
                        help="Include row counts (slow: full scan of every table).")
    args = parser.parse_args()

    db_path = args.db or load_config()["database"]["market_data_path"]
    conn = connect_readonly(db_path)
    try:
        tables = describe(conn)
        counts = row_counts(conn, tables) if args.counts else None
    finally:
        conn.close()

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render(tables, counts), encoding="utf-8")

    undocumented = [t["name"] for t in tables if not t["description"]]
    print(f"Wrote {out} — {len(tables)} tables, {len(undocumented)} undocumented")
    if undocumented:
        print("Undocumented: " + ", ".join(undocumented))


if __name__ == "__main__":
    main()
