"""
The Stockbot Value Fund — paper only. Phase 9, item 30.

WHY THIS IS NOT A PAPER RUN IN THE LEAGUE
-------------------------------------------
The spec insists the two systems stay separate and independently measurable,
and the reason is that they ask different questions:

    tactical : "which strategies are currently producing attractive results?"
    value    : "which companies appear fundamentally undervalued?"

Folding this into `paper_runs` would make it the 22nd member of a league whose
scoreboard ranks on Sharpe and turnover — measures that describe a swing
strategy and say almost nothing about a five-year holding. A value fund that
loses to a momentum fund over eleven weeks has not been refuted, and a league
that reports it as rank 18 of 22 would imply otherwise. So it gets its own
tables and its own review cadence.

WHAT IT HOLDS AND WHY IT SELLS
--------------------------------
Positions come from `value_score`, reviewed QUARTERLY rather than daily. A
company is bought inside the top decile of its industry and sold only when it
falls out of the top 40% — the same hysteresis the conviction screens use,
because a single threshold churns on noise and turnover is the one cost a
long-horizon fund cannot argue away.

**There is no stop loss.** That is deliberate and is the clearest difference
from everything else in this project. A stop converts a fundamental thesis into
a price rule, and a value position falling 30% is either the thesis breaking or
the opportunity improving — a stop cannot tell which, and would reliably sell
the second case.

EVERY POSITION CARRIES ITS REASONING, FROZEN AT ENTRY
-------------------------------------------------------
The full nine-dimension score, the intrinsic-value estimate, the method spread
and the margin of safety are stored as JSON on the position when it is opened,
and never updated. A thesis that can be edited after the fact is not a thesis,
and "I always thought it was risky" is the easiest sentence in investing to say
afterwards.

WHAT THIS FUND CANNOT DO
-------------------------
It cannot reach the broker. It imports neither `execution` nor `broker`, the
same firewall the league operates under. It is paper only, and opening it today
starts a forward record at zero: it will hold no rankable history for about a
quarter, which is the honest starting state rather than a limitation to be
engineered around.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
from datetime import datetime, timezone

import industry
import storage
import value_score as vs
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("value_fund")

FUND = "stockbot_value_fund"
REVIEW_DAYS = 90          # quarterly; a value thesis does not change weekly
BUY_PERCENTILE = 90.0     # top decile of its industry
SELL_PERCENTILE = 40.0    # hysteresis: sell only on falling out of the top 40%
MAX_POSITIONS = 10
MAX_PER_INDUSTRY = 3      # a value screen concentrates; this bounds it

# The literal used by `symbols.security_type` for an ordinary share. Not a
# config option: this is a fact about the data, not a tunable, and a knob here
# would let a strategy edit widen what the fund is allowed to hold.
COMMON_STOCK = "common_stock"


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS value_fund (
            name          TEXT PRIMARY KEY,
            capital_usd   REAL NOT NULL,
            cash_usd      REAL NOT NULL,
            started_on    TEXT NOT NULL,
            last_review   TEXT,
            last_mark     TEXT,
            weighting     TEXT NOT NULL,
            status        TEXT NOT NULL,
            created_at    TEXT NOT NULL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS value_fund_positions (
            name          TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            opened_on     TEXT NOT NULL,
            entry_price   REAL NOT NULL,
            shares        REAL NOT NULL,
            industry      TEXT,
            -- The reasoning, frozen. Never updated after the position opens.
            thesis        TEXT NOT NULL,
            score_at_entry REAL,
            PRIMARY KEY (name, ticker)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS value_fund_trades (
            id            INTEGER PRIMARY KEY AUTOINCREMENT,
            name          TEXT NOT NULL,
            ticker        TEXT NOT NULL,
            opened_on     TEXT, closed_on TEXT,
            entry_price   REAL, exit_price REAL, shares REAL,
            net_pnl_usd   REAL, pnl_pct REAL,
            exit_reason   TEXT NOT NULL,
            thesis        TEXT, score_at_entry REAL, score_at_exit REAL
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS value_fund_equity (
            name          TEXT NOT NULL,
            date          TEXT NOT NULL,
            cash_usd      REAL, positions_usd REAL, equity_usd REAL,
            n_positions   INTEGER,
            PRIMARY KEY (name, date)
        )
    """)
    conn.commit()


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _price(conn, ticker: str, as_of: str):
    r = conn.execute("SELECT close FROM prices WHERE ticker=? AND date<=? "
                     "AND close>0 ORDER BY date DESC LIMIT 1",
                     (ticker, as_of)).fetchone()
    return float(r[0]) if r else None


