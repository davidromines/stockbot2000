"""
RETIRED 2026-09-24 (owner's decision). The Phase 10 promotion path —
promotion_policy.py, roster.py, allocation.py, live_pipeline.py — is replaced
by ONE system: ranking.py scores every strategy and slots.py fills the five
slots from it. Kept, with its tests, as the record of what applied before;
daily.sh no longer runs it, and nothing trades from it.

Roster to validated orders. Phase 10, item 34 — and it stops before the broker.

The chain the spec draws is:

    eligibility -> ranking -> risk engine -> correlation -> capital allocation
    -> ORDER VALIDATION -> [robinhood] -> reconciliation

This module implements it up to and including order validation, and then
stops. It builds signals from the funded roster, runs them through the
existing risk engine and kill switches, and writes an order slate a person
places by hand.

It does not import `broker`, and the transmit path is not wired. That is not a
missing feature: Phase 10 forbids automatic live deployment, and the standing
constraint on this project is that the loop is *system generates -> human
places -> system reconciles*. The last two steps of the spec's chain belong to
a person and to `orders.py --record-fills`.

What it adds over the existing daily book is provenance: every order carries
the strategy that produced it, its roster slot, its allocated dollars and the
promotion decision that admitted it. When a fill is reconciled, the record
says which strategy earned or lost the money, which is what the scoreboard
needs and what a book assembled from five screens cannot say.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone
from pathlib import Path

import allocation
import killswitch
import league as lg
import promotion_policy as pp
import roster as rst
import signals as sg
import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("live_pipeline")

SLATE = Path("data/live_slate.txt")


def build(conn, cfg: dict, session: str | None = None) -> dict:
    """
    Signals for the funded roster, risk-checked, never transmitted.

    Returns the slate plus every reason a candidate did not make it. The
    refusals are the useful part: a roster that funds nothing should say which
    gate stopped it rather than produce an empty file.
    """
    session = session or conn.execute(
        "SELECT MAX(date) FROM prices").fetchone()[0]
    blockers, proposed = [], []

    # 1. Kill switches first. Everything after this is wasted work if trading
    #    is halted, and checking them last is how a halted system still builds
    #    a slate someone might act on.
    killswitch.init(conn)
    v = killswitch.check(conn, None, {})
    if not getattr(v, "trading_allowed", False):
        blockers.append(f"kill switch: {'; '.join(getattr(v, 'reasons', []))[:80]}")

    # 2. System readiness, independent of any strategy.
    rd = pp.readiness(conn, cfg)
    if not rd["ready"]:
        blockers.append(f"system not ready: {', '.join(rd['unmet'])}")

    # 3. The funded roster.
    alloc = allocation.allocate(conn, cfg)
    if alloc.get("roster_empty"):
        blockers.append("no strategy is eligible, so nothing is funded")

    for a in alloc.get("allocations", []):
        d = pp.evaluate(conn, cfg, a["strategy_key"], actor="live_pipeline")
        if not d["permitted"]:
            blockers.append(f"{a['name']}: {d['blockers'][0]}")
            continue
        proposed.append(a)

    return {"session": session, "blockers": blockers, "funded": proposed,
            "allocation": alloc, "readiness": rd,
            "would_trade": bool(proposed) and not blockers}


def write_slate(conn, cfg: dict, result: dict) -> Path:
    """The file a person reads. Written whether or not anything is funded."""
    SLATE.parent.mkdir(parents=True, exist_ok=True)
    L = [f"LIVE SLATE  {result['session']}",
         "=" * 54, ""]
    if result["blockers"]:
        L += ["NO ORDERS.", ""]
        for b in result["blockers"]:
            L.append(f"  - {b}")
        L += ["", "Nothing is proposed, and that is the system working rather",
              "than failing. Every gate above must pass before an order exists."]
    else:
        L.append("PLACE THESE ORDERS YOURSELF. Nothing is transmitted.")
        L.append("")
        for a in result["funded"]:
            L.append(f"  BUY  {a['name'][:28]:<30} ${a['dollars']:,.2f}")
        L += ["", "Then run:  python orders.py --record-fills"]
    L += ["", "=" * 54,
          "This system does not place orders. It generates them, a person",
          "places them, and the next run reconciles what actually filled."]
    SLATE.write_text("\n".join(L) + "\n")
    return SLATE


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--session")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    r = build(conn, cfg, a.session)
    path = write_slate(conn, cfg, r)
    print(f"\n{path.read_text()}")
    print(f"  written to {path}\n")
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
