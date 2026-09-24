"""
Market cap for names the filings do not cover — a SOURCED fallback, never an
assumed one.

WHY THIS EXISTS
---------------
The risk engine rejects an unknown market cap (the TNON rule: a missing
measurement is not an average one). The only cap this database had came from
parsed SEC filings (`fundamentals.market_cap`), which misses ~800 liquid names
— issuers whose filings are unparsed or mapped to another ticker. On the first
LIVE session that rejected GEN (Gen Digital, ~$14.5B) and NWSA (News Corp,
~$15.9B) as "unknown", and slot 5 bought nothing.

The fix is not to relax the rule. It is to measure the cap from a second source
and record where it came from:

    1. the newest filing cap (fundamentals)    unchanged; wins when present
    2. a quoted cap in `market_cap_quotes`     Robinhood fundamentals (LIVE) or
                                               yfinance (backfill, SIMULATION),
                                               no older than max_age_days

Nothing else. A cap older than the window, or a source that returns nothing,
is still unknown and still rejected. ETFs quote their fund size (AUM) as
market cap; it goes through the same floor, so a small inverse ETF is refused
like a small company.

`market_cap_quotes` is append-only (one row per ticker, source and date): what
the risk engine saw on a given day stays on record.

    python market_caps.py --status              coverage of liquid names
    python market_caps.py --backfill            Robinhood (needs the MCP sign-in), liquid
                                                names without a cap; daily.sh [3c]
    python market_caps.py --backfill --source yfinance    no sign-in; ~1 request per name
    python market_caps.py --lookup GEN NWSA
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import sqlite3
import sys
from datetime import date, datetime, timedelta, timezone

log = logging.getLogger("market_caps")

DEFAULTS = {"max_age_days": 7, "backfill_source": "robinhood",
            "backfill_types": ["common_stock", "etf"]}
_settings = None


def settings(cfg: dict | None = None) -> dict:
    global _settings
    if cfg is not None:
        return {**DEFAULTS, **(cfg.get("market_caps") or {})}
    if _settings is None:
        try:
            from universe import load_config
            _settings = {**DEFAULTS, **(load_config().get("market_caps") or {})}
        except Exception:                                    # noqa: BLE001 — defaults are conservative
            _settings = dict(DEFAULTS)
    return _settings


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS market_cap_quotes (
            ticker      TEXT NOT NULL,
            as_of       TEXT NOT NULL,
            market_cap  REAL NOT NULL,
            source      TEXT NOT NULL,
            fetched_at  TEXT NOT NULL,
            PRIMARY KEY (ticker, as_of, source)
        )""")
    conn.commit()


def record(conn, ticker: str, cap, source: str, as_of: str | None = None) -> bool:
    """Store one quoted cap. A missing or non-positive cap is not stored."""
    try:
        cap = float(cap)
    except (TypeError, ValueError):
        return False
    if not cap > 0:
        return False
    init(conn)
    conn.execute("INSERT OR IGNORE INTO market_cap_quotes VALUES (?,?,?,?,?)",
                 (ticker.upper(), as_of or date.today().isoformat(), cap, source,
                  datetime.now(timezone.utc).isoformat(timespec="seconds")))
    conn.commit()
    return True


def lookup(conn, symbol: str, max_age_days: int | None = None, today: date | None = None) -> tuple:
    """(market_cap, source) or (None, None). Reads only; never fetches."""
    try:
        r = conn.execute("SELECT market_cap FROM fundamentals WHERE ticker=? AND market_cap>0 "
                         "ORDER BY filed DESC LIMIT 1", (symbol,)).fetchone()
        if r and r[0]:
            return float(r[0]), "sec_filing"
    except sqlite3.OperationalError:
        pass
    age = int(max_age_days if max_age_days is not None else settings()["max_age_days"])
    since = ((today or date.today()) - timedelta(days=age)).isoformat()
    try:
        r = conn.execute("SELECT market_cap, source FROM market_cap_quotes WHERE ticker=? AND as_of >= ? "
                         "ORDER BY as_of DESC, fetched_at DESC LIMIT 1",
                         (symbol.upper(), since)).fetchone()
    except sqlite3.OperationalError:                         # table not created yet
        return None, None
    return (float(r[0]), str(r[1])) if r else (None, None)


# --- sources -------------------------------------------------------------------

