"""Stage O-pol: US House STOCK Act periodic transaction reports.

Point-in-time discipline: a trade is only knowable from the first trading
session strictly after the report's filing date, so every panel column is
keyed on that session, never on the transaction date or the filing day.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import io
import re
import sqlite3
import sys
import time
import xml.etree.ElementTree as ET
from datetime import date, datetime, timedelta

import numpy as np
import pandas as pd
import requests

USER_AGENT = "stockbot2000 research davidromines@gmail.com"
SLEEP_SECONDS = 0.2
INDEX_URL = "https://disclosures-clerk.house.gov/public_disc/financial-pdfs/{year}FD.zip"
PDF_URL = "https://disclosures-clerk.house.gov/public_disc/ptr-pdfs/{year}/{doc_id}.pdf"

# Owner codes are optional; asset type is bracketed; amounts are a range or "Over $x".
TRADE_RE = re.compile(
    r"(?:(?P<owner>SP|JT|DC)\s+)?"
    r"(?P<asset>.+?)\s*"
    r"\((?P<ticker>[A-Za-z0-9.\-]+)\)\s*"
    r"\[(?P<asset_type>[A-Z]{2})\]\s*"
    r"(?P<txn_type>S\s*\(partial\)|P|S|E)\s+"
    r"(?P<txn_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<notif_date>\d{1,2}/\d{1,2}/\d{4})\s+"
    r"(?P<amount>\$[\d,]+(?:\s*-\s*\$[\d,]+)?|Over\s*\$[\d,]+)"
)

DDL = """
CREATE TABLE IF NOT EXISTS congress_trades(
    doc_id TEXT, seq INTEGER, member TEXT, state_dst TEXT, owner TEXT,
    ticker TEXT, asset_type TEXT, txn_type TEXT, txn_date TEXT,
    notif_date TEXT, filed_date TEXT, amount_lo REAL, amount_hi REAL,
    PRIMARY KEY(doc_id, seq));
CREATE TABLE IF NOT EXISTS congress_docs(
    doc_id TEXT PRIMARY KEY, year INTEGER, member TEXT, state_dst TEXT,
    filed_date TEXT, status TEXT, trades INTEGER, fetched_at TEXT);
