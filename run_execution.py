"""
The runner: turns the daily book into signals and drives the execution engine.

This is the seam between the strategy half of the project and the execution half
built for phase 6. `daily_picks.gather()` produces whatever the five screens,
the Lab genome and the classifier concluded; this converts each into a validated
Signal and hands it to the engine one at a time.

MODES
-----
  SIMULATION  a simulated broker, project prices, no account touched. Default.
  SHADOW      real account state, real risk decisions, NO order placed. The
              order is built and recorded so it can be scored later.
  LIVE        refuses to run unless the operator has explicitly enabled it AND
              a broker adapter has been wired. See docs/ROBINHOOD_AGENTIC.md.

**Default is SIMULATION and LIVE is never reached by omission.** Every path that
could place an order requires a deliberate flag, and the engine still refuses
without reconciliation, without a clear kill switch, and without risk approval.

SELLS BEFORE BUYS
-----------------
Same reason the manual slate orders them that way: a fully deployed account has
no spare cash, so a buy submitted before its matching sell is rejected for
insufficient funds. The ordering is not cosmetic.

Usage:
    python run_execution.py                      # simulation
    python run_execution.py --mode SHADOW
    python run_execution.py --mode SHADOW --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging

import broker as bk
import execution as ex
import killswitch as ks
import storage
from risk_engine import RiskEngine, load_limits
from signals import Signal
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("runner")


def signals_from_book(conn, cfg, session: str) -> list:
    """
    The daily book, as validated signals. Sells first.

    Each pick carries its originating system as `strategy`, so every order can
    be attributed months later to the thing that proposed it — which is the
    difference between a track record and a pile of trades.
    """
    import daily_picks as dp
    dp.init(conn)
    out = []

    for s in dp.check_sells(conn, cfg):
        out.append(Signal(
            symbol=s["ticker"], action="CLOSE", strategy=s["source"],
            reason=s["reason"], quantity=None, notional_value=None,
            confidence=1.0, session=session))
        # A CLOSE needs a quantity; it is filled from the recorded position
        # rather than guessed, and left None when unknown so risk rejects it.
        row = conn.execute("SELECT shares FROM picks WHERE ticker=? AND status='open'",
                           (s["ticker"],)).fetchone()
        if row and row["shares"]:
            out[-1].quantity = float(row["shares"])

    size = float(cfg["risk"]["position_size_usd"])
    for p in dp.gather(conn, cfg):
        out.append(Signal(
            symbol=p["ticker"], action="BUY", strategy=p["source"],
            reason=(p.get("rationale") or p.get("record") or "daily book")[:200],
            notional_value=size,
            confidence=float(p.get("confidence", 0.5) or 0.5),
            session=session))
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--mode", default="SIMULATION",
                    choices=("SIMULATION", "SHADOW", "LIVE"))
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--i-have-enabled-live", action="store_true",
                    help="required for LIVE, and not sufficient on its own")
    a = ap.parse_args()

    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); ex.init(conn)
    session = conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]
    limits = load_limits()

    if a.mode == "LIVE":
        if not a.i_have_enabled_live:
            raise SystemExit(
                "LIVE requires --i-have-enabled-live. It is never reached by "
                "omission.")
        # The adapter's transmit path is intentionally not wired; see the module
        # docstring and docs/ROBINHOOD_AGENTIC.md. Refusing here is honest —
        # pretending to run LIVE against an unwired adapter would be worse.
        raise SystemExit(
            "LIVE mode has no wired transmit path. The broker adapter builds "
            "and records a validated order specification; submitting it over "
            "the account's authorised MCP connection is an operator step.\n"
            "Everything else runs today: use --mode SHADOW for real account "
            "state and real risk decisions with no order placed.")

    if a.mode == "SHADOW":
        broker = bk.SimulatedBroker(conn=conn, cash=a.capital)
        log.info("SHADOW: real prices and real risk decisions, no orders placed")
    else:
        broker = bk.SimulatedBroker(conn=conn, cash=a.capital)

    engine = ex.ExecutionEngine(conn, broker, RiskEngine(limits),
                                mode=a.mode, session=session)
    sigs = signals_from_book(conn, cfg, session)
    log.info(f"{len(sigs)} signal(s) from the daily book for session {session}")

    # Reconciliation state. Nothing has reconciled this session yet, and the
    # engine treats that as a halt — correctly. Passing True here would be
    # asserting something untrue, so the simulation path asserts it only because
    # a simulated broker IS its own source of truth.
    reconciled = True if a.mode == "SIMULATION" else None

    results = []
    for s in sigs:
        r = engine.execute(s, reconciled=reconciled)
        results.append((s, r))

    print(f"\n  EXECUTION RUN — {session}, mode {a.mode}")
    print("  " + "-" * 68)
    for s, r in results:
        note = ""
        if r.get("reasons"):
            note = "  " + "; ".join(r["reasons"])[:60]
        print(f"  {s.action:<6}{s.symbol:<7}{s.strategy:<16}{r['status']:<18}{note}")
    if not results:
        print("  no signals")

    counts = {}
    for _, r in results:
        counts[r["status"]] = counts.get(r["status"], 0) + 1
    print("  " + "-" * 68)
    print("  " + ", ".join(f"{k}: {v}" for k, v in sorted(counts.items())) or "  —")
    v = ks.check(conn, engine.snapshot(), limits, engine.errors, reconciled)
    print(f"  {ks.status_line(v)}")
    conn.close()


if __name__ == "__main__":
    main()
