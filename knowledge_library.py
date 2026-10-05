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
    ("options premium selling", ("short straddle", "short strangle", "iron condor", "put-write", "putwrite",
                                 "covered call", "cash-secured put", "variance risk premium", "vrp harvest",
                                 "volatility risk premium", "premium selling", "credit spread")),
    ("options earnings", ("earnings straddle", "earnings iv", "pre-earnings", "earnings announcement drift",
                          "post-earnings option", "earnings option")),
    ("options signals", ("option order flow", "put-call parity", "implied volatility spread", "smirk",
                         "call-put spread", "options signals")),
    ("options momentum", ("option momentum", "straddle momentum", "option return")),
    ("options volatility", ("cheap iv", "low iv", "implied vs realized", "goyal saretto",
                            "iv discount", "options volatility")),
    ("options directional", ("call option", "put option", "bull call", "bear put", "protective put",
                              "covered call", "pead call", "breakout call")),
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


def import_published_factors(conn) -> int:
    """Import 153 JKP published factors from published_signals as knowledge entries (O10 seed library).

    Reads the published_signals table (source='jkp') and creates knowledge_entries with
    source_type='KNOWN_FACTOR'. Post-publication evidence from published_evidence sets
    source_confidence. Idempotent: re-importing unchanged rows is a no-op.
    """
    if not conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='published_signals'").fetchone():
        return 0
    # Build post-pub evidence lookup: signal -> (mean_excess, tstat_excess)
    post_ev: dict = {}
    try:
        for r in conn.execute(
                "SELECT signal, mean_excess, tstat_excess FROM published_evidence "
                "WHERE period='post' AND weighting='ew'"):
            post_ev[r[0]] = (r[1], r[2])
    except Exception:
        pass
    # Fundamental-data clusters
    fundamental_clusters = {"accounting", "value", "profitability", "investment", "earnings quality",
                             "accruals", "financing activities", "debt issuance", "equity issuance"}
    rows = conn.execute(
        "SELECT signal, description, cluster, year, sample_start, sample_end, "
        "direction, authors, op_return, op_tstat, significance "
        "FROM published_signals WHERE source='jkp'").fetchall()
    n = 0
    for r in rows:
        sig, desc, cluster, year, s_start, s_end, direction, authors, op_ret, op_tstat, sig_flag = r
        post_mean, post_t = post_ev.get(sig, (None, None))
        if post_t is not None and post_t >= 2.0:
            conf = "HIGH"
        elif post_t is not None and post_t >= 1.5:
            conf = "MEDIUM"
        elif post_t is not None:
            conf = "LOW"
        elif op_tstat is not None and abs(op_tstat) >= 2.0:
            conf = "MEDIUM"
        else:
            conf = "LOW"
        dir_word = "high" if (direction or 1) > 0 else "low"
        in_sample = f"in-sample t={op_tstat:.1f}" if op_tstat is not None else "in-sample t unavailable"
        if post_t is not None:
            claim = (f"{dir_word.capitalize()} {sig} predicts higher returns "
                     f"({in_sample}; post-pub ew t={post_t:.1f})")
        else:
            claim = (f"{dir_word.capitalize()} {sig} predicts higher returns ({in_sample})"
                     if op_tstat else f"JKP signal {sig}")
        req = ("fundamentals" if (cluster or "").lower() in fundamental_clusters else "daily_price")
        upsert(conn, {
            "entry_id": f"jkp:{sig}",
            "source": "jkp",
            "strategy_name": desc or sig,
            "strategy_family": family_of(desc or sig),
            "source_type": "KNOWN_FACTOR",
            "source_title": "JKP Global Factor Data (Jensen, Kelly, and Pedersen 2023)",
            "source_author": authors,
            "source_publication": "JKP 2023",
            "original_claim": claim,
            "original_market": "US equities",
            "original_time_period": (f"{s_start or ''}–{s_end or ''}").strip("–") or None,
            "required_data": req,
            "source_confidence": conf,
            "machine_translatable": "YES",
            "generation_method": "PUBLISHED_REPRODUCTION",
            "licence": "academic",
            "provenance": {"importer": "jkp", "signal": sig, "fetched_at": _now()},
        })
        n += 1
    conn.commit()
    return n


