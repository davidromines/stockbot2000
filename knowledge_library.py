"""
Stage O (Addendum E) — the Knowledge Strategy Library: steps O1 (schema) and
O2 (ingestion). Spec: docs/ADDENDUM_E_KNOWLEDGE_FACTORY.md.

Documented trading ideas become HYPOTHESES with complete provenance. Nothing
here tests, ranks or trades anything; translation into strategy objects (O3-O5)
and the existing pipeline (O11) come after. A source saying a strategy works is
recorded as the source's CLAIM, never as a Stockbot result (§4, §19).

TABLES (O1)
-----------
knowledge_entries      one documented idea, §2 schema: source type/title/author/
                       publication/url/date/section, original claim/market/
                       asset class/period/frequency, the rule fields as the
                       source states them, required inputs, source confidence,
                       machine_translatable (YES / PENDING / NON_MACHINE_TESTABLE),
                       generation_method (§14), status (always starts HYPOTHESIS)
knowledge_parents      entry -> parent entry (variants, hybrids: every parent, §3, §15)
knowledge_links        entry -> tested strategy (strategy_key, version) — the
                       connection that must never be lost (§2)

SOURCES (O2) — what each gives, as found 2026-09-25
---------------------------------------------------
pwb_papers   Papers With Backtest, awesome-systematic-trading/scripts/paper_meta.json:
             3,806 papers, title + markets only. No rules -> PENDING. (Their coded
             library of 5,000+ is behind a paid tier; not used.)
pwb_coded    the same repo's static/strategies/*.py: 60 strategies, each with a
             rule description (sourced from Quantpedia) and a QuantConnect
             implementation. The repo states no licence: the description is kept
             in the local cache for translation, the database stores the URL and
             our own structured fields, and none of it is committed.
qc_library   QuantConnect Tutorials, "04 Strategy Library" (Apache-2.0): ~85
             documented strategies; stored with attribution.
stockbot     the 40 curated research-library entries already here (strategy_library).
StockSharp AlgoTrading is proprietary (all rights reserved): not ingested.

    ./venv/bin/python knowledge_library.py --import all
    ./venv/bin/python knowledge_library.py --report
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import hashlib
import json
import logging
import re
import sqlite3
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

log = logging.getLogger("knowledge_library")
CACHE = Path("data/knowledge")
PWB_REPO = "paperswithbacktest/awesome-systematic-trading"
QC_REPO = "QuantConnect/Tutorials"

SOURCE_TYPES = ("BOOK", "ACADEMIC_PAPER", "PRACTITIONER_RESEARCH", "OPEN_SOURCE", "PUBLISHED_SIGNAL",
                "KNOWN_FACTOR", "TRADING_SYSTEM", "MACHINE_GENERATED", "HYBRID")
GENERATION_METHODS = ("PUBLISHED_REPRODUCTION", "PUBLISHED_VARIANT", "PUBLISHED_HYBRID", "MACHINE_GENERATED",
                      "MACHINE_MUTATION", "HUMAN_DEFINED")
TRANSLATABLE = ("YES", "PENDING", "NON_MACHINE_TESTABLE")

FAMILY_WORDS = [  # §21 starting families; first match wins, so specific before general
    ("earnings surprise", ("earnings surprise", "post-earnings", "pead", "earnings announcement", "sue")),
    ("analyst revision", ("analyst", "revision", "recommendation", "forecast dispersion")),
    ("seasonality", ("january", "turn of the month", "seasonal", "calendar", "day-of-the-week", "holiday",
                     "halloween", "month", "overnight", "intraday seasonality", "lunar", "fomc")),
    ("pairs / relative value", ("pairs", "cointegration", "spread", "relative value", "arbitrage")),
    ("low volatility", ("low volatility", "low-volatility", "betting against beta", "low beta", "idiosyncratic volatility")),
    ("reversal", ("reversal", "contrarian", "overreaction")),
    ("mean reversion", ("mean reversion", "mean-reversion", "bollinger", "rsi")),
    ("breakout", ("breakout", "52-week", "52 week", "channel", "donchian", "high effect")),
    ("trend following", ("trend", "moving average", "time-series momentum", "time series momentum")),
    ("momentum", ("momentum", "winners", "relative strength")),
    ("quality", ("quality", "profitability", "fscore", "f-score", "piotroski", "accrual", "earnings quality")),
    ("value", ("value", "book-to-market", "book to market", "earnings yield", "cheap", "ppp", "carry")),
    ("size", ("size effect", "small cap", "small firm", "small companies", "size")),
    ("liquidity", ("liquidity", "illiquidity", "turnover", "volume")),
    ("volatility", ("volatility", "vix", "variance")),
    ("regime strategies", ("regime", "market state", "recession", "business cycle")),
    ("factor combinations", ("factor", "multi-factor", "combining", "combined")),
]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def family_of(text: str) -> str:
    t = (text or "").lower()
    for fam, words in FAMILY_WORDS:
        if any(w in t for w in words):
            return fam
    return "unclassified"


def entry_id(source: str, ref: str) -> str:
    return f"{source}:" + hashlib.sha1(ref.encode()).hexdigest()[:12]


# --- O1: schema ---------------------------------------------------------------------------

def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_entries (
            entry_id              TEXT PRIMARY KEY,
            source                TEXT NOT NULL,          -- importer: pwb_papers / pwb_coded / qc_library / stockbot
            strategy_name         TEXT NOT NULL,
            strategy_family       TEXT,
            source_type           TEXT NOT NULL,
            source_title          TEXT,
            source_author         TEXT,
            source_publication    TEXT,
            source_url            TEXT,
            source_date           TEXT,
            source_page_or_section TEXT,
            original_claim        TEXT,                   -- what the SOURCE says it earned; never our result
            original_market       TEXT,
            original_asset_class  TEXT,
            original_time_period  TEXT,
            original_frequency    TEXT,
            long_short            TEXT,
            entry_rules           TEXT,
            exit_rules            TEXT,
            position_sizing       TEXT,
            stop_loss             TEXT,
            take_profit           TEXT,
            holding_period        TEXT,
            rebalance_frequency   TEXT,
            required_data         TEXT,
            required_indicators   TEXT,
            fundamental_inputs    TEXT,
            technical_inputs      TEXT,
            volatility_inputs     TEXT,
            regime_inputs         TEXT,
            source_confidence     TEXT,                   -- HIGH peer-reviewed / MEDIUM practitioner / LOW unverified
            machine_translatable  TEXT NOT NULL DEFAULT 'PENDING',
            translation_notes     TEXT,
            generation_method     TEXT NOT NULL DEFAULT 'PUBLISHED_REPRODUCTION',
            status                TEXT NOT NULL DEFAULT 'HYPOTHESIS',
            licence               TEXT,
            raw_cache             TEXT,                   -- local path of the cached source text (never committed)
            provenance            TEXT NOT NULL,          -- JSON: importer, fetched_at, source ref, hash
            imported_at           TEXT NOT NULL
        )""")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_parents (
            entry_id TEXT NOT NULL, parent_id TEXT NOT NULL, relation TEXT NOT NULL,
            PRIMARY KEY (entry_id, parent_id))""")
    conn.execute("""CREATE TABLE IF NOT EXISTS knowledge_links (
            entry_id TEXT NOT NULL, strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
            variant TEXT NOT NULL,           -- SOURCE_REPRODUCTION / SOURCE_DERIVED_VARIANT / CONTROLLED_VARIANT / MUTATION
            linked_at TEXT NOT NULL, PRIMARY KEY (entry_id, strategy_key, version))""")
    conn.commit()


def upsert(conn, e: dict) -> None:
    """Insert or refresh an entry. Refreshing never touches status, links or translation —
    a re-import updates what the source says, not what Stockbot has learned."""
    assert e["source_type"] in SOURCE_TYPES, e["source_type"]
    e = {"imported_at": _now(), **e}
    e["provenance"] = json.dumps(e.get("provenance") or {}, sort_keys=True)
    cols = list(e)
    keep = {"status", "machine_translatable", "translation_notes", "generation_method"}
    upd = ", ".join(f"{c}=excluded.{c}" for c in cols if c not in keep and c != "entry_id")
    conn.execute(f"INSERT INTO knowledge_entries ({','.join(cols)}) VALUES ({','.join('?' * len(cols))}) "
                 f"ON CONFLICT(entry_id) DO UPDATE SET {upd}", [e[c] for c in cols])


# --- O2: importers -------------------------------------------------------------------------------

def _get(url: str, dest: Path | None = None, tries: int = 4) -> bytes:
    import requests
    for i in range(tries):
        try:
            r = requests.get(url, timeout=60, headers={"User-Agent": "stockbot2000 research"})
            if r.status_code == 200:
                if dest:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    dest.write_bytes(r.content)
                return r.content
            if r.status_code == 404:
                return b""
        except Exception:                                    # noqa: BLE001
            pass
        time.sleep(2 ** i)
    raise RuntimeError(f"could not fetch {url}")


def _tree(repo: str, branch: str) -> list:
    d = json.loads(_get(f"https://api.github.com/repos/{repo}/git/trees/{branch}?recursive=1"))
    return [x["path"] for x in d.get("tree", []) if x["type"] == "blob"]


def import_pwb_papers(conn) -> int:
    dest = CACHE / "pwb" / "paper_meta.json"
    raw = _get(f"https://raw.githubusercontent.com/{PWB_REPO}/main/scripts/paper_meta.json", dest)
    meta = json.loads(raw)
    n = 0
    for slug, v in meta.items():
        if slug.startswith("__"):
            continue                                        # pipeline section headers, not papers
        title = (v.get("title") or slug).strip().rstrip("*")
        upsert(conn, {
            "entry_id": entry_id("pwb_papers", slug), "source": "pwb_papers", "strategy_name": title,
            "strategy_family": family_of(title), "source_type": "ACADEMIC_PAPER", "source_title": title,
            "source_publication": "via Papers With Backtest catalogue", "original_asset_class": v.get("markets"),
            "source_url": f"https://paperswithbacktest.com/strategies/{slug.replace('_', '-')}",
            "source_confidence": "HIGH" if v.get("markets") else "MEDIUM", "machine_translatable": "PENDING",
            "translation_notes": "title and asset class only; rules must be extracted from the paper before testing",
            "licence": "not stated", "raw_cache": str(dest),
            "provenance": {"importer": "pwb_papers", "repo": PWB_REPO, "file": "scripts/paper_meta.json", "slug": slug,
                           "fetched_at": _now()}})
        n += 1
    conn.commit()
    return n


def _header_comment(code: str) -> tuple:
    """(source url, description) from the leading comment block of a PWB coded strategy."""
    lines, url = [], None
    for ln in code.splitlines():
        if not ln.startswith("#"):
            if lines:
                break
            continue
        t = ln.lstrip("#").strip()
        if t.startswith("http") and url is None:
            url = t
            continue
        lines.append(t)
    return url, " ".join(x for x in lines if x).strip()


def _fields(text: str) -> dict:
    """Structured hints from a rule description — recorded as the SOURCE's words, never invented."""
    t = text.lower()
    f = {}
    if "short" in t and ("long" in t or "buy" in t):
        f["long_short"] = "long-short"
    elif "buy" in t or "long" in t:
        f["long_short"] = "long-only"
    for word, val in (("daily", "daily"), ("weekly", "weekly"), ("monthly", "monthly"), ("quarterly", "quarterly"),
                      ("annual", "annual"), ("yearly", "annual")):
        if re.search(rf"\b{word}\b|rebalanced {word}|each {word.rstrip('ly')}", t):
            f["rebalance_frequency"] = val
            break
    m = re.search(r"hold[s]?(?: them| it| the portfolio)? for (\w+ (?:day|week|month|year)s?)", t)
    if m:
        f["holding_period"] = m.group(1)
    fund = [w for w in ("book", "earnings", "accrual", "asset growth", "roa", "roe", "cash flow", "dividend", "sales",
                        "market cap", "leverage", "fscore", "profit") if w in t]
    tech = [w for w in ("moving average", "52-week", "momentum", "return", "volatility", "rsi", "volume",
                        "high", "reversal", "beta") if w in t]
    if fund:
        f["fundamental_inputs"] = ", ".join(fund)
    if tech:
        f["technical_inputs"] = ", ".join(tech)
    if "crsp" in t or "nyse" in t or "nasdaq" in t or "stocks" in t:
        f["original_market"] = "US equities" if ("nyse" in t or "nasdaq" in t or "crsp" in t) else "equities"
    return f


