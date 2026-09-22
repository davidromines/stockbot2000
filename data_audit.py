"""Report how complete the research universe actually is.

Every backtest figure inherits the gap left by missing delisted companies, so
this module measures that gap rather than estimating it. Read-only: it never
writes to a table and never downloads anything.
"""

import runtime  # noqa: F401  -- must precede pandas/numpy; they latch thread limits at import

import argparse
import json
import logging
import os
import sys

import universe
from storage import connect

log = logging.getLogger("data_audit")

# The prices table holds ~35M rows. Every count below is an aggregate computed
# in SQLite; loading frames into pandas would materialise the whole table and
# is not viable here.
#
# Column names are taken from the schema, not inferred: prices and symbols are
# both keyed by `ticker`, and delistings is keyed by `symbol`. Getting this
# wrong does not raise -- SQLite happily returns 0 for a join on a column that
# does not exist in one of the tables -- so the names are copied verbatim.
_COUNT_SECURITIES = "SELECT COUNT(*) FROM symbols"

_COUNT_BY_TYPE = """
SELECT COALESCE(security_type, 'UNKNOWN') AS security_type, COUNT(*) AS n
FROM symbols
GROUP BY COALESCE(security_type, 'UNKNOWN')
ORDER BY n DESC, security_type ASC
"""

# A security "has prices" if at least one row exists. EXISTS short-circuits on
# the first matching row, which is far cheaper than COUNT(DISTINCT ticker) over
# 35M rows.
_COUNT_WITH_PRICES = """
SELECT COUNT(*) FROM symbols s
WHERE EXISTS (SELECT 1 FROM prices p WHERE p.ticker = s.ticker)
"""

_COUNT_WITHOUT_PRICES = """
SELECT COUNT(*) FROM symbols s
WHERE NOT EXISTS (SELECT 1 FROM prices p WHERE p.ticker = s.ticker)
"""

_COUNT_DELISTED = "SELECT COUNT(*) FROM delistings"

# delistings is keyed by `symbol` (see schema), while prices is keyed by
# `ticker`. The join is therefore d.symbol = p.ticker, not symbol = symbol.
_COUNT_DELISTED_WITH_PRICES = """
SELECT COUNT(*) FROM delistings d
WHERE EXISTS (SELECT 1 FROM prices p WHERE p.ticker = d.symbol)
"""

_COUNT_DELISTED_WITHOUT_PRICES = """
SELECT COUNT(*) FROM delistings d
WHERE NOT EXISTS (SELECT 1 FROM prices p WHERE p.ticker = d.symbol)
"""

_COUNT_FIRST_SEEN = "SELECT COUNT(*) FROM symbols WHERE first_seen IS NOT NULL"

_COUNT_FUNDAMENTAL_TICKERS = """
SELECT COUNT(DISTINCT ticker) FROM daily_fundamentals
"""

# Cheap sanity check on the table we are actually pointed at. If this is small
# or zero, the audit is reading the wrong database and every figure below is
# meaningless -- better to see that in the log than in the report.
_COUNT_PRICE_ROWS = "SELECT COUNT(*) FROM prices"


def _scalar(conn, sql, default=0):
    """Run a single-value aggregate, returning `default` if the table is absent.

    A missing table means the audit cannot answer the question, not that the
    answer is zero. We surface that as a logged warning and a zero count so the
    report still parses; the warning is the signal that the number is unknown.
    """
    try:
        row = conn.execute(sql).fetchone()
    except Exception as exc:  # sqlite3.OperationalError and friends
        log.warning("query failed, reporting 0: %s (%s)", sql.strip().split("\n")[0], exc)
        return default
    if row is None or row[0] is None:
        return default
    return int(row[0])


def _by_security_type(conn):
    try:
        rows = conn.execute(_COUNT_BY_TYPE).fetchall()
    except Exception as exc:
        log.warning("security_type breakdown unavailable: %s", exc)
        return {}
    return {str(r[0]): int(r[1]) for r in rows}


def collect(conn):
    """Gather every completeness figure into a plain dict."""
    total = _scalar(conn, _COUNT_SECURITIES)
    with_prices = _scalar(conn, _COUNT_WITH_PRICES)
    without_prices = _scalar(conn, _COUNT_WITHOUT_PRICES)

    # The two counts are computed by independent queries. If they disagree with
    # the total, one of the queries is wrong and every downstream figure is
    # suspect -- say so loudly rather than emitting a quietly inconsistent report.
    if with_prices + without_prices != total:
        log.error(
            "inconsistent price coverage: %d + %d != %d",
            with_prices, without_prices, total,
        )

    delisted_total = _scalar(conn, _COUNT_DELISTED)
    delisted_with = _scalar(conn, _COUNT_DELISTED_WITH_PRICES)
    delisted_without = _scalar(conn, _COUNT_DELISTED_WITHOUT_PRICES)

    if delisted_with + delisted_without != delisted_total:
        log.error(
            "inconsistent delisting coverage: %d + %d != %d",
            delisted_with, delisted_without, delisted_total,
        )

    first_seen = _scalar(conn, _COUNT_FIRST_SEEN)
    fundamental_tickers = _scalar(conn, _COUNT_FUNDAMENTAL_TICKERS)

    return {
        "total_securities": total,
        "securities_by_type": _by_security_type(conn),
        "securities_with_prices": with_prices,
        "securities_without_prices": without_prices,
        "delisted_total": delisted_total,
        "delisted_with_prices": delisted_with,
        "delisted_without_prices": delisted_without,
        "securities_with_first_seen": first_seen,
        "securities_without_first_seen": max(total - first_seen, 0),
        "fundamental_tickers": fundamental_tickers,
    }


