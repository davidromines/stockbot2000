"""Daily EDGAR 10-Q / 10-K feed into sec_filings / sec_facts.

The SEC's quarterly Financial Statement Data Sets lag filings by up to three
months, so fundamentals and earnings surprises were arriving stale. This module
pulls the daily index and the per-company submissions / companyfacts JSON
directly, writing the same row shapes sec_fundamentals.load writes.
"""
import runtime  # noqa: F401  (thread limits must be set before other imports)

import argparse
import datetime as dt
import json
import re
import sys
import time
import urllib.error
import urllib.request
from zoneinfo import ZoneInfo

import sec_fundamentals
import storage

DAILY_INDEX = "https://www.sec.gov/Archives/edgar/daily-index/{y}/QTR{q}/form.{d}.idx"
SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik:010d}.json"
COMPANYFACTS = "https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json"

NY = ZoneInfo("America/New_York")
# EDGAR's documented ceiling is 10 req/s; 8 leaves headroom for retries.
MIN_INTERVAL = 1.0 / 8.0

_last_request = [0.0]


def _throttle():
    now = time.monotonic()
    wait = MIN_INTERVAL - (now - _last_request[0])
    if wait > 0:
        time.sleep(wait)
    _last_request[0] = time.monotonic()


def _http(url, as_json):
    """GET with throttle, 3 retries and 404 -> None.

    A 404 is a normal answer here (weekends and holidays have no daily index),
    so it must not be retried or raised.
    """
    last = None
    for attempt in range(3):
        _throttle()
        req = urllib.request.Request(url, headers={"User-Agent": sec_fundamentals.UA,
                                                   "Accept-Encoding": "gzip"})
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                # companyfacts JSON is several MB; gzip cuts the transfer ~10x.
                if resp.headers.get("Content-Encoding") == "gzip":
                    import gzip
                    raw = gzip.decompress(raw)
                body = raw.decode("utf-8", "replace")
            return json.loads(body) if as_json else body
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return None
            last = exc
        except Exception as exc:  # noqa: BLE001 - network layer, retry anything
            last = exc
        if attempt < 2:
            time.sleep(2 ** attempt)
    if last is not None:
        print(f"  ! {url}: {last}", file=sys.stderr)
    return None


def get_text(url):
    return _http(url, as_json=False)


def get_json(url):
    return _http(url, as_json=True)


def parse_index(text):
    """Rows from a daily index, wanted forms only.

    Fixed-width columns are unreliable across years, so split from the right:
    the last three whitespace fields are file name, date and CIK, the first is
    the form, and the company name is whatever lies between.
    """
    if not text:
        return []
    out = []
    started = False
    for line in text.splitlines():
        if not started:
            if line.startswith("-"):
                started = True
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        form = parts[0].strip()
        if form not in sec_fundamentals.FORMS:
            continue
        # Line order: form, company name, CIK, date filed, file name.
        cik, filed, fname = parts[-3], parts[-2], parts[-1]
        name = " ".join(parts[1:-3]).strip()
        if not fname.endswith(".txt"):
            continue
        adsh = fname.rsplit("/", 1)[-1][: -len(".txt")]
        try:
            cik_int = int(cik)
        except ValueError:
            continue
        out.append({"form": form, "name": name, "cik": cik_int,
                    "filed": filed, "adsh": adsh})
    return out