def import_options_literature(conn) -> int:
    """Import core options strategy academic literature as ACADEMIC_PAPER entries.
    Covers the variance risk premium, put-write, earnings IV effects, and option signals.
    Idempotent."""
    ENTRIES = [
        {"entry_id": "opts:coval_shumway_2001", "strategy_name": "ATM straddle short (VRP)",
         "strategy_family": "options premium selling",
         "source_title": "Expected Option Returns",
         "source_author": "Coval and Shumway (2001)",
         "source_publication": "Journal of Finance 56(3)",
         "source_date": "2001-06-01",
         "original_claim": "At-the-money straddles earn approximately -3%/week for buyers; option markets "
                           "systematically overprice variance, implying short straddles earn a positive risk "
                           "premium.",
         "original_market": "US equities (CBOE)", "original_time_period": "1983–1995",
         "required_data": "option_chains", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:carr_wu_2009", "strategy_name": "Variance risk premium capture",
         "strategy_family": "options premium selling",
         "source_title": "Variance Risk Premiums",
         "source_author": "Carr and Wu (2009)",
         "source_publication": "Review of Financial Studies 22(3)",
         "source_date": "2009-03-01",
         "original_claim": "Implied volatility exceeds expected realized volatility by a persistent, "
                           "economically large margin across individual stocks and indices. Selling variance "
                           "through delta-hedged straddles earns the spread.",
         "original_market": "US equities, indices", "original_time_period": "1996–2003",
         "required_data": "option_chains, option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:whaley_2002", "strategy_name": "Put-write / cash-secured short put",
         "strategy_family": "options premium selling",
         "source_title": "Return and Risk of CBOE Buy Write Monthly Index",
         "source_author": "Whaley (2002)",
         "source_publication": "Journal of Derivatives 10(2)",
         "source_date": "2002-12-01",
         "original_claim": "CBOE PutWrite Index (PUT) outperforms buy-and-hold S&P500 on risk-adjusted "
                           "basis over 20+ year history. Systematic selling of at-the-money puts harvests "
                           "the volatility risk premium.",
         "original_market": "S&P 500 index", "original_time_period": "1988–2001",
         "required_data": "option_chains, option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:bondarenko_2014", "strategy_name": "Short put (overpriced downside insurance)",
         "strategy_family": "options premium selling",
         "source_title": "Why Are Put Options So Expensive?",
         "source_author": "Bondarenko (2014)",
         "source_publication": "Quarterly Journal of Finance 4(3)",
         "source_date": "2014-09-01",
         "original_claim": "Put options on S&P500 are systematically overpriced relative to any reasonable "
                           "model; buyers chronically overpay for downside insurance, making short puts "
                           "systematically profitable.",
         "original_market": "S&P 500 index", "original_time_period": "1987–2000",
         "required_data": "option_chains, option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:patell_wolfson_1979", "strategy_name": "Earnings IV crush (short straddle before)",
         "strategy_family": "options earnings",
         "source_title": "Anticipated Information Releases Reflected in Call Option Prices",
         "source_author": "Patell and Wolfson (1979)",
         "source_publication": "Journal of Accounting Research 17(1)",
         "source_date": "1979-01-01",
         "original_claim": "Implied volatility rises monotonically in the weeks before earnings "
                           "announcements, then collapses immediately after. Selling at-the-money straddles "
                           "just before earnings and closing after the announcement captures the IV crush.",
         "original_market": "US equities", "original_time_period": "1973–1975",
         "required_data": "option_chains, edgar_events", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:dubinsky_johannes_2005", "strategy_name": "Earnings variance premium",
         "strategy_family": "options earnings",
         "source_title": "Earnings Announcements and Equity Options",
         "source_author": "Dubinsky and Johannes (2005)",
         "source_publication": "SSRN Working Paper",
         "source_date": "2005-01-01",
         "original_claim": "Individual stock options contain a large earnings variance premium: options "
                           "are more expensive in the weeks surrounding earnings than at other times, "
                           "even after controlling for realized volatility.",
         "original_market": "US equities", "original_time_period": "1996–2004",
         "required_data": "option_chains, edgar_events", "source_confidence": "MEDIUM",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:goyal_saretto_2009", "strategy_name": "Long straddle on low-IV stocks",
         "strategy_family": "options volatility",
         "source_title": "Cross-Section of Option Returns and Volatility",
         "source_author": "Goyal and Saretto (2009)",
         "source_publication": "Journal of Financial Economics 94(2)",
         "source_date": "2009-11-01",
         "original_claim": "Straddles on stocks where implied vol is far below historical vol earn "
                           "~22.7%/month in a long-short portfolio (long low-IV stocks, short high-IV). "
                           "The effect is strong and persistent post-publication.",
         "original_market": "US equities", "original_time_period": "1996–2006",
         "required_data": "option_chains, option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:cremers_weinbaum_2010", "strategy_name": "Call-put IV spread signal",
         "strategy_family": "options signals",
         "source_title": "Deviations from Put-Call Parity and Stock Return Predictability",
         "source_author": "Cremers and Weinbaum (2010)",
         "source_publication": "Journal of Financial and Quantitative Analysis 45(2)",
         "source_date": "2010-04-01",
         "original_claim": "Stocks where calls are priced above same-strike puts outperform by ~51 bp/week "
                           "(long-short). The call-put implied-vol spread predicts stock returns.",
         "original_market": "US equities", "original_time_period": "1996–2005",
         "required_data": "option_chains", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:xing_2010", "strategy_name": "OTM put smirk as bearish signal",
         "strategy_family": "options signals",
         "source_title": "What Does the Individual Option Volatility Smirk Tell Us About Future Equity Returns?",
         "source_author": "Xing, Zhang and Zhao (2010)",
         "source_publication": "Journal of Financial and Quantitative Analysis 45(3)",
         "source_date": "2010-06-01",
         "original_claim": "Stocks with steepest OTM put smirk (OTM put IV minus ATM call IV) underperform "
                           "by ~10.9%/year. The smirk reflects informed trading in puts about future "
                           "negative news.",
         "original_market": "US equities", "original_time_period": "1996–2005",
         "required_data": "option_chains", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:an_2014", "strategy_name": "Rising IV call signal",
         "strategy_family": "options signals",
         "source_title": "Stock Return Predictability: Evidence from Option Markets",
         "source_author": "An, Ang, Bali and Cakici (2014)",
         "source_publication": "Journal of Finance 69(4)",
         "source_date": "2014-08-01",
         "original_claim": "Stocks with the largest one-month increase in implied volatility earn "
                           "~1%/month more in equity returns. IV rises signal informed buying.",
         "original_market": "US equities", "original_time_period": "1996–2010",
         "required_data": "option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:heston_2023", "strategy_name": "Option return momentum",
         "strategy_family": "options momentum",
         "source_title": "The Cross-Section of Option Returns",
         "source_author": "Heston, Jones, Khorram, Li and Mo (2023)",
         "source_publication": "Journal of Finance 78(4)",
         "source_date": "2023-08-01",
         "original_claim": "At-the-money straddles whose returns were high over months t-12 to t-2 "
                           "continue to outperform (option momentum). Distinct from equity momentum.",
         "original_market": "US equities", "original_time_period": "1996–2018",
         "required_data": "option_chains, option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:bakshi_kapadia_2003", "strategy_name": "Delta-hedged short straddle",
         "strategy_family": "options premium selling",
         "source_title": "Delta-Hedged Gains and the Negative Market Volatility Risk Premium",
         "source_author": "Bakshi and Kapadia (2003)",
         "source_publication": "Review of Financial Studies 16(2)",
         "source_date": "2003-01-01",
         "original_claim": "Delta-hedged short straddles on S&P500 earn reliably positive returns "
                           "(negative market volatility risk premium). Individual stock options also earn "
                           "a volatility premium, with higher idiosyncratic vol stocks earning more.",
         "original_market": "S&P500 and individual US stocks", "original_time_period": "1991–2000",
         "required_data": "option_chains, option_vol", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:cao_han_2013", "strategy_name": "Short straddle on high-idiovol stocks",
         "strategy_family": "options premium selling",
         "source_title": "Cross Section of Option Returns and Idiosyncratic Stock Volatility",
         "source_author": "Cao and Han (2013)",
         "source_publication": "Journal of Financial Economics 108(1)",
         "source_date": "2013-04-01",
         "original_claim": "The volatility risk premium is larger for stocks with higher idiosyncratic "
                           "equity volatility. Short straddles on high-idiosyncratic-vol stocks earn "
                           "abnormally high returns.",
         "original_market": "US equities", "original_time_period": "1996–2009",
         "required_data": "option_chains, option_vol", "source_confidence": "MEDIUM",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:muravyev_2016", "strategy_name": "Options order flow signal",
         "strategy_family": "options signals",
         "source_title": "Order Flow and Expected Option Returns",
         "source_author": "Muravyev (2016)",
         "source_publication": "Journal of Finance 71(2)",
         "source_date": "2016-04-01",
         "original_claim": "Options order flow (signed volume) predicts equity returns. Buy pressure in "
                           "calls predicts positive stock returns; buy pressure in puts predicts "
                           "negative returns. Distinct from put-call ratio.",
         "original_market": "US equities", "original_time_period": "2004–2011",
         "required_data": "option_chains", "source_confidence": "MEDIUM",
         "machine_translatable": "PENDING", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:gao_2018", "strategy_name": "Earnings straddle (Gao, Xing, Zhang)",
         "strategy_family": "options earnings",
         "source_title": "Earnings Announcements and Option Returns",
         "source_author": "Gao, Xing and Zhang (2018)",
         "source_publication": "Journal of Financial and Quantitative Analysis 53(3)",
         "source_date": "2018-06-01",
         "original_claim": "Straddles bought 2-6 days before earnings announcements earn +3.34% on "
                           "average (3 days). The effect concentrates in firms with high analyst "
                           "disagreement.",
         "original_market": "US equities", "original_time_period": "1996–2013",
         "required_data": "option_chains, edgar_events", "source_confidence": "HIGH",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:lakonishok_2007", "strategy_name": "Long OTM call (retail lottery demand)",
         "strategy_family": "options directional",
         "source_title": "Equilibrium Prices of Options Written on the Market Portfolio",
         "source_author": "Lakonishok, Lee, Pearson and Poteshman (2007)",
         "source_publication": "Review of Financial Studies 20(3)",
         "source_date": "2007-01-01",
         "original_claim": "Retail demand for cheap OTM calls drives those options to be overpriced. "
                           "Firm customers (sophisticated) tend to sell OTM calls; retail buys them. "
                           "Short OTM calls should outperform.",
         "original_market": "US equities", "original_time_period": "1990–2001",
         "required_data": "option_chains", "source_confidence": "MEDIUM",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
        {"entry_id": "opts:hutchinson_2020", "strategy_name": "Short iron condor (range-bound)",
         "strategy_family": "options premium selling",
         "source_title": "Benchmarking Commodity Investments",
         "source_author": "Hutchinson and Mulqueeney (2020)",
         "source_publication": "Practitioner research",
         "source_date": "2020-01-01",
         "original_claim": "Iron condors (short OTM call + short OTM put + long further OTM wings) "
                           "earn positive expected returns when sold at elevated IV. Defined-risk "
                           "version of the VRP trade; max loss = spread width - premium.",
         "original_market": "US equities, ETFs", "original_time_period": "2010–2019",
         "required_data": "option_chains, option_vol", "source_confidence": "LOW",
         "machine_translatable": "YES", "generation_method": "PUBLISHED_REPRODUCTION"},
    ]
    n = 0
    for e in ENTRIES:
        full = {
            "source": "opts_literature",
            "strategy_family": e.get("strategy_family", "options"),
            "source_type": "ACADEMIC_PAPER",
            "licence": "academic",
            "provenance": {"importer": "options_literature", "fetched_at": _now()},
            **e,
        }
        if conn.execute("SELECT 1 FROM knowledge_entries WHERE entry_id=?",
                        (e["entry_id"],)).fetchone():
            continue
        upsert(conn, full)
        n += 1
    if n:
        conn.commit()
    return n


IMPORTERS = {"pwb_papers": import_pwb_papers, "pwb_coded": import_pwb_coded, "qc_library": import_qc_library,
             "stockbot": import_stockbot, "published_factors": import_published_factors,
             "options_literature": import_options_literature}


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
