"""Regression tests for signal_activity.all_slots."""
import runtime  # noqa: F401

import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import signal_activity as sa

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print(f"  PASS  {name}")
    else:
        print(f"  FAIL  {name}  {detail}")
        FAILED.append(name)


def _db():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """CREATE TABLE slot_assignments (
               id INTEGER PRIMARY KEY AUTOINCREMENT,
               at TEXT NOT NULL, slot_id INTEGER NOT NULL, action TEXT NOT NULL,
               strategy_key TEXT, version INTEGER, capital_usd REAL,
               mode TEXT, reason TEXT)"""
    )
    conn.execute(
        """CREATE TABLE strategy_objects (
               strategy_key TEXT NOT NULL, version INTEGER NOT NULL,
               family TEXT, PRIMARY KEY (strategy_key, version))"""
    )
    return conn


def _assign(conn, at, slot_id, action, key, version):
    conn.execute(
        "INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version) "
        "VALUES (?, ?, ?, ?, ?)",
        (at, slot_id, action, key, version),
    )


def main():
    conn = _db()
    _assign(conn, "2026-09-01T00:00:00", 1, "ASSIGN", "fx_aaa", 1)
    _assign(conn, "2026-09-02T00:00:00", 2, "ASSIGN", "fx_bbb", 3)
    # A later ASSIGN for slot 1 must win over the earlier one.
    _assign(conn, "2026-09-03T00:00:00", 1, "ASSIGN", "fx_ccc", 2)
    # A non-ASSIGN row must not be treated as a holder.
    _assign(conn, "2026-09-04T00:00:00", 3, "RELEASE", "fx_ddd", 1)
    conn.execute(
        "INSERT INTO strategy_objects (strategy_key, version, family) VALUES (?, ?, ?)",
        ("fx_ccc", 2, "earnings_surprise"),
    )
    conn.execute(
        "INSERT INTO strategy_objects (strategy_key, version, family) VALUES (?, ?, ?)",
        ("fx_bbb", 3, "etf_rotation"),
    )
    conn.commit()

    # activity() would hit the real genome/paper_trading stack; stub it so the
    # test exercises slot resolution only.
    orig = sa.activity
    sa.activity = lambda conn, cfg, key, version, **kw: {
        "key": key, "version": version, "measurable": True,
        "active_sessions": 0, "last_signal": None,
    }
    try:
        out = sa.all_slots(conn, {})
    finally:
        sa.activity = orig

    check("returns five entries", len(out) == 5, len(out))
    check("slot ids 1..5", [e["slot_id"] for e in out] == [1, 2, 3, 4, 5],
          [e["slot_id"] for e in out])
    check("slot 1 latest ASSIGN wins", out[0]["strategy_key"] == "fx_ccc", out[0])
    check("slot 1 version", out[0]["version"] == 2, out[0])
    check("slot 1 family", out[0]["family"] == "earnings_surprise", out[0])
    check("slot 2 key", out[1]["strategy_key"] == "fx_bbb", out[1])
    check("slot 2 family", out[1]["family"] == "etf_rotation", out[1])
    check("slot 3 RELEASE is not a holder", out[2]["strategy_key"] is None, out[2])
    for i in (2, 3, 4):
        check(f"slot {i + 1} empty", out[i]["strategy_key"] is None, out[i])
        check(f"slot {i + 1} version None", out[i]["version"] is None, out[i])
        check(f"slot {i + 1} family None", out[i]["family"] is None, out[i])
    check("occupied slot merges activity", out[0]["measurable"] is True, out[0])

    if FAILED:
        print(f"\n{len(FAILED)} FAILED")
        sys.exit(1)
    print("\nALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
