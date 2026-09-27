"""
The paper pages behind the 3,803 title-only Knowledge Library entries.

Titles alone translate to nothing — the extractor correctly refuses to invent rules
from a title (377 of 377 came back "not translatable", 2026-09-27). Each entry links
to its public page (paperswithbacktest.com/strategies/<slug>; robots.txt allows
/strategies/), which carries the paper's abstract, authors, date, rebalancing and
markets traded. That is enough for a labelled interpretation in many cases.

The page text is cached locally (data/knowledge/pwb/pages/<slug>.txt) and read into
the extractor's PROMPT only — like every cached source whose licence is not stated,
it is never copied into the database; the entry's raw_cache points at the file.
Polite: one request per second, the project's User-Agent, resumable (a cached page is
never refetched). An entry whose earlier translation said "metadata only" is cleared
so the daily cycle translates it again with the page.

    ./venv/bin/python knowledge_pages.py --fetch [--limit N]
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import argparse
import html
import json
import logging
import re
import sqlite3
import sys
import time
from pathlib import Path

log = logging.getLogger("knowledge_pages")
UA = "stockbot2000 research davidromines@gmail.com"
DIR = Path("data/knowledge/pwb/pages")
PAUSE = 1.0
MAX_CHARS = 6000


def page_text(raw: str) -> str:
    """Readable text of a strategy page: scripts and tags stripped, from the title to the
    backtest results (the site's own numbers are the source's claim, kept short)."""
    t = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    t = re.sub(r"\s+", " ", t).strip()
    i = t.find("Home / Trading Strategies /")
    if i >= 0:
        t = t[i + len("Home / Trading Strategies /"):]
    j = t.find("Results from the backtest")
    if j >= 0:
        t = t[:j + 400]
    return t[:MAX_CHARS].strip()


def slug(url: str) -> str | None:
    m = re.search(r"/strategies/([A-Za-z0-9\-_.]+)", url or "")
    return m.group(1) if m else None


def fetch(conn, limit: int | None = None, get=None) -> dict:
    """Fetch every title-only entry's page not yet cached; point its raw_cache at it."""
    import requests
    get = get or (lambda u: requests.get(u, headers={"User-Agent": UA}, timeout=60))
    DIR.mkdir(parents=True, exist_ok=True)
    rows = conn.execute("SELECT entry_id, source_url FROM knowledge_entries WHERE source='pwb_papers' "
                        "ORDER BY entry_id").fetchall()
    out = {"entries": len(rows), "fetched": 0, "cached": 0, "failed": 0, "retranslate": 0}
    n = 0
    for eid, url in rows:
        s = slug(url)
        if not s:
            out["failed"] += 1
            continue
        path = DIR / f"{s}.txt"
        if not path.exists():
            if limit is not None and n >= limit:
                break
            n += 1
            try:
                r = get(url)
                code = getattr(r, "status_code", 200)
                text = page_text(r.text) if code == 200 else ""
            except Exception as e:                             # noqa: BLE001 — one page, not the run
                log.warning(f"{eid}: {type(e).__name__}: {e}")
                text = ""
            time.sleep(PAUSE)
            if len(text) < 200:
                out["failed"] += 1
                continue
            path.write_text(text, encoding="utf-8")
            out["fetched"] += 1
        else:
            out["cached"] += 1
        conn.execute("UPDATE knowledge_entries SET raw_cache=? WHERE entry_id=?", (str(path), eid))
        # A translation made from the title alone is superseded by one made from the page.
        if conn.execute("SELECT 1 FROM sqlite_master WHERE name='knowledge_translations'").fetchone():
            c = conn.execute("DELETE FROM knowledge_translations WHERE entry_id=? AND prompt_version < '5' AND "
                             "machine_translatable='NO' AND genome IS NULL", (eid,)).rowcount
            out["retranslate"] += c
        conn.commit()
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fetch", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    a = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    from universe import load_config
    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=120)
    if a.fetch:
        print(json.dumps(fetch(conn, a.limit), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
