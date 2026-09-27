"""SEC Form 4 insider transactions (quarterly data sets, 2006 onward).

Point-in-time rule: the data sets carry a filing DATE but no acceptance time,
so a filing is first usable on the first trading session strictly AFTER its
FILING_DATE.  Anything else would let a panel see a filing on the day it was
filed, which is not knowable from a date alone.
"""
import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import io
import logging
import sqlite3
import sys
import time
import zipfile
from datetime import date, datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

log = logging.getLogger("insider")

URL = ("https://www.sec.gov/files/structureddata/data/"
       "insider-transactions-data-sets/{quarter}_form345.zip")
URL2 = ("https://www.sec.gov/files/datastandardsinnovation/data/"
        "insider-transactions-data-sets/{quarter}_form345.zip")
UA = "stockbot2000 research davidromines@gmail.com"
DATA_DIR = Path("data/insider")
WINDOW_DAYS = 90
ROUTINE_YEARS = 3

TRADE_COLS = ["accession", "trans_sk", "owner_cik", "ticker", "issuer_cik",
              "trans_date", "filing_date", "code", "shares", "price",
              "value_usd", "relationship"]

DDL = """
CREATE TABLE IF NOT EXISTS insider_trades(
    accession TEXT, trans_sk TEXT, owner_cik TEXT, ticker TEXT,
    issuer_cik TEXT, trans_date TEXT, filing_date TEXT, code TEXT,
    shares REAL, price REAL, value_usd REAL, relationship TEXT,
    PRIMARY KEY(accession, trans_sk, owner_cik));
CREATE TABLE IF NOT EXISTS insider_fetch_log(
    quarter TEXT PRIMARY KEY, status INTEGER, rows INTEGER, fetched_at TEXT);
"""


def init(conn):
    conn.executescript(DDL)
    conn.commit()


def quarters(start="2006q1", end=None):
    def parse(q):
        y, n = q.lower().split("q")
        return int(y), int(n)

    y0, n0 = parse(start)
    if end is None:
        today = datetime.utcnow().date()
        y1, n1 = today.year, (today.month - 1) // 3 + 1
    else:
        y1, n1 = parse(end)
    out = []
    y, n = y0, n0
    while (y, n) <= (y1, n1):
        out.append(f"{y}q{n}")
        n += 1
        if n == 5:
            y, n = y + 1, 1
    return out


def fetch(quarter, session=None, force=False):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    dest = DATA_DIR / f"{quarter}_form345.zip"
    if dest.exists() and not force:
        return dest
    s = session or requests.Session()
    # The SEC moved newer quarters to a second path (2026q2 is under
    # datastandardsinnovation); try both before calling a quarter unpublished.
    for url in (URL.format(quarter=quarter), URL2.format(quarter=quarter)):
        try:
            r = s.get(url, headers={"User-Agent": UA}, timeout=120)
        finally:
            # SEC asks for <10 req/s; a fixed pause is simpler than a token bucket.
            time.sleep(0.2)
        if r.status_code != 404:
            break
    if r.status_code == 404:
        log.info("%s not published (404)", quarter)
        return None
    r.raise_for_status()
    dest.write_bytes(r.content)
    return dest


def _read_tsv(zf, name):
    with zf.open(name) as fh:
        raw = fh.read()
    return pd.read_csv(io.BytesIO(raw), sep="\t", dtype=str, quoting=3,
                       on_bad_lines="skip")


def _iso(series):
    return pd.to_datetime(series, format="%d-%b-%Y", errors="coerce")


def parse_zip(path):
    with zipfile.ZipFile(path) as zf:
        sub = _read_tsv(zf, "SUBMISSION.tsv")
        tr = _read_tsv(zf, "NONDERIV_TRANS.tsv")
        own = _read_tsv(zf, "REPORTINGOWNER.tsv")

    sub = sub[sub["DOCUMENT_TYPE"].isin(["4", "4/A"])]
    tr = tr[tr["TRANS_CODE"].isin(["P", "S"])]
    df = tr.merge(sub, on="ACCESSION_NUMBER", how="inner")
    df = df.merge(own, on="ACCESSION_NUMBER", how="inner")

    df["ticker"] = df["ISSUERTRADINGSYMBOL"].fillna("").str.strip().str.upper()
    df = df[df["ticker"] != ""]

    for src, dst in (("TRANS_DATE", "trans_date"), ("FILING_DATE", "filing_date")):
        df[dst] = _iso(df[src])
    df = df[df["trans_date"].notna() & df["filing_date"].notna()]

    shares = pd.to_numeric(df["TRANS_SHARES"], errors="coerce")
    price = pd.to_numeric(df["TRANS_PRICEPERSHARE"], errors="coerce")
    out = pd.DataFrame({
        "accession": df["ACCESSION_NUMBER"],
        "trans_sk": df["NONDERIV_TRANS_SK"].astype(str),
        "owner_cik": df["RPTOWNERCIK"].astype(str),
        "ticker": df["ticker"],
        "issuer_cik": df["ISSUERCIK"].astype(str),
        "trans_date": df["trans_date"].dt.strftime("%Y-%m-%d"),
        "filing_date": df["filing_date"].dt.strftime("%Y-%m-%d"),
        "code": df["TRANS_CODE"],
        "shares": shares,
        "price": price,
        "value_usd": shares * price,
        "relationship": df["RPTOWNER_RELATIONSHIP"].fillna(""),
    })
    return out[TRADE_COLS].reset_index(drop=True)


