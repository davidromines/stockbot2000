"""
The Claude Fund — positions I choose myself, tracked separately from the systems.

WHAT MAKES THIS DIFFERENT FROM THE DAILY BOOK
----------------------------------------------
`daily_picks.py` reports whatever the screens, the Lab and the classifier output.
This fund does not. It holds what I actually think is worth holding, drawing on
everything visible — the screens' output, the forward paper evidence, the news
feed, the fundamentals — and it is allowed to hold nothing at all.

That last point is the reason it exists. The daily book is structurally obliged
to fill five slots every morning whether or not five good ideas exist, because
`top_n` selection always returns a top N. A fund that can decline to trade is a
different instrument, and its record means something the book's cannot.

**Its track record is kept honest by being separate.** Mixing my judgement into
the systems' numbers would make both unreadable: a good month could be the
screens or could be me, and nobody could tell. Everything here is stamped with a
rationale and a date so the record can be argued with later.

HOW A POSITION GETS IN
----------------------
I add it with `--add`, which records ticker, size, entry, stop, thesis, and the
evidence I am leaning on. Nothing is added without a thesis, because "it looked
good" is not something a later reader can evaluate or falsify.

**I do not place orders.** This records intent; the trades are yours to place,
exactly like the daily slate.

FUNDING
-------
The fund starts UNFUNDED and marks positions at database closes, which makes it
a paper track record until real money is assigned. That is deliberate: it can
build evidence before it costs anything, and `--fund` sets real capital when and
if you decide it has earned some.

Usage:
    python claude_fund.py --status
    python claude_fund.py --fund 100
    python claude_fund.py --add TICKER --usd 20 --stop 0.15 --why "thesis"
    python claude_fund.py --close TICKER --why "reason"
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
from datetime import date

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("claudefund")

FUND = "claude_fund"


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS claude_fund (
            ticker      TEXT NOT NULL,
            opened_on   TEXT NOT NULL,
            usd         REAL NOT NULL,
            entry_price REAL NOT NULL,
            shares      REAL NOT NULL,
            stop_price  REAL,
            thesis      TEXT NOT NULL,
            evidence    TEXT,
            status      TEXT NOT NULL DEFAULT 'open',
            closed_on   TEXT,
            exit_price  REAL,
            exit_reason TEXT,
            PRIMARY KEY (ticker, opened_on)
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS claude_fund_meta (
            key TEXT PRIMARY KEY, value TEXT NOT NULL
        ) STRICT
    """)
    conn.commit()


def _meta(conn, key, default=None):
    r = conn.execute("SELECT value FROM claude_fund_meta WHERE key=?", (key,)).fetchone()
    return r["value"] if r else default


def capital(conn) -> float:
    return float(_meta(conn, "capital_usd", "0") or 0)


def last_close(conn, ticker: str):
    return conn.execute("SELECT date, close FROM prices WHERE ticker=? AND close>0 "
                        "ORDER BY date DESC LIMIT 1", (ticker,)).fetchone()


def status(conn) -> dict:
    """Current marks. Unfunded means paper-tracked, and says so rather than $0."""
    init(conn)
    rows = []
    for r in conn.execute("SELECT * FROM claude_fund WHERE status='open' ORDER BY ticker"):
        px = last_close(conn, r["ticker"])
        now = float(px["close"]) if px else None
        value = r["shares"] * now if now else None
        rows.append({"ticker": r["ticker"], "usd": r["usd"], "entry": r["entry_price"],
                     "shares": r["shares"], "now": now, "value": value,
                     "pct": ((value / r["usd"] - 1) * 100) if value else None,
                     "stop": r["stop_price"],
                     "breached": bool(r["stop_price"] and now and now <= r["stop_price"]),
                     "thesis": r["thesis"], "opened": r["opened_on"],
                     "as_of": px["date"] if px else None})
    closed = list(conn.execute(
        "SELECT ticker, usd, entry_price, exit_price, shares, closed_on, exit_reason "
        "FROM claude_fund WHERE status='closed' ORDER BY closed_on DESC"))
    realised = sum((c["exit_price"] - c["entry_price"]) * c["shares"] for c in closed)
    return {"capital": capital(conn), "open": rows, "closed": closed,
            "realised": realised}


def render(conn) -> str:
    s = status(conn)
    L = ["CLAUDE FUND  (positions I choose, not the systems')"]
    cap = s["capital"]
    L.append(f"  capital: ${cap:,.2f}" if cap else
             "  UNFUNDED — paper-tracked at database closes")
    if not s["open"] and not s["closed"]:
        L.append("  no positions. Holding nothing is a position, and right now")
        L.append("  it is the one the evidence supports.")
        return "\n".join(L)
    deployed = sum(r["usd"] for r in s["open"])
    value = sum(r["value"] or r["usd"] for r in s["open"])
    if deployed:
        L.append(f"  ${value:,.2f} from ${deployed:,.2f}  "
                 f"({value - deployed:+,.2f}, {(value/deployed-1)*100:+.2f}%)")
    for r in s["open"]:
        flag = "  << STOP" if r["breached"] else ""
        pct = f"{r['pct']:+.1f}%" if r["pct"] is not None else "  n/a"
        L.append(f"    {r['ticker']:<6}{pct:>8}  ${r['value'] or 0:>7.2f}{flag}")
        L.append(f"           {r['thesis'][:64]}")
    if s["closed"]:
        L.append(f"  closed: {len(s['closed'])}, realised {s['realised']:+,.2f}")
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--fund", type=float, help="assign real capital")
    ap.add_argument("--add"); ap.add_argument("--usd", type=float, default=20.0)
    ap.add_argument("--stop", type=float, default=0.15, help="stop as a fraction below entry")
    ap.add_argument("--why"); ap.add_argument("--evidence")
    ap.add_argument("--close"); ap.add_argument("--out", default="data/claude_fund.txt")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)

    if a.fund is not None:
        conn.execute("INSERT OR REPLACE INTO claude_fund_meta VALUES ('capital_usd',?)",
                     (str(a.fund),)); conn.commit()
        print(f"  capital set to ${a.fund:,.2f}")
    if a.add:
        if not a.why:
            raise SystemExit("  --why is required. A position without a thesis "
                             "cannot be argued with later, which is the whole point.")
        px = last_close(conn, a.add.upper())
        if not px:
            raise SystemExit(f"  no price for {a.add}")
        entry = float(px["close"])
        conn.execute("INSERT OR REPLACE INTO claude_fund (ticker,opened_on,usd,"
                     "entry_price,shares,stop_price,thesis,evidence,status) "
                     "VALUES (?,?,?,?,?,?,?,?,'open')",
                     (a.add.upper(), date.today().isoformat(), a.usd, entry,
                      a.usd / entry, round(entry * (1 - a.stop), 4), a.why, a.evidence))
        conn.commit(); print(f"  added {a.add.upper()} at {entry:.4f}")
    if a.close:
        px = last_close(conn, a.close.upper())
        conn.execute("UPDATE claude_fund SET status='closed', closed_on=?, exit_price=?, "
                     "exit_reason=? WHERE ticker=? AND status='open'",
                     (date.today().isoformat(), float(px["close"]) if px else None,
                      a.why or "closed", a.close.upper()))
        conn.commit(); print(f"  closed {a.close.upper()}")

    text = render(conn)
    print("\n" + text)
    from pathlib import Path
    Path(a.out).write_text(text, encoding="utf-8")
    conn.close()


if __name__ == "__main__":
    main()
