"""
The research queue. Phase 13 §22, §32; used by library_bridge.py (H4) and
discovery.py (H9).

Every idea waiting to become or advance a strategy is one row. Sources:
`library` (research library entries), `template` (factory families),
`human` (a hypothesis typed in), `recycle` (a failed strategy's mutation),
`variant` (a variant of a promising one). Nothing here is deleted; a row
moves queued -> taken -> done | blocked, and the reason stays with it.
"""
import runtime  # noqa: F401  — must precede numpy/pandas
import json
from datetime import datetime, timezone

SOURCES = ("library", "template", "human", "recycle", "variant", "ml", "regime")
STATUSES = ("queued", "taken", "done", "blocked")


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def init(conn) -> None:
    conn.execute("""
        CREATE TABLE IF NOT EXISTS research_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            source      TEXT NOT NULL,
            ref         TEXT NOT NULL,          -- library entry, family, or strategy_key
            family      TEXT,
            strategy_key TEXT,
            version     INTEGER,
            priority    REAL NOT NULL DEFAULT 0,
            status      TEXT NOT NULL DEFAULT 'queued',
            reason      TEXT,
            payload     TEXT,
            created_at  TEXT NOT NULL,
            updated_at  TEXT NOT NULL,
            UNIQUE (source, ref, strategy_key)
        )""")
    conn.commit()


def enqueue(conn, source: str, ref: str, family: str | None = None,
            strategy_key: str | None = None, version: int | None = None,
            priority: float = 0.0, reason: str = "", payload: dict | None = None) -> bool:
    """Idempotent: the same (source, ref, strategy_key) is queued once."""
    init(conn)
    if source not in SOURCES:
        raise ValueError(f"unknown source {source!r}")
    cur = conn.execute(
        "INSERT OR IGNORE INTO research_queue (source, ref, family, strategy_key, version, "
        "priority, reason, payload, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (source, ref, family, strategy_key or "", version, priority, reason,
         json.dumps(payload or {}, default=str), _now(), _now()))
    conn.commit()
    return cur.rowcount == 1


def set_status(conn, item_id: int, status: str, reason: str | None = None) -> None:
    if status not in STATUSES:
        raise ValueError(status)
    conn.execute("UPDATE research_queue SET status=?, reason=COALESCE(?, reason), "
                 "updated_at=? WHERE id=?", (status, reason, _now(), item_id))
    conn.commit()


def reprioritize(conn, item_id: int, priority: float) -> None:
    conn.execute("UPDATE research_queue SET priority=?, updated_at=? WHERE id=?",
                 (priority, _now(), item_id))
    conn.commit()


def pending(conn, limit: int = 50) -> list:
    init(conn)
    cur = conn.execute("SELECT * FROM research_queue WHERE status='queued' "
                       "ORDER BY priority DESC, id LIMIT ?", (limit,))
    cols = [c[0] for c in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def counts(conn) -> dict:
    init(conn)
    return {f"{s}/{st}": n for s, st, n in conn.execute(
        "SELECT source, status, COUNT(*) FROM research_queue GROUP BY source, status")}
