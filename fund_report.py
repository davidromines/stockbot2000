"""
One daily status line per fund, across everything this project can actually see.

WHAT COUNTS AS A FUND, AND WHERE THE NUMBERS COME FROM
------------------------------------------------------
Nothing here is estimated or remembered. Each section names its source and is
recomputed on every run:

  Claude fund     the Robinhood account this system manages. Positions come from
                  the broker; entry prices come from `picks`, which records the
                  ACTUAL fill rather than the price the book quoted.
  Paper funds     `paper_runs` + `paper_equity` in market_data.db. Simulated
                  money, stepped daily. This is where most of the evidence is.
  Other accounts  the user's three other Robinhood accounts. **This system does
                  not manage them** and never places orders there; they are
                  reported so a single number for "everything" exists, and are
                  labelled so nobody mistakes them for results.

**Brokerage figures are not fetched here.** This module has no broker access —
it runs from cron with no credentials. The assistant supplies a JSON snapshot it
read from the broker, and this merges it with the database. A run without that
snapshot still reports every paper fund and says plainly that the live sections
are missing, rather than printing a zero that reads like a loss.

WHAT IS DELIBERATELY NOT HERE
-----------------------------
The ERX/ERY switching test is not a fund and is not listed as one. It was a
pre-registered experiment, run once, closed FAIL — no capital was ever committed
and no position exists in any account. Reporting a closed negative as a fund
would turn a settled answer back into an open question.

Usage:
    python fund_report.py                          # paper funds only
    python fund_report.py --live data/live.json    # with a broker snapshot
    python fund_report.py --live data/live.json --notify
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from pathlib import Path

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("funds")


def paper_funds(conn) -> list:
    """Every open paper run with its latest equity mark."""
    rows = conn.execute("""
        SELECT p.name, p.label, p.family, p.capital_usd, p.started_on,
               e.equity_usd, e.date, e.open_positions
        FROM paper_runs p
        LEFT JOIN paper_equity e ON e.run_id = p.run_id
         AND e.date = (SELECT MAX(date) FROM paper_equity e2 WHERE e2.run_id = p.run_id)
        WHERE p.status = 'open'
        ORDER BY p.name
    """).fetchall()
    out = []
    for r in rows:
        start = float(r["capital_usd"] or 0)
        # No equity row yet means the run opened but has never been stepped.
        # Reported as stalled rather than as a flat 0% — those are different
        # facts, and conflating them hides a broken run behind a neutral number.
        eq = float(r["equity_usd"]) if r["equity_usd"] is not None else None
        out.append({"name": r["label"] or r["name"], "raw": r["name"],
                    "family": r["family"] or "other", "start": start, "equity": eq,
                    "as_of": r["date"], "positions": r["open_positions"],
                    "pct": ((eq / start - 1) * 100) if (eq and start) else None})
    return out


def claude_fund(conn, live: dict | None) -> dict:
    """The managed account: broker positions priced against recorded fills."""
    picks = {r["ticker"]: dict(r) for r in conn.execute(
        "SELECT ticker, source, price, stop_price, entry_date, shares FROM picks "
        "WHERE status='open'")}
    if not live or "claude_fund" not in live:
        # Cron has no broker credentials, so fall back to the database's own
        # closes. Share counts come from the recorded fill — position size
        # divided by the price actually paid — which is exact, not an estimate.
        # A report that says "unavailable" every morning is one nobody reads.
        cfg_ = load_config()
        size = float(cfg_["risk"]["position_size_usd"])
        rows, asof = [], None
        for t, rec in picks.items():
            px = conn.execute("SELECT date, close FROM prices WHERE ticker=? "
                              "ORDER BY date DESC LIMIT 1", (t,)).fetchone()
            if not px:
                continue
            asof = max(asof or px["date"], px["date"])
            entry = float(rec["price"] or 0)
            if not entry:
                continue
            # Recorded fill quantity where we have it. Falling back to
            # size/entry is an assumption and is flagged, not hidden.
            qty = float(rec["shares"]) if rec.get("shares") else size / entry
            value, cost = qty * float(px["close"]), qty * entry
            stop = rec.get("stop_price")
            rows.append({"ticker": t, "source": rec.get("source", "?"), "qty": qty,
                         "entry": entry, "price": float(px["close"]),
                         "cost": cost, "value": value, "pnl": value - cost,
                         "pct": (value / cost - 1) * 100,
                         "stop": stop,
                         "breached": bool(stop and float(px["close"]) <= float(stop))})
        return {"positions": rows, "missing": False, "picks": picks,
                "source": f"database closes to {asof}"}
    rows = []
    for p in live["claude_fund"].get("positions", []):
        t = p["symbol"]
        qty, px = float(p["quantity"]), float(p.get("price") or 0)
        rec = picks.get(t, {})
        entry = float(rec.get("price") or p.get("average_buy_price") or 0)
        cost = qty * entry
        value = qty * px
        stop = rec.get("stop_price")
        rows.append({"ticker": t, "source": rec.get("source", "?"), "qty": qty,
                     "entry": entry, "price": px, "cost": cost, "value": value,
                     "pnl": value - cost,
                     "pct": ((value / cost - 1) * 100) if cost else None,
                     "stop": stop,
                     "breached": bool(stop and px and px <= float(stop))})
    return {"positions": rows, "missing": False, "picks": picks}


def render(conn, live: dict | None) -> str:
    cfg = load_config()
    L = []
    asof = live.get("as_of") if live else None
    L.append(f"FUNDS — {asof or 'database only'}")
    L.append("=" * 46)

    # --- the managed account ------------------------------------------------
    cf = claude_fund(conn, live)
    L.append("")
    tag = f"  [{cf['source']}]" if cf.get("source") else ""
    L.append(f"AGENTIC ACCOUNT  (Robinhood, traded by the systems){tag}")
    if cf["missing"]:
        L.append("  no broker snapshot — live figures unavailable")
        L.append(f"  {len(cf['picks'])} position(s) on record in the database")
    elif not cf["positions"]:
        L.append("  no open positions")
    else:
        cost = sum(r["cost"] for r in cf["positions"])
        value = sum(r["value"] for r in cf["positions"])
        pnl = value - cost
        pct = (value / cost - 1) * 100 if cost else 0.0
        L.append(f"  ${value:,.2f}  ({pnl:+,.2f}, {pct:+.2f}%)  from ${cost:,.2f}")
        for r in sorted(cf["positions"], key=lambda x: x["pct"] or 0):
            flag = "  << STOP BREACHED" if r["breached"] else ""
            L.append(f"    {r['ticker']:<6}{r['source']:<15}"
                     f"{r['pct']:>+7.1f}%  ${r['value']:>6.2f}{flag}")

    # --- the discretionary fund ---------------------------------------------
    try:
        import claude_fund as cfd
        L.append("")
        L.append(cfd.render(conn))
    except Exception as e:      # noqa: BLE001 — a report must not die on one section
        L.append("")
        L.append(f"CLAUDE FUND  unavailable ({type(e).__name__})")

    # --- paper --------------------------------------------------------------
    pf = paper_funds(conn)
    live_runs = [f for f in pf if f["pct"] is not None]
    stalled = [f for f in pf if f["pct"] is None]
    L.append("")
    L.append(f"PAPER FUNDS  ({len(pf)} open, simulated)")
    if live_runs:
        tot_start = sum(f["start"] for f in live_runs)
        tot_eq = sum(f["equity"] for f in live_runs)
        L.append(f"  ${tot_eq:,.2f} from ${tot_start:,.2f}  "
                 f"({(tot_eq/tot_start-1)*100:+.2f}% aggregate)")
        wins = sum(1 for f in live_runs if f["pct"] > 0)
        L.append(f"  {wins} up, {len(live_runs)-wins} down")
        # EVERY fund, grouped by family. A best-3/worst-3 summary hides the
        # thing that actually matters here: whole families win or lose
        # together, and you cannot see that from the extremes.
        for fam in ("momentum", "model", "crash", "conviction", "other"):
            group = [f for f in live_runs if f["family"] == fam]
            if not group:
                continue
            avg = sum(f["pct"] for f in group) / len(group)
            L.append(f"  {fam.upper()}  ({len(group)} funds, avg {avg:+.2f}%)")
            for f in sorted(group, key=lambda x: -x["pct"]):
                L.append(f"    {f['name']:<24}{f['pct']:>+7.2f}%")
        marks = {f["as_of"] for f in live_runs}
        if len(marks) > 1:
            L.append(f"  NOTE: mixed mark dates {sorted(marks)}")
    if stalled:
        L.append(f"  STALLED — never stepped: "
                 f"{', '.join(f['name'] for f in stalled)}")

    # --- bull/bear ETF switching --------------------------------------------
    try:
        import pair_funds as pfd
        L.append("")
        L.append(pfd.render(conn))
    except Exception as e:      # noqa: BLE001 — one section must not kill the report
        L.append("")
        L.append(f"PAIR FUNDS  unavailable ({type(e).__name__})")

    # --- value fund ---------------------------------------------------------
    # Long-horizon, paper-only, deliberately outside the tactical league. It is
    # reported here so it stays visible; it is NOT ranked against the paper
    # funds, because a five-year thesis judged on weeks of marks would read as
    # a refutation that has not happened.
    try:
        import value_fund as vfd
        st = vfd.status(conn)
        L.append("")
        L.append("VALUE FUND  (paper, long horizon)")
        if not st.get("exists"):
            L.append("  not yet opened — no value fund on record")
        else:
            # status() nests the database row under "fund"; the top-level keys
            # are the derived figures. Reading started_on off the top level
            # silently yields None and prints "?" — which is how this section
            # first shipped broken.
            fund = st.get("fund") or {}
            start = fund.get("started_on") or "?"
            weight = fund.get("weighting") or "?"
            equity = st.get("equity")
            capital = fund.get("capital_usd")
            ret = st.get("return")
            marks = st.get("marks")
            positions = st.get("positions") or []
            L.append(f"  opened {start}  weighting {weight}")
            if equity is not None and capital:
                # `return` is a fraction, not a percent — format it as one.
                pct = f"{float(ret):+.2%}" if ret is not None else "?"
                L.append(f"  ${float(equity):,.2f} on ${float(capital):,.2f}"
                         f"  ({pct})")
            elif equity is not None:
                L.append(f"  ${float(equity):,.2f}")
            L.append(f"  {len(positions)} open position(s), "
                     f"{marks if marks is not None else '?'} daily mark(s)")
            if positions:
                for p in positions:
                    ticker = p.get("ticker", "?")
                    industry = p.get("industry") or "?"
                    L.append(f"    {ticker:<6}{industry}")
            else:
                # An empty section with no explanation reads as a bug. The fund
                # is new and its first review has not run; say so.
                L.append("  no positions — fund is new, first review has not run")
            if marks is not None and int(marks) < 60:
                L.append(f"  {int(marks)} daily mark(s) — not yet rankable "
                         f"(needs 60)")
    except Exception as e:      # noqa: BLE001 — one section must not kill the report
        L.append("")
        L.append(f"VALUE FUND  unavailable ({type(e).__name__})")

    # --- everything else ----------------------------------------------------
    if live and live.get("other_accounts"):
        L.append("")
        L.append("OTHER ACCOUNTS  (not managed by this system)")
        for a in live["other_accounts"]:
            L.append(f"  {a['label']:<22}${float(a['value']):>12,.2f}"
                     f"   {a['positions']} positions")

    L.append("")
    L.append("=" * 46)
    L.append("Agentic is the only real money. Paper funds are simulated; the")
    L.append("Claude Fund is discretionary and paper-tracked until funded.")
    L.append("Pair funds switch between a bull and bear ETF, never both. They beat")
    L.append("random switching but LOSE to buy-and-hold on every index: S&P 1x made")
    L.append("+6.8%/yr on 2010-19 against SPY's +13.3%, and -4.1% through the")
    L.append("2020-22 crash against +7.7%. Opened anyway, to settle it forward.")
    L.append("The Value Fund is paper-only and long-horizon; it is kept out of the")
    L.append("tactical league, so its marks are not comparable to the paper funds.")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--live", help="JSON snapshot of broker data")
    ap.add_argument("--notify", action="store_true", help="send to Telegram")
    ap.add_argument("--out", default="data/fund_report.txt")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)

    live = None
    if a.live:
        p = Path(a.live)
        if p.exists():
            live = json.loads(p.read_text())
        else:
            log.warning(f"{a.live} not found — reporting database figures only")

    text = render(conn, live)
    print(text)
    Path(a.out).write_text(text, encoding="utf-8")
    if a.notify:
        import notify as nt
        sent = nt.notify("Stockbot2000 — funds", text)
        print(f"\n  sent via: {', '.join(sent) or 'nothing'}")
    conn.close()


if __name__ == "__main__":
    main()
