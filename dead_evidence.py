"""
Stage M2 — real evidence for dead companies, from SEC filings.

Generator v4 guessed the exit reason for 8,060 of its 8,141 synthetic dead
companies (a 40/55/5 prior). The filings say what happened. This module
collects that evidence; it generates nothing. Research and design:
docs/STAGE_M_RESEARCH.md.

THREE PASSES, EACH RESUMABLE
----------------------------
1. `--index`   (local, no network) — every quarterly EDGAR form index already
   cached by edgar_registry.py (data/edgar/form_*.idx, 1993-now) is scanned
   for the forms that mark an exit, plus annual reports:
       25 / 25-NSE        delisting (25-NSE: filed by the exchange; 25: by the issuer)
       15-12B/12G/15D     deregistration
       DEFM14A/DEFM14C    merger proxy / information statement      -> acquired
       SC TO-T, SC 14D9   third-party tender offer / target response -> acquired
       SC 13E3            going-private transaction
       10-K family        last annual report
   Written to data/universe/edgar_exit_forms.parquet.
2. `--link`    (local) — companies with no CIK (half the synthetic set) are
   linked by normalised name, but ONLY to a filer whose filings end near the
   company's own last date, and only when exactly one filer qualifies (the
   ticker-reuse lesson: a name or ticker alone attaches the wrong company).
3. `--fetch`   (network, SEC rate limit) — each dead company's submissions
   record, cached under data/edgar/submissions/: 8-K item codes (1.03
   bankruptcy, 2.01 acquisition completed, 3.01 delisting notice), SIC (6770 =
   blank check / SPAC), exchanges, former names.
Then `--classify` writes data/universe/dead_evidence.parquet: one row per dead
company with an evidence-based exit type, the delisting date, and the forms
that justify it — or `unknown`, never a guess.

EXIT TYPES (evidence rules, in priority order)
----------------------------------------------
    spac          SIC 6770, or a blank-check name with no operating history
    bankruptcy    8-K item 1.03
    acquired      DEFM14A/C, SC TO-T or SC 14D9 in the 18 months before the
                  end, or the target's 8-K item 5.01 (change in control), or
                  8-K item 2.01 AND a Form 25-NSE
    going_private SC 13E3
    transfer_not_death  a delisting form, but annual reports continue a year
                  later: an exchange transfer or relisting (8-K 3.01 also covers
                  "transfer of listing"). NOT a death; excluded from generation.
    performance   8-K 3.01 or Form 25-NSE, no acquisition evidence, AND the
                  company then deregistered (Form 15) or stopped filing
    voluntary     issuer-filed Form 25 with no acquisition evidence
    delisted_unclear  a delisting form and nothing that settles it
    unknown       nothing conclusive

TESTED 2026-09-25 on 116 real dead companies we hold prices for: the first
rules labelled 9 as performance and only 4 were (Brunswick, Fossil, Hennessy
were exchange transfers) — hence the transfer and stop-filing tests.
Every row carries `evidence` (the forms and dates) and `exit_src`.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import json
import logging
import re
import sys
import time
from pathlib import Path

import pandas as pd

log = logging.getLogger("dead_evidence")

INDEX_DIR = Path("data/edgar")
SUBS_DIR = Path("data/edgar/submissions")
FORMS_OUT = Path("data/universe/edgar_exit_forms.parquet")
LINK_OUT = Path("data/universe/dead_cik_links.parquet")
OUT = Path("data/universe/dead_evidence.parquet")
LAYER_A = Path("data/universe/layer_a.parquet")

EXIT_FORMS = {"25", "25-NSE", "15-12B", "15-12G", "15-15D", "DEFM14A", "DEFM14C", "SC TO-T", "SC 14D9",
              "SC 13E3", "10-K", "10-K405", "10-KSB", "10-K/A", "20-F", "40-F"}
ACQ_FORMS = {"DEFM14A", "DEFM14C", "SC TO-T", "SC 14D9"}
SUFFIX = re.compile(r"\b(INC|INCORPORATED|CORP|CORPORATION|CO|COMPANY|LTD|LIMITED|LLC|LP|PLC|HOLDINGS?|GROUP|"
                    r"THE|NEW|DE|DEL|NV|MD|/[A-Z]{2}/?)\b")
BLANK_CHECK = re.compile(r"\bACQUISITION (CORP|CO|COMPANY|INC|LTD|HOLDINGS)\b|\bBLANK CHECK\b|\bSPAC\b", re.I)


def norm(name: str) -> str:
    s = re.sub(r"[^A-Z0-9 /]", " ", str(name or "").upper())
    s = SUFFIX.sub(" ", s)
    return re.sub(r"\s+", " ", s).strip()


# --- pass 1: the local form indexes -------------------------------------------------

LINE = re.compile(r"^(?P<form>\S+(?: \S+)*?)\s{2,}(?P<name>.+?)\s+(?P<cik>\d+)\s+"
                  r"(?P<date>\d{4}-\d{2}-\d{2}|\d{8})\s+(?P<file>\S+)\s*$")


def _parse_index(path: Path) -> list:
    """(form, name, cik, filed, file) for the exit forms in one form.idx. Parsed from the right:
    long company names overflow the fixed columns in some quarters, so column slicing misreads them."""
    out, body = [], False
    with path.open("r", errors="replace") as fh:
        for line in fh:
            if not body:
                body = line.startswith("---")
                continue
            m = LINE.match(line.rstrip("\n"))
            if not m or m["form"] not in EXIT_FORMS:
                continue
            d = m["date"]
            d = d if "-" in d else f"{d[:4]}-{d[4:6]}-{d[6:]}"
            out.append((m["form"], m["name"].strip(), int(m["cik"]), d, m["file"]))
    return out


def build_index() -> pd.DataFrame:
    files = sorted(INDEX_DIR.glob("form_*.idx"))
    rows = []
    for f in files:
        rows += _parse_index(f)
    df = pd.DataFrame(rows, columns=["form", "name", "cik", "filed", "file"]).drop_duplicates()
    FORMS_OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(FORMS_OUT, index=False)
    log.info(f"{len(files)} indexes -> {len(df):,} exit/annual filings, {df.cik.nunique():,} filers")
    return df


# --- pass 2: link companies without a CIK -----------------------------------------------

def dead_companies() -> pd.DataFrame:
    """Layer A companies that ended and have no real prices — the ones synthetic data stands in for."""
    a = pd.read_parquet(LAYER_A)
    ended = a["status"].astype(str).str.lower().isin(["delisted", "dead", "ended", "inactive"]) | a["delisted_on"].notna()
    d = a[ended & ~a["has_primary_prices"].astype(bool)].copy()
    d["end"] = d["delisted_on"].fillna(d["last_seen"])
    return d


def link(forms: pd.DataFrame, dead: pd.DataFrame) -> pd.DataFrame:
    """CIK for dead companies without one: unique normalised-name match whose filings end near the company's end."""
    fil = forms.assign(n=forms["name"].map(norm)).groupby(["n", "cik"]).agg(last=("filed", "max"),
                                                                             first=("filed", "min")).reset_index()
    by_name = {k: g for k, g in fil.groupby("n")}
    out = []
    for r in dead[dead["cik"].isna()].itertuples():
        n = norm(r.name)
        g = by_name.get(n)
        if g is None or not r.end:
            continue
        end = pd.Timestamp(str(r.end)[:10])
        ok = g[(pd.to_datetime(g["last"]) >= end - pd.Timedelta(days=730)) &
               (pd.to_datetime(g["last"]) <= end + pd.Timedelta(days=400))]
        if len(ok) == 1:
            out.append({"company_id": r.company_id, "cik": int(ok.iloc[0]["cik"]), "link": "name+dates",
                        "filer_last": ok.iloc[0]["last"]})
    df = pd.DataFrame(out)
    df.to_parquet(LINK_OUT, index=False)
    log.info(f"linked {len(df):,} of {int(dead['cik'].isna().sum()):,} dead companies without a CIK")
    return df