def import_pwb_coded(conn) -> int:
    paths = [p for p in _tree(PWB_REPO, "main") if p.startswith("static/strategies/") and p.endswith(".py")]
    n = 0
    for p in paths:
        slug = Path(p).stem
        dest = CACHE / "pwb" / "coded" / f"{slug}.py"
        code = (dest.read_bytes() if dest.exists() else
                _get(f"https://raw.githubusercontent.com/{PWB_REPO}/main/{p}", dest)).decode("utf-8", "replace")
        url, desc = _header_comment(code)
        name = slug.replace("-", " ").strip().capitalize()
        f = _fields(desc)
        upsert(conn, {
            "entry_id": entry_id("pwb_coded", slug), "source": "pwb_coded", "strategy_name": name,
            "strategy_family": family_of(name + " " + desc[:300]), "source_type": "PRACTITIONER_RESEARCH",
            "source_title": name, "source_publication": "Quantpedia strategy description, coded in the PWB repo",
            "source_url": url or f"https://github.com/{PWB_REPO}/blob/main/{p}",
            "entry_rules": "see cached source description (not stored: licence not stated)",
            "source_confidence": "MEDIUM", "machine_translatable": "PENDING" if desc else "NON_MACHINE_TESTABLE",
            "translation_notes": ("explicit rule description + QuantConnect implementation available for O4 translation"
                                  if desc else "no rule description found"),
            "licence": "not stated", "raw_cache": str(dest), **f,
            "provenance": {"importer": "pwb_coded", "repo": PWB_REPO, "file": p, "fetched_at": _now(),
                           "sha1": hashlib.sha1(code.encode()).hexdigest()}})
        n += 1
    conn.commit()
    return n


