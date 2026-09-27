"""
knowledge_pages.py and parallel extraction: a strategy page becomes readable text from the
title to the backtest results; a title-only entry points at its cached page and its
title-only "not translatable" answer is cleared for retranslation; a cached page is never
refetched; knowledge_extract.run with workers gives the same result as one worker.
Fake HTTP and model; in-memory database.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
import os
import sqlite3
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from pathlib import Path

import knowledge_extract as ke
import knowledge_library as kl
import knowledge_pages as kp

FAILED = []
PAGE = ("<html><script>var x=1;</script><body>Nav Home / Trading Strategies / Value in Crashes "
        "<p>We sort stocks on book-to-market and hold the top decile for a month.</p> Strategy characteristics "
        "Rebalancing Monthly Markets traded Equities " + "x " * 120 + "Results from the backtest Net worth 1</body>")


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


class R:
    def __init__(self, text, code=200):
        self.text, self.status_code = text, code


class Model:
    def complete(self, system, user, max_tokens=2000, temperature=0.0):
        g = {"entry": {"op": "gt", "args": [{"op": "rank", "args": [{"col": "book_to_market"}]}, {"const": 0.9}]},
             "exit": {"op": "lt", "args": [{"col": "close"}, {"const": 0}]},
             "risk": {"stop_atr_multiple": 3.0, "max_hold_days": 21}}
        body = {"fields": {f: "stated" for f in ke.FIELDS}, "genome": g, "assumptions": [], "ambiguities": [],
                "missing_information": [], "translation_confidence": 0.5, "family": "VALUE", "data_available": "YES"}
        if "PROPOSED GENOME" in user:
            body = {"ok": True, "problems": [], "genome": g}
        r = type("Resp", (), {})()
        r.text, r.model, r.prompt_tokens, r.completion_tokens = "```json\n" + json.dumps(body) + "\n```", "m", 1, 1
        return r


def main():
    t = kp.page_text(PAGE)
    check("page text keeps the abstract, drops scripts and navigation",
          "book-to-market" in t and "var x" not in t and not t.startswith("Nav"), t[:80])
    check("slug from the entry's URL", kp.slug("https://paperswithbacktest.com/strategies/value-in-crashes") == "value-in-crashes")
    kp.DIR = Path(tempfile.mkdtemp())
    kp.PAUSE = 0
    c = sqlite3.connect(":memory:")
    c.row_factory = sqlite3.Row
    kl.init(c); ke.init(c)
    for i in range(6):
        kl.upsert(c, {"entry_id": f"pwb_papers:{i}", "source": "pwb_papers", "strategy_name": f"P{i}",
                      "source_type": "ACADEMIC_PAPER", "source_title": f"Paper {i}",
                      "source_url": f"https://paperswithbacktest.com/strategies/p{i}", "provenance": {}})
    c.execute("INSERT INTO knowledge_translations (entry_id, prompt_version, machine_translatable, genome) "
              "VALUES ('pwb_papers:0', '4', 'NO', NULL)")
    c.commit()
    calls = []
    out = kp.fetch(c, get=lambda u: calls.append(u) or R(PAGE))
    check("every page fetched and cached", out["fetched"] == 6 and len(calls) == 6, out)
    check("the entry points at its cached page",
          c.execute("SELECT raw_cache FROM knowledge_entries WHERE entry_id='pwb_papers:3'").fetchone()[0].endswith("p3.txt"))
    check("the title-only NO answer is cleared for retranslation", out["retranslate"] == 1 and
          not c.execute("SELECT 1 FROM knowledge_translations WHERE entry_id='pwb_papers:0'").fetchone())
    again = kp.fetch(c, get=lambda u: calls.append(u) or R(PAGE))
    check("a cached page is never refetched", again["fetched"] == 0 and len(calls) == 6, again)
    check("the page text reaches the prompt", "book-to-market" in ke.build_prompt(
        dict(c.execute("SELECT * FROM knowledge_entries WHERE entry_id='pwb_papers:1'").fetchone()))[1])
    r = ke.run(c, Model(), limit=10, workers=4)
    check("parallel extraction translates every entry", r["translated"] == 6 and r["yes"] == 6 and r["errors"] == 0, r)
    check("all rows written", c.execute("SELECT COUNT(*) FROM knowledge_translations").fetchone()[0] == 6)
    print()
    if FAILED:
        print(f"  {len(FAILED)} FAILED")
        return 1
    print("  ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
