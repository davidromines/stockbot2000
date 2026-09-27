"""Telegram command listener for Stockbot2000.

Security model
--------------
* Owner-only.  An update is authorized only when BOTH the chat id and the
  sender id match the configured owner.  If the owner id cannot be derived
  (no ``user_id`` line and a non-positive ``chat_id``) nothing is authorized:
  the bot fails closed rather than guessing.
* Message text is data, never code.  Nothing in a message is eval'd, exec'd,
  imported or passed to a shell.
* No order commands exist.  This module never places, modifies or cancels an
  order; the only state it can change is the file kill switch, and only after
  an explicit two-step confirmation.
* Stale commands are ignored.  A message older than STALE_S is reported and
  dropped, so a replayed or delayed update cannot trigger an action.
* Unauthorized updates are recorded (without their text) and never answered.
"""

import runtime  # noqa: F401  (thread limits must be set before numpy/pandas)

import argparse
import json
import sqlite3
import sys
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

import requests

import control_center_extra
import eod_report
import killswitch
import notify
import slot_trader
from universe import load_config
import timefmt

OFFSET_FILE = Path("data/telegram_offset.json")
PENDING_FILE = Path("data/telegram_pending.json")
STALE_S = 600
CONFIRM_S = 120
MAX_REPLY = 4000
API = "https://api.telegram.org/bot{token}/{method}"

HELP = (
    "/help - this list\n"
    "/status - kill switch, latest LIVE run, open LIVE slot positions\n"
    "/positions - open LIVE slot positions\n"
    "/health - strategy health counts and data age\n"
    "/report - end-of-day report\n"
    "/kill - request a stop (needs /kill confirm)\n"
    "/resume - request a resume (needs /resume confirm)"
)


def _utcnow():
    return datetime.now(timezone.utc)


def _iso(dt):
    return dt.astimezone(timezone.utc).isoformat()


def _read_json(path, default):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def _write_json(path, payload):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(payload, fh)
    tmp.replace(path)


def owner_id(creds):
    """The owner's user id, or None when it cannot be established.

    A private chat's id IS the user's id, so a positive chat_id is a valid
    fallback; a negative chat_id means a group, where the chat id says nothing
    about who is speaking, so we refuse to authorize anyone.
    """
    if not creds:
        return None
    if creds.get("user_id") not in (None, ""):
        try:
            return int(creds["user_id"])
        except (TypeError, ValueError):
            return None
    try:
        chat_id = int(creds["chat_id"])
    except (KeyError, TypeError, ValueError):
        return None
    return chat_id if chat_id > 0 else None


def authorized(update, creds):
    uid = owner_id(creds)
    if uid is None:
        return False
    try:
        chat_id = int(creds["chat_id"])
        msg = update["message"]
        return int(msg["chat"]["id"]) == chat_id and int(msg["from"]["id"]) == uid
    except (KeyError, TypeError, ValueError):
        return False


def _send(creds, text):
    token = creds["token"]
    url = API.format(token=token, method="sendMessage")
    requests.post(
        url,
        json={"chat_id": creds["chat_id"], "text": text[:MAX_REPLY]},
        timeout=20,
    )


def _positions(conn):
    try:
        rows = slot_trader.open_positions(conn, "LIVE")
    except Exception as exc:  # a status command must never take the bot down
        return ["positions unavailable: %s" % exc]
    out = []
    # open_positions returns {slot_id: position}; a list is accepted too.
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    for row in rows or []:
        try:
            out.append(
                "slot %s %s %s @ %s"
                % (row["slot_id"], row["symbol"], row["quantity"], row["price"])
            )
        except (KeyError, TypeError):
            out.append(str(row))
    return out or ["no open LIVE positions"]


def _status(conn):
    reason = killswitch.global_engaged()
    lines = ["kill switch: %s" % (reason if reason else "clear")]
    row = conn.execute(
        "SELECT at, outcome, positions, cash FROM trader_runs"
        " WHERE mode = 'LIVE' ORDER BY at DESC LIMIT 1"
    ).fetchone()
    if row is None:
        lines.append("no LIVE trader runs recorded")
    else:
        lines.append(
            "last LIVE run %s outcome=%s positions=%s cash=%s"
            % (timefmt.pt(row["at"]), row["outcome"], row["positions"], row["cash"])
        )
    lines.extend(_positions(conn))
    return "\n".join(lines)


def _health(conn):
    try:
        counts = control_center_extra.health_view(conn).get("counts", {})
    except Exception as exc:
        return "health unavailable: %s" % exc
    lines = ["strategy health: " + ", ".join("%s=%s" % kv for kv in sorted(counts.items()))]
    row = conn.execute("SELECT MAX(at) AS at FROM trader_runs").fetchone()
    if row is None or row["at"] is None:
        lines.append("no trader runs recorded")
    else:
        try:
            age = (_utcnow() - datetime.fromisoformat(row["at"])).total_seconds() / 60.0
            lines.append("newest trader run %.1f minutes old" % age)
        except ValueError:
            lines.append("newest trader run at %s" % timefmt.pt(row["at"]))
    return "\n".join(lines)


