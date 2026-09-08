"""
Builds the ticker universe to scan.

Three sources, selected by config.yaml -> universe.source:

- "all_us":  every US common stock on NYSE / NYSE American / NASDAQ, built from the
             NASDAQ Trader symbol directory. ~6,100 tickers. This is the production
             source for the historical backfill.
- "sp500":   S&P 500 constituents scraped from Wikipedia. Wikipedia returns HTTP 403
             to this box, so in practice this falls back to 18 hardcoded tickers —
             which is what the smoke test runs on.
- "custom":  a newline-delimited file of tickers.

Note the deliberate difference in failure behaviour: "sp500" falls back silently
(it is the smoke-test path, and a hardcoded list is a useful stand-in), while
"all_us" raises. A silent fallback from 6,100 tickers to 18 would look like a
successful run and quietly poison everything downstream.
"""
import logging
from datetime import date
from pathlib import Path

import pandas as pd
import requests
import yaml

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("universe")

WIKI_SP500_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"

FALLBACK_TICKERS = [
    "AAPL", "MSFT", "AMZN", "GOOGL", "META", "NVDA", "TSLA", "BRK-B",
    "JPM", "V", "UNH", "HD", "PG", "MA", "XOM", "COST", "JNJ", "AVGO",
]

# NASDAQ 5th-letter suffixes that mean the security is not common stock:
# W=warrant, R=rights, U=unit, P/Q=preferred, Z=misc/depositary.
NON_COMMON_SUFFIXES = set("WRUPQZ")

# Suffixes after a dot that are NOT share classes. BRK.B and BF.B are ordinary
# common stock and must be kept; AAC.W is a warrant and must not be.
DOT_SUFFIX_NOT_COMMON = {"W", "U", "R", "WS", "WI", "WD"}


def load_config(path: str = "config.yaml") -> dict:
    with open(path, "r") as f:
        return yaml.safe_load(f)


# --------------------------------------------------------------------------
# S&P 500 (smoke-test path)
# --------------------------------------------------------------------------

def get_sp500_tickers() -> list[str]:
    try:
        tables = pd.read_html(WIKI_SP500_URL)
        df = tables[0]
        tickers = df["Symbol"].tolist()
        # yfinance wants dots as dashes for tickers like BRK.B -> BRK-B
        tickers = [t.replace(".", "-") for t in tickers]
        log.info(f"Pulled {len(tickers)} S&P 500 tickers from Wikipedia.")
        return tickers
    except Exception as e:
        log.warning(f"Wikipedia scrape failed ({e}); using fallback list of {len(FALLBACK_TICKERS)} tickers.")
        return FALLBACK_TICKERS


# --------------------------------------------------------------------------
# Full US common stock universe (production path)
# --------------------------------------------------------------------------

def _fetch_symbol_file(url: str, timeout: int, snapshot_path: Path | None = None) -> list[dict]:
    """
    Fetch one pipe-delimited NASDAQ Trader directory file and return its rows as
    dicts. Both files carry a trailing 'File Creation Time' line that is not a
    record; it is dropped here.

    If `snapshot_path` is given, the raw response is written there first. These
    snapshots are the primary record: the directory is a live view of what is
    listed *today*, and nobody publishes yesterday's. Keeping the raw file means
    a future point-in-time universe can be reconstructed from what we saw,
    rather than from what is still listed when we ask.
    """
    resp = requests.get(url, timeout=timeout)
    resp.raise_for_status()

    if snapshot_path is not None:
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        snapshot_path.write_text(resp.text, encoding="utf-8")
        log.info(f"Snapshot saved: {snapshot_path}")

    lines = [ln for ln in resp.text.splitlines() if ln and not ln.startswith("File Creation Time")]
    if len(lines) < 2:
        raise ValueError(f"{url} returned no usable rows")

    header = lines[0].split("|")
    rows = []
    for line in lines[1:]:
        parts = line.split("|")
        if len(parts) == len(header):
            rows.append(dict(zip(header, parts)))
    return rows


def normalize_symbol(symbol: str) -> str | None:
    """
    Return the yfinance ticker for a directory symbol, or None if it is not
    ordinary common stock.

    Two shapes are handled:

    - Dotted symbols are share classes or derivative securities. `BRK.B` and
      `BF.B` are common stock and become `BRK-B` / `BF-B`, which is the form
      yfinance expects. `AAC.W` (warrant), `.U` (unit) and `.R` (rights) are
      dropped. Getting this wrong is expensive in both directions: dropping all
      dotted symbols loses Berkshire and Brown-Forman, keeping all of them
      pollutes the universe with ~130 warrants and units.
    - Plain symbols are common stock unless they carry a NASDAQ 5th-letter
      suffix marking a warrant, right, unit or preferred share.

    '$' and '^' always indicate preferred series or when-issued lines.
    """
    symbol = symbol.strip().upper()
    if not symbol or "$" in symbol or "^" in symbol:
        return None

    if "." in symbol:
        base, _, suffix = symbol.partition(".")
        if suffix in DOT_SUFFIX_NOT_COMMON:
            return None
        if len(suffix) != 1 or not suffix.isalpha():
            return None
        if not base.isalpha() or not 1 <= len(base) <= 4:
            return None
        return f"{base}-{suffix}"

    if len(symbol) > 5 or not symbol.isalpha():
        return None
    if len(symbol) == 5 and symbol[4] in NON_COMMON_SUFFIXES:
        return None
    return symbol