def import_quarter(conn, quarter, force=False):
    path = fetch(quarter, force=force)
    if path is None:
        conn.execute("INSERT OR REPLACE INTO insider_fetch_log VALUES (?,?,?,?)",
                     (quarter, 404, 0, datetime.utcnow().isoformat(timespec="seconds")))
        conn.commit()
        return 0
    df = parse_zip(path)
    rows = [tuple(None if (isinstance(v, float) and np.isnan(v)) else v
                  for v in rec)
            for rec in df.itertuples(index=False, name=None)]
    conn.executemany(
        "INSERT OR REPLACE INTO insider_trades VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
        rows)
    conn.execute("INSERT OR REPLACE INTO insider_fetch_log VALUES (?,?,?,?)",
                 (quarter, 200, len(rows),
                  datetime.utcnow().isoformat(timespec="seconds")))
    conn.commit()
    return len(rows)


def run(conn, start="2006q1", refresh_last=2):
    init(conn)
    done = {r[0] for r in conn.execute(
        "SELECT quarter FROM insider_fetch_log WHERE status=200")}
    qs = quarters(start)
    # The newest quarters' files keep growing until the SEC closes them, so they are
    # re-downloaded, not read from the cached zip.
    fresh = set(qs[-refresh_last:]) if refresh_last else set()
    todo = [q for q in qs if q not in done or q in fresh]
    total = 0
    for q in todo:
        total += import_quarter(conn, q, force=q in fresh)
    return total


def purchases(conn, tickers=None):
    sql = ("SELECT accession, trans_sk, ticker, owner_cik, trans_date, filing_date, value_usd, relationship "
           "FROM insider_trades WHERE code='P' AND value_usd > 0")
    params = []
    if tickers is not None:
        tickers = list(tickers)
        if not tickers:
            return pd.DataFrame(columns=["accession", "trans_sk", "ticker", "owner_cik", "trans_date",
                                         "filing_date", "value_usd", "relationship", "routine", "value_once"])
        sql += " AND ticker IN (%s)" % ",".join("?" * len(tickers))
        params = tickers
    df = pd.read_sql_query(sql, conn, params=params)
    if df.empty:
        df["routine"] = pd.Series(dtype=bool)
        return df

    rel = df["relationship"].fillna("").str.lower()
    df = df[rel.str.contains("director") | rel.str.contains("officer")].copy()
    if df.empty:
        df["routine"] = pd.Series(dtype=bool)
        return df

    # Routine = the same owner traded this ticker in the same calendar month in
    # EACH of the ROUTINE_YEARS prior calendar years (P or S, any value).
    hist = pd.read_sql_query(
        "SELECT ticker, owner_cik, trans_date FROM insider_trades "
        "WHERE code IN ('P','S')", conn)
    hist["ym"] = hist["trans_date"].str.slice(0, 7)
    hist["y"] = hist["trans_date"].str.slice(0, 4).astype(int)
    hist["m"] = hist["trans_date"].str.slice(5, 7)
    hist = hist.drop_duplicates(["ticker", "owner_cik", "y", "m"])
    keys = set(zip(hist["ticker"], hist["owner_cik"], hist["y"], hist["m"]))

    df["y"] = df["trans_date"].str.slice(0, 4).astype(int)
    df["m"] = df["trans_date"].str.slice(5, 7)
    df["routine"] = [
        all((t, o, y - k, m) in keys for k in range(1, ROUTINE_YEARS + 1))
        for t, o, y, m in zip(df["ticker"], df["owner_cik"], df["y"], df["m"])
    ]
    # A joint filing lists the same transaction once per reporting owner; its dollars
    # count once (value_once), its owners each count as a buyer.
    df["value_once"] = np.where(df.duplicated(["accession", "trans_sk"]), 0.0, df["value_usd"].astype(float))
    return df.drop(columns=["y", "m"]).reset_index(drop=True)


def first_tradeable(filing_dates, sessions):
    """First session strictly after each filing date (None if none)."""
    sess = sorted(sessions)
    arr = np.array(sess, dtype="datetime64[D]")
    out = []
    for fd in filing_dates:
        if fd is None:
            out.append(None)
            continue
        d = np.datetime64(str(fd)[:10], "D")
        i = int(np.searchsorted(arr, d, side="right"))
        out.append(sess[i] if i < len(arr) else None)
    return out


