"""
Corporate events from 8-K filings, and what actually happens afterwards.

The question behind this is whether news can be traded. The honest framing is
that it cannot be traded *fast* — parsers score 50,000 articles a minute at under
50ms each from co-located servers, and a retail order routed through a broker to
a market maker arrives hundreds of milliseconds to seconds later, by which time
the counterparty filling it is the firm that read the news first.

What can still be traded is **drift**: the tendency of prices to keep moving in
the direction of a surprise for days afterwards. Post-earnings announcement drift
has been documented since Ball & Brown (1968). It needs no speed, only patience,
which is the one advantage a small account genuinely has.

So this module measures rather than trades. It reads 8-K filings — the primary
source that financial journalism is written *about* — buckets them by the SEC's
own item codes, and reports the forward return distribution after each. That
answers "is there anything here at all" before anyone builds a strategy on it.

TIMESTAMP DISCIPLINE, WHICH IS THE WHOLE GAME
---------------------------------------------
A filing's acceptance time is not its filing date. Apple's Q3 8-K was accepted at
20:30 UTC — half past four in the afternoon, New York time, **after the close**.
Measuring its effect from that day's closing price would read a reaction that had
not happened yet, and would look like a spectacular edge.

Entry is therefore always the **next trading day's close** after acceptance.
That is deliberately conservative: it discards the overnight reaction, which is
where much of the move happens, and so understates any real effect. Understating
is the right direction to be wrong in. The exit-pricing bug in this project
inflated results by 71% by being wrong in the other direction.

Usage:
    python edgar_events.py --fetch --limit 500
    python edgar_events.py --measure
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import datetime as dt
import logging
import time

import numpy as np
import pandas as pd
import requests

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("events")

UA = "stockbot2000 research davidromines@gmail.com"

# The SEC's own taxonomy. Reading these rather than a sentiment model's guess is
# the point: the item code is the issuer's own classification of what happened,
# filed under legal obligation, with no interpretation layer in between.
ITEMS = {
    "1.01": "Material agreement entered",
    "1.02": "Material agreement terminated",
    "1.03": "Bankruptcy or receivership",
    "2.01": "Acquisition or disposition completed",
    "2.02": "Results of operations (earnings)",
    "2.03": "Direct financial obligation created",
    "2.04": "Obligation acceleration triggered",
    "2.05": "Exit or disposal costs",
    "2.06": "Material impairment",
    "3.01": "Delisting notice / listing rule failure",
    "3.02": "Unregistered equity sale (dilution)",
    "3.03": "Security holder rights modified",
    "4.01": "Auditor changed",
    "4.02": "Non-reliance on prior financials (restatement)",
    "5.01": "Change in control",
    "5.02": "Director or officer departure",
    "5.03": "Articles or bylaws amended",
    "7.01": "Regulation FD disclosure",
    "8.01": "Other events",
}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edgar_events (
            adsh        TEXT NOT NULL,
            cik         INTEGER NOT NULL,
            ticker      TEXT,
            form        TEXT NOT NULL,
            item        TEXT NOT NULL,
            filed       TEXT NOT NULL,
            accepted    TEXT NOT NULL,   -- UTC, the moment it became public
            PRIMARY KEY (adsh, item)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_item ON edgar_events(item)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_ev_ticker ON edgar_events(ticker, filed)")
    conn.commit()


def fetch(conn, limit=None, rate=0.15, since="2015-01-01") -> None:
    """
    Pull 8-K filings per company from the SEC submissions API.

    One request per company rather than per filing: the submissions endpoint
    returns a company's entire recent filing history in a single response, with
    item codes and acceptance timestamps already attached. Paced at well under
    the SEC's published 10 requests/second.
    """
    init(conn)
    rows = conn.execute("""
        SELECT DISTINCT cik, ticker FROM sec_filings
        WHERE ticker IS NOT NULL ORDER BY ticker""").fetchall()
    if limit:
        rows = rows[:limit]
    s = requests.Session()
    s.headers.update({"User-Agent": UA, "Accept": "application/json"})
    log.info(f"Fetching 8-K events for {len(rows):,} companies")

    out, n, got = [], 0, 0
    for cik, ticker in rows:
        n += 1
        try:
            r = s.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", timeout=45)
            if r.status_code != 200:
                continue
            rec = r.json().get("filings", {}).get("recent", {})
        except Exception:
            time.sleep(rate * 4)
            continue
        forms = rec.get("form", [])
        for i, form in enumerate(forms):
            if not form.startswith("8-K"):
                continue
            filed = rec["filingDate"][i]
            if filed < since:
                continue
            items = (rec.get("items") or [""] * len(forms))[i]
            acc = (rec.get("acceptanceDateTime") or [""] * len(forms))[i]
            if not acc:
                continue
            for it in [x.strip() for x in items.split(",") if x.strip()]:
                out.append((rec["accessionNumber"][i], int(cik), ticker, form,
                            it, filed, acc))
                got += 1
        if len(out) >= 20000:
            conn.executemany("INSERT OR REPLACE INTO edgar_events "
                             "(adsh,cik,ticker,form,item,filed,accepted) "
                             "VALUES (?,?,?,?,?,?,?)", out)
            conn.commit(); out = []
        if n % 250 == 0:
            log.info(f"  {n:,}/{len(rows):,} companies | {got:,} event rows")
        time.sleep(rate)
    if out:
        conn.executemany("INSERT OR REPLACE INTO edgar_events "
                         "(adsh,cik,ticker,form,item,filed,accepted) "
                         "VALUES (?,?,?,?,?,?,?)", out)
    conn.commit()
    tot = conn.execute("SELECT COUNT(*) FROM edgar_events").fetchone()[0]
    log.info(f"edgar_events: {tot:,} rows")


def measure(conn, horizons=(1, 5, 21), min_n=100) -> None:
    """
    Forward returns after each event type, against the market over the same days.

    Two rules make this honest rather than flattering:

    **Entry is the next trading day's close after acceptance.** Not the filing
    date's close — Apple's earnings 8-K was accepted at 16:30 New York time, and
    measuring from that day's close would read a reaction that had not happened.
    The cost is the overnight move, which is where much of the reaction lands, so
    every number here understates the true effect. That is the safe direction.

    **The baseline is the stock's own behaviour, not the index.** The first
    version of this benchmarked against SPY and produced a table where *every*
    event category was negative at *every* horizon — which is not a signal, it is
    Bessembinder's result showing through: the median stock underperforms a
    cap-weighted index, because the index is carried by a few enormous winners.
    Any random sample of filers would have produced the same negative column, so
    the table was measuring the size effect and calling it news.

    Each event is now scored against the same ticker's median forward return over
    the whole period. That asks the only question worth asking: given this
    company, did this event change what happened next?
    """
    init(conn)
    cal = [r[0] for r in conn.execute(
        "SELECT DISTINCT date FROM prices WHERE date>='2014-01-01' ORDER BY date")]

    rows = conn.execute("""
        SELECT ticker, item, accepted FROM edgar_events
        WHERE ticker IS NOT NULL AND accepted != '' ORDER BY ticker""").fetchall()
    log.info(f"Measuring {len(rows):,} events across {len(horizons)} horizons")

    px_cache: dict = {}
    base_cache: dict = {}
    results: dict = {}
    for ticker, item, accepted in rows:
        if ticker not in px_cache:
            px_cache[ticker] = dict(conn.execute(
                "SELECT date, close FROM prices WHERE ticker=? AND close>0 "
                "AND date>='2014-01-01'", (ticker,)))
        px = px_cache[ticker]
        if not px:
            continue
        # Per-ticker baseline: the median h-day forward return on ALL days. This
        # is what "normal" looks like for this company, and an event only counts
        # if it moved the stock relative to its own normal.
        if ticker not in base_cache:
            arr = np.array([px[d] for d in cal if d in px], dtype="float64")
            base_cache[ticker] = {}
            for h in horizons:
                if len(arr) > h + 20:
                    fwd = arr[h:] / arr[:-h] - 1.0
                    fwd = fwd[np.isfinite(fwd) & (np.abs(fwd) < 5)]
                    base_cache[ticker][h] = float(np.median(fwd)) if fwd.size else 0.0
                else:
                    base_cache[ticker][h] = None
        base = base_cache[ticker]
        # The first session strictly AFTER the acceptance timestamp's date. This
        # is the conservative choice whether the filing landed at 6am or 8pm.
        try:
            acc_date = accepted[:10]
        except Exception:
            continue
        pos = None
        for j in range(len(cal)):
            if cal[j] > acc_date:
                pos = j
                break
        if pos is None or cal[pos] not in px:
            continue
        p0 = px.get(cal[pos])
        if not p0:
            continue
        for h in horizons:
            k = pos + h
            if k >= len(cal) or base.get(h) is None:
                continue
            p1 = px.get(cal[k])
            if not p1:
                continue
            excess = (p1 / p0 - 1) - base[h]
            if abs(excess) < 5:                     # guard against split artifacts
                results.setdefault((item, h), []).append(excess)

    print(f"\n  WHAT HAPPENS AFTER AN 8-K — excess over the same stock's own norm")
    print(f"  Entry is the NEXT session's close after acceptance, so the overnight")
    print(f"  reaction is excluded and every figure understates the true move.\n")
    print(f"  {'item':<6}{'event':<40}{'n':>7}{'+1d':>9}{'+5d':>9}{'+21d':>9}")
    print("  " + "-" * 82)

    items = sorted({i for i, _ in results})
    table = []
    for it in items:
        n = len(results.get((it, horizons[0]), []))
        if n < min_n:
            continue
        cells = []
        for h in horizons:
            v = np.array(results.get((it, h), []))
            cells.append(float(np.median(v)) if v.size else np.nan)
        table.append((it, n, cells))
    for it, n, cells in sorted(table, key=lambda r: -(r[2][-1] if np.isfinite(r[2][-1]) else -9)):
        c = "".join(f"{x:>+9.2%}" if np.isfinite(x) else f"{'—':>9}" for x in cells)
        print(f"  {it:<6}{ITEMS.get(it,'(unclassified)')[:38]:<40}{n:>7,}{c}")

    print("\n  Medians, not means: a handful of takeover pops would otherwise carry")
    print("  an entire category. Read the sample size first — anything under a few")
    print("  hundred events is one company's history wearing a category label.")
    print("\n  This measures whether a signal EXISTS. It is not a strategy: no costs")
    print("  are charged, no position sizing, no survivorship correction, and the")
    print("  events are drawn only from companies that still file today.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--measure", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--since", default="2015-01-01")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)
    if a.fetch:
        fetch(conn, a.limit, since=a.since)
    if a.measure or not a.fetch:
        measure(conn)
    conn.close()


if __name__ == "__main__":
    main()
