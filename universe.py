"""
Builds the ticker universe to scan.

Three sources, selected by config.yaml -> universe.source:

- "all_us":  every non-test listing on NASDAQ / NYSE / NYSE American / NYSE Arca /
             Cboe BZX / IEX, from the NASDAQ Trader symbol directory — ~13,000
             instruments, each tagged with a `security_type`. The backfill stores
             all of them; the daily scanner sees only `universe.tradeable_types`
             (common stock by default).
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
import re
from collections import Counter
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

# CQS/ACT dot-suffixes and how Yahoo spells them. Share-class suffixes (.A/.B/.C)
# are not here — those pass through as a single letter, so BRK.B -> BRK-B.
CQS_SUFFIX_TO_YAHOO = {
    "W": "WT", "WS": "WT", "WI": "WI", "WD": "WD",   # warrants / when-issued / when-distributed
    "U": "UN",                                        # units
    "R": "RT", "RT": "RT",                            # rights
}

# Instrument types the daily scanner may trade. Everything else is stored and
# tagged but kept out of the tradeable universe.
DEFAULT_TRADEABLE_TYPES = ["common_stock"]


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


def classify_security_type(name: str, etf_flag: str, symbol: str) -> str:
    """
    Classify a listing from its `Security Name`, which is descriptive and far more
    reliable than symbol-suffix conventions alone.

    Order matters — the checks run most-specific first, because the descriptions
    overlap. Two cases in particular:

    - "American Depositary Shares, each representing two common shares" is an ADR
      of *common stock*. "Depositary Shares, each Representing a 1/1,000th
      Interest in ... Preferred" is *preferred*. Matching "depositary" alone
      merges the two, which would quietly put hundreds of preferred issues into
      the common-stock universe the model trains on.
    - "Trust" is not a fund signal. Plenty of REITs are "... Realty Trust" and are
      ordinary common stock, so only "Fund" is used for closed-end funds.

    The raw name is stored alongside the type, so anything mis-tagged can be
    reclassified later without re-fetching a single bar.
    """
    n = (name or "").lower()

    # Units must be tested before warrants and rights. A SPAC unit is described as
    # "Units, each consisting of one Class A ordinary share and one-half of one
    # redeemable warrant" — it contains the word "warrant", so checking warrants
    # first tags every unit in the market as a warrant.
    if re.search(r"\bunit(s)?\b", n):
        return "unit"
    if re.search(r"\bright(s)?\b", n):
        return "right"
    if "warrant" in n:
        return "warrant"
    if re.search(r"%\s*(senior\s+)?note|notes due|debenture", n):
        return "note"
    if etf_flag == "Y":
        return "etf"
    if re.search(r"\bETN\b", name or ""):
        return "etn"
    if "preferred" in n or re.search(r"\bpfd\b", n):
        return "preferred"
    # Depositary shares that are NOT American Depositary Receipts are preferred.
    if "depositary" in n and "american depositary" not in n:
        return "preferred"
    if "american depositary" in n:
        return "adr"
    if re.search(r"\bfund\b", n):
        return "closed_end_fund"
    return "common_stock"


def normalize_symbol(symbol: str) -> str | None:
    """
    Translate a directory symbol into the ticker Yahoo uses, or None if it cannot
    be expressed.

    The two exchanges spell derivatives differently, and getting this wrong
    silently costs whole instrument classes:

    - NASDAQ symbols pass through verbatim — Yahoo uses the 5th-letter forms
      directly, so the warrant `AACIW` is simply `AACIW`.
    - NYSE/AMEX symbols arrive in CQS notation and must be rewritten: `BRK.B` is
      a share class and becomes `BRK-B`, while `AAC.W` is a warrant and becomes
      `AAC-WT`, `.U` units become `-UN`, `.R` rights become `-RT`. Preferred
      issues arrive as `AGM$C` and become `AGM-PC`.

    Security *type* is no longer decided here — `classify_security_type` does
    that from the security name, which is far more reliable.
    """
    symbol = symbol.strip().upper()
    if not symbol or "^" in symbol:
        return None

    # NYSE/AMEX preferred issues arrive as "AGM$C"; Yahoo writes them "AGM-PC".
    if "$" in symbol:
        base, _, series = symbol.partition("$")
        if not base.isalpha():
            return None
        return f"{base}-P{series}" if series else f"{base}-P"

    if "." in symbol:
        base, _, suffix = symbol.partition(".")
        if not base.isalpha() or not 1 <= len(base) <= 4:
            return None
        # Yahoo spells the derivative suffixes out; share classes stay single letters.
        mapped = CQS_SUFFIX_TO_YAHOO.get(suffix)
        if mapped:
            return f"{base}-{mapped}"
        if len(suffix) == 1 and suffix.isalpha():
            return f"{base}-{suffix}"
        return None

    # NASDAQ symbols are used verbatim by Yahoo, including the 5th-letter forms
    # (AACIW is a warrant and is spelled exactly that way).
    if len(symbol) > 5 or not symbol.isalpha():
        return None
    return symbol


def get_all_us_symbols(config: dict, save_snapshot: bool = True) -> list[dict]:
    """
    Every non-test listing in the NASDAQ Trader directory, tagged by security type.

    Returns *all* instrument types — common stock, ETFs, preferred, warrants,
    units, rights, notes, ADRs and closed-end funds — rather than filtering here.
    Filtering is the caller's job via `security_type`, so the database holds the
    whole market and the daily scanner still only sees what it should trade.
    """
    ucfg = config["universe"]
    timeout = ucfg.get("request_timeout_seconds", 30)
    keep_exchanges = set(ucfg.get("exchanges", ["N", "A", "P", "Z", "V"]))

    snap_dir = Path(ucfg.get("snapshot_dir", "data/symbol_snapshots"))
    today = date.today().isoformat()
    nas_snap = snap_dir / f"{today}_nasdaqlisted.txt" if save_snapshot else None
    oth_snap = snap_dir / f"{today}_otherlisted.txt" if save_snapshot else None

    nasdaq = _fetch_symbol_file(ucfg["nasdaq_listed_url"], timeout, nas_snap)
    other = _fetch_symbol_file(ucfg["other_listed_url"], timeout, oth_snap)
    log.info(f"Symbol directory: {len(nasdaq)} NASDAQ rows, {len(other)} other-listed rows.")

    found: dict[str, dict] = {}
    exchange_names = {"N": "NYSE", "A": "NYSE American", "P": "NYSE Arca",
                      "Z": "Cboe BZX", "V": "IEX"}

    for row in nasdaq:
        if row.get("Test Issue") != "N":
            continue
        raw = row.get("Symbol", "")
        ticker = normalize_symbol(raw)
        if not ticker:
            continue
        name = row.get("Security Name", "").strip()
        found[ticker] = {
            "ticker": ticker,
            "name": name or None,
            "exchange": "NASDAQ",
            "security_type": classify_security_type(name, row.get("ETF", "N"), raw),
        }

    for row in other:
        if row.get("Test Issue") != "N":
            continue
        code = row.get("Exchange")
        if code not in keep_exchanges:
            continue
        raw = row.get("ACT Symbol", "")
        ticker = normalize_symbol(raw)
        if not ticker:
            continue
        name = row.get("Security Name", "").strip()
        found[ticker] = {
            "ticker": ticker,
            "name": name or None,
            "exchange": exchange_names.get(code, code),
            "security_type": classify_security_type(name, row.get("ETF", "N"), raw),
        }

    if not found:
        raise ValueError("Symbol directory parsed but yielded zero listings.")

    result = [found[t] for t in sorted(found)]
    counts = Counter(s["security_type"] for s in result)
    log.info(f"Universe: {len(result)} listings — " +
             ", ".join(f"{k} {v}" for k, v in counts.most_common()))
    return result


def get_all_us_tickers(config: dict) -> list[str]:
    """
    Tickers the daily scanner may trade — common stock only by default.

    The database deliberately holds far more than this. A swing-trading model
    should not train on leveraged ETFs or thinly-quoted warrants, so the tradeable
    universe stays narrow even though the stored universe is the whole market.
    """
    allowed = set(config["universe"].get("tradeable_types", DEFAULT_TRADEABLE_TYPES))
    return [s["ticker"] for s in get_all_us_symbols(config)
            if s["security_type"] in allowed]


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