def _sessions(conn):
    try:
        rows = conn.execute(
            "SELECT DISTINCT date FROM prices WHERE ticker='SPY'").fetchall()
    except sqlite3.OperationalError:
        return []
    return sorted(r[0] for r in rows if r[0])


def attach(conn, df):
    for c in ("insider_buy_usd_90", "insider_buyers_90", "opp_buyers_90"):
        df[c] = np.float32(np.nan)
    if df.empty:
        return df

    try:
        conn.execute("SELECT 1 FROM insider_trades LIMIT 1")
    except sqlite3.OperationalError:
        return df

    sessions = _sessions(conn)
    if not sessions:
        return df
    sess_arr = np.array(sessions, dtype="datetime64[D]")

    seen = {r[0] for r in conn.execute("SELECT DISTINCT ticker FROM insider_trades")}
    try:
        buys = purchases(conn)
    except Exception:  # pragma: no cover - defensive, table shape changed
        return df

    t = df["_t"].astype(str).values
    d = pd.to_datetime(df["_d"].astype(str).str[:10]).values.astype("datetime64[D]")
    groups = pd.Series(np.arange(len(t))).groupby(t).indices
    by_ticker = {}

    if not buys.empty:
        buys = buys.copy()
        buys["tradeable"] = first_tradeable(buys["filing_date"].tolist(), sessions)
        buys = buys[buys["tradeable"].notna()]
        buys["ts"] = np.array([np.datetime64(x, "D") for x in buys["tradeable"]])
        buys["opp"] = ~buys["routine"].astype(bool)
        by_ticker = dict(tuple(buys.groupby("ticker")))

    for tk, idx in groups.items():
        if tk not in seen:
            continue  # never filed a Form 4: unknown, not zero
        if buys.empty:
            df.iloc[idx, df.columns.get_loc("insider_buy_usd_90")] = np.float32(0.0)
            df.iloc[idx, df.columns.get_loc("insider_buyers_90")] = np.float32(0.0)
            df.iloc[idx, df.columns.get_loc("opp_buyers_90")] = np.float32(0.0)
            continue
        b = by_ticker.get(tk)
        if b is None or b.empty:
            df.iloc[idx, df.columns.get_loc("insider_buy_usd_90")] = np.float32(0.0)
            df.iloc[idx, df.columns.get_loc("insider_buyers_90")] = np.float32(0.0)
            df.iloc[idx, df.columns.get_loc("opp_buyers_90")] = np.float32(0.0)
            continue
        bts = b["ts"].values
        bval = b["value_once"].astype(float).values
        bown = b["owner_cik"].values
        bopp = b["opp"].values
        order = np.argsort(bts, kind="stable")
        bts, bval, bown, bopp = bts[order], bval[order], bown[order], bopp[order]

        dd = d[idx]
        lo = np.searchsorted(bts, dd - np.timedelta64(WINDOW_DAYS, "D"), side="right")
        hi = np.searchsorted(bts, dd, side="right")
        usd = np.zeros(len(idx), dtype=np.float64)
        nbuy = np.zeros(len(idx), dtype=np.float64)
        nopp = np.zeros(len(idx), dtype=np.float64)
        for j in range(len(idx)):
            a, z = lo[j], hi[j]
            if z <= a:
                continue
            usd[j] = np.nansum(bval[a:z])
            nbuy[j] = len(set(bown[a:z]))
            nopp[j] = len(set(bown[a:z][bopp[a:z]]))
        df.iloc[idx, df.columns.get_loc("insider_buy_usd_90")] = usd.astype(np.float32)
        df.iloc[idx, df.columns.get_loc("insider_buyers_90")] = nbuy.astype(np.float32)
        df.iloc[idx, df.columns.get_loc("opp_buyers_90")] = nopp.astype(np.float32)
    return df


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="SEC Form 4 insider transactions")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--status", action="store_true")
    ap.add_argument("--start", default="2006q1")
    args = ap.parse_args(argv)

    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    try:
        if args.status:
            init(conn)
            n = conn.execute("SELECT COUNT(*) FROM insider_fetch_log").fetchone()[0]
            rows = conn.execute("SELECT COUNT(*) FROM insider_trades").fetchone()[0]
            buys = conn.execute(
                "SELECT COUNT(*) FROM insider_trades WHERE code='P'").fetchone()[0]
            newest = conn.execute(
                "SELECT MAX(filing_date) FROM insider_trades").fetchone()[0]
            print(f"quarters logged: {n}\nrows: {rows}\n"
                  f"purchase rows: {buys}\nnewest filing_date: {newest}")
        elif args.daily:
            # Only the newest two quarters can still be growing; re-fetching
            # the whole history every day would be 80 requests for nothing.
            print(run(conn, start=args.start, refresh_last=2))
        elif args.fetch:
            print(run(conn, start=args.start))
        else:
            ap.print_help()
    finally:
        conn.close()


if __name__ == "__main__":
    sys.exit(main())
