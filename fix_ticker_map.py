"""
Repair issuer tickers pointing at preferred series. Phase 9, item 24.

THE DEFECT
----------
`sec_filings.ticker` comes from a CIK->ticker map that, for 212 issuers,
selected a PREFERRED or WARRANT series rather than the common stock. The list
is a who's-who of large caps:

    J P MORGAN CHASE -> JPM-PM        WELLS FARGO -> WFC-PZ
    AT&T            -> T-PC           FORD MOTOR  -> F-PD
    METLIFE         -> MET-PF         SIMON PROPERTY -> SPG-PJ

The consequence is not cosmetic. The conviction screens need price AND
fundamentals under the same ticker. JPM has 11,723 price bars and **zero**
fundamental rows; JPM-PM has 69 fundamental rows and 1,295 price bars. So
JPMorgan, Wells Fargo, AT&T, Ford and MetLife are not ranked poorly by the
fundamental screens — they are **invisible to them**.

That makes this a second, independent cause of the "why does the daily book
never recommend an S&P 500 name" result from 2026-09-14. That investigation
found value ranks were size ranks in disguise and fixed it. This is a separate
mechanism sitting underneath: a slice of the largest companies in the market,
concentrated in financials, could not be screened at all.

THE RULE, AND WHY IT IS NARROW
--------------------------------
A dash does not always mean "preferred". BRK-A and BRK-B are both genuine
common stock, and mapping either to "BRK" would invent a security. So a remap
happens only when BOTH hold:

    the base ticker exists in `symbols` AND is common_stock
    the dashed ticker is NOT itself common_stock

260 of 305 dashed tickers satisfy that; the other 45 are left alone. Being
unable to fix 45 is a better outcome than inventing one wrong mapping, because
a wrong mapping attaches one company's financials to another company's prices
and nothing downstream would ever notice.

The original value is preserved in `ticker_raw` so the repair is auditable and
reversible.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("tickermap")


def plan(conn) -> list:
    """Reads only. Every candidate remap, with the evidence for it."""
    out = []
    for r in conn.execute("SELECT DISTINCT ticker FROM sec_filings "
                          "WHERE ticker LIKE '%-%'"):
        dashed = r[0]
        base = dashed.split("-")[0]
        b = conn.execute("SELECT security_type FROM symbols WHERE ticker=?",
                         (base,)).fetchone()
        d = conn.execute("SELECT security_type FROM symbols WHERE ticker=?",
                         (dashed,)).fetchone()
        base_common = bool(b and b[0] == "common_stock")
        dashed_common = bool(d and d[0] == "common_stock")
        if base_common and not dashed_common:
            n = conn.execute("SELECT COUNT(*) FROM sec_filings WHERE ticker=?",
                             (dashed,)).fetchone()[0]
            out.append({"from": dashed, "to": base, "filings": n,
                        "dashed_type": (d[0] if d else "not listed")})
    return sorted(out, key=lambda x: -x["filings"])


def apply(conn, dry_run: bool = True) -> dict:
    rows = plan(conn)
    if dry_run:
        return {"candidates": len(rows), "updated": 0, "rows": rows}

    have = {r[1] for r in conn.execute("PRAGMA table_info(sec_filings)")}
    if "ticker_raw" not in have:
        conn.execute("ALTER TABLE sec_filings ADD COLUMN ticker_raw TEXT")
        conn.commit()
        log.info("added sec_filings.ticker_raw")

    n = 0
    for r in rows:
        # ticker_raw is set only once: re-running must not overwrite the true
        # original with an already-repaired value and destroy the audit trail.
        cur = conn.execute(
            "UPDATE sec_filings SET ticker_raw = COALESCE(ticker_raw, ticker), "
            "ticker = ? WHERE ticker = ?", (r["to"], r["from"]))
        n += cur.rowcount
    conn.commit()
    return {"candidates": len(rows), "updated": n, "rows": rows}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    res = apply(conn, dry_run=not a.run)

    print(f"\n  ISSUER TICKER REPAIR{'' if a.run else '  (DRY RUN)'}")
    print(f"  {res['candidates']} tickers point at a preferred or warrant series")
    print("  " + "-" * 70)
    print(f"  {'from':<12}{'to':<10}{'filings':>9}   dashed security type")
    for r in res["rows"][:20]:
        print(f"  {r['from']:<12}{r['to']:<10}{r['filings']:>9}   {r['dashed_type']}")
    if len(res["rows"]) > 20:
        print(f"  ... and {len(res['rows']) - 20} more")
    print("  " + "-" * 70)
    if a.run:
        print(f"  updated {res['updated']:,} filing rows; originals kept in "
              f"ticker_raw")
        print("  Re-run value_metrics and fundamental_features to rebuild the")
        print("  screens against the repaired mapping.")
    else:
        print("  Re-run with --run to apply. 45 ambiguous cases are left alone:")
        print("  BRK-A and BRK-B are both real common stock, and inventing one")
        print("  wrong mapping attaches one company's financials to another")
        print("  company's prices where nothing downstream would notice.")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