def import_qc_library(conn) -> int:
    paths = [p for p in _tree(QC_REPO, "master") if p.startswith("04 Strategy Library/")]
    by_dir = {}
    for p in paths:
        parts = p.split("/")
        if len(parts) >= 3 and not parts[1].startswith("00 "):
            by_dir.setdefault(parts[1], []).append(p)
    n = 0
    for d, files in sorted(by_dir.items()):
        name = re.sub(r"^\d+\s+", "", d).strip()
        docs = [p for p in files if p.lower().endswith((".html", ".md", ".txt"))]
        text = []
        for p in docs[:12]:
            dest = CACHE / "qc" / d / Path(p).name
            raw = dest.read_bytes() if dest.exists() else _get(
                "https://raw.githubusercontent.com/" + QC_REPO + "/master/" + p.replace(" ", "%20"), dest)
            text.append(re.sub(r"<[^>]+>", " ", raw.decode("utf-8", "replace")))
        body = re.sub(r"\s+", " ", " ".join(text)).strip()
        f = _fields(body)
        upsert(conn, {
            "entry_id": entry_id("qc_library", d), "source": "qc_library", "strategy_name": name,
            "strategy_family": family_of(name + " " + body[:400]), "source_type": "PRACTITIONER_RESEARCH",
            "source_title": name, "source_author": "QuantConnect Strategy Library (and the papers it cites)",
            "source_publication": "QuantConnect Tutorials, 04 Strategy Library",
            "source_url": f"https://github.com/{QC_REPO}/tree/master/04%20Strategy%20Library/{d.replace(' ', '%20')}",
            "source_page_or_section": d, "entry_rules": body[:4000] or None,
            "source_confidence": "MEDIUM", "machine_translatable": "PENDING" if body else "NON_MACHINE_TESTABLE",
            "translation_notes": "documented method + implementation; translation pending (O4)",
            "licence": "Apache-2.0 (QuantConnect/Tutorials)", "raw_cache": str(CACHE / "qc" / d), **f,
            "provenance": {"importer": "qc_library", "repo": QC_REPO, "dir": d, "files": len(files),
                           "fetched_at": _now()}})
        n += 1
    conn.commit()
    return n