def get_all_us_symbols(config: dict, save_snapshot: bool = True) -> list[dict]:
    """
    Build the full US common-stock universe from the NASDAQ Trader symbol directory,
    returning ticker/name/exchange rather than bare tickers.

    Free, no API key, and served as plain text — unlike the Wikipedia scrape, which
    this box gets a 403 from.
    """
    ucfg = config["universe"]
    timeout = ucfg.get("request_timeout_seconds", 30)
    keep_exchanges = set(ucfg.get("exchanges", ["N", "A"]))

    snap_dir = Path(ucfg.get("snapshot_dir", "data/symbol_snapshots"))
    today = date.today().isoformat()
    nas_snap = snap_dir / f"{today}_nasdaqlisted.txt" if save_snapshot else None
    oth_snap = snap_dir / f"{today}_otherlisted.txt" if save_snapshot else None

    nasdaq = _fetch_symbol_file(ucfg["nasdaq_listed_url"], timeout, nas_snap)
    other = _fetch_symbol_file(ucfg["other_listed_url"], timeout, oth_snap)
    log.info(f"Symbol directory: {len(nasdaq)} NASDAQ rows, {len(other)} other-listed rows.")

    found: dict[str, dict] = {}

    for row in nasdaq:
        if row.get("Test Issue") != "N" or row.get("ETF") != "N":
            continue
        ticker = normalize_symbol(row.get("Symbol", ""))
        if ticker:
            found[ticker] = {
                "ticker": ticker,
                "name": row.get("Security Name", "").strip() or None,
                "exchange": "NASDAQ",
            }

    # otherlisted covers NYSE (N) and NYSE American (A); P/Z/V are ARCA/BATS/IEX,
    # which list ETFs rather than operating companies.
    exchange_names = {"N": "NYSE", "A": "NYSE American"}
    for row in other:
        if row.get("Test Issue") != "N" or row.get("ETF") != "N":
            continue
        code = row.get("Exchange")
        if code not in keep_exchanges:
            continue
        ticker = normalize_symbol(row.get("ACT Symbol", ""))
        if ticker:
            found[ticker] = {
                "ticker": ticker,
                "name": row.get("Security Name", "").strip() or None,
                "exchange": exchange_names.get(code, code),
            }

    if not found:
        raise ValueError("Symbol directory parsed but yielded zero common-stock tickers.")

    result = [found[t] for t in sorted(found)]
    log.info(f"Universe: {len(result)} US common stocks on NASDAQ/{'/'.join(sorted(keep_exchanges))}.")
    return result


def get_all_us_tickers(config: dict) -> list[str]:
    """Ticker-only view of `get_all_us_symbols`, for callers that want a plain list."""
    return [s["ticker"] for s in get_all_us_symbols(config)]


def get_custom_tickers(path: str) -> list[str]:
    with open(path, "r") as f:
        return [line.strip().upper() for line in f if line.strip()]


def get_universe(config: dict) -> list[str]:
    source = config["universe"]["source"]
    if source == "sp500":
        return get_sp500_tickers()
    elif source == "all_us":
        return get_all_us_tickers(config)
    elif source == "custom":
        return get_custom_tickers(config["universe"]["custom_tickers_file"])
    else:
        raise ValueError(f"Unknown universe source: {source}")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Build the ticker universe.")
    parser.add_argument("--record", action="store_true",
                        help="Write today's symbol snapshot into the symbols table.")
    args = parser.parse_args()

    cfg = load_config()

    if args.record:
        import storage

        symbols = get_all_us_symbols(cfg)
        conn = storage.connect(cfg["database"]["market_data_path"])
        storage.init_db(conn)
        n = storage.record_symbols(conn, symbols)
        active = conn.execute("SELECT COUNT(*) FROM symbols WHERE is_active=1").fetchone()[0]
        inactive = conn.execute("SELECT COUNT(*) FROM symbols WHERE is_active=0").fetchone()[0]
        conn.close()
        print(f"Recorded {n} symbols. Active: {active}, no longer listed: {inactive}")
    else:
        tickers = get_universe(cfg)
        print(f"Universe size: {len(tickers)}")
        print(tickers[:20], "...")
