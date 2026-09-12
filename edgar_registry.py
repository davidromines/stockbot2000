"""
A point-in-time registry of every public US company, built from SEC EDGAR.

The survivorship problem in one line: this project holds **5 tickers that stopped
trading during 2006-2019** against 9,029 companies the Internet Archive says
existed. Every backtest is run on a universe from which almost all the failures
have been deleted.

EDGAR fixes the *universe* half of that, for free and without an account. Every
company that has filed with the SEC since 1993 appears in the quarterly form
indexes, with its CIK, name and filing date. A company filing 10-Ks and then
stopping has been acquired, gone private, or died — and the quarter it stops is a
close proxy for when. That is a point-in-time registry going back **fifteen years
further than the Internet Archive reconstruction**, which only reaches 2008.

**What this does not give you is prices.** EDGAR has no market data, so a
delisted company's returns remain unavailable and the backtests stay biased. What
changes is that the bias becomes *measurable per strategy and per window* instead
of estimated from a single 10.4-point average — we will know exactly which
companies were missing on any given date, and how many.

Rate limits are the SEC's published ones: 10 requests/second, and a User-Agent
identifying the operator is required. `--rate` is set well under that. This
module is polite by construction because the alternative is being blocked.

Usage:
    python edgar_registry.py --fetch                # download quarterly indexes
    python edgar_registry.py --build                # parse them into the registry
    python edgar_registry.py --coverage             # what we hold vs what existed
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import logging
import time
from pathlib import Path

import requests

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("edgar")

# The SEC requires a descriptive User-Agent with contact details. Sending a
# browser string instead is both against their guidance and a good way to get the
# whole VM blocked.
UA = "stockbot2000 research davidromines@gmail.com"
BASE = "https://www.sec.gov/Archives/edgar/full-index"
CACHE = Path("data/edgar")
# Forms that mean "an operating company reported this year". Excludes funds,
# trusts and foreign private issuers filing 20-F, which are a different universe.
ANNUAL = {"10-K", "10-K405", "10-KSB", "10-K/A"}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edgar_filers (
            cik           INTEGER NOT NULL,
            year          INTEGER NOT NULL,
            quarter       INTEGER NOT NULL,
            company_name  TEXT NOT NULL,
            form_type     TEXT NOT NULL,
            filed_date    TEXT NOT NULL,
            PRIMARY KEY (cik, year, quarter, form_type)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS edgar_companies (
            cik           INTEGER PRIMARY KEY,
            company_name  TEXT NOT NULL,
            ticker        TEXT,
            first_filed   TEXT NOT NULL,
            last_filed    TEXT NOT NULL,
            n_annual      INTEGER NOT NULL,
            still_filing  INTEGER NOT NULL
        ) STRICT
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_edgar_ticker ON edgar_companies(ticker)")
    conn.commit()


def fetch(start_year: int = 1993, end_year: int | None = None, rate: float = 0.35) -> int:
    """
    Download the quarterly form indexes. Resumable — already-cached files are kept.

    Each index is a few megabytes of fixed-width text listing every filing that
    quarter. Roughly 135 quarters at 1993-2026, so this is a single-digit
    gigabyte download done once, not a recurring cost.
    """
    CACHE.mkdir(parents=True, exist_ok=True)
    end_year = end_year or time.gmtime().tm_year
    session = requests.Session()
    session.headers.update({"User-Agent": UA, "Accept-Encoding": "gzip, deflate"})

    got = skipped = missing = 0
    for year in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            dest = CACHE / f"form_{year}_QTR{q}.idx"
            if dest.exists() and dest.stat().st_size > 1000:
                skipped += 1
                continue
            url = f"{BASE}/{year}/QTR{q}/form.idx"
            # Retry with backoff. The SEC drops connections under sustained load
            # ("Response ended prematurely") rather than returning 429, so a
            # transient failure is indistinguishable from a real one until it is
            # retried — the first run of this lost 120 of 135 quarters that way.
            r = None
            for attempt in range(4):
                try:
                    r = session.get(url, timeout=90)
                    break
                except requests.RequestException as e:
                    wait = rate * (4 ** attempt)
                    log.warning(f"{year} Q{q}: {type(e).__name__}; retry in {wait:.1f}s")
                    time.sleep(wait)
            if r is None:
                log.error(f"{year} Q{q}: giving up after 4 attempts")
                continue
            if r.status_code == 404:
                missing += 1          # future quarters, and 1993 Q1 partials
                continue
            if r.status_code != 200:
                log.warning(f"{year} Q{q}: HTTP {r.status_code}")
                if r.status_code == 403:
                    log.error("403 from the SEC usually means the User-Agent was "
                              "rejected or the rate limit was exceeded. Stopping.")
                    return got
                continue
            dest.write_bytes(r.content)
            got += 1
            if got % 20 == 0:
                log.info(f"  {got} downloaded ({year} Q{q})")
            time.sleep(rate)
    log.info(f"Fetched {got}, already had {skipped}, {missing} not published")
    return got


def _parse(path: Path):
    """
    Yield (form, company, cik, date) from one fixed-width index.

    Parsed by column position rather than by splitting on whitespace: company
    names contain spaces, commas and the occasional tab, and a naive split
    silently mangles roughly one row in twenty.
    """
    text = path.read_text(encoding="latin-1", errors="replace").splitlines()
    start = 0
    for i, line in enumerate(text):
        if line.startswith("---"):
            start = i + 1
            break
    for line in text[start:]:
        if len(line) < 98:
            continue
        form = line[0:12].strip()
        if form not in ANNUAL:
            continue
        name = line[12:74].strip()
        cik = line[74:86].strip()
        date = line[86:98].strip()
        if not cik.isdigit():
            continue
        yield form, name, int(cik), date


def build(conn) -> None:
    init(conn)
    files = sorted(CACHE.glob("form_*.idx"))
    if not files:
        raise SystemExit("No indexes cached. Run --fetch first.")
    log.info(f"Parsing {len(files)} quarterly indexes")

    rows, n = [], 0
    for f in files:
        year, q = int(f.stem.split("_")[1]), int(f.stem.split("QTR")[1])
        for form, name, cik, date in _parse(f):
            rows.append((cik, year, q, name, form, date))
            n += 1
        if len(rows) >= 50000:
            conn.executemany("INSERT OR REPLACE INTO edgar_filers "
                             "(cik,year,quarter,company_name,form_type,filed_date) "
                             "VALUES (?,?,?,?,?,?)", rows)
            conn.commit(); rows = []
    if rows:
        conn.executemany("INSERT OR REPLACE INTO edgar_filers "
                         "(cik,year,quarter,company_name,form_type,filed_date) "
                         "VALUES (?,?,?,?,?,?)", rows)
    conn.commit()
    log.info(f"{n:,} annual filings recorded")

    # Collapse to one row per company, with the span of years it reported.
    conn.execute("DELETE FROM edgar_companies")
    conn.execute("""
        INSERT INTO edgar_companies (cik, company_name, ticker, first_filed,
                                     last_filed, n_annual, still_filing)
        SELECT cik,
               (SELECT company_name FROM edgar_filers x WHERE x.cik = f.cik
                 ORDER BY filed_date DESC LIMIT 1),
               NULL, MIN(filed_date), MAX(filed_date), COUNT(*),
               CASE WHEN MAX(year) >= (SELECT MAX(year) - 1 FROM edgar_filers)
                    THEN 1 ELSE 0 END
        FROM edgar_filers f GROUP BY cik
    """)
    conn.commit()
    tot = conn.execute("SELECT COUNT(*) FROM edgar_companies").fetchone()[0]
    dead = conn.execute("SELECT COUNT(*) FROM edgar_companies WHERE still_filing=0").fetchone()[0]
    log.info(f"{tot:,} distinct companies; {dead:,} stopped filing before the last year")


def map_tickers(conn) -> None:
    """
    Attach current tickers to CIKs from the SEC's own mapping file.

    Only resolves companies that still exist, which is the smaller half of the
    problem — a company that died in 2009 has no entry here. That is expected and
    is exactly the asymmetry being measured: the registry knows the company
    existed, our price database does not, and the ticker map cannot bridge it.
    """
    r = requests.get("https://www.sec.gov/files/company_tickers.json",
                     headers={"User-Agent": UA}, timeout=60)
    r.raise_for_status()
    data = r.json()
    pairs = [(v["ticker"].upper(), int(v["cik_str"])) for v in data.values()]
    conn.executemany("UPDATE edgar_companies SET ticker=? WHERE cik=?", pairs)
    conn.commit()
    n = conn.execute("SELECT COUNT(*) FROM edgar_companies WHERE ticker IS NOT NULL").fetchone()[0]
    log.info(f"Mapped {n:,} CIKs to current tickers from the SEC map")


def coverage(conn) -> None:
    """What existed, per year, against what this project actually holds."""
    init(conn)
    have_years = conn.execute("""
        SELECT COUNT(*) FROM edgar_companies""").fetchone()[0]
    if not have_years:
        raise SystemExit("Registry empty. Run --fetch then --build.")

    print("\n  PUBLIC COMPANIES THAT FILED AN ANNUAL REPORT, vs WHAT WE HOLD PRICES FOR")
    print(f"  {'year':<8}{'filed 10-K':>12}{'we have prices':>16}{'coverage':>11}"
          f"{'missing':>10}")
    print("  " + "-" * 60)
    for year in range(1995, 2027, 3):
        filed = conn.execute("SELECT COUNT(DISTINCT cik) FROM edgar_filers WHERE year=?",
                             (year,)).fetchone()[0]
        if not filed:
            continue
        held = conn.execute("""
            SELECT COUNT(DISTINCT p.ticker) FROM prices p
            WHERE p.date BETWEEN ? AND ?
              AND p.ticker IN (SELECT ticker FROM symbols WHERE security_type='common_stock')
        """, (f"{year}-01-01", f"{year}-12-31")).fetchone()[0]
        pct = held / filed if filed else 0
        print(f"  {year:<8}{filed:>12,}{held:>16,}{pct:>10.0%}{max(filed - held, 0):>10,}")

    print("\n  Coverage above 100% is possible and not an error: we hold ETFs, ADRs and")
    print("  funds that never file a 10-K, while EDGAR counts operating companies that")
    print("  were never listed on an exchange we track. The two populations overlap")
    print("  heavily but are not the same set — read the trend, not the level.")

    dead = conn.execute("SELECT COUNT(*) FROM edgar_companies WHERE still_filing=0").fetchone()[0]
    tot = conn.execute("SELECT COUNT(*) FROM edgar_companies").fetchone()[0]
    print(f"\n  {tot:,} companies have filed an annual report since 1993.")
    print(f"  {dead:,} ({dead/tot:.0%}) stopped filing — acquired, taken private, or failed.")
    print("  Those are the companies a backtest on this database can never buy.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--tickers", action="store_true")
    ap.add_argument("--coverage", action="store_true")
    ap.add_argument("--start", type=int, default=1993)
    ap.add_argument("--rate", type=float, default=0.35,
                    help="Seconds between SEC requests. Their limit is 10/s; stay well under.")
    a = ap.parse_args()

    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)

    if a.fetch:
        fetch(a.start, rate=a.rate)
    if a.build:
        build(conn)
    if a.tickers:
        map_tickers(conn)
    if a.coverage or not (a.fetch or a.build or a.tickers):
        coverage(conn)
    conn.close()


if __name__ == "__main__":
    main()