# --- pass 3: submissions records (network) ------------------------------------------------

def fetch(ciks: list, rate: float = 0.12) -> int:
    import requests
    import edgar_registry as er
    SUBS_DIR.mkdir(parents=True, exist_ok=True)
    s = requests.Session()
    s.headers.update({"User-Agent": er.UA, "Accept-Encoding": "gzip, deflate"})
    got = 0
    for i, cik in enumerate(ciks):
        dest = SUBS_DIR / f"CIK{int(cik):010d}.json"
        if dest.exists():
            continue
        for attempt in range(4):
            try:
                r = s.get(f"https://data.sec.gov/submissions/CIK{int(cik):010d}.json", timeout=45)
                break
            except requests.RequestException:
                time.sleep(rate * 4 ** attempt)
        else:
            continue
        if r.status_code == 403:
            log.error("403 from the SEC — User-Agent rejected or rate exceeded; stopping")
            return got
        if r.status_code == 200:
            dest.write_bytes(r.content)
            got += 1
        time.sleep(rate)
        if i % 500 == 0:
            log.info(f"submissions {i:,}/{len(ciks):,} ({got:,} new)")
    return got


def _subs(cik) -> dict:
    p = SUBS_DIR / f"CIK{int(cik):010d}.json"
    if not p.exists():
        return {}
    try:
        d = json.loads(p.read_text())
    except ValueError:
        return {}
    r = d.get("filings", {}).get("recent", {})
    items = [(f, dt, it) for f, dt, it in zip(r.get("form", []), r.get("filingDate", []),
                                              r.get("items", [""] * len(r.get("form", [])))) if f.startswith("8-K")]
    return {"sic": d.get("sic"), "sic_desc": d.get("sicDescription"), "exchanges": d.get("exchanges") or [],
            "items": items}


