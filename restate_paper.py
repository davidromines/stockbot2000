"""
Restate closed paper trades at NEXT-OPEN fills (Addendum F, G1) — beside the originals, never over them.

The paper engine prices an entry at the close of the session that produced the signal and an exit at the
close that triggers it (`paper_trading.py`); the simulator and backtest have used next-open fills since
2026-09-15. A close fill is a price nobody could have traded, so forward records read that way flatter the
strategy by roughly the amount the 09-15 finding measured. This does not touch `paper_trades`. For every
closed trade it stores, in `paper_trades_restated` under an accounting version, what the same trade returns
if it enters at the open of the session AFTER the entry date and exits at the open of the session AFTER the
exit date, on the adjusted price series (so a split or spin-off during the hold is handled by the series,
not booked as a loss), minus the engine's own modelled round-trip cost.

Append-only and idempotent: a (version, run_id, ticker, entry_date) row is written once. A trade whose exit
has no next-session open yet is skipped and picked up by the next run. The table can be rebuilt from
`paper_trades` and `prices` at any time, so it is not in the irreplaceable backup group.

    ./venv/bin/python restate_paper.py            # restate everything that can be
    ./venv/bin/python restate_paper.py --report   # rows per version and family
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import sqlite3
import sys

import numpy as np
import pandas as pd

from audit_forward import attach_prices
from forward_stats import CA_THRESHOLD, corporate_action_flag
from universe import load_config

VERSION = "v2_next_open"


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS paper_trades_restated (
            version          TEXT NOT NULL,
            run_id           TEXT NOT NULL,
            ticker           TEXT NOT NULL,
            entry_date       TEXT NOT NULL,
            exit_date        TEXT NOT NULL,
            entry_open_next  REAL NOT NULL,
            exit_open_next   REAL NOT NULL,
            gross_pct        REAL NOT NULL,
            cost_pct         REAL NOT NULL,
            net_pct          REAL NOT NULL,
            net_usd          REAL NOT NULL,
            corporate_action INTEGER NOT NULL,
            computed_at      TEXT NOT NULL,
            PRIMARY KEY (version, run_id, ticker, entry_date)
        )""")
    conn.commit()


def pending(conn) -> pd.DataFrame:
    """Closed paper trades with no restatement row yet under this version."""
    return pd.read_sql_query(
        """SELECT t.run_id, t.ticker, t.entry_date, t.exit_date, t.entry_price, t.exit_price, t.shares,
                  t.costs_usd AS costs
           FROM paper_trades t
           LEFT JOIN paper_trades_restated r ON r.version = ? AND r.run_id = t.run_id
                AND r.ticker = t.ticker AND r.entry_date = t.entry_date
           WHERE r.run_id IS NULL AND t.pnl_pct IS NOT NULL""", conn, params=(VERSION,))


def restate(conn, limit: int | None = None) -> dict:
    init(conn)
    df = pending(conn)
    if limit:
        df = df.head(limit)
    out = {"pending": int(len(df)), "written": 0, "waiting_for_next_open": 0}
    if df.empty:
        return out
    d = attach_prices(conn, df)
    d["notional"] = d["entry_price"] * d["shares"]
    d["cost_pct"] = d["costs"] / d["notional"] * 100
    ok = d.dropna(subset=["open_next_entry", "open_next_exit"]).copy()
    out["waiting_for_next_open"] = int(len(d) - len(ok))
    if ok.empty:
        return out
    ok["gross_pct"] = (ok["open_next_exit"] / ok["open_next_entry"] - 1) * 100
    ok["net_pct"] = ok["gross_pct"] - ok["cost_pct"]
    ok["net_usd"] = ok["notional"] * ok["net_pct"] / 100
    ok["ca"] = corporate_action_flag(ok, CA_THRESHOLD).astype(int)
    now = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    rows = [(VERSION, r.run_id, r.ticker, r.entry_date, r.exit_date, float(r.open_next_entry), float(r.open_next_exit),
             float(r.gross_pct), float(r.cost_pct), float(r.net_pct), float(r.net_usd), int(r.ca), now)
            for r in ok.itertuples()]
    conn.executemany("INSERT OR IGNORE INTO paper_trades_restated VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    conn.commit()
    out["written"] = len(rows)
    return out


def report(conn) -> str:
    init(conn)
    L = [f"paper_trades_restated, version {VERSION}"]
    n = conn.execute("SELECT COUNT(*) FROM paper_trades_restated WHERE version=?", (VERSION,)).fetchone()[0]
    tot = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE pnl_pct IS NOT NULL").fetchone()[0]
    L.append(f"  restated {n:,} of {tot:,} closed trades ({100 * n / max(tot, 1):.1f}%)")
    for fam, k, m in conn.execute(
            """SELECT p.family, COUNT(*), AVG(r.net_pct) FROM paper_trades_restated r
               JOIN paper_runs p ON p.run_id = r.run_id WHERE r.version=? GROUP BY p.family ORDER BY 2 DESC LIMIT 12""",
            (VERSION,)):
        L.append(f"  {str(fam):<28} n={k:>6,}  mean net (next-open) {m:+.2f}%")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=120)
    if a.report:
        print(report(conn))
        return 0
    r = restate(conn, a.limit)
    print(f"restate_paper {VERSION}: {r['pending']:,} pending, {r['written']:,} written, "
          f"{r['waiting_for_next_open']:,} waiting for a next-session open")
    print(report(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