def _pct(numerator, denominator):
    if not denominator:
        return "n/a"
    return f"{100.0 * numerator / denominator:.1f}%"


def render_markdown(report):
    lines = []
    lines.append("# Data completeness")
    lines.append("")
    lines.append("Read-only audit of the research universe. Counts are aggregate")
    lines.append("SQL over the live database; nothing is downloaded or written.")
    lines.append("")

    total = report["total_securities"]
    with_prices = report["securities_with_prices"]
    without_prices = report["securities_without_prices"]

    lines.append("## Securities")
    lines.append("")
    lines.append("| Metric | Count | Share |")
    lines.append("|---|---:|---:|")
    lines.append(f"| Total securities | {total} | 100.0% |")
    lines.append(f"| With at least one price row | {with_prices} | {_pct(with_prices, total)} |")
    lines.append(f"| With no price rows | {without_prices} | {_pct(without_prices, total)} |")
    lines.append("")

    by_type = report.get("securities_by_type") or {}
    if by_type:
        lines.append("## By security type")
        lines.append("")
        lines.append("| Security type | Count |")
        lines.append("|---|---:|")
        for name, count in by_type.items():
            lines.append(f"| {name} | {count} |")
        lines.append("")

    d_total = report["delisted_total"]
    d_with = report["delisted_with_prices"]
    d_without = report["delisted_without_prices"]

    lines.append("## Delistings")
    lines.append("")
    lines.append("| Metric | Count | Share |")
    lines.append("|---|---:|---:|")
    lines.append(f"| Delisted securities | {d_total} | 100.0% |")
    lines.append(f"| With price rows | {d_with} | {_pct(d_with, d_total)} |")
    lines.append(f"| With no price rows | {d_without} | {_pct(d_without, d_total)} |")
    lines.append("")

    first_seen = report["securities_with_first_seen"]
    lines.append("## Date coverage")
    lines.append("")
    lines.append("| Metric | Count | Share |")
    lines.append("|---|---:|---:|")
    lines.append(f"| Securities with a listing date | {first_seen} | {_pct(first_seen, total)} |")
    lines.append(
        f"| Securities without a listing date | {report['securities_without_first_seen']} "
        f"| {_pct(report['securities_without_first_seen'], total)} |"
    )
    lines.append(f"| Distinct tickers in daily_fundamentals | {report['fundamental_tickers']} | n/a |")
    lines.append("")

    return "\n".join(lines) + "\n"


def write_reports(report, out_dir):
    os.makedirs(out_dir, exist_ok=True)

    json_path = os.path.join(out_dir, "data_completeness.json")
    md_path = os.path.join(out_dir, "data_completeness.md")

    # Write to a temp file and rename so an interrupted run cannot leave a
    # half-written report that a later stage would happily parse.
    tmp_json = json_path + ".tmp"
    with open(tmp_json, "w", encoding="utf-8") as fh:
        json.dump(report, fh, indent=2, sort_keys=True)
        fh.write("\n")
    os.replace(tmp_json, json_path)

    tmp_md = md_path + ".tmp"
    with open(tmp_md, "w", encoding="utf-8") as fh:
        fh.write(render_markdown(report))
    os.replace(tmp_md, md_path)

    return json_path, md_path


def _market_data_path(cfg):
    """Resolve the research-universe database path from config.

    The project has more than one SQLite file: `positions.db` is the trade
    ledger (what the system did) and `market_data.db` is the research universe
    (what the market did). Auditing the wrong one produces a clean, plausible
    report about the wrong thing, so the path is read from config and never
    defaulted to a filename.
    """
    if not isinstance(cfg, dict):
        raise SystemExit("config.yaml did not load as a mapping; cannot locate market_data_path")
    db_cfg = cfg.get("database") or {}
    path = db_cfg.get("market_data_path")
    if not path:
        raise SystemExit(
            "config.yaml is missing database.market_data_path; refusing to guess "
            "which database to audit"
        )
    return path


def main(argv=None):
    parser = argparse.ArgumentParser(description="Audit research universe completeness.")
    parser.add_argument("--out-dir", default="reports", help="directory for the reports")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    # load_config() is the single source of truth for the database path and
    # universe settings; reading config.yaml directly here would let the two
    # drift apart.
    cfg = universe.load_config()
    db_path = _market_data_path(cfg)

    conn = connect(db_path)
    try:
        # Log the path and the prices row count before any other query. A run
        # against the wrong database then announces itself in the first line of
        # output instead of hiding inside a plausible-looking report.
        price_rows = _scalar(conn, _COUNT_PRICE_ROWS)
        log.info("auditing database at %s (%d rows in prices)", db_path, price_rows)
        report = collect(conn)
    finally:
        conn.close()

    json_path, md_path = write_reports(report, args.out_dir)
    log.info("wrote %s and %s", json_path, md_path)

    print(
        "securities: {total} total, {with_p} with prices, {without_p} without; "
        "delisted: {d_total} total, {d_with} with prices, {d_without} without".format(
            total=report["total_securities"],
            with_p=report["securities_with_prices"],
            without_p=report["securities_without_prices"],
            d_total=report["delisted_total"],
            d_with=report["delisted_with_prices"],
            d_without=report["delisted_without_prices"],
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
