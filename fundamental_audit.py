"""Audit point-in-time availability of fundamental facts.

A fundamental value is only usable on a decision date if the date the market
could first have known it (the filing date) is at or before that decision date.
The period end is when the quarter closed, not when it was public, so anything
keyed on `period` alone is look-ahead. This module measures how much of the
stored data carries a usable availability date and where the lag is impossible.
"""

import runtime  # noqa: F401  (must precede pandas/numpy: thread limits are read at import)

import argparse
import json
import os
import sqlite3
import sys
from datetime import date, datetime

import universe
import storage


# fundamentals.filed is documented as ISO but the SEC ingest has historically
# written YYYYMMDD; both forms appear in the table, so normalise before comparing.
def _normalise_date(value):
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if len(text) == 8 and text.isdigit():
        return "%s-%s-%s" % (text[0:4], text[4:6], text[6:8])
    return text[:10]


def _parse_date(value):
    text = _normalise_date(value)
    if text is None:
        return None
    try:
        return datetime.strptime(text, "%Y-%m-%d").date()
    except ValueError:
        return None


def _median(values):
    """Median of a list of ints, without pulling in numpy for one number."""
    if not values:
        return None
    ordered = sorted(values)
    n = len(ordered)
    mid = n // 2
    if n % 2 == 1:
        return float(ordered[mid])
    return (ordered[mid - 1] + ordered[mid]) / 2.0


def _scalar(conn, sql, params=()):
    row = conn.execute(sql, params).fetchone()
    if row is None:
        return None
    return row[0]


def audit_fundamentals(conn):
    total = _scalar(conn, "SELECT COUNT(*) FROM fundamentals") or 0
    with_filed = _scalar(
        conn,
        "SELECT COUNT(*) FROM fundamentals WHERE filed IS NOT NULL AND TRIM(filed) <> ''",
    ) or 0
    missing_filed = total - with_filed

    # Lag is computed in Python rather than SQL because `filed` may be either
    # YYYY-MM-DD or YYYYMMDD and SQLite's date functions silently return NULL
    # for the latter, which would hide exactly the rows we are auditing.
    lags = []
    negative = []
    unparseable = 0
    rows = conn.execute(
        "SELECT ticker, filed, period FROM fundamentals WHERE filed IS NOT NULL AND TRIM(filed) <> ''"
    )
    for ticker, filed, period in rows:
        filed_d = _parse_date(filed)
        period_d = _parse_date(period)
        if filed_d is None or period_d is None:
            unparseable += 1
            continue
        lag = (filed_d - period_d).days
        lags.append(lag)
        if lag < 0:
            negative.append({"ticker": ticker, "filed": _normalise_date(filed), "period": _normalise_date(period), "lag_days": lag})

    lag_stats = {
        "min": min(lags) if lags else None,
        "median": _median(lags),
        "max": max(lags) if lags else None,
        "n": len(lags),
        "unparseable_dates": unparseable,
    }

    per_year = []
    for year, n_rows, n_tickers in conn.execute(
        """
        SELECT SUBSTR(REPLACE(filed, '-', ''), 1, 4) AS y,
               COUNT(*),
               COUNT(DISTINCT ticker)
        FROM fundamentals
        WHERE filed IS NOT NULL AND TRIM(filed) <> ''
        GROUP BY y
        ORDER BY y
        """
    ):
        per_year.append({"year": year, "rows": n_rows, "tickers": n_tickers})

    return {
        "fundamentals_total": total,
        "fundamentals_with_filed": with_filed,
        "fundamentals_missing_filed": missing_filed,
        "lag_days": lag_stats,
        "negative_lag_count": len(negative),
        "negative_lag_examples": negative[:50],
        "per_year": per_year,
    }


def audit_daily_fundamentals(conn):
    total = _scalar(conn, "SELECT COUNT(*) FROM daily_fundamentals") or 0
    min_lag = _scalar(
        conn, "SELECT MIN(days_since_filing) FROM daily_fundamentals WHERE days_since_filing IS NOT NULL"
    )
    max_lag = _scalar(
        conn, "SELECT MAX(days_since_filing) FROM daily_fundamentals WHERE days_since_filing IS NOT NULL"
    )
    # NULL days_since_filing is as unusable as a negative one: the row cannot be
    # shown to have been public on its own date, so it is counted with the
    # look-ahead cases rather than treated as merely missing.
    bad = _scalar(
        conn,
        "SELECT COUNT(*) FROM daily_fundamentals WHERE days_since_filing IS NULL OR days_since_filing < 0",
    ) or 0
    negative_only = _scalar(
        conn, "SELECT COUNT(*) FROM daily_fundamentals WHERE days_since_filing < 0"
    ) or 0
    null_only = _scalar(
        conn, "SELECT COUNT(*) FROM daily_fundamentals WHERE days_since_filing IS NULL"
    ) or 0

    return {
        "daily_fundamentals_total": total,
        "daily_min_days_since_filing": min_lag,
        "daily_max_days_since_filing": max_lag,
        "daily_negative_or_null_lag": bad,
        "daily_negative_lag": negative_only,
        "daily_null_lag": null_only,
    }


