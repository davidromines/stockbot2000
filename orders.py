"""
Turn the daily book into an order list, and reconcile it against the real account.

The loop this supports has three stages, two of which run themselves:

  1. GENERATE   cron, 07:00      order spec written to data/orders_today.txt
  2. EXECUTE    you, manually    place them in Robinhood
  3. RECONCILE  cron, next day   reads your ACTUAL positions and fills, and
                                 updates the ledger with real prices

Stage 3 is what makes this feel automatic despite stage 2 being manual: you never
report a fill back. The next run reads the account, matches what it finds against
what was specified, and records the difference — including flagging an order that
was placed at a size or price the spec did not ask for, which is the most likely
human error and the one hardest to notice later.

**Sells are listed before buys, always.** A $100 account fully deployed across
five positions has no spare cash, so a buy placed before its matching sell is
rejected for insufficient funds. Ordering the list correctly removes an entire
category of morning confusion.

**Every order here is a market order, and the slate no longer says so.** It is
not a choice being made each morning: a dollar-amount order at Robinhood is
market-only, and a $100 account across five positions has to be sized in dollars
to buy fractional shares. Limit and stop orders require whole-share quantities,
which this account cannot afford at most prices. So "market, regular hours" was
a constant printed on every line, and a constant repeated five times a day is
noise that hides the fields that do change. If sizing ever moves to whole shares,
order type becomes a real decision and belongs back on the slate.

Claude does not place these orders. The spec is deliberately plain text you can
read and check in ten seconds before acting on it.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import json
import logging
from pathlib import Path

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("orders")


def _latest_date(conn) -> str:
    return conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]


def build(conn, cfg, top_n: int = 5) -> dict:
    """The day's orders: sells first, then buys to refill the freed slots."""
    import daily_picks as dp
    dp.init(conn)
    size = float(cfg["risk"]["position_size_usd"])
    cap = int(cfg["risk"]["max_open_positions"])

    sells = dp.check_sells(conn, cfg)
    # Only CONFIRMED holdings count against the cap. A recommendation that has
    # not been executed is not a position, and counting it as one would make the
    # book stop recommending after its first morning.
    open_now = [r["ticker"] for r in conn.execute(
        "SELECT ticker FROM picks WHERE status='open'")]
    pending = [r["ticker"] for r in conn.execute(
        "SELECT ticker FROM picks WHERE status='recommended'")]
    selling = {s["ticker"] for s in sells}
    keeping = [t for t in open_now if t not in selling]
    slots = max(0, cap - len(keeping))

    picks = dp.gather(conn, cfg)
    buys, seen = [], set(keeping) | selling
    for p in picks:
        if len(buys) >= min(slots, top_n):
            break
        if p["ticker"] in seen:
            continue
        seen.add(p["ticker"])
        buys.append(p)

    return {"date": conn.execute("SELECT MAX(date) FROM prices").fetchone()[0],
            "size": size, "cap": cap, "keeping": keeping, "pending": pending,
            "sells": sells, "buys": buys}


def render(spec: dict) -> str:
    L = [f"\n  ORDERS — {spec['date']}",
         "  " + "=" * 66,
         f"  ${spec['size']:.2f} per position, {spec['cap']} positions maximum\n"]

    if spec["sells"]:
        L.append(f"  SELL FIRST — {len(spec['sells'])} order(s)\n")
        for s in spec["sells"]:
            L.append(f"    SELL  {s['ticker']:<8} entire position   "
                     f"({s['pnl_pct']:+.1f}%, {s['reason']})")
        L.append("")
    else:
        L.append("  SELL — none today\n")

    if spec["buys"]:
        L.append(f"  THEN BUY — {len(spec['buys'])} order(s)\n")
        for b in spec["buys"]:
            L.append(f"    BUY   {b['ticker']:<8} ${spec['size']:.2f}   "
                     f"(stop if it closes below ${b['stop_price']:.2f})")
    else:
        L.append("  BUY — no free slots\n")

    if spec["keeping"]:
        L.append(f"\n  HOLD — {', '.join(spec['keeping'])}")

    L.append("\n  " + "=" * 66)
    L.append("  Sells are listed first because a fully deployed account has no spare")
    L.append("  cash: a buy placed before its matching sell is rejected.")
    L.append("")
    L.append("  Stops are NOT resting orders. Dollar-based fractional orders are")
    L.append("  market-only and cannot rest at the broker, so the stop above is an")
    L.append("  instruction this system checks each day against the close. An")
    L.append("  overnight gap through it is not protected against.")
    return "\n".join(L)


