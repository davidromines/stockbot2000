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

**Telegram has no text colour.** There is no way to make the word BUY green; the
API offers bold, italic, code and links, and nothing else. Colour therefore comes
from emoji — a green circle on every buy, a red one on every sell — which renders
identically on every client and needs no parse mode to survive. The orders
themselves are formatted from the JSON spec rather than scraped out of the
terminal report: the report is aligned with spaces for a monospace terminal, and
Telegram's proportional font collapses that alignment into the run-together wall
of text this formatter exists to replace. One order, several short lines, a blank
line between each.

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
    python notify.py --slate --dry-run
"""
import runtime  # noqa: F401
import argparse
import json
import logging
import re
import subprocess
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("notify")

TELEGRAM_KEY = Path.home() / ".telegram"
SLATE = Path("data/orders_today.txt")
SLATE_JSON = Path("data/orders_today.json")

BUY_DOT = "\U0001F7E2"   # green circle
SELL_DOT = "\U0001F534"  # red circle
HOLD_DOT = "\u26AA"      # white circle
RULE = "\u2500" * 18


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


def send_telegram(text: str, parse_mode: str | None = None) -> bool:
    """
    Post one message. `parse_mode` is HTML where the body carries markup.

    A malformed tag makes Telegram reject the whole message with a 400, so a
    parsed send that fails is retried once as plain text with the tags stripped.
    A slate that arrives ugly beats a slate that never arrives.
    """
    c = _telegram_creds()
    if not c:
        return False

    def _post(body, mode):
        payload = {"chat_id": c["chat_id"], "text": body[:4000],
                   "disable_web_page_preview": True}
        if mode:
            payload["parse_mode"] = mode
        r = requests.post(
            f"https://api.telegram.org/bot{c['token']}/sendMessage",
            json=payload, timeout=30)
        if r.status_code != 200:
            log.warning(f"telegram: HTTP {r.status_code} {r.text[:200]}")
        return r.status_code == 200

    try:
        if _post(text, parse_mode):
            return True
        if parse_mode:
            return _post(re.sub(r"<[^>]+>", "", text), None)
        return False
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


def notify(title: str, body: str, html: str | None = None) -> list:
    """
    Send to every configured channel.

    `html` is the Telegram-formatted body where one exists. Desktop popups get
    the plain version: notify-send's markup support varies by daemon, and a
    literal <b> on screen is worse than no bold.
    """
    sent = []
    if send_telegram(f"{title}\n\n{html or body}", "HTML" if html else None):
        sent.append("telegram")
    if send_desktop(title, body):
        sent.append("desktop")
    return sent


def _esc(v) -> str:
    """Escape for Telegram HTML. Tickers are tame; reasons carry <= comparisons."""
    return (str(v).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


def format_slate(spec: dict) -> tuple[str, str]:
    """
    The day's orders as (plain, html).

    One order per block, never one order per line. The previous version sent the
    terminal report's own lines, each carrying ticker, size, venue and stop; on a
    phone those wrap mid-field and five orders become a paragraph. Splitting each
    into a headline and two short detail lines, with a blank line between orders,
    costs vertical space that a phone has and horizontal space it does not.
    """
    P, H = [], []

    def both(plain, html=None):
        P.append(plain); H.append(html if html is not None else _esc(plain))

    size = float(spec.get("size", 0.0))
    both(f"{spec.get('date', '')}  —  ${size:.2f} per position",
         f"<b>{_esc(spec.get('date', ''))}</b>  —  ${size:.2f} per position")
    both("")

    sells = spec.get("sells") or []
    if sells:
        both(f"{SELL_DOT} SELL FIRST — {len(sells)}",
             f"{SELL_DOT} <b>SELL FIRST — {len(sells)}</b>")
        both(RULE)
        for x in sells:
            both("")
            both(f"{SELL_DOT} SELL  {x['ticker']} — entire position",
                 f"{SELL_DOT} SELL  <b>{_esc(x['ticker'])}</b> — entire position")
            pnl = x.get("pnl_pct")
            if pnl is not None:
                both(f"       {pnl:+.1f}% since entry")
            both(f"       {x.get('reason', '')}")
        both("")

    buys = spec.get("buys") or []
    if buys:
        both(f"{BUY_DOT} BUY — {len(buys)}", f"{BUY_DOT} <b>BUY — {len(buys)}</b>")
        both(RULE)
        for x in buys:
            both("")
            both(f"{BUY_DOT} BUY  {x['ticker']}  ${float(x.get('usd', size)):.2f}",
                 f"{BUY_DOT} BUY  <b>{_esc(x['ticker'])}</b>  "
                 f"${float(x.get('usd', size)):.2f}")
            if x.get("stop") is not None:
                both(f"       sell if it closes below ${float(x['stop']):.2f}")
            if x.get("source"):
                both(f"       from: {x['source']}",
                     f"       from: <i>{_esc(x['source'])}</i>")
    elif not sells:
        both("No orders today.")

    keeping = spec.get("keeping") or []
    if keeping:
        both("")
        both(f"{HOLD_DOT} HOLD — {', '.join(keeping)}",
             f"{HOLD_DOT} <b>HOLD</b> — {_esc(', '.join(keeping))}")

    if buys:
        both("")
        both("Stops are checked once a day at the close, not resting at the "
             "broker. A gap through one is not protected.")

    return "\n".join(P), "\n".join(H)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--slate", action="store_true")
    ap.add_argument("--alert")
    ap.add_argument("--test", action="store_true")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the slate as it would be sent, send nothing")
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
        # The JSON spec, not the rendered report: formatting for a phone needs
        # the fields, and parsing them back out of aligned text is a way to be
        # wrong later when the report's layout changes.
        if not SLATE_JSON.exists():
            print("  no slate to send"); return
        spec = json.loads(SLATE_JSON.read_text())
        plain, html = format_slate(spec)
        if a.dry_run:
            print(plain); return
        sent = notify("Stockbot2000 — today's orders", plain, html)
        print(f"  slate sent via: {', '.join(sent) if sent else 'NOTHING configured'}")


if __name__ == "__main__":
    main()
