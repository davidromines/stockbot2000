"""
Consolidated data-integrity report (Stage AD1, Addendum H Phase A). Read-only. One page answering: does every layer
measure the same thing the same way, and what known distortion is still in the numbers?

    1. Fill conventions by layer, and how much of the paper record is restated at next-open fills
    2. Corporate actions flagged in the restated paper record (an adjusted/unadjusted price mismatch reads as a loss)
    3. The live ledger against the account's equity change
    4. Backup coverage of the forward and decision tables
    5. Survivorship backtests carrying the dispersion the risk-adjusted ranking needs
    6. The pre-registered prospective test's progress
    7. Live fill quality against the decision-time quote
    8. The Robinhood sign-in's age

    ./venv/bin/python integrity_report.py [--write]     -> reports/integrity_<date>.md
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
import time
from datetime import date
from pathlib import Path

from universe import load_config

ROOT = Path(__file__).resolve().parent
EXPECTED_FORWARD = ("paper_runs", "paper_trades", "paper_trades_restated", "slot_trades", "slot_assignments", "orders",
                    "live_equity", "minute_bars", "intraday_runner_signals", "experiment_registry", "alpha_trials",
                    "allocator_shadow", "capital_gate_shadow")


def _has(conn, t: str) -> bool:
    return conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone() is not None


def collect(conn) -> dict:
    out = {}
    closed = conn.execute("SELECT COUNT(*) FROM paper_trades WHERE pnl_pct IS NOT NULL").fetchone()[0] \
        if _has(conn, "paper_trades") else 0
    if _has(conn, "paper_trades_restated"):
        n, ca = conn.execute("SELECT COUNT(*), COALESCE(SUM(corporate_action), 0) FROM paper_trades_restated").fetchone()
        top = conn.execute("SELECT ticker, COUNT(*) FROM paper_trades_restated WHERE corporate_action=1 GROUP BY 1 "
                           "ORDER BY 2 DESC LIMIT 5").fetchall()
    else:
        n, ca, top = 0, 0, []
    out["restated"] = {"closed": closed, "restated": n, "share": (n / closed) if closed else None,
                       "corporate_action": ca, "ca_share": (ca / n) if n else None, "ca_top": top}
    try:
        import live_attribution as la
        r = la.build(conn)
        a = r["account"]
        fq = r["trades"]["fill_vs_quote"].dropna() if len(r["trades"]) else []
        out["ledger"] = {"gap": a.get("ledger_gap"), "change": a.get("change"), "realised": a.get("realised"),
                         "unrealised": a.get("unrealised")}
        out["fills"] = {"n": len(fq), "mean": float(fq.mean()) if len(fq) else None}
    except Exception as e:                                       # noqa: BLE001
        out["ledger"] = {"error": f"{type(e).__name__}: {e}"}
        out["fills"] = {}
    import backup
    out["backup"] = {"missing": [t for t in EXPECTED_FORWARD if _has(conn, t) and t not in backup.TABLES],
                     "absent": [t for t in EXPECTED_FORWARD if not _has(conn, t)]}
    if _has(conn, "survivorship_backtests"):
        cols = {r[1] for r in conn.execute("PRAGMA table_info(survivorship_backtests)")}
        if "sd_per_trade" in cols:
            tot, have = conn.execute("SELECT COUNT(*), SUM(sd_per_trade IS NOT NULL) FROM survivorship_backtests "
                                     "WHERE trades > 1").fetchone()
        else:
            tot, have = conn.execute("SELECT COUNT(*) FROM survivorship_backtests").fetchone()[0], 0
        out["dispersion"] = {"rows": tot, "with_sd": have or 0}
    try:
        import prospective_eval as pe
        txt = pe.report(conn, False)
        line = next((x for x in txt.splitlines() if "Pooled entry dates so far" in x or "pooled entry dates" in x.lower()),
                    "")
        out["prospective"] = line.strip()
    except Exception as e:                                       # noqa: BLE001
        out["prospective"] = f"unavailable ({type(e).__name__})"
    try:
        import robinhood_mcp as rh
        at = rh.login_at()
        out["login_days"] = (time.time() - at) / 86400 if at else None
    except Exception:                                            # noqa: BLE001
        out["login_days"] = None
    return out


def render(d: dict) -> str:
    r, lg, fl = d["restated"], d.get("ledger", {}), d.get("fills", {})
    f = lambda v, s="{:+.2f}": "n/a" if v is None else s.format(v)     # noqa: E731
    L = [f"# Data integrity — {date.today().isoformat()} (Stage AD1)", "",
         "## 1. Fill conventions", "",
         "| layer | entry fill | exit fill |", "|---|---|---|",
         "| simulator / backtests | next open | next open after the triggering close |",
         "| paper engine (original record) | signal-day close | triggering close |",
         "| paper record, restated (`paper_trades_restated`) | next open | next open |",
         "| live slots | market order at or after the open | market order when a 5-minute check fires |", "",
         f"Restated: {r['restated']:,} of {r['closed']:,} closed paper trades ({f(r['share'], '{:.0%}')}); the rest exit on "
         "the newest bar and have no next open yet. Decision layers (allocator, prospective test, funnel honest column) read "
         "the restated record. The paper engine's own convention is unchanged (a separate, careful change: it must defer "
         "orders across daily runs).", "",
         "## 2. Corporate actions", "",
         f"{r['corporate_action']:,} restated trades ({f(r['ca_share'], '{:.2%}')}) carry the corporate-action flag (an implausible "
         "one-trade move consistent with an adjusted/unadjusted price mismatch). Most frequent: "
         + (", ".join(f"{t} {n}" for t, n in r["ca_top"]) or "none") + ". Flagged trades are excluded from the restated "
         "statistics; the originals are kept.", "",
         "## 3. Live ledger", "",
         (f"Equity change {f(lg.get('change'))}; ledger realised {f(lg.get('realised'))} + unrealised "
          f"{f(lg.get('unrealised'))}; gap {f(lg.get('gap'))} (dividends, cash interest and fractional rounding are not in "
          "the trade ledger; to be matched against Robinhood's realised-P&L and dividend records)."
          if "error" not in lg else f"unavailable: {lg['error']}"), "",
         "## 4. Backups", "",
         ("Every expected forward/decision table present is in the nightly backup." if not d["backup"]["missing"]
          else "NOT in the backup: " + ", ".join(d["backup"]["missing"]))
         + (f" Not yet created: {', '.join(d['backup']['absent'])}." if d["backup"]["absent"] else ""), "",
         "## 5. Survivorship dispersion (for risk-adjusted ranking)", "",
         (f"{d['dispersion']['with_sd']:,} of {d['dispersion']['rows']:,} backtest rows carry sd per trade. "
          "Run `survivorship_backtest.py --refill` once to complete it." if d.get("dispersion") else "no table"), "",
         "## 6. Prospective test", "", d.get("prospective") or "n/a", "",
         "## 7. Live fill quality", "",
         (f"{fl.get('n', 0)} buys with a stored decision-time quote: average fill {f(fl.get('mean'), '{:+.3%}')} against it."
          if fl.get("n") else "no stored quotes"), "",
         "## 8. Sign-in", "",
         (f"Last full Robinhood sign-in {d['login_days']:.0f} days ago (renewal warning from 20 days)."
          if d.get("login_days") is not None else "unknown"), ""]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row             # the experiment registry reads rows by name
    text = render(collect(conn))
    print(text)
    if a.write:
        p = ROOT / "reports" / f"integrity_{date.today().isoformat()}.md"
        p.write_text(text)
        print(f"written {p}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
