"""
Push the morning slate somewhere you will actually see it.

The daily job writes files to disk. That is fine for a machine and useless for a
person: a report nobody reads has the same value as no report. This sends the
slate through whatever channels are configured, and says clearly when none are.

Channels, in order of usefulness:

  telegram   Needs ~/.telegram (token + chat_id). Reaches your phone, which is
             the only channel that works when you are not at this machine — and
             you are usually not at this machine.
  desktop    notify-send, a popup on the XFCE desktop. Works with no setup, but
             only if someone is looking at that screen.
  file       Always written. data/orders_today.txt, for `cat` on login.

Alerts matter more than the daily slate, and this is deliberately built to carry
both. This project's characteristic failure is silence: the daily capture would
have broken every morning from a classifier mismatch and nobody would have known;
the search loop stalled for three hours unnoticed; the database corrupted itself
without a word. A morning report you read for a week and then ignore is worth
less than a message that arrives only when something is wrong.

Usage:
    python notify.py --slate            # send today's orders
    python notify.py --alert "text"     # send a breakage alert
    python notify.py --test
"""
import runtime  # noqa: F401
import argparse
import logging
import subprocess
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("notify")

TELEGRAM_KEY = Path.home() / ".telegram"
SLATE = Path("data/orders_today.txt")


def _telegram_creds():
    """Token and chat id from a 0600 file outside the repo, never from config."""
    if not TELEGRAM_KEY.exists():
        return None
    creds = {}
    for line in TELEGRAM_KEY.read_text().splitlines():
        if ":" in line:
            k, _, v = line.partition(":")
            creds[k.strip().lower()] = v.strip()
    if creds.get("token") and creds.get("chat_id"):
        return creds
    return None


def send_telegram(text: str) -> bool:
    c = _telegram_creds()
    if not c:
        return False
    try:
        r = requests.post(
            f"https://api.telegram.org/bot{c['token']}/sendMessage",
            json={"chat_id": c["chat_id"], "text": text[:4000],
                  "disable_web_page_preview": True},
            timeout=30)
        return r.status_code == 200
    except requests.RequestException as e:
        log.warning(f"telegram: {type(e).__name__}")
        return False


def send_desktop(title: str, body: str) -> bool:
    """
    XFCE desktop popup. Needs DISPLAY, which cron does not provide by default —
    hence the explicit environment. Silently pointless if nobody is at the screen,
    which is why it is never the only channel.
    """
    try:
        subprocess.run(["notify-send", "-u", "normal", "-t", "20000", title, body[:400]],
                       env={"DISPLAY": ":0", "DBUS_SESSION_BUS_ADDRESS":
                            f"unix:path=/run/user/{__import__('os').getuid()}/bus",
                            "PATH": "/usr/bin:/bin"},
                       timeout=15, capture_output=True)
        return True
    except Exception:
        return False


def notify(title: str, body: str) -> list:
    sent = []
    if send_telegram(f"{title}\n\n{body}"):
        sent.append("telegram")
    if send_desktop(title, body):
        sent.append("desktop")
    return sent


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slate", action="store_true")
    ap.add_argument("--alert")
    ap.add_argument("--test", action="store_true")
    a = ap.parse_args()

    if a.test:
        sent = notify("Stockbot2000", "Test message. If you can read this, the "
                                      "channel works.")
        print(f"  sent via: {', '.join(sent) if sent else 'NOTHING — no channel configured'}")
        if not _telegram_creds():
            print(f"\n  Telegram is not set up. To enable it:")
            print(f"    1. Message @BotFather on Telegram, send /newbot")
            print(f"    2. Message your new bot once, then open")
            print(f"       https://api.telegram.org/bot<TOKEN>/getUpdates to find chat_id")
            print(f"    3. printf 'token: X\\nchat_id: Y\\n' > {TELEGRAM_KEY} "
                  f"&& chmod 600 {TELEGRAM_KEY}")
        return

    if a.alert:
        sent = notify("Stockbot2000 ALERT", a.alert)
        print(f"  alert sent via: {', '.join(sent) or 'nothing'}")
        return

    if a.slate:
        if not SLATE.exists():
            print("  no slate to send"); return
        text = SLATE.read_text()
        # Just the actionable lines. A phone notification should be readable
        # without scrolling; the full report is on disk for anyone who wants it.
        lines = [l for l in text.splitlines()
                 if l.strip().startswith(("BUY", "SELL")) or "order(s)" in l
                 or l.strip().startswith("ORDERS")]
        body = "\n".join(lines[:20]) or "no orders today"
        sent = notify("Stockbot2000 — today's orders", body)
        print(f"  slate sent via: {', '.join(sent) if sent else 'NOTHING configured'}")


if __name__ == "__main__":
    main()