"""


def init(conn):
    conn.executescript(DDL)
    conn.commit()


def _iso(mdY):
    return datetime.strptime(mdY.strip(), "%m/%d/%Y").date().isoformat()


def _amounts(raw):
    raw = raw.strip()
    if raw.lower().startswith("over"):
        return float(raw.split("$", 1)[1].replace(",", "")), None
    lo, _, hi = raw.partition("-")
    return (float(lo.replace("$", "").replace(",", "").strip()),
            float(hi.replace("$", "").replace(",", "").strip()))


def parse_index(xml_text):
    """P (periodic transaction report) filings only; others are not trades."""
    root = ET.fromstring(xml_text)
    out = []
    for m in root.iter("Member"):
        if (m.findtext("FilingType") or "").strip() != "P":
            continue
        first = (m.findtext("First") or "").strip()
        last = (m.findtext("Last") or "").strip()
        out.append({
            "doc_id": (m.findtext("DocID") or "").strip(),
            "year": int((m.findtext("Year") or "0").strip() or 0),
            "member": (first + " " + last).strip(),
            "state_dst": (m.findtext("StateDst") or "").strip(),
            "filed_date": _iso(m.findtext("FilingDate") or ""),
        })
    return out


def parse_trades(text):
    flat = re.sub(r"\s+", " ", text or "")
    out = []
    for seq, m in enumerate(TRADE_RE.finditer(flat)):
        txn = re.sub(r"\s+", " ", m.group("txn_type")).strip()
        if txn.upper().startswith("S") and "partial" in txn.lower():
            txn = "S (partial)"
        lo, hi = _amounts(m.group("amount"))
        out.append({
            "seq": seq,
            "owner": m.group("owner") or "",
            "ticker": m.group("ticker").upper(),
            "asset_type": m.group("asset_type"),
            "txn_type": txn,
            "txn_date": _iso(m.group("txn_date")),
            "notif_date": _iso(m.group("notif_date")),
            "amount_lo": lo,
            "amount_hi": hi,
        })
    return out


def pdf_text(content):
    from pypdf import PdfReader
    return "".join(page.extract_text() or "" for page in PdfReader(io.BytesIO(content)).pages)


def _default_get(url):
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=60)
    time.sleep(SLEEP_SECONDS)
    return r.status_code, r.content


def _index_xml(content):
    import zipfile
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        name = next(n for n in z.namelist() if n.lower().endswith(".xml"))
        return z.read(name).decode("utf-8", "replace")


def fetch_year(conn, year, get=None):
    get = get or _default_get
    init(conn)
    stats = {"year": year, "reports": 0, "ok": 0, "skipped": 0, "errors": 0, "trades": 0}
    try:
        status, content = get(INDEX_URL.format(year=year))
        if status != 200:
            raise RuntimeError("index status %s" % status)
        filings = parse_index(_index_xml(content))
    except Exception:
        stats["errors"] += 1
        conn.commit()   # per report: never hold the write lock across downloads
        return stats

    done = {r[0] for r in conn.execute(
        "SELECT doc_id FROM congress_docs WHERE status IN ('ok','skipped')")}
    now = datetime.utcnow().isoformat(timespec="seconds")
    for f in filings:
        doc_id = f["doc_id"]
        if not doc_id or doc_id in done:
            continue
        stats["reports"] += 1
        # Electronically filed reports have 8-digit DocIDs starting with "2";
        # the rest are scanned images with no extractable text.
        if not (len(doc_id) == 8 and doc_id.startswith("2")):
            conn.execute(
                "INSERT OR REPLACE INTO congress_docs VALUES (?,?,?,?,?,?,?,?)",
                (doc_id, year, f["member"], f["state_dst"], f["filed_date"],
                 "skipped", 0, now))
            stats["skipped"] += 1
            conn.commit()   # per report: never hold the write lock across downloads
            continue
        try:
            status, content = get(PDF_URL.format(year=year, doc_id=doc_id))
            if status != 200:
                raise RuntimeError("pdf status %s" % status)
            trades = parse_trades(pdf_text(content))
        except Exception:
            conn.execute(
                "INSERT OR REPLACE INTO congress_docs VALUES (?,?,?,?,?,?,?,?)",
                (doc_id, year, f["member"], f["state_dst"], f["filed_date"],
                 "error", 0, now))
            stats["errors"] += 1
            conn.commit()   # per report: never hold the write lock across downloads
            continue
        for t in trades:
            conn.execute(
                "INSERT OR REPLACE INTO congress_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (doc_id, t["seq"], f["member"], f["state_dst"], t["owner"],
                 t["ticker"], t["asset_type"], t["txn_type"], t["txn_date"],
                 t["notif_date"], f["filed_date"], t["amount_lo"], t["amount_hi"]))
        conn.execute(
            "INSERT OR REPLACE INTO congress_docs VALUES (?,?,?,?,?,?,?,?)",
            (doc_id, year, f["member"], f["state_dst"], f["filed_date"],
             "ok", len(trades), now))
        stats["ok"] += 1
        conn.commit()   # per report: never hold the write lock across downloads
        stats["trades"] += len(trades)
    conn.commit()
    return stats


def run(conn, start=2013, end=None, get=None):
    end = end or date.today().year
    out = []
    for year in range(start, end + 1):
        out.append(fetch_year(conn, year, get=get))
    return out


def _sessions(conn):
    rows = conn.execute("SELECT DISTINCT date FROM prices WHERE ticker='SPY' ORDER BY date").fetchall()
    return np.array([r[0] for r in rows], dtype=object)


def _first_session_after(sessions, filed_date):
    """Index of the first session strictly after filed_date, or None."""
    if len(sessions) == 0:
        return None
    i = int(np.searchsorted(sessions, filed_date, side="right"))
    return i if i < len(sessions) else None


def attach(conn, df):
    cols = ["congress_buyers_90", "congress_sellers_90"]
    try:
        rows = conn.execute(
            "SELECT ticker, txn_type, asset_type, filed_date, member FROM congress_trades").fetchall()
    except sqlite3.OperationalError:
        for c in cols:
            df[c] = np.float32(np.nan)
        return df
    for c in cols:
        df[c] = np.float32(np.nan)
    if not rows:
        return df

    sessions = _sessions(conn)
    # Per ticker: the session index at which each member's trade becomes
    # knowable, split by direction. Only [ST] stock trades count.
    buys, sells = {}, {}
    for ticker, txn_type, asset_type, filed_date, member in rows:
        if asset_type != "ST":
            continue
        if txn_type == "P":
            bucket = buys
        elif txn_type in ("S", "S (partial)"):
            bucket = sells
        else:
            continue
        idx = _first_session_after(sessions, filed_date)
        if idx is None:
            continue
        bucket.setdefault(ticker, []).append((idx, member))

    tcol = "_t" if "_t" in df.columns else "ticker"
    dcol = "_d" if "_d" in df.columns else "date"
    for col, bucket in zip(cols, (buys, sells)):
        for ticker, group in df.groupby(tcol, sort=False).groups.items():
            entries = bucket.get(ticker)
            if not entries:
                continue
            arr = np.array([e[0] for e in entries])
            members = np.array([e[1] for e in entries], dtype=object)
            pos = df.index.get_indexer(group)
            dates = df[dcol].to_numpy(dtype=object)[pos]
            # Window is (date - 90 calendar days, date]; the lower bound is
            # exclusive so a trade exactly 90 days old has already dropped out.
            lo = np.array([(date.fromisoformat(d) - timedelta(days=90)).isoformat()
                           for d in dates], dtype=object)
            hi = np.array([d for d in dates], dtype=object)
            left = np.searchsorted(sessions, lo, side="right")
            right = np.searchsorted(sessions, hi, side="right")
            vals = np.zeros(len(dates), dtype=np.float32)
            for k in range(len(dates)):
                sel = (arr >= left[k]) & (arr < right[k])
                vals[k] = len(set(members[sel])) if sel.any() else 0.0
            df.iloc[pos, df.columns.get_loc(col)] = vals
    return df


def main(argv=None):
    import argparse
    from universe import load_config
    ap = argparse.ArgumentParser()
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--start", type=int, default=2013)
    args = ap.parse_args(argv)
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=60)
    try:
        init(conn)
        if args.fetch:
            for s in run(conn, start=args.start):
                print(s)
        if args.daily:
            y = date.today().year
            for s in run(conn, start=y - 1, end=y):
                print(s)
        if args.status:
            for row in conn.execute(
                    "SELECT status, COUNT(*), COALESCE(SUM(trades),0) FROM congress_docs GROUP BY status"):
                print(row)
    finally:
        conn.close()


if __name__ == "__main__":
    main()