def et_accepted(iso_utc):
    """EDGAR acceptance timestamps are UTC; sec_filings stores New York local."""
    if not iso_utc:
        return None
    s = iso_utc.strip().replace("Z", "+00:00")
    stamp = dt.datetime.fromisoformat(s)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=dt.timezone.utc)
    local = stamp.astimezone(NY)
    return local.strftime("%Y-%m-%d %H:%M:%S.") + str(local.microsecond // 100000)


def qtrs(start, end):
    """Quarters covered by a fact; instant facts (no start) are 0."""
    if start is None:
        return 0
    try:
        a = dt.date.fromisoformat(start)
        b = dt.date.fromisoformat(end)
    except (TypeError, ValueError):
        return 0
    return max(1, round((b - a).days / 91.31))


def _sub_entry(sub, adsh):
    recent = ((sub or {}).get("filings") or {}).get("recent") or {}
    accns = recent.get("accessionNumber") or []
    for i, accn in enumerate(accns):
        if accn == adsh:
            def at(key):
                vals = recent.get(key) or []
                return vals[i] if i < len(vals) else None
            return {"form": at("form"), "filingDate": at("filingDate"),
                    "reportDate": at("reportDate"),
                    "acceptanceDateTime": at("acceptanceDateTime")}
    return None


def _first_fact(facts, adsh):
    for tag, node in ((facts or {}).get("us-gaap") or {}).items():
        for unit_facts in (node.get("units") or {}).values():
            for fact in unit_facts:
                if fact.get("accn") == adsh:
                    return fact
    return None


def filing_row(adsh, cik, sub, facts, ticker):
    entry = _sub_entry(sub, adsh)
    if entry is None:
        return None
    fact = _first_fact(facts, adsh)
    fy = str(fact["fy"]) if fact and fact.get("fy") is not None else None
    fp = fact.get("fp") if fact else None
    period = (entry.get("reportDate") or "").replace("-", "") or None
    filed = (entry.get("filingDate") or "").replace("-", "") or None
    return (adsh, cik, (sub or {}).get("name"), (sub or {}).get("sic"),
            entry.get("form"), period, fy, fp, filed, ticker,
            et_accepted(entry.get("acceptanceDateTime")), 0, None)


def fact_rows(adsh, facts):
    """Wanted us-gaap facts for one accession, last duplicate wins."""
    seen = {}
    for tag, node in ((facts or {}).get("us-gaap") or {}).items():
        if tag not in sec_fundamentals.WANTED:
            continue
        for unit_facts in (node.get("units") or {}).values():
            for fact in unit_facts:
                if fact.get("accn") != adsh:
                    continue
                end = fact.get("end")
                val = fact.get("val")
                if end is None or val is None:
                    continue
                try:
                    value = float(val)
                except (TypeError, ValueError):
                    continue
                ddate = end.replace("-", "")
                key = (tag, ddate, qtrs(fact.get("start"), end))
                seen[key] = (adsh, tag, ddate, key[2], value)
    return list(seen.values())


FILING_UPSERT = """
INSERT INTO sec_filings
    (adsh, cik, name, sic, form, period, fy, fp, filed, ticker, accepted,
     prevrpt, detail)
VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
ON CONFLICT(adsh) DO UPDATE SET
    cik=excluded.cik, name=excluded.name, sic=excluded.sic,
    form=excluded.form, period=excluded.period, fy=excluded.fy,
    fp=excluded.fp, filed=excluded.filed,
    ticker=CASE WHEN sec_filings.ticker_raw IS NULL
                THEN excluded.ticker ELSE sec_filings.ticker END,
    accepted=excluded.accepted, prevrpt=excluded.prevrpt,
    detail=excluded.detail
"""


def load_filing(conn, entry, get_json, tmap):
    adsh = entry["adsh"]
    if conn.execute("SELECT 1 FROM sec_filings WHERE adsh=?", (adsh,)).fetchone():
        return 0
    cik = entry["cik"]
    # No cache across filings: a company's facts JSON is several MB decoded, and a peak
    # earnings day has hundreds of filers (reviewed 2026-09-29). Most CIKs file once a day.
    sub = get_json(SUBMISSIONS.format(cik=cik))
    # companyfacts JSON is {"cik", "entityName", "facts": {"us-gaap": {...}}}.
    facts = (get_json(COMPANYFACTS.format(cik=cik)) or {}).get("facts")
    row = filing_row(adsh, cik, sub, facts, tmap.get(cik))
    if row is None:
        return 0
    conn.execute(FILING_UPSERT, row)
    rows = fact_rows(adsh, facts)
    conn.executemany(
        "INSERT OR REPLACE INTO sec_facts (adsh, tag, ddate, qtrs, value) "
        "VALUES (?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)


def init(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS edgar_financials_days(
        day TEXT PRIMARY KEY, filings INTEGER, loaded_at TEXT)""")
    conn.commit()


def universe_ciks(conn):
    tmap = sec_fundamentals._ticker_map(conn)
    priced = {r[0] for r in conn.execute("SELECT ticker FROM symbols")}
    return {cik for cik, ticker in tmap.items() if ticker in priced}


def _index_url(day):
    d = dt.date.fromisoformat(day)
    return DAILY_INDEX.format(y=d.year, q=(d.month - 1) // 3 + 1,
                              d=d.strftime("%Y%m%d"))


def run(conn, days, get_text, get_json, only_ciks=None):
    init(conn)
    tmap = sec_fundamentals._ticker_map(conn)
    stats = {"days": 0, "filings_seen": 0, "loaded": 0, "facts": 0, "skipped": 0}
    for day in days:
        text = get_text(_index_url(day))
        if text is None:
            continue
        entries = parse_index(text)
        if only_ciks is not None:
            entries = [e for e in entries if e["cik"] in only_ciks]
        stats["filings_seen"] += len(entries)
        for entry in entries:
            n = load_filing(conn, entry, get_json, tmap)
            if n:
                stats["loaded"] += 1
                stats["facts"] += n
            else:
                stats["skipped"] += 1
        conn.execute(
            "INSERT OR REPLACE INTO edgar_financials_days (day, filings, loaded_at) "
            "VALUES (?,?,?)",
            (day, len(entries), dt.datetime.now(dt.timezone.utc).isoformat()))
        conn.commit()
        stats["days"] += 1
    return stats


def _weekdays(start, end):
    out = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d.isoformat())
        d += dt.timedelta(days=1)
    return out


def _pending(conn, days):
    done = {r[0] for r in conn.execute("SELECT day FROM edgar_financials_days")}
    return [d for d in days if d not in done]


def main(argv=None):
    ap = argparse.ArgumentParser(description="Daily EDGAR 10-Q / 10-K feed")
    ap.add_argument("--daily", action="store_true")
    ap.add_argument("--days", type=int, default=7)
    ap.add_argument("--since")
    ap.add_argument("--status", action="store_true")
    args = ap.parse_args(argv)

    from universe import load_config
    conn = storage.connect(load_config()["database"]["market_data_path"])
    sec_fundamentals.init(conn)
    init(conn)

    if args.status:
        n = conn.execute("SELECT COUNT(*) FROM edgar_financials_days").fetchone()[0]
        f = conn.execute("SELECT COUNT(*) FROM sec_filings").fetchone()[0]
        print({"days_recorded": n, "sec_filings": f})
        return 0

    today = dt.datetime.now(dt.timezone.utc).date()
    if args.since:
        days = _weekdays(dt.date.fromisoformat(args.since), today)
    else:
        days = _weekdays(today - dt.timedelta(days=max(args.days, 1) * 2), today)
        days = days[-max(args.days, 1):]
    # Today and yesterday are always re-processed: filings accepted after the
    # index was generated would otherwise be missed permanently.
    recent = {today.isoformat(), (today - dt.timedelta(days=1)).isoformat()}
    days = [d for d in days if d in recent or d not in
            {r[0] for r in conn.execute("SELECT day FROM edgar_financials_days")}]

    only = universe_ciks(conn)
    print(run(conn, days, get_text, get_json, only_ciks=only))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
