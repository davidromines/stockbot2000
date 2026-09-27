import runtime  # noqa: F401

import json
import os
import sqlite3
import sys
import tempfile
import types
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import digest  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  " + name)
    else:
        print("  FAIL  " + name + ("  " + str(detail) if detail else ""))
        FAILED.append(name)


SCHEMA = """
CREATE TABLE strategy_decisions (at TEXT, strategy_key TEXT, version INTEGER,
    decision TEXT, from_state TEXT, to_state TEXT, reason TEXT);
CREATE TABLE slot_trades (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT, mode TEXT,
    slot_id INTEGER, strategy_key TEXT, version INTEGER, symbol TEXT, action TEXT,
    quantity REAL, price REAL);
CREATE TABLE slot_assignments (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT,
    slot_id INTEGER, action TEXT, strategy_key TEXT, version INTEGER, reason TEXT);
CREATE TABLE ranking_history (date TEXT, strategy_key TEXT, version INTEGER,
    rank INTEGER, score REAL);
CREATE TABLE league_strategies (strategy_key TEXT, version INTEGER, name TEXT);
"""


def make_conn():
    conn = sqlite3.connect(":memory:")
    conn.executescript(SCHEMA)
    return conn


def seed(conn, now):
    this_week = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%S")
    last_week = (now - timedelta(days=10)).strftime("%Y-%m-%dT%H:%M:%S")

    conn.execute(
        "INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol,"
        " action, quantity, price) VALUES (?,?,?,?,?,?,?,?,?)",
        (this_week, "LIVE", 1, "k1", 1, "AAA", "OPEN", 10, 5.0),
    )
    conn.execute(
        "INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol,"
        " action, quantity, price) VALUES (?,?,?,?,?,?,?,?,?)",
        (this_week, "LIVE", 1, "k1", 1, "AAA", "CLOSE", 10, 6.0),
    )
    # last week's round trip must not be counted
    conn.execute(
        "INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol,"
        " action, quantity, price) VALUES (?,?,?,?,?,?,?,?,?)",
        (last_week, "LIVE", 2, "k2", 1, "BBB", "OPEN", 5, 10.0),
    )
    conn.execute(
        "INSERT INTO slot_trades (at, mode, slot_id, strategy_key, version, symbol,"
        " action, quantity, price) VALUES (?,?,?,?,?,?,?,?,?)",
        (last_week, "LIVE", 2, "k2", 1, "BBB", "CLOSE", 5, 20.0),
    )

    for state in ("PAPER", "PAPER", "REJECTED", "QUALIFIED"):
        conn.execute(
            "INSERT INTO strategy_decisions (at, strategy_key, version, decision,"
            " from_state, to_state, reason) VALUES (?,?,?,?,?,?,?)",
            (this_week, "k1", 1, "d", "X", state, "r"),
        )
    conn.execute(
        "INSERT INTO strategy_decisions (at, strategy_key, version, decision,"
        " from_state, to_state, reason) VALUES (?,?,?,?,?,?,?)",
        (last_week, "k9", 1, "d", "X", "REJECTED", "r"),
    )

    conn.execute(
        "INSERT INTO slot_assignments (at, slot_id, action, strategy_key, version,"
        " reason) VALUES (?,?,?,?,?,?)",
        (this_week, 3, "ASSIGN", "k1", 1, "promoted"),
    )
    conn.execute(
        "INSERT INTO league_strategies (strategy_key, version, name) VALUES (?,?,?)",
        ("k1", 1, "Alpha Fund"),
    )

    conn.execute(
        "INSERT INTO ranking_history (date, strategy_key, version, rank, score)"
        " VALUES (?,?,?,?,?)",
        ("2026-09-20", "k1", 1, 1, 0.5),
    )
    for i in range(6):
        conn.execute(
            "INSERT INTO ranking_history (date, strategy_key, version, rank, score)"
            " VALUES (?,?,?,?,?)",
            ("2026-09-26", "k%d" % i, 1, i + 1, 1.0 - i * 0.1),
        )
    conn.commit()


def write_data(root, funnel=True, knowledge=True):
    data = os.path.join(root, "data")
    os.makedirs(data, exist_ok=True)
    if funnel:
        with open(os.path.join(data, "funnel.json"), "w") as fh:
            json.dump(
                {
                    "as_of": "2026-09-26",
                    "market": {
                        "unseen": {"tested": 40, "net_positive": 3, "above_random": 2},
                        "checks": {"bear_market": {"PASS": 1, "FAIL": 0, "NA": 0}},
                    },
                    "failures": [
                        {"strategy_key": "a", "reasons": ["x"], "near_miss": True},
                        {"strategy_key": "b", "reasons": ["y"], "near_miss": False},
                    ],
                },
                fh,
            )
    if knowledge:
        with open(os.path.join(data, "knowledge_factory.json"), "w") as fh:
            json.dump(
                {
                    "entries": 5,
                    "translated": 4,
                    "translated_yes": 3,
                    "requiring_interpretation": 1,
                    "reproductions": 2,
                    "variants": 7,
                    "lineages": 1,
                },
                fh,
            )


def main():
    now = datetime(2026, 9, 27, 12, 0, tzinfo=timezone.utc)
    tmp = tempfile.mkdtemp()
    write_data(tmp)
    conn = make_conn()
    seed(conn, now)

    d = digest.collect(conn, now=now, root=tmp)
    check("live net from paired OPEN/CLOSE", d["live"]["net_usd"] == 10.0, d["live"])
    check("live closed count is 1", d["live"]["closed"] == 1, d["live"])
    check("live wins is 1", d["live"]["wins"] == 1, d["live"])
    check(
        "pipeline counted by to_state",
        d["pipeline"] == {"entered_paper": 2, "rejected": 1, "qualified": 1},
        d["pipeline"],
    )
    check("slot change carries strategy name", d["slots"][0]["strategy"] == "Alpha Fund", d["slots"])
    check("top 5 from newest date", len(d["top"]) == 5 and d["top"][0][1] == 1.0, d["top"])
    check("knowledge section loaded", d["knowledge"]["translated"] == 4, d["knowledge"])
    check("near misses counted", d["funnel"]["near_misses"] == 1, d["funnel"])

    text = digest.render(d)
    low = text.lower()
    check(
        "no banned words",
        not any(w in low for w in ("fee", "fees", "spread", "cost", "costs")),
        text,
    )
    check("ends with evidence line", text.rstrip().endswith("Evidence, not advice."), text)

    empty = tempfile.mkdtemp()
    d2 = digest.collect(conn, now=now, root=empty)
    check("missing json omits sections", d2["knowledge"] is None and d2["funnel"] is None, d2)
    digest.render(d2)

    calls = []
    fake = types.ModuleType("notify")
    fake.notify = lambda title, body: calls.append((title, body))
    sys.modules["notify"] = fake
    out = digest.send(conn, now=now, root=tmp)
    check("send calls notify once", len(calls) == 1, calls)
    check("send returns rendered text", out == digest.render(d), out)
    calls.clear()
    digest.send(conn, now=now, root=tmp, dry_run=True)
    check("dry_run does not notify", len(calls) == 0, calls)

    conn.close()
    if FAILED:
        print("FAILED: " + ", ".join(FAILED))
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