def is_common_stock(conn, ticker: str) -> bool:
    """
    True only when `symbols` says this ticker is an ordinary share.

    An unknown security type is excluded, not assumed. A ticker absent from
    `symbols`, or present with a NULL `security_type`, returns False: the fund
    would otherwise be free to buy a note, a preferred or a warrant on the
    strength of a fundamentals row that belongs to the issuer rather than to
    the instrument. The rest of the project already fails closed this way.
    """
    r = conn.execute("SELECT security_type FROM symbols WHERE ticker=?",
                     (ticker,)).fetchone()
    if not r or r[0] is None:
        return False
    return str(r[0]).strip().lower() == COMMON_STOCK


def open_fund(conn, capital: float = 100.0, as_of: str | None = None,
              weighting: str = vs.DEFAULT_WEIGHTING) -> dict:
    init(conn)
    if conn.execute("SELECT 1 FROM value_fund WHERE name=?", (FUND,)).fetchone():
        raise SystemExit(f"{FUND} already exists. A forward record is only "
                         f"worth what its start date says, so it is never "
                         f"reopened — close it explicitly if you mean to.")
    as_of = as_of or datetime.now(timezone.utc).date().isoformat()
    conn.execute("""INSERT INTO value_fund (name, capital_usd, cash_usd,
        started_on, weighting, status, created_at) VALUES (?,?,?,?,?,?,?)""",
        (FUND, capital, capital, as_of, weighting, "open", _now()))
    conn.commit()
    log.info(f"opened {FUND} with ${capital:,.2f} on {as_of}")
    return {"name": FUND, "capital": capital, "started_on": as_of}


def candidates(conn, as_of: str, weighting: str, limit: int = 600) -> list:
    """
    Top-decile companies across every industry, best first.

    Ranked within industry and then pooled, never ranked across the market: a
    P/B of 0.9 is unremarkable for a lender and extraordinary for a software
    company, and pooling the raw multiples would simply discover which
    industries are structurally cheap.

    Only common stock is eligible. The percentile cut is taken over the
    eligible names, so a note or a warrant cannot occupy a decile slot that a
    company should have had.
    """
    divs = {d for d in (industry.division_of(r[0])[0] for r in conn.execute(
        "SELECT DISTINCT sic FROM sec_filings WHERE sic IS NOT NULL"))
        if d != "unknown"}
    out = []
    for d in sorted(divs):
        rows = vs.score_division(conn, as_of, d, weighting, limit)
        scored = [r for r in rows
                  if r["composite"] is not None and not r.get("stale")]
        # One lookup per scored name, and only for names that could still make
        # the cut — the type filter runs before the decile is computed so the
        # ranking is over companies rather than over instruments.
        scored = [r for r in scored if is_common_stock(conn, r["ticker"])]
        if len(scored) < 10:
            # A "top decile" of eight companies is the top one. Industries this
            # thin are skipped rather than allowed to contribute a winner by
            # having almost no competition.
            continue
        cutoff = max(1, int(len(scored) * (100 - BUY_PERCENTILE) / 100))
        out.extend(scored[:cutoff])
    out.sort(key=lambda r: -r["composite"])
    return out