def render_markdown(report):
    f = report["fundamentals"]
    d = report["daily_fundamentals"]
    lag = f["lag_days"]
    lines = []
    lines.append("# Fundamental availability audit")
    lines.append("")
    lines.append("Generated: %s" % report["generated_at"])
    lines.append("Database: `%s`" % report["database"])
    lines.append("")
    lines.append("## Verdict")
    lines.append("")
    if report["ok"]:
        lines.append("PASS — no impossible filing dates and no look-ahead rows found.")
    else:
        lines.append("**FAIL — correctness defects found.**")
        if f["negative_lag_count"]:
            lines.append("")
            lines.append("- %d fundamentals rows have a filing date *before* the period they report." % f["negative_lag_count"])
        if d["daily_negative_or_null_lag"]:
            lines.append("")
            lines.append("- %d daily_fundamentals rows have a negative or NULL `days_since_filing`." % d["daily_negative_or_null_lag"])
    lines.append("")
    lines.append("## fundamentals")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append("| total rows | %d |" % f["fundamentals_total"])
    lines.append("| with filed date | %d |" % f["fundamentals_with_filed"])
    lines.append("| missing filed date | %d |" % f["fundamentals_missing_filed"])
    lines.append("| negative lag rows | %d |" % f["negative_lag_count"])
    lines.append("")
    lines.append("Rows with a NULL `filed` cannot be used point-in-time at all and must be excluded from any value screen.")
    lines.append("")
    lines.append("### Filing lag (filed - period), days")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append("| min | %s |" % lag["min"])
    lines.append("| median | %s |" % lag["median"])
    lines.append("| max | %s |" % lag["max"])
    lines.append("| rows measured | %d |" % lag["n"])
    lines.append("| unparseable dates | %d |" % lag["unparseable_dates"])
    lines.append("")
    if f["negative_lag_examples"]:
        lines.append("### Negative lag examples")
        lines.append("")
        lines.append("| ticker | filed | period | lag_days |")
        lines.append("|---|---|---|---|")
        for row in f["negative_lag_examples"]:
            lines.append("| %s | %s | %s | %d |" % (row["ticker"], row["filed"], row["period"], row["lag_days"]))
        lines.append("")
    lines.append("### Coverage by filing year")
    lines.append("")
    lines.append("| year | rows | distinct tickers |")
    lines.append("|---|---|---|")
    for row in f["per_year"]:
        lines.append("| %s | %d | %d |" % (row["year"], row["rows"], row["tickers"]))
    lines.append("")
    lines.append("## daily_fundamentals")
    lines.append("")
    lines.append("| metric | value |")
    lines.append("|---|---|")
    lines.append("| total rows | %d |" % d["daily_fundamentals_total"])
    lines.append("| min days_since_filing | %s |" % d["daily_min_days_since_filing"])
    lines.append("| max days_since_filing | %s |" % d["daily_max_days_since_filing"])
    lines.append("| negative or NULL lag | %d |" % d["daily_negative_or_null_lag"])
    lines.append("| negative lag | %d |" % d["daily_negative_lag"])
    lines.append("| NULL lag | %d |" % d["daily_null_lag"])
    lines.append("")
    lines.append("Negative or NULL `days_since_filing` rows are look-ahead: the value cannot be shown to have been public on the row's own date.")
    lines.append("")
    return "\n".join(lines)


def build_report(conn, db_path):
    fundamentals = audit_fundamentals(conn)
    daily = audit_daily_fundamentals(conn)
    ok = fundamentals["negative_lag_count"] == 0 and daily["daily_negative_or_null_lag"] == 0
    return {
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "database": db_path,
        "ok": ok,
        "fundamentals": fundamentals,
        "daily_fundamentals": daily,
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit point-in-time availability of fundamental facts.")
    parser.add_argument("--out-dir", default="reports", help="directory for the JSON and Markdown reports")
    args = parser.parse_args(argv)

    config = universe.load_config()
    db_path = config["database"]["market_data_path"]

    os.makedirs(args.out_dir, exist_ok=True)

    conn = storage.connect(db_path)
    try:
        report = build_report(conn, db_path)
    finally:
        conn.close()

    json_path = os.path.join(args.out_dir, "fundamental_availability.json")
    md_path = os.path.join(args.out_dir, "fundamental_availability.md")

    with open(json_path, "w") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")

    with open(md_path, "w") as fh:
        fh.write(render_markdown(report))

    f = report["fundamentals"]
    d = report["daily_fundamentals"]
    print("fundamentals: %d rows, %d with filed, %d missing filed" % (
        f["fundamentals_total"], f["fundamentals_with_filed"], f["fundamentals_missing_filed"]))
    print("negative lag rows: %d" % f["negative_lag_count"])
    print("daily_fundamentals: %d rows, %d negative or NULL lag" % (
        d["daily_fundamentals_total"], d["daily_negative_or_null_lag"]))
    print("wrote %s and %s" % (json_path, md_path))

    # A negative lag is impossible data, not a statistic; failing the process is
    # the only way it gets noticed by whatever runs this in a pipeline.
    if not report["ok"]:
        print("FAIL: point-in-time defects found", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