def _report(conn, now):
    today = now.astimezone(timezone.utc).date().isoformat()
    return eod_report.render(eod_report.build(conn, today, "LIVE", rank_fn=None))


def _pending_action(conn, now, action):
    """Consume a fresh pending request, or explain why there is nothing to do."""
    pending = _read_json(PENDING_FILE, None)
    if not pending or pending.get("action") != action:
        return "nothing to confirm"
    try:
        requested = datetime.fromisoformat(pending["at"])
    except (KeyError, ValueError):
        return "nothing to confirm"
    if (now - requested).total_seconds() > CONFIRM_S:
        return "nothing to confirm"
    _write_json(PENDING_FILE, {})
    if action == "kill":
        killswitch.engage(conn, "telegram /kill by owner at %s" % _iso(now))
        return (
            "kill switch engaged. Trading stops and slot positions are flattened"
            " at the next market-hours run. /resume confirm to restart."
        )
    if killswitch.release(conn, "telegram /resume by owner at %s" % _iso(now)):
        return "kill switch released. Trading resumes at the next market-hours run."
    return "kill switch was already clear."


def handle(conn, update, creds, now=None, reply=None):
    now = now or _utcnow()
    reply = reply or (lambda text: _send(creds, text))
    if not authorized(update, creds):
        # Record the attempt without the text: an unauthorized sender's words
        # are not ours to store.
        killswitch.record_event(
            conn, "telegram_ignored", "unauthorized update %s" % update.get("update_id"), "info"
        )
        return None

    msg = update["message"]
    text = (msg.get("text") or "").strip()
    try:
        age = (now - datetime.fromtimestamp(int(msg["date"]), timezone.utc)).total_seconds()
    except (KeyError, TypeError, ValueError):
        age = 0.0
    if age > STALE_S:
        out = "ignored: command was %d minutes old" % round(age / 60.0)
        killswitch.record_event(conn, "telegram_command", "stale: %s" % text, "info")
        reply(out)
        return out

    low = text.lower()
    if low == "/help":
        out = HELP
    elif low == "/status":
        out = _status(conn)
    elif low == "/positions":
        out = "\n".join(_positions(conn))
    elif low == "/health":
        out = _health(conn)
    elif low == "/report":
        out = _report(conn, now)
    elif low == "/kill":
        _write_json(PENDING_FILE, {"action": "kill", "at": _iso(now)})
        out = (
            "Reply /kill confirm within 2 minutes to stop all trading and flatten"
            " slot positions at the next market-hours run."
        )
    elif low == "/kill confirm":
        out = _pending_action(conn, now, "kill")
    elif low == "/resume":
        _write_json(PENDING_FILE, {"action": "resume", "at": _iso(now)})
        out = "Reply /resume confirm within 2 minutes to release the kill switch."
    elif low == "/resume confirm":
        out = _pending_action(conn, now, "resume")
    else:
        out = "unknown command — /help"

    killswitch.record_event(conn, "telegram_command", text[:200], "info")
    reply(out)
    return out


def _scrub(text, creds):
    token = (creds or {}).get("token") or ""
    return text.replace(token, "<token>") if token else text


def _get_updates(creds, offset, timeout):
    url = API.format(token=creds["token"], method="getUpdates")
    resp = requests.get(
        url, params={"offset": offset, "timeout": timeout}, timeout=timeout + 10
    )
    return resp.json().get("result", [])


def poll(conn, creds, seconds=55, get_updates=None, reply=None):
    get_updates = get_updates or (lambda offset, timeout: _get_updates(creds, offset, timeout))
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        offset = _read_json(OFFSET_FILE, {}).get("offset", 0)
        try:
            updates = get_updates(offset, 25)
        except Exception as exc:
            # The request URL carries the bot token: never let it reach a log.
            print("telegram poll error: %s" % _scrub(str(exc), creds), file=sys.stderr)
            time.sleep(2)
            continue
        for update in updates or []:
            try:
                handle(conn, update, creds, reply=reply)
            except Exception as exc:
                print("telegram handle error: %s" % _scrub(str(exc), creds), file=sys.stderr)
            # Persist after EACH update so a crash cannot replay a handled one.
            _write_json(OFFSET_FILE, {"offset": int(update["update_id"]) + 1})


def main(argv=None):
    parser = argparse.ArgumentParser(description="Telegram command listener")
    parser.add_argument("--poll", action="store_true")
    parser.add_argument("--seconds", type=int, default=55)
    args = parser.parse_args(argv)

    creds = notify._telegram_creds()
    if not creds:
        print("no telegram credentials in ~/.telegram; nothing to do")
        return 0
    if not args.poll:
        print("nothing to do without --poll")
        return 0

    conn = sqlite3.connect(load_config()["database"]["market_data_path"], timeout=30)
    conn.row_factory = sqlite3.Row
    try:
        poll(conn, creds, seconds=args.seconds)
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
