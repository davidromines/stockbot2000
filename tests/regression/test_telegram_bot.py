import runtime  # noqa: F401
import time

import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import killswitch  # noqa: E402
import telegram_bot as tb  # noqa: E402

FAILED = []


def check(name, cond, detail=""):
    if cond:
        print("  PASS  %s" % name)
    else:
        print("  FAIL  %s %s" % (name, detail))
        FAILED.append(name)


def schema(conn):
    conn.executescript(
        """
        CREATE TABLE trader_runs (at TEXT, mode TEXT, outcome TEXT,
                                  positions INTEGER, cash REAL);
        CREATE TABLE slot_trades (id INTEGER PRIMARY KEY, at TEXT, mode TEXT,
                                  slot_id INTEGER, symbol TEXT, action TEXT,
                                  quantity REAL, price REAL);
        """
    )
    conn.execute(
        "INSERT INTO trader_runs VALUES ('2026-09-26T10:00:00+00:00','LIVE','ok',2,41.5)"
    )
    conn.commit()


def update(uid, chat, text, age_s=0, update_id=1):
    ts = int((datetime.now(timezone.utc) - timedelta(seconds=age_s)).timestamp())
    return {
        "update_id": update_id,
        "message": {
            "message_id": 1,
            "date": ts,
            "chat": {"id": chat},
            "from": {"id": uid},
            "text": text,
        },
    }


def main():
    tmp = tempfile.mkdtemp()
    old = (killswitch.KILL_FILE, tb.OFFSET_FILE, tb.PENDING_FILE)
    killswitch.KILL_FILE = Path(tmp) / "KILL_SWITCH"
    tb.OFFSET_FILE = Path(tmp) / "offset.json"
    tb.PENDING_FILE = Path(tmp) / "pending.json"
    try:
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        schema(conn)
        killswitch.init(conn)
        creds = {"token": "t", "chat_id": "555", "user_id": "555"}
        sent = []
        reply = sent.append

        # stranger: different from.id, same chat
        out = tb.handle(conn, update(999, 555, "/kill"), creds, reply=reply)
        check("stranger gets no reply", out is None and sent == [])
        check("stranger changes nothing", not killswitch.KILL_FILE.exists())

        # owner id but a different chat
        out = tb.handle(conn, update(555, 777, "/kill"), creds, reply=reply)
        check("wrong chat refused", out is None and sent == [])

        # no user_id and a group (negative) chat id -> nobody authorized
        group = {"token": "t", "chat_id": "-100200"}
        check("negative chat authorizes nobody", not tb.authorized(update(-100200, -100200, "/help"), group))
        check("missing creds authorize nobody", not tb.authorized(update(1, 1, "/help"), None))

        # /kill alone must not engage
        out = tb.handle(conn, update(555, 555, "/kill"), creds, reply=reply)
        check("/kill asks for confirmation", "confirm" in (out or ""))
        check("/kill alone does not engage", not killswitch.KILL_FILE.exists())

        # confirm within the window
        out = tb.handle(conn, update(555, 555, "/kill confirm"), creds, reply=reply)
        check("/kill confirm engages", killswitch.KILL_FILE.exists() and "engaged" in (out or ""))

        # expired confirm
        tb._write_json(tb.PENDING_FILE, {"action": "kill", "at": (datetime.now(timezone.utc) - timedelta(seconds=121)).isoformat()})
        killswitch.release(conn, "test")
        out = tb.handle(conn, update(555, 555, "/kill confirm"), creds, reply=reply)
        check("expired confirm refused", out == "nothing to confirm" and not killswitch.KILL_FILE.exists())

        # stale message is not executed
        tb._write_json(tb.PENDING_FILE, {"action": "kill", "at": datetime.now(timezone.utc).isoformat()})
        out = tb.handle(conn, update(555, 555, "/kill confirm", age_s=660), creds, reply=reply)
        check("stale command ignored", "minutes old" in (out or "") and not killswitch.KILL_FILE.exists())

        # resume
        killswitch.engage(conn, "test")
        tb.handle(conn, update(555, 555, "/resume"), creds, reply=reply)
        out = tb.handle(conn, update(555, 555, "/resume confirm"), creds, reply=reply)
        check("/resume confirm releases", not killswitch.KILL_FILE.exists())

        # status mentions the kill switch
        out = tb.handle(conn, update(555, 555, "/status"), creds, reply=reply)
        check("/status mentions kill switch", "kill switch" in (out or ""))

        # unknown text
        out = tb.handle(conn, update(555, 555, "/drop tables"), creds, reply=reply)
        check("unknown command refused", "unknown command" in (out or ""))

        # poll persists the offset
        seen = []

        def fake_get(offset, timeout):
            seen.append(offset)
            return [update(555, 555, "/help", update_id=41)] if offset == 0 else []

        tb.poll(conn, creds, seconds=0.2, get_updates=fake_get, reply=reply)
        check("poll persists offset", tb._read_json(tb.OFFSET_FILE, {}).get("offset") == 42)
        tb.poll(conn, creds, seconds=0.2, get_updates=fake_get, reply=reply)
        check("re-run skips handled updates", seen[-1] == 42)

        # /positions renders slot_trader.open_positions' real shape ({slot: position}).
        import slot_trader
        real_op = slot_trader.open_positions
        slot_trader.open_positions = lambda c, m: {1: {"slot_id": 1, "symbol": "SNDK", "quantity": 0.01069,
                                                      "price": 1801.6}}
        try:
            upd = {"update_id": 99, "message": {"message_id": 1, "date": int(time.time()),
                                                 "chat": {"id": 555}, "from": {"id": 555}, "text": "/positions"}}
            out = tb.handle(conn, upd, creds, reply=lambda t: None)
            check("/positions lists the real position dict", "slot 1 SNDK 0.01069 @ 1801.6" in (out or ""), out)
        finally:
            slot_trader.open_positions = real_op
        check("the bot token never reaches a log line",
              tb._scrub("HTTPSConnectionPool: /botSECRET123/getUpdates", {"token": "SECRET123"}).count("SECRET123") == 0)
    finally:
        killswitch.KILL_FILE, tb.OFFSET_FILE, tb.PENDING_FILE = old

    if FAILED:
        print("FAILED: %s" % ", ".join(FAILED))
        return 1
    print("ALL PASS")
    return 0


if __name__ == "__main__":
    sys.exit(main())