def review(conn, as_of: str, dry_run: bool = True) -> dict:
    """One quarterly review: sell what has fallen out, buy what qualifies."""
    init(conn)
    f = conn.execute("SELECT * FROM value_fund WHERE name=?", (FUND,)).fetchone()
    if not f:
        raise SystemExit("no value fund — run --open first")
    f = dict(f)
    held = {r["ticker"]: dict(r) for r in conn.execute(
        "SELECT * FROM value_fund_positions WHERE name=?", (FUND,))}

    cands = candidates(conn, as_of, f["weighting"])
    by_ticker = {c["ticker"]: c for c in cands}

    # --- sells: only on falling out of the top 40% of the industry ----------
    sells = []
    for t, pos in held.items():
        rows = vs.score_division(conn, as_of, pos["industry"], f["weighting"])
        scored = [r for r in rows if r["composite"] is not None]
        me = next((r for r in scored if r["ticker"] == t), None)
        if me is None:
            sells.append((t, None, "no longer scoreable"))
            continue
        rank = 100.0 * (1 - scored.index(me) / max(len(scored), 1))
        if rank < SELL_PERCENTILE:
            sells.append((t, me["composite"],
                          f"fell to the {rank:.0f}th percentile of "
                          f"{pos['industry']} (sell below {SELL_PERCENTILE:.0f})"))

    # --- buys: fill to MAX_POSITIONS, bounded per industry ------------------
    keeping = {t for t in held if t not in {s[0] for s in sells}}
    per_ind: dict = {}
    for t in keeping:
        d = held[t]["industry"]
        per_ind[d] = per_ind.get(d, 0) + 1
    buys = []
    for c in cands:
        if len(keeping) + len(buys) >= MAX_POSITIONS:
            break
        if c["ticker"] in keeping:
            continue
        d = c["division"]
        if per_ind.get(d, 0) >= MAX_PER_INDUSTRY:
            continue
        if _price(conn, c["ticker"], as_of) is None:
            continue
        buys.append(c)
        per_ind[d] = per_ind.get(d, 0) + 1

    if dry_run:
        return {"as_of": as_of, "sells": sells, "buys": buys,
                "held": len(held), "dry_run": True}

    cash = float(f["cash_usd"])
    for t, score_now, why in sells:
        pos = held[t]
        px = _price(conn, t, as_of)
        if px is None:
            continue
        proceeds = px * pos["shares"]
        pnl = proceeds - pos["entry_price"] * pos["shares"]
        conn.execute("""INSERT INTO value_fund_trades (name, ticker, opened_on,
            closed_on, entry_price, exit_price, shares, net_pnl_usd, pnl_pct,
            exit_reason, thesis, score_at_entry, score_at_exit)
            VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (FUND, t, pos["opened_on"], as_of, pos["entry_price"], px,
             pos["shares"], pnl, (px / pos["entry_price"] - 1) * 100, why,
             pos["thesis"], pos["score_at_entry"], score_now))
        conn.execute("DELETE FROM value_fund_positions WHERE name=? AND ticker=?",
                     (FUND, t))
        cash += proceeds

    slots = MAX_POSITIONS - (len(held) - len(sells))
    if buys and slots > 0:
        size = cash / min(len(buys), slots)
        for c in buys[:slots]:
            px = _price(conn, c["ticker"], as_of)
            if px is None or size <= 0:
                continue
            shares = size / px
            thesis = json.dumps({
                "composite": c["composite"],
                "dimensions": c["dimensions"],
                "dimensions_scored": c["dimensions_scored"],
                "weighting": f["weighting"],
                "industry": c["division"],
                "bought_because": (
                    f"top decile of {c['division']} on the "
                    f"{f['weighting']} weighting, scored on "
                    f"{c['dimensions_scored']} of {c['dimensions_total']} "
                    f"dimensions"),
            }, sort_keys=True, default=str)
            conn.execute("""INSERT OR REPLACE INTO value_fund_positions
                (name, ticker, opened_on, entry_price, shares, industry,
                 thesis, score_at_entry) VALUES (?,?,?,?,?,?,?,?)""",
                (FUND, c["ticker"], as_of, px, shares, c["division"],
                 thesis, c["composite"]))
            cash -= size
    conn.execute("UPDATE value_fund SET cash_usd=?, last_review=? WHERE name=?",
                 (cash, as_of, FUND))
    conn.commit()
    return {"as_of": as_of, "sells": sells, "buys": buys,
            "held": len(held), "dry_run": False}


def mark(conn, as_of: str) -> dict:
    """Mark the fund to market. Daily, so a forward record accrues."""
    init(conn)
    f = conn.execute("SELECT * FROM value_fund WHERE name=?", (FUND,)).fetchone()
    if not f:
        return {"marked": False, "reason": "no fund"}
    pos = [dict(r) for r in conn.execute(
        "SELECT * FROM value_fund_positions WHERE name=?", (FUND,))]
    total, priced = 0.0, 0
    for p in pos:
        px = _price(conn, p["ticker"], as_of)
        if px is None:
            # A position that cannot be priced is NOT marked at cost. Carrying
            # it at entry price would report a fund that never loses on the
            # names it can no longer see.
            continue
        total += px * p["shares"]
        priced += 1
    if priced != len(pos):
        return {"marked": False,
                "reason": f"{len(pos) - priced} of {len(pos)} positions could "
                          f"not be priced on {as_of}; refusing to mark a "
                          f"partial book"}
    equity = float(f["cash_usd"]) + total
    conn.execute("""INSERT OR REPLACE INTO value_fund_equity
        (name, date, cash_usd, positions_usd, equity_usd, n_positions)
        VALUES (?,?,?,?,?,?)""",
        (FUND, as_of, f["cash_usd"], total, equity, len(pos)))
    conn.execute("UPDATE value_fund SET last_mark=? WHERE name=?", (as_of, FUND))
    conn.commit()
    return {"marked": True, "date": as_of, "equity": equity,
            "positions": len(pos)}


def status(conn) -> dict:
    init(conn)
    f = conn.execute("SELECT * FROM value_fund WHERE name=?", (FUND,)).fetchone()
    if not f:
        return {"exists": False}
    f = dict(f)
    pos = [dict(r) for r in conn.execute(
        "SELECT * FROM value_fund_positions WHERE name=? ORDER BY score_at_entry DESC",
        (FUND,))]
    eq = [dict(r) for r in conn.execute(
        "SELECT * FROM value_fund_equity WHERE name=? ORDER BY date", (FUND,))]
    trades = conn.execute(
        "SELECT COUNT(*), COALESCE(SUM(net_pnl_usd),0) FROM value_fund_trades "
        "WHERE name=?", (FUND,)).fetchone()
    latest = eq[-1]["equity_usd"] if eq else f["cash_usd"]
    return {"exists": True, "fund": f, "positions": pos, "marks": len(eq),
            "equity": latest, "return": latest / f["capital_usd"] - 1.0,
            "closed_trades": trades[0], "realised_pnl": trades[1]}


def render(s: dict) -> str:
    if not s.get("exists"):
        return "\n  No value fund. Open one with: value_fund.py --open\n"
    f = s["fund"]
    L = ["", "  STOCKBOT VALUE FUND — paper only",
         f"  opened {f['started_on']}   weighting '{f['weighting']}'   "
         f"last review {f['last_review'] or 'never'}",
         f"  equity ${s['equity']:,.2f} on ${f['capital_usd']:,.2f}  "
         f"({s['return']:+.2%})   {s['marks']} daily marks",
         "  " + "-" * 78]
    if s["positions"]:
        L.append(f"  {'ticker':<8}{'industry':<22}{'entry':>10}{'score':>8}  opened")
        for p in s["positions"]:
            L.append(f"  {p['ticker']:<8}{(p['industry'] or '—')[:21]:<22}"
                     f"{p['entry_price']:>10,.2f}"
                     f"{(p['score_at_entry'] or 0):>8.1f}  {p['opened_on']}")
    else:
        L.append("  holds nothing yet")
    L += ["  " + "-" * 78,
          f"  {s['closed_trades']} closed trades, realised "
          f"${s['realised_pnl']:,.2f}"]
    if s["marks"] < 60:
        L += ["",
              f"  NOT YET RANKABLE. {s['marks']} daily marks against the 60 the",
              "  league requires before a return distinguishes skill from noise.",
              "  This fund is measured separately from the tactical league on",
              "  purpose: losing to a momentum strategy over a few weeks does",
              "  not refute a five-year thesis, and a shared scoreboard would",
              "  imply it did."]
    L.append("")
    return "\n".join(L)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--open", action="store_true")
    ap.add_argument("--capital", type=float, default=100.0)
    ap.add_argument("--review", action="store_true")
    ap.add_argument("--apply", action="store_true",
                    help="with --review, actually trade instead of previewing")
    ap.add_argument("--mark", action="store_true")
    ap.add_argument("--as-of")
    ap.add_argument("--thesis", metavar="TICKER")
    a = ap.parse_args()
    cfg = load_config(); runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    init(conn)
    as_of = a.as_of or conn.execute("SELECT MAX(date) FROM prices").fetchone()[0]

    if a.open:
        r = open_fund(conn, a.capital, as_of)
        print(f"\n  opened {r['name']} with ${r['capital']:,.2f} on "
              f"{r['started_on']}\n")

    if a.thesis:
        r = conn.execute("SELECT thesis, opened_on, score_at_entry FROM "
                         "value_fund_positions WHERE name=? AND ticker=?",
                         (FUND, a.thesis)).fetchone()
        if not r:
            print(f"\n  {a.thesis} is not held\n"); conn.close(); return 1
        t = json.loads(r["thesis"])
        print(f"\n  {a.thesis} — bought {r['opened_on']} at score "
              f"{r['score_at_entry']:.1f}")
        print(f"  {t['bought_because']}")
        print("  " + "-" * 60)
        for d, v in (t.get("dimensions") or {}).items():
            print(f"  {d:<18}{'—' if v is None else format(v, '.0f'):>8}")
        print("\n  This reasoning was frozen at entry and is never updated.\n")
        conn.close(); return 0

    if a.review:
        r = review(conn, as_of, dry_run=not a.apply)
        print(f"\n  VALUE FUND REVIEW {r['as_of']}"
              f"{'  (PREVIEW)' if r['dry_run'] else ''}")
        print("  " + "-" * 70)
        for t, sc, why in r["sells"]:
            print(f"  SELL  {t:<8}{why}")
        for c in r["buys"]:
            print(f"  BUY   {c['ticker']:<8}score {c['composite']:.1f}  "
                  f"{c['division']}  ({c['dimensions_scored']}/9 dimensions)")
        if not r["sells"] and not r["buys"]:
            print("  no changes")
        if r["dry_run"]:
            print("\n  Re-run with --apply to trade.")
        print()

    if a.mark:
        m = mark(conn, as_of)
        if m["marked"]:
            print(f"\n  marked {m['date']}: ${m['equity']:,.2f} across "
                  f"{m['positions']} positions")
        else:
            print(f"\n  NOT marked — {m['reason']}")

    print(render(status(conn)))
    conn.close(); return 0


if __name__ == "__main__":
    raise SystemExit(main())
