"""
Ledger reconciliation to the cent (Stage AD1.3). Read-only against the broker; writes a report and, on a gap above
`TOLERANCE`, a system event. Answers: does the system's own trade ledger explain the real account exactly?

Two checks, both against Robinhood's own figures:

1. **Realised P&L by day** — Robinhood's `get_realized_pnl` against the slot ledger (`live_pnl.compute`, LIVE). A day
   whose difference exceeds the tolerance is listed. (09-24's -$0.74 is the owner's manual ACT sale before the first
   LIVE run: it is outside the slot ledger by design and is excluded by START.)
2. **Account value now** — the starting equity + the ledger's realised net + the open slot positions valued at the
   BROKER's market value (not our marks) against the broker's total value. Our own marks are taken at different times
   from the broker's; that timing, not missing money, was the earlier $0.23 "gap" (found 2026-10-20: 2 cents remain).

    ./venv/bin/python ledger_check.py [--write]       # daily.sh [9k7]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import sqlite3
import sys
from datetime import date
from pathlib import Path

from universe import load_config

ROOT = Path(__file__).resolve().parent
START = "2026-09-25"           # first day of slot-only realised P&L (09-24 holds the owner's manual ACT sale)
TOLERANCE = 0.05


def _num(x) -> float:
    try:
        return float(x)
    except (TypeError, ValueError):
        return 0.0


def broker_figures(account: str, call=None) -> dict:
    """Robinhood's realised P&L by day, positions' market value and total value."""
    if call is None:
        import robinhood_mcp as rh
        res = rh.calls([("get_realized_pnl", {"account_number": account}), ("get_portfolio", {"account_number": account}),
                        ("get_equity_positions", {"account_number": account})])
    else:
        res = [call(t, {"account_number": account}) for t in ("get_realized_pnl", "get_portfolio", "get_equity_positions")]
    pnl, port, pos = res
    by_day = {}
    for p in (pnl.get("data") or {}).get("data_points", []):
        if p.get("realized_gain") is not None:
            by_day[p["start_time"][:10]] = _num(p["realized_gain"])
    d = port.get("data") or {}
    rows = (pos.get("data") or {}).get("positions") or (pos.get("data") if isinstance(pos.get("data"), list) else [])
    held = {r["symbol"]: _num(r.get("quantity")) for r in rows or [] if r.get("symbol") and _num(r.get("quantity")) > 0}
    # The positions call carries no prices; the portfolio's equity_value is every stock position at the broker's marks.
    return {"realized_by_day": by_day, "total_value": _num(d.get("total_value")), "equity_value": _num(d.get("equity_value")),
            "positions": held}


def check(conn, cfg, broker: dict) -> dict:
    import live_pnl
    d = live_pnl.compute(conn, cfg, "LIVE")
    led = {}
    for t in d["closed"]:
        led[t["closed"][:10]] = led.get(t["closed"][:10], 0.0) + t["net"]
    days = sorted(set(led) | {k for k in broker["realized_by_day"] if k >= START})
    diffs = []
    for k in days:
        if k < START:
            continue
        b, l_ = broker["realized_by_day"].get(k, 0.0), led.get(k, 0.0)
        if abs(b - l_) > TOLERANCE:
            diffs.append((k, b, l_))
    first = conn.execute("SELECT equity FROM live_equity ORDER BY at LIMIT 1").fetchone()
    start_eq = float(first[0]) if first else 0.0
    basis = sum(o["entry"] * o["quantity"] for o in d["open"])
    open_syms = {o["symbol"] for o in d["open"]}
    outside = sorted(s for s in broker["positions"] if s not in open_syms)
    broker_mv = broker["equity_value"]
    expected = start_eq + d["closed_total"]["net"] + (broker_mv - basis)
    gap = broker["total_value"] - expected
    return {"start_equity": start_eq, "realised_net": d["closed_total"]["net"], "open_basis": basis,
            "open_broker_value": broker_mv, "outside_slots": outside, "expected": expected,
            "broker_total": broker["total_value"], "gap": gap, "day_diffs": diffs, "days": len(days),
            "ok": abs(gap) <= TOLERANCE and not diffs and not outside}


def render(r: dict) -> str:
    L = [f"# Ledger check — {date.today().isoformat()} (Stage AD1.3)", "",
         f"Start equity ${r['start_equity']:.2f} + ledger realised {r['realised_net']:+.2f} + open slot positions at the "
         f"broker's value (${r['open_broker_value']:.2f} on a basis of ${r['open_basis']:.2f}) = expected ${r['expected']:.2f}; "
         f"broker total ${r['broker_total']:.2f}; **gap {r['gap']:+.2f}** ({'within' if abs(r['gap']) <= TOLERANCE else 'OUTSIDE'} "
         f"the ${TOLERANCE:.2f} tolerance).", ""]
    if r["outside_slots"]:
        L.append("Held at the broker but not by the slots (placed by hand?): " + ", ".join(r["outside_slots"])
                 + " — their value is inside the broker's figures, so the gap includes them.")
    L.append(f"Realised P&L by day since {START}: {r['days']} days compared; "
             + ("all match within the tolerance." if not r["day_diffs"] else
                "differences: " + "; ".join(f"{k} broker {b:+.2f} vs ledger {l_:+.2f}" for k, b, l_ in r["day_diffs"])))
    L += ["", "A remaining gap of a few cents is dividends, cash interest or fractional rounding, which the trade ledger "
          "does not record. The broker's realised figure for the current day can lag until it settles."]
    return "\n".join(L) + "\n"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--write", action="store_true")
    a = ap.parse_args(argv)
    cfg = load_config()
    import risk_engine
    acct = str((risk_engine.load_limits().get("robinhood") or {}).get("account_number") or "")
    conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
    r = check(conn, cfg, broker_figures(acct))
    text = render(r)
    print(text)
    if a.write:
        p = ROOT / "reports" / f"ledger_check_{date.today().isoformat()}.md"
        p.write_text(text)
    if not r["ok"]:
        try:
            import killswitch
            w = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
            killswitch.init(w)
            killswitch.record_event(w, "ledger_gap", f"gap {r['gap']:+.2f}; days {len(r['day_diffs'])}", "warning")
        except Exception:                                       # noqa: BLE001 — a report never fails the run
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
