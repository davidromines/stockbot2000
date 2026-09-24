"""
Addendum C (revision 2), Stage 1 — Layer A: which US companies existed.

One record per company, 1996-2024, merged from every free source this project
holds, with per-field provenance. Nothing here is a price; Layer B (synthetic
paths) builds on this.

SOURCES, AND WHAT EACH IS TRUSTED FOR
-------------------------------------
  edgar_companies / sec_filings   every annual filer by CIK, name, SIC, first and
                                  last filing (1993-, dense from 1996). The spine.
  delistings (Alpha Vantage)      exchange, IPO and delisting DATES — real, but
                                  thin before 2009.
  historical_listings (IA)        which common-stock tickers were listed on each
                                  snapshot date, 2008-.
  symbols / prices                which companies we hold real prices for.
  finsaber_prices (finsaber.db)   delisted-inclusive S&P 500 prices, 2000-2024.
  edgar_events (8-K items)        delisting REASONS where filed: 1.03
                                  bankruptcy, 2.01 completed acquisition, 3.01
                                  delisting notice. Never inferred when absent.

PROVENANCE
----------
Every derived field carries `<field>_src`: the source it came from, or
`imputed:<how>` (e.g. `imputed:first_edgar_filing` for a listing date), or
null when unknown. Unknown stays unknown — a missing delisting reason is null,
not "merger" (Addendum C; the same rule as statements.py: absence is never
zero).

MATCHING
--------
CIK is the key where known. An Alpha Vantage or Internet Archive listing is
joined to a CIK by ticker (edgar/sec_filings) and then by normalised company
name; an unmatched listing becomes its own record with a source-prefixed id
(`AV:SYMBOL:ipo`, `IA:TICKER`). A dead company with no recoverable ticker keeps
its CIK id and `ticker_src = null` (Addendum C question 4, recommended answer).

ASSUMPTIONS (the eight Stage J questions — built on the recommended answers
2026-09-24 under the user's instruction to build every roadmap item; each is a
config value in `universe_reconstruction:` and can be changed):
  1 scope 1996-2024           5 synthetic rows: retests/stress only
  2 primary DB is real data   6 separate store: data/universe/
  3 NYSE/NASDAQ/AMEX common   7 SPY trailing 12m conditioning (Stage 3)
  4 CIK ids for no-ticker     8 merger delisting return ~ +1% +/- 3% (Stage 3)

    python universe_layer_a.py --build      writes data/universe/layer_a.parquet
    python universe_layer_a.py --report     counts, provenance, alive by year
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
import os
import re
import sqlite3
import sys
from datetime import datetime, timezone

import pandas as pd

log = logging.getLogger("universe_layer_a")

OUT_DIR = "data/universe"
DEFAULTS = {"start": "1996-01-01", "end": "2024-12-31",
            "exchanges": ["NYSE", "NASDAQ", "NYSE MKT", "AMEX", "NYSE AMERICAN"]}
REASON_ITEMS = {"1.03": "bankruptcy", "2.01": "acquisition", "3.01": "delisting_notice"}
_SUFFIX = re.compile(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|PLC|LLC|LP|"
                     r"HOLDINGS?|GROUP|THE|NEW|DEL|DE|CLASS [A-Z]|COMMON STOCK|ORDINARY SHARES|SHARES)\b")


def settings(cfg: dict) -> dict:
    return {**DEFAULTS, **(cfg.get("universe_reconstruction") or {})}


def norm_name(name) -> str:
    """Upper-case, punctuation and corporate suffixes stripped: 'Altaba Inc.' -> 'ALTABA'."""
    if not isinstance(name, str):
        return ""
    s = re.sub(r"[^A-Z0-9 ]", " ", name.upper().replace("&", " AND "))
    s = _SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


def _month_end(ym: str | None) -> str | None:
    if not ym:
        return None
    return (pd.Period(ym, "M").end_time.date()).isoformat() if len(ym) == 7 else ym[:10]


def _month_start(ym: str | None) -> str | None:
    if not ym:
        return None
    return f"{ym}-01" if len(ym) == 7 else ym[:10]


def build(conn, cfg: dict, finsaber_db: str = "data/finsaber.db") -> pd.DataFrame:
    s = settings(cfg)
    q = lambda sql, *a: pd.read_sql_query(sql, conn, params=a)      # noqa: E731

    # --- the EDGAR spine ------------------------------------------------------
    ed = q("SELECT cik, company_name, ticker, first_filed, last_filed, n_annual, still_filing "
           "FROM edgar_companies")
    # SQLite's bare-column rule: with MAX() in the select list, the other
    # columns come from the row holding the max — the latest filing per CIK.
    sic = q("SELECT cik, sic, MAX(filed) AS f FROM sec_filings WHERE sic IS NOT NULL GROUP BY cik")[["cik", "sic"]]
    tick = q("SELECT cik, ticker, MAX(filed) AS f FROM sec_filings WHERE ticker IS NOT NULL "
             "GROUP BY cik")[["cik", "ticker"]]
    ed = ed.merge(sic, on="cik", how="left").merge(tick.rename(columns={"ticker": "sec_ticker"}),
                                                  on="cik", how="left")
    rec = pd.DataFrame({
        "company_id": "CIK" + ed["cik"].astype(str).str.zfill(10),
        "cik": ed["cik"],
        "name": ed["company_name"], "name_src": "edgar",
        "ticker": ed["sec_ticker"].fillna(ed["ticker"]),
        "sic": ed["sic"],
        "first_seen": ed["first_filed"].map(_month_start), "first_seen_src": "imputed:first_edgar_filing",
        "last_seen": ed["last_filed"].map(_month_end), "last_seen_src": "imputed:last_edgar_filing",
        "status": ed["still_filing"].map({1: "active", 0: "ended"}),
        "exchange": None, "exchange_src": None,
    })
    rec["ticker_src"] = rec["ticker"].notna().map({True: "edgar", False: None})
    rec["sic_src"] = rec["sic"].notna().map({True: "sec_filings", False: None})
    rec["norm"] = rec["name"].map(norm_name)
    by_ticker = {t: i for i, t in rec["ticker"].dropna().items()}
    by_name = {}
    for i, n in rec["norm"].items():
        if n:
            by_name.setdefault(n, i)

    def attach(ticker, name):
        if ticker and ticker in by_ticker:
            return by_ticker[ticker], "ticker"
        n = norm_name(name)
        if n and n in by_name:
            return by_name[n], "name"
        return None, None

    extra = []

    # --- Alpha Vantage delistings: real dates and exchange ---------------------
    av = q("SELECT symbol, name, exchange, ipo_date, delisting_date FROM delistings WHERE asset_type='Stock'")
    rec["delisted_on"], rec["delisted_on_src"], rec["match"] = None, None, None
    for r in av.itertuples(index=False):
        i, how = attach(r.symbol, r.name)
        if i is None:
            extra.append({"company_id": f"AV:{r.symbol}:{r.ipo_date}", "name": r.name, "name_src": "alphavantage",
                          "ticker": r.symbol, "ticker_src": "alphavantage", "exchange": r.exchange,
                          "exchange_src": "alphavantage", "first_seen": r.ipo_date, "first_seen_src": "alphavantage",
                          "last_seen": r.delisting_date, "last_seen_src": "alphavantage",
                          "delisted_on": r.delisting_date, "delisted_on_src": "alphavantage",
                          "status": "delisted", "match": "unmatched"})
            continue
        rec.at[i, "delisted_on"], rec.at[i, "delisted_on_src"] = r.delisting_date, "alphavantage"
        rec.at[i, "last_seen"], rec.at[i, "last_seen_src"] = r.delisting_date, "alphavantage"
        rec.at[i, "status"] = "delisted"
        rec.at[i, "exchange"], rec.at[i, "exchange_src"] = r.exchange, "alphavantage"
        if r.ipo_date:
            rec.at[i, "first_seen"], rec.at[i, "first_seen_src"] = r.ipo_date, "alphavantage"
        if pd.isna(rec.at[i, "ticker"]):
            rec.at[i, "ticker"], rec.at[i, "ticker_src"] = r.symbol, "alphavantage"
        rec.at[i, "match"] = f"alphavantage:{how}"

    # --- Internet Archive: listed common stock, 2008- ---------------------------
    ia = q("SELECT ticker, MIN(snapshot_date) first_d, MAX(snapshot_date) last_d, MAX(name) name, "
           "MAX(exchange) exchange FROM historical_listings WHERE security_type='common_stock' GROUP BY ticker")
    rec["in_ia"] = False
    for r in ia.itertuples(index=False):
        i, how = attach(r.ticker, r.name)
        if i is None:
            extra.append({"company_id": f"IA:{r.ticker}", "name": r.name, "name_src": "internet_archive",
                          "ticker": r.ticker, "ticker_src": "internet_archive", "exchange": r.exchange,
                          "exchange_src": "internet_archive", "first_seen": r.first_d,
                          "first_seen_src": "imputed:first_ia_snapshot", "last_seen": r.last_d,
                          "last_seen_src": "imputed:last_ia_snapshot", "status": None, "in_ia": True,
                          "match": "unmatched"})
            continue
        rec.at[i, "in_ia"] = True
        if pd.isna(rec.at[i, "exchange"]) and r.exchange:
            rec.at[i, "exchange"], rec.at[i, "exchange_src"] = r.exchange, "internet_archive"
        if pd.isna(rec.at[i, "ticker"]):
            rec.at[i, "ticker"], rec.at[i, "ticker_src"] = r.ticker, "internet_archive"
        if pd.isna(rec.at[i, "match"]):
            rec.at[i, "match"] = f"internet_archive:{how}"

    df = pd.concat([rec, pd.DataFrame(extra)], ignore_index=True)

    # --- real prices we hold ----------------------------------------------------
    have = set(t for (t,) in conn.execute("SELECT ticker FROM symbols WHERE security_type='common_stock'"))
    df["has_primary_prices"] = df["ticker"].isin(have)
    fins = set()
    if os.path.exists(finsaber_db):
        f = sqlite3.connect(f"file:{finsaber_db}?mode=ro", uri=True)
        fins = {t for (t,) in f.execute("SELECT DISTINCT symbol FROM finsaber_prices")}
        f.close()
    df["has_finsaber_prices"] = df["ticker"].isin(fins)

    # --- delisting reasons, only where an 8-K says so --------------------------
    ev = q("SELECT cik, item, filed FROM edgar_events WHERE item IN ('1.03','2.01','3.01')")
    ev = ev.sort_values("filed").groupby("cik").tail(1)
    reason = dict(zip(ev["cik"], ev["item"].map(REASON_ITEMS)))
    df["delisting_reason"] = df["cik"].map(reason)
    df.loc[df["status"].isin(["active"]), "delisting_reason"] = None
    df["delisting_reason_src"] = df["delisting_reason"].notna().map({True: "edgar_8k", False: None})

    # --- listing evidence and scope ---------------------------------------------
    def evidence(r):
        if r["has_primary_prices"] or r["has_finsaber_prices"]:
            return "prices"
        if r["delisted_on_src"] == "alphavantage" or str(r["company_id"]).startswith("AV:"):
            return "alphavantage"
        if r["in_ia"]:
            return "internet_archive"
        if isinstance(r["ticker"], str):
            return "edgar_ticker"
        return "edgar_only"
    df["listing_evidence"] = df.apply(evidence, axis=1)
    ex_ok = df["exchange"].isna() | df["exchange"].str.upper().isin([e.upper() for e in s["exchanges"]])
    alive = (df["first_seen"].fillna("0000") <= s["end"]) & (df["last_seen"].fillna("9999") >= s["start"])
    df["in_scope"] = ex_ok & alive
    df["built_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    return df.drop(columns=["norm"], errors="ignore")


def report(df: pd.DataFrame, cfg: dict) -> dict:
    s = settings(cfg)
    sc = df[df["in_scope"]]
    years = {}
    for y in range(int(s["start"][:4]), int(s["end"][:4]) + 1):
        d = f"{y}-06-30"
        a = sc[(sc["first_seen"].fillna("0000") <= d) & (sc["last_seen"].fillna("9999") >= d)]
        years[y] = {"alive": int(len(a)),
                    "with_real_prices": int((a["has_primary_prices"] | a["has_finsaber_prices"]).sum()),
                    "listing_evidence_beyond_edgar": int((a["listing_evidence"] != "edgar_only").sum())}
        years[y]["priced_share"] = round(years[y]["with_real_prices"] / years[y]["alive"], 3) if len(a) else None
    return {
        "records": int(len(df)), "in_scope": int(len(sc)),
        "by_listing_evidence": sc["listing_evidence"].value_counts().to_dict(),
        "by_status": sc["status"].fillna("unknown").value_counts().to_dict(),
        "delisting_reason_known": int(sc["delisting_reason"].notna().sum()),
        "by_reason": sc["delisting_reason"].value_counts().to_dict(),
        "match": sc["match"].fillna("edgar_spine").value_counts().to_dict(),
        "provenance": {f: sc[f + "_src"].fillna("unknown").value_counts().to_dict()
                       for f in ("first_seen", "last_seen", "ticker", "exchange")},
        "by_year": years,
    }


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Addendum C Stage 1: Layer A universe reconstruction.")
    ap.add_argument("--build", action="store_true")
    ap.add_argument("--report", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    os.makedirs(OUT_DIR, exist_ok=True)
    path = os.path.join(OUT_DIR, "layer_a.parquet")
    if args.build:
        conn = sqlite3.connect(f"file:{cfg['database']['market_data_path']}?mode=ro", uri=True)
        df = build(conn, cfg)
        df.to_parquet(path, index=False)
        digest = hashlib.sha256(open(path, "rb").read()).hexdigest()
        rep = {**report(df, cfg), "sha256": digest, "path": path, "settings": settings(cfg)}
        with open(os.path.join(OUT_DIR, "layer_a_report.json"), "w") as f:
            json.dump(rep, f, indent=2, default=str)
        log.info(f"wrote {path} ({len(df):,} records, sha256 {digest[:16]})")
    if args.report or args.build:
        rep = json.load(open(os.path.join(OUT_DIR, "layer_a_report.json")))
        print(json.dumps({k: v for k, v in rep.items() if k != "by_year"}, indent=1, default=str))
        print("year  alive  priced  share  listed-evidence")
        for y, v in rep["by_year"].items():
            print(f"{y}  {v['alive']:>6} {v['with_real_prices']:>6}  {v['priced_share']}  "
                  f"{v['listing_evidence_beyond_edgar']:>6}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
