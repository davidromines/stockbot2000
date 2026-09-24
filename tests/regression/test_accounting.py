"""
Regression tests for accounting.py (Addendum B §B18) and the two
paper_trading.py fixes of 2026-09-24.

The accounting module exists because four fund engines disagreed about when a
trade is charged, and every disagreement inflated equity. These tests pin the
arithmetic and, more importantly, the reconciliation verdicts: a difference
that is fully explained by a known cause must not be reported as an unexplained
accounting problem, and a difference with no explanation must not be waved
through as EXPLAINED.

Plain script, no pytest — matches the other tests in tests/regression.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import accounting
import paper_trading

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}" + (f"  [{detail}]" if detail else ""))
        FAILED.append(name)


class StubCost:
    """Fixed round-trip cost, so the arithmetic under test is not the cost model's."""

    enabled = True

    def __init__(self, amount=0.2):
        self.amount = amount

    def round_trip(self, *a, **k):
        return self.amount


def _paper_db(positions_usd=24.0, cash=81.9):
    """
    One paper run: capital 100, one closed trade (+2 gross, 0.1 costs), one open
    position of 2 shares entered at 10 and marked at 12.

    cash is passed in rather than derived so a test can hold the ledger fixed
    and move only the engine's own curve — which is the thing reconciliation is
    supposed to catch.
    """
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE paper_runs (
            run_id TEXT PRIMARY KEY, name TEXT, strategy TEXT,
            capital_usd REAL, cash_usd REAL, started_on TEXT, last_step_on TEXT,
            status TEXT, created_at TEXT, last_review TEXT, label TEXT, family TEXT);
        CREATE TABLE paper_equity (
            run_id TEXT, date TEXT, cash_usd REAL, positions_usd REAL,
            equity_usd REAL, open_positions INTEGER);
        CREATE TABLE paper_trades (
            run_id TEXT, ticker TEXT, entry_date TEXT, exit_date TEXT,
            entry_price REAL, exit_price REAL, shares REAL,
            gross_pnl_usd REAL, costs_usd REAL, net_pnl_usd REAL, pnl_pct REAL,
            exit_reason TEXT);
        CREATE TABLE paper_positions (
            run_id TEXT, ticker TEXT, entry_date TEXT, entry_price REAL,
            shares REAL, stop_price REAL, days_held INTEGER);
        CREATE TABLE prices (
            ticker TEXT, date TEXT, open REAL, high REAL, low REAL, close REAL,
            volume REAL, source TEXT);
        CREATE TABLE features (ticker TEXT, date TEXT, dollar_volume_20 REAL);
    """)
    conn.execute("INSERT INTO paper_runs VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("r1", "test_run", "model", 100.0, cash, "2026-09-01",
                  "2026-09-22", "open", "2026-09-01T00:00:00", None, "Test Run", None))
    conn.execute("INSERT INTO paper_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                 ("r1", "AAA", "2026-09-02", "2026-09-10", 10.0, 12.0, 1.0,
                  2.0, 0.1, 1.9, 20.0, "horizon_timeout"))
    conn.execute("INSERT INTO paper_positions VALUES (?,?,?,?,?,?,?)",
                 ("r1", "BBB", "2026-09-15", 10.0, 2.0, 9.0, 3))
    conn.execute("INSERT INTO prices VALUES (?,?,?,?,?,?,?,?)",
                 ("BBB", "2026-09-22", 11.0, 12.5, 10.8, 12.0, 100000.0, "test"))
    conn.execute("INSERT INTO features VALUES (?,?,?)", ("BBB", "2026-09-22", 5_000_000.0))
    conn.execute("INSERT INTO paper_equity VALUES (?,?,?,?,?,?)",
                 ("r1", "2026-09-22", cash, positions_usd, cash + positions_usd, 1))
    conn.commit()
    return conn


def main():
    print("\naccounting.py — _row identity and reconciliation verdicts")

    # --- 2. identity ------------------------------------------------------
    r = accounting._row(as_of="2026-09-22", fund_kind="paper", fund_id="x",
                        label="x", capital_usd=100.0, gross_usd=5.0,
                        costs_realized=1.0, costs_open=0.5, equity_original=None,
                        open_positions=0, closed_trades=0, cost_basis="modeled")
    check("_row costs_usd = realized + open", abs(r["costs_usd"] - 1.5) < 1e-9,
          f"got {r['costs_usd']}")
    check("_row net_usd = gross - costs", abs(r["net_usd"] - 3.5) < 1e-9,
          f"got {r['net_usd']}")
    check("_row equity_restated = capital + net",
          abs(r["equity_restated"] - 103.5) < 1e-9, f"got {r['equity_restated']}")
    check("_row with no original curve is RECONCILED",
          r["recon_status"] == "RECONCILED", r["recon_status"])

    # --- 3. RECONCILED ----------------------------------------------------
    # The engine's curve agrees with capital + gross - costs_realized. Note the
    # open round trip is deliberately NOT in this comparison: the engine has not
    # paid it, so charging it here would manufacture a difference.
    r = accounting._row(as_of="2026-09-22", fund_kind="paper", fund_id="x",
                        label="x", capital_usd=100.0, gross_usd=5.0,
                        costs_realized=1.0, costs_open=0.5, equity_original=104.0,
                        open_positions=0, closed_trades=0, cost_basis="modeled")
    check("agreeing original curve is RECONCILED",
          r["recon_status"] == "RECONCILED" and r["reconciled"] == 1,
          f"{r['recon_status']} diff={r['recon_diff_usd']}")

    # --- 4. EXPLAINED -----------------------------------------------------
    # Off by 3.0, and the two known causes account for all 3.0.
    r = accounting._row(as_of="2026-09-22", fund_kind="paper", fund_id="x",
                        label="x", capital_usd=100.0, gross_usd=5.0,
                        costs_realized=1.0, costs_open=0.5, equity_original=107.0,
                        cash_drift_usd=2.0, mark_diff_usd=1.0,
                        open_positions=0, closed_trades=0, cost_basis="modeled")
    check("fully explained difference is EXPLAINED",
          r["recon_status"] == "EXPLAINED", r["recon_status"])
    check("explained difference leaves ~0 unexplained",
          abs(r["unexplained_usd"]) < 1e-9, f"got {r['unexplained_usd']}")

    # --- 5. ACCOUNTING_PROBLEM -------------------------------------------
    r = accounting._row(as_of="2026-09-22", fund_kind="paper", fund_id="x",
                        label="x", capital_usd=100.0, gross_usd=5.0,
                        costs_realized=1.0, costs_open=0.5, equity_original=107.0,
                        open_positions=0, closed_trades=0, cost_basis="modeled")
    check("unexplained difference is ACCOUNTING_PROBLEM",
          r["recon_status"] == "ACCOUNTING_PROBLEM", r["recon_status"])
    check("unexplained difference is reported in full",
          abs(r["unexplained_usd"] - 3.0) < 1e-9, f"got {r['unexplained_usd']}")

    print("\naccounting.py — paper_funds on a hand-built ledger")

    # --- 6. consistent ledger --------------------------------------------
    # cash 81.9 = 100 - 20 (open cost basis) + 1.9 (net of the closed trade).
    conn = _paper_db(positions_usd=24.0, cash=81.9)
    rows = accounting.paper_funds(conn, StubCost(0.2))
    check("paper_funds returns the open run", len(rows) == 1, f"got {len(rows)}")
    if rows:
        p = rows[0]
        check("gross = closed gross + open mark-to-market",
              abs(p["gross_usd"] - 6.0) < 1e-9, f"got {p['gross_usd']}")
        check("costs_open = round trip on the open position",
              abs(p["costs_open"] - 0.2) < 1e-9, f"got {p['costs_open']}")
        check("costs_realized = costs the engine charged",
              abs(p["costs_realized"] - 0.1) < 1e-9, f"got {p['costs_realized']}")
        check("equity_restated = capital + gross - costs",
              abs(p["equity_restated"] - (100.0 + 6.0 - 0.3)) < 1e-9,
              f"got {p['equity_restated']}")
        check("consistent ledger reconciles",
              p["recon_status"] == "RECONCILED", p["recon_status"])
    conn.close()

    # --- 7. engine marked the position at entry --------------------------
    # positions_usd 20 instead of 24: the engine valued 2 shares at their 10.00
    # entry rather than the 12.00 close. That is the 2026-09-22 bug, and it must
    # surface as a mark difference rather than as an unexplained problem.
    conn = _paper_db(positions_usd=20.0, cash=81.9)
    rows = accounting.paper_funds(conn, StubCost(0.2))
    check("mark-at-entry run still returns a row", len(rows) == 1, f"got {len(rows)}")
    if rows:
        p = rows[0]
        check("mark difference is -4.00",
              abs(p["mark_diff_usd"] + 4.0) < 1e-9, f"got {p['mark_diff_usd']}")
        check("mark-at-entry is EXPLAINED, not a problem",
              p["recon_status"] == "EXPLAINED", p["recon_status"])
    conn.close()

    print("\npaper_trading.py — stale marks and the no-overwrite rule")

    # --- 8. _stale_marks --------------------------------------------------
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE prices (ticker TEXT, date TEXT, close REAL)")
    conn.execute("INSERT INTO prices VALUES ('X','2026-09-18',7.0)")
    conn.execute("INSERT INTO prices VALUES ('X','2026-09-21',8.0)")
    conn.commit()
    stale = paper_trading._stale_marks(conn, ["X", "Y"], {"Y": 5.0}, "2026-09-22")
    check("_stale_marks returns the last real close for an unmarked ticker",
          stale == {"X": 8.0}, f"got {stale}")
    check("_stale_marks leaves a ticker that has today's price alone",
          "Y" not in stale, f"got {stale}")
    conn.close()

    # --- 9. no-overwrite rule --------------------------------------------
    # Source inspection, because the failure mode is a repeated step silently
    # replacing a held position: the old shares vanish with no trade record
    # while the new buy still leaves cash, and the fund's cash stops
    # reconciling. A plain INSERT plus an IntegrityError skip is the fix.
    with open(os.path.join(ROOT, "paper_trading.py")) as fh:
        src = fh.read()
    check("position inserts skip on conflict rather than replace",
          "except sqlite3.IntegrityError" in src)
    # The conviction step rebalances whole books and keeps its own REPLACE
    # (its cash reconciles); only the genome/model step may not replace.
    remaining = src.count("INSERT OR REPLACE INTO paper_positions")
    import inspect
    import paper_trading as _pt
    conv = inspect.getsource(_pt._conviction_step)
    check("the genome/model step no longer replaces held positions",
          remaining == conv.count("INSERT OR REPLACE INTO paper_positions"),
          f"{remaining} occurrence(s) in the file")

    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED: {', '.join(FAILED)}")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