def fetch_robinhood(conn, symbols: list, call=None, calls=None) -> dict:
    """
    Robinhood get_equity_fundamentals, 10 symbols per call. symbol -> cap stored.

    With no `call`, every chunk runs in ONE MCP session (robinhood_mcp.calls):
    ~80 chunks for the daily backfill instead of ~80 sign-in round trips. If the
    batch fails as a whole, the chunks are retried one by one so one bad chunk
    does not lose the rest.
    """
    import robinhood_live as rl
    import robinhood_mcp as rh
    syms = sorted({s.upper() for s in symbols})
    chunks = [syms[i:i + 10] for i in range(0, len(syms), 10)]
    results = [None] * len(chunks)
    if len(chunks) > 1 and (calls is not None or call is None):
        try:
            results = (calls or rh.calls)([("get_equity_fundamentals", {"symbols": ch}) for ch in chunks])
        except rh.NeedsLogin:
            raise
        except Exception as e:                               # noqa: BLE001
            log.warning(f"batched fundamentals failed ({type(e).__name__}: {e}); retrying per chunk")
            results = [None] * len(chunks)
    call = call or rh.call
    got = {}
    for ch, r in zip(chunks, results):
        if r is None:
            try:
                r = call("get_equity_fundamentals", {"symbols": ch})
            except rh.NeedsLogin:
                raise
            except Exception as e:                           # noqa: BLE001 — stays unknown, fails closed
                log.warning(f"robinhood fundamentals {ch}: {type(e).__name__}: {e}")
                continue
        for rec in rl.rows(r, "results"):
            sym = str(rec.get("symbol") or "").upper()
            cap = rl.num(rec.get("market_cap"))
            if sym in ch and record(conn, sym, cap, "robinhood", rec.get("market_date")):
                got[sym] = cap
    return got


def fetch_yfinance(conn, symbols: list) -> dict:
    """yfinance fast_info market cap (shares x last price). symbol -> cap stored."""
    import yfinance as yf
    got = {}
    for s in symbols:
        try:
            cap = yf.Ticker(s).fast_info.market_cap
        except Exception as e:                               # noqa: BLE001
            log.debug(f"{s}: yfinance market cap failed: {type(e).__name__}")
            continue
        if record(conn, s, cap, "yfinance"):
            got[s.upper()] = float(cap)
    return got


def ensure(conn, symbol: str, source: str, call=None) -> tuple:
    """lookup(), and on a miss one fetch from `source`, then lookup() again."""
    cap, src = lookup(conn, symbol)
    if cap is not None:
        return cap, src
    try:
        if source == "robinhood":
            fetch_robinhood(conn, [symbol], call=call)
        elif source == "yfinance":
            fetch_yfinance(conn, [symbol])
    except Exception as e:                                   # noqa: BLE001
        if type(e).__name__ == "NeedsLogin":                 # an expired sign-in halts LIVE, loudly
            raise
        log.warning(f"{symbol}: market cap fetch failed: {type(e).__name__}: {e}")
    return lookup(conn, symbol)


# --- backfill --------------------------------------------------------------------

def targets(conn, cfg: dict) -> list:
    """Liquid names of the configured types with no filing cap and no fresh quoted cap."""
    risk = cfg.get("risk") or {}
    types = settings(cfg)["backfill_types"]
    ph = ",".join("?" * len(types))
    day = conn.execute("SELECT MAX(date) FROM features WHERE ticker='SPY'").fetchone()[0]
    rows = conn.execute(
        f"SELECT f.ticker FROM features f JOIN symbols s ON s.ticker = f.ticker "
        f"JOIN prices p ON p.ticker = f.ticker AND p.date = f.date "
        f"WHERE f.date = ? AND f.dollar_volume_20 >= ? AND p.close >= ? "
        f"AND s.security_type IN ({ph}) AND COALESCE(s.data_quality, '') = ''",
        (day, float(risk.get("min_dollar_volume") or 0), float(risk.get("min_price") or 0), *types)
    ).fetchall()
    return sorted(t for (t,) in rows if lookup(conn, t)[0] is None)


def backfill(conn, cfg: dict, source: str | None = None, limit: int | None = None) -> dict:
    init(conn)
    source = source or settings(cfg)["backfill_source"]
    todo = targets(conn, cfg)[:limit] if limit else targets(conn, cfg)
    log.info(f"{len(todo)} liquid names without a market cap; fetching from {source}")
    got = fetch_robinhood(conn, todo) if source == "robinhood" else fetch_yfinance(conn, todo)
    missing = [t for t in todo if t.upper() not in got]
    return {"source": source, "targets": len(todo), "filled": len(got), "still_unknown": missing}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Sourced market-cap fallback for the risk engine.")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--backfill", action="store_true")
    ap.add_argument("--source", choices=("yfinance", "robinhood"))
    ap.add_argument("--limit", type=int)
    ap.add_argument("--lookup", nargs="+")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    init(conn)
    if args.backfill:
        r = backfill(conn, cfg, args.source, args.limit)
        print(f"  {r['source']}: {r['filled']} of {r['targets']} filled; "
              f"{len(r['still_unknown'])} still unknown (rejected by the risk engine)")
        if r["still_unknown"]:
            print("  still unknown: " + " ".join(r["still_unknown"][:50])
                  + (" ..." if len(r["still_unknown"]) > 50 else ""))
    if args.lookup:
        for s in args.lookup:
            cap, src = lookup(conn, s)
            print(f"  {s:<6} " + (f"${cap/1e9:,.2f}B  ({src})" if cap else "unknown"))
    if args.status or not (args.backfill or args.lookup):
        n = conn.execute("SELECT source, COUNT(DISTINCT ticker), MAX(as_of) FROM market_cap_quotes "
                         "GROUP BY source").fetchall()
        print("  quoted caps: " + (", ".join(f"{s} {c} tickers (newest {d})" for s, c, d in n) or "none"))
        print(f"  liquid names still without a cap: {len(targets(conn, cfg))}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
