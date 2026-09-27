"""Daily Form 4 insider-transaction feed straight from EDGAR.

insider.py imports the SEC's quarterly data sets, which lag by up to a
quarter. This module pulls the same filings from the daily index so the
insider-buying signal is current. Both write insider_trades; when the
official quarterly set for a period is imported, reconcile() drops the
daily-feed rows for accessions the official set also covers, so the
authoritative source wins and no transaction is double counted.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import datetime as _dt
import re
import sqlite3
import time
import xml.etree.ElementTree as ET

import requests

INDEX_URL = "https://www.sec.gov/Archives/edgar/daily-index/{year}/QTR{q}/form.{ymd}.idx"
FILING_URL = "https://www.sec.gov/Archives/{path}"
REQUEST_SLEEP = 0.12  # SEC allows 10 req/s; stay under it.

# Fixed-width index columns: form, company, cik, date, file name. The company
# name may contain spaces, so split from the right.
_INDEX_RE = re.compile(
    r"^(?P<form>\S+)\s+(?P<company>.*?)\s+(?P<cik>\d+)\s+(?P<filed>\d{8})\s+(?P<path>\S+)\s*$"
)
_XML_RE = re.compile(r"<XML>(.*?)</XML>", re.IGNORECASE | re.DOTALL)


def init(conn):
    import insider
    insider.init(conn)
    conn.execute(
        """CREATE TABLE IF NOT EXISTS form4_daily_log(
               day TEXT PRIMARY KEY, filings INTEGER, rows INTEGER,
               fetched_at TEXT, note TEXT)"""
    )
    conn.commit()


def _iso(ymd):
    return "%s-%s-%s" % (ymd[0:4], ymd[4:6], ymd[6:8])


def parse_index(text):
    """Return Form 4 / 4-A entries from a daily index body."""
    out = []
    seen_dashes = False
    for line in text.splitlines():
        if not seen_dashes:
            if line.strip().startswith("---"):
                seen_dashes = True
            continue
        m = _INDEX_RE.match(line)
        if not m:
            continue
        form = m.group("form").strip()
        if form not in ("4", "4/A"):
            continue
        path = m.group("path").strip()
        out.append({
            "form": form,
            "cik": int(m.group("cik")),
            "filed": _iso(m.group("filed")),
            "path": path,
            "accession": path.rsplit("/", 1)[-1][:-4] if path.endswith(".txt") else path.rsplit("/", 1)[-1],
        })
    return out


def extract_xml(filing_text):
    if not filing_text:
        return None
    m = _XML_RE.search(filing_text)
    if not m:
        return None
    body = m.group(1).strip()
    return body or None


def _text(node, path):
    if node is None:
        return None
    found = node.find(path)
    if found is None or found.text is None:
        return None
    return found.text.strip()


def _flag(node, path):
    v = _text(node, path)
    if v is None:
        return False
    return v.lower() in ("1", "true", "yes")


def _num(node, path):
    v = _text(node, path)
    if v in (None, ""):
        return None
    try:
        return float(v)
    except ValueError:
        return None


def parse_form4(xml_text, accession, filed_iso):
    """One row per (P/S nonDerivativeTransaction) x (reporting owner)."""
    if not xml_text:
        return []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    if root.tag != "ownershipDocument":
        # Some filings wrap the document; find it if present.
        found = root.find(".//ownershipDocument")
        if found is None:
            return []
        root = found

    issuer = root.find("issuer")
    ticker = _text(issuer, "issuerTradingSymbol")
    if ticker is None:
        return []
    ticker = ticker.strip().upper()
    if not ticker:
        return []
    issuer_cik = _text(issuer, "issuerCik")

    owners = []
    for owner in root.findall("reportingOwner"):
        oid = owner.find("reportingOwnerId")
        cik = _text(oid, "rptOwnerCik")
        rel = owner.find("reportingOwnerRelationship")
        parts = []
        if _flag(rel, "isDirector"):
            parts.append("Director")
        if _flag(rel, "isOfficer"):
            parts.append("Officer")
        if _flag(rel, "isTenPercentOwner"):
            parts.append("TenPercentOwner")
        if _flag(rel, "isOther"):
            parts.append("Other")
        owners.append({"cik": cik, "relationship": ",".join(parts)})

    rows = []
    table = root.find("nonDerivativeTable")
    if table is None:
        return []
    for idx, txn in enumerate(table.findall("nonDerivativeTransaction")):
        code = _text(txn, "transactionCoding/transactionCode")
        if code not in ("P", "S"):
            continue
        shares = _num(txn, "transactionAmounts/transactionShares/value")
        # Real filings nest the price under transactionAmounts; accept either placement.
        price = _num(txn, "transactionAmounts/transactionPricePerShare/value")
        if price is None:
            price = _num(txn, "transactionPricePerShare/value")
        value = None
        if shares is not None and price is not None:
            value = shares * price
        trans_date = _text(txn, "transactionDate/value")
        trans_sk = "d%d" % idx
        for owner in owners:
            rows.append({
                "accession": accession,
                "trans_sk": trans_sk,
                "owner_cik": owner["cik"],
                "ticker": ticker,
                "issuer_cik": issuer_cik,
                "trans_date": trans_date,
                "filing_date": filed_iso,
                "code": code,
                "shares": shares,
                "price": price,
                "value_usd": value,
                "relationship": owner["relationship"],
            })
    return rows


def _default_get(url):
    resp = requests.get(url, headers={"User-Agent": _ua()}, timeout=30)
    time.sleep(REQUEST_SLEEP)
    return resp.status_code, resp.text


def _ua():
    import insider
    return insider.UA


def fetch_day(conn, day_iso, get=None):
    import insider
    if get is None:
        get = _default_get
    d = _dt.date.fromisoformat(day_iso)
    url = INDEX_URL.format(year=d.year, q=(d.month - 1) // 3 + 1, ymd=d.strftime("%Y%m%d"))
    status, text = get(url)
    now = _dt.datetime.now(_dt.timezone.utc).isoformat(timespec="seconds")
    if status == 404:
        conn.execute(
            "INSERT OR REPLACE INTO form4_daily_log(day, filings, rows, fetched_at, note)"
            " VALUES(?,?,?,?,?)", (day_iso, 0, 0, now, "no index"))
        conn.commit()
        return {"day": day_iso, "filings": 0, "rows": 0}

    # The index lists a filing once per filer (issuer and every reporting owner): fetch
    # each accession once.
    seen, entries = set(), []
    for e in parse_index(text or ""):
        if e["accession"] not in seen:
            seen.add(e["accession"])
            entries.append(e)
    filings = 0
    rows = 0
    failed = 0
    for entry in entries:
        fstatus, ftext = get(FILING_URL.format(path=entry["path"]))
        if fstatus != 200 or not ftext:
            failed += 1
            continue
        xml_text = extract_xml(ftext)
        parsed = parse_form4(xml_text, entry["accession"], entry["filed"])
        filings += 1
        for row in parsed:
            conn.execute(
                """INSERT OR IGNORE INTO insider_trades
                   (accession, trans_sk, owner_cik, ticker, issuer_cik, trans_date,
                    filing_date, code, shares, price, value_usd, relationship)
                   VALUES(:accession, :trans_sk, :owner_cik, :ticker, :issuer_cik,
                          :trans_date, :filing_date, :code, :shares, :price,
                          :value_usd, :relationship)""", row)
            rows += max(conn.execute("SELECT changes()").fetchone()[0], 0)
        # Commit per filing: an open write transaction held across a day of network
        # fetches locked out every other writer (three jobs died "database is locked").
        conn.commit()
    note = "" if not failed else "%d filing(s) failed" % failed
    conn.execute(
        "INSERT OR REPLACE INTO form4_daily_log(day, filings, rows, fetched_at, note)"
        " VALUES(?,?,?,?,?)", (day_iso, filings, rows, now, note))
    conn.commit()
    return {"day": day_iso, "filings": filings, "rows": rows}


def run(conn, days=5, today=None, get=None):
    if today is None:
        today = _dt.date.today()
    elif isinstance(today, str):
        today = _dt.date.fromisoformat(today)
    logged = {r[0] for r in conn.execute(
        "SELECT day FROM form4_daily_log WHERE filings > 0")}
    out = []
    for i in range(1, days + 1):
        day = (today - _dt.timedelta(days=i)).isoformat()
        if day in logged:
            continue
        out.append(fetch_day(conn, day, get=get))
    return out


def reconcile(conn):
    """Official quarterly rows win over daily-feed rows for the same accession."""
    cur = conn.execute(
        """DELETE FROM insider_trades
           WHERE trans_sk LIKE 'd%'
             AND accession IN (SELECT accession FROM insider_trades
                               WHERE trans_sk NOT LIKE 'd%')""")
    conn.commit()
    return cur.rowcount


def main(argv=None):
    import argparse
    import sys
    from universe import load_config
    import insider  # noqa: F401  (ensures UA is available)

    parser = argparse.ArgumentParser(description="EDGAR Form 4 daily feed")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--daily", action="store_true")
    group.add_argument("--backfill", nargs=2, metavar=("FROM", "TO"))
    group.add_argument("--status", action="store_true")
    parser.add_argument("--days", type=int, default=5)
    args = parser.parse_args(argv)

    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    try:
        init(conn)
        if args.status:
            for row in conn.execute(
                    "SELECT day, filings, rows, fetched_at, note FROM form4_daily_log"
                    " ORDER BY day DESC LIMIT 30"):
                print(row)
            return 0
        if args.daily:
            run(conn, days=args.days)
            reconcile(conn)
            return 0
        start = _dt.date.fromisoformat(args.backfill[0])
        end = _dt.date.fromisoformat(args.backfill[1])
        day = start
        while day <= end:
            fetch_day(conn, day.isoformat())
            day += _dt.timedelta(days=1)
        reconcile(conn)
        return 0
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