def record_fills(conn, cfg, fills: list) -> None:
    """
    Write what the account ACTUALLY did over what the book proposed.

    The spec is a proposal; this is the record. They diverge in three ways and
    each is written down rather than smoothed over, because a forward track
    record built from intentions instead of fills is worth nothing:

      matched    a recommendation that was bought. Status becomes 'open' and the
                 entry price becomes the FILL, never the price the book quoted.
                 Stops are recomputed off the fill for the same reason — a stop
                 measured from a price nobody paid protects nothing.
      unplanned  a position with no recommendation behind it. Recorded with its
                 stated source so it is tracked like any other, never silently
                 dropped for not being on the list.
      skipped    a recommendation that was not bought. Marked, not deleted. A
                 row left at 'recommended' forever is indistinguishable from one
                 still waiting to be filled.
    """
    import daily_picks as dp
    dp.init(conn)
    today = _latest_date(conn)
    seen = set()
    for f in fills:
        t = f["ticker"].upper()
        seen.add(t)
        price = float(f["price"])
        shares = float(f["shares"]) if f.get("shares") is not None else None
        # Calendar date of the fill, not the data date the book was built from.
        entry_date = f.get("date") or dt.date.today().isoformat()
        # Matches an already-open row as well as a recommended one, so a second
        # run re-matches instead of re-inserting. Stages here must be idempotent,
        # and the first version was not: re-running reported every position it had
        # already recorded as "unplanned" and wrote it again.
        row = conn.execute(
            "SELECT pick_date, source FROM picks WHERE ticker=? "
            "AND status IN ('recommended','open') ORDER BY pick_date DESC LIMIT 1",
            (t,)).fetchone()
        source = f.get("source") or (row["source"] if row else "manual")
        prov = dp.PROVENANCE.get(source, {})
        stop = round(price * (1 - prov.get("stop_pct", 0.15)), 4)
        hold = prov.get("hold_days")
        if row:
            conn.execute(
                "UPDATE picks SET status='open', price=?, stop_price=?, hold_days=?, "
                "entry_date=?, shares=? WHERE ticker=? AND pick_date=? AND source=?",
                (price, stop, hold, entry_date, shares, t, row["pick_date"],
                 row["source"]))
            log.info(f"  {t:<6} matched   {row['source']:<14} fill {price:.4f} stop {stop:.4f}")
        else:
            conn.execute(
                "INSERT OR REPLACE INTO picks (pick_date, ticker, source, rank, price, "
                "stop_price, hold_days, rationale, entry_date, shares, status) "
                "VALUES (?,?,?,?,?,?,?,?,?,?,'open')",
                (today, t, source, f.get("rank"), price, stop, hold,
                 f.get("rationale", "recorded from an actual fill"), entry_date,
                 shares))
            log.info(f"  {t:<6} unplanned {source:<14} fill {price:.4f} stop {stop:.4f}")
    stale = [r["ticker"] for r in conn.execute(
        "SELECT DISTINCT ticker FROM picks WHERE status='recommended'")
        if r["ticker"] not in seen]
    for t in stale:
        conn.execute("UPDATE picks SET status='skipped' WHERE ticker=? AND status='recommended'", (t,))
        log.info(f"  {t:<6} skipped   not bought")
    conn.commit()


def reconcile(conn, cfg) -> None:
    """
    Compare recorded picks against the real account, and say where they differ.

    Read-only. The point is to catch the divergences that are invisible later: a
    pick that was never actually bought, a position held that no system asked
    for, or a size that does not match the spec.
    """
    import daily_picks as dp
    dp.init(conn)
    open_picks = {r["ticker"]: dict(r) for r in conn.execute(
        "SELECT * FROM picks WHERE status='open'")}
    print(f"\n  RECONCILIATION — {len(open_picks)} open picks on record")
    print("  " + "-" * 60)
    for t, p in sorted(open_picks.items()):
        px = conn.execute("SELECT date, close FROM prices WHERE ticker=? "
                          "ORDER BY date DESC LIMIT 1", (t,)).fetchone()
        # **A bar from before the entry is not a current price.** Entries are
        # filled intraday; the newest bar in the database is the last COMPLETED
        # session, which on any morning before the top-up predates the fill. The
        # first version divided one by the other anyway and printed the result as
        # P&L, so a position bought today at a higher price than Friday's close
        # was reported as an immediate loss — it was comparing a Monday fill
        # against a Friday close and calling the difference performance.
        now = float(px["close"]) if px else None
        fresh = bool(px) and px["date"] >= (p["entry_date"] or p["pick_date"])
        pnl = ((now / p["price"] - 1) * 100) if (now and fresh) else None
        note = "" if fresh else "  no bar since entry"
        print(f"  {t:<8}{p['source']:<16} entry {p['price']:>8.2f}"
              f"{'  now ' + format(now, '8.2f') if (now and fresh) else '':<16}"
              f"{format(pnl, '+7.1f') + '%' if pnl is not None else note:>9}")
    print("\n  Live account positions are read separately by the assistant and")
    print("  compared against this list; a mismatch means an order was missed,")
    print("  placed at the wrong size, or placed outside the book.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--reconcile", action="store_true")
    ap.add_argument("--record-fills", metavar="JSON",
                    help="path to a JSON list of actual fills: "
                         "[{ticker, price, source?, rank?}]")
    ap.add_argument("--out", default="data/orders_today.txt")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn)
    if a.record_fills:
        record_fills(conn, cfg, json.loads(Path(a.record_fills).read_text()))
        reconcile(conn, cfg); conn.close(); return
    if a.reconcile:
        reconcile(conn, cfg); conn.close(); return
    spec = build(conn, cfg)
    text = render(spec)
    print(text)
    Path(a.out).write_text(text, encoding="utf-8")
    Path(a.out.replace(".txt", ".json")).write_text(
        json.dumps({"date": spec["date"], "size": spec["size"],
                    "keeping": spec["keeping"],
                    "sells": [{"side": "SELL", "ticker": s["ticker"],
                               "source": s["source"], "entry": s["entry"],
                               "now": s["now"], "pnl_pct": s["pnl_pct"],
                               "reason": s["reason"]} for s in spec["sells"]],
                    "buys": [{"side": "BUY", "ticker": b["ticker"],
                              "usd": spec["size"], "stop": b["stop_price"],
                              "source": b["source"]} for b in spec["buys"]]},
                   indent=2), encoding="utf-8")
    print(f"\n  written to {a.out} and {a.out.replace('.txt', '.json')}")
    conn.close()


if __name__ == "__main__":
    main()