def import_stockbot(conn) -> int:
    """The curated research library (Phase 8) as knowledge entries, linked to what was already tested."""
    rows = conn.execute("SELECT entry_id, name, family, original_author, source, publication, original_hypothesis, "
                        "original_universe, original_period, original_metrics, required_data, validation_status, "
                        "faithfulness FROM strategy_library").fetchall()
    n = 0
    for r in rows:
        eid = f"stockbot:{r[0]}"
        upsert(conn, {
            "entry_id": eid, "source": "stockbot", "strategy_name": r[1], "strategy_family": family_of(r[1] + " " + (r[2] or "")),
            "source_type": "ACADEMIC_PAPER" if r[5] else "OPEN_SOURCE", "source_title": r[5] or r[4],
            "source_author": r[3], "source_publication": r[5], "original_claim": r[9], "original_market": r[7],
            "original_time_period": r[8], "required_data": r[10], "source_confidence": "HIGH" if r[5] else "MEDIUM",
            "machine_translatable": "YES", "translation_notes": f"curated Phase 8 entry; faithfulness {r[12]}",
            "generation_method": "PUBLISHED_REPRODUCTION" if r[12] == "FAITHFUL" else "PUBLISHED_VARIANT",
            "licence": "own", "provenance": {"importer": "stockbot", "strategy_library": r[0], "fetched_at": _now()}})
        conn.execute("UPDATE knowledge_entries SET status=? WHERE entry_id=?", (r[11] or "HYPOTHESIS", eid))
        for (k, v) in conn.execute("SELECT strategy_key, version FROM library_strategy_link WHERE entry_id=?", (r[0],)):
            conn.execute("INSERT OR IGNORE INTO knowledge_links VALUES (?,?,?,?,?)",
                         (eid, k, v, "SOURCE_REPRODUCTION", _now()))
        n += 1
    conn.commit()
    return n


