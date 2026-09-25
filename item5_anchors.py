"""
Real quarterly price anchors for dead companies, from their 10-Ks (Stage M2b).

For each company (by CIK): list its 10-K filings from the SEC submissions file,
fetch each primary document once, keep only the Item 5 window (item5.locate)
on disk, parse it (item5.parse) and store one row per fiscal quarter in
`item5_anchors`, with the accession it came from. Resumable: a filing whose
window file exists is not fetched again, and rows are INSERT OR IGNORE.

`--validate N` measures the parser OUT OF SAMPLE on companies whose daily prices
this database holds: the quarter's high/low ratio from the filing against the
ratio from our own bars. A ratio is immune to the split/dividend adjustment
factor that separates filed prices from yfinance's adjusted ones, so a mismatch
means the parser read the wrong numbers.

SEC fair-access rules: a declared User-Agent (edgar_registry.UA) and under ten
requests a second.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import html
import json
import logging
import random
import re
import sqlite3
import sys
import time
from pathlib import Path

import item5

log = logging.getLogger("item5_anchors")
SUBS = Path("data/edgar/submissions")
WIN = Path("data/edgar/item5")
FORMS = ("10-K", "10-K405", "10-KSB", "10-KT")
RATE = 0.15


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS item5_anchors (
            cik          INTEGER NOT NULL,
            accession    TEXT NOT NULL,
            filed        TEXT NOT NULL,
            form         TEXT,
            fye_month    INTEGER NOT NULL,
            fiscal_year  INTEGER NOT NULL,
            quarter      INTEGER NOT NULL,
            period_end   TEXT NOT NULL,
            high         REAL NOT NULL,
            low          REAL NOT NULL,
            PRIMARY KEY (cik, fiscal_year, quarter, accession)
        )""")
    conn.commit()


def fye_month_of(sub: dict) -> int:
    """Fiscal year-end month from the submissions file ('MMDD'). A 52/53-week year
    ending in the first week of a month (e.g. '0103') really ends the month before."""
    fye = str(sub.get("fiscalYearEnd") or "1231")
    if not (len(fye) == 4 and fye.isdigit() and 1 <= int(fye[:2]) <= 12):
        return 12
    m, d = int(fye[:2]), int(fye[2:])
    return (m - 2) % 12 + 1 if d <= 7 else m


def _session():
    import requests
    import edgar_registry as er
    s = requests.Session()
    s.headers.update({"User-Agent": er.UA, "Accept-Encoding": "gzip, deflate"})
    return s


def submissions(cik: int, s=None) -> dict:
    p = SUBS / f"CIK{int(cik):010d}.json"
    if not p.exists() and s is not None:
        r = s.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", timeout=45)
        time.sleep(RATE)
        if r.status_code != 200:
            return {}
        SUBS.mkdir(parents=True, exist_ok=True)
        p.write_bytes(r.content)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except ValueError:
        return {}


def tenks(sub: dict, last: int = 3, before: str | None = None) -> list:
    """The company's newest `last` annual reports (filed before `before`): [(form, filed, accession, doc)]."""
    r = (sub.get("filings") or {}).get("recent") or {}
    rows = [(f, d, a, p) for f, d, a, p in zip(r.get("form", []), r.get("filingDate", []),
                                                r.get("accessionNumber", []), r.get("primaryDocument", []))
            if f in FORMS and p and (before is None or d < before)]
    rows.sort(key=lambda x: x[1], reverse=True)
    return rows[:last]


def _text(raw: str) -> str:
    t = html.unescape(re.sub(r"<[^>]+>", " ", raw))
    return re.sub(r"[ \t\xa0]+", " ", t)


def window(cik: int, accession: str, doc: str, s) -> str | None:
    """The filing's Item 5 window, cached on disk ('' when the filing has none)."""
    WIN.mkdir(parents=True, exist_ok=True)
    p = WIN / f"{int(cik)}_{accession}.txt"
    if p.exists():
        return p.read_text()
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/{doc}"
    try:
        r = s.get(url, timeout=90)
    except Exception as e:                                   # noqa: BLE001 — retried on the next run
        log.warning(f"{cik} {accession}: {type(e).__name__}")
        return None
    time.sleep(RATE)
    if r.status_code == 403:
        raise SystemExit("403 from the SEC — User-Agent rejected or rate exceeded; stopping")
    if r.status_code != 200:
        return None
    w = item5.locate(_text(r.text))
    p.write_text(w)
    return w


