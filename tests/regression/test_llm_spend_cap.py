"""
llm/provider.py daily spend cap: a DeepSeek call is refused once today's recorded spend
(llm_calls, UTC day) reaches ado.daily_cap_usd; yesterday's spend does not count; no cap
set means no refusal; a database without llm_calls counts as zero. No network: the
refusal happens before any request is built, and the uncapped path is checked by
catching the missing-key error that comes after the cap check.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from llm import provider as lp

FAILED = []


def check(name, cond, detail=""):
    print(("  PASS  " if cond else "  FAIL  ") + name + ("" if cond else f"  [{detail}]"))
    if not cond:
        FAILED.append(name)


def add(conn, at, cost):
    conn.execute("""INSERT INTO llm_calls (at, task_id, purpose, provider, model,
        prompt_tokens, completion_tokens, cost_usd, latency_s, ok)
        VALUES (?,NULL,'t','deepseek','m',1,1,?,0.1,1)""", (at, cost))
    conn.commit()


with tempfile.TemporaryDirectory() as d:
    db = Path(d) / "m.db"
    check("missing database counts as zero", lp.spent_today(db) == 0.0)
    conn = sqlite3.connect(db)
    check("database without llm_calls counts as zero", lp.spent_today(db) == 0.0)
    conn.row_factory = sqlite3.Row
    lp.init(conn)
    now = datetime.now(timezone.utc)
    add(conn, (now - timedelta(days=1)).isoformat(), 5.0)
    add(conn, now.isoformat(), 0.40)
    check("only today's spend counts", abs(lp.spent_today(db) - 0.40) < 1e-9, lp.spent_today(db))

    missing_key = Path(d) / "no_key"
    p = lp.DeepSeekProvider(daily_cap_usd=0.50, db_path=db, key_file=missing_key)
    try:
        p.complete("s", "u")
        check("under the cap proceeds past the check", False, "no error")
    except lp.SpendCapReached:
        check("under the cap proceeds past the check", False, "refused")
    except lp.LLMError as e:
        check("under the cap proceeds past the check", "not found" in str(e), e)

    add(conn, now.isoformat(), 0.10)
    try:
        p.complete("s", "u")
        check("at the cap the call is refused", False, "not refused")
    except lp.SpendCapReached as e:
        check("at the cap the call is refused", "0.50" in str(e), e)

    free = lp.DeepSeekProvider(daily_cap_usd=None, db_path=db, key_file=missing_key)
    try:
        free.complete("s", "u")
    except lp.SpendCapReached:
        check("no cap never refuses", False)
    except lp.LLMError:
        check("no cap never refuses", True)

    got = lp.get_provider({"ado": {"provider": "deepseek", "model": "x", "daily_cap_usd": 1.25}})
    check("get_provider passes the configured cap", got.daily_cap_usd == 1.25, got.daily_cap_usd)
    conn.close()

sys.exit(1 if FAILED else 0)
