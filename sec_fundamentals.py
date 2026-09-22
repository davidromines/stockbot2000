"""
Fundamental data from SEC XBRL filings. The raw material for value investing.

Everything this project has searched so far has been price and volume. That is
the high-turnover regime, and the evidence on it is discouraging: Novy-Marx &
Velikov (*A Taxonomy of Anomalies and Their Trading Costs*) find that **few
anomalies with one-sided monthly turnover above 50% survive transaction costs**,
while most below it do — and the ones below it are Value, Gross Profitability and
Size, all rebalanced annually. Our own measurements agree from the other side:
costs consume 87% of gross profit here, and 0 of 20 published technical
strategies beat the null.

So fundamentals are not merely more columns. They are the one family where the
academic evidence survives the cost problem that has defeated everything tried
here so far.

**Source.** The SEC's Financial Statement Data Sets: every numeric fact from the
face financials of every XBRL filing, 2009 to present, one ZIP per quarter, free
and bulk. Each quarter is roughly 60 MB compressed and holds around 7,700 filings
and 3.6 million facts.

**Only wanted tags are kept.** Storing every fact would be ~250 million rows
across the full history to support perhaps thirty ratios. The tag whitelist below
cuts that by more than an order of magnitude, and each entry exists because some
ratio needs it.

**Point-in-time is enforced by `filed`, never by `period`.** A June quarter is
published weeks after June 30, so aligning fundamentals to the period end would
let a backtest read a balance sheet before it existed — the same look-ahead class
that has produced six false results in this project already. Everything is keyed
on the filing date and a deliberate buffer on top.

Usage:
    python sec_fundamentals.py --fetch              # download quarterly ZIPs
    python sec_fundamentals.py --load               # parse them into the database
    python sec_fundamentals.py --status
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import csv
import io
import logging
import time
import zipfile
from pathlib import Path

import requests

import storage
from universe import load_config

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("sec_fund")

UA = "stockbot2000 research davidromines@gmail.com"
BASE = "https://www.sec.gov/files/dera/data/financial-statement-data-sets"
CACHE = Path("data/sec_fundamentals")

# Only annual and quarterly reports of US registrants. 20-F and 6-K are foreign
# private issuers on a different reporting basis; 11-K are employee benefit plans.
FORMS = {"10-K", "10-Q", "10-K/A", "10-Q/A"}

# Every tag here is needed by a ratio, and several ratios need a fallback chain
# because XBRL lets companies choose among synonyms — revenue alone is reported
# under at least four different tags depending on company and era.
WANTED = {
    # balance sheet
    "Assets", "AssetsCurrent", "Liabilities", "LiabilitiesCurrent",
    "StockholdersEquity", "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest",
    "LongTermDebtNoncurrent", "LongTermDebt", "CashAndCashEquivalentsAtCarryingValue",
    "RetainedEarningsAccumulatedDeficit", "InventoryNet",
    # income statement
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "RevenueFromContractWithCustomerIncludingAssessedTax", "SalesRevenueNet",
    "CostOfRevenue", "CostOfGoodsAndServicesSold", "CostOfGoodsSold",
    "GrossProfit", "OperatingIncomeLoss", "NetIncomeLoss",
    "IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
    "InterestExpense", "IncomeTaxExpenseBenefit", "EarningsPerShareBasic",
    # cash flow — Piotroski and Sloan both need operating cash flow
    "NetCashProvidedByUsedInOperatingActivities",
    "NetCashProvidedByUsedInOperatingActivitiesContinuingOperations",
    # EBITDA is NOT a GAAP measure and is never tagged; it is constructed from
    # operating income plus these.
    "DepreciationDepletionAndAmortization", "DepreciationAmortizationAndAccretionNet",
    "Depreciation", "DepreciationAndAmortization",
    # shares — for market cap and book-to-market. Point-in-time from the filing,
    # which is the whole reason not to take a current share count from a quote API.
    "CommonStockSharesOutstanding", "CommonStockSharesIssued",
    "WeightedAverageNumberOfSharesOutstandingBasic",
    "WeightedAverageNumberOfDilutedSharesOutstanding",
    # --- added 2026-09-22 for the statement engine (Phase 9 section 26) ---
    # Capex, to compute free cash flow honestly. Without it FCF has to be
    # approximated by operating cash flow, which overstates it for every
    # capital-intensive business — exactly the ones where it matters.
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    # Tangible book value: book value is misleading for acquisitive companies
    # whose equity is mostly purchase-price goodwill.
    "Goodwill", "IntangibleAssetsNetExcludingGoodwill",
    "FiniteLivedIntangibleAssetsNet",
    # Operating leverage and the R&D/SG&A split. A software company and a
    # manufacturer with identical operating margins are different businesses,
    # and this is where the difference shows.
    "ResearchAndDevelopmentExpense",
    "SellingGeneralAndAdministrativeExpense",
    "GeneralAndAdministrativeExpense", "SellingAndMarketingExpense",
    # Short-term borrowings, so net debt is not understated by the portion of
    # debt that is actually due first.
    "ShortTermBorrowings", "LongTermDebtCurrent",
    "DebtCurrent", "OtherShortTermBorrowings",
    # Diluted EPS. Basic EPS flatters any company that has issued options.
    "EarningsPerShareDiluted",
    # Shareholder yield needs both legs; buybacks without dividends is half
    # the picture and vice versa.
    "PaymentsOfDividendsCommonStock", "PaymentsOfDividends",
    "PaymentsForRepurchaseOfCommonStock",
}


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_filings (
            adsh     TEXT PRIMARY KEY,
            cik      INTEGER NOT NULL,
            name     TEXT,
            sic      TEXT,
            form     TEXT NOT NULL,
            period   TEXT,
            fy       TEXT, fp TEXT,
            filed    TEXT NOT NULL,
            ticker   TEXT,
            -- Provenance required by Phase 9 section 24. `accepted` is the
            -- acceptance timestamp to the minute; `filed` alone cannot say
            -- whether a filing was tradeable on its own date, because the SEC
            -- stamps that date on a 17:30 cutoff rather than the 16:00 close.
            accepted TEXT,
            prevrpt  INTEGER,   -- 1 when later superseded by an amendment
            detail   INTEGER,
            -- The issuer ticker before repair, when the CIK map had selected a
            -- preferred or warrant series. See fix_ticker_map.py.
            ticker_raw TEXT,
            -- First session this filing could be acted on. Resolved against the
            -- real market calendar by pit_facts.annotate().
            first_tradeable TEXT
        ) STRICT
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sec_facts (
            adsh   TEXT NOT NULL,
            tag    TEXT NOT NULL,
            ddate  TEXT NOT NULL,
            qtrs   INTEGER NOT NULL,
            value  REAL NOT NULL,
            PRIMARY KEY (adsh, tag, ddate, qtrs)
        ) STRICT, WITHOUT ROWID
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS idx_filings_cik ON sec_filings(cik)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_filings_filed ON sec_filings(filed)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_filings_ticker ON sec_filings(ticker)")
    conn.commit()


def quarters(start_year: int = 2009, end_year: int | None = None):
    end_year = end_year or time.gmtime().tm_year
    for y in range(start_year, end_year + 1):
        for q in (1, 2, 3, 4):
            yield y, q


def fetch(start_year: int = 2009, rate: float = 0.8) -> int:
    """Download the quarterly archives. Resumable — cached files are kept."""
    CACHE.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": UA})
    got = have = missing = 0
    for y, q in quarters(start_year):
        dest = CACHE / f"{y}q{q}.zip"
        if dest.exists() and dest.stat().st_size > 100000:
            have += 1
            continue
        url = f"{BASE}/{y}q{q}.zip"
        r = None
        for attempt in range(4):
            try:
                r = s.get(url, timeout=180)
                break
            except requests.RequestException as e:
                wait = rate * (4 ** attempt)
                log.warning(f"{y}Q{q}: {type(e).__name__}; retry in {wait:.0f}s")
                time.sleep(wait)
        if r is None:
            log.error(f"{y}Q{q}: giving up"); continue
        if r.status_code == 404:
            missing += 1; continue          # quarter not published yet
        if r.status_code != 200:
            log.warning(f"{y}Q{q}: HTTP {r.status_code}"); continue
        dest.write_bytes(r.content)
        got += 1
        log.info(f"  {y}Q{q}: {len(r.content)/1e6:.1f} MB  ({got} downloaded)")
        time.sleep(rate)
    log.info(f"Fetched {got}, already had {have}, {missing} not published")
    return got


def _ticker_map(conn) -> dict:
    """
    CIK -> ticker, from the SEC's own mapping plus our EDGAR registry.

    Only resolves companies that still exist, which is the smaller half of the
    problem: a company that died in 2012 filed 10-Qs we can read and has no
    current ticker to attach them to. Those filings are still stored — the CIK is
    the durable key — they simply cannot be joined to a price series. That
    asymmetry is the survivorship gap showing up again, from the other side.
    """
    m = {}
    try:
        r = requests.get("https://www.sec.gov/files/company_tickers.json",
                         headers={"User-Agent": UA}, timeout=60)
        r.raise_for_status()
        for v in r.json().values():
            m[int(v["cik_str"])] = v["ticker"].upper()
    except Exception as e:
        log.warning(f"SEC ticker map unavailable ({e}); falling back to edgar_companies")
    try:
        for cik, t in conn.execute(
                "SELECT cik, ticker FROM edgar_companies WHERE ticker IS NOT NULL"):
            m.setdefault(int(cik), str(t).upper())
    except Exception:
        pass
    return m


def load(conn, limit: int | None = None) -> None:
    """
    Parse cached quarters into `sec_filings` and `sec_facts`.

    Two filters do the heavy lifting on volume. Only US annual and quarterly
    reports are kept, and within them only the whitelisted tags — which takes a
    quarter from 3.6 million facts to roughly a hundred thousand.

    Consolidated figures only: rows carrying a `segments` or `coreg` value are
    per-segment or per-subsidiary breakdowns, and mixing those into a
    company-level ratio produces silent nonsense rather than an error.
    """
    init(conn)
    tmap = _ticker_map(conn)
    log.info(f"CIK->ticker map: {len(tmap):,} entries")

    files = sorted(CACHE.glob("*.zip"))
    if limit:
        files = files[:limit]
    done = conn.execute("SELECT COUNT(*) FROM sec_facts").fetchone()[0]
    log.info(f"Parsing {len(files)} quarters (facts already stored: {done:,})")

    t0 = time.time()
    for n, path in enumerate(files, 1):
        try:
            with zipfile.ZipFile(path) as z:
                subs, keep = {}, []
                with z.open("sub.txt") as f:
                    for row in csv.DictReader(io.TextIOWrapper(f, "latin-1"), delimiter="\t"):
                        if row.get("form") not in FORMS:
                            continue
                        cik = int(row["cik"]) if row.get("cik", "").isdigit() else None
                        # `accepted` and `prevrpt` are stored at load time
                        # rather than backfilled later. The first version kept
                        # only `filed`, and a filed DATE cannot distinguish a
                        # filing accepted at 09:00 (tradeable that session) from
                        # one accepted at 16:30 (not tradeable until the next) —
                        # the SEC stamps both with the same date, because its
                        # cutoff is 17:30 rather than the market close.
                        # `prevrpt` is the amendment status: a 10-K later amended
                        # is still form "10-K", so the form string cannot tell
                        # you a filing was superseded.
                        subs[row["adsh"]] = (
                            row["adsh"], cik, row.get("name"), row.get("sic"),
                            row.get("form"), row.get("period"), row.get("fy"),
                            row.get("fp"), row.get("filed"),
                            tmap.get(cik) if cik else None,
                            row.get("accepted") or None,
                            int(row["prevrpt"]) if row.get("prevrpt", "").isdigit() else None,
                            int(row["detail"]) if row.get("detail", "").isdigit() else None)
                if subs:
                    # UPSERT, not INSERT OR REPLACE. REPLACE deletes the whole
                    # row and reinserts it, which silently wiped `ticker_raw`
                    # and `first_tradeable` and reverted every repaired issuer
                    # ticker the moment the zips were re-parsed on 2026-09-22 —
                    # JPMorgan went straight back to JPM-PM.
                    #
                    # `ticker` is only overwritten when no repair is recorded,
                    # so a corrected mapping survives a reload. The two derived
                    # columns are never touched here: they are owned by
                    # fix_ticker_map.py and pit_facts.py respectively.
                    conn.executemany(
                        "INSERT INTO sec_filings "
                        "(adsh,cik,name,sic,form,period,fy,fp,filed,ticker,"
                        "accepted,prevrpt,detail) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?) "
                        "ON CONFLICT(adsh) DO UPDATE SET "
                        "cik=excluded.cik, name=excluded.name, sic=excluded.sic, "
                        "form=excluded.form, period=excluded.period, "
                        "fy=excluded.fy, fp=excluded.fp, filed=excluded.filed, "
                        "accepted=excluded.accepted, prevrpt=excluded.prevrpt, "
                        "detail=excluded.detail, "
                        "ticker=CASE WHEN sec_filings.ticker_raw IS NULL "
                        "            THEN excluded.ticker ELSE sec_filings.ticker END",
                        list(subs.values()))

                with z.open("num.txt") as f:
                    for row in csv.DictReader(io.TextIOWrapper(f, "latin-1"), delimiter="\t"):
                        if row["adsh"] not in subs or row["tag"] not in WANTED:
                            continue
                        if row.get("segments") or row.get("coreg"):
                            continue          # consolidated only
                        v = row.get("value")
                        if not v:
                            continue
                        try:
                            val = float(v)
                        except ValueError:
                            continue
                        keep.append((row["adsh"], row["tag"], row["ddate"],
                                     int(row["qtrs"] or 0), val))
                        if len(keep) >= 50000:
                            conn.executemany(
                                "INSERT OR REPLACE INTO sec_facts "
                                "(adsh,tag,ddate,qtrs,value) VALUES (?,?,?,?,?)", keep)
                            keep = []
                if keep:
                    conn.executemany(
                        "INSERT OR REPLACE INTO sec_facts "
                        "(adsh,tag,ddate,qtrs,value) VALUES (?,?,?,?,?)", keep)
            conn.commit()
            if n % 5 == 0 or n == len(files):
                nf = conn.execute("SELECT COUNT(*) FROM sec_facts").fetchone()[0]
                log.info(f"  {n}/{len(files)} quarters | {nf:,} facts | "
                         f"{time.time()-t0:.0f}s", )
        except Exception as e:
            log.error(f"{path.name}: {type(e).__name__}: {e}")
    log.info("Load complete")


def status(conn) -> None:
    init(conn)
    nf = conn.execute("SELECT COUNT(*) FROM sec_filings").fetchone()[0]
    if not nf:
        raise SystemExit("Nothing loaded — run --fetch then --load.")
    facts = conn.execute("SELECT COUNT(*) FROM sec_facts").fetchone()[0]
    tick = conn.execute("SELECT COUNT(*) FROM sec_filings WHERE ticker IS NOT NULL").fetchone()[0]
    rng = conn.execute("SELECT MIN(filed), MAX(filed) FROM sec_filings").fetchone()
    print(f"\n  SEC FUNDAMENTALS")
    print(f"  {'filings':<26}{nf:>12,}   {rng[0]} .. {rng[1]}")
    print(f"  {'with a current ticker':<26}{tick:>12,}   {tick/nf:>6.0%}")
    print(f"  {'numeric facts':<26}{facts:>12,}")
    print(f"\n  {'tag':<58}{'facts':>10}")
    print("  " + "-" * 70)
    for r in conn.execute("""SELECT tag, COUNT(*) c FROM sec_facts
                             GROUP BY tag ORDER BY c DESC LIMIT 14"""):
        print(f"  {r[0][:56]:<58}{r[1]:>10,}")
    print("\n  Filings with no ticker are mostly companies that no longer exist.")
    print("  Their fundamentals are stored and keyed by CIK; they simply cannot be")
    print("  joined to a price series we do not have. The survivorship gap again.")


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--load", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--status", action="store_true")
    a = ap.parse_args()
    cfg = load_config()
    runtime.be_nice()
    conn = storage.connect(cfg["database"]["market_data_path"])
    storage.init_db(conn); init(conn)
    if a.fetch:
        fetch()
    if a.load:
        load(conn, a.limit)
    if a.status or not (a.fetch or a.load):
        status(conn)
    conn.close()


if __name__ == "__main__":
    main()