IMPORTERS = {"pwb_papers": import_pwb_papers, "pwb_coded": import_pwb_coded, "qc_library": import_qc_library,
             "stockbot": import_stockbot}


def report(conn) -> str:
    L = ["", "  KNOWLEDGE LIBRARY — hypotheses, not results"]
    for src, n, y, p, nm in conn.execute(
            "SELECT source, COUNT(*), SUM(machine_translatable='YES'), SUM(machine_translatable='PENDING'), "
            "SUM(machine_translatable='NON_MACHINE_TESTABLE') FROM knowledge_entries GROUP BY source"):
        L.append(f"  {src:<12} {n:>6,}   translatable {y or 0:>4}   pending {p or 0:>5}   non-testable {nm or 0:>4}")
    L.append("\n  by family (§21):")
    for fam, n in conn.execute("SELECT strategy_family, COUNT(*) FROM knowledge_entries GROUP BY 1 ORDER BY 2 DESC"):
        L.append(f"    {fam:<24} {n:>6,}")
    L.append(f"\n  linked to tested strategies: "
             f"{conn.execute('SELECT COUNT(DISTINCT entry_id) FROM knowledge_links').fetchone()[0]} entries")
    return "\n".join(L)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Knowledge Strategy Library (Stage O1-O2).")
    ap.add_argument("--import", dest="imp", choices=list(IMPORTERS) + ["all"])
    ap.add_argument("--report", action="store_true")
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    cfg = load_config()
    conn = sqlite3.connect(cfg["database"]["market_data_path"], timeout=60)
    init(conn)
    if a.imp:
        for k in (IMPORTERS if a.imp == "all" else [a.imp]):
            log.info(f"{k}: {IMPORTERS[k](conn):,} entries")
    print(report(conn))
    return 0


if __name__ == "__main__":
    sys.exit(main())