def harvest(conn, ciks: list, last: int = 3, before: str | None = None) -> dict:
    init(conn)
    s = _session()
    stats = {"companies": 0, "filings": 0, "parsed": 0, "rows": 0}
    for n, cik in enumerate(ciks):
        sub = submissions(int(cik), s)
        fye_month = fye_month_of(sub)
        stats["companies"] += 1
        for form, filed, acc, doc in tenks(sub, last, before):
            w = window(int(cik), acc, doc, s)
            if w is None:
                continue
            stats["filings"] += 1
            rows = item5.parse(w, fye_month) if w else []
            stats["parsed"] += bool(rows)
            for r in rows:
                cur = conn.execute(
                    "INSERT OR IGNORE INTO item5_anchors VALUES (?,?,?,?,?,?,?,?,?,?)",
                    (int(cik), acc, filed, form, fye_month, r["year"], r["quarter"],
                     item5.quarter_end(r["year"], r["quarter"], fye_month), r["high"], r["low"]))
                stats["rows"] += cur.rowcount
        conn.commit()
        if n % 100 == 0:
            log.info(f"{n:,}/{len(ciks):,} companies  {stats}")
    return stats


def reparse(conn) -> int:
    """Rebuild item5_anchors from the cached windows (after a parser change). No network."""
    init(conn)
    conn.execute("DELETE FROM item5_anchors")
    n = 0
    for w in sorted(WIN.glob("*.txt")):
        cik, acc = w.stem.split("_", 1)
        sub = submissions(int(cik))
        fye_month = fye_month_of(sub)
        r = (sub.get("filings") or {}).get("recent") or {}
        meta = {a: (f, d) for f, d, a in zip(r.get("form", []), r.get("filingDate", []), r.get("accessionNumber", []))}
        form, filed = meta.get(acc, (None, ""))
        for x in item5.parse(w.read_text(), fye_month):
            n += conn.execute("INSERT OR IGNORE INTO item5_anchors VALUES (?,?,?,?,?,?,?,?,?,?)",
                              (int(cik), acc, filed, form, fye_month, x["year"], x["quarter"],
                               item5.quarter_end(x["year"], x["quarter"], fye_month), x["high"], x["low"])).rowcount
    conn.commit()
    return n


def validate(conn, n: int = 150, seed: int = 12) -> dict:
    """Out-of-sample precision: filed high/low ratio vs our own bars' ratio, per quarter."""
    random.seed(seed)
    pairs = conn.execute("""SELECT f.cik, MIN(f.ticker) FROM sec_filings f
        JOIN symbols s ON s.ticker = f.ticker AND s.security_type = 'common_stock'
        WHERE f.ticker IS NOT NULL GROUP BY f.cik""").fetchall()
    pairs = random.sample(pairs, min(n, len(pairs)))
    # Filed before 2018: Regulation S-K dropped the quarterly price table after that.
    harvest(conn, [c for c, _ in pairs], last=1, before="2018-01-01")
    tick = dict(pairs)
    checked = agree = 0
    bad = []
    for cik, ticker in pairs:
        for pe, hi, lo in conn.execute("SELECT period_end, high, low FROM item5_anchors WHERE cik=?", (cik,)):
            end = pe
            start = f"{int(pe[:4]) - (1 if int(pe[5:7]) <= 2 else 0)}-{(int(pe[5:7]) - 3) % 12 + 1:02d}-01"
            r = conn.execute("SELECT MAX(high), MIN(low), COUNT(*) FROM prices WHERE ticker=? AND date>=? "
                             "AND date<=?", (tick[cik], start, end)).fetchone()
            if not r or not r[2] or r[2] < 40 or not r[1] or r[1] <= 0:
                continue
            checked += 1
            ours, filed = r[0] / r[1], hi / lo
            if abs(filed / ours - 1) <= 0.10:
                agree += 1
            else:
                bad.append((cik, ticker, pe, round(filed, 3), round(ours, 3)))
    return {"quarters_checked": checked, "agree_within_10pct": agree,
            "share": (agree / checked) if checked else None, "disagreements": bad[:30]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--validate", type=int, metavar="N", help="out-of-sample check on N priced companies")
    ap.add_argument("--dead", action="store_true", help="harvest the dead companies the synthetic set uses")
    ap.add_argument("--last", type=int, default=3, help="10-Ks per company (newest first)")
    ap.add_argument("--reparse", action="store_true", help="rebuild the table from cached windows")
    ap.add_argument("--synthetic", action="store_true",
                    help="harvest the companies generator v5 synthesizes (10-Ks filed before 2019)")
    ap.add_argument("--seed", type=int, default=12)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    init(conn)
    if a.reparse:
        print(f"reparsed: {reparse(conn):,} rows")
    if a.validate:
        print(json.dumps(validate(conn, a.validate, a.seed), indent=1))
    if a.synthetic:
        import pandas as pd
        v = pd.read_parquet("data/universe/synthetic_v5.parquet", columns=["company_id"]).drop_duplicates()
        ev = pd.read_parquet("data/universe/dead_evidence.parquet", columns=["company_id", "cik"])
        ciks = sorted(v.merge(ev, on="company_id").cik.dropna().astype(int).unique().tolist())
        print(harvest(conn, ciks, a.last, before="2019-01-01"))
    if a.dead:
        import pandas as pd
        ev = pd.read_parquet("data/universe/dead_evidence.parquet")
        ciks = sorted(ev["cik"].dropna().astype(int).unique().tolist())
        print(harvest(conn, ciks, a.last))
    return 0


if __name__ == "__main__":
    sys.exit(main())