# --- classification --------------------------------------------------------------------------

def classify(forms: pd.DataFrame, dead: pd.DataFrame, links: pd.DataFrame, out_path: Path | None = OUT) -> pd.DataFrame:
    dead = dead.copy()
    lk = links.set_index("company_id")["cik"] if len(links) else pd.Series(dtype=float)
    dead["cik_link"] = dead["company_id"].map(lk)
    dead["cik_use"] = dead["cik"].fillna(dead["cik_link"])
    dead["cik_src"] = dead["cik"].notna().map({True: "layer_a", False: None})
    dead.loc[dead["cik"].isna() & dead["cik_link"].notna(), "cik_src"] = "name+dates"
    by_cik = {k: g for k, g in forms.groupby("cik")}
    rows = []
    for r in dead.itertuples():
        ev, typ, src, delist = [], "unknown", None, None
        end = pd.Timestamp(str(r.end)[:10]) if r.end else None
        sub = _subs(r.cik_use) if pd.notna(r.cik_use) else {}
        g = by_cik.get(int(r.cik_use)) if pd.notna(r.cik_use) else None
        if g is not None and end is not None:
            near = g[(pd.to_datetime(g["filed"]) >= end - pd.Timedelta(days=548)) &
                     (pd.to_datetime(g["filed"]) <= end + pd.Timedelta(days=200))]
            ev = [f"{f}@{d}" for f, d in zip(near["form"], near["filed"]) if not re.match(r"10-K|20-F|40-F", f)]
            forms_near = set(near["form"])
            d25 = near[near["form"].isin(["25", "25-NSE"])]["filed"]
            delist = d25.min() if len(d25) else None
        else:
            forms_near = set()
        items = set()
        for f, dt, it in sub.get("items", []):
            if end is not None and abs((pd.Timestamp(dt) - end).days) <= 548:
                for x in str(it).split(","):
                    if x.strip() in ("1.03", "2.01", "3.01", "5.01"):
                        items.add(x.strip())
                        ev.append(f"8-K {x.strip()}@{dt}")
        sic = str(sub.get("sic") or r.sic or "")
        if sic == "6770" or (BLANK_CHECK.search(str(r.name or "")) and not (forms_near & ACQ_FORMS)):
            typ, src = "spac", "SIC 6770" if sic == "6770" else "blank-check name"
        elif "1.03" in items:
            typ, src = "bankruptcy", "8-K 1.03"
        elif forms_near & ACQ_FORMS:
            typ, src = "acquired", "+".join(sorted(forms_near & ACQ_FORMS))
        elif "5.01" in items:
            # The TARGET's own 8-K: change in control. Stock-for-stock deals often file the
            # proxy under the acquirer's CIK only, so this is how many of them show.
            typ, src = "acquired", "8-K 5.01 (change in control)"
        elif "2.01" in items and "25-NSE" in forms_near:
            typ, src = "acquired", "8-K 2.01 + 25-NSE"
        elif "SC 13E3" in forms_near:
            typ, src = "going_private", "SC 13E3"
        last_10k = g[g["form"].str.match(r"10-K|20-F|40-F")]["filed"].max() if g is not None else None
        delist_signal = "3.01" in items or "25-NSE" in forms_near or "25" in forms_near
        ref = pd.Timestamp(delist) if delist else end
        if typ == "unknown" and delist_signal and last_10k and ref is not None \
                and pd.Timestamp(last_10k) > ref + pd.Timedelta(days=365):
            # Still filing annual reports a year after the delisting form: an exchange
            # transfer or relisting, not a death (tested 2026-09-25: Brunswick, Fossil,
            # Hennessy Advisors). Excluded from synthetic generation.
            typ, src = "transfer_not_death", f"annual reports continue to {last_10k}"
        elif typ == "unknown" and delist_signal:
            dereg = bool(forms_near & {"15-12B", "15-12G", "15-15D"})
            stopped = not last_10k or ref is None or pd.Timestamp(last_10k) <= ref + pd.Timedelta(days=30)
            if "25" in forms_near and "25-NSE" not in forms_near and "3.01" not in items:
                typ, src = "voluntary", "issuer-filed Form 25"
            elif dereg or stopped:
                typ, src = "performance", ("8-K 3.01" if "3.01" in items else "25-NSE") + \
                    (" + deregistered (Form 15)" if dereg else " + annual reports stop") + ", no acquisition evidence"
            else:
                typ, src = "delisted_unclear", "delisting form, filings neither stop nor continue clearly"
        rows.append({"company_id": r.company_id, "cik": r.cik_use, "cik_src": r.cik_src, "name": r.name,
                     "exchange": r.exchange, "end": str(r.end)[:10] if r.end else None, "exit_type": typ,
                     "exit_src": src, "delist_form_date": delist, "last_10k": last_10k, "sic": sic or None,
                     "evidence": "; ".join(sorted(set(ev)))[:2000]})
    out = pd.DataFrame(rows)
    if out_path:
        out.to_parquet(out_path, index=False)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Evidence-based exit types for dead companies (Stage M2).")
    ap.add_argument("--index", action="store_true")
    ap.add_argument("--link", action="store_true")
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--classify", action="store_true")
    ap.add_argument("--all", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    forms = build_index() if (a.index or a.all or not FORMS_OUT.exists()) else pd.read_parquet(FORMS_OUT)
    dead = dead_companies()
    links = link(forms, dead) if (a.link or a.all or not LINK_OUT.exists()) else pd.read_parquet(LINK_OUT)
    if a.fetch or a.all:
        # Relevant: dead companies with listing evidence (v4's set), plus EDGAR-only dead filers with a
        # Form 25 — the exchange's own delisting form, so proof of a listing. An acquisition form alone
        # is not: OTC companies file those too. Most dead filers never traded on an exchange.
        lk = links.set_index("company_id")["cik"] if len(links) else pd.Series(dtype=float)
        cik = dead["cik"].fillna(dead["company_id"].map(lk))
        listed = set(forms[forms["form"].isin(["25", "25-NSE"])]["cik"])      # a Form 25 = was exchange-listed
        keep = dead["listing_evidence"].fillna("edgar_only").ne("edgar_only") | cik.isin(listed)
        ciks = sorted(set(cik[keep].dropna().astype(int)))
        log.info(f"fetching submissions for {len(ciks):,} CIKs")
        fetch(ciks)
    if a.classify or a.all:
        out = classify(forms, dead, links)
        print(f"\n  DEAD-COMPANY EVIDENCE — {len(out):,} companies")
        print(out["exit_type"].value_counts().to_string())
        print(f"\n  with a CIK: {out['cik'].notna().mean():.0%}   delisting date from Form 25: "
              f"{out['delist_form_date'].notna().mean():.0%}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
